"""
coordinator.py – DataUpdateCoordinator for GoodWe Modbus.

Reads Modbus registers from master (and optional slave) inverter, decodes and
filters the data, and makes the combined result available to sensor entities.

The synchronous pymodbus calls are offloaded to the HA executor thread pool so
they never block the event loop.
"""

from __future__ import annotations

import logging
import struct
from collections import deque
from datetime import timedelta
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_MODBUS_PORT,
    CONF_UNIT_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# ── Register map ──────────────────────────────────────────────────────────────
_BLOCK_A_START = 35100
_BLOCK_A_COUNT = 100
_BLOCK_B_START = 36000
_BLOCK_B_COUNT = 50  # covers offsets 0–49 (36000–36049)

_A = {
    "vpv1": 3, "ipv1": 4, "ppv1": 5,
    "vpv2": 6, "ipv2": 7, "ppv2": 8,
    "vpv3": 9, "ipv3": 10, "ppv3": 11,
    "vpv4": 12, "ipv4": 13, "ppv4": 14,
    "vgrid_r": 16, "igrid_r": 17, "fgrid_r": 18, "pgrid_r": 19,
    "pgrid_s": 23, "pgrid_t": 27, "pgrid_total": 28,
    "work_mode": 37,
    "pbattery": 40, "soc": 41,
    "pload": 47,
    "temperature": 54,
    "e_day_pv": 56,
    "e_total_pv": 60,
    "e_day_charge": 70,
    "e_day_discharge": 74,
}

_B = {
    # External meter – compact int16 readings (offsets 5–14)
    "meter_p1":    5,   # Active power L1 (signed int16, W)
    "meter_p2":    6,   # Active power L2 (signed int16, W)
    "meter_p3":    7,   # Active power L3 (signed int16, W)
    "meter_p":     8,   # Active power total (signed int16, W)
    "meter_q":     9,   # Reactive power total (signed int16, var)
    "meter_pf":   13,   # Power factor (×0.001)
    "meter_freq": 14,   # Frequency (×0.01 Hz)
    # External meter – energy counters.  Stored as IEEE 754 float32 (big-endian
    # word order); raw unit is Wh, divide by 1000 to get kWh.  See also the
    # marcelblijleven/goodwe reference library (Float type, scale=1000).
    "e_total_export_hi": 15, "e_total_export_lo": 16,   # float32 → Wh ÷1000 = kWh
    "e_total_import_hi": 17, "e_total_import_lo": 18,   # float32 → Wh ÷1000 = kWh
    # Extended 32-bit active power (signed int32)
    "meter_p_total_hi": 25, "meter_p_total_lo": 26,
}

_MAX_PV_W      = 30_000
_MAX_BAT_W     = 20_000
_MAX_GRID_W    = 30_000
_MAX_LOAD_W    = 30_000
_MAX_ENERGY    = 999_999


# ── Low-level helpers (run in executor) ───────────────────────────────────────

def _s16(v: int) -> int:
    return v if v < 0x8000 else v - 0x10000


def _u32(hi: int, lo: int) -> int:
    return (hi << 16) | lo


def _clamp(value: float, max_abs: float) -> Optional[float]:
    return value if abs(value) <= max_abs else None


def _f32(hi: int, lo: int) -> float:
    """Decode two 16-bit big-endian Modbus registers as an IEEE 754 float32."""
    return struct.unpack(">f", struct.pack(">HH", hi, lo))[0]


def _s32(hi: int, lo: int) -> int:
    """Decode two 16-bit registers as a signed int32."""
    val = (hi << 16) | lo
    return val if val < 0x80000000 else val - 0x100000000


