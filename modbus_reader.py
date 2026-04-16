"""
modbus_reader.py – Reads raw Modbus TCP registers from a GoodWe inverter.

Register blocks used
--------------------
Block A  35100 – 35199  (inverter runtime: PV, battery, grid, load)
Block B  36000 – 36049  (ARM external meter: grid import/export energy)

All addresses are *Modbus holding-register* addresses (function code 0x03).
The unit ID defaults to 247 (0xF7) which is the GoodWe broadcast address.
"""

from __future__ import annotations

import logging
from typing import Optional

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

import config

logger = logging.getLogger(__name__)

# ── Register map ──────────────────────────────────────────────────────────────
BLOCK_A_START = 35100
BLOCK_A_COUNT = 100          # covers all runtime registers up to 35199

BLOCK_B_START = 36000
BLOCK_B_COUNT = 50           # covers ARM meter registers up to 36049

# Offsets within Block A (relative to 35100)
_A = {
    "vpv1":          3,   # PV1 voltage          ×0.1 V
    "ipv1":          4,   # PV1 current          ×0.1 A
    "ppv1":          5,   # PV1 power            W
    "vpv2":          6,   # PV2 voltage          ×0.1 V
    "ipv2":          7,   # PV2 current          ×0.1 A
    "ppv2":          8,   # PV2 power            W
    "vpv3":          9,   # PV3 voltage          ×0.1 V
    "ipv3":         10,   # PV3 current          ×0.1 A
    "ppv3":         11,   # PV3 power            W
    "vpv4":         12,   # PV4 voltage          ×0.1 V
    "ipv4":         13,   # PV4 current          ×0.1 A
    "ppv4":         14,   # PV4 power            W
    "vgrid_r":      16,   # Grid phase R voltage ×0.1 V
    "igrid_r":      17,   # Grid phase R current ×0.1 A
    "fgrid_r":      18,   # Grid phase R freq    ×0.01 Hz
    "pgrid_r":      19,   # Grid phase R power   W  (signed)
    "vgrid_s":      20,
    "igrid_s":      21,
    "fgrid_s":      22,
    "pgrid_s":      23,
    "vgrid_t":      24,
    "igrid_t":      25,
    "fgrid_t":      26,
    "pgrid_t":      27,
    "pgrid_total":  28,   # Total grid power     W  (signed, + = export)
    "work_mode":    37,   # Work mode code
    "pbattery":     40,   # Battery power        W  (signed, + = charging)
    "soc":          41,   # Battery SOC          %
    "temperature":  54,   # Inverter temperature ×0.1 °C
    "pload":        47,   # Load power           W
    "e_day_pv":     56,   # Today PV energy      ×0.1 kWh  (32-bit, hi+lo)
    "e_total_pv":   60,   # Total PV energy      ×0.1 kWh  (32-bit, hi+lo)
    "e_day_charge": 70,   # Today battery charge ×0.1 kWh  (32-bit, hi+lo)
    "e_day_discharge": 74, # Today battery disch ×0.1 kWh  (32-bit, hi+lo)
}

# Offsets within Block B (relative to 36000)
_B = {
    "e_total_export_hi": 15,   # Grid total export energy hi word  ×0.1 kWh
    "e_total_export_lo": 16,   # Grid total export energy lo word
    "e_total_import_hi": 17,   # Grid total import energy hi word  ×0.1 kWh
    "e_total_import_lo": 18,   # Grid total import energy lo word
}


def _to_signed16(value: int) -> int:
    """Convert unsigned 16-bit register value to signed integer."""
    return value if value < 0x8000 else value - 0x10000


def _to_u32(hi: int, lo: int) -> int:
    """Combine two 16-bit words into one unsigned 32-bit integer."""
    return (hi << 16) | lo


