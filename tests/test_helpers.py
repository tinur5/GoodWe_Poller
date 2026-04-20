"""Tests for the low-level helper functions in coordinator.py."""

import struct
import pytest

# Stubs for HA modules are installed by conftest.py before this import.
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom_components.goodwe_modbus.coordinator import (
    _s16,
    _u32,
    _s32,
    _f32,
    _clamp,
)


# ── _s16 ──────────────────────────────────────────────────────────────────────

class TestS16:
    def test_zero(self):
        assert _s16(0) == 0

    def test_positive_below_threshold(self):
        assert _s16(0x7FFF) == 32767

    def test_max_unsigned(self):
        # 0xFFFF → −1
        assert _s16(0xFFFF) == -1

    def test_negative_one(self):
        assert _s16(0xFFFF) == -1

    def test_most_negative(self):
        # 0x8000 → −32768
        assert _s16(0x8000) == -32768

    def test_mid_negative(self):
        assert _s16(0xFFFE) == -2

    def test_small_positive(self):
        assert _s16(1) == 1

    def test_boundary_positive(self):
        # 0x7FFF is the largest positive s16 value
        assert _s16(0x7FFF) == 32767

    def test_boundary_negative(self):
        # 0x8000 is the smallest (most negative) s16 value
        assert _s16(0x8000) == -32768


# ── _u32 ──────────────────────────────────────────────────────────────────────

class TestU32:
    def test_zero(self):
        assert _u32(0, 0) == 0

    def test_lo_only(self):
        assert _u32(0, 42) == 42

    def test_hi_only(self):
        assert _u32(1, 0) == 0x10000

    def test_both(self):
        assert _u32(0x0001, 0x0002) == 0x00010002

    def test_max(self):
        assert _u32(0xFFFF, 0xFFFF) == 0xFFFFFFFF

    def test_known_value(self):
        # 10000 kWh × 10 = 100000 raw → u32(0x0001, 0x86A0)
        assert _u32(0x0001, 0x86A0) == 100000


# ── _s32 ──────────────────────────────────────────────────────────────────────

class TestS32:
    def test_zero(self):
        assert _s32(0, 0) == 0

    def test_positive(self):
        assert _s32(0, 1000) == 1000

    def test_negative_one(self):
        assert _s32(0xFFFF, 0xFFFF) == -1

    def test_most_negative(self):
        assert _s32(0x8000, 0x0000) == -2147483648

    def test_max_positive(self):
        assert _s32(0x7FFF, 0xFFFF) == 2147483647

    def test_typical_export_power(self):
        # Grid exporting 5000 W: s32 = 5000 = 0x00001388
        assert _s32(0x0000, 0x1388) == 5000

    def test_typical_import_power(self):
        # Grid importing 3000 W: s32 = -3000 = 0xFFFFF448
        assert _s32(0xFFFF, 0xF448) == -3000


# ── _f32 ──────────────────────────────────────────────────────────────────────

class TestF32:
    def _encode(self, value: float):
        """Return the (hi, lo) register pair for *value* as an IEEE 754 float32."""
        raw = struct.pack(">f", value)
        hi, lo = struct.unpack(">HH", raw)
        return hi, lo

    def test_zero(self):
        hi, lo = self._encode(0.0)
        assert _f32(hi, lo) == 0.0

    def test_positive_one(self):
        hi, lo = self._encode(1.0)
        assert _f32(hi, lo) == pytest.approx(1.0)

    def test_negative_one(self):
        hi, lo = self._encode(-1.0)
        assert _f32(hi, lo) == pytest.approx(-1.0)

    def test_typical_export_kwh(self):
        # A realistic export total: 1234.5 kWh
        hi, lo = self._encode(1234.5)
        assert _f32(hi, lo) == pytest.approx(1234.5, rel=1e-5)

    def test_large_value(self):
        hi, lo = self._encode(99999.9)
        assert _f32(hi, lo) == pytest.approx(99999.9, rel=1e-4)

    def test_small_fractional(self):
        hi, lo = self._encode(0.1)
        assert _f32(hi, lo) == pytest.approx(0.1, rel=1e-5)

    def test_round_trip_consistency(self):
        """_f32 must always decode what struct.pack('>f', …) encodes."""
        for v in (0.0, 1.0, -1.0, 500.25, 99000.0):
            hi, lo = self._encode(v)
            assert _f32(hi, lo) == pytest.approx(v, rel=1e-5)


# ── _clamp ────────────────────────────────────────────────────────────────────

class TestClamp:
    def test_within_range_positive(self):
        assert _clamp(100.0, 1000.0) == 100.0

    def test_within_range_negative(self):
        assert _clamp(-100.0, 1000.0) == -100.0

    def test_exactly_at_upper_bound(self):
        assert _clamp(1000.0, 1000.0) == 1000.0

    def test_exactly_at_lower_bound(self):
        assert _clamp(-1000.0, 1000.0) == -1000.0

    def test_exceeds_upper_bound(self):
        assert _clamp(1001.0, 1000.0) is None

    def test_exceeds_lower_bound(self):
        assert _clamp(-1001.0, 1000.0) is None

    def test_zero(self):
        assert _clamp(0.0, 1000.0) == 0.0

    def test_soc_valid(self):
        # SOC 0–100 %
        assert _clamp(75.0, 100.0) == 75.0

    def test_soc_overflow(self):
        # A corrupted register might give 65535 — should be clamped out
        assert _clamp(65535.0, 100.0) is None

    def test_temperature_valid(self):
        assert _clamp(45.0, 120.0) == 45.0

    def test_temperature_negative_valid(self):
        assert _clamp(-20.0, 120.0) == -20.0

    def test_temperature_overflow(self):
        assert _clamp(200.0, 120.0) is None
