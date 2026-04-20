"""Config flow for GoodWe Modbus integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_MODBUS_PORT,
    CONF_UNIT_ID,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE_HOST,
    CONF_SLAVE_MODBUS_PORT,
    CONF_SLAVE_UNIT_ID,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_MODBUS_PORT, default=DEFAULT_PORT): vol.All(
            int, vol.Range(min=1, max=65535)
        ),
        vol.Optional(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(
            int, vol.Range(min=1, max=255)
        ),
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=5, max=300)
        ),
        # ── Optional slave inverter ────────────────────────────────────────────
        # In a parallel (master/slave) GoodWe setup the external CT meter is
        # physically connected to only one inverter (usually the master).
        # When slave_host is set, the coordinator polls both inverters and uses
        # the external-meter (Block B) data from whichever has it, while summing
        # PV and battery values across both units.
        vol.Optional(CONF_SLAVE_HOST, default=""): str,
        vol.Optional(CONF_SLAVE_MODBUS_PORT, default=DEFAULT_PORT): vol.All(
            int, vol.Range(min=1, max=65535)
        ),
        vol.Optional(CONF_SLAVE_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(
            int, vol.Range(min=1, max=255)
        ),
    }
)


async def _test_connection(hass: HomeAssistant, host: str, port: int,
                           unit_id: int) -> None:
    """Try to read one register block; raise CannotConnect on failure."""
    from pymodbus.client import ModbusTcpClient
    from pymodbus.exceptions import ModbusException

    def _connect() -> None:
        client = ModbusTcpClient(host=host, port=port, timeout=5)
        if not client.connect():
            raise CannotConnect(f"Cannot reach {host}:{port}")
        try:
            rr = client.read_holding_registers(
                address=35100, count=10, device_id=unit_id)
            if rr.isError():
                raise CannotConnect(f"Modbus error from {host}: {rr}")
        except ModbusException as exc:
            raise CannotConnect(str(exc)) from exc
        finally:
            client.close()

    await hass.async_add_executor_job(_connect)


class GoodWeModbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup of a GoodWe Modbus integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host    = user_input[CONF_HOST].strip()
            port    = user_input[CONF_MODBUS_PORT]
            unit_id = user_input[CONF_UNIT_ID]
            slave_host = user_input.get(CONF_SLAVE_HOST, "").strip()

            # Prevent duplicate entries for the same inverter
            await self.async_set_unique_id(f"{host}:{port}:{unit_id}")
            self._abort_if_unique_id_configured()

            try:
                await _test_connection(self.hass, host, port, unit_id)
                if slave_host:
                    slave_port    = user_input[CONF_SLAVE_MODBUS_PORT]
                    slave_unit_id = user_input[CONF_SLAVE_UNIT_ID]
                    await _test_connection(self.hass, slave_host, slave_port, slave_unit_id)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"
            else:
                entry_data: dict = {
                    CONF_HOST:          host,
                    CONF_MODBUS_PORT:   port,
                    CONF_UNIT_ID:       unit_id,
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                }
                if slave_host:
                    entry_data[CONF_SLAVE_HOST]        = slave_host
                    entry_data[CONF_SLAVE_MODBUS_PORT] = user_input[CONF_SLAVE_MODBUS_PORT]
                    entry_data[CONF_SLAVE_UNIT_ID]     = user_input[CONF_SLAVE_UNIT_ID]
                return self.async_create_entry(
                    title=f"GoodWe @ {host}",
                    data=entry_data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Raised when the inverter is unreachable."""