def _read_inverter(host: str, port: int, unit_id: int) -> Optional[dict]:
    """
    Open a Modbus TCP connection, read both register blocks, return raw dict.
    Executed in the HA executor thread (blocking I/O).
    """
    from pymodbus.client import ModbusTcpClient
    from pymodbus.exceptions import ModbusException

    client = ModbusTcpClient(host=host, port=port, timeout=5)
    if not client.connect():
        _LOGGER.warning("Cannot connect to inverter at %s:%s", host, port)
        return None

    try:
        rr_a = client.read_holding_registers(
            address=_BLOCK_A_START, count=_BLOCK_A_COUNT, device_id=unit_id)
        if rr_a.isError():
            _LOGGER.warning("Modbus error (block A) from %s: %s", host, rr_a)
            return None
        a = rr_a.registers

        rr_b = client.read_holding_registers(
            address=_BLOCK_B_START, count=_BLOCK_B_COUNT, device_id=unit_id)
        b = rr_b.registers if not rr_b.isError() else None

    except ModbusException as exc:
        _LOGGER.error("ModbusException from %s: %s", host, exc)
        return None
    finally:
        client.close()

    def rb(key: str) -> int:
        return b[_B[key]] if b else 0

    def _rb_grid_w(key: str) -> Optional[float]:
        """Read a signed int16 grid-power register; returns None when Block B is absent."""
        return _clamp(float(_s16(rb(key))), _MAX_GRID_W) if b else None

    ppv1 = _clamp(float(a[_A["ppv1"]]), _MAX_PV_W)
    ppv2 = _clamp(float(a[_A["ppv2"]]), _MAX_PV_W)
    ppv3 = _clamp(float(a[_A["ppv3"]]), _MAX_PV_W)
    ppv4 = _clamp(float(a[_A["ppv4"]]), _MAX_PV_W)
    pv_total = sum(p for p in (ppv1, ppv2, ppv3, ppv4) if p is not None)

    # External meter readings from Block B (None when Block B unavailable)
    meter_p_total32 = (
        _clamp(float(_s32(rb("meter_p_total_hi"), rb("meter_p_total_lo"))), _MAX_GRID_W)
        if b else None
    )

    # The energy registers at offsets 15–18 contain IEEE 754 float32 values
    # whose raw unit is Wh (divide by 1000 to obtain kWh).  This matches the
    # encoding documented in the marcelblijleven/goodwe reference library.
    # Note: these sensors do not have monotonic guards; the firmware counter
    # may reset at midnight for daily values, so TOTAL_INCREASING semantics
    # rely on HA's own long-term statistics correction.
    meter_exp_kwh = _f32(rb("e_total_export_hi"), rb("e_total_export_lo")) / 1000.0 if b else None
    meter_imp_kwh = _f32(rb("e_total_import_hi"), rb("e_total_import_lo")) / 1000.0 if b else None

    return {
        "pv1_voltage_v":   a[_A["vpv1"]] * 0.1,
        "pv1_current_a":   a[_A["ipv1"]] * 0.1,
        "pv1_power_w":     ppv1,
        "pv2_voltage_v":   a[_A["vpv2"]] * 0.1,
        "pv2_current_a":   a[_A["ipv2"]] * 0.1,
        "pv2_power_w":     ppv2,
        "pv3_voltage_v":   a[_A["vpv3"]] * 0.1,
        "pv3_current_a":   a[_A["ipv3"]] * 0.1,
        "pv3_power_w":     ppv3,
        "pv4_voltage_v":   a[_A["vpv4"]] * 0.1,
        "pv4_current_a":   a[_A["ipv4"]] * 0.1,
        "pv4_power_w":     ppv4,
        "pv_power_w":      pv_total,
        "grid_voltage_v":  a[_A["vgrid_r"]] * 0.1,
        "grid_frequency_hz": a[_A["fgrid_r"]] * 0.01,
        "grid_power_r_w":  _clamp(float(_s16(a[_A["pgrid_r"]])), _MAX_GRID_W),
        "grid_power_s_w":  _clamp(float(_s16(a[_A["pgrid_s"]])), _MAX_GRID_W),
        "grid_power_t_w":  _clamp(float(_s16(a[_A["pgrid_t"]])), _MAX_GRID_W),
        "grid_power_w":    _clamp(float(_s16(a[_A["pgrid_total"]])), _MAX_GRID_W),
        "battery_power_w": _clamp(float(_s16(a[_A["pbattery"]])), _MAX_BAT_W),
        "battery_soc_pct": float(a[_A["soc"]]),
        "load_power_w":    _clamp(float(a[_A["pload"]]), _MAX_LOAD_W),
        "inverter_temp_c": a[_A["temperature"]] * 0.1,
        "pv_energy_today_kwh":        _u32(a[_A["e_day_pv"]],        a[_A["e_day_pv"] + 1])        * 0.1,
        "pv_energy_total_kwh":        _u32(a[_A["e_total_pv"]],      a[_A["e_total_pv"] + 1])      * 0.1,
        "battery_charge_today_kwh":   _u32(a[_A["e_day_charge"]],    a[_A["e_day_charge"] + 1])    * 0.1,
        "battery_discharge_today_kwh":_u32(a[_A["e_day_discharge"]], a[_A["e_day_discharge"] + 1]) * 0.1,
        "grid_export_total_kwh": _u32(rb("e_total_export_hi"), rb("e_total_export_lo")) * 0.1,
        "grid_import_total_kwh": _u32(rb("e_total_import_hi"), rb("e_total_import_lo")) * 0.1,
        "work_mode": a[_A["work_mode"]],
        # ── External meter (Block B) ──────────────────────────────────────────
        "meter_power_r_w":      _rb_grid_w("meter_p1"),
        "meter_power_s_w":      _rb_grid_w("meter_p2"),
        "meter_power_t_w":      _rb_grid_w("meter_p3"),
        "meter_power_w":        _rb_grid_w("meter_p"),
        "meter_power_total_w":  meter_p_total32,
        "meter_frequency_hz":   rb("meter_freq") * 0.01 if b else None,
        "meter_power_factor":   rb("meter_pf") * 0.001 if b else None,
        "meter_export_total_kwh": meter_exp_kwh,
        "meter_import_total_kwh": meter_imp_kwh,
    }


