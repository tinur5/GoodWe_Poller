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

from .const import DOMAIN, CONF_MASTER_HOST, SENSOR_DESCRIPTIONS, GoodWeSensorEntityDescription
from .coordinator import GoodWeCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GoodWe Modbus sensor entities from a config entry."""
    coordinator: GoodWeCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        GoodWeSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class GoodWeSensor(CoordinatorEntity[GoodWeCoordinator], SensorEntity):
    """A single sensor entity backed by the GoodWe coordinator."""

    entity_description: GoodWeSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GoodWeCoordinator,
        entry: ConfigEntry,
        description: GoodWeSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="GoodWe",
            model="Hybrid Inverter (ET/EH/BT/BH)",
            configuration_url=f"http://{entry.data[CONF_MASTER_HOST]}",
        )

    @property
    def native_value(self) -> Any:
        """Return the current sensor value from coordinator data."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self.entity_description.key)
        if value is None:
            return None
        # Round floats to one decimal for clean display
        if isinstance(value, float):
            return round(value, 1)
        return value
