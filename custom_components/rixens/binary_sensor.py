"""Binary sensor platform for Rixens integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RixensCoordinator
from .faults import (
    HEATER_STATE_ERROR,
    active_fault_code,
    is_fault,
    stored_fault_codes,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rixens binary sensors based on a config entry."""
    coordinator: RixensCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [RixensConnectionSensor(coordinator), RixensHeaterFaultSensor(coordinator)]
    )


class RixensConnectionSensor(CoordinatorEntity[RixensCoordinator], BinarySensorEntity):
    """Binary sensor showing device connection status."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RixensCoordinator) -> None:
        """Initialize the connection sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_connection"
        self._attr_translation_key = "connection"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )

    @property
    def is_on(self) -> bool:
        """Return True if device is connected."""
        return self.coordinator.is_available

    @property
    def available(self) -> bool:
        """Connection sensor is always available to show connection state."""
        return True


class RixensHeaterFaultSensor(CoordinatorEntity[RixensCoordinator], BinarySensorEntity):
    """Binary sensor that is on while the heater reports a fault."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "heater_fault"

    def __init__(self, coordinator: RixensCoordinator) -> None:
        """Initialize the heater fault sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_heater_fault"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the heater is in its error state or has an active fault."""
        data = self.coordinator.data
        if not data:
            return None
        return data.heater_state == HEATER_STATE_ERROR or is_fault(
            active_fault_code(data)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the raw fault codes."""
        data = self.coordinator.data
        if not data:
            return {}
        return {
            "active_fault_code": active_fault_code(data),
            "stored_fault_codes": stored_fault_codes(data),
            "heater_state": data.heater_state,
        }
