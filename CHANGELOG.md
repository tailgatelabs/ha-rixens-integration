# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Fuel used sensor: a running total of the fuel the furnace has burned, kept
  across restarts, for charting fuel use per day, week or month (#86)
- Hot water timer sensor: time left on the Hot Water timer (unknown when no
  timer is running or the firmware does not report it) (#70)
- Circulation pump and Engine heat binary sensors (#70)

### Changed

- **Breaking:** the thermostat's Off/Heat mode now uses the controller's
  thermostat on/off command and shows its thermostat state, instead of turning
  the furnace and electric heat switches off and on (#67). The heat source
  switches keep their settings while the thermostat is off. While it is off the
  thermostat shows no target temperature (it used to show 20 °C).
- **Breaking:** requires Home Assistant 2026.9 or later. The config flow now
  uses `probatio`, which replaced voluptuous in Home Assistant 2026.9.
- Development and test dependencies updated to the latest versions that work
  together (Home Assistant 2026.10.4, pytest-homeassistant-custom-component
  0.13.375, ruff 0.17.3).
- **Breaking:** the Comfort Hot tank sensor now reports Not ready, Ready
  (120–160°F) or Hot (above 160°F), following Rixen's description of
  `glycolstate` (#72). It previously reported Off, Warming, Ready or Max, so
  `glycolstate=1` showed as Warming instead of Ready and `2` as Ready instead of
  Hot. Automations that compare its state must be updated.
- **Breaking:** the Heater state sensor uses Rixen's state names (#71). `40` is
  now Paused (`paused`) instead of Purging before start (`pre_start_purge`), and
  Cold blow (13), Stabilizing flame (15) and Shutting down to standby (31) are
  new states that previously reported unknown.
- Numeric sensors now have a default display precision, so values like
  temperature and battery voltage show rounded without manual setup (#84).
- **Breaking:** System uptime is now a timestamp of when the controller last
  booted, instead of a duration in seconds, so it no longer records a new state
  on every poll (#88). Home Assistant will raise a one-time statistics repair
  for it; choose to delete the old statistics.
- Flame temperature is rounded to 1 °C and inlet/outlet temperatures to 0.1 °C,
  so they no longer record a new state on almost every poll (#88).
- The fan's `actual_speed` and the thermostat's `current_humidity` attributes
  are no longer recorded in history; the PID speed and humidity sensors already
  record them (#88).
- PID speed, burner motor, dosing pump and flame, inlet and outlet temperature
  sensors are disabled by default on new installs. Existing installs keep them
  enabled; disable them on the device page to save recorder space. Fuel
  consumption stays enabled (#89).
- PID speed and burner motor no longer keep long-term statistics. Home Assistant
  will raise a one-time statistics repair for them (#89).
- The device is polled every 8 s instead of 5 s, cutting recorder writes by
  about a third. Switches, the fan and the thermostat now show a change as soon
  as you make it and confirm it with a refresh about 1 s later. The device is
  marked unavailable after about 48 s of failed polls (#90).

## [1.2.1] - 2026-10-25

### Added

- Entity icons for heat sources, heater diagnostics and faults, with icons that
  change with state (for example furnace on/off, heater running/off) (#80)

### Changed

- HACS now requires Home Assistant 2024.11 or later, the minimum the integration
  already needed (#80)
- README: new light and dark screenshots, HACS 2.x install steps, the port and
  fuel dose options, and corrected automation examples (#80)

### Fixed

- The integration version shown in Home Assistant now matches the release (it
  reported 1.0.0 since v1.0.0) (#81)

## [1.2.0] - 2026-10-25

### Added

- Heater fault reporting (#76): a Heater fault problem binary sensor, Active
  fault and Last fault diagnostic sensors, and a Heater fault event that fires
  when a new fault appears. Fault names, P-codes and error classes come from
  Eberspächer's Hydronic S3 CS fault table and are unconfirmed by Rixen's; raw
  codes are always exposed.
- Comfort Hot tank status sensor: Off, Warming, Ready (122°F) or Max (158°F)
  (#65)

### Changed

- **Breaking:** the Heater state sensor now reports a named state (Off, Starting
  (cold), Starting (warm), Running, Shutting down, Purging before start, Error)
  instead of the raw `heaterstate` number (#71). Unrecognised values report
  unknown. The raw number is kept in the `raw_state` attribute. Automations,
  templates or conditions that compare this sensor to a number must be updated,
  for example to `state_attr('sensor.…_heater_state', 'raw_state')`. Only 200
  (error) is documented; the other names are inferred from live data and
  unconfirmed by Rixen's.
- Aligned the API client with Rixen's official MCS Local API documentation (#64)
- The "Continuous heat" switch is now named "Hot water", matching the official
  docs. Existing entity IDs (`switch.…_continuous_heat`) are unchanged.
- Heater runtime displays in hours by default on new installs (#78)

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

## [1.1.0] - 2026-04-21

### Changed

- Fan control is now a native fan entity (on/off, 10-100% speed, Auto preset)
  instead of a switch plus a number entity (#62)
- README rewritten for non-technical users; developer details moved to
  DEVELOPER.md (#58)
- Repository moved to the tailgatelabs organisation (#63)

### Fixed

- Fan mode control matches the device protocol: the fan is turned on before
  setting a speed or Auto (#59, #60)

## [1.0.4] - 2026-03-10

### Added

- Continuous heat switch (now named Hot water)

## [1.0.3] - 2026-03-10

### Added

- Configurable fuel dose per pump cycle for the fuel consumption sensor

### Fixed

- Options flow and reconfigure errors (`AttributeError`, `TypeError`)
- Invalid `icon` key removed from `manifest.json`

## [1.0.0] - 2026-01-20

### Added

- Error handling and resilience: failed polls are retried and the last known
  data is kept for about 50 seconds before entities go unavailable (#43)

### Fixed

- HVAC mode only considers actual heat sources (#47)
- Flame temperature scaling (divided by 100, not 10) (#49)

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

[Unreleased]:
  https://github.com/tailgatelabs/ha-rixens-integration/compare/v1.2.1...HEAD
[1.2.1]:
  https://github.com/tailgatelabs/ha-rixens-integration/compare/v1.2.0...v1.2.1
[1.2.0]:
  https://github.com/tailgatelabs/ha-rixens-integration/compare/v1.1.0...v1.2.0
[1.1.0]:
  https://github.com/tailgatelabs/ha-rixens-integration/compare/v1.0.4...v1.1.0
[1.0.4]:
  https://github.com/tailgatelabs/ha-rixens-integration/compare/v1.0.3...v1.0.4
[1.0.3]:
  https://github.com/tailgatelabs/ha-rixens-integration/compare/v1.0.0...v1.0.3
[1.0.0]:
  https://github.com/tailgatelabs/ha-rixens-integration/releases/tag/v1.0.0
[0.1.0]:
  https://github.com/tailgatelabs/ha-rixens-integration/releases/tag/v0.1.0
