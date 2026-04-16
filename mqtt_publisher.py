"""
mqtt_publisher.py – Publish GoodWe metrics to MQTT.

Topic layout
------------
{BASE_TOPIC}/total/decoded/{metric_key}

Example:
  goodwe_direct/total/decoded/pv_power_w  → "3450.0"

Each metric is published as a separate retained message with a plain-text float
(or integer) payload so that Home Assistant MQTT sensors can subscribe directly.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import paho.mqtt.client as mqtt

import config

logger = logging.getLogger(__name__)

_RETAIN = True
_QOS    = 0


class MqttPublisher:
    """Thin wrapper around paho-mqtt for publishing decoded inverter metrics."""

    def __init__(self) -> None:
        self._client = mqtt.Client(client_id="goodwe_poller", clean_session=True)
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._connected = False

        if config.MQTT_USERNAME:
            self._client.username_pw_set(config.MQTT_USERNAME,
                                          config.MQTT_PASSWORD)

    # ── MQTT callbacks ────────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            logger.info("MQTT connected to %s:%s", config.MQTT_HOST, config.MQTT_PORT)
        else:
            logger.error("MQTT connect failed (rc=%s)", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            logger.warning("MQTT unexpectedly disconnected (rc=%s)", rc)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        try:
            self._client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=60)
            self._client.loop_start()
            # Give the broker a moment to complete the handshake
            import time; time.sleep(0.5)
            return self._connected
        except OSError as exc:
            logger.error("Cannot connect to MQTT broker: %s", exc)
            return False

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    # ── Publishing ────────────────────────────────────────────────────────────

    def publish(self, metrics: Optional[dict]) -> None:
        """Publish every key in *metrics* to its own MQTT topic."""
        if not metrics:
            return
        if not self._connected:
            logger.warning("MQTT not connected – skipping publish")
            return

        base = f"{config.BASE_TOPIC}/total/decoded"
        for key, value in metrics.items():
            if value is None:
                continue
            topic = f"{base}/{key}"
            payload = _format_payload(value)
            self._client.publish(topic, payload, qos=_QOS, retain=_RETAIN)

        logger.debug("Published %d metrics to %s/…", len(metrics), base)


def _format_payload(value) -> str:
    """Render a value as a clean string payload."""
    if isinstance(value, float):
        # Strip unnecessary trailing zeros but keep at least one decimal
        return f"{value:.1f}"
    return str(value)
