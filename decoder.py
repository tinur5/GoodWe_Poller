"""
decoder.py – Convert raw register values to human-readable physical quantities.

All raw values are produced by ModbusReader.read_raw().
The decoded dict uses SI units:
  _w   → Watts
  _v   → Volts
  _hz  → Hertz
  _kwh → kWh
  _pct → %
  _c   → °C
"""

from __future__ import annotations

import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)

# Maximum credible values (anything beyond is treated as garbage)
_MAX_PV_POWER_W       = 30_000   # 30 kW per inverter
_MAX_BATTERY_POWER_W  = 20_000
_MAX_GRID_POWER_W     = 30_000
_MAX_LOAD_POWER_W     = 30_000
_MAX_ENERGY_KWH       = 999_999  # ~1 GWh lifetime


def _scale(value: int, factor: float, max_abs: Optional[float] = None) -> Optional[float]:
    """Apply scale factor and optional sanity clamp. Returns None on bad value."""
    result = value * factor
    if max_abs is not None and abs(result) > max_abs:
        logger.debug("Value %s (raw=%s, ×%s) exceeds max=%s – discarded",
                     result, value, factor, max_abs)
        return None
    return result


def decode(raw: dict) -> Optional[dict]:
    """
    Decode a raw register dict (from ModbusReader.read_raw) into physical values.
    Returns None if the raw data is empty or None.
    """
    if not raw:
        return None

    ppv1 = _scale(raw["ppv1_w"],   1.0, _MAX_PV_POWER_W)
    ppv2 = _scale(raw["ppv2_w"],   1.0, _MAX_PV_POWER_W)
    ppv3 = _scale(raw["ppv3_w"],   1.0, _MAX_PV_POWER_W)
    ppv4 = _scale(raw["ppv4_w"],   1.0, _MAX_PV_POWER_W)

    decoded = {
        # ── PV ──────────────────────────────────────────────────────────────
        "pv1_voltage_v":       _scale(raw["vpv1_dv"],  0.1),
        "pv1_current_a":       _scale(raw["ipv1_da"],  0.1),
        "pv1_power_w":         ppv1,
        "pv2_voltage_v":       _scale(raw["vpv2_dv"],  0.1),
        "pv2_current_a":       _scale(raw["ipv2_da"],  0.1),
        "pv2_power_w":         ppv2,
        "pv3_voltage_v":       _scale(raw["vpv3_dv"],  0.1),
        "pv3_current_a":       _scale(raw["ipv3_da"],  0.1),
        "pv3_power_w":         ppv3,
        "pv4_voltage_v":       _scale(raw["vpv4_dv"],  0.1),
        "pv4_current_a":       _scale(raw["ipv4_da"],  0.1),
        "pv4_power_w":         ppv4,
        # PV total power (sum of valid strings)
        "pv_power_w": sum(
            p for p in (ppv1, ppv2, ppv3, ppv4) if p is not None
        ),
        # ── Grid ────────────────────────────────────────────────────────────
        "grid_voltage_v":      _scale(raw["vgrid_r_dv"], 0.1),
        "grid_frequency_hz":   _scale(raw["fgrid_r_cHz"], 0.01),
        "grid_power_r_w":      _scale(raw["pgrid_r_w"],   1.0, _MAX_GRID_POWER_W),
        "grid_power_s_w":      _scale(raw["pgrid_s_w"],   1.0, _MAX_GRID_POWER_W),
        "grid_power_t_w":      _scale(raw["pgrid_t_w"],   1.0, _MAX_GRID_POWER_W),
        "grid_power_w":        _scale(raw["pgrid_total_w"], 1.0, _MAX_GRID_POWER_W),
        # ── Battery ─────────────────────────────────────────────────────────
        "battery_power_w":     _scale(raw["pbattery_w"],  1.0, _MAX_BATTERY_POWER_W),
        "battery_soc_pct":     raw["soc_pct"],
        # ── Load ────────────────────────────────────────────────────────────
        "load_power_w":        _scale(raw["pload_w"],     1.0, _MAX_LOAD_POWER_W),
        # ── Temperature ─────────────────────────────────────────────────────
        "inverter_temp_c":     _scale(raw["temp_dc"],     0.1),
        # ── Energy (today) ──────────────────────────────────────────────────
        "pv_energy_today_kwh":       _scale(raw["e_day_pv_dk"],       0.1, _MAX_ENERGY_KWH),
        "battery_charge_today_kwh":  _scale(raw["e_day_charge_dk"],   0.1, _MAX_ENERGY_KWH),
        "battery_discharge_today_kwh": _scale(raw["e_day_discharge_dk"], 0.1, _MAX_ENERGY_KWH),
        # ── Energy (total lifetime) ──────────────────────────────────────────
        "pv_energy_total_kwh":       _scale(raw["e_total_pv_dk"],      0.1, _MAX_ENERGY_KWH),
        "grid_export_total_kwh":     _scale(raw["e_total_export_dk"],   0.1, _MAX_ENERGY_KWH),
        "grid_import_total_kwh":     _scale(raw["e_total_import_dk"],   0.1, _MAX_ENERGY_KWH),
        # ── Meta ────────────────────────────────────────────────────────────
        "work_mode": raw["work_mode"],
    }

    if config.DEBUG_DECODE:
        logger.debug("decoded: %s", decoded)

    return decoded
