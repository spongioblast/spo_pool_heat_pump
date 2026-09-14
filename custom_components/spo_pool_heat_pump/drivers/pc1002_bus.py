"""Sniff the 2001×90 broadcast; write as the second panel (slave2), or via dtu_99 / panel_1.

The main board is the bus master (see drivers/slave2.py). ``slave2`` answers
its polls and pushes like a second display and hands it changed settings the
way the wired display does. ``dtu_99`` is mode-only on this bus (1012 is
adopted; 1013/1076 are acked by the module and ignored). ``panel_1`` sends an
unsolicited FC16 at the wired display and is unproven.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from ..const import BROADCAST_QTY, BROADCAST_START, WRITE_PATH_DTU, WRITE_PATH_SLAVE2
from ..modbus_rtu import encode_fc03, encode_fc16, parse_frame
from ..profiles import decode_panel_clock, lookup_write_spec, profile_registers
from .base import HeatPumpDriver, HeatPumpState
from .decode import apply_map
from .pending import DEFAULT_TTL_S as PENDING_TTL_S
from .pending import PAGE_TTL_S, PendingWrites
from .settings import SettingsCache
from .slave2 import SettingsUnseeded, Slave2Responder, _page_of

_LOGGER = logging.getLogger(__name__)

__all__ = ["PENDING_TTL_S", "Pc1002BusDriver"]

_SETPOINT_KEYS = frozenset({"setpoint", "setpoint_heat", "setpoint_cool", "setpoint_auto"})
_PER_MODE_SETPOINT = {
    "heat": "setpoint_heat",
    "cool": "setpoint_cool",
    "auto": "setpoint_auto",
}
# How our copy of a settings page gets seeded on the slave-2 path.
#
# The board does NOT push 1001/1091/1181 to the displays every cycle. DR164 dumps
# 2026-09-14: in 15 min of mode toggles (17:55) 1091 went to slave 1/2 zero times;
# in 15 min with four setpoint changes (19:06) it went to slave 2 nine times, all
# within seconds of a write. 1181 never went to slave 1/2. Idle, the board pushes
# 1091 only to the WiFi module (slave 99), every ~210 s. After a Home Assistant
# restart 1091 therefore stays unseeded until someone changes a setpoint on the
# panel. Build 03b4f19 waited 3 s and raised "settings page for 1136 is not
# seeded" on the live box.
#
# So: wait briefly for a push (cheap, and the board may be mid-push), then do the
# one-shot FC03 read of the display that ede2449 did all afternoon without a
# collision. What did collide (11:51) was the *re-read on a 3011 flag change*
# after a failed page read; that stays removed on this path.
PAGE_SEED_WAIT_S = 3.0


class Pc1002BusDriver(HeatPumpDriver):
    is_push = True

    def __init__(
        self,
        profile: dict[str, Any],
        send: Callable,  # async (bytes) -> None
        write_path: str = WRITE_PATH_SLAVE2,
        on_state: Callable[[HeatPumpState], None] | None = None,
    ) -> None:
        self.profile = profile
        self._send = send
        self.write_path = write_path
        self._on_state = on_state
        spec = (profile.get("driver") or {}).get("broadcast") or {}
        self._broadcast_start = int(spec.get("start", BROADCAST_START))
        self._broadcast_qty = int(spec.get("qty", BROADCAST_QTY))
        self.state = HeatPumpState()
        self.settings = SettingsCache(broadcast_start=self._broadcast_start)
        self.slave2 = Slave2Responder(broadcast_start=self._broadcast_start)
        self._reply_event = asyncio.Event()
        self._page_seeded = asyncio.Event()
        self._bus_lock = asyncio.Lock()
        self._last_3011: int | None = None
        self._pending_flag_pages: list[int] | str | None = None
        self.pending = PendingWrites(profile)
        self.page_seed_wait_s = PAGE_SEED_WAIT_S

    async def async_start(self) -> None:
        return None

    async def async_stop(self) -> None:
        return None

    def handle_frame(self, frame: bytes) -> bytes | None:
        parsed = parse_frame(frame)
        if parsed is None:
            return self.maybe_slave2_reply(frame)
        self.slave2.observe(parsed)
        if parsed.function == 16 and parsed.slave == 2 and parsed.start == 3001:
            # The board's 3001×11 sync to us echoes *our* flags; it is not display
            # state and must never look like a display flag change.
            settings_changed = False
        else:
            settings_changed = self.settings.absorb_frame(parsed)
        if parsed.function == 16 and parsed.start in (1001, 1091, 1181) and parsed.values:
            if self.slave2.seed_page(int(parsed.start), list(parsed.values)):
                self._page_seeded.set()
        matched = self.settings.take_page()
        if matched is not None:
            start, values = matched
            if self.slave2.seed_page(start, values):
                self._page_seeded.set()
            self._reply_event.set()
            settings_changed = True
        if (
            parsed.function == 16
            and parsed.slave == 0
            and parsed.start == self._broadcast_start
            and parsed.qty == self._broadcast_qty
            and parsed.values
        ):
            regs = {self._broadcast_start + i: v for i, v in enumerate(parsed.values)}
            self.slave2.cache_from_broadcast(regs)
            self._publish(regs)
            return self.maybe_slave2_reply(frame)
        if settings_changed and self.write_path != WRITE_PATH_SLAVE2:
            # As the second panel we are pushed every page the board changes, so
            # there is nothing to read back — and a FC03 from us would make Home
            # Assistant a second master on the board's bus (the live capture
            # 2026-09-14 11:51 shows one going out 23 ms after a failed page read).
            self._maybe_queue_flag_reread()
        if settings_changed and self.state.available:
            self._publish(self.state.raw)
        return self.maybe_slave2_reply(frame)

    def _republish_if_seeded(self) -> None:
        if self.state.available or self.state.raw:
            self._publish(self.state.raw)

    def _publish(self, regs: dict[int, int]) -> HeatPumpState:
        state = apply_map(self.profile, regs, settings=self.settings.regs)
        if not state.clock:
            state.clock = decode_panel_clock(self.settings.page_3001 or self.slave2.block_3001)
        self.pending.overlay(state)
        self.state = state
        if self._on_state:
            self._on_state(state)
        return state

    def _write_mode(self) -> str | None:
        # Selected mode (page 1012, including a pending overlay) picks the
        # per-mode word. Until 1001 is seeded, fall back to the running
        # direction (2012) so a heat/cool write still hits 1136/1135.
        return self.state.mode or self.state.get("active_mode")

    def _flag_spec(self) -> dict[str, Any]:
        return ((self.profile.get("driver") or {}).get("settings") or {}).get("flags") or {}

    def _flag_pages(self, flags_word: int) -> list[int] | str:
        pages: set[int] = set()
        refresh_all = False
        for bit, target in (self._flag_spec().get("bits") or {}).items():
            if flags_word & int(bit):
                if target == "all":
                    refresh_all = True
                else:
                    pages.add(int(target))
        return "all" if refresh_all else sorted(pages)

    def _maybe_queue_flag_reread(self) -> None:
        spec = self._flag_spec()
        if not spec:
            return
        reg = int(spec.get("reg", 3011))
        word = self.settings.regs.get(reg)
        if word is None:
            page = self.settings.page_3001 or self.slave2.block_3001
            offset = reg - 3001
            if page and 0 <= offset < len(page):
                word = page[offset]
        if word is None or word == self._last_3011:
            return
        prev = self._last_3011
        self._last_3011 = int(word)
        if prev is None:
            return
        pages = self._flag_pages(int(word))
        if pages:
            self._pending_flag_pages = pages

    async def after_frame(self) -> list[int] | str | None:
        pages = self._pending_flag_pages
        self._pending_flag_pages = None
        return pages

    def maybe_slave2_reply(self, frame: bytes) -> bytes | None:
        if self.write_path != WRITE_PATH_SLAVE2:
            return None
        return self.slave2.reply(frame)

    async def refresh_settings(self, only: list[int] | None = None) -> bool:
        async with self._bus_lock:
            inst = self.profile.get("service_menu") or {}
            pages = inst.get("pages") or []
            if only is not None:
                wanted = {int(x) for x in only}
                pages = [page for page in pages if int(page["start"]) in wanted]
            if not pages:
                return True
            read = inst.get("read") or {}
            slave = int(read.get("slave", 1))
            timeout = float(read.get("timeout_s", 0.8))
            ok = True
            for page in pages:
                start = int(page["start"])
                qty = int(page["qty"])
                self.settings.expect_reply(start, slave=slave, qty=qty)
                self._reply_event = asyncio.Event()
                result = self._send(encode_fc03(slave, start, qty))
                if asyncio.iscoroutine(result):
                    await result
                try:
                    await asyncio.wait_for(self._reply_event.wait(), timeout=timeout)
                except TimeoutError:
                    _LOGGER.debug("service_menu read timeout start=%s", start)
                    ok = False
            self._republish_if_seeded()
            return ok

    async def write_register(self, name: str, value: int | float) -> None:
        if name in _SETPOINT_KEYS:
            which = None if name == "setpoint" else name
            await self.set_setpoint(float(value), which=which)
            return
        register, encoded = self.encoded_write(name, value)
        await self._write_encoded(name, register, encoded)

    def _pending_ttl(self, name: str, also: str | None = None) -> float:
        """Broadcast-confirmed values (power, quiet) echo in 2–4 s; a value that
        only exists in a settings page (mode, timers) is confirmed by the board's
        page push one round later, ~8–10 s after the write. A write that can be
        confirmed by a page as well (setpoint) waits the page window too."""
        spec = lookup_write_spec(self.profile, name)
        if also or spec.get("prefer") == "settings" or "reg" not in spec:
            return PAGE_TTL_S
        return self.pending.ttl_s

    async def _write_encoded(
        self, shown_as: str, register: int, encoded: int, *, also: str | None = None
    ) -> None:
        """Send ``register=encoded`` and show it optimistically under ``shown_as``.

        ``also`` names a second state field (the per-mode setpoint word from page
        1091) whose echo proves the board took the write before ``shown_as``
        (broadcast 2013) catches up.
        """
        self.pending.mark(shown_as, encoded, ttl_s=self._pending_ttl(shown_as, also), also=also)
        accepted = False
        try:
            await self._emit_write(register, encoded)
            accepted = True
            for extra in self.extra_write_addrs(register):
                await self._emit_write(extra, encoded)
        except Exception:
            # Only revert if the primary write never reached the page / wire.
            # A later extra-register failure (or a coordinator error during the
            # board's post-commit pause) must not hide a value the board already
            # has a chance to read.
            if not accepted:
                self.pending.discard(shown_as)
                self.slave2.discard_write(register)
                self._republish_if_seeded()
            raise

    async def _emit_write(self, register: int, encoded: int) -> None:
        # The settings cache is deliberately not touched here: it mirrors what
        # the *board* has said. The new value is shown through ``self.pending``
        # and is confirmed only when the board pushes the page (or broadcasts the
        # derived word) with that value; writing our own cache would confirm the
        # write to ourselves.
        if self.write_path == WRITE_PATH_SLAVE2:
            if not self.slave2.page_seeded(register):
                await self._wait_for_page_seed(register)
            if not self.slave2.page_seeded(register):
                # No push came (see PAGE_SEED_WAIT_S). Read just this page from the
                # display once, under the bus lock; the transport holds the frame
                # until the bus has been idle one gap. Same path as the startup
                # seed and the refresh_service_menu service.
                page = _page_of(register)
                await self.refresh_settings(only=[page] if page else None)
            if not self.slave2.page_seeded(register):
                raise SettingsUnseeded(f"settings page for {register} is not seeded")
            self.slave2.queue_write(register, encoded)
            self._republish_if_seeded()
            return
        self._republish_if_seeded()
        slave = 99 if self.write_path == WRITE_PATH_DTU else 1
        result = self._send(encode_fc16(slave, register, [encoded]))
        if asyncio.iscoroutine(result):
            await result

    async def _wait_for_page_seed(self, register: int) -> None:
        """Give the board a moment to push the page before we read it ourselves."""
        deadline = time.monotonic() + self.page_seed_wait_s
        while not self.slave2.page_seeded(register):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self._page_seeded.clear()
            if self.slave2.page_seeded(register):
                return
            try:
                await asyncio.wait_for(self._page_seeded.wait(), timeout=remaining)
            except TimeoutError:
                return

    async def set_power(self, on: bool) -> None:
        await self.write_register("power", on)

    async def set_mode(self, mode: str) -> None:
        # Page 1001 word 1012 is the selected mode. The board switches the working
        # setpoint (broadcast 2013) to the matching 1135/1136/1137 value itself;
        # the panel does not touch 1013 for a mode change. Drop a pending setpoint
        # overlay so we do not keep showing the old mode's target while 2013 swaps.
        self.pending.discard("setpoint")
        await self._write_encoded("mode", *self.encoded_write("mode", mode))

    async def set_setpoint(self, celsius: float, which: str | None = None) -> None:
        if self.write_path == WRITE_PATH_DTU:
            # The factory WiFi module takes the app's words: it acked 1012 (and the
            # board adopted the mode 1.5 s later) but ignored 1136 on the live bus
            # (2026-09-14 16:44). Send the working setpoint 1013 like the app does.
            register, encoded = self.encoded_write("setpoint", celsius)
            await self._write_encoded("setpoint", register, encoded)
            return
        mapping = profile_registers(self.profile)
        if which in _PER_MODE_SETPOINT.values():
            per_mode = which
        else:
            per_mode = _PER_MODE_SETPOINT.get(self._write_mode() or "")
        if not (per_mode and per_mode in mapping and "write" in mapping[per_mode]):
            register, encoded = self.encoded_write("setpoint", celsius)
            await self._write_encoded("setpoint", register, encoded)
            return
        # The working setpoint is the per-mode word in page 1091 (1135 cool /
        # 1136 heat / 1137 auto); that is the one register the wired display
        # changes (flag 0x0040) and the board mirrors it into broadcast 2013.
        # Word 1013 in page 1001 is panel-owned and lags 2013 for minutes, so
        # writing it neither moves the target nor confirms anything. Show the
        # new target optimistically under "setpoint"; the board's 1091 push
        # (~8 s) proves it took the value, 2013 follows up to ~12 s later
        # (36→35 on the live bus: page 8.6 s, broadcast 21 s after the write).
        register, encoded = self.encoded_write(per_mode, celsius)
        await self._write_encoded("setpoint", register, encoded, also=per_mode)

    async def set_silent(self, on: bool) -> None:
        await self.write_register("silent", on)
