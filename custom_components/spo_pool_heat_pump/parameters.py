"""Unified parameter catalog: registers + service_menu.params, with risk tiers."""

from __future__ import annotations

from typing import Any

from .const import CONF_MANUAL_COP_FLOW, CONF_WATER_FLOW_M3H, WATER_FLOW_MAX, WATER_FLOW_MIN
from .cop import cop_options
from .drivers.base import HeatPumpState
from .profiles import is_bool_spec, profile_registers, service_menu_params

LOCAL_COP_KEYS = frozenset({CONF_MANUAL_COP_FLOW, CONF_WATER_FLOW_M3H})

TIER_SAFE = "safe"
TIER_SERVICE_MENU = "service_menu"
TIER_READONLY = "readonly"

REGISTER_GROUP_ORDER = ("Control", "Timers", "Status", "Outputs", "Identity")
SERVICE_MENU_GROUP_ORDER = ("H", "F", "D", "E", "P", "R", "T", "U", "KW")
SERVICE_MENU_GROUP_LABELS = {
    "H": "System (H)",
    "F": "Fan (F)",
    "D": "Defrost (D)",
    "E": "Expansion valve (E)",
    "P": "Water pump (P)",
    "R": "Limits (R)",
    "T": "Timers (T)",
    "U": "Unit (U)",
    "KW": "Power (KW)",
}

CONTROL_KEYS = {
    "power",
    "mode",
    "setpoint",
    "setpoint_heat",
    "setpoint_cool",
    "setpoint_auto",
    "silent",
    "silent_timer",
}
IDENTITY_KEYS = {"serial", "fw_display", "fw_main", "fw_mini"}
OUTPUT_KEYS = {"outputs", "faults", "switches"}

REGISTER_LABELS = {
    "power": "Power",
    "mode": "Mode",
    "setpoint": "Setpoint",
    "setpoint_heat": "Heat setpoint",
    "setpoint_cool": "Cool setpoint",
    "setpoint_auto": "Auto setpoint",
    "silent": "Quiet",
    "silent_timer": "Quiet timer",
    "silent_timer_start_h": "Quiet timer start hour",
    "silent_timer_stop_h": "Quiet timer stop hour",
    "timer1_on": "Timer 1 on",
    "timer1_off": "Timer 1 off",
    "timer1_on_h": "Timer 1 on hour",
    "timer1_on_min": "Timer 1 on minute",
    "timer1_off_h": "Timer 1 off hour",
    "timer1_off_min": "Timer 1 off minute",
    "timer2_on": "Timer 2 on",
    "timer2_off": "Timer 2 off",
    "timer2_on_h": "Timer 2 on hour",
    "timer2_on_min": "Timer 2 on minute",
    "timer2_off_h": "Timer 2 off hour",
    "timer2_off_min": "Timer 2 off minute",
    "t_inlet": "Inlet",
    "t_outlet": "Outlet",
    "t_ambient": "Ambient",
    "t_coil": "Coil",
    "t_exhaust": "Exhaust",
    "t_suction": "Suction",
    "t_coil_2": "Coil 2",
    "power_kw": "Power",
    "energy_24h_kwh": "Energy 24h",
    "comp_hz": "Compressor frequency",
    "comp_hz_target": "Target frequency",
    "fan_rpm": "Fan",
    "serial": "Serial",
    "fw_display": "Display firmware",
    "fw_main": "Main firmware",
    "fw_mini": "Mini firmware",
    "outputs": "Outputs",
    "faults": "Faults",
    "clock": "Panel clock",
    "low_pressure": "Low pressure",
    "superheat": "Superheat",
    "ac_voltage": "AC voltage",
    "dc_bus": "DC bus",
    "phase_current": "Phase current",
    "ipm_temp": "IPM temperature",
    "eev_steps": "EEV steps",
    "antifreeze": "Antifreeze",
    "cop": "COP",
    "capacity": "Capacity",
    "switches": "Switches",
}

