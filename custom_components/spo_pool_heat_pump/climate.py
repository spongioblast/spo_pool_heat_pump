"""Climate entity — inlet is current_temperature; OEM auto is HEAT_COOL."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PRESET_SILENT
from .cop import resolve_cop
from .coordinator import PoolHeatPumpConfigEntry, PoolHeatPumpCoordinator
from .entity import PoolHeatPumpEntity, suggested_object_id
from .profiles import profile_registers

PARALLEL_UPDATES = 0

HA_MODE = {"heat": HVACMode.HEAT, "cool": HVACMode.COOL, "auto": HVACMode.HEAT_COOL}
OEM_MODE = {HVACMode.HEAT: "heat", HVACMode.COOL: "cool", HVACMode.HEAT_COOL: "auto"}


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolHeatPumpConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([PoolHeatPumpClimate(entry.runtime_data)])


class PoolHeatPumpClimate(PoolHeatPumpEntity, ClimateEntity):
    _attr_name = None
    _attr_translation_key = "climate"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_precision = 0.1
    _attr_min_temp = 8
    _attr_max_temp = 40

    def __init__(self, coordinator: PoolHeatPumpCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}_climate"
        self._attr_suggested_object_id = suggested_object_id()
        if coordinator.profile["driver"]["type"] == "listen_only":
            self._attr_hvac_modes = [HVACMode.OFF]
            self._attr_supported_features = ClimateEntityFeature(0)
            return
        oem_modes = coordinator.profile.get("modes") or ["heat"]
        modes = [HVACMode.OFF, HVACMode.HEAT]
        if "auto" in oem_modes:
            modes.append(HVACMode.HEAT_COOL)
        if "cool" in oem_modes:
            modes.append(HVACMode.COOL)
        self._attr_hvac_modes = modes
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if "silent" in profile_registers(coordinator.profile):
            features |= ClimateEntityFeature.PRESET_MODE
            self._attr_preset_modes = [PRESET_SILENT, "none"]
        self._attr_supported_features = features

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.state.t_inlet

    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.state.setpoint

    @property
    def min_temp(self) -> float:
        return self._setpoint_bounds()[0]

    @property
    def max_temp(self) -> float:
        return self._setpoint_bounds()[1]

    def _setpoint_bounds(self) -> tuple[float, float]:
        extras = self.coordinator.state.extras
        mode = self.coordinator.state.mode
        if mode == "cool":
            lo, hi = extras.get("r08_min_cool_setpoint"), extras.get("r09_max_cool_setpoint")
        elif mode == "heat":
            lo, hi = extras.get("r10_min_heat_setpoint"), extras.get("r11_max_heat_setpoint")
        else:
            lows = [extras.get("r08_min_cool_setpoint"), extras.get("r10_min_heat_setpoint")]
            highs = [extras.get("r09_max_cool_setpoint"), extras.get("r11_max_heat_setpoint")]
            present_lo = [float(x) for x in lows if x is not None]
            present_hi = [float(x) for x in highs if x is not None]
            lo = min(present_lo) if present_lo else None
            hi = max(present_hi) if present_hi else None
        return float(lo) if lo is not None else 8.0, float(hi) if hi is not None else 40.0

    @property
    def hvac_mode(self) -> HVACMode:
        state = self.coordinator.state
        if not state.power:
            mode = HVACMode.OFF
        else:
            mode = HA_MODE.get(state.mode, HVACMode.HEAT)
        if mode not in self.hvac_modes:
            return HVACMode.HEAT if HVACMode.HEAT in self.hvac_modes else self.hvac_modes[0]
        return mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.state
        attrs: dict[str, Any] = {"activity": state.card_status()}
        if self.coordinator.profile["driver"]["type"] == "listen_only" or state.values.get("dump_only"):
            attrs["dump_only"] = True
        if state.fault_code:
            attrs["fault"] = state.fault_code
        if state.fault_text:
            attrs["fault_text"] = state.fault_text
        cop, source = resolve_cop(state, self.coordinator.cop_options)
        if cop is not None and source:
            attrs["cop"] = round(float(cop), 2)
            attrs["cop_source"] = source
        return attrs

    @property
    def hvac_action(self) -> HVACAction:
        state = self.coordinator.state
        if not state.power:
            return HVACAction.OFF
        if state.compressor_on and state.mode == "cool":
            return HVACAction.COOLING
        if state.compressor_on and state.mode == "heat":
            return HVACAction.HEATING
        if state.compressor_on and state.mode == "auto":
            return HVACAction.HEATING if state.auto_is_heating() else HVACAction.COOLING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        if PRESET_SILENT not in (self.preset_modes or []):
            return None
        return PRESET_SILENT if self.coordinator.state.silent else "none"

    def _reject_dump_only(self) -> None:
        if self.coordinator.profile["driver"]["type"] == "listen_only":
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="dump_only_no_writes")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        self._reject_dump_only()
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self.coordinator.driver.set_setpoint(float(temp))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._reject_dump_only()
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.driver.set_power(False)
            return
        await self.coordinator.driver.set_power(True)
        oem = OEM_MODE.get(hvac_mode)
        if oem:
            await self.coordinator.driver.set_mode(oem)

    async def async_turn_on(self) -> None:
        self._reject_dump_only()
        await self.coordinator.driver.set_power(True)

    async def async_turn_off(self) -> None:
        self._reject_dump_only()
        await self.coordinator.driver.set_power(False)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._reject_dump_only()
        await self.coordinator.driver.set_silent(preset_mode == PRESET_SILENT)
