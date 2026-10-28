"""Binary sensor platform for Rixens integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import RixensData
from .const import DOMAIN
from .coordinator import RixensCoordinator
from .faults import (
    HEATER_STATE_ERROR,
    active_fault_code,
    fault_attributes,
    is_fault,
    stored_fault_codes,
)


@dataclass(frozen=True, kw_only=True)
class RixensBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Rixens binary sensor entity."""

    value_fn: Callable[[RixensData], bool]


BINARY_SENSOR_DESCRIPTIONS: tuple[RixensBinarySensorEntityDescription, ...] = (
    RixensBinarySensorEntityDescription(
        key="circulation_pump",
        translation_key="circulation_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda data: data.settings.pump_state,
    ),
    RixensBinarySensorEntityDescription(
        key="engine_heat",
        translation_key="engine_heat",
        value_fn=lambda data: data.engine_state == 1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rixens binary sensors based on a config entry."""
    coordinator: RixensCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [
        RixensConnectionSensor(coordinator),
        RixensHeaterFaultSensor(coordinator),
    ]
    entities.extend(
        RixensBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )
    async_add_entities(entities)


class RixensBinarySensor(CoordinatorEntity[RixensCoordinator], BinarySensorEntity):
    """Representation of a Rixens binary sensor."""

    _attr_has_entity_name = True
    entity_description: RixensBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: RixensCoordinator,
        description: RixensBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )

    @property
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""
        if self.coordinator.data:
            return self.entity_description.value_fn(self.coordinator.data)
        return None


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
        """Return the raw fault codes and the active fault's P-code and class."""
        data = self.coordinator.data
        if not data:
            return {}
        active = fault_attributes(active_fault_code(data))
        return {
            "active_fault_code": active["code"],
            "active_fault_p_code": active["p_code"],
            "active_fault_class": active["fault_class"],
            "stored_fault_codes": stored_fault_codes(data),
            "heater_state": data.heater_state,
        }
