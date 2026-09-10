"""Listen-only driver: stay available, never write, never poll."""

from __future__ import annotations

from typing import Any, Callable

from .base import HeatPumpDriver, HeatPumpState


class DumpOnlyWriteError(PermissionError):
    """listen_only never writes the bus."""


class ListenOnlyDriver(HeatPumpDriver):
    is_push = True

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

    def _publish(self, available: bool = True) -> None:
        ident = self.profile.get("identity") or {}
        state = HeatPumpState(
            available=available,
            manufacturer=str(ident.get("brand") or ""),
            model=str(ident.get("model") or ""),
            values={"dump_only": True},
        )
        self.state = state
        if self._on_state:
            self._on_state(state)

    def set_available(self, available: bool) -> None:
        if self.state.available == available and self.state.values.get("dump_only"):
            return
        self._publish(available)

    async def async_start(self) -> None:
        self._publish()

    async def async_stop(self) -> None:
        return None

    def handle_frame(self, frame: bytes) -> bytes | None:
        if not self.state.available:
            self._publish()
        return None

    def _refuse(self) -> None:
        raise DumpOnlyWriteError("Dump-only profile does not write")

    async def set_power(self, on: bool) -> None:
        self._refuse()

    async def set_mode(self, mode: str) -> None:
        self._refuse()

    async def set_setpoint(self, celsius: float, which: str | None = None) -> None:
        self._refuse()

    async def set_silent(self, on: bool) -> None:
        self._refuse()

    async def write_register(self, name: str, value: int | float) -> None:
        self._refuse()
