"""
Tests for _read_inverter in coordinator.py.

pymodbus is mocked so no real hardware is required.  The tests validate the
register decoding and sanity-clamping logic that lives inside _read_inverter.
"""

import struct
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

# HA stubs installed by conftest.py


def _make_registers(size: int, values: dict[int, int] | None = None) -> list[int]:
    """Return a zero-filled register list of *size* with *values* applied."""
    regs = [0] * size
    if values:
        for idx, val in values.items():
            regs[idx] = val
    return regs


def _f32_regs(value: float):
    """Encode *value* as two big-endian 16-bit registers (IEEE 754 float32)."""
    raw = struct.pack(">f", value)
    hi, lo = struct.unpack(">HH", raw)
    return hi, lo


def _u16_s16(value: int) -> int:
    """Return the unsigned 16-bit representation of a signed 16-bit *value*."""
    return value & 0xFFFF


# ---------------------------------------------------------------------------
# Helpers to build mock pymodbus clients
# ---------------------------------------------------------------------------

def _make_mock_client(a_regs, b_regs=None, c_regs=None, *,
                      connect_ok=True, a_error=False, b_error=False, c_error=False):
    """Return a mock ModbusTcpClient that serves the provided register lists."""

    def _make_response(regs, error: bool):
        rr = MagicMock()
        rr.isError.return_value = error
        rr.registers = regs if not error else []
        return rr

    client = MagicMock()
    client.connect.return_value = connect_ok

    results = []
    # Order: block A, then B, then C
    results.append(_make_response(a_regs, a_error))
    results.append(_make_response(b_regs if b_regs is not None else [], b_error or b_regs is None))
    results.append(_make_response(c_regs if c_regs is not None else [], c_error or c_regs is None))

    client.read_holding_registers.side_effect = results
    return client


# ---------------------------------------------------------------------------
# Import the function under test
# ---------------------------------------------------------------------------

from custom_components.goodwe_modbus.coordinator import _read_inverter


# ── Connection failures ────────────────────────────────────────────────────────

class TestReadInverterConnection:
    def test_cannot_connect_returns_none(self):
        mock_client = _make_mock_client(
            _make_registers(125), connect_ok=False
        )
        with patch("custom_components.goodwe_modbus.coordinator.ModbusTcpClient",
                   return_value=mock_client, create=True):
            with patch.dict("sys.modules", {
                "pymodbus": MagicMock(),
                "pymodbus.client": MagicMock(ModbusTcpClient=MagicMock(return_value=mock_client)),
                "pymodbus.exceptions": MagicMock(ModbusException=Exception),
            }):
                result = _read_inverter("192.168.1.1", 502, 247)
        assert result is None

    def test_block_a_error_returns_none(self):
        mock_client = _make_mock_client(
            _make_registers(125), a_error=True
        )
        with patch.dict("sys.modules", {
            "pymodbus": MagicMock(),
            "pymodbus.client": MagicMock(ModbusTcpClient=MagicMock(return_value=mock_client)),
            "pymodbus.exceptions": MagicMock(ModbusException=Exception),
        }):
            result = _read_inverter("192.168.1.1", 502, 247)
        assert result is None


# ── PV decoding ───────────────────────────────────────────────────────────────

