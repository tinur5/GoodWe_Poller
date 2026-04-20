"""
conftest.py – Provides lightweight stubs for the homeassistant packages so
that coordinator.py, sensor.py and config_flow.py can be imported without a
full HA installation.
"""

import sys
import types
from unittest.mock import MagicMock


def _make_module(name: str, **attrs):
    """Create a stub module with the given attributes."""
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    return mod


# ── homeassistant.core ────────────────────────────────────────────────────────

class _FakeHomeAssistant:
    """Minimal stub for HomeAssistant."""

    def __init__(self):
        self.data = {}

    async def async_add_executor_job(self, func, *args):
        # Execute synchronously in tests (no real thread pool needed).
        return func(*args)


ha_core = _make_module(
    "homeassistant.core",
    HomeAssistant=_FakeHomeAssistant,
    callback=lambda f: f,
)

# ── homeassistant.exceptions ──────────────────────────────────────────────────

class _HomeAssistantError(Exception):
    pass

ha_exc = _make_module(
    "homeassistant.exceptions",
    HomeAssistantError=_HomeAssistantError,
)

# ── homeassistant.helpers.update_coordinator ─────────────────────────────────

class _DataUpdateCoordinator:
    """Minimal stub."""

    def __init__(self, hass, logger, *, name, update_interval):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data = None

    async def async_config_entry_first_refresh(self):
        self.data = await self._async_update_data()

    async def async_refresh(self):
        self.data = await self._async_update_data()


class _UpdateFailed(Exception):
    pass


ha_coordinator = _make_module(
    "homeassistant.helpers.update_coordinator",
    DataUpdateCoordinator=_DataUpdateCoordinator,
    UpdateFailed=_UpdateFailed,
)

# ── homeassistant.config_entries ──────────────────────────────────────────────

class _ConfigFlow:
    def __init_subclass__(cls, *, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
    def __init__(self):
        self.hass = _FakeHomeAssistant()

    async def async_set_unique_id(self, uid):
        self._unique_id = uid

    def _abort_if_unique_id_configured(self):
        pass

    def async_create_entry(self, *, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, *, step_id, data_schema, errors=None):
        return {"type": "form", "step_id": step_id, "errors": errors or {}}


class _ConfigFlowResult(dict):
    pass


class _ConfigEntry:
    def __init__(self, entry_id="test_entry", data=None, title="Test"):
        self.entry_id = entry_id
        self.data = data or {}
        self.title = title


ha_config_entries = _make_module(
    "homeassistant.config_entries",
    ConfigFlow=_ConfigFlow,
    ConfigFlowResult=_ConfigFlowResult,
    ConfigEntry=_ConfigEntry,
)

# ── homeassistant.components.sensor ──────────────────────────────────────────

class _SensorDeviceClass:
    POWER       = "power"
    ENERGY      = "energy"
    VOLTAGE     = "voltage"
    CURRENT     = "current"
    TEMPERATURE = "temperature"
    BATTERY     = "battery"
    FREQUENCY   = "frequency"
    POWER_FACTOR = "power_factor"


class _SensorStateClass:
    MEASUREMENT      = "measurement"
    TOTAL_INCREASING = "total_increasing"


from dataclasses import dataclass, field

@dataclass(frozen=True)
class _SensorEntityDescription:
    """Stub that accepts the same keyword arguments as the real HA class."""
    key: str = ""
    name: str | None = None
    native_unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    icon: str | None = None
    entity_registry_enabled_default: bool = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class _SensorEntity:
    pass


ha_sensor = _make_module(
    "homeassistant.components.sensor",
    SensorDeviceClass=_SensorDeviceClass,
    SensorEntityDescription=_SensorEntityDescription,
    SensorStateClass=_SensorStateClass,
    SensorEntity=_SensorEntity,
)

# ── homeassistant.const ───────────────────────────────────────────────────────

class _UnitOfPower:
    WATT = "W"


class _UnitOfEnergy:
    KILO_WATT_HOUR = "kWh"


class _UnitOfElectricPotential:
    VOLT = "V"


class _UnitOfElectricCurrent:
    AMPERE = "A"


class _UnitOfTemperature:
    CELSIUS = "°C"


class _UnitOfFrequency:
    HERTZ = "Hz"


ha_const = _make_module(
    "homeassistant.const",
    UnitOfPower=_UnitOfPower,
    UnitOfEnergy=_UnitOfEnergy,
    UnitOfElectricPotential=_UnitOfElectricPotential,
    UnitOfElectricCurrent=_UnitOfElectricCurrent,
    UnitOfTemperature=_UnitOfTemperature,
    UnitOfFrequency=_UnitOfFrequency,
    PERCENTAGE="%",
)

# ── homeassistant.helpers.device_registry ────────────────────────────────────

class _DeviceInfo(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


ha_device_registry = _make_module(
    "homeassistant.helpers.device_registry",
    DeviceInfo=_DeviceInfo,
)

# ── homeassistant.helpers.entity_platform ────────────────────────────────────

ha_entity_platform = _make_module(
    "homeassistant.helpers.entity_platform",
    AddEntitiesCallback=MagicMock,
)

# ── homeassistant.helpers.update_coordinator (CoordinatorEntity) ─────────────

class _CoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def __class_getitem__(cls, item):
        return cls


ha_coordinator.CoordinatorEntity = _CoordinatorEntity

# ── Register all stubs ────────────────────────────────────────────────────────

_STUBS = {
    "homeassistant":                                _make_module("homeassistant"),
    "homeassistant.core":                           ha_core,
    "homeassistant.exceptions":                     ha_exc,
    "homeassistant.helpers":                        _make_module("homeassistant.helpers"),
    "homeassistant.helpers.update_coordinator":     ha_coordinator,
    "homeassistant.helpers.device_registry":        ha_device_registry,
    "homeassistant.helpers.entity_platform":        ha_entity_platform,
    "homeassistant.config_entries":                 ha_config_entries,
    "homeassistant.components":                     _make_module("homeassistant.components"),
    "homeassistant.components.sensor":              ha_sensor,
    "homeassistant.const":                          ha_const,
}

for _name, _mod in _STUBS.items():
    sys.modules.setdefault(_name, _mod)
