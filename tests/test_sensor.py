"""Tests for the Rixens sensor platform."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTime, UnitOfVolume

from custom_components.rixens.const import CONF_FUEL_DOSE, DEFAULT_FUEL_DOSE
from custom_components.rixens.faults import FAULT_OPTIONS
from custom_components.rixens.sensor import (
    FUEL_USED_MAX_GAP,
    SENSOR_DESCRIPTIONS,
    RixensFuelUsedSensor,
    RixensSensor,
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
            assert isinstance(value, (datetime, int, float, str, type(None)))

    @pytest.mark.parametrize(
        "key",
        [
            "pid_speed",
            "burner_motor",
            "dosing_pump",
            "flame_temperature",
            "inlet_temperature",
            "outlet_temperature",
        ],
    )
    def test_noisy_diagnostics_disabled_by_default(self, key):
        """Troubleshooting sensors that change every poll start disabled (#89)."""
        desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == key)
        assert desc.entity_registry_enabled_default is False

    def test_fuel_consumption_enabled_by_default(self):
        desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "fuel_consumption")
        assert desc.entity_registry_enabled_default is True

    @pytest.mark.parametrize("key", ["pid_speed", "burner_motor"])
    def test_no_long_term_statistics(self, key):
        """No state_class, so no long-term statistics are kept (#89)."""
        desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == key)
        assert desc.state_class is None

    def test_numeric_sensors_have_display_precision(self):
        """Every numeric sensor ships a default precision (#84)."""
        data = make_rixens_data()
        for desc in SENSOR_DESCRIPTIONS:
            if desc.device_class in (
                SensorDeviceClass.ENUM,
                SensorDeviceClass.TIMESTAMP,
            ) or isinstance(desc.value_fn(data), str):
                assert desc.suggested_display_precision is None, desc.key
            else:
                assert desc.suggested_display_precision is not None, desc.key


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

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(0, "not_ready"), (1, "ready"), (2, "hot"), (3, None)],
    )
    def test_glycol_tank_state(self, mock_coordinator, raw, expected):
        """glycolstate maps 0-2 to named states; others are unknown."""
        mock_coordinator.data = make_rixens_data(glycol_state=raw)
        sensor = self._make_sensor(mock_coordinator, "glycol_tank")
        assert sensor.native_value == expected

    def test_glycol_tank_is_enum_with_options(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator, "glycol_tank")
        assert sensor.device_class == SensorDeviceClass.ENUM
        assert sensor.options == ["not_ready", "ready", "hot"]

    @pytest.mark.parametrize("raw", [1795, None])
    def test_hot_water_timer(self, mock_coordinator, raw):
        """Remaining Hot Water timer in seconds; unknown when not running."""
        mock_coordinator.data = make_rixens_data(cnst_heat_timer_val=raw)
        sensor = self._make_sensor(mock_coordinator, "hot_water_timer")
        assert sensor.native_value == raw
        assert sensor.device_class == SensorDeviceClass.DURATION
        assert sensor.native_unit_of_measurement == UnitOfTime.SECONDS
        assert sensor.entity_category is None  # shown on dashboards by default

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (0, "off"),
            (10, "starting_cold"),
            (12, "starting_warm"),
            (13, "cold_blow"),
            (15, "stabilizing_flame"),
            (20, "running"),
            (30, "shutting_down"),
            (31, "shutting_down_to_standby"),
            (40, "paused"),
            (200, "error"),
            (11, None),
        ],
    )
    def test_heater_state(self, mock_coordinator, raw, expected):
        """heaterstate maps known values to named states; others are unknown."""
        mock_coordinator.data = make_rixens_data(heater_state=raw)
        sensor = self._make_sensor(mock_coordinator, "heater_state")
        assert sensor.native_value == expected
        assert sensor.extra_state_attributes == {"raw_state": raw}

    def test_heater_state_is_diagnostic_enum(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator, "heater_state")
        assert sensor.device_class == SensorDeviceClass.ENUM
        assert sensor.options == [
            "off",
            "starting_cold",
            "starting_warm",
            "cold_blow",
            "stabilizing_flame",
            "running",
            "shutting_down",
            "shutting_down_to_standby",
            "paused",
            "error",
        ]
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC

    def test_fault_sensors_are_diagnostic_enums(self, mock_coordinator):
        for key in ("active_fault", "last_fault"):
            sensor = self._make_sensor(mock_coordinator, key)
            assert sensor.device_class == SensorDeviceClass.ENUM
            assert sensor.options == FAULT_OPTIONS
            assert sensor.entity_category == EntityCategory.DIAGNOSTIC

    @pytest.mark.parametrize(
        ("af", "expected", "p_code", "fault_class"),
        [
            (0, "no_fault", None, None),
            (48, "metering_pump_open", "P000200", "fuel_supply_or_pump"),
            (123, "other", None, None),
            (255, None, None, None),
        ],
    )
    def test_active_fault(self, mock_coordinator, af, expected, p_code, fault_class):
        mock_coordinator.data = make_rixens_data(faults={"AF": af})
        sensor = self._make_sensor(mock_coordinator, "active_fault")
        assert sensor.native_value == expected
        assert sensor.extra_state_attributes == {
            "code": af,
            "p_code": p_code,
            "fault_class": fault_class,
        }

    def test_active_fault_not_reported(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(faults={})
        sensor = self._make_sensor(mock_coordinator, "active_fault")
        assert sensor.native_value is None
        assert sensor.extra_state_attributes == {
            "code": None,
            "p_code": None,
            "fault_class": None,
        }

    def test_last_fault_uses_f1(self, mock_coordinator):
        """F1 is the most recent stored fault."""
        mock_coordinator.data = make_rixens_data(
            faults={"AF": 0, "F1": 52, "F2": 50, "F3": 0, "F4": 0, "F5": 11}
        )
        sensor = self._make_sensor(mock_coordinator, "last_fault")
        assert sensor.native_value == "start_failed"
        assert sensor.extra_state_attributes == {
            "code": 52,
            "p_code": "P00012A",
            "fault_class": "fuel_supply_or_pump",
            "stored_fault_codes": [52, 50, 0, 0, 11],
        }

    def test_last_fault_no_stored_faults(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(faults={"AF": 0})
        sensor = self._make_sensor(mock_coordinator, "last_fault")
        assert sensor.native_value is None
        assert sensor.extra_state_attributes == {
            "code": None,
            "p_code": None,
            "fault_class": None,
            "stored_fault_codes": [],
        }

    def test_sensor_without_attributes_fn(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator, "battery_voltage")
        assert sensor.extra_state_attributes is None

    def test_native_value_battery(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator, "battery_voltage")
        assert sensor.native_value == 12.5

    def test_native_value_flame_temp(self, mock_coordinator):
        """Rounded to 1 °C so it isn't recorded on every poll (#88)."""
        sensor = self._make_sensor(mock_coordinator, "flame_temperature")
        assert sensor.native_value == 145

    @pytest.mark.parametrize(
        ("key", "expected"),
        [("inlet_temperature", 70.8), ("outlet_temperature", 73.0)],
    )
    def test_native_value_glycol_temps_rounded(self, mock_coordinator, key, expected):
        """Rounded to 0.1 °C so they aren't recorded on every poll (#88)."""
        sensor = self._make_sensor(mock_coordinator, key)
        assert sensor.native_value == expected

    def test_system_uptime_is_boot_time(self, mock_coordinator):
        """Uptime is reported as the boot time, to the minute (#88)."""
        now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
        mock_coordinator.data = make_rixens_data(uptime=3600 + 20)
        sensor = self._make_sensor(mock_coordinator, "system_uptime")
        assert sensor.device_class == SensorDeviceClass.TIMESTAMP
        assert sensor.state_class is None
        assert sensor.native_unit_of_measurement is None
        with patch("homeassistant.util.dt.utcnow", return_value=now):
            assert sensor.native_value == datetime(2026, 10, 28, 11, 0, tzinfo=UTC)

    def test_system_uptime_steady_between_polls(self, mock_coordinator):
        """Boot time stays put across polls, even across a minute boundary."""
        now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
        sensor = self._make_sensor(mock_coordinator, "system_uptime")
        values = set()
        # Poll jitter puts the computed boot time either side of 11:00:30
        for poll, uptime in enumerate((3570, 3574, 3581, 3583, 3590)):
            mock_coordinator.data = make_rixens_data(uptime=uptime)
            with patch(
                "homeassistant.util.dt.utcnow",
                return_value=now + timedelta(seconds=5 * poll),
            ):
                values.add(sensor.native_value)
        assert len(values) == 1

    def test_system_uptime_changes_on_reboot(self, mock_coordinator):
        now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
        sensor = self._make_sensor(mock_coordinator, "system_uptime")
        with patch("homeassistant.util.dt.utcnow", return_value=now):
            mock_coordinator.data = make_rixens_data(uptime=86400)
            assert sensor.native_value == datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
            mock_coordinator.data = make_rixens_data(uptime=120)
            assert sensor.native_value == datetime(2026, 10, 28, 11, 58, tzinfo=UTC)

    def test_native_value_runtime(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator, "heater_runtime")
        assert sensor.native_value == 114236

    def test_runtime_unit_is_minutes(self, mock_coordinator):
        """heater1.runtime counts minutes (verified against live data, #72)."""
        sensor = self._make_sensor(mock_coordinator, "heater_runtime")
        assert sensor.native_unit_of_measurement == UnitOfTime.MINUTES

    def test_runtime_displays_in_hours(self, mock_coordinator):
        """New installs show runtime in hours by default."""
        sensor = self._make_sensor(mock_coordinator, "heater_runtime")
        assert sensor.suggested_unit_of_measurement == UnitOfTime.HOURS
        assert sensor.suggested_display_precision == 1

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
        mock_coordinator.data = make_rixens_data(cnst_heat=1, cnst_heat_timer_val=1795)
        for desc in SENSOR_DESCRIPTIONS:
            sensor = RixensSensor(mock_coordinator, desc)
            assert sensor.native_value is not None


class TestFuelUsedSensor:
    """Tests for the cumulative fuel used sensor (#86)."""

    # 1.6 Hz at the default dose
    RATE = 1.6 * DEFAULT_FUEL_DOSE * 3600  # mL/h

    @pytest.fixture
    def clock(self):
        with patch("custom_components.rixens.sensor.monotonic") as clock:
            clock.return_value = 1000.0
            yield clock

    def _make_sensor(self, mock_coordinator) -> RixensFuelUsedSensor:
        sensor = RixensFuelUsedSensor(mock_coordinator)
        sensor.async_write_ha_state = MagicMock()
        return sensor

    def _poll(self, sensor, mock_coordinator, clock, seconds, **data):
        clock.return_value += seconds
        mock_coordinator.data = make_rixens_data(**data)
        sensor._handle_coordinator_update()

    def test_attributes(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator)
        assert sensor.unique_id == "test_entry_id_fuel_used"
        assert sensor.translation_key == "fuel_used"
        assert sensor.device_class == SensorDeviceClass.VOLUME
        assert sensor.state_class == SensorStateClass.TOTAL_INCREASING
        assert sensor.native_unit_of_measurement == UnitOfVolume.MILLILITERS
        assert sensor.entity_category is None
        assert sensor.native_value == 0

    def test_accumulates_previous_rate(self, mock_coordinator, clock):
        sensor = self._make_sensor(mock_coordinator)
        sensor._handle_coordinator_update()  # baseline at 1.6 Hz
        self._poll(sensor, mock_coordinator, clock, 5, dosing_pump=0.0)
        # Left sum: the 5 s before the pump stopped count at 1.6 Hz
        assert sensor.native_value == round(self.RATE * 5 / 3600, 2)
        self._poll(sensor, mock_coordinator, clock, 5, dosing_pump=0.0)
        assert sensor.native_value == round(self.RATE * 5 / 3600, 2)
        sensor.async_write_ha_state.assert_called()

    def test_uses_configured_dose(self, mock_coordinator, clock):
        mock_coordinator.config_entry.options = {CONF_FUEL_DOSE: 0.05}
        sensor = self._make_sensor(mock_coordinator)
        sensor._handle_coordinator_update()
        self._poll(sensor, mock_coordinator, clock, 3600)
        # An hour gap is skipped, so poll in steps instead
        assert sensor.native_value == 0
        for _ in range(720):
            self._poll(sensor, mock_coordinator, clock, 5)
        assert sensor.native_value == pytest.approx(1.6 * 0.05 * 3600, abs=0.01)

    def test_skips_stale_data_from_failed_poll(self, mock_coordinator, clock):
        sensor = self._make_sensor(mock_coordinator)
        sensor._handle_coordinator_update()
        # A failed poll returns the same data object: nothing is added yet
        clock.return_value += 5
        sensor._handle_coordinator_update()
        assert sensor.native_value == 0
        # The next fresh poll counts the whole 10 s
        self._poll(sensor, mock_coordinator, clock, 5)
        assert sensor.native_value == round(self.RATE * 10 / 3600, 2)

    def test_skips_long_gap(self, mock_coordinator, clock):
        sensor = self._make_sensor(mock_coordinator)
        sensor._handle_coordinator_update()
        self._poll(sensor, mock_coordinator, clock, FUEL_USED_MAX_GAP + 1)
        assert sensor.native_value == 0
        self._poll(sensor, mock_coordinator, clock, 5)
        assert sensor.native_value == round(self.RATE * 5 / 3600, 2)

    def test_no_data(self, mock_coordinator, clock):
        mock_coordinator.data = None
        sensor = self._make_sensor(mock_coordinator)
        sensor._handle_coordinator_update()
        assert sensor.native_value == 0

    @pytest.mark.parametrize(
        ("restored", "expected"), [("1234.5", 1234.5), (None, 0), ("bad", 0)]
    )
    async def test_restores_total(self, mock_coordinator, clock, restored, expected):
        sensor = self._make_sensor(mock_coordinator)
        last = MagicMock(native_value=restored)
        with (
            patch(
                "homeassistant.helpers.update_coordinator.CoordinatorEntity"
                ".async_added_to_hass",
                AsyncMock(),
            ),
            patch.object(
                sensor, "async_get_last_sensor_data", AsyncMock(return_value=last)
            ),
        ):
            await sensor.async_added_to_hass()
        assert sensor.native_value == expected
        # The current poll is the baseline: time before the restart isn't counted
        self._poll(sensor, mock_coordinator, clock, 5)
        assert sensor.native_value == round(expected + self.RATE * 5 / 3600, 2)

    async def test_nothing_to_restore(self, mock_coordinator):
        sensor = self._make_sensor(mock_coordinator)
        with (
            patch(
                "homeassistant.helpers.update_coordinator.CoordinatorEntity"
                ".async_added_to_hass",
                AsyncMock(),
            ),
            patch.object(
                sensor, "async_get_last_sensor_data", AsyncMock(return_value=None)
            ),
        ):
            await sensor.async_added_to_hass()
        assert sensor.native_value == 0


async def test_setup_entry_adds_fuel_used(mock_coordinator):
    from custom_components.rixens.const import DOMAIN
    from custom_components.rixens.sensor import async_setup_entry

    hass = MagicMock()
    hass.data = {DOMAIN: {"test_entry_id": mock_coordinator}}
    add_entities = MagicMock()
    await async_setup_entry(hass, mock_coordinator.config_entry, add_entities)
    entities = add_entities.call_args.args[0]
    assert len(entities) == len(SENSOR_DESCRIPTIONS) + 1
    assert isinstance(entities[-1], RixensFuelUsedSensor)
