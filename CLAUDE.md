# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## Project Overview

This is a Home Assistant custom integration for Rixens RV heating/climate
control systems, distributed via HACS. The integration communicates with Rixens
devices over HTTP using a local polling approach.

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
├── binary_sensor.py # Connection status, heater fault
├── event.py         # Heater fault event
├── faults.py        # Fault code table and helpers
├── icons.json       # Entity icons by translation key
├── manifest.json    # Integration metadata
├── strings.json     # Translatable strings (source)
└── translations/    # Localized UI strings
```

## Device API

The integration implements the official
[Rixen's MCS Local API](https://documenter.getpostman.com/view/55318949/2sBXwnsBuf).
Field and command descriptions from the docs are kept as comments in `api.py`.
Where the docs differ from observed data, current behaviour is kept and tracked
in issue #72.

**Status endpoint:** `GET /status.xml` - Returns XML with all device state

- Poll every 2-5 s for live dashboards, never faster than 1 req/s (we use 8 s
  to reduce recorder writes, #90, plus a refresh ~1 s after each command)
- Command responses are not authoritative; always refresh from `status.xml`
- Temperatures (`currenttemp`, `setpoint`) are **tenths of °C**; flame, inlet
  and outlet temps are **hundredths of °C**
- Confirmed by Rixen's (Oct 2026): `runtime` is minutes; `glycolstate` is 0 =
  not ready, 1 = ready (120-160°F), 2 = hot (>160°F); `heatsources` bits are
  furnace 4, electric 2, engine 1 (8 = floor heat is observed, unconfirmed);
  `fanspeed` is `Off`, a percentage or `Auto`
- `currenttemp=-9990` / `currenthumidity=-999` mean no cabin sensor (parsed as
  `None`)
- The device does not escape `&` in strings; `api.py` escapes it before parsing
- The XML contains Wi-Fi credentials (`key`, `infra_pass`): never log it or
  expose them as entities
- Home Assistant handles display unit conversion based on user preferences

**Control endpoint:** `GET /interface.cgi?act=<id>&val=<int>` (base-10 integers
only), sent via `RixensApi.send_command(Command.<NAME>, value)`

| act | Command (`api.Command`) | Notes                          |
| --- | ----------------------- | ------------------------------ |
| 1   | Target temperature      | `Math.round(°C * 10)`          |
| 2   | Fan speed               | 0-100, 999 = Auto (we use 10+) |
| 3   | Engine add heat         | not exposed yet (#66)          |
| 4   | Electric heat           | 0/1                            |
| 5   | Furnace                 | 0/1                            |
| 6   | Hot water               | 0/1                            |
| 7   | Engine pre-heat         | not exposed yet (#66)          |
| 8   | Fan state               | 0/1                            |
| 9   | Thermostat state        | not used yet (#67)             |
| 10  | Heated floors           | 0/1                            |
| 11  | Aux                     | not exposed yet (#66)          |

`buttons.cgi` momentary commands are not implemented yet (#69).

## Key Patterns

- **Coordinator pattern**: `RixensCoordinator` polls the device every 8 seconds
  and distributes data to all entities
- **Entity descriptions**: Sensors and switches use dataclass descriptions with
  `value_fn` callbacks for clean state extraction
- **API client**: `RixensApi` handles HTTP communication and XML parsing, uses
  Home Assistant's shared aiohttp session
- **Entities**: All entities inherit from `CoordinatorEntity` for automatic
  updates

## Platforms

| Platform      | Entities                                                                                                                              |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| climate       | Main thermostat (setpoint, current temp, fan modes, HVAC modes)                                                                       |
| sensor        | Temperature, humidity, Comfort Hot tank, battery voltage, flame/inlet/outlet temps, altitude, runtime, fuel used, faults, diagnostics |
| switch        | Furnace, floor heat, electric heat, hot water                                                                                         |
| fan           | Fan (on/off, 10-100% speed, auto preset)                                                                                              |
| binary_sensor | Connection status, heater fault                                                                                                       |
| event         | Heater fault detected                                                                                                                 |

## Development

**Testing in Home Assistant:**

1. Copy `custom_components/rixens/` to your HA `config/custom_components/`
   directory
2. Restart Home Assistant
3. Add integration via Settings > Devices & Services > Add Integration > Rixens
4. Enter device IP address (port defaults to 80)

**Adding new controls:**

1. Use the documented `Command` in `api.py` (or add a parsed field)
2. Add entity description in appropriate platform file
3. Add translation key in `strings.json` and `translations/en.json`
4. Add an icon for the translation key in `icons.json`

## Python Environment

Always activate the local venv before running any Python command:

```bash
source .venv/bin/activate
```

The project is pinned to **Python 3.14** (see `.python-version`). All commands
below assume the venv is active.

## Dev Commands

- **Test:**
  `source .venv/bin/activate && pytest tests/ -v --cov=custom_components/rixens`
- **Lint:** `source .venv/bin/activate && ruff check custom_components/`
- **Format:** `source .venv/bin/activate && ruff format custom_components/`
- **Type-check:** `source .venv/bin/activate && pyright custom_components/`

## Testing

- Tests live in `tests/` and mirror the module structure of
  `custom_components/rixens/`
- 90% code coverage threshold enforced by CI
- Use `aioresponses` for HTTP-level mocking
- See `CONTRIBUTING.md` for full testing requirements and patterns

## Code Navigation — Prefer Serena MCP Tools

When exploring or reading code in this project, **prefer Serena MCP tools** over
Read/Grep/Glob:

- `get_symbols_overview` — get a file's classes, functions, and methods without
  reading the full file
- `find_symbol` — locate a symbol by name path (e.g. `RixensApi/get_status`),
  optionally with `include_body=True`
- `find_referencing_symbols` — find all callers/users of a symbol before
  modifying it
- `search_for_pattern` — fast regex search across the codebase

Only fall back to Read/Grep/Glob when working with non-code files (JSON, YAML,
markdown) or when you need raw file content that isn't organized into symbols.
