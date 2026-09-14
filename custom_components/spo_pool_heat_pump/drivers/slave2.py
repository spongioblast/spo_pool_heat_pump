"""Behave as the second display panel (slave 2) on a PC1002 bus.

The main board is the Modbus master. Each cycle it polls slave 1 (the wired
display), slave 2 (an optional second display) and slave 66 for their 3001×30
status page, then broadcasts the 2001×90 status page. It pushes the settings
pages 1001 / 1091 / 1181 ×90 and 3001×11 (serial + flags) to every slave that
answers, and expects the normal FC16 echo (``slave 16 start qty``) as an ack —
the display acks within ~30 ms, the WiFi module within ~80 ms. A slave that
never acks is retried twice per cycle, forever (live dump 20260914_103324:
the cycle stretched from 1.7 s to 6.7 s), and its settings are ignored.

A panel changes a setting by raising a bit in word 3011 of its 3001 reply. The
board then reads that page back from the panel ~0.35 s later, applies it,
pushes the new page to all slaves and writes 3001×11 with flags 0 to clear.
Bits measured on the real display (dumps 2026-09-04 … 09-06, 13 events):

* ``0x0004`` → board reads 1001×90 (4/4); the page diff was 1011 / 1016 / 1068-1069
* ``0x0020`` → board reads 1091×90 (6/6); the page diff was always timers 1150-1159
* ``0x0040`` → board reads 1091×90 (2/2); the page diff was the setpoint 1136
* ``0x8000`` → seen once, board read nothing. Never send it.

The bit says *what* changed, not just which page. Live test 2026-09-14: a
setpoint written with ``0x0020`` made the board re-read 1091 from the wired
display as well and keep the display's copy — the write was dropped. Setpoints
(1135-1137) must go with ``0x0040``; ``0x0020`` is for the timer words. Other
1091 words have never been changed from a panel in any dump.

No bit for page 1181 was ever observed; writes there are overlaid but only
reach the board if it reads that page for another reason.

Never answer 1001/1091/1181 until that page is seeded — a zero page would wipe
the menu. Pages are seeded from the board's own pushes (any slave) or from a
FC03 read of the display.
"""

from __future__ import annotations

import time

from ..modbus_rtu import RtuFrame, encode_fc03_reply, encode_fc16_reply
from .settings import is_blank_menu_page

FLAG_READ_1001 = 0x0004
FLAG_READ_1091 = 0x0020  # timers in page 1091
FLAG_SETPOINT = 0x0040  # setpoints 1135 cool / 1136 heat / 1137 auto
FLAG_HEAT_SP = FLAG_SETPOINT  # historical name
SETPOINT_REGS = range(1135, 1138)

REG_3011 = 3011

# A queued value stays in our page until the board pushes it back (confirmed)
# or this long has passed (rejected / never read) — then the board's value wins.
OVERLAY_TTL_S = 20.0

# How often one write may ask to be read again after the board's read of our
# page did not get through (~1 in 12 on the live bus).
MAX_READ_RETRIES = 2
# A clean 3001 sync follows a successful read by ~0.85 s; the next poll comes
# 1.1–1.4 s after the read. No sync by then = the read failed.
SYNC_ACK_S = 1.0

_PAGES = (1001, 1091, 1181)


class SettingsUnseeded(RuntimeError):
    """Slave-2 would have to invent a settings page."""


def _page_of(register: int) -> int | None:
    for start in _PAGES:
        if start <= register < start + 90:
            return start
    return None