# ── Spike filter ──────────────────────────────────────────────────────────────

class _SpikeFilter:
    def __init__(self, window: int = 5, max_delta: float = 10_000) -> None:
        self._history: deque[float] = deque(maxlen=window)
        self._last: Optional[float] = None
        self._max_delta = max_delta

    def __call__(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return self._last
        if self._history:
            median = sorted(self._history)[len(self._history) // 2]
            if abs(value - median) > self._max_delta:
                return self._last
        self._history.append(value)
        self._last = value
        return value


class _MonotonicGuard:
    def __init__(self) -> None:
        self._last: Optional[float] = None

    def __call__(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return self._last
        if self._last is not None and value < self._last:
            return self._last
        self._last = value
        return value


# ── Coordinator ───────────────────────────────────────────────────────────────

class GoodWeCoordinator(DataUpdateCoordinator):
    """Fetches and filters data from a single GoodWe inverter."""

    def __init__(self, hass: HomeAssistant, entry_data: dict) -> None:
        self._host    = entry_data[CONF_HOST]
        self._port    = entry_data.get(CONF_MODBUS_PORT, DEFAULT_PORT)
        self._unit_id = entry_data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)
        interval      = entry_data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

        # Output-side spike filters
        self._sf_pv   = _SpikeFilter(max_delta=10_000)
        self._sf_bat  = _SpikeFilter(max_delta=8_000)
        self._sf_grid = _SpikeFilter(max_delta=10_000)
        self._sf_load = _SpikeFilter(max_delta=10_000)

        # Monotonic energy guards
        self._mono = {k: _MonotonicGuard() for k in (
            "pv_energy_total_kwh", "grid_export_total_kwh", "grid_import_total_kwh")}

    async def _async_update_data(self) -> dict:
        data = await self.hass.async_add_executor_job(
            _read_inverter, self._host, self._port, self._unit_id
        )

        if data is None:
            raise UpdateFailed(f"No data received from inverter at {self._host}")

        # Apply monotonic guards
        for key, guard in self._mono.items():
            data[key] = guard(data.get(key))

        # Apply output spike filters
        data["pv_power_w"]      = self._sf_pv(data.get("pv_power_w"))
        data["battery_power_w"] = self._sf_bat(data.get("battery_power_w"))
        grid = self._sf_grid(data.get("grid_power_w"))
        data["grid_power_w"]    = 0.0 if grid is not None and abs(grid) < 30 else grid
        data["load_power_w"]    = self._sf_load(data.get("load_power_w"))

        return data
