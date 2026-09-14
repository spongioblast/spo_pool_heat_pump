"""Sniff the 2001×90 broadcast; write as the second panel (slave2), or via dtu_99 / panel_1.

The main board is the bus master (see drivers/slave2.py). ``slave2`` answers
its polls and pushes like a second display and hands it changed settings the
way the wired display does. ``dtu_99`` / ``panel_1`` send an unsolicited FC16
as a second master; neither has been seen to work on the verified bus.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from ..const import BROADCAST_QTY, BROADCAST_START, WRITE_PATH_DTU, WRITE_PATH_SLAVE2
from ..modbus_rtu import encode_fc03, encode_fc16, parse_frame
from ..profiles import decode_panel_clock, lookup_write_spec, profile_registers
from .base import HeatPumpDriver, HeatPumpState
from .decode import apply_map
from .pending import DEFAULT_TTL_S as PENDING_TTL_S
from .pending import PAGE_TTL_S, PendingWrites
from .settings import SettingsCache
from .slave2 import SettingsUnseeded, Slave2Responder

_LOGGER = logging.getLogger(__name__)

__all__ = ["PENDING_TTL_S", "Pc1002BusDriver"]


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
        self._bus_lock = asyncio.Lock()
        self._last_3011: int | None = None
        self._pending_flag_pages: list[int] | str | None = None
        self.pending = PendingWrites(profile)

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
            self.slave2.seed_page(int(parsed.start), list(parsed.values))
        matched = self.settings.take_page()
        if matched is not None:
            start, values = matched
            self.slave2.seed_page(start, values)
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

    def _write_mode(self) -> str:
        # ``state.mode`` is the selected mode (page 1001 word 1012 when seeded,
        # else broadcast 2012) and already carries a pending mode write as an
        # overlay, so it is the right key for the per-mode setpoint register.
        return self.state.mode

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
        register, encoded = self.encoded_write(name, value)
        await self._write_encoded(name, register, encoded)

    def _pending_ttl(self, name: str) -> float:
        """Broadcast-confirmed values (power, setpoint, quiet) echo in 2–4 s; a value
        that only exists in a settings page (mode, timers) is confirmed by the
        board's page push one round later, ~8–10 s after the write."""
        spec = lookup_write_spec(self.profile, name)
        if spec.get("prefer") == "settings" or "reg" not in spec:
            return PAGE_TTL_S
        return self.pending.ttl_s

    async def _write_encoded(self, shown_as: str, register: int, encoded: int) -> None:
        """Send ``register=encoded`` and show it optimistically under ``shown_as``."""
        self.pending.mark(shown_as, encoded, ttl_s=self._pending_ttl(shown_as))
        try:
            await self._emit_write(register, encoded)
            for extra in self.extra_write_addrs(register):
                await self._emit_write(extra, encoded)
        except Exception:
            # Nothing reached the bus; do not show a value the pump never got.
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
                await self.refresh_settings()
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

    async def set_power(self, on: bool) -> None:
        await self.write_register("power", on)

    async def set_mode(self, mode: str) -> None:
        # Page 1001 word 1012 is the selected mode. The board switches the working
        # setpoint (broadcast 2013) to the matching 1135/1136/1137 value itself;
        # the panel does not touch 1013 for a mode change.
        await self.write_register("mode", mode)

    async def set_setpoint(self, celsius: float, which: str | None = None) -> None:
        if which is not None:
            await self.write_register(which, celsius)
            return
        if self.write_path == WRITE_PATH_DTU:
            # The factory WiFi module takes the app's words: it acked 1012 (and the
            # board adopted the mode 1.5 s later) but ignored 1136 on the live bus
            # (2026-09-14 16:44). Send the working setpoint 1013 like the app does.
            await self.write_register("setpoint", celsius)
            return
        mapping = profile_registers(self.profile)
        per_mode = {
            "heat": "setpoint_heat",
            "cool": "setpoint_cool",
            "auto": "setpoint_auto",
        }.get(self._write_mode())
        if not (per_mode and per_mode in mapping and "write" in mapping[per_mode]):
            await self.write_register("setpoint", celsius)
            return
        # The working setpoint is the per-mode word in page 1091 (1135 cool /
        # 1136 heat / 1137 auto); that is the one register the wired display
        # changes (flag 0x0040) and the board mirrors it into broadcast 2013.
        # Word 1013 in page 1001 is panel-owned and lags 2013 for minutes, so
        # writing it neither moves the target nor confirms anything. Show the
        # new target optimistically under "setpoint" and confirm on 2013.
        register, encoded = self.encoded_write(per_mode, celsius)
        await self._write_encoded("setpoint", register, encoded)

    async def set_silent(self, on: bool) -> None:
        await self.write_register("silent", on)
