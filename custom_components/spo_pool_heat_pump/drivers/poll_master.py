"""HA is the Modbus master. Used by Fairland CN13 and legacy coil maps."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from ..modbus_rtu import (
    encode_fc01,
    encode_fc04,
    encode_fc05,
    encode_fc06,
    encode_fc16,
    parse_frame,
)
from ..profiles import lookup_write_spec, profile_polls
from .base import HeatPumpDriver, HeatPumpState
from .decode import apply_map
from .pending import DEFAULT_TTL_S, PendingWrites
from .settings import SettingsCache

_LOGGER = logging.getLogger(__name__)


def pending_ttl_for_interval(poll_interval_s: float) -> float:
    """A write is confirmed by the next full poll cycle; allow two of them."""
    return max(DEFAULT_TTL_S, 2.0 * float(poll_interval_s) + 4.0)


class PollMasterDriver(HeatPumpDriver):
    is_push = False

    def __init__(
        self,
        profile: dict[str, Any],
        send: Callable,
        on_state: Callable[[HeatPumpState], None] | None = None,
    ) -> None:
        self.profile = profile
        self._send = send
        self._on_state = on_state
        self.state = HeatPumpState()
        self.settings = SettingsCache()
        self._blocks: dict[str, list[int]] = {}
        self._regs: dict[int, int] = {}
        self._poll_i = 0
        self._awaiting: int | None = None
        self._service_menu_start: int | None = None
        self._reply_event = asyncio.Event()
        self._reply_exception = False
        self._bus_lock = asyncio.Lock()
        interval = float((profile.get("driver") or {}).get("poll_interval", 10))
        self.pending = PendingWrites(profile, ttl_s=pending_ttl_for_interval(interval))

    def set_poll_interval(self, seconds: float) -> None:
        """Entry option overrides the profile default; keep the pending TTL in step."""
        self.pending.ttl_s = pending_ttl_for_interval(seconds)

    def _publish(self) -> HeatPumpState:
        state = apply_map(self.profile, self._regs, self._blocks, self.settings.regs)
        self.pending.overlay(state)
        self.state = state
        if self._on_state:
            self._on_state(state)
        return state

    async def async_start(self) -> None:
        return None

    async def async_stop(self) -> None:
        return None

    def handle_frame(self, frame: bytes) -> bytes | None:
        parsed = parse_frame(frame)
        if parsed is None:
            return None
        if parsed.kind == "exception":
            self._service_menu_start = None
            self._reply_exception = True
            self._reply_event.set()
            return None
        if parsed.kind != "reply":
            return None
        if self._service_menu_start is not None:
            start = self._service_menu_start
            self.settings.absorb_fc03_reply(start, list(parsed.values))
            for i, val in enumerate(parsed.values):
                self._regs[start + i] = val
            self._service_menu_start = None
            self._reply_event.set()
            return None
        polls = profile_polls(self.profile)
        if not polls:
            return None
        idx = self._awaiting if self._awaiting is not None else 0
        spec = polls[idx % len(polls)]
        name = spec.get("name")
        start = int(spec.get("start", 0))
        if name:
            self._blocks[name] = list(parsed.values)
        else:
            for i, val in enumerate(parsed.values):
                self._regs[start + i] = val
        self._reply_event.set()
        if (idx + 1) % len(polls) == 0:
            self._publish()
        return None

    async def poll_once(self, wait_s: float = 0.8) -> None:
        async with self._bus_lock:
            polls = profile_polls(self.profile)
            if not polls:
                return
            spec = polls[self._poll_i % len(polls)]
            slave = int(spec.get("slave", self.profile["driver"].get("poll_slave", 1)))
            start = int(spec["start"])
            qty = int(spec["qty"])
            fc = int(spec["fc"])
            if fc == 1:
                frame = encode_fc01(slave, start, qty)
            elif fc == 4:
                frame = encode_fc04(slave, start, qty)
            else:
                from ..modbus_rtu import encode_fc03

                frame = encode_fc03(slave, start, qty)
            self._awaiting = self._poll_i % len(polls)
            self._reply_event = asyncio.Event()
            self._reply_exception = False
            await self._send(frame)
            if wait_s:
                try:
                    await asyncio.wait_for(self._reply_event.wait(), timeout=wait_s)
                except TimeoutError:
                    _LOGGER.debug("poll timeout fc=%s start=%s", fc, start)
            self._poll_i += 1

    async def refresh_settings(self, only: list[int] | None = None) -> bool:
        async with self._bus_lock:
            inst = self.profile.get("service_menu") or {}
            pages = inst.get("pages") or []
            if only is not None:
                wanted = {int(x) for x in only}
                pages = [page for page in pages if int(page["start"]) in wanted]
            if not pages:
                return True
            ok = True
            for page in pages:
                start = int(page["start"])
                qty = int(page["qty"])
                slave = int((inst.get("read") or {}).get("slave", self.profile["driver"].get("poll_slave", 1)))
                wait_s = float((inst.get("read") or {}).get("timeout_s", 0.8))
                from ..modbus_rtu import encode_fc03

                self._service_menu_start = start
                self._reply_event = asyncio.Event()
                self._reply_exception = False
                self.settings.expect_reply(start, slave=slave, qty=qty)
                await self._send(encode_fc03(slave, start, qty))
                try:
                    await asyncio.wait_for(self._reply_event.wait(), timeout=wait_s)
                    if self._reply_exception:
                        ok = False
                except TimeoutError:
                    ok = False
            if self._regs or self._blocks:
                self._publish()
            return ok

    async def write_register(self, name: str, value: int | float) -> None:
        spec = lookup_write_spec(self.profile, name)
        register, encoded = self.encoded_write(name, value)
        self.pending.mark(name, encoded)
        accepted = False
        try:
            await self._emit_write(spec, register, encoded)
            accepted = True
            for extra in self.extra_write_addrs(register):
                await self._emit_write(spec, extra, encoded)
        except Exception:
            if not accepted:
                self.pending.discard(name)
            raise
        finally:
            if self._regs or self._blocks:
                # Show the new value now; the next poll cycle confirms or reverts it.
                self._publish()

    async def _emit_write(self, spec: dict[str, Any], register: int, encoded: int) -> None:
        slave = int(self.profile["driver"].get("poll_slave", 1))
        self.settings.put(register, encoded)
        fc = int(spec.get("write_fc") or self.profile["driver"].get("write_fc", 6))
        if fc == 5:
            await self._send(encode_fc05(slave, register, bool(encoded)))
        elif fc == 16:
            await self._send(encode_fc16(slave, register, [encoded]))
        else:
            await self._send(encode_fc06(slave, register, encoded))

    async def set_power(self, on: bool) -> None:
        await self.write_register("power", on)

    async def set_mode(self, mode: str) -> None:
        await self.write_register("mode", mode)

    async def set_setpoint(self, celsius: float, which: str | None = None) -> None:
        await self.write_register("setpoint", celsius)

    async def set_silent(self, on: bool) -> None:
        await self.write_register("silent", on)
