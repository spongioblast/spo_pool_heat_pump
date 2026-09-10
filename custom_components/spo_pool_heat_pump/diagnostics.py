"""Redacted diagnostics."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import PoolHeatPumpConfigEntry
from .dump import dir_used_bytes, list_dump_files
from .profiles import booklet_unmapped, profile_registers, service_menu_params

TO_REDACT = {"serial", "host"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PoolHeatPumpConfigEntry
) -> dict[str, Any]:
    coord = entry.runtime_data
    state = coord.state
    return async_redact_data(
        {
            "entry": {**entry.data, **entry.options},
            "profile": coord.profile["identity"],
            "state": {
                "available": state.available,
                "power": state.power,
                "mode": state.mode,
                "setpoint": state.setpoint,
                "t_inlet": state.t_inlet,
                "t_outlet": state.t_outlet,
                "t_ambient": state.t_ambient,
                "power_kw": state.power_kw,
                "energy_24h_kwh": state.energy_24h_kwh,
                "comp_hz": state.comp_hz,
                "outputs": state.outputs,
                "faults": state.faults,
                "fault_text": state.fault_text,
                "serial": state.serial,
            },
            "raw": state.raw,
            "settings": getattr(coord.driver, "settings", None) and coord.driver.settings.regs,
            "clock": state.clock,
            "service_menu": {
                key: state.extras[key]
                for key in service_menu_params(coord.profile)
                if key in state.extras
            },
            "service_menu_writes": coord.service_menu_writes,
            "fault_booklet_unmapped": booklet_unmapped(profile_registers(coord.profile).get("faults") or {}),
            "dumps": {
                "used_bytes": dir_used_bytes(coord.dumps_path()),
                "files": [
                    {"name": row["name"], "size": row["size"], "started": row["started"]}
                    for row in list_dump_files(coord.dumps_path())
                ],
            },
        },
        TO_REDACT,
    )
