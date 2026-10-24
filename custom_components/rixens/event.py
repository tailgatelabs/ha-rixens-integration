"""Event platform for Rixens integration."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RixensCoordinator
from .faults import active_fault_code, fault_attributes, fault_key, is_fault

EVENT_FAULT_DETECTED = "fault_detected"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rixens event entities based on a config entry."""
    coordinator: RixensCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RixensHeaterFaultEvent(coordinator)])


class RixensHeaterFaultEvent(CoordinatorEntity[RixensCoordinator], EventEntity):
    """Event entity that fires when the heater reports a new active fault."""

    _attr_has_entity_name = True
    _attr_translation_key = "heater_fault"
    _attr_event_types = [EVENT_FAULT_DETECTED]

    def __init__(self, coordinator: RixensCoordinator) -> None:
        """Initialize the heater fault event entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_heater_fault_event"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )
        # A fault already active at startup does not fire; the Heater fault
        # binary sensor reports it instead.
        self._last_code = (
            active_fault_code(coordinator.data) if coordinator.data else None
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Fire fault_detected when the active fault code changes to a fault."""
        if self.coordinator.data:
            code = active_fault_code(self.coordinator.data)
            if is_fault(code) and code != self._last_code:
                self._trigger_event(
                    EVENT_FAULT_DETECTED,
                    {**fault_attributes(code), "fault": fault_key(code)},
                )
            self._last_code = code
        super()._handle_coordinator_update()
