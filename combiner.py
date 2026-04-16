"""
combiner.py – Merge decoded data from master and (optional) slave inverter,
apply spike filters, and produce a single aggregated metrics dict.

Aggregation rules
-----------------
Power values  → sum of master + slave
SOC           → average of master + slave (or just master if no slave)
Temperature   → maximum of master + slave
Voltage/freq  → taken from master only
Energy        → sum of master + slave (after monotonic guard per inverter)
"""

from __future__ import annotations

import logging
from typing import Optional

from filter import SpikeFilter, DeadbandFilter, MonotonicGuard

import config

logger = logging.getLogger(__name__)

# Keys that are *summed* across inverters
_SUM_KEYS = {
    "pv_power_w",
    "pv1_power_w", "pv2_power_w", "pv3_power_w", "pv4_power_w",
    "battery_power_w",
    "grid_power_w",
    "grid_power_r_w", "grid_power_s_w", "grid_power_t_w",
    "load_power_w",
    "pv_energy_today_kwh",
    "pv_energy_total_kwh",
    "battery_charge_today_kwh",
    "battery_discharge_today_kwh",
    "grid_export_total_kwh",
    "grid_import_total_kwh",
}

# Keys taken only from master
_MASTER_ONLY_KEYS = {
    "grid_voltage_v",
    "grid_frequency_hz",
    "work_mode",
}


def _safe_add(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None and b is None:
        return None
    return (a or 0.0) + (b or 0.0)


def _safe_avg(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2.0


def _safe_max(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


class Combiner:
    """
    Combines one or two decoded inverter dicts and applies output filters.
    """

    def __init__(self) -> None:
        # Output-side spike filters (applied to combined totals)
        self._spike_pv       = SpikeFilter(window=5, max_delta=10_000, name="total_pv")
        self._spike_bat      = SpikeFilter(window=5, max_delta=8_000,  name="total_bat")
        self._spike_grid     = SpikeFilter(window=5, max_delta=10_000, name="total_grid")
        self._spike_load     = SpikeFilter(window=5, max_delta=10_000, name="total_load")
        self._deadband_grid  = DeadbandFilter(threshold=30.0, name="total_grid")
        # Per-inverter monotonic energy guards
        self._mono: dict[str, dict[str, MonotonicGuard]] = {
            "master": _build_mono_guards("master"),
            "slave":  _build_mono_guards("slave"),
        }

    def combine(self,
                master: Optional[dict],
                slave: Optional[dict] = None) -> Optional[dict]:
        """
        Combine master and optional slave decoded dicts.
        Returns a single aggregated dict, or None if both inputs are None.
        """
        if master is None and slave is None:
            return None

        # Apply per-inverter monotonic guards to energy counters
        if master:
            master = _apply_mono(master, self._mono["master"])
        if slave:
            slave = _apply_mono(slave, self._mono["slave"])

        combined = _merge(master, slave)

        if config.DEBUG_COMBINE:
            logger.debug("combined (pre-filter): %s", combined)

        # Apply output spike filters
        combined["pv_power_w"]      = self._spike_pv.update(combined.get("pv_power_w"))
        combined["battery_power_w"] = self._spike_bat.update(combined.get("battery_power_w"))
        grid_raw = self._spike_grid.update(combined.get("grid_power_w"))
        combined["grid_power_w"]    = self._deadband_grid.update(grid_raw)
        combined["load_power_w"]    = self._spike_load.update(combined.get("load_power_w"))

        return combined


def _build_mono_guards(label: str) -> dict[str, MonotonicGuard]:
    return {
        key: MonotonicGuard(name=f"{label}/{key}")
        for key in (
            "pv_energy_total_kwh",
            "grid_export_total_kwh",
            "grid_import_total_kwh",
        )
    }


def _apply_mono(data: dict, guards: dict[str, MonotonicGuard]) -> dict:
    out = dict(data)
    for key, guard in guards.items():
        if key in out:
            out[key] = guard.update(out[key])
    return out


def _merge(master: Optional[dict], slave: Optional[dict]) -> dict:
    """Merge two decoded dicts according to aggregation rules."""
    # Use whichever is available as base
    base = master if master is not None else slave
    other = slave if master is not None else None

    out: dict = {}
    for key in base:
        m_val = master.get(key) if master else None
        s_val = slave.get(key)  if slave  else None

        if key in _MASTER_ONLY_KEYS:
            out[key] = m_val
        elif key == "battery_soc_pct":
            out[key] = _safe_avg(m_val, s_val)
        elif key == "inverter_temp_c":
            out[key] = _safe_max(m_val, s_val)
        elif key in _SUM_KEYS:
            out[key] = _safe_add(m_val, s_val)
        else:
            out[key] = m_val  # fallback: master wins

    return out
