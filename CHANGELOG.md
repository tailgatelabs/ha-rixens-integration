# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Comfort Hot tank status sensor: Off, Warming, Ready (122°F) or Max (158°F)
  (#65)

### Changed

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
  installs will see the value jump to the correct, larger number.

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
