"""Shared entity base."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PoolHeatPumpCoordinator

ENTITY_OBJECT_PREFIX = "pool_heat_pump"


def suggested_object_id(suffix: str | None = None) -> str:
    """HA object_id: device slug, plus a short suffix for child entities."""
    if suffix:
        return f"{ENTITY_OBJECT_PREFIX}_{suffix}"
    return ENTITY_OBJECT_PREFIX


def configuration_url_for(host: str | None) -> str | None:
    if not host:
        return None
    if host in {"replay", "localhost", "127.0.0.1"}:
        return None
    if host.replace(".", "").isdigit() and host.count(".") == 3:
        return f"http://{host}"
    if "." in host:
        return f"http://{host}"
    return None


class PoolHeatPumpEntity(CoordinatorEntity[PoolHeatPumpCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PoolHeatPumpCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        state = self.coordinator.state
        ident = self.coordinator.profile["identity"]
        host = self.coordinator.entry.data.get(CONF_HOST)
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.unique_id)},
            manufacturer=ident["brand"],
            model=ident["model"],
            name=self.coordinator.device_name,
            serial_number=state.serial,
            sw_version=str(state.fw_main) if state.fw_main else None,
            configuration_url=configuration_url_for(host),
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.state.available
