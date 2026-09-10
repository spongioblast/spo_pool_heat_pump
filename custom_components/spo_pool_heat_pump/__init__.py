"""SPO Pool Heat Pump — Modbus RTU client for inverter pool heat pumps."""

from __future__ import annotations

from .const import DOMAIN

try:
    from homeassistant.helpers import config_validation as cv

    CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
except ImportError:
    CONFIG_SCHEMA = None


def _register_dump_http(hass) -> None:
    from .dump_http import DumpDownloadView

    data = hass.data.setdefault(DOMAIN, {})
    if data.get("dump_http"):
        return
    hass.http.register_view(DumpDownloadView())
    data["dump_http"] = True


async def async_setup(hass, config):
    from .frontend import async_register_card
    from .services import async_register_services
    from .websocket import async_register_websocket

    await async_register_card(hass)
    await async_register_services(hass)
    await async_register_websocket(hass)
    _register_dump_http(hass)
    return True


async def async_setup_entry(hass, entry):
    from homeassistant.const import CONF_HOST
    from homeassistant.exceptions import ConfigEntryNotReady

    from .const import CONF_PORT, CONF_PROFILE, PLATFORMS, migrate_entry_storage
    from .coordinator import PoolHeatPumpCoordinator
    from .frontend import async_register_card
    from .profiles import load_profile, migrate_profile_fields
    from .transport.tcp import TcpRtuClient
    from .websocket import async_register_websocket

    await async_register_card(hass)
    await async_register_websocket(hass)
    _register_dump_http(hass)
    data, options, renamed = migrate_profile_fields(dict(entry.data), dict(entry.options))
    data, options, moved = migrate_entry_storage(data, options)
    if renamed or moved:
        hass.config_entries.async_update_entry(entry, data=data, options=options)
    client = TcpRtuClient(data[CONF_HOST], int(data[CONF_PORT]))
    profile_id = options.get(CONF_PROFILE, data.get(CONF_PROFILE))
    profile = await hass.async_add_executor_job(load_profile, profile_id)
    coordinator = PoolHeatPumpCoordinator(hass, entry, client, profile)
    try:
        await coordinator.async_start()
        if coordinator.is_polling:
            await coordinator.async_config_entry_first_refresh()
    except (OSError, ConfigEntryNotReady) as err:
        await coordinator.async_stop()
        if isinstance(err, ConfigEntryNotReady):
            raise
        raise ConfigEntryNotReady(str(err)) from err
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _purge_service_menu_registry(hass, entry)
    return True


async def _purge_service_menu_registry(hass, entry) -> None:
    from homeassistant.helpers import entity_registry as er

    from .profiles import service_menu_params

    coord = entry.runtime_data
    keys = set(service_menu_params(coord.profile))
    registry = er.async_get(hass)
    prefix = f"{coord.unique_id}_"
    for entity in list(registry.entities.values()):
        if entity.config_entry_id != entry.entry_id:
            continue
        unique = entity.unique_id or ""
        suffix = unique[len(prefix) :] if unique.startswith(prefix) else ""
        if suffix in keys or suffix == "temperature_unit":
            registry.async_remove(entity.entity_id)


async def async_unload_entry(hass, entry):
    from .const import PLATFORMS

    unload = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.async_stop()
    return unload


async def _async_reload(hass, entry):
    from .const import reload_option_fingerprint, service_menu_writes_enabled

    coord = getattr(entry, "runtime_data", None)
    fingerprint = reload_option_fingerprint(entry.data, entry.options)
    if coord is not None and fingerprint == getattr(coord, "reload_fingerprint", None):
        coord.driver.service_menu_writes = service_menu_writes_enabled(entry.data, entry.options)
        coord.async_update_listeners()
        return
    await hass.config_entries.async_reload(entry.entry_id)