REGISTER_UNITS = {
    "t_inlet": "°C",
    "t_outlet": "°C",
    "t_ambient": "°C",
    "t_coil": "°C",
    "t_exhaust": "°C",
    "t_suction": "°C",
    "t_coil_2": "°C",
    "setpoint": "°C",
    "setpoint_heat": "°C",
    "setpoint_cool": "°C",
    "setpoint_auto": "°C",
    "ipm_temp": "°C",
    "antifreeze": "°C",
    "superheat": "°C",
    "power_kw": "kW",
    "energy_24h_kwh": "kWh",
    "comp_hz": "Hz",
    "comp_hz_target": "Hz",
    "fan_rpm": "rpm",
    "low_pressure": "bar",
    "ac_voltage": "V",
    "dc_bus": "V",
    "phase_current": "A",
}


def service_menu_bounds(spec: dict) -> tuple[float, float, float]:
    unit = spec.get("unit") or ""
    step = 0.1 if spec.get("scale") == 0.1 else 1
    if spec.get("min") is not None and spec.get("max") is not None:
        return float(spec["min"]), float(spec["max"]), step
    if unit in ("°C", "C"):
        return -30, 80, step
    if unit == "Hz":
        return 0, 120, step
    if unit == "bar":
        return 0, 50, step
    if unit == "h":
        return 0, 23, 1
    if unit == "min":
        return 0, 600, 1
    if unit == "rpm":
        return 0, 2000, 1
    if unit == "A":
        return 0, 50, step
    return -1000, 10000, step


def group_order(profile: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> list[str]:
    seen: list[str] = []
    for row in rows if rows is not None else parameter_catalog(profile):
        group = row["group"]
        if group not in seen:
            seen.append(group)
    ranked = [g for g in (*REGISTER_GROUP_ORDER, *SERVICE_MENU_GROUP_ORDER) if g in seen]
    ranked.extend(g for g in seen if g not in ranked)
    return ranked


def _register_group(key: str, spec: dict[str, Any]) -> str:
    if spec.get("group"):
        return str(spec["group"])
    if key in CONTROL_KEYS:
        return "Control"
    if key.startswith("timer") or key.startswith("silent_timer_"):
        return "Timers"
    if key in IDENTITY_KEYS:
        return "Identity"
    if key in OUTPUT_KEYS:
        return "Outputs"
    return "Status"


def _register_label(key: str, spec: dict[str, Any]) -> str:
    if spec.get("label"):
        return str(spec["label"])
    if key in REGISTER_LABELS:
        return REGISTER_LABELS[key]
    return key.replace("_", " ")


def _register_unit(key: str, spec: dict[str, Any]) -> str | None:
    if spec.get("unit"):
        return str(spec["unit"])
    return REGISTER_UNITS.get(key)


def _register_bounds(key: str, spec: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    typ = spec.get("type")
    if typ in ("bits", "faults", "ascii", "bcd_hms"):
        return None, None, None
    if spec.get("min") is not None and spec.get("max") is not None:
        step = 0.1 if spec.get("scale") == 0.1 else 1
        return float(spec["min"]), float(spec["max"]), step
    if is_bool_spec(spec):
        return 0, 1, 1
    if key.startswith("setpoint"):
        return 8, 40, 0.5
    if key.endswith("_min"):
        return 0, 59, 1
    if key.endswith("_h"):
        return 0, 23, 1
    lo, hi, step = service_menu_bounds({**spec, "unit": _register_unit(key, spec) or spec.get("unit") or ""})
    return lo, hi, step


def _tier(spec: dict[str, Any], *, service_menu: bool) -> str:
    if service_menu:
        return TIER_SERVICE_MENU if spec.get("writable") else TIER_READONLY
    if spec.get("write") is not None:
        return TIER_SAFE
    return TIER_READONLY


def _enum_options(spec: dict[str, Any], enums: dict[str, Any]) -> list[str] | None:
    name = spec.get("enum")
    if spec.get("type") == "enum" or name:
        table = enums.get(name or "", {})
        return [str(v) for v in table.values()]
    return None


def _display_label(label: str) -> str:
    text = str(label).strip()
    if not text:
        return text
    return text[:1].upper() + text[1:]


def _jsonable(value: Any, *, scale: float | None = None) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if scale == 0.1:
            return round(value, 1)
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v, scale=scale) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v, scale=scale) for v in value]
    return str(value)