class TestReadInverterPV:
    """Tests for PV power, voltage, current decoding."""

    def _run(self, a_regs, b_regs=None, c_regs=None):
        """Run _read_inverter with the given register arrays."""
        c_regs = c_regs or _make_registers(8)
        mock_client = _make_mock_client(a_regs, b_regs, c_regs)
        with patch.dict("sys.modules", {
            "pymodbus": MagicMock(),
            "pymodbus.client": MagicMock(ModbusTcpClient=MagicMock(return_value=mock_client)),
            "pymodbus.exceptions": MagicMock(ModbusException=Exception),
        }):
            return _read_inverter("192.168.1.1", 502, 247)

    def test_pv1_power_zero(self):
        a = _make_registers(125)
        result = self._run(a)
        assert result["pv1_power_w"] == 0.0

    def test_pv1_power_typical(self):
        # PV1: 3000 W → u32 hi=0, lo=3000 at offsets 5,6
        a = _make_registers(125, {5: 0, 6: 3000})
        result = self._run(a)
        assert result["pv1_power_w"] == 3000.0

    def test_pv2_power_typical(self):
        # PV2: 2500 W at offsets 9, 10
        a = _make_registers(125, {9: 0, 10: 2500})
        result = self._run(a)
        assert result["pv2_power_w"] == 2500.0

    def test_pv3_power_typical(self):
        a = _make_registers(125, {13: 0, 14: 1500})
        result = self._run(a)
        assert result["pv3_power_w"] == 1500.0

    def test_pv4_power_typical(self):
        a = _make_registers(125, {17: 0, 18: 800})
        result = self._run(a)
        assert result["pv4_power_w"] == 800.0

    def test_pv_total_is_sum_of_strings(self):
        a = _make_registers(125, {6: 1000, 10: 2000, 14: 500, 18: 250})
        result = self._run(a)
        assert result["pv_power_w"] == 3750.0

    def test_pv1_voltage_decoded_with_scale(self):
        # vpv1 at offset 3: raw 3200 → 320.0 V
        a = _make_registers(125, {3: 3200})
        result = self._run(a)
        assert result["pv1_voltage_v"] == pytest.approx(320.0)

    def test_pv1_current_decoded_with_scale(self):
        # ipv1 at offset 4: raw 95 → 9.5 A
        a = _make_registers(125, {4: 95})
        result = self._run(a)
        assert result["pv1_current_a"] == pytest.approx(9.5)

    def test_pv_power_clamped_above_max(self):
        # 35000 W exceeds _MAX_PV_W (30000) → None
        a = _make_registers(125, {6: 35000})
        result = self._run(a)
        assert result["pv1_power_w"] is None

    def test_pv_voltage_clamped_above_max(self):
        # 12000 raw → 1200 V exceeds _MAX_PV_VOLT (1000) → None
        a = _make_registers(125, {3: 12000})
        result = self._run(a)
        assert result["pv1_voltage_v"] is None


# ── Grid / load decoding ──────────────────────────────────────────────────────

class TestReadInverterGrid:
    def _run(self, a_regs, b_regs=None, c_regs=None):
        c_regs = c_regs or _make_registers(8)
        mock_client = _make_mock_client(a_regs, b_regs, c_regs)
        with patch.dict("sys.modules", {
            "pymodbus": MagicMock(),
            "pymodbus.client": MagicMock(ModbusTcpClient=MagicMock(return_value=mock_client)),
            "pymodbus.exceptions": MagicMock(ModbusException=Exception),
        }):
            return _read_inverter("192.168.1.1", 502, 247)

    def test_grid_power_export_negated(self):
        # pgrid_total at offset 40: raw signed = +1000 (export) → HA = -1000 W
        a = _make_registers(125, {40: 1000})
        result = self._run(a)
        assert result["grid_power_w"] == -1000.0

    def test_grid_power_import_negated(self):
        # pgrid_total at offset 40: raw signed = -500 (import) → HA = +500 W
        a = _make_registers(125, {40: _u16_s16(-500)})
        result = self._run(a)
        assert result["grid_power_w"] == 500.0

    def test_grid_voltage_decoded(self):
        # vgrid_r at offset 21: raw 2300 → 230.0 V
        a = _make_registers(125, {21: 2300})
        result = self._run(a)
        assert result["grid_voltage_v"] == pytest.approx(230.0)

    def test_grid_frequency_decoded(self):
        # fgrid_r at offset 23: raw 5000 → 50.00 Hz
        a = _make_registers(125, {23: 5000})
        result = self._run(a)
        assert result["grid_frequency_hz"] == pytest.approx(50.0)

    def test_load_power_decoded(self):
        # pload at offset 72: raw signed = 2500 W
        a = _make_registers(125, {72: 2500})
        result = self._run(a)
        assert result["load_power_w"] == 2500.0

    def test_load_power_negative_decoded(self):
        # Negative load (unusual but can happen) — raw = -100
        a = _make_registers(125, {72: _u16_s16(-100)})
        result = self._run(a)
        assert result["load_power_w"] == -100.0

    def test_grid_voltage_clamped(self):
        # 3500 raw → 350 V > _MAX_GRID_VOLT (320) → None
        a = _make_registers(125, {21: 3500})
        result = self._run(a)
        assert result["grid_voltage_v"] is None

    def test_grid_power_clamped(self):
        # An extremely high signed16 value after sign-extension and negation
        a = _make_registers(125, {40: _u16_s16(-31000)})
        result = self._run(a)
        assert result["grid_power_w"] is None


