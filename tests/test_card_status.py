from spo_pool_heat_pump.drivers.base import HeatPumpState


def _state(**kw) -> HeatPumpState:
    base = dict(available=True, power=True, mode="heat", outputs={"water_pump": True, "compressor": False})
    base.update(kw)
    return HeatPumpState(**base)


def test_pump_only_below_setpoint_is_warming_up() -> None:
    assert _state(t_inlet=24.0, setpoint=28.0).card_status() == "Warming up"


def test_pump_only_at_setpoint_is_idle() -> None:
    assert _state(t_inlet=28.0, setpoint=28.0).card_status() == "Idle"
    assert _state(t_inlet=29.5, setpoint=28.0).card_status() == "Idle"


def test_pump_only_unknown_temps_keeps_prerun_label() -> None:
    assert _state(t_inlet=None, setpoint=28.0).card_status() == "Warming up"
    assert _state(t_inlet=24.0, setpoint=None).card_status() == "Warming up"


def test_cool_prerun_is_starting_and_idle_when_cold_enough() -> None:
    assert _state(mode="cool", t_inlet=30.0, setpoint=26.0).card_status() == "Starting"
    assert _state(mode="cool", t_inlet=25.0, setpoint=26.0).card_status() == "Idle"
    assert _state(mode="cool", t_inlet=None, setpoint=26.0).card_status() == "Starting"


def test_auto_prerun_follows_direction() -> None:
    assert _state(mode="auto", t_inlet=24.0, setpoint=28.0).card_status() == "Warming up"
    assert _state(mode="auto", t_inlet=30.0, setpoint=28.0).card_status() == "Starting"
    assert _state(mode="auto", t_inlet=28.1, setpoint=28.0).card_status() == "Idle"


def test_auto_running_direction_from_delta_t() -> None:
    running = {"water_pump": True, "compressor": True}
    # Overshoot: inlet already above target but water still being heated.
    s = _state(mode="auto", t_inlet=28.6, t_outlet=30.1, setpoint=28.0, outputs=running)
    assert s.card_status() == "Heating"
    s = _state(mode="auto", t_inlet=27.5, t_outlet=25.9, setpoint=28.0, outputs=running)
    assert s.card_status() == "Cooling"
    # No usable ΔT yet: fall back to the setpoint side.
    s = _state(mode="auto", t_inlet=28.6, t_outlet=28.6, setpoint=28.0, outputs=running)
    assert s.card_status() == "Cooling"
    s = _state(mode="auto", t_inlet=24.0, t_outlet=None, setpoint=28.0, outputs=running)
    assert s.card_status() == "Heating"


def test_cool_mode_running_is_cooling_even_above_target() -> None:
    s = _state(mode="cool", t_inlet=27.0, t_outlet=25.5, setpoint=28.0, outputs={"water_pump": True, "compressor": True})
    assert s.card_status() == "Cooling"


def test_compressor_running_still_heating() -> None:
    s = _state(t_inlet=28.5, setpoint=28.0, outputs={"water_pump": True, "compressor": True})
    assert s.card_status() == "Heating"


def test_pump_off_is_idle() -> None:
    assert _state(t_inlet=24.0, setpoint=28.0, outputs={}).card_status() == "Idle"
