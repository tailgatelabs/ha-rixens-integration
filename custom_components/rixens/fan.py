"""Fan platform for Rixens integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import percentage_to_ordered_list_item

from .api import Command, RixensData
from .const import (
    DEVICE_FAN_AUTO,
    DEVICE_FAN_OFF,
    DOMAIN,
    FAN_SPEED_AUTO,
    FAN_SPEED_MAX,
    FAN_SPEED_MIN,
)
from .coordinator import RixensCoordinator

ORDERED_NAMED_FAN_SPEEDS = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
PRESET_MODE_AUTO = "auto"


def compute_fan_speed(data: RixensData) -> int:
    """Compute effective fan speed percentage from device data.

    Returns 0 when fan is off, otherwise 0-100 for auto or 10-100 for manual.
    """
    if not data.settings.fan_state:
        return 0

    fan_speed = data.settings.fan_speed

    if fan_speed == DEVICE_FAN_OFF:
        return 0

    # Auto mode: use PID-controlled speed
    if fan_speed == DEVICE_FAN_AUTO:
        return min(FAN_SPEED_MAX, max(0, data.heater.pid_speed))

    # Manual mode: use configured setpoint
    try:
        speed = int(fan_speed)
        return max(FAN_SPEED_MIN, min(FAN_SPEED_MAX, speed))
    except ValueError:
        return 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rixens fan entity based on a config entry."""
    coordinator: RixensCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RixensFan(coordinator)])


class RixensFan(CoordinatorEntity[RixensCoordinator], FanEntity):
    """Representation of a Rixens fan."""

    _attr_has_entity_name = True
    _attr_translation_key = "fan"
    _attr_speed_count = 10
    _attr_preset_modes = [PRESET_MODE_AUTO]
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: RixensCoordinator) -> None:
        """Initialize the fan entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_fan"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the fan is on."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.settings.fan_state

    @property
    def percentage(self) -> int | None:
        """Return the current speed as a percentage."""
        if not self.coordinator.data:
            return None
        return compute_fan_speed(self.coordinator.data)

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        if not self.coordinator.data:
            return None
        if self.coordinator.data.settings.fan_speed == DEVICE_FAN_AUTO:
            return PRESET_MODE_AUTO
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        data = self.coordinator.data
        fan_speed = data.settings.fan_speed
        is_off = not data.settings.fan_state
        is_auto = fan_speed == DEVICE_FAN_AUTO

        if is_off:
            mode = "off"
        elif is_auto:
            mode = "auto"
        else:
            mode = "manual"

        attributes: dict[str, Any] = {
            "mode": mode,
            "actual_speed": data.heater.pid_speed,
        }

        if mode == "manual":
            try:
                attributes["configured_speed"] = int(fan_speed)
            except ValueError:
                pass

        return attributes

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan."""
        await self.coordinator.api.send_command(Command.FAN_STATE, True)

        if preset_mode == PRESET_MODE_AUTO:
            await self.coordinator.api.send_command(Command.FAN_SPEED, FAN_SPEED_AUTO)
        elif percentage is not None:
            speed = percentage_to_ordered_list_item(
                ORDERED_NAMED_FAN_SPEEDS, percentage
            )
            await self.coordinator.api.send_command(Command.FAN_SPEED, speed)

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan."""
        await self.coordinator.api.send_command(Command.FAN_STATE, False)
        await self.coordinator.async_request_refresh()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan."""
        if percentage == 0:
            await self.async_turn_off()
            return

        speed = percentage_to_ordered_list_item(ORDERED_NAMED_FAN_SPEEDS, percentage)
        await self.coordinator.api.send_command(Command.FAN_STATE, True)
        await self.coordinator.api.send_command(Command.FAN_SPEED, speed)
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of the fan."""
        if preset_mode == PRESET_MODE_AUTO:
            await self.coordinator.api.send_command(Command.FAN_STATE, True)
            await self.coordinator.api.send_command(Command.FAN_SPEED, FAN_SPEED_AUTO)
            await self.coordinator.async_request_refresh()
