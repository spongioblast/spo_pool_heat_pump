"""Compressor / pump / fault bits."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PoolHeatPumpConfigEntry, PoolHeatPumpCoordinator
from .drivers.base import HeatPumpState
from .entity import PoolHeatPumpEntity, suggested_object_id
from .profiles import profile_registers

PARALLEL_UPDATES = 0

BITS = (
    ("compressor_running", "compressor_running", lambda s: s.compressor_on, BinarySensorDeviceClass.RUNNING, EntityCategory.DIAGNOSTIC),
    ("pump_running", "pump_running", lambda s: s.pump_on, BinarySensorDeviceClass.RUNNING, EntityCategory.DIAGNOSTIC),
    ("fault", "fault", lambda s: bool(s.faults), BinarySensorDeviceClass.PROBLEM, None),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolHeatPumpConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: PoolHeatPumpCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [PoolHeatPumpBinary(coord, *row) for row in BITS]
    for key, spec in profile_registers(coord.profile).items():
        ent = spec.get("entity") or {}
        if ent.get("platform") != "binary_sensor":
            continue
        bits = spec.get("bits") or {}
        if spec.get("type") == "bits" and bits:
            for bit_name in bits:
                entities.append(ProfileBitBinary(coord, key, bit_name, ent))
        else:
            entities.append(ProfileBitBinary(coord, key, key, ent))
    async_add_entities(entities)


class PoolHeatPumpBinary(PoolHeatPumpEntity, BinarySensorEntity):
    def __init__(
        self,
        coordinator: PoolHeatPumpCoordinator,
        key: str,
        translation_key: str,
        is_on: Callable[[HeatPumpState], bool],
        device_class: BinarySensorDeviceClass | None,
        category: EntityCategory | None,
    ) -> None:
        super().__init__(coordinator)
        self._is_on = is_on
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{coordinator.unique_id}_{key}"
        self._attr_suggested_object_id = suggested_object_id(key)
        self._attr_device_class = device_class
        self._attr_entity_category = category

    @property
    def is_on(self) -> bool:
        return self._is_on(self.coordinator.state)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        if self.translation_key != "fault":
            return None
        state = self.coordinator.state
        if not state.fault_code:
            return None
        attrs = {"code": state.fault_code}
        if state.fault_text:
            attrs["text"] = state.fault_text
        return attrs


class ProfileBitBinary(PoolHeatPumpEntity, BinarySensorEntity):
    def __init__(
        self,
        coordinator: PoolHeatPumpCoordinator,
        group: str,
        bit_name: str,
        ent: dict,
    ) -> None:
        super().__init__(coordinator)
        self._group = group
        self._bit_name = bit_name
        self._attr_translation_key = bit_name
        self._attr_unique_id = f"{coordinator.unique_id}_{group}_{bit_name}"
        self._attr_suggested_object_id = suggested_object_id(bit_name)
        if ent.get("category") == "diagnostic":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = bool(ent.get("enabled", False))

    @property
    def is_on(self) -> bool:
        state = self.coordinator.state
        if self._group == "outputs":
            return bool(state.outputs.get(self._bit_name))
        bits = state.values.get(self._group, state.extras.get(self._group)) or {}
        if isinstance(bits, dict):
            return bool(bits.get(self._bit_name))
        return bool(bits)
