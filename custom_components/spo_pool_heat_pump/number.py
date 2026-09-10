"""Timer hour/minute knobs — created from profile map keys."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PoolHeatPumpConfigEntry, PoolHeatPumpCoordinator
from .entity import PoolHeatPumpEntity, suggested_object_id
from .profiles import profile_registers

PARALLEL_UPDATES = 0


def _number_row(key: str) -> tuple[str, str, float, float, str] | None:
    if key.endswith("_min"):
        return key, key, 0, 59, "min"
    if key.endswith("_h"):
        return key, key, 0, 23, "h"
    return None


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolHeatPumpConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: PoolHeatPumpCoordinator = entry.runtime_data
    rows = [_number_row(key) for key in profile_registers(coord.profile) if _number_row(key)]
    async_add_entities([PoolHeatPumpNumber(coord, *row) for row in rows if row])


class PoolHeatPumpNumber(PoolHeatPumpEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: PoolHeatPumpCoordinator,
        key: str,
        translation_key: str,
        minimum: float,
        maximum: float,
        unit: str,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{coordinator.unique_id}_{key}"
        self._attr_suggested_object_id = suggested_object_id(key)
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> float:
        return float(self.coordinator.state.extras.get(self._key) or 0)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.driver.write_register(self._key, int(value))
