"""Switch platform for Rixens integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Command, RixensData
from .const import DOMAIN
from .coordinator import RixensCoordinator
from .optimistic import OptimisticState


@dataclass(frozen=True, kw_only=True)
class RixensSwitchEntityDescription(SwitchEntityDescription):
    """Describes a Rixens switch entity."""

    value_fn: Callable[[RixensData], bool]
    command: Command  # Sent with val=1 to turn on, val=0 to turn off


# *src fields: hardware state (0 = Off, 1 = ready, 2 = active)
SWITCH_DESCRIPTIONS: tuple[RixensSwitchEntityDescription, ...] = (
    RixensSwitchEntityDescription(
        key="furnace",
        translation_key="furnace",
        value_fn=lambda data: data.settings.furnace_src != 0,
        command=Command.FURNACE,
    ),
    RixensSwitchEntityDescription(
        key="floor_heat",
        translation_key="floor_heat",
        value_fn=lambda data: data.settings.floor_src != 0,
        command=Command.HEATED_FLOORS,
    ),
    RixensSwitchEntityDescription(
        key="electric_heat",
        translation_key="electric_heat",
        value_fn=lambda data: data.settings.electric_src != 0,
        command=Command.ELECTRIC_HEAT,
    ),
    # Hot Water mode (cnstheat). The key predates the official docs and is
    # kept so the unique_id stays stable for existing installs.
    RixensSwitchEntityDescription(
        key="continuous_heat",
        translation_key="hot_water",
        value_fn=lambda data: data.settings.cnst_heat != 0,
        command=Command.HOT_WATER,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rixens switches based on a config entry."""
    coordinator: RixensCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        RixensSwitch(coordinator, description) for description in SWITCH_DESCRIPTIONS
    )


class RixensSwitch(CoordinatorEntity[RixensCoordinator], SwitchEntity):
    """Representation of a Rixens switch."""

    _attr_has_entity_name = True
    entity_description: RixensSwitchEntityDescription

    def __init__(
        self,
        coordinator: RixensCoordinator,
        description: RixensSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.entity_description = description
        self._optimistic = OptimisticState[bool]()
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        actual = None
        if self.coordinator.data:
            actual = self.entity_description.value_fn(self.coordinator.data)
        return self._optimistic.resolve(actual)

    async def _async_set(self, on: bool) -> None:
        """Send the command, show the new state now and confirm via a refresh."""
        await self.coordinator.api.send_command(self.entity_description.command, on)
        self._optimistic.set(on)
        if self.hass is not None:
            self.async_write_ha_state()
        self.coordinator.async_refresh_after_command()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_set(False)