# ── Battery decoding ──────────────────────────────────────────────────────────

class TestReadInverterBattery:
    def _run(self, a_regs, c_regs=None):
        c_regs = c_regs or _make_registers(8)
        mock_client = _make_mock_client(a_regs, None, c_regs, b_error=True)
        with patch.dict("sys.modules", {
            "pymodbus": MagicMock(),
            "pymodbus.client": MagicMock(ModbusTcpClient=MagicMock(return_value=mock_client)),
            "pymodbus.exceptions": MagicMock(ModbusException=Exception),
        }):
            return _read_inverter("192.168.1.1", 502, 247)

    def test_battery_power_discharging(self):
        # pbattery s32 hi/lo at offsets 82, 83: +5000 W (discharging)
        a = _make_registers(125, {82: 0, 83: 5000})
        result = self._run(a)
        assert result["battery_power_w"] == 5000.0

    def test_battery_power_charging(self):
        # Charging: negative s32
        a = _make_registers(125, {82: 0xFFFF, 83: _u16_s16(-3000) & 0xFFFF})
        result = self._run(a)
        assert result["battery_power_w"] == pytest.approx(-3000.0, abs=1)

    def test_battery_soc_decoded(self):
        # SOC at Block C offset 7
        c = _make_registers(8, {7: 80})
        a = _make_registers(125)
        result = self._run(a, c)
        assert result["battery_soc_pct"] == 80.0

    def test_battery_soc_none_when_block_c_missing(self):
        mock_client = _make_mock_client(_make_registers(125), None, None,
                                        b_error=True, c_error=True)
        with patch.dict("sys.modules", {
            "pymodbus": MagicMock(),
            "pymodbus.client": MagicMock(ModbusTcpClient=MagicMock(return_value=mock_client)),
            "pymodbus.exceptions": MagicMock(ModbusException=Exception),
        }):
            result = _read_inverter("192.168.1.1", 502, 247)
        assert result["battery_soc_pct"] is None

    def test_battery_power_clamped(self):
        # 25000 W > _MAX_BAT_W (20000) → None
        a = _make_registers(125, {82: 0, 83: 25000})
        result = self._run(a)
        assert result["battery_power_w"] is None


# ── Energy counters ────────────────────────────────────────────────────────────

