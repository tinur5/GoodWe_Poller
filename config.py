"""
config.py – Load configuration from environment / .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _get_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")


# ── MQTT ──────────────────────────────────────────────────────────────────────
MQTT_HOST: str = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME: str = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD: str = os.getenv("MQTT_PASSWORD", "")

# ── Inverter hosts ─────────────────────────────────────────────────────────────
MASTER_HOST: str = os.getenv("MASTER_HOST", "192.168.1.10")
SLAVE_HOST: str = os.getenv("SLAVE_HOST", "")          # empty → single-inverter mode

# ── Modbus ─────────────────────────────────────────────────────────────────────
MODBUS_PORT: int = int(os.getenv("MODBUS_PORT", "502"))
MODBUS_UNIT_ID: int = int(os.getenv("MODBUS_UNIT_ID", "247"))

# ── Polling ────────────────────────────────────────────────────────────────────
POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", "10"))

# ── MQTT topic ─────────────────────────────────────────────────────────────────
BASE_TOPIC: str = os.getenv("BASE_TOPIC", "goodwe_direct")

# ── Debug flags ────────────────────────────────────────────────────────────────
DEBUG_MODBUS: bool = _get_bool("DEBUG_MODBUS", False)
DEBUG_DECODE: bool = _get_bool("DEBUG_DECODE", False)
DEBUG_COMBINE: bool = _get_bool("DEBUG_COMBINE", False)
