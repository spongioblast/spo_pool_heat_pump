from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spo_pool_heat_pump.drivers.decode import apply_map
from spo_pool_heat_pump.modbus_rtu import encode_fc16, parse_frame
from spo_pool_heat_pump.profiles import encode_value, load_profile, service_menu_params

from tools.simulator.physics import tick
from tools.simulator.state import SimUnit
from tools.simulator.wire import apply_write, encode_broadcast_words, encode_maps, settings_page


def test_roundtrip_broadcast_matches_apply_map() -> None:
    profile = load_profile("mida_cosma_pc1002")
    unit = SimUnit.seed(profile)
    unit.power = True
    unit.mode = "heat"
    unit.setpoint = 28.0
    unit.t_inlet = 22.4
    unit.t_outlet = 24.9
    unit.t_ambient = 18.0
    unit.comp_hz = 40
    unit.fan_rpm = 720
    unit.power_kw = 1.6
    unit.energy_24h_kwh = 3.2
    unit.silent = False
    unit.outputs["compressor"] = True
    unit.outputs["water_pump"] = True
    regs, _, settings = encode_maps(unit)
    words = encode_broadcast_words(unit)
    assert len(words) == 90
    state = apply_map(profile, regs, settings=settings)
    assert state.power is True
    assert state.mode == "heat"
    assert state.setpoint == 28.0
    assert abs((state.t_inlet or 0) - 22.4) < 1e-9
    assert abs((state.t_outlet or 0) - 24.9) < 1e-9
    assert state.t_ambient == 18.0
    assert state.comp_hz == 40
    assert state.fan_rpm == 720
    assert state.power_kw == 1.6
    assert state.outputs["compressor"] is True
    assert state.serial == "SIMCOSMA"


def test_fc16_setpoint_write_in_next_broadcast() -> None:
    profile = load_profile("mida_cosma_pc1002")
    unit = SimUnit.seed(profile)
    apply_write(unit, 1013, [encode_value(profile["registers"]["setpoint"], 31.0, profile["enums"])])
    regs, _, settings = encode_maps(unit)
    state = apply_map(profile, regs, settings=settings)
    assert state.setpoint == 31.0
    frame = encode_fc16(99, 1013, [310])
    parsed = parse_frame(frame)
    assert parsed is not None
    assert parsed.start == 1013


def test_service_menu_page_returns_seeded_defaults() -> None:
    profile = load_profile("mida_cosma_pc1002")
    unit = SimUnit.seed(profile)
    page = settings_page(unit, 1001, 90)
    spec = service_menu_params(profile)["h06_min_freq_heat"]
    offset = int(spec["reg"]) - 1001
    assert page[offset] == spec["default"]
    spec8 = service_menu_params(profile)["h08_max_freq_heat"]
    assert page[int(spec8["reg"]) - 1001] == spec8["default"]


def test_e03_surfaces_as_fault_code() -> None:
    profile = load_profile("mida_cosma_pc1002")
    unit = SimUnit.seed(profile)
    unit.inject_fault("E03")
    regs, _, settings = encode_maps(unit)
    state = apply_map(profile, regs, settings=settings)
    assert state.fault_code == "E03"
    assert state.fault_text and "Flow switch" in state.fault_text
    assert regs[2074] & (1 << 9)


def test_e03_stops_pump_and_compressor() -> None:
    profile = load_profile("mida_cosma_pc1002")
    unit = SimUnit.seed(profile)
    unit.power = True
    unit.mode = "heat"
    unit.setpoint = 28.0
    unit.t_inlet = 16.0
    unit.inject_fault("E03")
    for _ in range(20):
        tick(unit, 1.0, profile)
    assert unit.comp_hz == 0
    assert unit.outputs["water_pump"] is False
    assert unit.outputs["compressor"] is False
    inlet_faulted = unit.t_inlet
    unit.clear_faults()
    for _ in range(20):
        tick(unit, 2.0, profile)
    assert unit.comp_hz > 10
    assert unit.outputs["water_pump"] is True
    assert unit.t_inlet > inlet_faulted


def test_physics_ramps_toward_setpoint() -> None:
    profile = load_profile("mida_cosma_pc1002")
    unit = SimUnit.seed(profile)
    unit.power = True
    unit.mode = "heat"
    unit.setpoint = 28.0
    unit.t_inlet = 16.0
    for _ in range(20):
        tick(unit, 2.0, profile)
    assert unit.comp_hz > 10
    assert unit.t_outlet > unit.t_inlet
    assert unit.outputs["water_pump"] is True
