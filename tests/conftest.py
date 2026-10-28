"""Shared fixtures for Rixens integration tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry

from custom_components.rixens.api import (
    RixensApi,
    RixensData,
    RixensHeaterData,
    RixensSettings,
)
from custom_components.rixens.const import CONF_HOST, CONF_PORT, DEFAULT_PORT
from custom_components.rixens.coordinator import RixensCoordinator

# Manufacturer's sample from the official API docs (firmware HW2-1.208),
# Wi-Fi credentials redacted. Contains a bare "&" and no-sensor sentinels.
SAMPLE_XML_1_208 = (
    Path(__file__).parent.parent / "example_mcs7_status_hw2-1.208.xml"
).read_text()

SAMPLE_XML = """\
<response>
<version>HW2-1.205 2025_11_20 RIXENS</version>
<heatversion>1.06 2025-11-21 PID</heatversion>
<mode>1</mode>
<uptime>146691</uptime>
<systemheat>1</systemheat>
<heaterstate>20</heaterstate>
<zone2state>0</zone2state>
<zone3state>0</zone3state>
<enginestate>0</enginestate>
<glycolstate>2</glycolstate>
<currenttemp>171</currenttemp>
<currenthumidity>145</currenthumidity>
<heater1>
<heaton>1</heaton>
<battv>125</battv>
<runtime>114236</runtime>
<pidspeed>73</pidspeed>
<flametemp>14525</flametemp>
<inlettemp>7075</inlettemp>
<outlettemp>7300</outlettemp>
<altitude>997.200000</altitude>
<dosingpump>16</dosingpump>
<burnermotor>3532</burnermotor>
<glowpin>0</glowpin>
<heaterstate>20</heaterstate>
<preheat>0</preheat>
</heater1>
<heater1-faults>
  <fault><name>AF</name><value>0</value></fault>
  <fault><name>F1</name><value>0</value></fault>
</heater1-faults>
<settings>
  <setpoint>180</setpoint>
  <fanspeed>Auto</fanspeed>
  <pumpstate>1</pumpstate>
  <fanstate>1</fanstate>
  <floorenable>1</floorenable>
  <glycol>0</glycol>
  <engineenable>0</engineenable>
  <electricenable>1</electricenable>
  <preheatenable>0</preheatenable>
  <auxenable>0</auxenable>
  <fanenabled>1</fanenabled>
  <thermenabled>1</thermenabled>
  <heatsources>12</heatsources>
  <auxsrc>0</auxsrc>
  <floorsrc>2</floorsrc>
  <furnacesrc>2</furnacesrc>
  <electricsrc>0</electricsrc>
  <enginesrc>0</enginesrc>
  <cnstheat>0</cnstheat>
</settings>
</response>
"""


def make_rixens_data(
    *,
    current_temp: float | None = 17.1,
    current_humidity: float | None = 14.5,
    system_heat: bool = True,
    heater_state: int = 20,
    setpoint: float | None = 18.0,
    fan_speed: str = "Auto",
    pump_state: bool = True,
    fan_state: bool = True,
    floor_enable: bool = True,
    electric_enable: bool = True,
    furnace_src: int = 2,
    electric_src: int = 0,
    engine_src: int = 0,
    floor_src: int = 2,
    cnst_heat: int = 0,
    cnst_heat_timer_val: int | None = None,
    engine_state: int = 0,
    therm_enabled: bool = True,
    glycol_state: int = 2,
    heat_on: bool = True,
    battery_voltage: float = 12.5,
    runtime: int = 114236,
    pid_speed: int = 73,
    flame_temp: float = 145.25,
    inlet_temp: float = 70.75,
    outlet_temp: float = 73.0,
    atmospheric_pressure: float = 997.2,
    dosing_pump: float = 1.6,
    burner_motor: int = 3532,
    glow_pin: int = 0,
    preheat: int = 0,
    faults: dict[str, int] | None = None,
    version: str = "HW2-1.205 2025_11_20 RIXENS",
    heat_version: str = "1.06 2025-11-21 PID",
    uptime: int = 146691,
) -> RixensData:
    """Create a RixensData instance with sensible defaults for testing."""
    return RixensData(
        version=version,
        heat_version=heat_version,
        uptime=uptime,
        system_heat=system_heat,
        heater_state=heater_state,
        zone2_state=0,
        zone3_state=0,
        engine_state=engine_state,
        glycol_state=glycol_state,
        current_temp=current_temp,
        current_humidity=current_humidity,
        heater=RixensHeaterData(
            heat_on=heat_on,
            battery_voltage=battery_voltage,
            runtime=runtime,
            pid_speed=pid_speed,
            flame_temp=flame_temp,
            inlet_temp=inlet_temp,
            outlet_temp=outlet_temp,
            atmospheric_pressure=atmospheric_pressure,
            dosing_pump=dosing_pump,
            burner_motor=burner_motor,
            heater_state=heater_state,
            glow_pin=glow_pin,
            preheat=preheat,
            faults=(
                {name: 0 for name in ("AF", "F1", "F2", "F3", "F4", "F5")}
                if faults is None
                else faults
            ),
        ),
        settings=RixensSettings(
            setpoint=setpoint,
            fan_speed=fan_speed,
            pump_state=pump_state,
            fan_state=fan_state,
            floor_enable=floor_enable,
            electric_enable=electric_enable,
            engine_enable=False,
            preheat_enable=False,
            aux_enable=False,
            fan_enabled=True,
            therm_enabled=therm_enabled,
            glycol=0,
            heatsources=12,
            aux_src=0,
            floor_src=floor_src,
            furnace_src=furnace_src,
            electric_src=electric_src,
            engine_src=engine_src,
            cnst_heat=cnst_heat,
            cnst_heat_timer_val=cnst_heat_timer_val,
        ),
    )


@pytest.fixture
def mock_config_entry() -> ConfigEntry:
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: "192.168.1.100", CONF_PORT: DEFAULT_PORT}
    entry.options = {}
    return entry


@pytest.fixture
def mock_api() -> AsyncMock:
    """Create a mock RixensApi."""
    api = AsyncMock(spec=RixensApi)
    api.get_status = AsyncMock(return_value=make_rixens_data())
    api.test_connection = AsyncMock(return_value=True)
    api.set_temperature = AsyncMock()
    api.send_command = AsyncMock()
    return api


def sent_commands(api: AsyncMock) -> list[tuple[Any, ...]]:
    """Return the (command, value) pairs sent through a mock API, in order."""
    return [call.args for call in api.send_command.await_args_list]


@pytest.fixture
def mock_coordinator(mock_config_entry, mock_api) -> MagicMock:
    """Create a mock RixensCoordinator."""
    coordinator = MagicMock(spec=RixensCoordinator)
    coordinator.data = make_rixens_data()
    coordinator.config_entry = mock_config_entry
    coordinator.api = mock_api
    coordinator.async_refresh_after_command = MagicMock()
    coordinator.is_available = True
    return coordinator
