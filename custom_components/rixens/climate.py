"""Climate platform for Rixens integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_HOME,
    PRESET_SLEEP,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEVICE_FAN_AUTO,
    DEVICE_FAN_OFF,
    DOMAIN,
    FAN_MODE_AUTO,
    FAN_MODE_OFF,
    FAN_SPEED_AUTO,
    FAN_SPEED_MAX,
    FAN_SPEED_MIN,
    FAN_SPEED_STEP,
    TEMP_MAX,
    TEMP_MIN,
    TEMP_STEP,
)
from .api import Command
from .coordinator import RixensCoordinator

_LOGGER = logging.getLogger(__name__)

FAN_MODES = [FAN_MODE_OFF, FAN_MODE_AUTO] + [
    str(s) for s in range(FAN_SPEED_MIN, FAN_SPEED_MAX + 1, FAN_SPEED_STEP)
]

# Default preset temperatures (can be customized via integration options)
DEFAULT_PRESET_TEMPS = {
    PRESET_AWAY: 10.0,  # Freeze protection
    PRESET_HOME: 20.0,  # Comfortable living
    PRESET_SLEEP: 18.0,  # Night time
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rixens climate based on a config entry."""
    coordinator: RixensCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RixensClimate(coordinator)])


class RixensClimate(CoordinatorEntity[RixensCoordinator], ClimateEntity):
    """Representation of a Rixens climate device."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_fan_modes = FAN_MODES
    _attr_preset_modes = [PRESET_AWAY, PRESET_HOME, PRESET_SLEEP]
    _attr_min_temp = TEMP_MIN
    _attr_max_temp = TEMP_MAX
    _attr_target_temperature_step = TEMP_STEP
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.PRESET_MODE
    )

    def __init__(self, coordinator: RixensCoordinator) -> None:
        """Initialize the climate device."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name="Rixens Heater",
            manufacturer="Rixens",
            model="RV Heater",
            sw_version=coordinator.data.version if coordinator.data else None,
        )
        # Track last heat source configuration for state preservation
        self._last_heat_sources: dict[str, bool] | None = None
        # Track current preset mode
        self._preset_mode: str | None = None
        # Load preset temperatures from options or use defaults
        self._load_preset_temps()

    def _load_preset_temps(self) -> None:
        """Load preset temperatures from config entry options."""
        options = self.coordinator.config_entry.options
        self._preset_temps = {
            PRESET_AWAY: options.get(
                "preset_away_temp", DEFAULT_PRESET_TEMPS[PRESET_AWAY]
            ),
            PRESET_HOME: options.get(
                "preset_home_temp", DEFAULT_PRESET_TEMPS[PRESET_HOME]
            ),
            PRESET_SLEEP: options.get(
                "preset_sleep_temp", DEFAULT_PRESET_TEMPS[PRESET_SLEEP]
            ),
        }

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        if self.coordinator.data:
            return self.coordinator.data.current_temp
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        if self.coordinator.data:
            return self.coordinator.data.settings.setpoint
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode.

        Mode is based on whether heat sources are enabled, not whether
        heat is currently being called for (system_heat).
        """
        if not self.coordinator.data:
            return HVACMode.OFF

        # HVAC mode is HEAT if any heat source is enabled
        # (*src: 0 = Off, 1 = ready, 2 = active).
        # Only furnace_src, electric_src, and engine_src are actual heat sources
        if (
            self.coordinator.data.settings.furnace_src != 0
            or self.coordinator.data.settings.electric_src != 0
            or self.coordinator.data.settings.engine_src != 0
        ):
            return HVACMode.HEAT

        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action.

        Properly distinguishes between:
        - OFF: All heat sources disabled (all *src == 0)
        - IDLE: Heat sources enabled but not calling for heat (systemheat == 0)
        - HEATING: Calling for heat AND at least one source actively heating (*src == 2)
        """
        if not self.coordinator.data:
            return None

        # Check if all heat sources are disabled
        all_disabled = (
            self.coordinator.data.settings.furnace_src == 0
            and self.coordinator.data.settings.electric_src == 0
            and self.coordinator.data.settings.engine_src == 0
        )
        if all_disabled:
            return HVACAction.OFF

        # system_heat indicates thermostat is calling for heat (temp < setpoint)
        if self.coordinator.data.system_heat:
            # Check if any heat source is actively heating (== 2)
            any_heating = (
                self.coordinator.data.settings.furnace_src == 2
                or self.coordinator.data.settings.electric_src == 2
                or self.coordinator.data.settings.engine_src == 2
            )
            if any_heating:
                return HVACAction.HEATING
            # Calling for heat but not heating yet (startup delay, etc.)
            return HVACAction.IDLE

        # Heat sources enabled but not calling for heat (temp >= setpoint)
        return HVACAction.IDLE

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan mode."""
        if not self.coordinator.data:
            return None

        fan_speed = self.coordinator.data.settings.fan_speed
        if fan_speed == DEVICE_FAN_OFF:
            return FAN_MODE_OFF
        if fan_speed == DEVICE_FAN_AUTO:
            return FAN_MODE_AUTO
        # Numeric value — snap to nearest valid step
        try:
            speed = int(fan_speed)
            clamped = max(FAN_SPEED_MIN, min(FAN_SPEED_MAX, speed))
            snapped = round(clamped / FAN_SPEED_STEP) * FAN_SPEED_STEP
            return str(snapped)
        except (ValueError, TypeError):
            _LOGGER.warning("Unexpected fan speed value from device: %s", fan_speed)
            return FAN_MODE_AUTO

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        return self._preset_mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        return {
            "furnace_enabled": self.coordinator.data.settings.furnace_src != 0,
            "furnace_active": self.coordinator.data.settings.furnace_src == 2,
            "electric_heat_enabled": self.coordinator.data.settings.electric_src != 0,
            "electric_heat_active": self.coordinator.data.settings.electric_src == 2,
            "engine_heat_enabled": self.coordinator.data.settings.engine_src != 0,
            "engine_heat_active": self.coordinator.data.settings.engine_src == 2,
            "system_calling_for_heat": self.coordinator.data.system_heat,
            "current_humidity": self.coordinator.data.current_humidity,
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.api.set_temperature(float(temperature))
            # Clear preset mode when manually setting temperature
            self._preset_mode = None
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode.

        Preserves heat source configuration when toggling between OFF and HEAT.
        When turning on, restores previously enabled sources (or defaults to furnace).
        When turning off, remembers which sources were enabled.

        Engine add heat (act=3) is not toggled here; see #67 for moving HVAC
        OFF/HEAT to the thermostat state command (act=9).
        """
        if hvac_mode == HVACMode.HEAT:
            # Restore previous configuration or default to furnace only
            if self._last_heat_sources:
                if self._last_heat_sources.get("furnace"):
                    await self.coordinator.api.send_command(Command.FURNACE, True)
                if self._last_heat_sources.get("electric"):
                    await self.coordinator.api.send_command(Command.ELECTRIC_HEAT, True)
            else:
                # Default: enable furnace only
                await self.coordinator.api.send_command(Command.FURNACE, True)
        elif hvac_mode == HVACMode.OFF:
            # Save current heat source state before turning off
            if self.coordinator.data:
                self._last_heat_sources = {
                    "furnace": self.coordinator.data.settings.furnace_src != 0,
                    "electric": self.coordinator.data.settings.electric_src != 0,
                }
            await self.coordinator.api.send_command(Command.FURNACE, False)
            await self.coordinator.api.send_command(Command.ELECTRIC_HEAT, False)
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode.

        Off: turn fan off (act=8, val=0).
        Auto: turn fan on (act=8, val=1), then set auto speed (act=2, val=999).
        Manual: turn fan on (act=8, val=1), then set speed (act=2, val=N).
        """
        if fan_mode == FAN_MODE_OFF:
            await self.coordinator.api.send_command(Command.FAN_STATE, False)
        elif fan_mode == FAN_MODE_AUTO:
            await self.coordinator.api.send_command(Command.FAN_STATE, True)
            await self.coordinator.api.send_command(Command.FAN_SPEED, FAN_SPEED_AUTO)
        else:
            speed = int(fan_mode)
            if not FAN_SPEED_MIN <= speed <= FAN_SPEED_MAX:
                return
            await self.coordinator.api.send_command(Command.FAN_STATE, True)
            await self.coordinator.api.send_command(Command.FAN_SPEED, speed)
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode.

        Sets temperature to user-configured values for common RV heating scenarios.
        """
        if preset_mode in self._preset_temps:
            await self.coordinator.api.set_temperature(self._preset_temps[preset_mode])
            self._preset_mode = preset_mode
            await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the heating system on.

        Delegates to async_set_hvac_mode for consistent state preservation.
        """
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn the heating system off.

        Delegates to async_set_hvac_mode for consistent state preservation.
        """
        await self.async_set_hvac_mode(HVACMode.OFF)
