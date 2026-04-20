"""
Tests for GoodWeCoordinator._async_update_data.

Verifies that:
  • spike filters, daily energy filters, and monotonic guards are applied
  • meter-priority overrides replace the Block A values when Block B is present
  • the 30 W grid-power deadband is applied
  • UpdateFailed is raised when _read_inverter returns None
  • master/slave merge: PV/battery are summed, meter source is chosen correctly
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# HA stubs installed by conftest.py

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from custom_components.goodwe_modbus.coordinator import (
    GoodWeCoordinator,
    _has_meter,
    _merge_master_slave,
)
from custom_components.goodwe_modbus.const import (
    CONF_HOST, CONF_MODBUS_PORT, CONF_UNIT_ID, CONF_SCAN_INTERVAL,
    CONF_SLAVE_HOST, CONF_SLAVE_MODBUS_PORT, CONF_SLAVE_UNIT_ID,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_coordinator(hass=None):
    if hass is None:
        from tests.conftest import _FakeHomeAssistant
        hass = _FakeHomeAssistant()
    entry_data = {
        CONF_HOST: "192.168.1.1",
        CONF_MODBUS_PORT: 502,
        CONF_UNIT_ID: 247,
        CONF_SCAN_INTERVAL: 10,
    }
    return GoodWeCoordinator(hass, entry_data)


def _base_data(**overrides) -> dict:
    """Return a minimal valid data dict that _read_inverter would produce."""
    data = {
        "pv1_power_w": 1000.0,
        "pv2_power_w": 500.0,
        "pv3_power_w": 0.0,
        "pv4_power_w": 0.0,
        "pv_power_w":  1500.0,
        "battery_power_w": 200.0,
        "grid_power_w": -300.0,
        "grid_power_r_w": -100.0,
        "grid_power_s_w": -100.0,
        "grid_power_t_w": -100.0,
        "load_power_w": 1400.0,
        "battery_soc_pct": 60.0,
        "inverter_temp_c": 45.0,
        "pv_energy_today_kwh": 5.0,
        "pv_energy_total_kwh": 10000.0,
        "battery_charge_today_kwh": 2.0,
        "battery_discharge_today_kwh": 1.0,
        "battery_charge_total_kwh": 5000.0,
        "battery_discharge_total_kwh": 4000.0,
        "grid_export_total_kwh": 3000.0,
        "grid_import_total_kwh": 2000.0,
        "meter_power_w": None,
        "meter_power_r_w": None,
        "meter_power_s_w": None,
        "meter_power_t_w": None,
        "meter_power_total_w": None,
        "meter_frequency_hz": None,
        "meter_power_factor": None,
        "meter_export_total_kwh": None,
        "meter_import_total_kwh": None,
        "work_mode": 1,
        "pv1_voltage_v": 350.0,
        "pv1_current_a": 2.8,
        "pv2_voltage_v": 340.0,
        "pv2_current_a": 1.5,
        "pv3_voltage_v": None,
        "pv3_current_a": 0.0,
        "pv4_voltage_v": None,
        "pv4_current_a": 0.0,
        "grid_voltage_v": 230.0,
        "grid_frequency_hz": 50.0,
        "grid_power_r_w": -100.0,
        "grid_power_s_w": -100.0,
        "grid_power_t_w": -100.0,
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCoordinatorUpdateFailed:
    @pytest.mark.asyncio
    async def test_raises_update_failed_when_no_data(self):
        coordinator = _make_coordinator()
        from homeassistant.helpers.update_coordinator import UpdateFailed
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=None,
        ):
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()


class TestCoordinatorPassthrough:
    @pytest.mark.asyncio
    async def test_data_returned_for_valid_input(self):
        coordinator = _make_coordinator()
        data = _base_data()
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=data,
        ):
            result = await coordinator._async_update_data()
        assert result["pv_power_w"] is not None
        assert result["battery_power_w"] is not None

    @pytest.mark.asyncio
    async def test_grid_power_deadband_below_30w(self):
        """Values within ±30 W should be zeroed out."""
        coordinator = _make_coordinator()
        data = _base_data(grid_power_w=-20.0, meter_power_total_w=None)
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=data,
        ):
            result = await coordinator._async_update_data()
        assert result["grid_power_w"] == 0.0

    @pytest.mark.asyncio
    async def test_grid_power_above_deadband_preserved(self):
        coordinator = _make_coordinator()
        data = _base_data(grid_power_w=-300.0, meter_power_total_w=None)
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=data,
        ):
            result = await coordinator._async_update_data()
        assert result["grid_power_w"] == -300.0


class TestCoordinatorMeterPriorityOverrides:
    @pytest.mark.asyncio
    async def test_meter_export_overrides_block_a(self):
        """When Block B meter_export_total_kwh is present it must override the Block A value."""
        coordinator = _make_coordinator()
        data = _base_data(
            grid_export_total_kwh=3000.0,
            meter_export_total_kwh=3100.0,
        )
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=data,
        ):
            result = await coordinator._async_update_data()
        assert result["grid_export_total_kwh"] == pytest.approx(3100.0, rel=1e-3)

    @pytest.mark.asyncio
    async def test_meter_import_overrides_block_a(self):
        coordinator = _make_coordinator()
        data = _base_data(
            grid_import_total_kwh=2000.0,
            meter_import_total_kwh=2200.0,
        )
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=data,
        ):
            result = await coordinator._async_update_data()
        assert result["grid_import_total_kwh"] == pytest.approx(2200.0, rel=1e-3)

    @pytest.mark.asyncio
    async def test_meter_power32_overrides_grid_power_with_deadband(self):
        """meter_power_total_w should override grid_power_w, including deadband."""
        coordinator = _make_coordinator()
        # meter_power_total_w = -25 W → within ±30 W deadband → grid_power_w = 0
        data = _base_data(grid_power_w=-200.0, meter_power_total_w=-25.0)
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=data,
        ):
            result = await coordinator._async_update_data()
        assert result["grid_power_w"] == 0.0

    @pytest.mark.asyncio
    async def test_meter_power32_overrides_grid_power_above_deadband(self):
        coordinator = _make_coordinator()
        data = _base_data(grid_power_w=-200.0, meter_power_total_w=-500.0)
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=data,
        ):
            result = await coordinator._async_update_data()
        assert result["grid_power_w"] == -500.0

    @pytest.mark.asyncio
    async def test_no_meter_block_a_values_unchanged(self):
        """With no Block B data the Block A grid values must be preserved."""
        coordinator = _make_coordinator()
        data = _base_data(
            grid_export_total_kwh=3000.0,
            grid_import_total_kwh=2000.0,
            grid_power_w=-300.0,
            meter_export_total_kwh=None,
            meter_import_total_kwh=None,
            meter_power_total_w=None,
        )
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=data,
        ):
            result = await coordinator._async_update_data()
        assert result["grid_export_total_kwh"] == pytest.approx(3000.0, rel=1e-3)
        assert result["grid_import_total_kwh"] == pytest.approx(2000.0, rel=1e-3)
        assert result["grid_power_w"] == -300.0

    @pytest.mark.asyncio
    async def test_meter_zero_does_not_override_block_a(self):
        """Meter energy value of exactly 0.0 must NOT override the Block A value.

        When the external CT meter is not yet configured or not reporting to the
        inverter, Block B float32 registers at offsets 15–18 return 0.0 kWh.
        These zeros must not suppress the valid Block A counters already stored
        by the inverter.
        """
        coordinator = _make_coordinator()
        data = _base_data(
            grid_export_total_kwh=1500.0,
            grid_import_total_kwh=800.0,
            meter_export_total_kwh=0.0,
            meter_import_total_kwh=0.0,
        )
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=data,
        ):
            result = await coordinator._async_update_data()
        # Block A values must be preserved — meter zeros must not override
        assert result["grid_export_total_kwh"] == pytest.approx(1500.0, rel=1e-3)
        assert result["grid_import_total_kwh"] == pytest.approx(800.0, rel=1e-3)

    @pytest.mark.asyncio
    async def test_meter_nonzero_still_overrides_block_a(self):
        """Meter energy > 0 must still override Block A (regression guard)."""
        coordinator = _make_coordinator()
        data = _base_data(
            grid_export_total_kwh=1500.0,
            grid_import_total_kwh=800.0,
            meter_export_total_kwh=1600.0,
            meter_import_total_kwh=900.0,
        )
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=data,
        ):
            result = await coordinator._async_update_data()
        assert result["grid_export_total_kwh"] == pytest.approx(1600.0, rel=1e-3)
        assert result["grid_import_total_kwh"] == pytest.approx(900.0, rel=1e-3)


class TestCoordinatorMonotonicGuard:
    @pytest.mark.asyncio
    async def test_monotonic_guard_blocks_decrease(self):
        """A decrease in a total-energy counter must be blocked by the guard."""
        coordinator = _make_coordinator()
        # First cycle: establish the value
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=_base_data(pv_energy_total_kwh=10000.0),
        ):
            await coordinator._async_update_data()

        # Second cycle: counter appears to drop (corrupt read)
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=_base_data(pv_energy_total_kwh=9000.0),
        ):
            result = await coordinator._async_update_data()

        assert result["pv_energy_total_kwh"] == pytest.approx(10000.0, rel=1e-3)

    @pytest.mark.asyncio
    async def test_monotonic_guard_allows_increase(self):
        coordinator = _make_coordinator()
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=_base_data(pv_energy_total_kwh=10000.0),
        ):
            await coordinator._async_update_data()

        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=_base_data(pv_energy_total_kwh=10001.0),
        ):
            result = await coordinator._async_update_data()

        assert result["pv_energy_total_kwh"] == pytest.approx(10001.0, rel=1e-3)


class TestCoordinatorSpikeFilter:
    @pytest.mark.asyncio
    async def test_power_spike_suppressed(self):
        """A large jump in PV power should be suppressed."""
        coordinator = _make_coordinator()
        # Warm up the filter with a stable value
        for _ in range(5):
            with patch(
                "custom_components.goodwe_modbus.coordinator._read_inverter",
                return_value=_base_data(pv_power_w=1500.0),
            ):
                await coordinator._async_update_data()

        # Now inject a giant spike
        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            return_value=_base_data(pv_power_w=99000.0),
        ):
            result = await coordinator._async_update_data()

        assert result["pv_power_w"] == pytest.approx(1500.0)


class TestCoordinatorDefaults:
    def test_default_config_values(self):
        """Coordinator should accept partial entry_data, using defaults for missing keys."""
        from tests.conftest import _FakeHomeAssistant
        hass = _FakeHomeAssistant()
        coordinator = GoodWeCoordinator(hass, {CONF_HOST: "10.0.0.1"})
        assert coordinator._host == "10.0.0.1"
        assert coordinator._port == 502        # DEFAULT_PORT
        assert coordinator._unit_id == 247     # DEFAULT_UNIT_ID

    def test_slave_config_stored(self):
        """When slave_host is present in entry_data it should be stored on the coordinator."""
        from tests.conftest import _FakeHomeAssistant
        hass = _FakeHomeAssistant()
        coordinator = GoodWeCoordinator(hass, {
            CONF_HOST: "10.0.0.1",
            CONF_SLAVE_HOST: "10.0.0.2",
            CONF_SLAVE_MODBUS_PORT: 503,
            CONF_SLAVE_UNIT_ID: 248,
        })
        assert coordinator._slave_host == "10.0.0.2"
        assert coordinator._slave_port == 503
        assert coordinator._slave_unit_id == 248

    def test_slave_host_empty_string_treated_as_none(self):
        """An empty slave_host (from the config-flow default) must be treated as absent."""
        from tests.conftest import _FakeHomeAssistant
        hass = _FakeHomeAssistant()
        coordinator = GoodWeCoordinator(hass, {CONF_HOST: "10.0.0.1", CONF_SLAVE_HOST: ""})
        assert coordinator._slave_host is None


# ---------------------------------------------------------------------------
# Unit tests for _has_meter / _merge_master_slave
# ---------------------------------------------------------------------------

class TestHasMeter:
    def test_has_meter_when_block_b_present(self):
        """meter_power_w being a float (even 0.0) means Block B was readable."""
        data = _base_data(meter_power_w=0.0)
        assert _has_meter(data) is True

    def test_has_meter_when_block_b_nonzero(self):
        data = _base_data(meter_power_w=-450.0)
        assert _has_meter(data) is True

    def test_no_meter_when_block_b_absent(self):
        """meter_power_w = None means Block B was not available."""
        data = _base_data(meter_power_w=None)
        assert _has_meter(data) is False


class TestMergeMasterSlave:
    def _master(self, **kw) -> dict:
        base = _base_data(
            pv_power_w=2000.0,
            battery_power_w=500.0,
            pv_energy_total_kwh=8000.0,
            pv_energy_today_kwh=10.0,
            battery_charge_total_kwh=3000.0,
            battery_charge_today_kwh=2.0,
            battery_discharge_total_kwh=2500.0,
            battery_discharge_today_kwh=1.5,
            grid_power_w=300.0,
        )
        # Apply meter defaults then caller overrides
        base["meter_power_w"]          = -300.0
        base["meter_power_total_w"]    = -310.0
        base["meter_export_total_kwh"] = 5000.0
        base["meter_import_total_kwh"] = 4000.0
        base.update(kw)
        return base

    def _slave(self, **kw) -> dict:
        base = _base_data(
            pv_power_w=1500.0,
            battery_power_w=200.0,
            pv_energy_total_kwh=6000.0,
            pv_energy_today_kwh=8.0,
            battery_charge_total_kwh=2000.0,
            battery_charge_today_kwh=1.5,
            battery_discharge_total_kwh=1800.0,
            battery_discharge_today_kwh=1.0,
            grid_power_w=150.0,
        )
        # Slave has no meter by default
        base["meter_power_w"]          = None
        base["meter_power_total_w"]    = None
        base["meter_export_total_kwh"] = None
        base["meter_import_total_kwh"] = None
        base.update(kw)
        return base

    def test_pv_power_summed(self):
        merged = _merge_master_slave(self._master(), self._slave())
        assert merged["pv_power_w"] == pytest.approx(3500.0)

    def test_battery_power_summed(self):
        merged = _merge_master_slave(self._master(), self._slave())
        assert merged["battery_power_w"] == pytest.approx(700.0)

    def test_pv_energy_total_summed(self):
        merged = _merge_master_slave(self._master(), self._slave())
        assert merged["pv_energy_total_kwh"] == pytest.approx(14000.0)
        assert merged["pv_energy_today_kwh"] == pytest.approx(18.0)

    def test_battery_energy_totals_summed(self):
        merged = _merge_master_slave(self._master(), self._slave())
        assert merged["battery_charge_total_kwh"] == pytest.approx(5000.0)
        assert merged["battery_discharge_total_kwh"] == pytest.approx(4300.0)
        assert merged["battery_charge_today_kwh"] == pytest.approx(3.5)
        assert merged["battery_discharge_today_kwh"] == pytest.approx(2.5)

    def test_master_meter_used_when_master_has_meter(self):
        """When master has Block B, its meter values must be used."""
        merged = _merge_master_slave(self._master(), self._slave())
        assert merged["meter_export_total_kwh"] == pytest.approx(5000.0)
        assert merged["meter_import_total_kwh"] == pytest.approx(4000.0)
        assert merged["meter_power_total_w"] == pytest.approx(-310.0)

    def test_slave_meter_used_when_master_has_no_meter(self):
        """When master has no Block B but slave does, slave meter values must be used."""
        master = self._master(
            meter_power_w=None,
            meter_power_total_w=None,
            meter_export_total_kwh=None,
            meter_import_total_kwh=None,
        )
        slave = self._slave(
            meter_power_w=200.0,
            meter_power_total_w=210.0,
            meter_export_total_kwh=7000.0,
            meter_import_total_kwh=6000.0,
            grid_power_w=-200.0,
        )
        merged = _merge_master_slave(master, slave)
        assert merged["meter_power_w"] == pytest.approx(200.0)
        assert merged["meter_power_total_w"] == pytest.approx(210.0)
        assert merged["meter_export_total_kwh"] == pytest.approx(7000.0)
        assert merged["meter_import_total_kwh"] == pytest.approx(6000.0)
        assert merged["grid_power_w"] == pytest.approx(-200.0)

    def test_master_grid_values_preserved_when_neither_has_meter(self):
        """When neither inverter has Block B, master grid values are kept."""
        master = self._master(
            meter_power_w=None, meter_power_total_w=None,
            meter_export_total_kwh=None, meter_import_total_kwh=None,
            grid_power_w=300.0,
        )
        slave = self._slave(grid_power_w=150.0)
        merged = _merge_master_slave(master, slave)
        assert merged["grid_power_w"] == pytest.approx(300.0)

    def test_non_meter_fields_come_from_master(self):
        """Temperature, SOC, work_mode and load must always come from master."""
        master = self._master()
        slave  = self._slave()
        merged = _merge_master_slave(master, slave)
        assert merged["inverter_temp_c"] == master["inverter_temp_c"]
        assert merged["battery_soc_pct"] == master["battery_soc_pct"]
        assert merged["work_mode"] == master["work_mode"]
        assert merged["load_power_w"] == master["load_power_w"]


# ---------------------------------------------------------------------------
# Integration tests for coordinator with slave host
# ---------------------------------------------------------------------------

def _make_coordinator_with_slave(hass=None):
    if hass is None:
        from tests.conftest import _FakeHomeAssistant
        hass = _FakeHomeAssistant()
    entry_data = {
        CONF_HOST: "192.168.1.1",
        CONF_MODBUS_PORT: 502,
        CONF_UNIT_ID: 247,
        CONF_SCAN_INTERVAL: 10,
        CONF_SLAVE_HOST: "192.168.1.2",
        CONF_SLAVE_MODBUS_PORT: 502,
        CONF_SLAVE_UNIT_ID: 247,
    }
    return GoodWeCoordinator(hass, entry_data)


class TestCoordinatorSlaveIntegration:
    @pytest.mark.asyncio
    async def test_slave_pv_added_to_master(self):
        """Combined PV power must be master + slave."""
        coordinator = _make_coordinator_with_slave()
        master_data = _base_data(pv_power_w=2000.0, meter_power_w=-300.0)
        slave_data  = _base_data(pv_power_w=1500.0, meter_power_w=None)

        call_count = 0

        def fake_read(host, port, unit_id):
            nonlocal call_count
            call_count += 1
            return master_data if call_count == 1 else slave_data

        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            side_effect=fake_read,
        ):
            result = await coordinator._async_update_data()

        assert result["pv_power_w"] == pytest.approx(3500.0, rel=1e-2)

    @pytest.mark.asyncio
    async def test_slave_meter_used_when_master_has_no_block_b(self):
        """When master has no Block B, slave Block B meter values must be used for grid."""
        coordinator = _make_coordinator_with_slave()
        master_data = _base_data(
            meter_power_w=None,
            meter_power_total_w=None,
            meter_export_total_kwh=None,
            meter_import_total_kwh=None,
            grid_export_total_kwh=100.0,
            grid_import_total_kwh=50.0,
        )
        slave_data = _base_data(
            meter_power_w=150.0,
            meter_power_total_w=160.0,
            meter_export_total_kwh=9000.0,
            meter_import_total_kwh=8000.0,
        )

        call_count = 0

        def fake_read(host, port, unit_id):
            nonlocal call_count
            call_count += 1
            return master_data if call_count == 1 else slave_data

        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            side_effect=fake_read,
        ):
            result = await coordinator._async_update_data()

        assert result["meter_export_total_kwh"] == pytest.approx(9000.0, rel=1e-3)
        assert result["meter_import_total_kwh"] == pytest.approx(8000.0, rel=1e-3)
        # The meter-priority override in _async_update_data should propagate slave
        # meter values to grid_export/import totals
        assert result["grid_export_total_kwh"] == pytest.approx(9000.0, rel=1e-3)
        assert result["grid_import_total_kwh"] == pytest.approx(8000.0, rel=1e-3)

    @pytest.mark.asyncio
    async def test_slave_failure_does_not_crash_coordinator(self):
        """If slave returns None, coordinator should continue with master data only."""
        coordinator = _make_coordinator_with_slave()
        master_data = _base_data(pv_power_w=2000.0)

        call_count = 0

        def fake_read(host, port, unit_id):
            nonlocal call_count
            call_count += 1
            return master_data if call_count == 1 else None  # slave fails

        with patch(
            "custom_components.goodwe_modbus.coordinator._read_inverter",
            side_effect=fake_read,
        ):
            result = await coordinator._async_update_data()

        # Master data should still be returned
        assert result["pv_power_w"] is not None
