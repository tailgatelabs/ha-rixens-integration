"""Sensor platform for Rixens integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import monotonic
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

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

# Longest gap between fresh polls that is still added to the fuel total. A
# longer gap (device offline, Home Assistant busy) is skipped rather than
# guessed at the last known pump rate.
FUEL_USED_MAX_GAP = 60  # seconds


def fuel_rate_ml_per_hour(data: RixensData, fuel_dose: float) -> float:
    """Return the furnace fuel rate in mL/h from the dosing pump frequency."""
    # dosing_pump (Hz) * fuel_dose (mL/dose) * 3600 (s/h)
    return data.heater.dosing_pump * fuel_dose * 3600


@dataclass(frozen=True, kw_only=True)
class RixensSensorEntityDescription(SensorEntityDescription):
    """Describes a Rixens sensor entity."""

    value_fn: Callable[[RixensData], datetime | float | int | str | None]
    icon_fn: Callable[[datetime | float | int | str | None], str | None] | None = None
    attributes_fn: Callable[[RixensData], dict[str, Any]] | None = None


# Comfort Hot tank status, read from glycolstate (see RixensData.glycol_state),
# as confirmed by Rixen's (#72): 0 = not up to temp, 1 = ready (yellow dot,
# 120-160°F), 2 = above 160°F (red dot)
GLYCOL_TANK_STATES: dict[int, str] = {
    0: "not_ready",
    1: "ready",
    2: "hot",
}

# Heater operating state, read from heaterstate. Names are from Rixen's list
# (#71), which carries over Eberspächer's state codes and may not be complete;
# 200 is the documented error state. Any other value is reported as unknown.
HEATER_STATES: dict[int, str] = {
    0: "off",
    10: "starting_cold",  # Initial cold start: glow plug warming, pump priming
    12: "starting_warm",  # Warm start
    13: "cold_blow",  # Cold blow
    15: "stabilizing_flame",  # Flame stabilization window
    20: "running",
    30: "shutting_down",  # After run to shutdown
    31: "shutting_down_to_standby",  # After run to standby
    40: "paused",  # Pause; seen before a start requested while still hot
    200: "error",
}


def boot_time(data: RixensData) -> datetime:
    """Return when the controller booted, rounded to the minute.

    Derived from the uptime counter so the state only changes on reboot
    instead of on every poll.
    """
    boot = dt_util.utcnow() - timedelta(seconds=data.uptime)
    return (boot + timedelta(seconds=30)).replace(second=0, microsecond=0)


SENSOR_DESCRIPTIONS: tuple[RixensSensorEntityDescription, ...] = (
    RixensSensorEntityDescription(
        key="current_temperature",
        translation_key="current_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.current_temp,
    ),
    RixensSensorEntityDescription(
        key="current_humidity",
        translation_key="current_humidity",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.current_humidity,
    ),
    RixensSensorEntityDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heater.battery_voltage,
    ),
    RixensSensorEntityDescription(
        key="flame_temperature",
        translation_key="flame_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        # Reported in hundredths of °C; rounded so it isn't recorded every poll
        value_fn=lambda data: round(data.heater.flame_temp),
    ),
    RixensSensorEntityDescription(
        key="inlet_temperature",
        translation_key="inlet_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: round(data.heater.inlet_temp, 1),
    ),
    RixensSensorEntityDescription(
        key="outlet_temperature",
        translation_key="outlet_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: round(data.heater.outlet_temp, 1),
    ),
    RixensSensorEntityDescription(
        key="atmospheric_pressure",
        translation_key="atmospheric_pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        suggested_display_precision=0,
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
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=boot_time,
    ),
    RixensSensorEntityDescription(
        key="pid_speed",
        translation_key="pid_speed",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.heater.pid_speed,
    ),
    RixensSensorEntityDescription(
        key="burner_motor",
        translation_key="burner_motor",
        native_unit_of_measurement="RPM",
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.heater.burner_motor,
    ),
    RixensSensorEntityDescription(
        key="dosing_pump",
        translation_key="dosing_pump",
        native_unit_of_measurement="Hz",
        suggested_display_precision=1,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Same churn as fuel_consumption, which is derived from it
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.heater.dosing_pump,
    ),
    RixensSensorEntityDescription(
        key="fuel_consumption",
        translation_key="fuel_consumption",
        native_unit_of_measurement=f"{UnitOfVolume.MILLILITERS}/h",
        suggested_display_precision=1,
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
        key="hot_water_timer",
        translation_key="hot_water_timer",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda data: data.settings.cnst_heat_timer_val,
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
        suggested_display_precision=0,
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
    entities: list[SensorEntity] = [
        RixensSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    ]
    entities.append(RixensFuelUsedSensor(coordinator))
    async_add_entities(entities)


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
        self._boot_time: datetime | None = None

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
    def native_value(self) -> datetime | float | int | str | None:
        """Return the state of the sensor."""
        if self.coordinator.data:
            value = self.entity_description.value_fn(self.coordinator.data)

            # Boot time is computed from the poll time, so it can flip across a
            # minute boundary between polls; only move it on a real reboot
            if isinstance(value, datetime):
                if self._boot_time is None or abs(value - self._boot_time) > timedelta(
                    minutes=1
                ):
                    self._boot_time = value
                return self._boot_time

            # Special handling for fuel consumption - apply configurable dose
            if (
                self.entity_description.key == "fuel_consumption"
                and value is not None
                and isinstance(value, (int, float))
            ):
                fuel_dose: float = self.coordinator.config_entry.options.get(
                    CONF_FUEL_DOSE, DEFAULT_FUEL_DOSE
                )
                return round(fuel_rate_ml_per_hour(self.coordinator.data, fuel_dose), 2)

            return value
        return None


class RixensFuelUsedSensor(CoordinatorEntity[RixensCoordinator], RestoreSensor):
    """Running total of the fuel the furnace has burned (#86).

    Each fresh poll adds the previous poll's rate over the time since it (a
    left Riemann sum, since the pump rate is a step function). The total is
    restored across restarts and reloads.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "fuel_used"
    _attr_device_class = SensorDeviceClass.VOLUME
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.MILLILITERS
    _attr_suggested_unit_of_measurement = UnitOfVolume.LITERS
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: RixensCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_fuel_used"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )
        self._total = 0.0
        # Last fresh poll: its data, when it arrived and its fuel rate (mL/h)
        self._last_data: RixensData | None = None
        self._last_time: float | None = None
        self._last_rate = 0.0

    async def async_added_to_hass(self) -> None:
        """Restore the total and start counting from the current poll."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            try:
                self._total = float(last.native_value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
        self._record_poll()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Add the fuel burned since the last fresh poll."""
        self._record_poll()
        super()._handle_coordinator_update()

    def _record_poll(self) -> None:
        data = self.coordinator.data
        # A failed poll hands back the previous data object; skip it so the
        # interval is counted once the next fresh poll arrives
        if data is None or data is self._last_data:
            return
        now = monotonic()
        if self._last_time is not None:
            elapsed = now - self._last_time
            if elapsed <= FUEL_USED_MAX_GAP:
                self._total += self._last_rate * elapsed / 3600
        fuel_dose: float = self.coordinator.config_entry.options.get(
            CONF_FUEL_DOSE, DEFAULT_FUEL_DOSE
        )
        self._last_data = data
        self._last_time = now
        self._last_rate = fuel_rate_ml_per_hour(data, fuel_dose)

    @property
    def native_value(self) -> float:
        """Return the fuel burned so far in mL."""
        return round(self._total, 2)
