"""Admin WebSocket API for the parameter browser."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import PoolHeatPumpCoordinator
from .cop import coerce_cop_option
from .dump import DumpError
from .drivers.listen_only import DumpOnlyWriteError
from .parameters import LOCAL_COP_KEYS, catalog_payload, coerce_write_value
from .profiles import lookup_write_spec


def _catalog(coord: PoolHeatPumpCoordinator) -> dict[str, Any]:
    return catalog_payload(
        coord.profile,
        coord.state,
        service_menu_writes=coord.service_menu_writes,
        options=coord.cop_options,
    )


def _require_coord(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> PoolHeatPumpCoordinator | None:
    coord = PoolHeatPumpCoordinator.resolve(
        hass, entry_id=msg.get("entry_id"), entity_id=msg.get("entity_id")
    )
    if coord is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Unknown pool heat pump entry")
    return coord


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "spo_pool_heat_pump/parameters/list",
        vol.Optional("entry_id"): str,
        vol.Optional("entity_id"): str,
    }
)
@websocket_api.async_response
async def ws_parameters_list(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    coord = _require_coord(hass, connection, msg)
    if coord is None:
        return
    connection.send_result(msg["id"], _catalog(coord))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "spo_pool_heat_pump/parameters/set",
        vol.Required("key"): str,
        vol.Required("value"): vol.Any(int, float, str, bool),
        vol.Optional("entry_id"): str,
        vol.Optional("entity_id"): str,
    }
)
@websocket_api.async_response
async def ws_parameters_set(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    coord = _require_coord(hass, connection, msg)
    if coord is None:
        return
    key = msg["key"]
    try:
        if key in LOCAL_COP_KEYS:
            value = coerce_cop_option(key, msg["value"])
            options = {**coord.entry.options, key: value}
            hass.config_entries.async_update_entry(coord.entry, options=options)
        else:
            spec = lookup_write_spec(coord.profile, key)
            value = coerce_write_value(spec, msg["value"])
            await coord.driver.write_register(key, value)
    except DumpOnlyWriteError:
        connection.send_error(msg["id"], "dump_only_no_writes", "Dump-only profile does not write. Capture a bus dump, then switch to a real profile.")
        return
    except PermissionError:
        connection.send_error(msg["id"], "service_menu_writes_disabled", "Enable changing service settings in the integration options first")
        return
    except KeyError:
        connection.send_error(msg["id"], "not_writable", f"{key} is not a writable parameter")
        return
    except (TypeError, ValueError) as err:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err))
        return
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "write_failed", str(err))
        return
    connection.send_result(msg["id"], _catalog(coord))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "spo_pool_heat_pump/parameters/refresh",
        vol.Optional("entry_id"): str,
        vol.Optional("entity_id"): str,
    }
)
@websocket_api.async_response
async def ws_parameters_refresh(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    coord = _require_coord(hass, connection, msg)
    if coord is None:
        return
    ok = await coord.driver.async_refresh()
    connection.send_result(
        msg["id"],
        {
            "ok": ok,
            **_catalog(coord),
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "spo_pool_heat_pump/dump/status",
        vol.Optional("entry_id"): str,
        vol.Optional("entity_id"): str,
    }
)
@websocket_api.async_response
async def ws_dump_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    coord = _require_coord(hass, connection, msg)
    if coord is None:
        return
    connection.send_result(msg["id"], await coord.async_dump_status())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "spo_pool_heat_pump/dump/start",
        vol.Optional("duration_s"): int,
        vol.Optional("note"): str,
        vol.Optional("include_writes"): bool,
        vol.Optional("entry_id"): str,
        vol.Optional("entity_id"): str,
    }
)
@websocket_api.async_response
async def ws_dump_start(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    coord = _require_coord(hass, connection, msg)
    if coord is None:
        return
    try:
        payload = await coord.start_dump(
            duration_s=int(msg.get("duration_s", 900)),
            note=str(msg.get("note") or ""),
            include_writes=bool(msg.get("include_writes", True)),
        )
    except DumpError as err:
        connection.send_error(msg["id"], err.key, str(err) or err.key)
        return
    connection.send_result(msg["id"], payload)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "spo_pool_heat_pump/dump/stop",
        vol.Optional("entry_id"): str,
        vol.Optional("entity_id"): str,
    }
)
@websocket_api.async_response
async def ws_dump_stop(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    coord = _require_coord(hass, connection, msg)
    if coord is None:
        return
    try:
        payload = await coord.stop_dump()
    except DumpError as err:
        connection.send_error(msg["id"], err.key, str(err) or err.key)
        return
    connection.send_result(msg["id"], payload)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "spo_pool_heat_pump/dump/delete",
        vol.Required("name"): str,
        vol.Optional("entry_id"): str,
        vol.Optional("entity_id"): str,
    }
)
@websocket_api.async_response
async def ws_dump_delete(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    coord = _require_coord(hass, connection, msg)
    if coord is None:
        return
    try:
        payload = await coord.async_delete_dump(str(msg["name"]))
    except DumpError as err:
        connection.send_error(msg["id"], err.key, str(err) or err.key)
        return
    connection.send_result(msg["id"], payload)


async def async_register_websocket(hass: HomeAssistant) -> None:
    if hass.data.setdefault(DOMAIN, {}).get("websocket"):
        return
    websocket_api.async_register_command(hass, ws_parameters_list)
    websocket_api.async_register_command(hass, ws_parameters_set)
    websocket_api.async_register_command(hass, ws_parameters_refresh)
    websocket_api.async_register_command(hass, ws_dump_status)
    websocket_api.async_register_command(hass, ws_dump_start)
    websocket_api.async_register_command(hass, ws_dump_stop)
    websocket_api.async_register_command(hass, ws_dump_delete)
    hass.data[DOMAIN]["websocket"] = True
