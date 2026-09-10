from spo_pool_heat_pump.const import CONF_MANUAL_COP_FLOW, CONF_WATER_FLOW_M3H
from spo_pool_heat_pump.cop import coerce_cop_option, resolve_cop
from spo_pool_heat_pump.drivers.base import HeatPumpState
from spo_pool_heat_pump.parameters import catalog_payload, parameter_catalog
from spo_pool_heat_pump.profiles import load_profile, profile_registers, service_menu_params
import pytest


def test_bus_cop_zero_hides() -> None:
    state = HeatPumpState(available=True, power=True)
    state.extras["cop"] = 0
    assert resolve_cop(state, {}) == (None, None)


def test_bus_cop_nonzero() -> None:
    state = HeatPumpState(available=True, power=True)
    state.extras["cop"] = 4.2
    assert resolve_cop(state, {}) == (4.2, "controller")


def test_manual_flow_calculates() -> None:
    state = HeatPumpState(
        available=True,
        power=True,
        t_inlet=28.0,
        t_outlet=30.0,
        power_kw=1.163,
    )
    opts = {CONF_MANUAL_COP_FLOW: True, CONF_WATER_FLOW_M3H: 5.0}
    assert resolve_cop(state, opts) == (10.0, "calculated")


def test_manual_ignores_bus() -> None:
    state = HeatPumpState(
        available=True,
        power=True,
        t_inlet=28.0,
        t_outlet=30.0,
        power_kw=1.163,
    )
    state.extras["cop"] = 4.2
    opts = {CONF_MANUAL_COP_FLOW: True, CONF_WATER_FLOW_M3H: 5.0}
    assert resolve_cop(state, opts) == (10.0, "calculated")


def test_manual_zero_delta_hides() -> None:
    state = HeatPumpState(available=True, t_inlet=28.0, t_outlet=28.0, power_kw=1.5)
    opts = {CONF_MANUAL_COP_FLOW: True, CONF_WATER_FLOW_M3H: 5.0}
    assert resolve_cop(state, opts) == (None, None)


def test_manual_zero_power_hides() -> None:
    state = HeatPumpState(available=True, t_inlet=28.0, t_outlet=30.0, power_kw=0)
    opts = {CONF_MANUAL_COP_FLOW: True, CONF_WATER_FLOW_M3H: 5.0}
    assert resolve_cop(state, opts) == (None, None)


def test_manual_without_flow_hides_even_if_bus() -> None:
    state = HeatPumpState(available=True, t_inlet=28.0, t_outlet=30.0, power_kw=1.5)
    state.extras["cop"] = 4.2
    opts = {CONF_MANUAL_COP_FLOW: True, CONF_WATER_FLOW_M3H: 0}
    assert resolve_cop(state, opts) == (None, None)


def test_coerce_cop_option() -> None:
    assert coerce_cop_option(CONF_MANUAL_COP_FLOW, "true") is True
    assert coerce_cop_option(CONF_WATER_FLOW_M3H, "5") == 5.0
    assert coerce_cop_option(CONF_WATER_FLOW_M3H, 0) == 0.0
    with pytest.raises(ValueError):
        coerce_cop_option(CONF_WATER_FLOW_M3H, 70)
    with pytest.raises(KeyError):
        coerce_cop_option("setpoint", 28)


def test_catalog_injects_local_cop_rows() -> None:
    profile = load_profile("mida_cosma_pc1002")
    payload = catalog_payload(
        profile,
        HeatPumpState(),
        service_menu_writes=False,
        options={CONF_MANUAL_COP_FLOW: True, CONF_WATER_FLOW_M3H: 4.5},
    )
    by_key = {row["key"]: row for row in payload["parameters"]}
    assert by_key[CONF_MANUAL_COP_FLOW]["tier"] == "safe"
    assert by_key[CONF_MANUAL_COP_FLOW]["value"] is True
    assert by_key[CONF_WATER_FLOW_M3H]["unit"] == "m³/h"
    assert by_key[CONF_WATER_FLOW_M3H]["value"] == 4.5
    assert len(payload["parameters"]) == len(parameter_catalog(profile)) + 2
    assert len(parameter_catalog(profile)) == len(profile_registers(profile)) + len(service_menu_params(profile))
