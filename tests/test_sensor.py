"""
Tests for GoodWeSensor (sensor.py).

Verifies:
  • native_value returns the coordinator data value
  • None coordinator data returns None
  • Floats are rounded to one decimal place
  • Unique ID construction
  • Integer values passed through unchanged
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# HA stubs installed by conftest.py

from unittest.mock import MagicMock

from custom_components.goodwe_modbus.sensor import GoodWeSensor
from custom_components.goodwe_modbus.const import (
    DOMAIN,
    GoodWeSensorEntityDescription,
    SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS_METER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_description(key="pv_power_w"):
    for desc in SENSOR_DESCRIPTIONS + SENSOR_DESCRIPTIONS_METER:
        if desc.key == key:
            return desc
    # Fallback: build a minimal one
    return GoodWeSensorEntityDescription(key=key, name="Test Sensor")


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data
    return coord


def _make_entry(entry_id="entry_abc"):
    entry = MagicMock()
    entry.entry_id = entry_id
    return entry


def _make_device():
    from homeassistant.helpers.device_registry import DeviceInfo
    return DeviceInfo(identifiers={(DOMAIN, "entry_abc")}, name="GoodWe Test")


def _make_sensor(key="pv_power_w", data=None, entry_id="entry_abc"):
    coordinator = _make_coordinator(data)
    entry = _make_entry(entry_id)
    description = _make_description(key)
    device = _make_device()
    return GoodWeSensor(coordinator, entry, description, device)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGoodWeSensorNativeValue:
    def test_none_when_coordinator_data_is_none(self):
        sensor = _make_sensor(data=None)
        assert sensor.native_value is None

    def test_none_when_key_missing_from_data(self):
        sensor = _make_sensor(key="pv_power_w", data={"battery_soc_pct": 80})
        assert sensor.native_value is None

    def test_none_when_value_is_none(self):
        sensor = _make_sensor(key="pv_power_w", data={"pv_power_w": None})
        assert sensor.native_value is None

    def test_integer_returned_unchanged(self):
        sensor = _make_sensor(key="pv_power_w", data={"pv_power_w": 1500})
        assert sensor.native_value == 1500

    def test_float_rounded_to_one_decimal(self):
        sensor = _make_sensor(key="pv_power_w", data={"pv_power_w": 1500.456})
        assert sensor.native_value == 1500.5

    def test_float_already_clean_unchanged(self):
        sensor = _make_sensor(key="pv_power_w", data={"pv_power_w": 1500.0})
        assert sensor.native_value == 1500.0

    def test_zero_value_returned(self):
        sensor = _make_sensor(key="grid_power_w", data={"grid_power_w": 0.0})
        assert sensor.native_value == 0.0

    def test_negative_float_rounded(self):
        sensor = _make_sensor(key="grid_power_w", data={"grid_power_w": -123.456})
        assert sensor.native_value == -123.5

    def test_soc_integer(self):
        sensor = _make_sensor(key="battery_soc_pct", data={"battery_soc_pct": 75})
        assert sensor.native_value == 75

    def test_energy_value_rounded(self):
        sensor = _make_sensor(
            key="pv_energy_total_kwh",
            data={"pv_energy_total_kwh": 10000.123456},
        )
        assert sensor.native_value == 10000.1

    def test_meter_export_value(self):
        sensor = _make_sensor(
            key="meter_export_total_kwh",
            data={"meter_export_total_kwh": 3500.75},
        )
        assert sensor.native_value == 3500.8


class TestGoodWeSensorUniqueId:
    def test_unique_id_format(self):
        sensor = _make_sensor(key="pv_power_w", entry_id="abc123")
        assert sensor._attr_unique_id == "abc123_pv_power_w"

    def test_unique_id_different_keys(self):
        s1 = _make_sensor(key="pv_power_w", entry_id="xyz")
        s2 = _make_sensor(key="battery_soc_pct", entry_id="xyz")
        assert s1._attr_unique_id != s2._attr_unique_id

    def test_unique_id_different_entries(self):
        s1 = _make_sensor(key="pv_power_w", entry_id="entry1")
        s2 = _make_sensor(key="pv_power_w", entry_id="entry2")
        assert s1._attr_unique_id != s2._attr_unique_id


class TestGoodWeSensorDescriptions:
    """Sanity checks on the sensor description metadata."""

    def test_all_inverter_sensor_keys_unique(self):
        keys = [d.key for d in SENSOR_DESCRIPTIONS]
        assert len(keys) == len(set(keys)), "Duplicate sensor description keys found"

    def test_all_meter_sensor_keys_unique(self):
        keys = [d.key for d in SENSOR_DESCRIPTIONS_METER]
        assert len(keys) == len(set(keys)), "Duplicate meter sensor description keys found"

    def test_no_overlap_between_inverter_and_meter_keys(self):
        inv_keys = {d.key for d in SENSOR_DESCRIPTIONS}
        meter_keys = {d.key for d in SENSOR_DESCRIPTIONS_METER}
        overlap = inv_keys & meter_keys
        assert not overlap, f"Overlapping sensor keys: {overlap}"

    def test_inverter_sensors_have_name(self):
        for d in SENSOR_DESCRIPTIONS:
            assert d.name, f"Sensor {d.key!r} has no name"

    def test_meter_sensors_have_name(self):
        for d in SENSOR_DESCRIPTIONS_METER:
            assert d.name, f"Meter sensor {d.key!r} has no name"
