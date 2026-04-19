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
# Based on GoodWe ET/EH/BT/BH ARM205 Modbus protocol v1.7 and confirmed
# against the marcelblijleven/goodwe reference library (et.py, platform 205).

_BLOCK_A_START = 35100
_BLOCK_A_COUNT = 125   # offsets 0–124 (35100–35224)
_BLOCK_B_START = 36000
_BLOCK_B_COUNT = 50    # offsets 0–49  (36000–36049)
_BLOCK_C_START = 37000
_BLOCK_C_COUNT = 8     # offsets 0–7   (37000–37007); BMS data

# Block A – inverter running data (offsets relative to 35100)
_A = {
    # ── PV strings: voltage (u16, ×0.1 V), current (u16, ×0.1 A),
    #    power (u32 = 2 registers, W) ─────────────────────────────────────────
    "vpv1": 3,  "ipv1": 4,  "ppv1_hi": 5,  "ppv1_lo": 6,
    "vpv2": 7,  "ipv2": 8,  "ppv2_hi": 9,  "ppv2_lo": 10,
    "vpv3": 11, "ipv3": 12, "ppv3_hi": 13, "ppv3_lo": 14,
    "vpv4": 15, "ipv4": 16, "ppv4_hi": 17, "ppv4_lo": 18,
    # ── On-grid measurements (L1 voltage/current/frequency only) ─────────────
    "vgrid_r": 21,   # L1 Voltage  (u16, ×0.1 V)
    "igrid_r": 22,   # L1 Current  (u16, ×0.1 A)
    "fgrid_r": 23,   # L1 Frequency (u16, ×0.01 Hz)
    # offset 24: reserved
    "pgrid_r": 25,   # L1 Active Power (signed int16, W;  + = export to grid)
    "pgrid_s": 30,   # L2 Active Power (signed int16, W)
    "pgrid_t": 35,   # L3 Active Power (signed int16, W)
    "pgrid_total": 40,  # Active Power Total (signed int16, W; + = export)
    # ── Load & backup ─────────────────────────────────────────────────────────
    "pload": 72,     # Total Load Power (signed int16, W)
    # ── Temperatures ─────────────────────────────────────────────────────────
    "temperature": 76,  # Radiator temperature (signed int16, ×0.1 °C)
    # ── Work mode ────────────────────────────────────────────────────────────
    "work_mode": 87,
    # ── Battery (signed int32 = 2 registers; + = discharging) ────────────────
    "pbattery_hi": 82, "pbattery_lo": 83,
    # ── Energy counters (all u32 = 2 registers, raw ÷10 = kWh) ───────────────
    "e_total_pv_hi":  91, "e_total_pv_lo":  92,   # Total PV generation
    "e_day_pv_hi":    93, "e_day_pv_lo":    94,   # Today PV generation
    "e_total_export_hi": 95, "e_total_export_lo": 96,   # Total export
    # offsets 97–99: h_total (run hours) + e_day_exp (u16)
    "e_total_import_hi": 100, "e_total_import_lo": 101,  # Total import
    # offsets 102–105: e_day_imp / e_load_total / e_load_day
    "e_bat_charge_total_hi": 106, "e_bat_charge_total_lo": 107,
    "e_bat_charge_day":      108,  # u16, ÷10 = kWh
    "e_bat_discharge_total_hi": 109, "e_bat_discharge_total_lo": 110,
    "e_bat_discharge_day":       111,  # u16, ÷10 = kWh
}

# Block B – ARM external CT meter (offsets relative to 36000)
_B = {
    # Compact int16 active-power readings (offsets 5–9)
    "meter_p1":   5,   # L1 Active power (signed int16, W)
    "meter_p2":   6,   # L2 Active power (signed int16, W)
    "meter_p3":   7,   # L3 Active power (signed int16, W)
    "meter_p":    8,   # Total active power (signed int16, W)
    "meter_q":    9,   # Reactive power total (signed int16, var)
    "meter_pf":  13,   # Power factor (signed int16, ×0.001)
    "meter_freq": 14,  # Frequency (u16, ×0.01 Hz)
    # Energy counters stored as IEEE 754 float32 (big-endian word order).
    # The float32 value represents the energy in kWh directly — no scaling required.
    "e_total_export_hi": 15, "e_total_export_lo": 16,
    "e_total_import_hi": 17, "e_total_import_lo": 18,
    # Extended 32-bit active-power total (signed int32)
    "meter_p_total_hi": 25, "meter_p_total_lo": 26,
}

