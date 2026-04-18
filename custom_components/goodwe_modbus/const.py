"""Constants and sensor descriptions for the GoodWe Modbus integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    PERCENTAGE,
)

DOMAIN = "goodwe_modbus"

# ── Config-entry keys ──────────────────────────────────────────────────────────
CONF_HOST          = "host"
CONF_MODBUS_PORT   = "modbus_port"
CONF_UNIT_ID       = "unit_id"
CONF_SCAN_INTERVAL = "scan_interval"

# ── Defaults ───────────────────────────────────────────────────────────────────
DEFAULT_PORT          = 502
DEFAULT_UNIT_ID       = 247
DEFAULT_SCAN_INTERVAL = 10   # seconds


# ── Sensor descriptions ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GoodWeSensorEntityDescription(SensorEntityDescription):
    """Extended sensor description (placeholder for future per-sensor options)."""


# ── Inverter sensors ──────────────────────────────────────────────────────────

SENSOR_DESCRIPTIONS: tuple[GoodWeSensorEntityDescription, ...] = (
    # ── PV power ──────────────────────────────────────────────────────────────
    GoodWeSensorEntityDescription(
        key="pv_power_w",
        name="PV Power Total",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power",
    ),
    GoodWeSensorEntityDescription(
        key="pv1_power_w",
        name="PV1 Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-panel",
    ),
    GoodWeSensorEntityDescription(
        key="pv2_power_w",
        name="PV2 Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-panel",
    ),
    GoodWeSensorEntityDescription(
        key="pv3_power_w",
        name="PV3 Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-panel",
    ),
    GoodWeSensorEntityDescription(
        key="pv4_power_w",
        name="PV4 Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-panel",
    ),
    # ── PV voltage / current ──────────────────────────────────────────────────
    GoodWeSensorEntityDescription(
        key="pv1_voltage_v",
        name="PV1 Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    GoodWeSensorEntityDescription(
        key="pv1_current_a",
        name="PV1 Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    GoodWeSensorEntityDescription(
        key="pv2_voltage_v",
        name="PV2 Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    GoodWeSensorEntityDescription(
        key="pv2_current_a",
        name="PV2 Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    GoodWeSensorEntityDescription(
        key="pv3_voltage_v",
        name="PV3 Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    GoodWeSensorEntityDescription(
        key="pv3_current_a",
        name="PV3 Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    GoodWeSensorEntityDescription(
        key="pv4_voltage_v",
        name="PV4 Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    GoodWeSensorEntityDescription(
        key="pv4_current_a",
        name="PV4 Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # ── Battery ───────────────────────────────────────────────────────────────
    GoodWeSensorEntityDescription(
        key="battery_power_w",
        name="Battery Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging",
    ),
    GoodWeSensorEntityDescription(
        key="battery_soc_pct",
        name="Battery SOC",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GoodWeSensorEntityDescription(
        key="battery_charge_today_kwh",
        name="Battery Charged Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:battery-plus",
    ),
    GoodWeSensorEntityDescription(
        key="battery_discharge_today_kwh",
        name="Battery Discharged Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:battery-minus",
    ),
    # ── Grid ──────────────────────────────────────────────────────────────────
    GoodWeSensorEntityDescription(
        key="grid_power_w",
        name="Grid Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower",
    ),
    GoodWeSensorEntityDescription(
        key="grid_voltage_v",
        name="Grid Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    GoodWeSensorEntityDescription(
        key="grid_frequency_hz",
        name="Grid Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    GoodWeSensorEntityDescription(
        key="grid_export_total_kwh",
        name="Grid Export Total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:transmission-tower-export",
    ),
    GoodWeSensorEntityDescription(
        key="grid_import_total_kwh",
        name="Grid Import Total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:transmission-tower-import",
    ),
    # ── Load ──────────────────────────────────────────────────────────────────
    GoodWeSensorEntityDescription(
        key="load_power_w",
        name="Load Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-lightning-bolt",
    ),
    # ── PV energy ─────────────────────────────────────────────────────────────
    GoodWeSensorEntityDescription(
        key="pv_energy_today_kwh",
        name="PV Energy Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:solar-power-variant",
    ),
    GoodWeSensorEntityDescription(
        key="pv_energy_total_kwh",
        name="PV Energy Total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:solar-power-variant-outline",
    ),
    # ── Temperature ───────────────────────────────────────────────────────────
    GoodWeSensorEntityDescription(
        key="inverter_temp_c",
        name="Inverter Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

# ── External CT meter sensors (enabled by default) ──────────────────────────

SENSOR_DESCRIPTIONS_METER: tuple[GoodWeSensorEntityDescription, ...] = (
    # Active power – compact int16 readings (fast update, lower range)
    GoodWeSensorEntityDescription(
        key="meter_power_w",
        name="Meter Active Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:meter-electric",
    ),
    GoodWeSensorEntityDescription(
        key="meter_power_r_w",
        name="Meter Active Power L1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:meter-electric-outline",
    ),
    GoodWeSensorEntityDescription(
        key="meter_power_s_w",
        name="Meter Active Power L2",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:meter-electric-outline",
    ),
    GoodWeSensorEntityDescription(
        key="meter_power_t_w",
        name="Meter Active Power L3",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:meter-electric-outline",
    ),
    # Active power – extended 32-bit reading (wider range)
    GoodWeSensorEntityDescription(
        key="meter_power_total_w",
        name="Meter Active Power Total (32-bit)",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:meter-electric",
    ),
    # Frequency
    GoodWeSensorEntityDescription(
        key="meter_frequency_hz",
        name="Meter Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Power factor (dimensionless −1 … 1)
    GoodWeSensorEntityDescription(
        key="meter_power_factor",
        name="Meter Power Factor",
        native_unit_of_measurement=None,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Energy export / import – float32 representation from inverter firmware
    GoodWeSensorEntityDescription(
        key="meter_export_total_kwh",
        name="Meter Export Total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:transmission-tower-export",
    ),
    GoodWeSensorEntityDescription(
        key="meter_import_total_kwh",
        name="Meter Import Total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:transmission-tower-import",
    ),
)
