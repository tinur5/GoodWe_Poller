"""
coordinator.py – DataUpdateCoordinator for GoodWe Modbus.

Reads Modbus registers from master (and optional slave) inverter, decodes and
filters the data, and makes the combined result available to sensor entities.

The synchronous pymodbus calls are offloaded to the HA executor thread pool so
they never block the event loop.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import timedelta
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_MASTER_HOST,
    CONF_SLAVE_HOST,
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
_BLOCK_B_COUNT = 50

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
    "e_total_export_hi": 15, "e_total_export_lo": 16,
    "e_total_import_hi": 17, "e_total_import_lo": 18,
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

    ppv1 = _clamp(float(a[_A["ppv1"]]), _MAX_PV_W)
    ppv2 = _clamp(float(a[_A["ppv2"]]), _MAX_PV_W)
    ppv3 = _clamp(float(a[_A["ppv3"]]), _MAX_PV_W)
    ppv4 = _clamp(float(a[_A["ppv4"]]), _MAX_PV_W)
    pv_total = sum(p for p in (ppv1, ppv2, ppv3, ppv4) if p is not None)

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
    """Fetches and filters data from one or two GoodWe inverters."""

    def __init__(self, hass: HomeAssistant, entry_data: dict) -> None:
        self._master_host = entry_data[CONF_MASTER_HOST]
        self._slave_host  = entry_data.get(CONF_SLAVE_HOST, "")
        self._port        = entry_data.get(CONF_MODBUS_PORT, DEFAULT_PORT)
        self._unit_id     = entry_data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)
        interval          = entry_data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

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

        # Per-inverter monotonic energy guards
        self._mono_m = {k: _MonotonicGuard() for k in (
            "pv_energy_total_kwh", "grid_export_total_kwh", "grid_import_total_kwh")}
        self._mono_s = {k: _MonotonicGuard() for k in (
            "pv_energy_total_kwh", "grid_export_total_kwh", "grid_import_total_kwh")}

    async def _async_update_data(self) -> dict:
        master = await self.hass.async_add_executor_job(
            _read_inverter, self._master_host, self._port, self._unit_id
        )

        slave: Optional[dict] = None
        if self._slave_host:
            slave = await self.hass.async_add_executor_job(
                _read_inverter, self._slave_host, self._port, self._unit_id
            )

        if master is None and slave is None:
            raise UpdateFailed("No data received from any inverter")

        # Apply monotonic guards per inverter before summing
        if master:
            for key, guard in self._mono_m.items():
                master[key] = guard(master.get(key))
        if slave:
            for key, guard in self._mono_s.items():
                slave[key] = guard(slave.get(key))

        combined = _combine(master, slave)

        # Apply output spike filters
        combined["pv_power_w"]      = self._sf_pv(combined.get("pv_power_w"))
        combined["battery_power_w"] = self._sf_bat(combined.get("battery_power_w"))
        grid = self._sf_grid(combined.get("grid_power_w"))
        combined["grid_power_w"]    = 0.0 if grid is not None and abs(grid) < 30 else grid
        combined["load_power_w"]    = self._sf_load(combined.get("load_power_w"))

        return combined


# ── Merge master + slave ──────────────────────────────────────────────────────

_SUM_KEYS = frozenset({
    "pv_power_w",
    "pv1_power_w", "pv2_power_w", "pv3_power_w", "pv4_power_w",
    "battery_power_w",
    "grid_power_w", "grid_power_r_w", "grid_power_s_w", "grid_power_t_w",
    "load_power_w",
    "pv_energy_today_kwh", "pv_energy_total_kwh",
    "battery_charge_today_kwh", "battery_discharge_today_kwh",
    "grid_export_total_kwh", "grid_import_total_kwh",
})


def _add(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None and b is None:
        return None
    return (a or 0.0) + (b or 0.0)


def _avg(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2.0


def _combine(master: Optional[dict], slave: Optional[dict]) -> dict:
    base = master if master is not None else slave
    out: dict = {}
    for key in base:
        mv = master.get(key) if master else None
        sv = slave.get(key)  if slave  else None
        if key in _SUM_KEYS:
            out[key] = _add(mv, sv)
        elif key == "battery_soc_pct":
            out[key] = _avg(mv, sv)
        elif key == "inverter_temp_c":
            if mv is not None and sv is not None:
                out[key] = max(mv, sv)
            else:
                out[key] = mv if mv is not None else sv
        else:
            out[key] = mv  # master wins (voltage, frequency, work_mode)
    return out