# Block C – BMS / battery pack data (offsets relative to 37000)
_C = {
    "battery_soc": 7,  # Battery State of Charge (%, register 37007)
}

_MAX_PV_W      = 30_000
_MAX_BAT_W     = 20_000
_MAX_GRID_W    = 30_000
_MAX_LOAD_W    = 30_000
_MAX_ENERGY    = 999_999
_MAX_ENERGY_DAY = 1_000  # max plausible kWh in a single day for a residential system
_MAX_PV_VOLT   = 1_000      # max plausible PV string voltage (V)
_MAX_GRID_VOLT = 320        # max plausible AC grid voltage (V)
_MAX_FREQ_HZ   = 65         # max plausible grid frequency (Hz)
_MAX_TEMP_C    = 120        # inverter temp range: −120…120 °C (symmetric via _clamp)
_MAX_SOC_PCT   = 100        # battery SOC is 0–100 %


# ── Low-level helpers (run in executor) ───────────────────────────────────────

def _s16(v: int) -> int:
    return v if v < 0x8000 else v - 0x10000


def _u32(hi: int, lo: int) -> int:
    return (hi << 16) | lo


def _clamp(value: float, max_abs: float) -> Optional[float]:
    """Return *value* if it lies within [-max_abs, max_abs], else None."""
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

        rr_c = client.read_holding_registers(
            address=_BLOCK_C_START, count=_BLOCK_C_COUNT, device_id=unit_id)
        if rr_c.isError():
            _LOGGER.debug("Block C (BMS) not available from %s: %s", host, rr_c)
            c = None
        else:
            c = rr_c.registers

    except ModbusException as exc:
        _LOGGER.error("ModbusException from %s: %s", host, exc)
        return None
    finally:
        client.close()

    def rb(key: str) -> int:
        return b[_B[key]] if b else 0

    def _rb_grid_w(key: str) -> Optional[float]:
        """Read a signed int16 grid-power register from Block B.

        Negated so the HA convention holds: positive = import, negative = export.
        Returns None when Block B is absent.
        """
        return _clamp(-float(_s16(rb(key))), _MAX_GRID_W) if b else None

    ppv1 = _clamp(float(_u32(a[_A["ppv1_hi"]], a[_A["ppv1_lo"]])), _MAX_PV_W)
    ppv2 = _clamp(float(_u32(a[_A["ppv2_hi"]], a[_A["ppv2_lo"]])), _MAX_PV_W)
    ppv3 = _clamp(float(_u32(a[_A["ppv3_hi"]], a[_A["ppv3_lo"]])), _MAX_PV_W)
    ppv4 = _clamp(float(_u32(a[_A["ppv4_hi"]], a[_A["ppv4_lo"]])), _MAX_PV_W)
    pv_total = sum(p for p in (ppv1, ppv2, ppv3, ppv4) if p is not None)

    # Battery power: signed int32 (+ = discharging into house, − = charging)
    bat_power = _clamp(float(_s32(a[_A["pbattery_hi"]], a[_A["pbattery_lo"]])), _MAX_BAT_W)

    # External meter: total active power as signed int32, negated for HA convention
    meter_p_total32 = (
        _clamp(-float(_s32(rb("meter_p_total_hi"), rb("meter_p_total_lo"))), _MAX_GRID_W)
        if b else None
    )

    # External meter energy totals: float32 registers (36015–36018) hold the
    # cumulative energy directly in kWh.  No further scaling is required.
    meter_exp_kwh = _f32(rb("e_total_export_hi"), rb("e_total_export_lo")) if b else None
    meter_imp_kwh = _f32(rb("e_total_import_hi"), rb("e_total_import_lo")) if b else None

    return {
        "pv1_voltage_v":   _clamp(a[_A["vpv1"]] * 0.1, _MAX_PV_VOLT),
        "pv1_current_a":   a[_A["ipv1"]] * 0.1,
        "pv1_power_w":     ppv1,
        "pv2_voltage_v":   _clamp(a[_A["vpv2"]] * 0.1, _MAX_PV_VOLT),
        "pv2_current_a":   a[_A["ipv2"]] * 0.1,
        "pv2_power_w":     ppv2,
        "pv3_voltage_v":   _clamp(a[_A["vpv3"]] * 0.1, _MAX_PV_VOLT),
        "pv3_current_a":   a[_A["ipv3"]] * 0.1,
        "pv3_power_w":     ppv3,
        "pv4_voltage_v":   _clamp(a[_A["vpv4"]] * 0.1, _MAX_PV_VOLT),
        "pv4_current_a":   a[_A["ipv4"]] * 0.1,
        "pv4_power_w":     ppv4,
        "pv_power_w":      pv_total,
        "grid_voltage_v":  _clamp(a[_A["vgrid_r"]] * 0.1, _MAX_GRID_VOLT),
        "grid_frequency_hz": _clamp(a[_A["fgrid_r"]] * 0.01, _MAX_FREQ_HZ),
        # Grid power: negated — GoodWe positive = export; HA positive = import
        "grid_power_r_w":  _clamp(-float(_s16(a[_A["pgrid_r"]])),     _MAX_GRID_W),
        "grid_power_s_w":  _clamp(-float(_s16(a[_A["pgrid_s"]])),     _MAX_GRID_W),
        "grid_power_t_w":  _clamp(-float(_s16(a[_A["pgrid_t"]])),     _MAX_GRID_W),
        "grid_power_w":    _clamp(-float(_s16(a[_A["pgrid_total"]])), _MAX_GRID_W),
        "battery_power_w": bat_power,
        "battery_soc_pct": _clamp(float(c[_C["battery_soc"]]), _MAX_SOC_PCT) if c else None,
        "load_power_w":    _clamp(float(_s16(a[_A["pload"]])), _MAX_LOAD_W),
        "inverter_temp_c": _clamp(_s16(a[_A["temperature"]]) * 0.1, _MAX_TEMP_C),
        "pv_energy_today_kwh":        _clamp(_u32(a[_A["e_day_pv_hi"]],    a[_A["e_day_pv_lo"]])    * 0.1, _MAX_ENERGY_DAY),
        "pv_energy_total_kwh":        _clamp(_u32(a[_A["e_total_pv_hi"]],  a[_A["e_total_pv_lo"]]) * 0.1, _MAX_ENERGY),
        "battery_charge_today_kwh":   _clamp(a[_A["e_bat_charge_day"]]    * 0.1, _MAX_ENERGY_DAY),
        "battery_discharge_today_kwh": _clamp(a[_A["e_bat_discharge_day"]] * 0.1, _MAX_ENERGY_DAY),
        # Battery lifetime totals (Block A, u32, ÷10 = kWh)
        "battery_charge_total_kwh":    _clamp(_u32(a[_A["e_bat_charge_total_hi"]],    a[_A["e_bat_charge_total_lo"]])    * 0.1, _MAX_ENERGY),
        "battery_discharge_total_kwh": _clamp(_u32(a[_A["e_bat_discharge_total_hi"]], a[_A["e_bat_discharge_total_lo"]]) * 0.1, _MAX_ENERGY),
        # Inverter-side export/import totals (Block A, u32, ÷10 = kWh)
        "grid_export_total_kwh": _clamp(_u32(a[_A["e_total_export_hi"]], a[_A["e_total_export_lo"]]) * 0.1, _MAX_ENERGY),
        "grid_import_total_kwh": _clamp(_u32(a[_A["e_total_import_hi"]], a[_A["e_total_import_lo"]]) * 0.1, _MAX_ENERGY),
        "work_mode": a[_A["work_mode"]],
        # ── External meter (Block B) ──────────────────────────────────────────
        "meter_power_r_w":      _rb_grid_w("meter_p1"),
        "meter_power_s_w":      _rb_grid_w("meter_p2"),
        "meter_power_t_w":      _rb_grid_w("meter_p3"),
        "meter_power_w":        _rb_grid_w("meter_p"),
        "meter_power_total_w":  meter_p_total32,
        "meter_frequency_hz":   _clamp(rb("meter_freq") * 0.01, _MAX_FREQ_HZ) if b else None,
        "meter_power_factor":   _clamp(_s16(rb("meter_pf")) * 0.001, 1.0) if b else None,
        "meter_export_total_kwh": _clamp(meter_exp_kwh, _MAX_ENERGY) if meter_exp_kwh is not None else None,
        "meter_import_total_kwh": _clamp(meter_imp_kwh, _MAX_ENERGY) if meter_imp_kwh is not None else None,
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
            if abs(value - median) >= self._max_delta:
                return self._last
        self._history.append(value)
        self._last = value
        return value


class _DailyEnergyFilter:
    """Spike filter for daily (today) energy counters.

    Only upward spikes (value >= median + max_up_delta) are rejected.
    A significant *drop* — which indicates a midnight counter reset — is
    accepted and clears the history so the filter adapts to the new day
    immediately instead of freezing at the previous day's final value.
    """

    def __init__(self, window: int = 5, max_up_delta: float = 10) -> None:
        self._history: deque[float] = deque(maxlen=window)
        self._last: Optional[float] = None
        self._max_up_delta = max_up_delta

    def __call__(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return self._last
        if self._history:
            median = sorted(self._history)[len(self._history) // 2]
            if value >= median + self._max_up_delta:
                # Upward spike — corrupted register; suppress it
                return self._last
            if value < median - self._max_up_delta:
                # Significant drop — midnight reset; clear stale history
                self._history.clear()
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

        # Output-side spike filters — power channels
        self._sf_pv      = _SpikeFilter(max_delta=10_000)
        self._sf_pv1     = _SpikeFilter(max_delta=10_000)
        self._sf_pv2     = _SpikeFilter(max_delta=10_000)
        self._sf_pv3     = _SpikeFilter(max_delta=10_000)
        self._sf_pv4     = _SpikeFilter(max_delta=10_000)
        self._sf_bat     = _SpikeFilter(max_delta=8_000)
        self._sf_grid    = _SpikeFilter(max_delta=10_000)
        self._sf_grid_r  = _SpikeFilter(max_delta=10_000)
        self._sf_grid_s  = _SpikeFilter(max_delta=10_000)
        self._sf_grid_t  = _SpikeFilter(max_delta=10_000)
        self._sf_load    = _SpikeFilter(max_delta=10_000)
        self._sf_meter   = _SpikeFilter(max_delta=10_000)
        self._sf_meter_r = _SpikeFilter(max_delta=10_000)
        self._sf_meter_s = _SpikeFilter(max_delta=10_000)
        self._sf_meter_t = _SpikeFilter(max_delta=10_000)
        self._sf_meter32 = _SpikeFilter(max_delta=10_000)

        # Output-side spike filters — energy counters (applied before monotonic guard)
        self._sf_e_pv_total        = _SpikeFilter(max_delta=200)
        self._sf_e_export_total    = _SpikeFilter(max_delta=200)
        self._sf_e_import_total    = _SpikeFilter(max_delta=200)
        self._sf_e_meter_exp_total = _SpikeFilter(max_delta=200)
        self._sf_e_meter_imp_total = _SpikeFilter(max_delta=200)
        self._sf_e_bat_chg_total   = _SpikeFilter(max_delta=200)
        self._sf_e_bat_dis_total   = _SpikeFilter(max_delta=200)

        # Spike filters for daily (today) energy counters — only upward spikes are
        # rejected; midnight resets (drop to ~0) clear the history automatically.
        # max_up_delta=3.0 kWh: allows legitimate accumulation even at slow scan
        # intervals (≤300 s) while still catching register-corruption spikes
        # (e.g. a u16 glitch that jumps the reading by 10+ kWh in one cycle).
        self._sf_e_pv_today        = _DailyEnergyFilter(max_up_delta=3.0)
        self._sf_e_bat_chg_today   = _DailyEnergyFilter(max_up_delta=3.0)
        self._sf_e_bat_dis_today   = _DailyEnergyFilter(max_up_delta=3.0)

        # Monotonic energy guards
        self._mono = {k: _MonotonicGuard() for k in (
            "pv_energy_total_kwh",
            "grid_export_total_kwh",
            "grid_import_total_kwh",
            "meter_export_total_kwh",
            "meter_import_total_kwh",
            "battery_charge_total_kwh",
            "battery_discharge_total_kwh",
        )}

    async def _async_update_data(self) -> dict:
        data = await self.hass.async_add_executor_job(
            _read_inverter, self._host, self._port, self._unit_id
        )

        if data is None:
            raise UpdateFailed(f"No data received from inverter at {self._host}")

        # Spike-filter energy counters first, then apply monotonic guards so that
        # a single corrupted reading cannot permanently lock the counter too high.
        data["pv_energy_total_kwh"]          = self._sf_e_pv_total(data.get("pv_energy_total_kwh"))
        data["grid_export_total_kwh"]        = self._sf_e_export_total(data.get("grid_export_total_kwh"))
        data["grid_import_total_kwh"]        = self._sf_e_import_total(data.get("grid_import_total_kwh"))
        data["meter_export_total_kwh"]       = self._sf_e_meter_exp_total(data.get("meter_export_total_kwh"))
        data["meter_import_total_kwh"]       = self._sf_e_meter_imp_total(data.get("meter_import_total_kwh"))
        data["battery_charge_total_kwh"]     = self._sf_e_bat_chg_total(data.get("battery_charge_total_kwh"))
        data["battery_discharge_total_kwh"]  = self._sf_e_bat_dis_total(data.get("battery_discharge_total_kwh"))

        # Spike-filter daily energy counters — u16 register corruption (e.g. 65535)
        # yields 6 553.5 kWh which is far above the tight _MAX_ENERGY_DAY clamp but
        # the filter catches any residual implausible jumps as a second line of defence.
        data["pv_energy_today_kwh"]          = self._sf_e_pv_today(data.get("pv_energy_today_kwh"))
        data["battery_charge_today_kwh"]     = self._sf_e_bat_chg_today(data.get("battery_charge_today_kwh"))
        data["battery_discharge_today_kwh"]  = self._sf_e_bat_dis_today(data.get("battery_discharge_today_kwh"))

        # Apply monotonic guards
        for key, guard in self._mono.items():
            data[key] = guard(data.get(key))

        # Apply output spike filters — individual PV strings
        data["pv1_power_w"] = self._sf_pv1(data.get("pv1_power_w"))
        data["pv2_power_w"] = self._sf_pv2(data.get("pv2_power_w"))
        data["pv3_power_w"] = self._sf_pv3(data.get("pv3_power_w"))
        data["pv4_power_w"] = self._sf_pv4(data.get("pv4_power_w"))
        data["pv_power_w"]  = self._sf_pv(data.get("pv_power_w"))

        # Battery
        data["battery_power_w"] = self._sf_bat(data.get("battery_power_w"))

        # Grid — total and per phase
        grid = self._sf_grid(data.get("grid_power_w"))
        data["grid_power_w"]   = 0.0 if grid is not None and abs(grid) < 30 else grid
        data["grid_power_r_w"] = self._sf_grid_r(data.get("grid_power_r_w"))
        data["grid_power_s_w"] = self._sf_grid_s(data.get("grid_power_s_w"))
        data["grid_power_t_w"] = self._sf_grid_t(data.get("grid_power_t_w"))

        # Load
        data["load_power_w"] = self._sf_load(data.get("load_power_w"))

        # External meter — per phase and totals
        data["meter_power_r_w"]    = self._sf_meter_r(data.get("meter_power_r_w"))
        data["meter_power_s_w"]    = self._sf_meter_s(data.get("meter_power_s_w"))
        data["meter_power_t_w"]    = self._sf_meter_t(data.get("meter_power_t_w"))
        data["meter_power_w"]      = self._sf_meter(data.get("meter_power_w"))
        data["meter_power_total_w"] = self._sf_meter32(data.get("meter_power_total_w"))

        # ── Meter-priority overrides ──────────────────────────────────────────
        # When the external CT meter (Block B) is present its values match the
        # SEMS+ portal and are more accurate than the inverter's Block A counters:
        #
        # • grid_export/import: meter float32 (kWh) ← preferred over inverter u32
        # • grid_power_w:       meter s32 (32-bit range) ← preferred over s16
        #
        # Fallback to Block A values when Block B is unavailable.
        meter_exp = data.get("meter_export_total_kwh")
        meter_imp = data.get("meter_import_total_kwh")
        meter_pw  = data.get("meter_power_total_w")

        if meter_exp is not None:
            data["grid_export_total_kwh"] = meter_exp
        if meter_imp is not None:
            data["grid_import_total_kwh"] = meter_imp
        if meter_pw is not None:
            # Re-apply the same 30 W deadband used for Block A grid power
            # to suppress sub-threshold noise when the grid exchange is near zero.
            data["grid_power_w"] = 0.0 if abs(meter_pw) < 30 else meter_pw

        # ── Per-cycle debug logging ───────────────────────────────────────────
        _LOGGER.debug(
            "GoodWe cycle — "
            "PV: %s W | Bat: %s W | Grid: %s W | "
            "GridExp: %s kWh | GridImp: %s kWh | "
            "BatChg: %s kWh | BatDis: %s kWh | "
            "MeterExp: %s kWh | MeterImp: %s kWh",
            data.get("pv_power_w"),
            data.get("battery_power_w"),
            data.get("grid_power_w"),
            data.get("grid_export_total_kwh"),
            data.get("grid_import_total_kwh"),
            data.get("battery_charge_total_kwh"),
            data.get("battery_discharge_total_kwh"),
            data.get("meter_export_total_kwh"),
            data.get("meter_import_total_kwh"),
        )

        return data
