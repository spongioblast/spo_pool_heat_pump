"""In-memory heat-pump unit for the simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from spo_pool_heat_pump.profiles import (
    decode_value,
    encode_value,
    service_menu_params,
    profile_registers,
)


CORE_FIELDS = (
    "power",
    "mode",
    "setpoint",
    "setpoint_heat",
    "setpoint_cool",
    "setpoint_auto",
    "t_inlet",
    "t_outlet",
    "t_ambient",
    "t_coil",
    "t_exhaust",
    "t_suction",
    "power_kw",
    "energy_24h_kwh",
    "comp_hz",
    "fan_rpm",
    "silent",
    "serial",
    "fw_display",
    "fw_main",
    "fw_mini",
    "low_pressure",
    "superheat",
    "ac_voltage",
    "dc_bus",
    "phase_current",
    "ipm_temp",
    "eev_steps",
    "antifreeze",
    "t_coil_2",
    "comp_hz_target",
    "cop",
    "capacity",
)


def _default_outputs() -> dict[str, bool]:
    return {
        "compressor": False,
        "water_pump": False,
        "four_way_valve": False,
        "high_fan": False,
        "low_fan": False,
    }


@dataclass
class SimUnit:
    profile: dict[str, Any]
    power: bool = False
    mode: str = "heat"
    setpoint: float = 28.0
    setpoint_heat: float = 28.0
    setpoint_cool: float = 26.0
    setpoint_auto: float = 28.0
    t_inlet: float = 16.0
    t_outlet: float = 16.0
    t_ambient: float = 18.0
    t_coil: float = 20.0
    t_exhaust: float = 22.0
    t_suction: float = 14.0
    power_kw: float = 0.0
    energy_24h_kwh: float = 0.0
    energy_total_kwh: float = 0.0
    comp_hz: float = 0.0
    fan_rpm: int = 0
    silent: bool = False
    serial: str = "SIMCOSMA"
    fw_display: int = 713
    fw_main: int = 772
    fw_mini: int = 0
    low_pressure: float | None = 12.0
    superheat: float | None = 6.0
    ac_voltage: float | None = 230.0
    dc_bus: float | None = 360.0
    phase_current: float | None = 0.0
    ipm_temp: float | None = 35.0
    eev_steps: int | None = 200
    antifreeze: float | None = 4.0
    t_coil_2: float | None = 20.0
    comp_hz_target: float = 0.0
    cop: float | None = None
    capacity: float | None = None
    clock: datetime = field(default_factory=lambda: datetime(2026, 9, 7, 16, 21, 0, tzinfo=timezone.utc))
    outputs: dict[str, bool] = field(default_factory=_default_outputs)
    extras: dict[str, Any] = field(default_factory=dict)
    settings: dict[int, int] = field(default_factory=dict)
    fault_words: dict[int, int] = field(default_factory=dict)
    pages_timeout: bool = False
    dtu: bool = True
    last_mode: str = ""

    @classmethod
    def seed(cls, profile: dict[str, Any]) -> SimUnit:
        unit = cls(profile=profile)
        unit.settings = seed_settings(profile)
        unit.sync_extras()
        ident = profile.get("identity") or {}
        if ident.get("id") == "phnix_mini_pc1002":
            unit.fw_mini = 100
            unit.fw_display = 0
            unit.serial = "SIMMINI"
        return unit

    def sync_extras(self) -> None:
        enums = self.profile.get("enums") or {}
        for key, spec in service_menu_params(self.profile).items():
            raw = self.settings.get(int(spec["reg"]))
            if raw is None:
                continue
            self.extras[key] = decode_value(spec, raw, enums)

    def get_value(self, key: str) -> Any:
        if key == "outputs":
            return dict(self.outputs)
        if key == "clock":
            return self.clock
        if key == "faults":
            return dict(self.fault_words)
        if hasattr(self, key) and key in CORE_FIELDS:
            return getattr(self, key)
        if key in self.extras:
            return self.extras[key]
        return None

    def set_value(self, key: str, value: Any) -> None:
        if key == "outputs" and isinstance(value, dict):
            self.outputs.update({str(k): bool(v) for k, v in value.items()})
            return
        if key in CORE_FIELDS and hasattr(self, key):
            setattr(self, key, value)
            return
        self.extras[key] = value

    def inject_fault(self, code: str) -> None:
        spec = profile_registers(self.profile).get("faults") or {}
        for bit_key, row in (spec.get("bits") or {}).items():
            label = row.get("code") if isinstance(row, dict) else row
            if str(label) != code:
                continue
            reg_s, _, bit_s = str(bit_key).partition(".")
            if not bit_s:
                continue
            reg = int(reg_s)
            self.fault_words[reg] = self.fault_words.get(reg, 0) | (1 << int(bit_s))
            return
        raise KeyError(code)

    def clear_faults(self) -> None:
        self.fault_words.clear()

    def apply_patch(self, patch: dict[str, Any]) -> None:
        if patch.get("clear_faults"):
            self.clear_faults()
        if "fault" in patch and patch["fault"]:
            self.inject_fault(str(patch["fault"]))
        if "clock" in patch and patch["clock"]:
            text = str(patch["clock"])
            parts = [int(p) for p in text.split(":")]
            self.clock = self.clock.replace(
                hour=parts[0],
                minute=parts[1] if len(parts) > 1 else 0,
                second=parts[2] if len(parts) > 2 else 0,
            )
        alias = {
            "ambient": "t_ambient",
            "inlet": "t_inlet",
            "outlet": "t_outlet",
        }
        for key, value in patch.items():
            if key in ("fault", "clear_faults", "clock"):
                continue
            self.set_value(alias.get(key, key), value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "power": self.power,
            "mode": self.mode,
            "setpoint": self.setpoint,
            "t_inlet": self.t_inlet,
            "t_outlet": self.t_outlet,
            "t_ambient": self.t_ambient,
            "comp_hz": self.comp_hz,
            "fan_rpm": self.fan_rpm,
            "power_kw": self.power_kw,
            "energy_24h_kwh": self.energy_24h_kwh,
            "silent": self.silent,
            "outputs": dict(self.outputs),
            "fault_words": {str(k): v for k, v in self.fault_words.items()},
            "clock": self.clock.strftime("%H:%M:%S"),
            "pages_timeout": self.pages_timeout,
            "dtu": self.dtu,
            "extras": dict(self.extras),
        }


def seed_settings(profile: dict[str, Any]) -> dict[int, int]:
    enums = profile.get("enums") or {}
    settings: dict[int, int] = {}
    for page in (profile.get("service_menu") or {}).get("pages") or []:
        start = int(page["start"])
        qty = int(page["qty"])
        for i in range(qty):
            settings.setdefault(start + i, 0)
    for key, spec in service_menu_params(profile).items():
        default = spec.get("default")
        if default is None:
            continue
        settings[int(spec["reg"])] = encode_value(spec, default, enums) & 0xFFFF
    return settings
