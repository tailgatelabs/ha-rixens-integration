"""Sensor platform for Rixens integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import RixensData
from .const import CONF_FUEL_DOSE, DEFAULT_FUEL_DOSE, DOMAIN
from .coordinator import RixensCoordinator
from .fan import compute_fan_speed
from .faults import (
    FAULT_OPTIONS,
    active_fault_code,
    fault_attributes,
    fault_key,
    stored_fault_codes,
)


@dataclass(frozen=True, kw_only=True)
class RixensSensorEntityDescription(SensorEntityDescription):
    """Describes a Rixens sensor entity."""

    value_fn: Callable[[RixensData], float | int | str | None]
    icon_fn: Callable[[float | int | str | None], str | None] | None = None
    attributes_fn: Callable[[RixensData], dict[str, Any]] | None = None


# Comfort Hot tank status, read from glycolstate (see RixensData.glycol_state):
# 0 = Off, 1 = Warming, 2 = Ready (122°F), 3 = Max (158°F)
GLYCOL_TANK_STATES: dict[int, str] = {
    0: "off",
    1: "warming",
    2: "ready",
    3: "max",
}

# Heater operating state, read from heaterstate. The docs only define 200 as the
# error state; the rest is inferred from live HW2-1.209 data and unconfirmed by
# Rixen's (see #71). Any other value is reported as unknown.
HEATER_STATES: dict[int, str] = {
    0: "off",
    10: "starting_cold",  # Glow and ignition from a cold combustion chamber
    12: "starting_warm",  # Same, restarting while the heater is still warm
    20: "running",  # Flame confirmed, burning at full or part load
    30: "shutting_down",  # Fuel off, burner motor purging while it cools
    40: "pre_start_purge",  # Restart while still hot: motor cools it, no fuel
    200: "error",
}

SENSOR_DESCRIPTIONS: tuple[RixensSensorEntityDescription, ...] = (
    RixensSensorEntityDescription(
        key="current_temperature",
        translation_key="current_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.current_temp,
    ),
    RixensSensorEntityDescription(
        key="current_humidity",
        translation_key="current_humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.current_humidity,
    ),
    RixensSensorEntityDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heater.battery_voltage,
    ),
    RixensSensorEntityDescription(
        key="flame_temperature",
        translation_key="flame_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heater.flame_temp,
    ),
    RixensSensorEntityDescription(
        key="inlet_temperature",
        translation_key="inlet_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heater.inlet_temp,
    ),
    RixensSensorEntityDescription(
        key="outlet_temperature",
        translation_key="outlet_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heater.outlet_temp,
    ),
    RixensSensorEntityDescription(
        key="atmospheric_pressure",
        translation_key="atmospheric_pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.heater.atmospheric_pressure,
    ),
    RixensSensorEntityDescription(
        key="heater_runtime",
        translation_key="heater_runtime",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        # Lifetime runtime runs to thousands of hours; minutes are hard to read
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heater.runtime,
    ),
    RixensSensorEntityDescription(
        key="system_uptime",
        translation_key="system_uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.uptime,
    ),
    RixensSensorEntityDescription(
        key="pid_speed",
        translation_key="pid_speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heater.pid_speed,
    ),
    RixensSensorEntityDescription(
        key="burner_motor",
        translation_key="burner_motor",
        native_unit_of_measurement="RPM",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heater.burner_motor,
    ),
    RixensSensorEntityDescription(
        key="dosing_pump",
        translation_key="dosing_pump",
        native_unit_of_measurement="Hz",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heater.dosing_pump,
    ),
    RixensSensorEntityDescription(
        key="fuel_consumption",
        translation_key="fuel_consumption",
        native_unit_of_measurement=f"{UnitOfVolume.MILLILITERS}/h",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (
            data.heater.dosing_pump
        ),  # Will be calculated in native_value
    ),
    RixensSensorEntityDescription(
        key="heater_state",
        translation_key="heater_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(HEATER_STATES.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: HEATER_STATES.get(data.heater_state),
        attributes_fn=lambda data: {"raw_state": data.heater_state},
    ),
    RixensSensorEntityDescription(
        key="glycol_tank",
        translation_key="glycol_tank",
        device_class=SensorDeviceClass.ENUM,
        options=list(GLYCOL_TANK_STATES.values()),
        value_fn=lambda data: GLYCOL_TANK_STATES.get(data.glycol_state),
    ),
    RixensSensorEntityDescription(
        key="active_fault",
        translation_key="active_fault",
        device_class=SensorDeviceClass.ENUM,
        options=FAULT_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: fault_key(active_fault_code(data)),
        attributes_fn=lambda data: fault_attributes(active_fault_code(data)),
    ),
    RixensSensorEntityDescription(
        key="last_fault",
        translation_key="last_fault",
        device_class=SensorDeviceClass.ENUM,
        options=FAULT_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: fault_key(next(iter(stored_fault_codes(data)), None)),
        attributes_fn=lambda data: {
            **fault_attributes(next(iter(stored_fault_codes(data)), None)),
            "stored_fault_codes": stored_fault_codes(data),
        },
    ),
    RixensSensorEntityDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.version,
    ),
    RixensSensorEntityDescription(
        key="heat_firmware_version",
        translation_key="heat_firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heat_version,
    ),
    RixensSensorEntityDescription(
        key="effective_fan_speed",
        translation_key="effective_fan_speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: compute_fan_speed(data),
        icon_fn=lambda val: "mdi:fan-off" if val == 0 else "mdi:fan",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rixens sensors based on a config entry."""
    coordinator: RixensCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        RixensSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    )


class RixensSensor(CoordinatorEntity[RixensCoordinator], SensorEntity):
    """Representation of a Rixens sensor."""

    _attr_has_entity_name = True
    entity_description: RixensSensorEntityDescription

    def __init__(
        self,
        coordinator: RixensCoordinator,
        description: RixensSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )

    @property
    def icon(self) -> str | None:
        """Return the icon for the sensor."""
        if self.entity_description.icon_fn is not None:
            return self.entity_description.icon_fn(self.native_value)
        return super().icon

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if self.coordinator.data and self.entity_description.attributes_fn:
            return self.entity_description.attributes_fn(self.coordinator.data)
        return None

    @property
    def native_value(self) -> float | int | str | None:
        """Return the state of the sensor."""
        if self.coordinator.data:
            value = self.entity_description.value_fn(self.coordinator.data)

            # Special handling for fuel consumption - apply configurable dose
            if (
                self.entity_description.key == "fuel_consumption"
                and value is not None
                and isinstance(value, (int, float))
            ):
                fuel_dose: float = self.coordinator.config_entry.options.get(
                    CONF_FUEL_DOSE, DEFAULT_FUEL_DOSE
                )
                # Convert Hz to ml/h: dosing_pump (Hz) * fuel_dose (ml/dose) * 3600 (sec/hr)
                return round(value * fuel_dose * 3600, 2)

            return value
        return None
