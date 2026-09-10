"""Drivers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import HeatPumpDriver, HeatPumpState
from .listen_only import DumpOnlyWriteError, ListenOnlyDriver
from .pc1002_bus import Pc1002BusDriver
from .poll_master import PollMasterDriver

__all__ = [
    "DumpOnlyWriteError",
    "HeatPumpDriver",
    "HeatPumpState",
    "ListenOnlyDriver",
    "Pc1002BusDriver",
    "PollMasterDriver",
    "build_driver",
]


def build_driver(
    profile: dict[str, Any],
    send: Callable,
    write_path: str,
    on_state: Callable[[HeatPumpState], None] | None = None,
) -> HeatPumpDriver:
    kind = profile["driver"]["type"]
    if kind == "poll_master":
        return PollMasterDriver(profile, send, on_state)
    if kind == "listen_only":
        return ListenOnlyDriver(profile, send, on_state)
    return Pc1002BusDriver(profile, send, write_path, on_state)
