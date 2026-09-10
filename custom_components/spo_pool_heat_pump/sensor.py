"""Sensors — capability-gated. 2057 is MEASUREMENT; Energy total is TOTAL_INCREASING."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PoolHeatPumpConfigEntry, PoolHeatPumpCoordinator
from .cop import resolve_cop
from .drivers.base import HeatPumpState
from .entity import PoolHeatPumpEntity, suggested_object_id
from .profiles import profile_registers
from .publish import should_publish_sensor

PARALLEL_UPDATES = 0


@dataclass(frozen=True, slots=True)
class SensorDef:
    key: str
    translation_key: str
    capability: str | None
    value: Callable[[HeatPumpState], float | int | None]
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    unit: str | None = None
    entity_category: EntityCategory | None = None
    enabled_default: bool = True
    suggested_precision: int | None = 1


SENSORS = (
    SensorDef("inlet", "inlet", None, lambda s: s.t_inlet, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, UnitOfTemperature.CELSIUS),
    SensorDef("outlet", "outlet", None, lambda s: s.t_outlet, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, UnitOfTemperature.CELSIUS),
    SensorDef("ambient", "ambient", "ambient", lambda s: s.t_ambient, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, UnitOfTemperature.CELSIUS),
    SensorDef("power", "power", "power_meter", lambda s: s.power_kw, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, UnitOfPower.KILO_WATT),
    SensorDef("energy_24h", "energy_24h", "energy_24h", lambda s: s.energy_24h_kwh, None, SensorStateClass.MEASUREMENT, UnitOfEnergy.KILO_WATT_HOUR),
    SensorDef("compressor", "compressor", "compressor_hz", lambda s: s.compressor_pct, None, SensorStateClass.MEASUREMENT, PERCENTAGE),
    SensorDef("compressor_hz", "compressor_hz", "compressor_hz", lambda s: s.comp_hz, SensorDeviceClass.FREQUENCY, SensorStateClass.MEASUREMENT, UnitOfFrequency.HERTZ, EntityCategory.DIAGNOSTIC, False, 0),
    SensorDef("fan", "fan", None, lambda s: s.fan_rpm, None, SensorStateClass.MEASUREMENT, "rpm"),
)

MAP_SENSORS = {
    "t_coil": SensorDef("coil", "coil", None, lambda s: s.t_coil, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, UnitOfTemperature.CELSIUS, EntityCategory.DIAGNOSTIC),
    "t_exhaust": SensorDef("exhaust", "exhaust", None, lambda s: s.t_exhaust, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, UnitOfTemperature.CELSIUS, EntityCategory.DIAGNOSTIC),
    "fw_display": SensorDef("fw_display", "fw_display", None, lambda s: s.fw_display, None, None, None, EntityCategory.DIAGNOSTIC, False, 0),
    "fw_main": SensorDef("fw_main", "fw_main", None, lambda s: s.fw_main, None, None, None, EntityCategory.DIAGNOSTIC, False, 0),
    "fw_mini": SensorDef("fw_mini", "fw_mini", None, lambda s: s.extras.get("fw_mini"), None, None, None, EntityCategory.DIAGNOSTIC, False, 0),
}


_SENSOR_GATE = {
    "ambient": "t_ambient",
    "power": "power_kw",
    "energy_24h": "energy_24h_kwh",
    "compressor": "comp_hz",
    "compressor_hz": "comp_hz",
    "fan": "fan_rpm",
}

_DEVICE_CLASS = {
    "temperature": SensorDeviceClass.TEMPERATURE,
    "pressure": SensorDeviceClass.PRESSURE,
    "voltage": SensorDeviceClass.VOLTAGE,
    "current": SensorDeviceClass.CURRENT,
    "frequency": SensorDeviceClass.FREQUENCY,
    "power": SensorDeviceClass.POWER,
    "energy": SensorDeviceClass.ENERGY,
}

_UNITS = {
    "°C": UnitOfTemperature.CELSIUS,
    "C": UnitOfTemperature.CELSIUS,
    "V": UnitOfElectricPotential.VOLT,
    "A": UnitOfElectricCurrent.AMPERE,
    "Hz": UnitOfFrequency.HERTZ,
    "bar": UnitOfPressure.BAR,
    "kW": UnitOfPower.KILO_WATT,
    "kWh": UnitOfEnergy.KILO_WATT_HOUR,
}


def _state_value(state: HeatPumpState, key: str) -> float | int | None:
    value = state.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolHeatPumpConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: PoolHeatPumpCoordinator = entry.runtime_data
    mapping = profile_registers(coord.profile)
    entities: list[SensorEntity] = []
    for spec in SENSORS:
        gate = _SENSOR_GATE.get(spec.key)
        if gate and gate not in mapping:
            continue
        entities.append(PoolHeatPumpSensor(coord, spec))
    for map_key, spec in MAP_SENSORS.items():
        if map_key in mapping:
            entities.append(PoolHeatPumpSensor(coord, spec))
    if "power_kw" in mapping:
        entities.append(EnergyTotalSensor(coord))
    if "clock" in mapping or coord.profile.get("service_menu") or coord.profile["driver"]["type"] == "pc1002_bus":
        entities.append(PanelClockSensor(coord))
    if coord.profile["driver"]["type"] != "listen_only":
        entities.append(CopDisplaySensor(coord))
    claimed = {spec.key for spec in SENSORS} | {spec.key for spec in MAP_SENSORS.values()}
    claimed.update({"energy_total", "panel_clock", "inlet", "outlet", "ambient", "power", "fan", "coil", "exhaust", "cop_display"})
    for key, spec in mapping.items():
        ent = spec.get("entity") or {}
        if ent.get("platform") != "sensor":
            continue
        if key in claimed or any(getattr(e, "_key", None) == key for e in entities):
            continue
        entities.append(ProfileRegisterSensor(coord, key, spec, ent))
    async_add_entities(entities)


class ThrottledSensorMixin:
    """Write HA state at most every 15 s unless a discrete fingerprint forced it."""

    def __init__(self, *args, **kwargs) -> None:
        self._seen_force_seq = 0
        self._last_write: float | None = None
        super().__init__(*args, **kwargs)

    @callback
    def _handle_coordinator_update(self) -> None:
        now = time.monotonic()
        force_seq = getattr(self.coordinator, "force_seq", 0)
        if not should_publish_sensor(self._last_write, now, force_seq, self._seen_force_seq):
            return
        self._seen_force_seq = force_seq
        self._last_write = now
        self.async_write_ha_state()


class PoolHeatPumpSensor(ThrottledSensorMixin, PoolHeatPumpEntity, SensorEntity):
    def __init__(self, coordinator: PoolHeatPumpCoordinator, spec: SensorDef) -> None:
        super().__init__(coordinator)
        self._spec = spec
        self._key = spec.key
        self._attr_translation_key = spec.translation_key
        self._attr_unique_id = f"{coordinator.unique_id}_{spec.key}"
        self._attr_suggested_object_id = suggested_object_id(spec.key)
        self._attr_device_class = spec.device_class
        self._attr_state_class = spec.state_class
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_entity_category = spec.entity_category
        self._attr_entity_registry_enabled_default = spec.enabled_default
        if spec.suggested_precision is not None:
            self._attr_suggested_display_precision = spec.suggested_precision

    @property
    def native_value(self) -> float | int | None:
        return self._spec.value(self.coordinator.state)


class EnergyTotalSensor(ThrottledSensorMixin, PoolHeatPumpEntity, RestoreSensor):
    _attr_translation_key = "energy_total"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: PoolHeatPumpCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}_energy_total"
        self._attr_suggested_object_id = suggested_object_id("energy_total")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last and last.native_value is not None:
            try:
                self.coordinator.energy.total_kwh = float(last.native_value)
            except (TypeError, ValueError):
                pass

    @property
    def native_value(self) -> float:
        return round(self.coordinator.energy.total_kwh, 4)


class CopDisplaySensor(ThrottledSensorMixin, PoolHeatPumpEntity, SensorEntity):
    _attr_translation_key = "cop_display"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: PoolHeatPumpCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}_cop_display"
        self._attr_suggested_object_id = suggested_object_id("cop")

    def _resolved(self) -> tuple[float | None, str | None]:
        return resolve_cop(self.coordinator.state, self.coordinator.cop_options)

    @property
    def available(self) -> bool:
        return super().available and self._resolved()[0] is not None

    @property
    def native_value(self) -> float | None:
        return self._resolved()[0]


class PanelClockSensor(ThrottledSensorMixin, PoolHeatPumpEntity, SensorEntity):
    _attr_translation_key = "panel_clock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: PoolHeatPumpCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}_panel_clock"
        self._attr_suggested_object_id = suggested_object_id("panel_clock")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.state.clock


class ProfileRegisterSensor(ThrottledSensorMixin, PoolHeatPumpEntity, SensorEntity):
    def __init__(
        self,
        coordinator: PoolHeatPumpCoordinator,
        key: str,
        spec: dict,
        ent: dict,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.unique_id}_{key}"
        self._attr_suggested_object_id = suggested_object_id(key)
        self._attr_device_class = _DEVICE_CLASS.get(str(ent.get("device_class") or ""))
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = _UNITS.get(str(spec.get("unit") or ""))
        if ent.get("category") == "diagnostic":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = bool(ent.get("enabled", False))
        self._attr_suggested_display_precision = 1 if spec.get("scale") == 0.1 else 0

    @property
    def native_value(self) -> float | int | None:
        return _state_value(self.coordinator.state, self._key)
