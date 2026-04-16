"""
main.py – GoodWe Modbus Poller main entry point.

Reads inverter data via Modbus TCP, combines master + slave (if configured),
applies spike/deadband filters, and publishes cleaned metrics to MQTT.

Usage
-----
    python main.py

Configuration is loaded from a .env file (see .env.example).
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Optional

import config
from combiner import Combiner
from decoder import decode
from modbus_reader import ModbusReader
from mqtt_publisher import MqttPublisher

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if (config.DEBUG_MODBUS or config.DEBUG_DECODE) else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("main")


# ── Graceful shutdown ─────────────────────────────────────────────────────────
_running = True


def _signal_handler(signum, frame):
    global _running
    logger.info("Signal %s received – shutting down …", signum)
    _running = False


signal.signal(signal.SIGINT,  _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("GoodWe Poller starting …")
    logger.info("Master: %s   Slave: %s",
                config.MASTER_HOST, config.SLAVE_HOST or "—")
    logger.info("Poll interval: %ss   MQTT: %s:%s   Topic: %s",
                config.POLL_INTERVAL, config.MQTT_HOST, config.MQTT_PORT,
                config.BASE_TOPIC)

    # Inverter readers
    master_reader = ModbusReader(config.MASTER_HOST)
    slave_reader: Optional[ModbusReader] = (
        ModbusReader(config.SLAVE_HOST) if config.SLAVE_HOST else None
    )

    # MQTT
    publisher = MqttPublisher()
    if not publisher.connect():
        logger.error("Could not connect to MQTT broker – aborting.")
        sys.exit(1)

    combiner = Combiner()

    while _running:
        cycle_start = time.monotonic()

        # ── Read ─────────────────────────────────────────────────────────────
        master_raw  = master_reader.read_raw()
        master_data = decode(master_raw)

        slave_data: Optional[dict] = None
        if slave_reader:
            slave_raw  = slave_reader.read_raw()
            slave_data = decode(slave_raw)

        if master_data is None and slave_data is None:
            logger.warning("No data from any inverter – skipping publish")
        else:
            # ── Combine & filter ─────────────────────────────────────────────
            combined = combiner.combine(master_data, slave_data)

            # ── Publish ──────────────────────────────────────────────────────
            publisher.publish(combined)

            if config.DEBUG_COMBINE:
                logger.debug("published: %s", combined)

        # ── Wait for next poll ────────────────────────────────────────────────
        elapsed = time.monotonic() - cycle_start
        sleep_time = max(0.0, config.POLL_INTERVAL - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    master_reader.disconnect()
    if slave_reader:
        slave_reader.disconnect()
    publisher.disconnect()
    logger.info("GoodWe Poller stopped.")


if __name__ == "__main__":
    main()
