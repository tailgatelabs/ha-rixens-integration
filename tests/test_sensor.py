"""Tests for the Rixens sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rixens.const import CONF_FUEL_DOSE, DEFAULT_FUEL_DOSE
from custom_components.rixens.sensor import (
    SENSOR_DESCRIPTIONS,
    RixensSensor,
    RixensSensorEntityDescription,
)

from .conftest import make_rixens_data


class TestSensorDescriptions:
    """Tests for sensor entity descriptions."""

    def test_all_descriptions_have_value_fn(self):
        for desc in SENSOR_DESCRIPTIONS:
            assert callable(desc.value_fn)

    def test_description_keys_unique(self):
        keys = [d.key for d in SENSOR_DESCRIPTIONS]
        assert len(keys) == len(set(keys))

    def test_value_fn_returns_expected_types(self):
        data = make_rixens_data()
        for desc in SENSOR_DESCRIPTIONS:
            value = desc.value_fn(data)
            assert isinstance(value, (int, float, str, type(None)))


class TestSensorEntity:
    """Tests for the RixensSensor entity class."""

    def _make_sensor(self, mock_coordinator, key: str = "current_temperature"):
        desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == key)
        return RixensSensor(mock_coordinator, desc)

    def test_unique_id(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator)
        assert sensor._attr_unique_id == "test_entry_id_current_temperature"

    def test_native_value_temperature(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator, "current_temperature")
        assert sensor.native_value == 17.1

    def test_native_value_humidity(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator, "current_humidity")
        assert sensor.native_value == 14.5

    def test_native_value_no_cabin_sensor(self, mock_coordinator):
        """Missing cabin sensor reports unknown instead of a sentinel value."""
        mock_coordinator.data = make_rixens_data(
            current_temp=None, current_humidity=None
        )
        assert (
            self._make_sensor(mock_coordinator, "current_temperature").native_value
            is None
        )
        assert (
            self._make_sensor(mock_coordinator, "current_humidity").native_value is None
        )

    def test_native_value_battery(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator, "battery_voltage")
        assert sensor.native_value == 12.5

    def test_native_value_flame_temp(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator, "flame_temperature")
        assert sensor.native_value == 145.25

    def test_native_value_runtime(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator, "heater_runtime")
        assert sensor.native_value == 114236

    def test_native_value_firmware(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator, "firmware_version")
        assert sensor.native_value == "HW2-1.205 2025_11_20 RIXENS"

    def test_native_value_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        sensor = self._make_sensor(mock_coordinator)
        assert sensor.native_value is None

    def test_fuel_consumption_calculation(self, mock_coordinator):
        mock_coordinator.config_entry.options = {}
        sensor = self._make_sensor(mock_coordinator, "fuel_consumption")
        # dosing_pump = 1.6 Hz, default fuel_dose, * 3600
        expected = round(1.6 * DEFAULT_FUEL_DOSE * 3600, 2)
        assert sensor.native_value == expected

    def test_fuel_consumption_custom_dose(self, mock_coordinator):
        custom_dose = 0.05
        mock_coordinator.config_entry.options = {CONF_FUEL_DOSE: custom_dose}
        sensor = self._make_sensor(mock_coordinator, "fuel_consumption")
        expected = round(1.6 * custom_dose * 3600, 2)
        assert sensor.native_value == expected

    def test_fuel_consumption_zero_pump(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(dosing_pump=0.0)
        mock_coordinator.config_entry.options = {}
        sensor = self._make_sensor(mock_coordinator, "fuel_consumption")
        # dosing_pump = 0.0, value_fn returns 0.0 which is falsy,
        # so the special handling is skipped and raw 0.0 is returned
        assert sensor.native_value == 0.0

    def test_effective_fan_speed_auto(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(
            fan_state=True, fan_speed="Auto", pid_speed=73
        )
        sensor = self._make_sensor(mock_coordinator, "effective_fan_speed")
        assert sensor.native_value == 73

    def test_effective_fan_speed_off(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_state=False)
        sensor = self._make_sensor(mock_coordinator, "effective_fan_speed")
        assert sensor.native_value == 0

    def test_effective_fan_speed_manual(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_state=True, fan_speed="50")
        sensor = self._make_sensor(mock_coordinator, "effective_fan_speed")
        assert sensor.native_value == 50

    def test_effective_fan_speed_icon_on(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_state=True, fan_speed="50")
        sensor = self._make_sensor(mock_coordinator, "effective_fan_speed")
        assert sensor.icon == "mdi:fan"

    def test_effective_fan_speed_icon_off(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_state=False)
        sensor = self._make_sensor(mock_coordinator, "effective_fan_speed")
        assert sensor.icon == "mdi:fan-off"

    def test_all_sensors_instantiate(self, mock_coordinator):
        """Verify all sensor descriptions can create entities."""
        for desc in SENSOR_DESCRIPTIONS:
            sensor = RixensSensor(mock_coordinator, desc)
            assert sensor.native_value is not None
