"""Tests for the Rixens data update coordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.rixens.api import RixensApiError, RixensConnectionError
from custom_components.rixens.const import CONF_HOST, CONF_PORT, DEFAULT_PORT
from custom_components.rixens.coordinator import (
    COMMAND_REFRESH_DELAY,
    MAX_FAILED_UPDATES_BEFORE_UNAVAILABLE,
    SCAN_INTERVAL,
    RixensCoordinator,
)

from .conftest import make_rixens_data


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    return hass


@pytest.fixture
def mock_entry():
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"
    entry.data = {CONF_HOST: "192.168.1.100", CONF_PORT: DEFAULT_PORT}
    entry.options = {}
    return entry


def _make_coordinator(mock_hass, mock_entry):
    """Create a RixensCoordinator, patching out HA internals."""
    with patch(
        "custom_components.rixens.coordinator.async_get_clientsession"
    ), patch(
        "homeassistant.helpers.frame.report_usage"
    ):
        coordinator = RixensCoordinator(mock_hass, mock_entry)
    return coordinator


class TestCoordinatorInit:
    """Tests for coordinator initialization."""

    def test_init(self, mock_hass, mock_entry):
        coordinator = _make_coordinator(mock_hass, mock_entry)
        assert coordinator.config_entry is mock_entry
        assert coordinator._failed_update_count == 0
        assert coordinator._last_successful_update is None
        assert coordinator._is_available is True


class TestScanInterval:
    """Tests for polling configuration."""

    def test_interval_is_8_seconds(self, mock_hass, mock_entry):
        coordinator = _make_coordinator(mock_hass, mock_entry)
        assert SCAN_INTERVAL == timedelta(seconds=8)
        assert coordinator.update_interval == timedelta(seconds=8)

    def test_availability_grace_about_50_seconds(self):
        grace = MAX_FAILED_UPDATES_BEFORE_UNAVAILABLE * SCAN_INTERVAL.total_seconds()
        assert 45 <= grace <= 50


class TestRefreshAfterCommand:
    """Tests for the delayed post-command refresh."""

    def test_schedules_refresh_after_delay(self, mock_hass, mock_entry):
        coordinator = _make_coordinator(mock_hass, mock_entry)
        with patch(
            "custom_components.rixens.coordinator.async_call_later"
        ) as call_later:
            coordinator.async_refresh_after_command()
        call_later.assert_called_once_with(
            mock_hass, COMMAND_REFRESH_DELAY, coordinator._async_command_refresh
        )

    def test_rapid_commands_collapse_into_one_refresh(self, mock_hass, mock_entry):
        coordinator = _make_coordinator(mock_hass, mock_entry)
        unsubs = [MagicMock(), MagicMock(), MagicMock()]
        with patch(
            "custom_components.rixens.coordinator.async_call_later",
            side_effect=unsubs,
        ):
            for _ in unsubs:
                coordinator.async_refresh_after_command()
        # Every earlier timer was cancelled; only the last stays pending
        unsubs[0].assert_called_once()
        unsubs[1].assert_called_once()
        unsubs[2].assert_not_called()

    async def test_refresh_runs_when_timer_fires(self, mock_hass, mock_entry):
        coordinator = _make_coordinator(mock_hass, mock_entry)
        coordinator.async_refresh = AsyncMock()
        coordinator._command_refresh_unsub = MagicMock()
        await coordinator._async_command_refresh(None)
        coordinator.async_refresh.assert_awaited_once()
        assert coordinator._command_refresh_unsub is None

    async def test_shutdown_cancels_pending_refresh(self, mock_hass, mock_entry):
        coordinator = _make_coordinator(mock_hass, mock_entry)
        unsub = MagicMock()
        coordinator._command_refresh_unsub = unsub
        await coordinator.async_shutdown()
        unsub.assert_called_once()
        assert coordinator._command_refresh_unsub is None


class TestAsyncUpdateData:
    """Tests for the _async_update_data method."""

    async def test_successful_update(self, mock_hass, mock_entry):
        coordinator = _make_coordinator(mock_hass, mock_entry)
        coordinator.api = AsyncMock()
        coordinator.api.get_status = AsyncMock(return_value=make_rixens_data())

        result = await coordinator._async_update_data()
        assert result.current_temp == 17.1
        assert coordinator._failed_update_count == 0
        assert coordinator._is_available is True
        assert coordinator._last_successful_update is not None

    async def test_successful_update_after_failures(self, mock_hass, mock_entry):
        coordinator = _make_coordinator(mock_hass, mock_entry)
        coordinator.api = AsyncMock()
        coordinator.api.get_status = AsyncMock(return_value=make_rixens_data())
        coordinator._failed_update_count = 3

        result = await coordinator._async_update_data()
        assert coordinator._failed_update_count == 0
        assert coordinator._is_available is True

    async def test_failure_with_cached_data(self, mock_hass, mock_entry):
        coordinator = _make_coordinator(mock_hass, mock_entry)
        coordinator.api = AsyncMock()
        coordinator.api.get_status = AsyncMock(
            side_effect=RixensConnectionError("timeout")
        )
        coordinator.data = make_rixens_data()

        result = await coordinator._async_update_data()
        assert result.current_temp == 17.1
        assert coordinator._failed_update_count == 1

    async def test_failure_beyond_threshold_raises(self, mock_hass, mock_entry):
        coordinator = _make_coordinator(mock_hass, mock_entry)
        coordinator.api = AsyncMock()
        coordinator.api.get_status = AsyncMock(
            side_effect=RixensConnectionError("timeout")
        )
        coordinator._failed_update_count = MAX_FAILED_UPDATES_BEFORE_UNAVAILABLE
        coordinator.data = make_rixens_data()

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator._is_available is False

    async def test_first_failure_no_cached_data(self, mock_hass, mock_entry):
        """First failure with no cached data raises UpdateFailed."""
        coordinator = _make_coordinator(mock_hass, mock_entry)
        coordinator.api = AsyncMock()
        coordinator.api.get_status = AsyncMock(
            side_effect=RixensApiError("error")
        )

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    async def test_marks_unavailable_once(self, mock_hass, mock_entry):
        """_is_available transitions to False only once."""
        coordinator = _make_coordinator(mock_hass, mock_entry)
        coordinator.api = AsyncMock()
        coordinator.api.get_status = AsyncMock(
            side_effect=RixensConnectionError("timeout")
        )
        coordinator._failed_update_count = MAX_FAILED_UPDATES_BEFORE_UNAVAILABLE

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator._is_available is False

        # Second failure — already unavailable
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator._is_available is False


class TestIsAvailable:
    """Tests for the is_available property."""

    def test_available_by_default(self, mock_hass, mock_entry):
        coordinator = _make_coordinator(mock_hass, mock_entry)
        assert coordinator.is_available is True

    def test_reflects_internal_state(self, mock_hass, mock_entry):
        coordinator = _make_coordinator(mock_hass, mock_entry)
        coordinator._is_available = False
        assert coordinator.is_available is False
