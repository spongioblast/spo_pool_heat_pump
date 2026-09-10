"""Quiet + OEM timers as switches."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PoolHeatPumpConfigEntry, PoolHeatPumpCoordinator
from .drivers.base import HeatPumpState
from .entity import PoolHeatPumpEntity, suggested_object_id
from .profiles import is_bool_spec, profile_registers

PARALLEL_UPDATES = 0


@dataclass(frozen=True, slots=True)
class SwitchDef:
    key: str
    translation_key: str
    is_on: Callable[[HeatPumpState], bool]
    turn: str  # method name on driver or write map key
    entity_category: EntityCategory | None = None


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolHeatPumpConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: PoolHeatPumpCoordinator = entry.runtime_data
    mapping = profile_registers(coord.profile)
    entities: list[SwitchEntity] = []
    if "silent" in mapping:
        entities.append(PoolHeatPumpSwitch(coord, SwitchDef("silent", "silent", lambda s: s.silent, "set_silent")))
    for key, spec in mapping.items():
        if key == "silent":
            continue
        if not is_bool_spec(spec):
            continue
        if key.startswith("timer") or key.startswith("silent_timer"):
            entities.append(PoolHeatPumpWriteSwitch(coord, key, key, EntityCategory.CONFIG))
    async_add_entities(entities)


class PoolHeatPumpSwitch(PoolHeatPumpEntity, SwitchEntity):
    def __init__(self, coordinator: PoolHeatPumpCoordinator, spec: SwitchDef) -> None:
        super().__init__(coordinator)
        self._spec = spec
        self._attr_translation_key = spec.translation_key
        self._attr_unique_id = f"{coordinator.unique_id}_{spec.key}"
        suffix = "quiet" if spec.key == "silent" else spec.key
        self._attr_suggested_object_id = suggested_object_id(suffix)
        self._attr_entity_category = spec.entity_category

    @property
    def is_on(self) -> bool:
        return self._spec.is_on(self.coordinator.state)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await getattr(self.coordinator.driver, self._spec.turn)(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await getattr(self.coordinator.driver, self._spec.turn)(False)


class PoolHeatPumpWriteSwitch(PoolHeatPumpEntity, SwitchEntity):
    def __init__(
        self,
        coordinator: PoolHeatPumpCoordinator,
        key: str,
        translation_key: str,
        category: EntityCategory | None,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{coordinator.unique_id}_{key}"
        self._attr_suggested_object_id = suggested_object_id(key)
        self._attr_entity_category = category

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.state.extras.get(self._key, False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.driver.write_register(self._key, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.driver.write_register(self._key, 0)
