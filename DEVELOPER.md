# Developer Guide

This document covers the technical architecture, entity details, and development
workflow for the Rixens Home Assistant integration.

## Architecture

```
custom_components/rixens/
├── __init__.py      # Integration setup, coordinator initialization, platform forwarding
├── api.py           # HTTP API client for device communication
├── coordinator.py   # DataUpdateCoordinator for polling device status
├── config_flow.py   # UI-based configuration flow with connection validation
├── const.py         # Domain and configuration constants
├── climate.py       # Climate entity (thermostat control)
├── sensor.py        # Sensor entities (temp, humidity, diagnostics)
├── switch.py        # Switch entities (furnace, floor heat, electric heat, hot water)
├── fan.py           # Fan entity (on/off, speed, auto preset)
├── binary_sensor.py # Connection status
├── manifest.json    # Integration metadata
├── strings.json     # Translatable strings (source)
└── translations/    # Localized UI strings
```

## Key Patterns

- **Coordinator pattern**: `RixensCoordinator` polls the device every 5 seconds
  and distributes data to all entities
- **Entity descriptions**: Sensors and switches use dataclass descriptions with
  `value_fn` callbacks for clean state extraction
- **API client**: `RixensApi` handles HTTP communication and XML parsing, uses
  Home Assistant's shared aiohttp session
- **Entities**: All entities inherit from `CoordinatorEntity` for automatic
  updates

## Device API

