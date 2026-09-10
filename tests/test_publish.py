from spo_pool_heat_pump.const import SENSOR_PUBLISH_INTERVAL_S
from spo_pool_heat_pump.drivers.base import HeatPumpState
from spo_pool_heat_pump.publish import discrete_fingerprint, next_force_seq, should_publish_sensor


def test_should_publish_first_update() -> None:
    assert should_publish_sensor(None, 0.0, 1, 0) is True


def test_should_publish_skips_within_interval() -> None:
    assert should_publish_sensor(10.0, 20.0, 1, 1) is False
    assert should_publish_sensor(10.0, 10.0 + SENSOR_PUBLISH_INTERVAL_S - 0.01, 1, 1) is False


def test_should_publish_after_interval() -> None:
    assert should_publish_sensor(10.0, 10.0 + SENSOR_PUBLISH_INTERVAL_S, 1, 1) is True


def test_should_publish_on_force_seq_bump() -> None:
    assert should_publish_sensor(10.0, 11.0, 3, 1) is True


def test_force_seq_ignores_temperature() -> None:
    running = HeatPumpState(available=True, power=True, mode="heat", t_inlet=25.0, outputs={"compressor": True})
    seq, fp = next_force_seq(None, running, 0)
    assert seq == 1
    warmer = HeatPumpState(available=True, power=True, mode="heat", t_inlet=26.4, outputs={"compressor": True})
    seq2, fp2 = next_force_seq(fp, warmer, seq)
    assert seq2 == 1
    assert fp2 == fp


def test_force_seq_bumps_on_silent() -> None:
    loud = HeatPumpState(available=True, power=True, mode="heat", silent=False)
    seq, fp = next_force_seq(None, loud, 0)
    quiet = HeatPumpState(available=True, power=True, mode="heat", silent=True)
    seq2, _ = next_force_seq(fp, quiet, seq)
    assert seq2 == seq + 1


def test_force_seq_bumps_on_power_and_outputs() -> None:
    on = HeatPumpState(available=True, power=True, mode="heat", outputs={"compressor": True, "water_pump": True})
    seq, fp = next_force_seq(None, on, 0)
    off = HeatPumpState(available=True, power=False, mode="heat")
    seq2, _ = next_force_seq(fp, off, seq)
    assert seq2 == seq + 1


def test_discrete_fingerprint_stable_for_same_outputs() -> None:
    a = HeatPumpState(available=True, power=True, mode="heat", faults=["E03"], outputs={"b": True, "a": False})
    b = HeatPumpState(available=True, power=True, mode="heat", faults=["E03"], outputs={"a": False, "b": True})
    assert discrete_fingerprint(a) == discrete_fingerprint(b)
