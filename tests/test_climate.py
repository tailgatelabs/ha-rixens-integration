"""Tests for the Rixens climate platform."""

from __future__ import annotations

from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_HOME,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE

from custom_components.rixens.api import Command
from custom_components.rixens.climate import RixensClimate

from .conftest import make_rixens_data, sent_commands

# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestClimateProperties:
    """Tests for climate entity properties."""

    def test_current_temperature(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        assert climate.current_temperature == 17.1

    def test_current_temperature_no_cabin_sensor(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(current_temp=None)
        climate = RixensClimate(mock_coordinator)
        assert climate.current_temperature is None

    def test_current_temperature_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        climate = RixensClimate(mock_coordinator)
        assert climate.current_temperature is None

    def test_target_temperature(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        assert climate.target_temperature == 18.0

    def test_target_temperature_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        climate = RixensClimate(mock_coordinator)
        assert climate.target_temperature is None

    def test_unique_id(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        assert climate._attr_unique_id == "test_entry_id_climate"


class TestHvacMode:
    """Tests for HVAC mode property."""

    def test_heat_when_furnace_enabled(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(furnace_src=2)
        climate = RixensClimate(mock_coordinator)
        assert climate.hvac_mode == HVACMode.HEAT

    def test_heat_when_electric_enabled(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(furnace_src=0, electric_src=1)
        climate = RixensClimate(mock_coordinator)
        assert climate.hvac_mode == HVACMode.HEAT

    def test_heat_when_engine_enabled(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(furnace_src=0, engine_src=1)
        climate = RixensClimate(mock_coordinator)
        assert climate.hvac_mode == HVACMode.HEAT

    def test_off_when_all_disabled(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(
            furnace_src=0, electric_src=0, engine_src=0
        )
        climate = RixensClimate(mock_coordinator)
        assert climate.hvac_mode == HVACMode.OFF

    def test_off_when_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        climate = RixensClimate(mock_coordinator)
        assert climate.hvac_mode == HVACMode.OFF


class TestHvacAction:
    """Tests for HVAC action property."""

    def test_off_when_all_disabled(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(
            furnace_src=0, electric_src=0, engine_src=0
        )
        climate = RixensClimate(mock_coordinator)
        assert climate.hvac_action == HVACAction.OFF

    def test_heating_when_active(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(
            system_heat=True, furnace_src=2, electric_src=0, engine_src=0
        )
        climate = RixensClimate(mock_coordinator)
        assert climate.hvac_action == HVACAction.HEATING

    def test_idle_when_calling_but_not_heating(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(
            system_heat=True, furnace_src=1, electric_src=0, engine_src=0
        )
        climate = RixensClimate(mock_coordinator)
        assert climate.hvac_action == HVACAction.IDLE

    def test_idle_when_not_calling_for_heat(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(
            system_heat=False, furnace_src=2, electric_src=0, engine_src=0
        )
        climate = RixensClimate(mock_coordinator)
        assert climate.hvac_action == HVACAction.IDLE

    def test_none_when_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        climate = RixensClimate(mock_coordinator)
        assert climate.hvac_action is None


class TestFanMode:
    """Tests for fan mode property."""

    def test_off_mode(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_speed="Off")
        climate = RixensClimate(mock_coordinator)
        assert climate.fan_mode == "off"

    def test_auto_mode(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_speed="Auto")
        climate = RixensClimate(mock_coordinator)
        assert climate.fan_mode == "auto"

    def test_manual_speed(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_speed="50")
        climate = RixensClimate(mock_coordinator)
        assert climate.fan_mode == "50"

    def test_manual_speed_snapped(self, mock_coordinator):
        """Non-standard speed is snapped to nearest valid step."""
        mock_coordinator.data = make_rixens_data(fan_speed="47")
        climate = RixensClimate(mock_coordinator)
        assert climate.fan_mode == "50"

    def test_manual_speed_clamped_low(self, mock_coordinator):
        """Speed below minimum is clamped to minimum."""
        mock_coordinator.data = make_rixens_data(fan_speed="3")
        climate = RixensClimate(mock_coordinator)
        assert climate.fan_mode == "10"

    def test_unparseable_falls_back_to_auto(self, mock_coordinator):
        """Unexpected string value falls back to auto."""
        mock_coordinator.data = make_rixens_data(fan_speed="unknown")
        climate = RixensClimate(mock_coordinator)
        assert climate.fan_mode == "auto"

    def test_none_when_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        climate = RixensClimate(mock_coordinator)
        assert climate.fan_mode is None


class TestPresetMode:
    """Tests for preset mode property."""

    def test_default_no_preset(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        assert climate.preset_mode is None

    def test_preset_mode_tracked(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        climate._preset_mode = PRESET_HOME
        assert climate.preset_mode == PRESET_HOME


class TestExtraAttributes:
    """Tests for extra state attributes."""

    def test_attributes_with_data(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(
            furnace_src=2, electric_src=0, engine_src=0, system_heat=True
        )
        climate = RixensClimate(mock_coordinator)
        attrs = climate.extra_state_attributes
        assert attrs["furnace_enabled"] is True
        assert attrs["furnace_active"] is True
        assert attrs["electric_heat_enabled"] is False
        assert attrs["electric_heat_active"] is False
        assert attrs["engine_heat_enabled"] is False
        assert attrs["system_calling_for_heat"] is True
        assert "current_humidity" in attrs

    def test_current_humidity_not_recorded(self, mock_coordinator):
        """Duplicates the humidity sensor, so it is kept out of the recorder (#88)."""
        climate = RixensClimate(mock_coordinator)
        assert "current_humidity" in climate._unrecorded_attributes

    def test_attributes_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        climate = RixensClimate(mock_coordinator)
        assert climate.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


class TestClimateActions:
    """Tests for climate control actions."""

    async def test_set_temperature(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        await climate.async_set_temperature(**{ATTR_TEMPERATURE: 22.5})
        mock_coordinator.api.set_temperature.assert_awaited_once_with(22.5)
        mock_coordinator.async_refresh_after_command.assert_called_once()
        assert climate.target_temperature == 22.5
        assert climate._preset_mode is None

    async def test_set_temperature_no_value(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        await climate.async_set_temperature()
        mock_coordinator.api.set_temperature.assert_not_awaited()

    async def test_set_hvac_mode_heat_default(self, mock_coordinator):
        """Turning on with no previous state defaults to furnace."""
        climate = RixensClimate(mock_coordinator)
        await climate.async_set_hvac_mode(HVACMode.HEAT)
        assert sent_commands(mock_coordinator.api) == [(Command.FURNACE, True)]

    async def test_set_hvac_mode_heat_restores_sources(self, mock_coordinator):
        """Turning on restores previously enabled sources."""
        climate = RixensClimate(mock_coordinator)
        climate._last_heat_sources = {"furnace": True, "electric": True}
        await climate.async_set_hvac_mode(HVACMode.HEAT)
        assert sent_commands(mock_coordinator.api) == [
            (Command.FURNACE, True),
            (Command.ELECTRIC_HEAT, True),
        ]

    async def test_set_hvac_mode_heat_restores_only_furnace(self, mock_coordinator):
        """Restores only previously-enabled sources."""
        climate = RixensClimate(mock_coordinator)
        climate._last_heat_sources = {"furnace": True, "electric": False}
        await climate.async_set_hvac_mode(HVACMode.HEAT)
        assert sent_commands(mock_coordinator.api) == [(Command.FURNACE, True)]

    async def test_set_hvac_mode_off_saves_and_disables(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(furnace_src=2, electric_src=1)
        climate = RixensClimate(mock_coordinator)
        await climate.async_set_hvac_mode(HVACMode.OFF)
        assert climate._last_heat_sources == {"furnace": True, "electric": True}
        assert sent_commands(mock_coordinator.api) == [
            (Command.FURNACE, False),
            (Command.ELECTRIC_HEAT, False),
        ]

    async def test_set_fan_mode_off(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        await climate.async_set_fan_mode("off")
        assert sent_commands(mock_coordinator.api) == [(Command.FAN_STATE, False)]

    async def test_set_fan_mode_auto(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        await climate.async_set_fan_mode("auto")
        assert sent_commands(mock_coordinator.api) == [
            (Command.FAN_STATE, True),
            (Command.FAN_SPEED, 999),
        ]

    async def test_set_fan_mode_manual(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        await climate.async_set_fan_mode("50")
        assert sent_commands(mock_coordinator.api) == [
            (Command.FAN_STATE, True),
            (Command.FAN_SPEED, 50),
        ]

    async def test_set_fan_mode_out_of_range(self, mock_coordinator):
        """Fan speed outside valid range is not sent and no refresh is triggered."""
        climate = RixensClimate(mock_coordinator)
        await climate.async_set_fan_mode("5")
        mock_coordinator.api.send_command.assert_not_awaited()
        mock_coordinator.async_refresh_after_command.assert_not_called()

    async def test_set_preset_mode(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        await climate.async_set_preset_mode(PRESET_AWAY)
        mock_coordinator.api.set_temperature.assert_awaited_once_with(10.0)
        assert climate._preset_mode == PRESET_AWAY

    async def test_set_preset_mode_custom_temps(self, mock_coordinator):
        mock_coordinator.config_entry.options = {"preset_away_temp": 8.0}
        climate = RixensClimate(mock_coordinator)
        await climate.async_set_preset_mode(PRESET_AWAY)
        mock_coordinator.api.set_temperature.assert_awaited_once_with(8.0)

    async def test_set_invalid_preset_mode(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        await climate.async_set_preset_mode("nonexistent")
        mock_coordinator.api.set_temperature.assert_not_awaited()

    async def test_turn_on(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        await climate.async_turn_on()
        assert sent_commands(mock_coordinator.api) == [(Command.FURNACE, True)]

    async def test_turn_off(self, mock_coordinator):
        climate = RixensClimate(mock_coordinator)
        await climate.async_turn_off()
        assert sent_commands(mock_coordinator.api) == [
            (Command.FURNACE, False),
            (Command.ELECTRIC_HEAT, False),
        ]
