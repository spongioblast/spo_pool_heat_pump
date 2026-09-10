"""Normalized heat-pump state and driver interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class HeatPumpState:
    available: bool = False
    power: bool = False
    mode: str = "heat"  # cool | heat | auto
    setpoint: float | None = None
    setpoint_heat: float | None = None
    setpoint_cool: float | None = None
    setpoint_auto: float | None = None
    t_inlet: float | None = None
    t_outlet: float | None = None
    t_ambient: float | None = None
    t_coil: float | None = None
    t_exhaust: float | None = None
    power_kw: float | None = None
    energy_24h_kwh: float | None = None
    energy_total_kwh: float | None = None
    comp_hz: int | None = None
    hz_max: int = 90
    fan_rpm: int | None = None
    silent: bool = False
    outputs: dict[str, bool] = field(default_factory=dict)
    faults: list[str] = field(default_factory=list)
    fault_texts: list[str] = field(default_factory=list)
    serial: str | None = None
    fw_display: int | None = None
    fw_main: int | None = None
    manufacturer: str = ""
    model: str = ""
    raw: dict[int, int] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)
    clock: str | None = None

    @property
    def compressor_pct(self) -> int | None:
        if self.comp_hz is None or not self.hz_max:
            return None
        return int(round(100 * self.comp_hz / self.hz_max))

    @property
    def compressor_on(self) -> bool:
        return bool(self.outputs.get("compressor"))

    @property
    def pump_on(self) -> bool:
        return bool(self.outputs.get("water_pump"))

    @property
    def fault_code(self) -> str | None:
        return self.faults[0] if self.faults else None

    @property
    def fault_text(self) -> str | None:
        texts = [t for t in self.fault_texts if t]
        return " · ".join(texts) if texts else None

    def get(self, key: str) -> Any:
        if key not in ("extras", "values", "raw", "outputs") and hasattr(self, key):
            value = getattr(self, key)
            if not callable(value):
                return value
        return self.values.get(key, self.extras.get(key))

    def auto_is_heating(self) -> bool:
        """Direction of an auto-mode unit.

        With the compressor running the water ΔT is the physical truth
        (outlet above inlet = heating), which also survives the normal
        overshoot past the setpoint before the compressor stops. Otherwise
        fall back to which side of the setpoint the inlet sits.
        """
        inlet, outlet, target = self.t_inlet, self.t_outlet, self.setpoint
        if self.compressor_on and inlet is not None and outlet is not None and abs(outlet - inlet) >= 0.2:
            return outlet > inlet
        if inlet is not None and target is not None and inlet - 0.3 > target:
            return False
        return True

    def has_demand(self) -> bool | None:
        """Whether the water still needs conditioning towards the setpoint.

        None when inlet or setpoint is unknown (cannot tell). Heat: inlet
        below target. Cool: inlet above target. Auto: whichever direction
        auto_is_heating() picks.
        """
        inlet, target = self.t_inlet, self.setpoint
        if inlet is None or target is None:
            return None
        if self.mode == "cool":
            return inlet > target
        if self.mode == "auto":
            return inlet < target if self.auto_is_heating() else inlet > target
        return inlet < target

    def card_status(self) -> str:
        if not self.available:
            return "No data"
        if self.values.get("dump_only"):
            return "Dump only"
        if self.faults:
            return f"Fault · {self.faults[0]}"
        if not self.power:
            return "Off"
        if self.pump_on and not self.compressor_on:
            # Pump pre-run before the compressor starts. With the setpoint
            # reached the pump may still run (continuous / sampling), and
            # that is Idle, not a start-up.
            if self.has_demand() is False:
                return "Idle"
            return "Starting" if self.mode == "cool" or (self.mode == "auto" and not self.auto_is_heating()) else "Warming up"
        if self.compressor_on and self.mode == "heat":
            return "Heating"
        if self.compressor_on and self.mode == "cool":
            return "Cooling"
        if self.compressor_on and self.mode == "auto":
            return "Heating" if self.auto_is_heating() else "Cooling"
        if self.mode == "auto":
            return "Auto"
        return "Idle"


class HeatPumpDriver(ABC):
    is_push: bool = True
    service_menu_writes: bool = False
    profile: dict[str, Any]

    def encoded_write(self, name: str, value: Any) -> tuple[int, int]:
        from ..profiles import (
            encode_value,
            lookup_write_spec,
            service_menu_params,
            validate_service_menu_write,
            write_address,
        )

        if name in service_menu_params(self.profile):
            validate_service_menu_write(self.profile, self.service_menu_writes, name)
        spec = lookup_write_spec(self.profile, name)
        if name not in service_menu_params(self.profile) and spec.get("write") is None:
            raise KeyError(name)
        encoded = encode_value(spec, value, self.profile.get("enums") or {})
        return write_address(spec), encoded

    def extra_write_addrs(self, register: int) -> list[int]:
        if register != 1011:
            return []
        return [int(x) for x in (self.profile.get("driver") or {}).get("power_also_write") or []]

    @abstractmethod
    async def async_start(self) -> None: ...

    @abstractmethod
    async def async_stop(self) -> None: ...

    @abstractmethod
    async def set_power(self, on: bool) -> None: ...

    @abstractmethod
    async def set_mode(self, mode: str) -> None: ...

    @abstractmethod
    async def set_setpoint(self, celsius: float, which: str | None = None) -> None: ...

    @abstractmethod
    async def set_silent(self, on: bool) -> None: ...

    @abstractmethod
    async def write_register(self, name: str, value: int | float) -> None: ...

    def handle_frame(self, frame: bytes) -> bytes | None:
        """Consume one RTU frame. Return an optional reply (slave-2)."""
        return None

    async def poll_once(self, wait_s: float = 0.8) -> None:
        return None

    async def refresh_settings(self, only: list[int] | None = None) -> bool:
        return True

    async def async_refresh(self) -> bool:
        return await self.refresh_settings()

    async def after_frame(self) -> list[int] | str | None:
        return None
