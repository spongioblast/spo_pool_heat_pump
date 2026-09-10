"""When a coordinator push should force measurement sensors to write."""

from __future__ import annotations

from .const import SENSOR_PUBLISH_INTERVAL_S
from .drivers.base import HeatPumpState

DiscreteFingerprint = tuple[bool, bool, str, bool, tuple[str, ...], tuple[tuple[str, bool], ...]]


def discrete_fingerprint(state: HeatPumpState) -> DiscreteFingerprint:
    return (
        state.available,
        state.power,
        state.mode,
        state.silent,
        tuple(state.faults),
        tuple(sorted((name, bool(on)) for name, on in state.outputs.items())),
    )


def next_force_seq(
    prev: DiscreteFingerprint | None,
    state: HeatPumpState,
    force_seq: int,
) -> tuple[int, DiscreteFingerprint]:
    fp = discrete_fingerprint(state)
    if fp != prev:
        return force_seq + 1, fp
    return force_seq, fp


def should_publish_sensor(
    last_write: float | None,
    now: float,
    force_seq: int,
    seen_force_seq: int,
    interval: float = SENSOR_PUBLISH_INTERVAL_S,
) -> bool:
    if last_write is None:
        return True
    if force_seq > seen_force_seq:
        return True
    return now - last_write >= interval