The integration implements the official
[Rixen's MCS Local API](https://documenter.getpostman.com/view/55318949/2sBXwnsBuf).
The manufacturer's field and command descriptions are kept as comments in
`api.py`. Where the docs differ from observed data, the integration keeps its
current behaviour; see
[#72](https://github.com/tailgatelabs/ha-rixens-integration/issues/72).

> "The controller is state-owned. Command endpoints submit intent, but actual
> system state must be verified by reading status.xml."

### Status Endpoint

`GET /status.xml` — Returns XML with all device state. The docs recommend
polling every 2–5 seconds for live dashboards and never faster than once per
second; the integration polls every 5 seconds.

- Cabin temperature and setpoint are in **tenths of a degree Celsius** (e.g.,
  171 = 17.1°C); flame, inlet and outlet temperatures are in **hundredths**
- `currenttemp=-9990` and `currenthumidity=-999` mean no cabin sensor is
  connected; these are reported as unknown
- The XML includes Wi‑Fi credentials, so it is never logged
- Home Assistant handles display unit conversion based on user preferences

### Control Endpoint

`GET /interface.cgi?act=<id>&val=<int>`. Values must be base-10 integers.

| act  | Command            | Values                                                | Used by              |
| ---- | ------------------ | ----------------------------------------------------- | -------------------- |
| `1`  | Target temperature | `Math.round(°C × 10)` (75°F → 239)                    | Climate              |
| `2`  | Fan speed          | 0–100, `999` = Auto (integration sends 10–100 or 999) | Climate, Fan         |
| `3`  | Engine add heat    | 0/1                                                   | not yet (#66)        |
| `4`  | Electric heat      | 0/1                                                   | Electric heat switch |
| `5`  | Furnace            | 0/1                                                   | Furnace switch       |
| `6`  | Hot water          | 0/1                                                   | Hot water switch     |
| `7`  | Engine pre-heat    | 0/1                                                   | not yet (#66)        |
| `8`  | Fan state          | 0/1                                                   | Climate, Fan         |
| `9`  | Thermostat state   | 0/1                                                   | not yet (#67)        |
| `10` | Heated floors      | 0/1                                                   | Floor heat switch    |
| `11` | Aux                | 0/1                                                   | not yet (#66)        |

The momentary `buttons.cgi` commands (reset faults, prime fuel pump, 30-min hot
water timer) are not implemented yet
([#69](https://github.com/tailgatelabs/ha-rixens-integration/issues/69)).

## Entity Reference

### Climate Entity

- **Rixens Heater** (`climate.rixens_heater`)
  - Set target temperature (5-35°C)
  - View current temperature and humidity
  - Control HVAC mode (Off/Heat)
  - Select fan mode (Auto or 10-100% in 10% increments)
  - Choose preset modes (Away/Home/Sleep)
  - View HVAC action (Off/Idle/Heating)
  - Additional attributes show heat source states and system status

### Sensors

#### Environmental

- **Temperature** — Current room temperature (unknown if no cabin sensor)
- **Humidity** — Current room humidity (unknown if no cabin sensor)
- **Atmospheric Pressure** — Barometric pressure in hPa (used for altitude
  compensation)

#### Heater Diagnostics

- **Battery Voltage** — RV battery voltage monitoring
- **Flame Temperature** — Burner flame temperature
- **Inlet Temperature** — Heater inlet coolant temperature
- **Outlet Temperature** — Heater outlet coolant temperature
- **Heater Runtime** — Total heater operating time in seconds
- **System Uptime** — Device uptime since last restart

#### Performance

- **PID Speed** — Current PID-controlled fan speed percentage
- **Burner Motor** — Burner motor RPM
- **Dosing Pump** — Fuel pump frequency in Hz
- **Fuel Consumption** — Current fuel consumption rate in ml/h

#### System Information

- **Heater State** — Current operational state code
- **Firmware Version** — Main controller firmware version
- **Heat Firmware Version** — Heater module firmware version

### Switches

- **Furnace** — Enable/disable diesel/propane furnace heating
- **Electric Heat** — Enable/disable electric heating element
- **Floor Heat** — Enable/disable floor heating zone
- **Hot Water** — Enable/disable Hot Water mode (`cnstheat`). Existing installs
  keep the original `switch.…_continuous_heat` entity ID.

### Fan Entity

- **Fan** — On/off, manual speed (10-100%) and an `auto` preset
  - Displays actual PID speed when in auto mode

### Binary Sensors

- **Connection** — Device connectivity status (always available, even when
  device is offline)

## Advanced Behavior

### Heat Source State Preservation

When turning the climate entity on/off:

- The integration remembers which heat sources (furnace, electric) were enabled
- Turning back on restores your previous heat source configuration

### Fan Speed Intelligence

- **Auto Mode**: Displays actual PID-controlled speed from heater
- **Manual Mode**: Shows and controls configured speed setpoint

### HVAC Action States

- **Off**: HVAC mode is off
- **Idle**: Heating enabled but temperature at/above setpoint
- **Heating**: Actively calling for heat and heat sources running

### Error Handling

- **Automatic Retry**: Failed API calls are retried up to 3 times with
  exponential backoff
- **Graceful Degradation**: Entities remain available with last known data for
  up to 50 seconds during network issues
- **Connection Monitoring**: Binary sensor shows real-time connection status

## Platforms Summary

| Platform      | Entities                                                                                         |
| ------------- | ------------------------------------------------------------------------------------------------ |
| climate       | Main thermostat (setpoint, current temp, fan modes, HVAC modes)                                  |
| sensor        | Temperature, humidity, battery voltage, flame/inlet/outlet temps, altitude, runtime, diagnostics |
| switch        | Furnace, floor heat, electric heat, hot water                                                    |
| fan           | Fan (on/off, 10-100% speed, auto preset)                                                         |
| binary_sensor | Connection status                                                                                |

## Device Compatibility

This integration works with Rixens RV heating systems that have a WiFi
connection and expose an HTTP interface on port 80.

### Tested Devices

Firmware versions known to work:

```xml
<version>HW2-1.205 2025_11_20 RIXENS</version>
<heatversion>1.06 2025-11-21 PID</heatversion>
```

Sample `status.xml` files are kept at the repository root and used as test
fixtures: `example_mcs7_status.xml` (HW2-1.205, from a real device) and
`example_mcs7_status_hw2-1.208.xml` (HW2-1.208, the manufacturer's sample from
the official docs, Wi‑Fi credentials redacted).

## Adding New Controls

1. Use the documented `Command` in `api.py` (or add a parsed field)
2. Add entity description in appropriate platform file
3. Add translation key in `strings.json` and `translations/en.json`

## Contributing

For branching strategy, testing requirements, running tests, and deploying to
your Home Assistant instance, see [CONTRIBUTING.md](CONTRIBUTING.md).
