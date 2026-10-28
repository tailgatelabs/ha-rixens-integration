"""Tests for the Rixens config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.rixens.api import RixensConnectionError
from custom_components.rixens.config_flow import (
    CannotConnect,
    RixensConfigFlow,
    RixensOptionsFlowHandler,
    validate_input,
)
from custom_components.rixens.const import CONF_HOST, CONF_PORT, DEFAULT_PORT

from .conftest import make_rixens_data

# ---------------------------------------------------------------------------
# validate_input
# ---------------------------------------------------------------------------


class TestValidateInput:
    """Tests for the validate_input helper."""

    async def test_successful_validation(self):
        mock_hass = MagicMock(spec=HomeAssistant)
        data = {CONF_HOST: "192.168.1.100", CONF_PORT: DEFAULT_PORT}

        with (
            patch("custom_components.rixens.config_flow.async_get_clientsession"),
            patch("custom_components.rixens.config_flow.RixensApi") as mock_api_cls,
        ):
            mock_api = AsyncMock()
            mock_api.get_status = AsyncMock(return_value=make_rixens_data())
            mock_api_cls.return_value = mock_api

            result = await validate_input(mock_hass, data)
            assert result["title"] == "Rixens (192.168.1.100)"
            assert result["version"] == "HW2-1.205 2025_11_20 RIXENS"

    async def test_connection_error_raises_cannot_connect(self):
        mock_hass = MagicMock(spec=HomeAssistant)
        data = {CONF_HOST: "192.168.1.100", CONF_PORT: DEFAULT_PORT}

        with (
            patch("custom_components.rixens.config_flow.async_get_clientsession"),
            patch("custom_components.rixens.config_flow.RixensApi") as mock_api_cls,
        ):
            mock_api = AsyncMock()
            mock_api.get_status = AsyncMock(
                side_effect=RixensConnectionError("timeout")
            )
            mock_api_cls.return_value = mock_api

            with pytest.raises(CannotConnect):
                await validate_input(mock_hass, data)


# ---------------------------------------------------------------------------
# RixensConfigFlow
# ---------------------------------------------------------------------------


class TestConfigFlow:
    """Tests for the config flow handler."""

    async def test_show_form_on_initial_step(self):
        flow = RixensConfigFlow()
        flow.hass = MagicMock(spec=HomeAssistant)

        result = await flow.async_step_user(user_input=None)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

    async def test_create_entry_on_valid_input(self):
        flow = RixensConfigFlow()
        flow.hass = MagicMock(spec=HomeAssistant)
        flow._async_abort_entries_match = MagicMock()
        flow.async_create_entry = MagicMock(
            return_value={"type": FlowResultType.CREATE_ENTRY}
        )

        with patch(
            "custom_components.rixens.config_flow.validate_input",
            return_value={"title": "Rixens (192.168.1.100)", "version": "1.0"},
        ):
            await flow.async_step_user(
                user_input={CONF_HOST: "192.168.1.100", CONF_PORT: DEFAULT_PORT}
            )
            flow.async_create_entry.assert_called_once_with(
                title="Rixens (192.168.1.100)",
                data={CONF_HOST: "192.168.1.100", CONF_PORT: DEFAULT_PORT},
            )

    async def test_cannot_connect_error(self):
        flow = RixensConfigFlow()
        flow.hass = MagicMock(spec=HomeAssistant)
        flow._async_abort_entries_match = MagicMock()
        flow.async_show_form = MagicMock(return_value={"type": FlowResultType.FORM})

        with patch(
            "custom_components.rixens.config_flow.validate_input",
            side_effect=CannotConnect,
        ):
            await flow.async_step_user(
                user_input={CONF_HOST: "192.168.1.100", CONF_PORT: DEFAULT_PORT}
            )
            flow.async_show_form.assert_called_once()
            call_kwargs = flow.async_show_form.call_args
            assert call_kwargs.kwargs["errors"] == {"base": "cannot_connect"}

    async def test_unknown_error(self):
        flow = RixensConfigFlow()
        flow.hass = MagicMock(spec=HomeAssistant)
        flow._async_abort_entries_match = MagicMock()
        flow.async_show_form = MagicMock(return_value={"type": FlowResultType.FORM})

        with patch(
            "custom_components.rixens.config_flow.validate_input",
            side_effect=RuntimeError("unexpected"),
        ):
            await flow.async_step_user(
                user_input={CONF_HOST: "192.168.1.100", CONF_PORT: DEFAULT_PORT}
            )
            flow.async_show_form.assert_called_once()
            call_kwargs = flow.async_show_form.call_args
            assert call_kwargs.kwargs["errors"] == {"base": "unknown"}

    def test_async_get_options_flow(self):
        result = RixensConfigFlow.async_get_options_flow(MagicMock())
        assert isinstance(result, RixensOptionsFlowHandler)


# ---------------------------------------------------------------------------
# RixensOptionsFlowHandler
# ---------------------------------------------------------------------------


class TestOptionsFlow:
    """Tests for the options flow handler."""

    async def test_show_form_on_init(self):
        mock_entry = MagicMock(spec=ConfigEntry)
        mock_entry.options = {}
        handler = RixensOptionsFlowHandler()
        handler.async_show_form = MagicMock(return_value={"type": FlowResultType.FORM})

        with patch.object(
            type(handler),
            "config_entry",
            new_callable=lambda: property(lambda self: mock_entry),
        ):
            await handler.async_step_init(user_input=None)
        handler.async_show_form.assert_called_once()

    async def test_save_options(self):
        mock_entry = MagicMock(spec=ConfigEntry)
        mock_entry.options = {}
        handler = RixensOptionsFlowHandler()
        handler.async_create_entry = MagicMock(
            return_value={"type": FlowResultType.CREATE_ENTRY}
        )

        user_input = {
            "preset_away_temp": 12.0,
            "preset_home_temp": 21.0,
            "preset_sleep_temp": 17.0,
            "fuel_dose": 0.03,
        }
        await handler.async_step_init(user_input=user_input)
        handler.async_create_entry.assert_called_once_with(title="", data=user_input)
