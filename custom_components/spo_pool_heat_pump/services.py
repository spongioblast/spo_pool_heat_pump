"""Integration services. Registered once in async_setup."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN
from .coordinator import PoolHeatPumpCoordinator
from .dump import DumpError
from .profiles import validate_service_menu_write


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> PoolHeatPumpCoordinator:
    found = PoolHeatPumpCoordinator._matches(
        hass, entry_id=call.data.get("entry_id"), device_id=call.data.get("device_id")
    )
    if len(found) == 1:
        return found[0].runtime_data
    if len(found) > 1:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="multiple_entries")
    raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_entry")


async def async_register_services(hass: HomeAssistant) -> None:
    if hass.data.setdefault(DOMAIN, {}).get("services"):
        return

    async def refresh_service_menu(call: ServiceCall) -> None:
        coord = _coordinator(hass, call)
        ok = await coord.driver.async_refresh()
        if not ok:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="service_menu_timeout")

    async def set_service_menu(call: ServiceCall) -> None:
        coord = _coordinator(hass, call)
        try:
            validate_service_menu_write(coord.profile, coord.service_menu_writes, call.data["key"])
        except PermissionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="service_menu_writes_disabled"
            ) from err
        except KeyError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="service_menu_not_writable",
                translation_placeholders={"key": call.data["key"]},
            ) from err
        await coord.driver.write_register(call.data["key"], call.data["value"])

    async def start_dump(call: ServiceCall) -> None:
        coord = _coordinator(hass, call)
        try:
            await coord.start_dump(
                duration_s=int(call.data.get("duration", 900)),
                note=str(call.data.get("note") or ""),
                include_writes=bool(call.data.get("include_writes", True)),
            )
        except DumpError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=err.key) from err

    async def stop_dump(call: ServiceCall) -> None:
        coord = _coordinator(hass, call)
        try:
            await coord.stop_dump()
        except DumpError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=err.key) from err

    hass.services.async_register(
        DOMAIN,
        "refresh_service_menu",
        refresh_service_menu,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): cv.string,
                vol.Optional("device_id"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "set_service_menu",
        set_service_menu,
        schema=vol.Schema(
            {
                vol.Required("key"): cv.string,
                vol.Required("value"): vol.Any(int, float, str, bool),
                vol.Optional("entry_id"): cv.string,
                vol.Optional("device_id"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "start_dump",
        start_dump,
        schema=vol.Schema(
            {
                vol.Optional("duration", default=900): vol.All(int, vol.Range(min=0, max=7200)),
                vol.Optional("note", default=""): cv.string,
                vol.Optional("include_writes", default=True): cv.boolean,
                vol.Optional("entry_id"): cv.string,
                vol.Optional("device_id"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "stop_dump",
        stop_dump,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): cv.string,
                vol.Optional("device_id"): cv.string,
            }
        ),
    )
    hass.data[DOMAIN]["services"] = True
