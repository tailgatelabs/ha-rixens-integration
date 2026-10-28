"""Tests for the Rixens integration __init__.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.rixens import (
    PLATFORMS,
    async_setup_entry,
    async_unload_entry,
    async_update_options,
)
from custom_components.rixens.const import CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN


@pytest.fixture
def mock_hass():
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_reload = AsyncMock()
    return hass


@pytest.fixture
def mock_entry():
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"
    entry.data = {CONF_HOST: "192.168.1.100", CONF_PORT: DEFAULT_PORT}
    entry.options = {}
    entry.add_update_listener = MagicMock(return_value=MagicMock())
    entry.async_on_unload = MagicMock()
    return entry


class TestAsyncSetupEntry:
    """Tests for async_setup_entry."""

    async def test_setup_success(self, mock_hass, mock_entry):
        with patch("custom_components.rixens.RixensCoordinator") as mock_coord_cls:
            mock_coord = AsyncMock()
            mock_coord.async_config_entry_first_refresh = AsyncMock()
            mock_coord_cls.return_value = mock_coord

            result = await async_setup_entry(mock_hass, mock_entry)
            assert result is True
            assert DOMAIN in mock_hass.data
            assert mock_hass.data[DOMAIN][mock_entry.entry_id] is mock_coord
            mock_hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
                mock_entry, PLATFORMS
            )
            mock_entry.async_on_unload.assert_called_once()


class TestAsyncUnloadEntry:
    """Tests for async_unload_entry."""

    async def test_unload_success(self, mock_hass, mock_entry):
        mock_hass.data[DOMAIN] = {mock_entry.entry_id: MagicMock()}

        result = await async_unload_entry(mock_hass, mock_entry)
        assert result is True
        assert mock_entry.entry_id not in mock_hass.data[DOMAIN]

    async def test_unload_failure(self, mock_hass, mock_entry):
        mock_hass.data[DOMAIN] = {mock_entry.entry_id: MagicMock()}
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        result = await async_unload_entry(mock_hass, mock_entry)
        assert result is False
        # Entry should still be in data since unload failed
        assert mock_entry.entry_id in mock_hass.data[DOMAIN]


class TestAsyncUpdateOptions:
    """Tests for async_update_options."""

    async def test_reloads_entry(self, mock_hass, mock_entry):
        await async_update_options(mock_hass, mock_entry)
        mock_hass.config_entries.async_reload.assert_awaited_once_with(
            mock_entry.entry_id
        )
