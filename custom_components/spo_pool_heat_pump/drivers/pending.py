"""Optimistic writes: show the written value until the device echoes it.

Shared by the push (PC1002 broadcast) and poll (Fairland) drivers. A write is
marked pending with its decoded target. On every publish the overlay runs:

* device reports the target → confirmed, dropped;
* deadline passed without an echo → dropped and logged, the device value
  shows again so a rejected write never stays on screen;
* otherwise the decoded field is overridden with the target.

``HeatPumpState.pending`` lists the names still in flight so the UI can mark
them.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from ..profiles import decode_value, lookup_write_spec
from .base import HeatPumpState

_LOGGER = logging.getLogger(__name__)

# PC1002 via slave 2: the board polls slave 2 once per cycle (1.7 s), reads our
# page ~0.35 s after seeing the flag, and the change shows in the next 2001
# broadcast — a panel change reached the broadcast after a median 3.1 s and at
# most ~4.2 s in the recorded dumps. Leave headroom for a cycle stretched by
# retries. Poll drivers scale this with their poll interval (PendingWrites.ttl_s).
DEFAULT_TTL_S = 12.0

# Values that live only in a settings page (mode word 1012, timers, per-mode
# setpoints) are confirmed by the board *pushing* that page to the panels, which
# it does one full round after applying it: measured 8.4 s (quiet), 9.5 s and
# 10.1 s (mode) after the write on the live bus. 12 s leaves no margin there.
PAGE_TTL_S = 20.0

_CONTAINER_FIELDS = ("extras", "values", "raw", "outputs", "pending")


def same_value(a: Any, b: Any) -> bool:
    """Decoded-value equality with a tolerance for scaled numbers."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 0.05
    return a == b


@dataclass(slots=True)
class _Pending:
    value: Any  # decoded, as apply_map would produce it
    deadline: float
    ttl_s: float


class PendingWrites:
    def __init__(self, profile: dict[str, Any], ttl_s: float = DEFAULT_TTL_S) -> None:
        self._profile = profile
        self.ttl_s = float(ttl_s)
        self._items: dict[str, _Pending] = {}

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, name: str) -> bool:
        return name in self._items

    def mark(self, name: str, encoded: int, ttl_s: float | None = None) -> None:
        spec = lookup_write_spec(self._profile, name)
        decoded = decode_value(spec, encoded, self._profile.get("enums") or {})
        ttl = self.ttl_s if ttl_s is None else float(ttl_s)
        self._items[name] = _Pending(decoded, time.monotonic() + ttl, ttl)

    def discard(self, name: str) -> None:
        self._items.pop(name, None)

    def overlay(self, state: HeatPumpState) -> None:
        now = time.monotonic()
        for name, pend in list(self._items.items()):
            current = state.get(name)
            if same_value(current, pend.value):
                del self._items[name]
                continue
            if now >= pend.deadline:
                del self._items[name]
                _LOGGER.warning(
                    "write %s=%r not confirmed by the heat pump within %.0f s; showing device value %r",
                    name, pend.value, pend.ttl_s, current,
                )
                continue
            if name not in _CONTAINER_FIELDS and hasattr(state, name):
                setattr(state, name, pend.value)
            else:
                state.extras[name] = pend.value
        state.pending = sorted(self._items)