class Slave2Responder:
    def __init__(self, broadcast_start: int = 2001) -> None:
        self._broadcast_start = broadcast_start
        self.block_3001 = [0] * 30
        self._blocks: dict[int, list[int]] = {start: [0] * 90 for start in _PAGES}
        self._seeded: dict[int, bool] = {start: False for start in _PAGES}
        # register -> (value, deadline); applied on top of the seeded page.
        self._overlay: dict[int, tuple[int, float]] = {}
        self.flags_3011 = 0
        # Bits whose page we answered a read for, awaiting the board's 3001 sync.
        self._served = 0
        self._served_at = 0.0
        # Bits to raise again at the next poll (read failed, see observe/reply).
        self._retry_bits = 0
        self._retries_left = 0

    # -- compatibility accessors used by the driver and tests -------------
    @property
    def block_1001(self) -> list[int]:
        return self._page(1001)

    @property
    def block_1091(self) -> list[int]:
        return self._page(1091)

    @property
    def block_1181(self) -> list[int]:
        return self._page(1181)

    @property
    def seeded_1001(self) -> bool:
        return self._seeded[1001]

    @property
    def seeded_1091(self) -> bool:
        return self._seeded[1091]

    @property
    def seeded_1181(self) -> bool:
        return self._seeded[1181]

    @property
    def pending_registers(self) -> list[int]:
        self._expire()
        return sorted(self._overlay)

    # -- bus observation ---------------------------------------------------
    def observe(self, frame: RtuFrame) -> None:
        if frame.kind == "reply" and frame.function == 3 and len(frame.values) == 30:
            if frame.values[9] in (3001, 0x0BB9) or frame.values[0] > 0:
                self.block_3001 = list(frame.values[:30])
        if frame.function == 16 and frame.start in _PAGES and frame.values:
            self.seed_page(int(frame.start), list(frame.values))
        if (
            frame.function == 16
            and frame.slave == 2
            and frame.start == 3001
            and frame.values
        ):
            # The board writes 3001×11 to us ~0.85 s after every page read; word 10
            # is its view of our flags. 0 = it took the page (every success on the
            # live bus). When the read did not get through the sync comes 0.02–0.34 s
            # after the request and is mangled or echoes our bit (4/4 failures) and
            # the board falls back to the wired display's page. So: a clean 0 acks
            # the served bits; anything else, or no parsable sync at all before the
            # next poll (see reply), asks to be read again — bounded, so a board
            # that keeps refusing cannot loop us.
            n = min(len(frame.values), 30)
            self.block_3001[:n] = [int(v) & 0xFFFF for v in frame.values[:n]]
            if len(frame.values) > 10 and self._served:
                echoed = int(frame.values[10]) & 0xFFFF & self._served
                if echoed:
                    self._schedule_retry(echoed)
                self._served = 0

    def _schedule_retry(self, bits: int) -> None:
        if self._retries_left > 0:
            self._retry_bits |= bits

    def cache_from_broadcast(self, regs: dict[int, int]) -> None:
        serial = [regs.get(self._broadcast_start + i, 0) for i in range(10)]
        if any(serial):
            self.block_3001[0:10] = serial[:10]

    def seed_page(self, start: int, values: list[int]) -> bool:
        if start not in _PAGES:
            return False
        if is_blank_menu_page(start, values):
            return False
        self._blocks[start] = (list(values) + [0] * 90)[:90]
        self._seeded[start] = True
        # The board echoing our value back means it took it.
        for register in list(self._overlay):
            if _page_of(register) == start:
                value, _deadline = self._overlay[register]
                if self._blocks[start][register - start] == value:
                    del self._overlay[register]
        self._drop_stale_flags()
        return True

    def page_seeded(self, register: int) -> bool:
        start = _page_of(register)
        return bool(start is not None and self._seeded[start])

    # -- writes --------------------------------------------------------------
    def queue_write(self, register: int, value: int) -> None:
        """Overlay one register and raise the 3011 bit that makes the board read its page."""
        start = _page_of(register)
        if start is None or not self._seeded[start]:
            raise SettingsUnseeded(f"settings page for {register} is not seeded")
        self._overlay[register] = (
            int(value) & 0xFFFF,
            time.monotonic() + OVERLAY_TTL_S,
        )
        if start == 1001:
            bit = FLAG_READ_1001
        elif start == 1091:
            bit = FLAG_SETPOINT if register in SETPOINT_REGS else FLAG_READ_1091
        else:
            return
        self.flags_3011 |= bit
        self._served &= ~bit
        self._retry_bits &= ~bit
        self._retries_left = MAX_READ_RETRIES

    def discard_write(self, register: int) -> None:
        self._overlay.pop(register, None)
        self._drop_stale_flags()

    def _expire(self) -> None:
        now = time.monotonic()
        for register, (_value, deadline) in list(self._overlay.items()):
            if now >= deadline:
                del self._overlay[register]
        self._drop_stale_flags()

    def _drop_stale_flags(self) -> None:
        """A flag only stays up while its page still carries an unconfirmed value.

        Otherwise a rejected or expired write would keep the board re-reading our
        page every cycle forever."""
        live = {_page_of(register) for register in self._overlay}
        if 1001 not in live:
            self.flags_3011 &= ~FLAG_READ_1001
            self._retry_bits &= ~FLAG_READ_1001
        if 1091 not in live:
            self.flags_3011 &= ~(FLAG_READ_1091 | FLAG_SETPOINT)
            self._retry_bits &= ~(FLAG_READ_1091 | FLAG_SETPOINT)

    def _page(self, start: int) -> list[int]:
        self._expire()
        page = list(self._blocks[start])
        for register, (value, _deadline) in self._overlay.items():
            if _page_of(register) == start:
                page[register - start] = value
        return page

    # -- replies -------------------------------------------------------------
    def reply(self, request: bytes) -> bytes | None:
        from ..modbus_rtu import parse_frame

        parsed = parse_frame(request)
        if parsed is None or parsed.slave != 2:
            return None
        if (
            parsed.function == 16
            and parsed.kind == "write"
            and parsed.start is not None
            and parsed.qty
        ):
            # Ack the board's page push like a real panel; without it the board retries forever.
            return encode_fc16_reply(2, int(parsed.start), int(parsed.qty))
        if parsed.kind != "request" or parsed.function != 3:
            return None
        start = parsed.start or 0
        qty = parsed.qty or 0
        if start == 3001:
            self._expire()  # drops flags whose overlay has timed out
            if self._served and time.monotonic() - self._served_at >= SYNC_ACK_S:
                # Served a page, no clean sync since: the board did not take it
                # (live 2026-09-14 15:13: its sync arrived truncated to 28 B).
                self._schedule_retry(self._served)
                self._served = 0
            if self._retry_bits:
                self.flags_3011 |= self._retry_bits
                self._retry_bits = 0
                self._retries_left -= 1
            values = list(self.block_3001)
            if len(values) > 10:
                values[10] = self.flags_3011
            return encode_fc03_reply(2, values[:qty])
        if start in _PAGES:
            if not self._seeded[start]:
                return None
            # Drop the bit as soon as the page is served, exactly like the wired
            # display. Leaving it up does not help: the board then re-reads the page
            # every cycle and commits nothing until the bit drops (18 s on the live
            # bus, 2026-09-14 12:24). Remember what was served so the board's sync
            # can tell us whether the read actually got through.
            bits = FLAG_READ_1001 if start == 1001 else (FLAG_READ_1091 | FLAG_SETPOINT)
            if start in (1001, 1091):
                self._served = self.flags_3011 & bits
                self._served_at = time.monotonic()
                self.flags_3011 &= ~bits
            return encode_fc03_reply(2, self._page(start)[:qty])
        if start == REG_3011:
            return encode_fc03_reply(2, [self.flags_3011])
        return None