class ModbusReader:
    """Reads one GoodWe inverter via Modbus TCP."""

    def __init__(self, host: str, port: int = config.MODBUS_PORT,
                 unit_id: int = config.MODBUS_UNIT_ID) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self._client: Optional[ModbusTcpClient] = None

    # ── Connection lifecycle ──────────────────────────────────────────────────

    def connect(self) -> bool:
        self._client = ModbusTcpClient(host=self.host, port=self.port,
                                       timeout=5)
        if not self._client.connect():
            logger.error("Cannot connect to %s:%s", self.host, self.port)
            return False
        logger.info("Connected to inverter @ %s:%s", self.host, self.port)
        return True

    def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def is_connected(self) -> bool:
        return bool(self._client and self._client.connected)

    # ── Raw register reads ────────────────────────────────────────────────────

    def _read_registers(self, start: int, count: int) -> Optional[list[int]]:
        if not self.is_connected():
            if not self.connect():
                return None
        try:
            result = self._client.read_holding_registers(
                address=start, count=count, slave=self.unit_id)
            if result.isError():
                logger.warning("Modbus error reading %s+%s: %s",
                               start, count, result)
                return None
            if config.DEBUG_MODBUS:
                logger.debug("[%s] reg %s: %s",
                             self.host, start, result.registers)
            return result.registers
        except ModbusException as exc:
            logger.error("ModbusException @ %s: %s", self.host, exc)
            self.disconnect()
            return None

    # ── Public API ────────────────────────────────────────────────────────────

    def read_raw(self) -> Optional[dict]:
        """
        Return a dict of decoded raw values for this inverter.
        Returns None if the read fails.
        """
        regs_a = self._read_registers(BLOCK_A_START, BLOCK_A_COUNT)
        regs_b = self._read_registers(BLOCK_B_START, BLOCK_B_COUNT)

        if regs_a is None:
            return None

        def ra(key: str) -> int:
            return regs_a[_A[key]]

        def rb(key: str) -> int:
            return regs_b[_B[key]] if regs_b else 0

        raw = {
            # PV
            "vpv1_dv":     ra("vpv1"),
            "ipv1_da":     ra("ipv1"),
            "ppv1_w":      ra("ppv1"),
            "vpv2_dv":     ra("vpv2"),
            "ipv2_da":     ra("ipv2"),
            "ppv2_w":      ra("ppv2"),
            "vpv3_dv":     ra("vpv3"),
            "ipv3_da":     ra("ipv3"),
            "ppv3_w":      ra("ppv3"),
            "vpv4_dv":     ra("vpv4"),
            "ipv4_da":     ra("ipv4"),
            "ppv4_w":      ra("ppv4"),
            # Grid
            "pgrid_r_w":   _to_signed16(ra("pgrid_r")),
            "pgrid_s_w":   _to_signed16(ra("pgrid_s")),
            "pgrid_t_w":   _to_signed16(ra("pgrid_t")),
            "pgrid_total_w": _to_signed16(ra("pgrid_total")),
            "vgrid_r_dv":  ra("vgrid_r"),
            "fgrid_r_cHz": ra("fgrid_r"),
            # Battery
            "pbattery_w":  _to_signed16(ra("pbattery")),
            "soc_pct":     ra("soc"),
            # Load
            "pload_w":     ra("pload"),
            # Temperature
            "temp_dc":     ra("temperature"),
            # Today energy (×0.1 kWh)
            "e_day_pv_dk":      _to_u32(ra("e_day_pv"), regs_a[_A["e_day_pv"] + 1]),
            "e_total_pv_dk":    _to_u32(ra("e_total_pv"), regs_a[_A["e_total_pv"] + 1]),
            "e_day_charge_dk":  _to_u32(ra("e_day_charge"), regs_a[_A["e_day_charge"] + 1]),
            "e_day_discharge_dk": _to_u32(ra("e_day_discharge"),
                                          regs_a[_A["e_day_discharge"] + 1]),
            # Grid energy from ARM meter (×0.1 kWh)
            "e_total_export_dk": _to_u32(rb("e_total_export_hi"),
                                          rb("e_total_export_lo")),
            "e_total_import_dk": _to_u32(rb("e_total_import_hi"),
                                          rb("e_total_import_lo")),
            # Meta
            "work_mode":   ra("work_mode"),
        }

        if config.DEBUG_DECODE:
            logger.debug("[%s] raw: %s", self.host, raw)

        return raw
