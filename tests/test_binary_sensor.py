"""Tests for the Rixens binary sensor platform."""

from __future__ import annotations

import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.rixens.binary_sensor import (
    RixensConnectionSensor,
    RixensHeaterFaultSensor,
)

from .conftest import make_rixens_data


class TestConnectionSensor:
    """Tests for the connection binary sensor."""

    def test_unique_id(self, mock_coordinator):
        sensor = RixensConnectionSensor(mock_coordinator)
        assert sensor._attr_unique_id == "test_entry_id_connection"

    def test_translation_key(self, mock_coordinator):
        sensor = RixensConnectionSensor(mock_coordinator)
        assert sensor._attr_translation_key == "connection"

    def test_is_on_when_available(self, mock_coordinator):
        mock_coordinator.is_available = True
        sensor = RixensConnectionSensor(mock_coordinator)
        assert sensor.is_on is True

    def test_is_on_when_unavailable(self, mock_coordinator):
        mock_coordinator.is_available = False
        sensor = RixensConnectionSensor(mock_coordinator)
        assert sensor.is_on is False

    def test_always_available(self, mock_coordinator):
        sensor = RixensConnectionSensor(mock_coordinator)
        assert sensor.available is True


class TestHeaterFaultSensor:
    """Tests for the heater fault binary sensor."""

    def test_unique_id_and_class(self, mock_coordinator):
        sensor = RixensHeaterFaultSensor(mock_coordinator)
        assert sensor._attr_unique_id == "test_entry_id_heater_fault"
        assert sensor.device_class == BinarySensorDeviceClass.PROBLEM
        assert sensor.entity_category is None  # shown on dashboards

    def test_off_when_no_fault(self, mock_coordinator):
        sensor = RixensHeaterFaultSensor(mock_coordinator)
        assert sensor.is_on is False

    @pytest.mark.parametrize("af", [48, 123])
    def test_on_with_active_fault(self, mock_coordinator, af):
        mock_coordinator.data = make_rixens_data(faults={"AF": af})
        assert RixensHeaterFaultSensor(mock_coordinator).is_on is True

    def test_no_data_code_is_not_a_fault(self, mock_coordinator):
        """AF=255 means no data, not a fault."""
        mock_coordinator.data = make_rixens_data(faults={"AF": 255})
        assert RixensHeaterFaultSensor(mock_coordinator).is_on is False

    def test_on_in_heater_error_state(self, mock_coordinator):
        """heaterstate 200 is the documented error state."""
        mock_coordinator.data = make_rixens_data(heater_state=200)
        assert RixensHeaterFaultSensor(mock_coordinator).is_on is True

    def test_attributes(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(
            faults={"AF": 48, "F1": 48, "F2": 0, "F3": 0, "F4": 0, "F5": 0}
        )
        sensor = RixensHeaterFaultSensor(mock_coordinator)
        assert sensor.extra_state_attributes == {
            "active_fault_code": 48,
            "active_fault_p_code": "P000200",
            "active_fault_class": "fuel_supply_or_pump",
            "stored_fault_codes": [48, 0, 0, 0, 0],
            "heater_state": 20,
        }

    def test_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        sensor = RixensHeaterFaultSensor(mock_coordinator)
        assert sensor.is_on is None
        assert sensor.extra_state_attributes == {}