class TestReadInverterEnergy:
    def _run(self, a_regs, b_regs=None, c_regs=None):
        c_regs = c_regs or _make_registers(8)
        mock_client = _make_mock_client(a_regs, b_regs, c_regs)
        with patch.dict("sys.modules", {
            "pymodbus": MagicMock(),
            "pymodbus.client": MagicMock(ModbusTcpClient=MagicMock(return_value=mock_client)),
            "pymodbus.exceptions": MagicMock(ModbusException=Exception),
        }):
            return _read_inverter("192.168.1.1", 502, 247)

    def test_pv_energy_today(self):
        # e_day_pv_hi/lo at offsets 93, 94: raw 150 → 15.0 kWh
        a = _make_registers(125, {93: 0, 94: 150})
        result = self._run(a)
        assert result["pv_energy_today_kwh"] == pytest.approx(15.0)

    def test_pv_energy_total(self):
        # e_total_pv at offsets 91, 92: raw 100000 → 10000.0 kWh
        # 100000 = 0x000186A0 → hi=0x0001, lo=0x86A0
        a = _make_registers(125)
        a[91] = 0x0001
        a[92] = 0x86A0
        result = self._run(a)
        assert result["pv_energy_total_kwh"] == pytest.approx(10000.0)

    def test_battery_charge_today(self):
        # e_bat_charge_day at offset 108: raw 50 → 5.0 kWh
        a = _make_registers(125, {108: 50})
        result = self._run(a)
        assert result["battery_charge_today_kwh"] == pytest.approx(5.0)

    def test_battery_discharge_today(self):
        # e_bat_discharge_day at offset 111: raw 30 → 3.0 kWh
        a = _make_registers(125, {111: 30})
        result = self._run(a)
        assert result["battery_discharge_today_kwh"] == pytest.approx(3.0)

    def test_grid_export_total_block_a(self):
        # e_total_export at offsets 95, 96: raw 5000 → 500.0 kWh
        a = _make_registers(125, {95: 0, 96: 5000})
        result = self._run(a)
        assert result["grid_export_total_kwh"] == pytest.approx(500.0)

    def test_grid_import_total_block_a(self):
        # e_total_import at offsets 100, 101: raw 8000 → 800.0 kWh
        a = _make_registers(125, {100: 0, 101: 8000})
        result = self._run(a)
        assert result["grid_import_total_kwh"] == pytest.approx(800.0)

    def test_pv_energy_today_clamped(self):
        # raw 65535 × 0.1 = 6553.5 kWh > _MAX_ENERGY_DAY (1000) → None
        a = _make_registers(125, {93: 0, 94: 65535})
        result = self._run(a)
        assert result["pv_energy_today_kwh"] is None


# ── Block B / meter decoding ───────────────────────────────────────────────────