def parameter_value(state: HeatPumpState | None, key: str, spec: dict[str, Any]) -> Any:
    if state is None:
        return None
    typ = spec.get("type")
    if typ == "bits":
        if key == "outputs":
            return dict(state.outputs)
        bits = state.values.get(key, state.extras.get(key))
        return bits if isinstance(bits, dict) else None
    if typ == "faults":
        return list(state.faults)
    if typ == "ascii" or key == "serial":
        return state.serial
    if typ == "bcd_hms" or key == "clock":
        return state.clock
    return _jsonable(state.get(key), scale=spec.get("scale"))


def _row(
    key: str,
    spec: dict[str, Any],
    *,
    service_menu: bool,
    enums: dict[str, Any],
    state: HeatPumpState | None,
) -> dict[str, Any]:
    lo, hi, step = (service_menu_bounds(spec) if service_menu else _register_bounds(key, spec))
    if service_menu and spec.get("type") in ("bits", "faults", "ascii", "bcd_hms"):
        lo = hi = step = None
    app = spec.get("app")
    group = str(spec.get("group") or _register_group(key, spec))
    row = {
        "key": key,
        "label": _display_label(str(spec.get("label") or _register_label(key, spec))),
        "group": group,
        "group_label": SERVICE_MENU_GROUP_LABELS.get(group, group),
        "app": str(app) if app else None,
        "unit": spec.get("unit") if service_menu else _register_unit(key, spec),
        "min": lo,
        "max": hi,
        "step": step,
        "type": spec.get("type") or ("bool" if is_bool_spec(spec) else "u16"),
        "options": _enum_options(spec, enums),
        "tier": _tier(spec, service_menu=service_menu),
        "value": parameter_value(state, key, spec),
        "default": spec.get("default"),
    }
    return row


def parameter_catalog(
    profile: dict[str, Any],
    state: HeatPumpState | None = None,
) -> list[dict[str, Any]]:
    """One row per register and service-menu param, in profile order."""
    enums = profile.get("enums") or {}
    rows: list[dict[str, Any]] = []
    for key, spec in profile_registers(profile).items():
        if not isinstance(spec, dict):
            continue
        rows.append(_row(key, spec, service_menu=False, enums=enums, state=state))
    for key, spec in service_menu_params(profile).items():
        if not isinstance(spec, dict):
            continue
        rows.append(_row(key, spec, service_menu=True, enums=enums, state=state))
    return rows


def local_cop_rows(options: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    opts = cop_options({}, options or {})
    return [
        {
            "key": CONF_MANUAL_COP_FLOW,
            "label": "Use manual flow for COP",
            "group": "Control",
            "group_label": "Control",
            "app": None,
            "unit": None,
            "min": 0,
            "max": 1,
            "step": 1,
            "type": "bool",
            "options": None,
            "tier": TIER_SAFE,
            "value": bool(opts[CONF_MANUAL_COP_FLOW]),
            "default": False,
        },
        {
            "key": CONF_WATER_FLOW_M3H,
            "label": "Water flow",
            "group": "Control",
            "group_label": "Control",
            "app": None,
            "unit": "m³/h",
            "min": WATER_FLOW_MIN,
            "max": WATER_FLOW_MAX,
            "step": 0.1,
            "type": "i16",
            "options": None,
            "tier": TIER_SAFE,
            "value": opts[CONF_WATER_FLOW_M3H],
            "default": 0,
        },
    ]


def catalog_payload(
    profile: dict[str, Any],
    state: HeatPumpState | None,
    *,
    service_menu_writes: bool,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ident = profile.get("identity") or {}
    rows = local_cop_rows(options) + parameter_catalog(profile, state)
    return {
        "parameters": rows,
        "service_menu_writes": bool(service_menu_writes),
        "verification": ident.get("verification"),
        "profile": ident.get("id"),
        "groups": group_order(profile, rows),
    }


def coerce_write_value(spec: dict[str, Any], value: Any) -> Any:
    if is_bool_spec(spec):
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "on", "yes")
        return bool(value)
    if spec.get("type") == "enum" or spec.get("enum"):
        return value
    if spec.get("scale") and spec.get("scale") != 1:
        return float(value)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if number.is_integer() and spec.get("scale", 1) == 1:
        return int(number)
    return number
