"""Trapezoid integration of 2055 kW into a monotonic kWh total."""

from __future__ import annotations


class EnergyIntegrator:
    def __init__(self, initial: float = 0.0) -> None:
        self.total_kwh = float(initial)
        self._last_kw: float | None = None
        self._last_ts: float | None = None

    def update(self, kw: float | None, now: float) -> float:
        if kw is None:
            return self.total_kwh
        if self._last_kw is not None and self._last_ts is not None and now > self._last_ts:
            hours = (now - self._last_ts) / 3600.0
            # Skip gaps of 1h+ (stale / HA restart) so one missed sample
            # cannot add a huge trapezoid to the lifetime kWh.
            if 0 < hours < 1:
                self.total_kwh += (self._last_kw + kw) / 2.0 * hours
        self._last_kw = kw
        self._last_ts = now
        return self.total_kwh
