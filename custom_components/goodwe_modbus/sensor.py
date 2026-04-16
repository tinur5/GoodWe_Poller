"""Sensor platform for GoodWe Modbus integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_MASTER_HOST,
    CONF_SLAVE_HOST,
    SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS_MASTER,
    SENSOR_DESCRIPTIONS_SLAVE,
    SENSOR_DESCRIPTIONS_METER,
    GoodWeSensorEntityDescription,
)
from .coordinator import GoodWeCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GoodWe Modbus sensor entities from a config entry."""
    coordinator: GoodWeCoordinator = hass.data[DOMAIN][entry.entry_id]
    master_host = entry.data[CONF_MASTER_HOST]
    slave_host  = entry.data.get(CONF_SLAVE_HOST, "").strip()

    # ── Device: combined / total ──────────────────────────────────────────────
    combined_device = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="GoodWe",
        model="Hybrid Inverter (ET/EH/BT/BH)",
        configuration_url=f"http://{master_host}",
    )

    # ── Device: master inverter ───────────────────────────────────────────────
    master_device = DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_master")},
        name=f"{entry.title} – Inverter 1",
        manufacturer="GoodWe",
        model="Hybrid Inverter (ET/EH/BT/BH)",
        configuration_url=f"http://{master_host}",
        via_device=(DOMAIN, entry.entry_id),
    )

    entities: list[GoodWeSensor] = []

    # Combined sensors (existing behaviour, no change to unique IDs)
    for description in SENSOR_DESCRIPTIONS + SENSOR_DESCRIPTIONS_METER:
        entities.append(GoodWeSensor(coordinator, entry, description, combined_device))

    # Master inverter sensors (individual values, separate sub-device)
    for description in SENSOR_DESCRIPTIONS_MASTER:
        entities.append(
            GoodWeSensor(
                coordinator, entry, description, master_device,
                unique_id_suffix="master",
            )
        )

    # Slave inverter sensors – only when a slave IP is configured
    if slave_host:
        slave_device = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_slave")},
            name=f"{entry.title} – Inverter 2",
            manufacturer="GoodWe",
            model="Hybrid Inverter (ET/EH/BT/BH)",
            configuration_url=f"http://{slave_host}",
            via_device=(DOMAIN, entry.entry_id),
        )
        for description in SENSOR_DESCRIPTIONS_SLAVE:
            entities.append(
                GoodWeSensor(
                    coordinator, entry, description, slave_device,
                    unique_id_suffix="slave",
                )
            )

    async_add_entities(entities)


class GoodWeSensor(CoordinatorEntity[GoodWeCoordinator], SensorEntity):
    """A single sensor entity backed by the GoodWe coordinator."""

    entity_description: GoodWeSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GoodWeCoordinator,
        entry: ConfigEntry,
        description: GoodWeSensorEntityDescription,
        device_info: DeviceInfo,
        *,
        unique_id_suffix: str = "",
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        suffix = f"_{unique_id_suffix}" if unique_id_suffix else ""
        self._attr_unique_id = f"{entry.entry_id}{suffix}_{description.key}"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> Any:
        """Return the current sensor value from coordinator data."""
        source = self.entity_description.data_source
        if source == "master":
            data = self.coordinator.master_data
        elif source == "slave":
            data = self.coordinator.slave_data
        else:
            data = self.coordinator.data

        if data is None:
            return None
        value = data.get(self.entity_description.key)
        if value is None:
            return None
        # Round floats to one decimal for clean display
        if isinstance(value, float):
            return round(value, 1)
        return value
