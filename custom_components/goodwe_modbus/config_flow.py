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

            # Prevent duplicate entries for the same inverter
            await self.async_set_unique_id(f"{host}:{port}:{unit_id}")
            self._abort_if_unique_id_configured()

            try:
                await _test_connection(self.hass, host, port, unit_id)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"GoodWe @ {host}",
                    data={
                        CONF_HOST:          host,
                        CONF_MODBUS_PORT:   port,
                        CONF_UNIT_ID:       unit_id,
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Raised when the inverter is unreachable."""
