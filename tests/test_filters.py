"""Tests for the spike / daily-energy / monotonic filters in coordinator.py."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

# HA stubs installed by conftest.py
from custom_components.goodwe_modbus.coordinator import (
    _SpikeFilter,
    _DailyEnergyFilter,
    _MonotonicGuard,
)


# ── _SpikeFilter ──────────────────────────────────────────────────────────────

class TestSpikeFilter:
    def _filter(self, window=5, max_delta=10_000):
        return _SpikeFilter(window=window, max_delta=max_delta)

    def test_first_value_accepted(self):
        sf = self._filter()
        assert sf(100.0) == 100.0

    def test_none_returns_last(self):
        sf = self._filter()
        sf(100.0)
        assert sf(None) == 100.0

    def test_none_before_any_value_returns_none(self):
        sf = self._filter()
        assert sf(None) is None

    def test_normal_sequence_passes_through(self):
        sf = self._filter(max_delta=10_000)
        values = [1000.0, 1010.0, 990.0, 1005.0, 995.0]
        results = [sf(v) for v in values]
        assert results == values

    def test_spike_rejected_returns_last_accepted(self):
        sf = self._filter(max_delta=10_000)
        # Fill history with stable values around 1000 W
        for v in [1000.0, 1000.0, 1000.0, 1000.0, 1000.0]:
            sf(v)
        # Spike of +15000 W — well above max_delta from the median (1000)
        result = sf(16000.0)
        assert result == 1000.0

    def test_spike_below_max_delta_accepted(self):
        sf = self._filter(max_delta=10_000)
        for v in [1000.0, 1000.0, 1000.0]:
            sf(v)
        # Jump of 5000 W is within max_delta → accepted
        result = sf(6000.0)
        assert result == 6000.0

    def test_exactly_at_max_delta_rejected(self):
        """A jump *equal to* max_delta must be rejected (>= condition)."""
        sf = self._filter(max_delta=10_000)
        for v in [0.0, 0.0, 0.0, 0.0, 0.0]:
            sf(v)
        # Exactly 10000 from median 0 — should be rejected
        assert sf(10_000.0) == 0.0

    def test_negative_spike_rejected(self):
        sf = self._filter(max_delta=10_000)
        for v in [1000.0, 1000.0, 1000.0, 1000.0, 1000.0]:
            sf(v)
        # Large negative spike
        result = sf(-15000.0)
        assert result == 1000.0

    def test_window_limits_history(self):
        sf = self._filter(window=3, max_delta=10_000)
        # Feed 5 values into a window-3 filter — only the last 3 matter
        for v in [5000.0, 5000.0, 5000.0, 100.0, 100.0]:
            sf(v)
        # History is now [5000, 100, 100] → median = 100; a jump of 5000+ is rejected
        result = sf(11_000.0)
        assert result == 100.0

    def test_resumption_after_spike(self):
        """After a suppressed spike the filter resumes accepting normal values."""
        sf = self._filter(max_delta=10_000)
        for v in [1000.0] * 5:
            sf(v)
        sf(20_000.0)  # suppressed
        assert sf(1000.0) == 1000.0


# ── _DailyEnergyFilter ────────────────────────────────────────────────────────

class TestDailyEnergyFilter:
    def _filter(self, window=5, max_up_delta=10.0):
        return _DailyEnergyFilter(window=window, max_up_delta=max_up_delta)

    def test_first_value_accepted(self):
        f = self._filter()
        assert f(5.0) == 5.0

    def test_none_returns_last(self):
        f = self._filter()
        f(5.0)
        assert f(None) == 5.0

    def test_none_before_any_value_returns_none(self):
        f = self._filter()
        assert f(None) is None

    def test_normal_increasing_sequence(self):
        f = self._filter(max_up_delta=10.0)
        values = [0.0, 1.0, 2.0, 3.0, 4.0]
        results = [f(v) for v in values]
        assert results == values

    def test_upward_spike_rejected(self):
        f = self._filter(max_up_delta=3.0)
        for v in [10.0, 10.5, 11.0, 11.5, 12.0]:
            f(v)
        # Median ≈ 11.0; spike to 30.0 is > median + 3.0 → rejected
        result = f(30.0)
        assert result == 12.0

    def test_small_upward_step_accepted(self):
        f = self._filter(max_up_delta=3.0)
        for v in [10.0, 10.0, 10.0]:
            f(v)
        # Step of 2.9 kWh is within max_up_delta → accepted
        result = f(12.9)
        assert result == 12.9

    def test_midnight_reset_clears_history(self):
        """A significant drop (midnight reset) should clear history and be accepted."""
        f = self._filter(max_up_delta=3.0)
        # End of day
        for v in [95.0, 96.0, 97.0, 98.0, 99.0]:
            f(v)
        # Midnight reset — counter drops to near-zero
        result = f(0.1)
        assert result == pytest.approx(0.1)

    def test_value_after_midnight_reset_accepted(self):
        """After a midnight reset the filter should track new-day values normally."""
        f = self._filter(max_up_delta=3.0)
        for v in [95.0, 96.0, 97.0, 98.0, 99.0]:
            f(v)
        f(0.1)  # midnight reset
        # Next reading shortly after midnight
        result = f(0.5)
        assert result == pytest.approx(0.5)

    def test_downward_step_smaller_than_max_up_delta_is_accepted(self):
        """Small decreases (within max_up_delta) should pass through (only upward spikes filtered)."""
        f = self._filter(max_up_delta=3.0)
        for v in [10.0, 10.0, 10.0]:
            f(v)
        # Tiny decrease — not a spike, not a midnight reset; accepted
        result = f(9.5)
        assert result == pytest.approx(9.5)


# ── _MonotonicGuard ───────────────────────────────────────────────────────────

class TestMonotonicGuard:
    def test_first_value_accepted(self):
        g = _MonotonicGuard()
        assert g(100.0) == 100.0

    def test_none_returns_last(self):
        g = _MonotonicGuard()
        g(100.0)
        assert g(None) == 100.0

    def test_none_before_any_value_returns_none(self):
        g = _MonotonicGuard()
        assert g(None) is None

    def test_increasing_sequence_passes_through(self):
        g = _MonotonicGuard()
        values = [100.0, 100.5, 101.0, 102.0, 150.0]
        results = [g(v) for v in values]
        assert results == values

    def test_decrease_blocked(self):
        g = _MonotonicGuard()
        g(100.0)
        result = g(99.9)
        assert result == 100.0

    def test_same_value_accepted(self):
        g = _MonotonicGuard()
        g(100.0)
        assert g(100.0) == 100.0

    def test_large_decrease_blocked(self):
        g = _MonotonicGuard()
        g(5000.0)
        assert g(1.0) == 5000.0

    def test_last_held_across_multiple_nones(self):
        g = _MonotonicGuard()
        g(50.0)
        assert g(None) == 50.0
        assert g(None) == 50.0
        assert g(None) == 50.0

    def test_increases_after_hold(self):
        g = _MonotonicGuard()
        g(100.0)
        g(99.0)   # blocked
        assert g(101.0) == 101.0
