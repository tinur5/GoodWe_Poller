"""
filter.py – Signal filters to suppress spikes and invalid readings.

Three filter strategies are provided:

1. SpikeFilter    – sliding-window median + max-delta guard
2. DeadbandFilter – clamp small values to zero (e.g. grid power at standby)
3. MonotonicGuard – reject energy-counter decreases (rollback / glitch)
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


class SpikeFilter:
    """
    Reject a new sample if it deviates from the recent median by more than
    ``max_delta``.  If rejected, the previous accepted value is returned instead.

    Parameters
    ----------
    window      : number of recent accepted samples kept for median calculation
    max_delta   : maximum allowed absolute change from the running median
    name        : label used in log messages
    """

    def __init__(self, window: int = 5, max_delta: float = 5_000,
                 name: str = "") -> None:
        self._window = window
        self._max_delta = max_delta
        self._name = name
        self._history: deque[float] = deque(maxlen=window)
        self._last: Optional[float] = None

    def update(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return self._last

        if self._history:
            sorted_h = sorted(self._history)
            median = sorted_h[len(sorted_h) // 2]
            if abs(value - median) > self._max_delta:
                logger.warning(
                    "[SpikeFilter:%s] spike %.1f → median %.1f (Δ=%.1f > %.1f) – keeping %.1f",
                    self._name, value, median,
                    abs(value - median), self._max_delta,
                    self._last if self._last is not None else median,
                )
                return self._last if self._last is not None else median

        self._history.append(value)
        self._last = value
        return value


class DeadbandFilter:
    """
    Clamp values whose absolute magnitude is below ``threshold`` to zero.
    Useful for grid power to avoid jitter around zero.

    Parameters
    ----------
    threshold : values with |x| < threshold are mapped to 0
    """

    def __init__(self, threshold: float = 30.0, name: str = "") -> None:
        self._threshold = threshold
        self._name = name

    def update(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if abs(value) < self._threshold:
            return 0.0
        return value


class MonotonicGuard:
    """
    Reject energy-counter readings that decrease compared to the last accepted
    value (can happen due to register glitches or inverter reboots).

    A decrease larger than ``rollover_threshold`` is treated as a rollover and
    the new value is accepted.

    Parameters
    ----------
    rollover_threshold : absolute drop that is accepted as a true counter rollover
    name               : label used in log messages
    """

    def __init__(self, rollover_threshold: float = 0.0, name: str = "") -> None:
        self._rollover_threshold = rollover_threshold
        self._name = name
        self._last: Optional[float] = None

    def update(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return self._last

        if self._last is not None and value < self._last:
            drop = self._last - value
            if self._rollover_threshold > 0 and drop >= self._rollover_threshold:
                logger.info(
                    "[MonotonicGuard:%s] rollover detected: %.1f → %.1f (drop=%.1f)",
                    self._name, self._last, value, drop,
                )
            else:
                logger.warning(
                    "[MonotonicGuard:%s] decrease %.1f → %.1f rejected",
                    self._name, self._last, value,
                )
                return self._last

        self._last = value
        return value


# ── Pre-built filter sets used by the combiner ────────────────────────────────

def build_filters() -> dict:
    """
    Return a dict of ready-to-use filter instances for all main channels.
    Keys match the decoded dict keys produced by decoder.decode().
    """
    return {
        # Power channels – spike + deadband
        "pv_power_w":       SpikeFilter(window=5, max_delta=8_000, name="pv_power"),
        "battery_power_w":  SpikeFilter(window=5, max_delta=6_000, name="battery_power"),
        "grid_power_w":     SpikeFilter(window=5, max_delta=8_000, name="grid_power"),
        "load_power_w":     SpikeFilter(window=5, max_delta=8_000, name="load_power"),
        # Grid deadband (applied after spike filter)
        "_grid_deadband":   DeadbandFilter(threshold=30.0, name="grid_power"),
        # Energy counters – monotonic
        "pv_energy_total_kwh":   MonotonicGuard(name="pv_total"),
        "grid_export_total_kwh": MonotonicGuard(name="grid_export"),
        "grid_import_total_kwh": MonotonicGuard(name="grid_import"),
    }
