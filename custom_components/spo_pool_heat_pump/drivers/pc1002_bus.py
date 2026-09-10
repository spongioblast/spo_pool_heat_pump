"""Sniff the 2001×90 broadcast; write through dtu_99 / slave2 / panel_1."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from ..const import BROADCAST_QTY, BROADCAST_START, WRITE_PATH_DTU, WRITE_PATH_SLAVE2
from ..modbus_rtu import encode_fc03, encode_fc16, parse_frame
from ..profiles import decode_panel_clock, profile_registers
from .base import HeatPumpDriver, HeatPumpState
from .decode import apply_map
from .settings import SettingsCache
from .slave2 import SettingsUnseeded, Slave2Responder

_LOGGER = logging.getLogger(__name__)


class Pc1002BusDriver(HeatPumpDriver):
    is_push = True

    def __init__(
        self,
        profile: dict[str, Any],
        send: Callable,  # async (bytes) -> None
        write_path: str = WRITE_PATH_DTU,
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
        self._optimistic_mode: str | None = None

    async def async_start(self) -> None:
        return None

    async def async_stop(self) -> None:
        return None

    def handle_frame(self, frame: bytes) -> bytes | None:
        parsed = parse_frame(frame)
        if parsed is None:
            return self.maybe_slave2_reply(frame)
        self.slave2.observe(parsed)
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
        if settings_changed:
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
        if self._optimistic_mode is not None and state.mode == self._optimistic_mode:
            self._optimistic_mode = None
        self.state = state
        if self._on_state:
            self._on_state(state)
        return state

    def _write_mode(self) -> str:
        return self._optimistic_mode or self.state.mode

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
        await self._emit_write(register, encoded)
        for extra in self.extra_write_addrs(register):
            await self._emit_write(extra, encoded)

    async def _emit_write(self, register: int, encoded: int) -> None:
        if self.write_path == WRITE_PATH_SLAVE2:
            if not self.slave2.page_seeded(register):
                await self.refresh_settings()
            if not self.slave2.page_seeded(register):
                raise SettingsUnseeded(f"settings page for {register} is not seeded")
            self.settings.put(register, encoded)
            self.slave2.queue_write(register, encoded)
            self._republish_if_seeded()
            return
        self.settings.put(register, encoded)
        self._republish_if_seeded()
        slave = 99 if self.write_path == WRITE_PATH_DTU else 1
        result = self._send(encode_fc16(slave, register, [encoded]))
        if asyncio.iscoroutine(result):
            await result

    async def set_power(self, on: bool) -> None:
        await self.write_register("power", on)

    async def set_mode(self, mode: str) -> None:
        self._optimistic_mode = mode
        await self.write_register("mode", mode)
        key = {"heat": "setpoint_heat", "cool": "setpoint_cool", "auto": "setpoint_auto"}.get(mode)
        saved = getattr(self.state, key or "", None) if key else None
        if saved is not None:
            await self.write_register("setpoint", saved)

    async def set_setpoint(self, celsius: float, which: str | None = None) -> None:
        mapping = profile_registers(self.profile)
        await self.write_register(which or "setpoint", celsius)
        if which is None:
            extra = {"heat": "setpoint_heat", "cool": "setpoint_cool", "auto": "setpoint_auto"}.get(
                self._write_mode()
            )
            if extra and extra in mapping and "write" in mapping[extra]:
                await self.write_register(extra, celsius)

    async def set_silent(self, on: bool) -> None:
        await self.write_register("silent", on)