class TestReadInverterMeter:
    def _run(self, a_regs, b_regs, c_regs=None):
        c_regs = c_regs or _make_registers(8)
        mock_client = _make_mock_client(a_regs, b_regs, c_regs)
        with patch.dict("sys.modules", {
            "pymodbus": MagicMock(),
            "pymodbus.client": MagicMock(ModbusTcpClient=MagicMock(return_value=mock_client)),
            "pymodbus.exceptions": MagicMock(ModbusException=Exception),
        }):
            return _read_inverter("192.168.1.1", 502, 247)

    def test_meter_power_total_negated(self):
        # meter_p at offset 8 in Block B: raw +300 W (export) → HA = -300 W
        b = _make_registers(50, {8: 300})
        result = self._run(_make_registers(125), b)
        assert result["meter_power_w"] == -300.0

    def test_meter_power_l1_negated(self):
        b = _make_registers(50, {5: 100})
        result = self._run(_make_registers(125), b)
        assert result["meter_power_r_w"] == -100.0

    def test_meter_power_l2_negated(self):
        b = _make_registers(50, {6: 200})
        result = self._run(_make_registers(125), b)
        assert result["meter_power_s_w"] == -200.0

    def test_meter_power_l3_negated(self):
        b = _make_registers(50, {7: 150})
        result = self._run(_make_registers(125), b)
        assert result["meter_power_t_w"] == -150.0

    def test_meter_frequency_decoded(self):
        # meter_freq at offset 14: raw 5000 → 50.00 Hz
        b = _make_registers(50, {14: 5000})
        result = self._run(_make_registers(125), b)
        assert result["meter_frequency_hz"] == pytest.approx(50.0)

    def test_meter_power_factor_decoded(self):
        # meter_pf at offset 13: raw 980 → 0.980
        b = _make_registers(50, {13: 980})
        result = self._run(_make_registers(125), b)
        assert result["meter_power_factor"] == pytest.approx(0.980)

    def test_meter_power_factor_negative(self):
        # Negative power factor: raw signed = -900 → -0.9
        b = _make_registers(50, {13: _u16_s16(-900)})
        result = self._run(_make_registers(125), b)
        assert result["meter_power_factor"] == pytest.approx(-0.9)

    def test_meter_export_total_float32(self):
        # Registers store energy directly in kWh as float32 (unit=1kWh per GoodWe spec).
        hi, lo = _f32_regs(1500.75)
        b = _make_registers(50, {15: hi, 16: lo})
        result = self._run(_make_registers(125), b)
        assert result["meter_export_total_kwh"] == pytest.approx(1500.75, rel=1e-4)

    def test_meter_import_total_float32(self):
        # 2500.0 kWh stored directly as float32.
        hi, lo = _f32_regs(2500.0)
        b = _make_registers(50, {17: hi, 18: lo})
        result = self._run(_make_registers(125), b)
        assert result["meter_import_total_kwh"] == pytest.approx(2500.0, rel=1e-4)

    def test_meter_export_total_large_kwh_not_clamped(self):
        # 5799.3 kWh must NOT be clamped to None (well within _MAX_ENERGY=999_999).
        hi, lo = _f32_regs(5799.3)
        b = _make_registers(50, {15: hi, 16: lo})
        result = self._run(_make_registers(125), b)
        assert result["meter_export_total_kwh"] == pytest.approx(5799.3, rel=1e-3)

    def test_meter_import_total_large_kwh_not_clamped(self):
        # 3200.0 kWh must pass through correctly.
        hi, lo = _f32_regs(3200.0)
        b = _make_registers(50, {17: hi, 18: lo})
        result = self._run(_make_registers(125), b)
        assert result["meter_import_total_kwh"] == pytest.approx(3200.0, rel=1e-3)

    def test_meter_power_32bit(self):
        # meter_p_total s32 at offsets 25, 26: -1200 W
        val = -1200
        hi = (val & 0xFFFFFFFF) >> 16
        lo = val & 0xFFFF
        b = _make_registers(50, {25: hi, 26: lo})
        result = self._run(_make_registers(125), b)
        # Negated: -1200 → +1200 (import)
        assert result["meter_power_total_w"] == pytest.approx(1200.0)

    def test_meter_absent_gives_none_values(self):
        """When Block B is missing all meter keys must be None."""
        mock_client = _make_mock_client(
            _make_registers(125), None, _make_registers(8), b_error=True
        )
        with patch.dict("sys.modules", {
            "pymodbus": MagicMock(),
            "pymodbus.client": MagicMock(ModbusTcpClient=MagicMock(return_value=mock_client)),
            "pymodbus.exceptions": MagicMock(ModbusException=Exception),
        }):
            result = _read_inverter("192.168.1.1", 502, 247)
        for key in ("meter_status", "meter_power_w", "meter_power_r_w", "meter_power_s_w",
                    "meter_power_t_w", "meter_power_total_w",
                    "meter_frequency_hz", "meter_power_factor",
                    "meter_export_total_kwh", "meter_import_total_kwh"):
            assert result[key] is None, f"expected None for {key!r}"

    def test_block_b_too_short_gives_none_values(self):
        """Block B responding with fewer than 19 registers must not crash.

        This reproduces the IndexError reported when the inverter returns a
        non-error Modbus response for the Block B range but with fewer
        registers than needed for even the basic meter data (offset 18).
        All meter sensor keys must be None and no exception must be raised.
        """
        # Return only 10 registers — fewer than the minimum 19 required
        short_b = _make_registers(10)
        mock_client = _make_mock_client(_make_registers(125), short_b, _make_registers(8))
        with patch.dict("sys.modules", {
            "pymodbus": MagicMock(),
            "pymodbus.client": MagicMock(ModbusTcpClient=MagicMock(return_value=mock_client)),
            "pymodbus.exceptions": MagicMock(ModbusException=Exception),
        }):
            result = _read_inverter("192.168.1.1", 502, 247)
        assert result is not None, "should return data dict, not None"
        for key in ("meter_status", "meter_power_w", "meter_power_r_w", "meter_power_s_w",
                    "meter_power_t_w", "meter_power_total_w",
                    "meter_frequency_hz", "meter_power_factor",
                    "meter_export_total_kwh", "meter_import_total_kwh"):
            assert result[key] is None, f"expected None for {key!r}"

    def test_block_b_partial_gives_energy_but_no_int32_power(self):
        """Block B with 19–26 registers should provide int16/energy data but not int32 power.

        This reproduces the scenario where a GoodWe inverter returns Block B with
        enough registers for int16 power (offsets 5–9) and float32 energy (15–18)
        but not the extended 32-bit total power word (offsets 25–26).
        The 32-bit power sensor must be None; all other meter sensors must work.
        """
        hi, lo = _f32_regs(1234.5)
        partial_b = _make_registers(22, {
            8: 500,    # meter_p (int16, W): raw +500 → HA = -500 (negated)
            15: hi, 16: lo,  # e_total_export_hi/lo: 1234.5 kWh
        })
        mock_client = _make_mock_client(_make_registers(125), partial_b, _make_registers(8))
        with patch.dict("sys.modules", {
            "pymodbus": MagicMock(),
            "pymodbus.client": MagicMock(ModbusTcpClient=MagicMock(return_value=mock_client)),
            "pymodbus.exceptions": MagicMock(ModbusException=Exception),
        }):
            result = _read_inverter("192.168.1.1", 502, 247)
        assert result is not None, "should return data dict, not None"
        # int16 power and float32 energy must be available
        assert result["meter_power_w"] == pytest.approx(-500.0), "int16 power should be available"
        assert result["meter_export_total_kwh"] == pytest.approx(1234.5, rel=1e-3), \
            "float32 export energy should be available"
        # int32 total power must be None (offsets 25–26 out of range)
        assert result["meter_power_total_w"] is None, "int32 power must be None for partial Block B"

    def test_temperature_decoded(self):
        # temperature_heatsink at offset 76: raw signed 250 → 25.0 °C
        a = _make_registers(125, {76: 250})
        result = self._run(a, _make_registers(50))
        assert result["heatsink_temp_c"] == pytest.approx(25.0)

    def test_temperature_negative(self):
        # raw -100 → -10.0 °C
        a = _make_registers(125, {76: _u16_s16(-100)})
        result = self._run(a, _make_registers(50))
        assert result["heatsink_temp_c"] == pytest.approx(-10.0)

    def test_air_temperature_decoded(self):
        # temperature_air at offset 77: raw signed 200 → 20.0 °C
        a = _make_registers(125, {77: 200})
        result = self._run(a, _make_registers(50))
        assert result["air_temp_c"] == pytest.approx(20.0)

    def test_air_temperature_negative(self):
        # raw -50 → -5.0 °C
        a = _make_registers(125, {77: _u16_s16(-50)})
        result = self._run(a, _make_registers(50))
        assert result["air_temp_c"] == pytest.approx(-5.0)

    def test_meter_status_decoded(self):
        # meter_status at Block B offset 0: value 2 (three-phase)
        b = _make_registers(50, {0: 2})
        result = self._run(_make_registers(125), b)
        assert result["meter_status"] == 2

    def test_meter_status_none_when_block_b_absent(self):
        # When Block B is missing, meter_status must be None
        mock_client = _make_mock_client(
            _make_registers(125), None, _make_registers(8), b_error=True
        )
        with patch.dict("sys.modules", {
            "pymodbus": MagicMock(),
            "pymodbus.client": MagicMock(ModbusTcpClient=MagicMock(return_value=mock_client)),
            "pymodbus.exceptions": MagicMock(ModbusException=Exception),
        }):
            result = _read_inverter("192.168.1.1", 502, 247)
        assert result["meter_status"] is None
