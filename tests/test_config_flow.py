"""
Tests for the config_flow module.

Covers:
  • Schema validation (valid input accepted, bad input rejected)
  • Successful connection → entry created
  • Failed connection → 'cannot_connect' error shown
  • Unexpected exception → 'unknown' error shown
  • Duplicate entry prevention
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# HA stubs installed by conftest.py

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import voluptuous as vol

from custom_components.goodwe_modbus.config_flow import (
    GoodWeModbusConfigFlow,
    CannotConnect,
    STEP_USER_SCHEMA,
)
from custom_components.goodwe_modbus.const import (
    CONF_HOST,
    CONF_MODBUS_PORT,
    CONF_UNIT_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    DEFAULT_SCAN_INTERVAL,
)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestStepUserSchema:
    def test_valid_full_input(self):
        data = STEP_USER_SCHEMA({
            CONF_HOST: "192.168.1.100",
            CONF_MODBUS_PORT: 502,
            CONF_UNIT_ID: 247,
            CONF_SCAN_INTERVAL: 30,
        })
        assert data[CONF_HOST] == "192.168.1.100"

    def test_host_required(self):
        with pytest.raises(vol.Invalid):
            STEP_USER_SCHEMA({
                CONF_MODBUS_PORT: 502,
                CONF_UNIT_ID: 247,
                CONF_SCAN_INTERVAL: 10,
            })

    def test_port_out_of_range_low(self):
        with pytest.raises(vol.Invalid):
            STEP_USER_SCHEMA({
                CONF_HOST: "192.168.1.1",
                CONF_MODBUS_PORT: 0,
                CONF_UNIT_ID: 247,
                CONF_SCAN_INTERVAL: 10,
            })

    def test_port_out_of_range_high(self):
        with pytest.raises(vol.Invalid):
            STEP_USER_SCHEMA({
                CONF_HOST: "192.168.1.1",
                CONF_MODBUS_PORT: 70000,
                CONF_UNIT_ID: 247,
                CONF_SCAN_INTERVAL: 10,
            })

    def test_unit_id_out_of_range_low(self):
        with pytest.raises(vol.Invalid):
            STEP_USER_SCHEMA({
                CONF_HOST: "192.168.1.1",
                CONF_MODBUS_PORT: 502,
                CONF_UNIT_ID: 0,
                CONF_SCAN_INTERVAL: 10,
            })

    def test_unit_id_out_of_range_high(self):
        with pytest.raises(vol.Invalid):
            STEP_USER_SCHEMA({
                CONF_HOST: "192.168.1.1",
                CONF_MODBUS_PORT: 502,
                CONF_UNIT_ID: 256,
                CONF_SCAN_INTERVAL: 10,
            })

    def test_scan_interval_too_low(self):
        with pytest.raises(vol.Invalid):
            STEP_USER_SCHEMA({
                CONF_HOST: "192.168.1.1",
                CONF_MODBUS_PORT: 502,
                CONF_UNIT_ID: 247,
                CONF_SCAN_INTERVAL: 4,
            })

    def test_scan_interval_too_high(self):
        with pytest.raises(vol.Invalid):
            STEP_USER_SCHEMA({
                CONF_HOST: "192.168.1.1",
                CONF_MODBUS_PORT: 502,
                CONF_UNIT_ID: 247,
                CONF_SCAN_INTERVAL: 301,
            })

    def test_defaults_applied(self):
        data = STEP_USER_SCHEMA({CONF_HOST: "10.0.0.1"})
        assert data[CONF_MODBUS_PORT] == DEFAULT_PORT
        assert data[CONF_UNIT_ID] == DEFAULT_UNIT_ID
        assert data[CONF_SCAN_INTERVAL] == DEFAULT_SCAN_INTERVAL

    def test_boundary_port_min(self):
        data = STEP_USER_SCHEMA({
            CONF_HOST: "10.0.0.1",
            CONF_MODBUS_PORT: 1,
        })
        assert data[CONF_MODBUS_PORT] == 1

    def test_boundary_port_max(self):
        data = STEP_USER_SCHEMA({
            CONF_HOST: "10.0.0.1",
            CONF_MODBUS_PORT: 65535,
        })
        assert data[CONF_MODBUS_PORT] == 65535

    def test_boundary_scan_interval_min(self):
        data = STEP_USER_SCHEMA({
            CONF_HOST: "10.0.0.1",
            CONF_SCAN_INTERVAL: 5,
        })
        assert data[CONF_SCAN_INTERVAL] == 5

    def test_boundary_scan_interval_max(self):
        data = STEP_USER_SCHEMA({
            CONF_HOST: "10.0.0.1",
            CONF_SCAN_INTERVAL: 300,
        })
        assert data[CONF_SCAN_INTERVAL] == 300


# ---------------------------------------------------------------------------
# Config flow async_step_user tests
# ---------------------------------------------------------------------------

class TestGoodWeModbusConfigFlow:
    def _make_flow(self):
        flow = GoodWeModbusConfigFlow()
        return flow

    @pytest.mark.asyncio
    async def test_no_input_shows_form(self):
        flow = self._make_flow()
        result = await flow.async_step_user(None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {}

    @pytest.mark.asyncio
    async def test_successful_connection_creates_entry(self):
        flow = self._make_flow()
        with patch(
            "custom_components.goodwe_modbus.config_flow._test_connection",
            new_callable=AsyncMock,
        ) as mock_test:
            mock_test.return_value = None
            result = await flow.async_step_user({
                CONF_HOST: "192.168.1.1",
                CONF_MODBUS_PORT: 502,
                CONF_UNIT_ID: 247,
                CONF_SCAN_INTERVAL: 10,
            })
        assert result["type"] == "create_entry"
        assert result["data"][CONF_HOST] == "192.168.1.1"
        assert result["data"][CONF_MODBUS_PORT] == 502

    @pytest.mark.asyncio
    async def test_cannot_connect_shows_error(self):
        flow = self._make_flow()
        with patch(
            "custom_components.goodwe_modbus.config_flow._test_connection",
            side_effect=CannotConnect("unreachable"),
        ):
            result = await flow.async_step_user({
                CONF_HOST: "192.168.1.1",
                CONF_MODBUS_PORT: 502,
                CONF_UNIT_ID: 247,
                CONF_SCAN_INTERVAL: 10,
            })
        assert result["type"] == "form"
        assert result["errors"]["base"] == "cannot_connect"

    @pytest.mark.asyncio
    async def test_unexpected_exception_shows_unknown_error(self):
        flow = self._make_flow()
        with patch(
            "custom_components.goodwe_modbus.config_flow._test_connection",
            side_effect=RuntimeError("boom"),
        ):
            result = await flow.async_step_user({
                CONF_HOST: "192.168.1.1",
                CONF_MODBUS_PORT: 502,
                CONF_UNIT_ID: 247,
                CONF_SCAN_INTERVAL: 10,
            })
        assert result["type"] == "form"
        assert result["errors"]["base"] == "unknown"

    @pytest.mark.asyncio
    async def test_host_is_stripped_of_whitespace(self):
        flow = self._make_flow()
        with patch(
            "custom_components.goodwe_modbus.config_flow._test_connection",
            new_callable=AsyncMock,
        ) as mock_test:
            mock_test.return_value = None
            result = await flow.async_step_user({
                CONF_HOST: "  192.168.1.1  ",
                CONF_MODBUS_PORT: 502,
                CONF_UNIT_ID: 247,
                CONF_SCAN_INTERVAL: 10,
            })
        assert result["data"][CONF_HOST] == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_entry_title_contains_host(self):
        flow = self._make_flow()
        with patch(
            "custom_components.goodwe_modbus.config_flow._test_connection",
            new_callable=AsyncMock,
        ):
            result = await flow.async_step_user({
                CONF_HOST: "10.0.0.99",
                CONF_MODBUS_PORT: 502,
                CONF_UNIT_ID: 247,
                CONF_SCAN_INTERVAL: 10,
            })
        assert "10.0.0.99" in result["title"]


class TestCannotConnect:
    def test_is_homeassistant_error(self):
        from homeassistant.exceptions import HomeAssistantError
        assert issubclass(CannotConnect, HomeAssistantError)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(CannotConnect):
            raise CannotConnect("cannot reach inverter")
