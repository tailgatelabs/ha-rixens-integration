# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Heater fault reporting (#76): a Heater fault problem binary sensor, Active
  fault and Last fault diagnostic sensors, and a Heater fault event that fires
  when a new fault appears. Fault names, P-codes and error classes come from
  Eberspächer's Hydronic S3 CS fault table and are unconfirmed by Rixen's; raw
  codes are always exposed.
- Comfort Hot tank status sensor: Off, Warming, Ready (122°F) or Max (158°F)
  (#65)

### Changed

- **Breaking:** the Heater state sensor now reports a named state (Off,
  Starting (cold), Starting (warm), Running, Shutting down, Purging before
  start, Error) instead of the raw `heaterstate` number (#71). Unrecognised
  values report unknown. The raw number is kept in the `raw_state` attribute.
  Automations, templates or conditions that compare this sensor to a number
  must be updated, for example to
  `state_attr('sensor.…_heater_state', 'raw_state')`. Only 200 (error) is
  documented; the other names are inferred from live data and unconfirmed by
  Rixen's.
- Aligned the API client with Rixen's official MCS Local API documentation (#64)
- The "Continuous heat" switch is now named "Hot water", matching the official
  docs. Existing entity IDs (`switch.…_continuous_heat`) are unchanged.

### Fixed

- Status parsing no longer fails when a Wi‑Fi SSID or password contains `&`
- Fan speed `999` is recognised as Auto (newer firmware)
- Temperature setpoints are rounded instead of truncated (75°F now sends 239)
- Temperature and humidity report unknown instead of -999 when no cabin sensor
  is connected
- `settings.glycol` is parsed as an integer instead of a boolean
- Heater runtime is reported in minutes instead of seconds (#72). Existing
  installs will see the value jump to the correct, larger number. New installs
  display it in hours; existing installs keep their current display unit, which
  can be changed in the entity's settings.

## [0.1.0] - 2026-01-16

### Added

- Initial release of Rixens Home Assistant integration
- Climate entity for thermostat control
  - Temperature setpoint control (5-35°C)
  - HVAC modes: Off, Heat
  - Fan modes: Auto, 10-100%
- 16 sensor entities
  - Temperature and humidity sensors
  - Battery voltage monitoring
  - Flame, inlet, outlet temperature diagnostics
  - Altitude sensor (meters)
  - Runtime and uptime tracking
  - PID speed, burner motor RPM
  - Dosing pump frequency (Hz)
  - Fuel consumption calculation (mL/h)
  - Heater state and firmware versions
- 6 switch entities
  - System heat control
  - Pump, fan, floor heat, electric heat controls
  - Thermostat mode toggle
- Number entity for fan speed control (10-100%)
- Config flow for easy setup
- HACS compatibility
- Integration icon with Rixens branding

### Technical

- Local polling every 5 seconds
- XML-based HTTP API communication
- Automatic unit conversions (temperatures, altitude, dosing pump)
- DataUpdateCoordinator pattern for efficient updates

[0.1.0]:
  https://github.com/tailgatelabs/ha-rixens-integration/releases/tag/v0.1.0
