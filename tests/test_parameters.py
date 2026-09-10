import pytest

from spo_pool_heat_pump.drivers.base import HeatPumpState
from spo_pool_heat_pump.drivers.pc1002_bus import Pc1002BusDriver
from spo_pool_heat_pump.parameters import catalog_payload, parameter_catalog, service_menu_bounds
from spo_pool_heat_pump.profiles import load_profile, profile_registers, service_menu_params


def test_cosmo_catalog_is_193() -> None:
    profile = load_profile("mida_cosma_pc1002")
    rows = parameter_catalog(profile)
    assert len(rows) == len(profile_registers(profile)) + len(service_menu_params(profile))
    assert len(rows) == 193
    assert {row["tier"] for row in rows} == {"safe", "service_menu", "readonly"}
    assert sum(1 for row in rows if row["tier"] == "service_menu") == 105
    assert sum(1 for row in rows if row["tier"] == "readonly" and row["key"] in service_menu_params(profile)) == 37
    assert any(row["key"] == "power" and row["tier"] == "safe" for row in rows)
    assert any(row["key"] == "h06_min_freq_heat" and row["group"] == "H" and row["group_label"] == "System (H)" for row in rows)


def test_catalog_values_from_state() -> None:
    profile = load_profile("mida_cosma_pc1002")
    state = HeatPumpState(available=True, power=True, mode="heat", setpoint=28.0)
    state.extras["h08_max_freq_heat"] = 80
    payload = catalog_payload(profile, state, service_menu_writes=False)
    by_key = {row["key"]: row for row in payload["parameters"]}
    assert payload["service_menu_writes"] is False
    assert payload["verification"] == "verified"
    assert by_key["power"]["value"] is True
    assert by_key["setpoint"]["value"] == 28.0
    assert by_key["h08_max_freq_heat"]["value"] == 80
    assert "Control" in payload["groups"]
    assert "H" in payload["groups"]


def test_readonly_register_cannot_be_written() -> None:
    profile = load_profile("mida_cosma_pc1002")
    driver = Pc1002BusDriver(profile, lambda _f: None)
    with pytest.raises(KeyError):
        driver.encoded_write("t_inlet", 22)
    with pytest.raises(KeyError):
        driver.encoded_write("clock", "16:21:00")
    driver.service_menu_writes = True
    with pytest.raises(KeyError):
        driver.encoded_write("h02_mode_type_or_restrictor", 1)
    addr, encoded = driver.encoded_write("setpoint", 29)
    assert addr == 1013
    assert encoded == 290


def test_catalog_rounds_scale_and_labels() -> None:
    profile = load_profile("mida_cosma_pc1002")
    state = HeatPumpState(available=True, t_inlet=20.700000000000003)
    payload = catalog_payload(profile, state, service_menu_writes=False)
    by_key = {row["key"]: row for row in payload["parameters"]}
    assert by_key["t_inlet"]["value"] == 20.7
    assert by_key["h06_min_freq_heat"]["label"] == "Min freq heat"
    assert by_key["power"]["options"] is None


def test_service_menu_bounds_moved() -> None:
    lo, hi, step = service_menu_bounds({"min": 0, "max": 120, "unit": "Hz"})
    assert (lo, hi, step) == (0, 120, 1)
    lo, hi, step = service_menu_bounds({"unit": "°C", "scale": 0.1})
    assert (lo, hi, step) == (-30, 80, 0.1)
