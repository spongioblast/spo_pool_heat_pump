"""COP for the card: controller register when non-zero, else optional flow calc."""

from __future__ import annotations

import math
from typing import Any

from .const import (
    CONF_MANUAL_COP_FLOW,
    CONF_WATER_FLOW_M3H,
    COP_KW_PER_M3H_K,
    WATER_FLOW_MAX,
    WATER_FLOW_MIN,
)
from .drivers.base import HeatPumpState

COP_SOURCE_CONTROLLER = "controller"
COP_SOURCE_CALCULATED = "calculated"


def cop_options(data: dict[str, Any] | None, options: dict[str, Any] | None = None) -> dict[str, Any]:
    opts = options or {}
    src = data or {}
    return {
        CONF_MANUAL_COP_FLOW: bool(opts.get(CONF_MANUAL_COP_FLOW, src.get(CONF_MANUAL_COP_FLOW, False))),
        CONF_WATER_FLOW_M3H: _flow_value(opts.get(CONF_WATER_FLOW_M3H, src.get(CONF_WATER_FLOW_M3H, 0))),
    }


def _flow_value(raw: Any) -> float:
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def coerce_cop_option(key: str, value: Any) -> bool | float:
    if key == CONF_MANUAL_COP_FLOW:
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "on", "yes")
        return bool(value)
    if key != CONF_WATER_FLOW_M3H:
        raise KeyError(key)
    flow = float(value)
    if flow == 0:
        return 0.0
    if flow < WATER_FLOW_MIN or flow > WATER_FLOW_MAX:
        raise ValueError(f"water flow must be 0 or {WATER_FLOW_MIN}–{WATER_FLOW_MAX} m³/h")
    return round(flow, 1)


def _bus_cop(state: HeatPumpState) -> float | None:
    raw = state.values.get("cop", state.extras.get("cop"))
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value == 0 or not math.isfinite(value):
        return None
    return value


def resolve_cop(state: HeatPumpState, options: dict[str, Any] | None = None) -> tuple[float | None, str | None]:
    opts = options or {}
    if bool(opts.get(CONF_MANUAL_COP_FLOW)):
        flow = _flow_value(opts.get(CONF_WATER_FLOW_M3H))
        if flow <= 0 or state.t_inlet is None or state.t_outlet is None:
            return None, None
        power = state.power_kw
        if power is None or power <= 0:
            return None, None
        heat = COP_KW_PER_M3H_K * flow * abs(state.t_outlet - state.t_inlet)
        cop = heat / power
        if cop == 0 or not math.isfinite(cop):
            return None, None
        return round(cop, 1), COP_SOURCE_CALCULATED
    bus = _bus_cop(state)
    if bus is None:
        return None, None
    return round(bus, 1), COP_SOURCE_CONTROLLER
