"""Tests for the Rixens fan platform."""

from __future__ import annotations

from custom_components.rixens.api import Command
from custom_components.rixens.fan import (
    PRESET_MODE_AUTO,
    RixensFan,
    compute_fan_speed,
)

from .conftest import make_rixens_data, sent_commands


class TestComputeFanSpeed:
    """Tests for the compute_fan_speed helper."""

    def test_fan_off_returns_zero(self):
        data = make_rixens_data(fan_state=False, fan_speed="50")
        assert compute_fan_speed(data) == 0

    def test_device_fan_off_returns_zero(self):
        data = make_rixens_data(fan_state=True, fan_speed="Off")
        assert compute_fan_speed(data) == 0

    def test_auto_mode_returns_pid_speed(self):
        data = make_rixens_data(fan_state=True, fan_speed="Auto", pid_speed=73)
        assert compute_fan_speed(data) == 73

    def test_auto_mode_pid_zero(self):
        data = make_rixens_data(fan_state=True, fan_speed="Auto", pid_speed=0)
        assert compute_fan_speed(data) == 0

    def test_auto_mode_pid_clamped_to_max(self):
        data = make_rixens_data(fan_state=True, fan_speed="Auto", pid_speed=150)
        assert compute_fan_speed(data) == 100

    def test_manual_mode_returns_speed(self):
        data = make_rixens_data(fan_state=True, fan_speed="50")
        assert compute_fan_speed(data) == 50

    def test_manual_mode_clamped_to_min(self):
        data = make_rixens_data(fan_state=True, fan_speed="5")
        assert compute_fan_speed(data) == 10

    def test_manual_mode_clamped_to_max(self):
        data = make_rixens_data(fan_state=True, fan_speed="120")
        assert compute_fan_speed(data) == 100

    def test_manual_mode_invalid_returns_zero(self):
        data = make_rixens_data(fan_state=True, fan_speed="invalid")
        assert compute_fan_speed(data) == 0


class TestFanEntity:
    """Tests for the RixensFan entity."""

    def test_unique_id(self, mock_coordinator):
        entity = RixensFan(mock_coordinator)
        assert entity._attr_unique_id == "test_entry_id_fan"

    def test_is_on_true(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_state=True)
        entity = RixensFan(mock_coordinator)
        assert entity.is_on is True

    def test_is_on_false(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_state=False)
        entity = RixensFan(mock_coordinator)
        assert entity.is_on is False

    def test_is_on_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        entity = RixensFan(mock_coordinator)
        assert entity.is_on is None

    def test_percentage_manual(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_state=True, fan_speed="50")
        entity = RixensFan(mock_coordinator)
        assert entity.percentage == 50

    def test_percentage_auto(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(
            fan_state=True, fan_speed="Auto", pid_speed=73
        )
        entity = RixensFan(mock_coordinator)
        assert entity.percentage == 73

    def test_percentage_off(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_state=False)
        entity = RixensFan(mock_coordinator)
        assert entity.percentage == 0

    def test_percentage_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        entity = RixensFan(mock_coordinator)
        assert entity.percentage is None

    def test_preset_mode_auto(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_speed="Auto")
        entity = RixensFan(mock_coordinator)
        assert entity.preset_mode == PRESET_MODE_AUTO

    def test_preset_mode_manual(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_speed="50")
        entity = RixensFan(mock_coordinator)
        assert entity.preset_mode is None

    def test_preset_mode_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        entity = RixensFan(mock_coordinator)
        assert entity.preset_mode is None

    def test_extra_attributes_auto(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(
            fan_state=True, fan_speed="Auto", pid_speed=73
        )
        entity = RixensFan(mock_coordinator)
        attrs = entity.extra_state_attributes
        assert attrs["mode"] == "auto"
        assert attrs["actual_speed"] == 73
        assert "configured_speed" not in attrs

    def test_extra_attributes_manual(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(
            fan_state=True, fan_speed="50", pid_speed=48
        )
        entity = RixensFan(mock_coordinator)
        attrs = entity.extra_state_attributes
        assert attrs["mode"] == "manual"
        assert attrs["actual_speed"] == 48
        assert attrs["configured_speed"] == 50

    def test_actual_speed_not_recorded(self, mock_coordinator):
        """actual_speed changes every poll, so it is kept out of the recorder (#88)."""
        entity = RixensFan(mock_coordinator)
        assert "actual_speed" in entity._unrecorded_attributes

    def test_extra_attributes_off(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_state=False)
        entity = RixensFan(mock_coordinator)
        attrs = entity.extra_state_attributes
        assert attrs["mode"] == "off"

    def test_extra_attributes_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        entity = RixensFan(mock_coordinator)
        assert entity.extra_state_attributes == {}

    def test_extra_attributes_invalid_speed(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(fan_state=True, fan_speed="bad")
        entity = RixensFan(mock_coordinator)
        attrs = entity.extra_state_attributes
        assert attrs["mode"] == "manual"
        assert "configured_speed" not in attrs


class TestFanActions:
    """Tests for fan entity actions."""

    async def test_turn_on(self, mock_coordinator):
        entity = RixensFan(mock_coordinator)
        await entity.async_turn_on()
        assert sent_commands(mock_coordinator.api) == [(Command.FAN_STATE, True)]
        mock_coordinator.async_refresh_after_command.assert_called_once()
        assert entity.is_on is True

    async def test_turn_on_with_preset_auto(self, mock_coordinator):
        entity = RixensFan(mock_coordinator)
        await entity.async_turn_on(preset_mode=PRESET_MODE_AUTO)
        assert sent_commands(mock_coordinator.api) == [
            (Command.FAN_STATE, True),
            (Command.FAN_SPEED, 999),
        ]

    async def test_turn_on_with_percentage(self, mock_coordinator):
        entity = RixensFan(mock_coordinator)
        await entity.async_turn_on(percentage=50)
        assert sent_commands(mock_coordinator.api) == [
            (Command.FAN_STATE, True),
            (Command.FAN_SPEED, 50),
        ]

    async def test_turn_off(self, mock_coordinator):
        entity = RixensFan(mock_coordinator)
        await entity.async_turn_off()
        assert sent_commands(mock_coordinator.api) == [(Command.FAN_STATE, False)]
        mock_coordinator.async_refresh_after_command.assert_called_once()
        assert entity.is_on is False
        assert entity.percentage == 0

    async def test_set_percentage(self, mock_coordinator):
        entity = RixensFan(mock_coordinator)
        await entity.async_set_percentage(50)
        assert sent_commands(mock_coordinator.api) == [
            (Command.FAN_STATE, True),
            (Command.FAN_SPEED, 50),
        ]
        mock_coordinator.async_refresh_after_command.assert_called_once()
        assert entity.is_on is True
        assert entity.percentage == 50
        assert entity.preset_mode is None

    async def test_set_percentage_zero_turns_off(self, mock_coordinator):
        entity = RixensFan(mock_coordinator)
        await entity.async_set_percentage(0)
        assert sent_commands(mock_coordinator.api) == [(Command.FAN_STATE, False)]

    async def test_set_preset_mode_auto(self, mock_coordinator):
        entity = RixensFan(mock_coordinator)
        await entity.async_set_preset_mode(PRESET_MODE_AUTO)
        assert sent_commands(mock_coordinator.api) == [
            (Command.FAN_STATE, True),
            (Command.FAN_SPEED, 999),
        ]
        mock_coordinator.async_refresh_after_command.assert_called_once()
        assert entity.is_on is True
        assert entity.preset_mode == PRESET_MODE_AUTO
