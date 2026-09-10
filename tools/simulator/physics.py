"""Per-tick compressor / water / energy model."""

from __future__ import annotations

from datetime import timedelta
from math import exp
from typing import Any

from .state import SimUnit


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _e03_active(unit: SimUnit) -> bool:
    return bool(unit.fault_words.get(2074, 0) & (1 << 9))


def tick(unit: SimUnit, dt: float, profile: dict[str, Any] | None = None) -> None:
    extras = unit.extras
    h06 = _num(extras.get("h06_min_freq_heat"), 25)
    h07 = _num(extras.get("h07_min_freq_cool"), 25)
    h08 = _num(extras.get("h08_max_freq_heat"), 90)
    h09 = _num(extras.get("h09_max_freq_cool"), 55)
    heating = False
    cooling = False
    target_hz = 0.0
    if _e03_active(unit):
        unit.outputs["water_pump"] = False
        unit.outputs["compressor"] = False
        unit.outputs["four_way_valve"] = False
        unit.outputs["high_fan"] = False
        unit.outputs["low_fan"] = False
        unit.comp_hz_target = 0.0
        unit.comp_hz = 0.0
        unit.fan_rpm = 0
        unit.power_kw = 0.08 if unit.power else 0.0
        unit.phase_current = 0.4 if unit.power else 0.0
        unit.t_inlet += (unit.t_ambient - unit.t_inlet) * (1 - exp(-dt / 120))
        unit.t_outlet = unit.t_inlet
        unit.t_coil = unit.t_inlet
        unit.t_exhaust = unit.t_ambient + 1
        unit.t_suction = unit.t_inlet - 2
        unit.energy_24h_kwh += unit.power_kw * dt / 3600
        unit.energy_total_kwh += unit.power_kw * dt / 3600
        unit.clock = unit.clock + timedelta(seconds=dt)
        _ = profile
        return
    if unit.power:
        unit.outputs["water_pump"] = True
        if unit.mode == "heat":
            heating = unit.t_inlet < unit.setpoint - 0.2
        elif unit.mode == "cool":
            cooling = unit.t_inlet > unit.setpoint + 0.2
        else:
            heating = unit.t_inlet < unit.setpoint - 0.3
            cooling = unit.t_inlet > unit.setpoint + 0.3
        if heating:
            err = unit.setpoint - unit.t_inlet
            target_hz = min(h08, max(h06, h06 + err * 10))
        elif cooling:
            err = unit.t_inlet - unit.setpoint
            target_hz = min(h09, max(h07, h07 + err * 10))
    else:
        unit.outputs["water_pump"] = False
    unit.comp_hz_target = target_hz
    if unit.mode != unit.last_mode:
        # Real controllers stop the compressor at once on a mode change; the
        # slow ramp below is only for normal modulation.
        if unit.last_mode:
            unit.comp_hz = 0.0
        unit.last_mode = unit.mode
    ramp = min(1.0, dt / 8.0)
    unit.comp_hz += (target_hz - unit.comp_hz) * ramp
    if unit.comp_hz < 0.4:
        unit.comp_hz = 0.0
    running = unit.comp_hz > 5
    unit.outputs["compressor"] = running
    unit.outputs["four_way_valve"] = cooling and running
    unit.outputs["high_fan"] = unit.comp_hz > 20
    unit.outputs["low_fan"] = 5 < unit.comp_hz <= 20
    if unit.comp_hz > 1:
        unit.fan_rpm = int(400 + unit.comp_hz * 8)
        unit.power_kw = round(unit.comp_hz / max(h08, 1) * 2.4, 2)
        unit.phase_current = round(unit.power_kw * 4.2, 1)
    else:
        unit.fan_rpm = 0
        unit.power_kw = 0.08 if unit.power else 0.0
        unit.phase_current = 0.4 if unit.power else 0.0
    if running:
        tau = 40.0
        unit.t_inlet += (unit.setpoint - unit.t_inlet) * (1 - exp(-dt / tau))
        delta = 0.04 * unit.comp_hz
        unit.t_outlet = unit.t_inlet - delta if cooling else unit.t_inlet + delta
        unit.t_coil = unit.t_inlet + (-8 if cooling else 8) * (unit.comp_hz / max(h08, 1))
    else:
        unit.t_inlet += (unit.t_ambient - unit.t_inlet) * (1 - exp(-dt / 120))
        unit.t_outlet = unit.t_inlet
        unit.t_coil = unit.t_inlet
    unit.t_exhaust = unit.t_ambient + (8 if running else 1)
    unit.t_suction = unit.t_inlet - 2
    unit.energy_24h_kwh += unit.power_kw * dt / 3600
    unit.energy_total_kwh += unit.power_kw * dt / 3600
    unit.clock = unit.clock + timedelta(seconds=dt)
    _ = profile
