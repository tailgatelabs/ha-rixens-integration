"""Config flow for Rixens integration."""

from __future__ import annotations

import logging
from typing import Any

import probatio as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RixensApi, RixensConnectionError
from .const import (
    CONF_FUEL_DOSE,
    CONF_PORT,
    DEFAULT_FUEL_DOSE,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    api = RixensApi(
        host=data[CONF_HOST],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        session=async_get_clientsession(hass),
    )

    try:
        status = await api.get_status()
    except RixensConnectionError as err:
        _LOGGER.error(
            "Failed to connect to Rixens device at %s:%s - %s",
            data[CONF_HOST],
            data.get(CONF_PORT, DEFAULT_PORT),
            err,
        )
        raise CannotConnect from err

    _LOGGER.info(
        "Successfully connected to Rixens device at %s:%s (version: %s)",
        data[CONF_HOST],
        data.get(CONF_PORT, DEFAULT_PORT),
        status.version,
    )

    # Return info that you want to store in the config entry
    return {"title": f"Rixens ({data[CONF_HOST]})", "version": status.version}


class RixensConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Rixens."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return RixensOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check if already configured
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})

            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class RixensOptionsFlowHandler(OptionsFlow):
    """Handle options flow for Rixens integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage preset temperature options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current values from options or use defaults
        current_options = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "preset_away_temp",
                        default=current_options.get("preset_away_temp", 10.0),
                    ): vol.All(vol.Coerce(float), vol.Range(min=5.0, max=30.0)),
                    vol.Optional(
                        "preset_home_temp",
                        default=current_options.get("preset_home_temp", 20.0),
                    ): vol.All(vol.Coerce(float), vol.Range(min=5.0, max=30.0)),
                    vol.Optional(
                        "preset_sleep_temp",
                        default=current_options.get("preset_sleep_temp", 18.0),
                    ): vol.All(vol.Coerce(float), vol.Range(min=5.0, max=30.0)),
                    vol.Optional(
                        CONF_FUEL_DOSE,
                        default=current_options.get(CONF_FUEL_DOSE, DEFAULT_FUEL_DOSE),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.001, max=1.0)),
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
