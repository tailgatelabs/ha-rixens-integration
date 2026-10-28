"""API client for Rixens devices.

Implements the Rixen's MCS Local API:
https://documenter.getpostman.com/view/55318949/2sBXwnsBuf

"The controller is state-owned. Command endpoints submit intent, but actual
system state must be verified by reading status.xml." Command responses are
therefore ignored and the coordinator refreshes from status.xml instead.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass
from enum import IntEnum
from xml.etree import ElementTree

import aiohttp

from .const import DEVICE_FAN_AUTO, FAN_SPEED_AUTO

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

# Raw values the device reports when no cabin sensor is connected
NO_SENSOR_TEMP = -9990
NO_SENSOR_HUMIDITY = -999

# The device does not escape "&" in strings (e.g. <infra_ssid>R&DRouter</infra_ssid>),
# which makes the XML invalid. Matches any "&" that does not start an entity.
_BARE_AMPERSAND = re.compile(r"&(?!(?:[A-Za-z]+|#[0-9]+|#x[0-9A-Fa-f]+);)")


class Command(IntEnum):
    """Command IDs for GET /interface.cgi?act=<id>&val=<int>.

    "All values must be base-10 integers. Do not send floats, decimals, or
    string booleans."
    """

    TARGET_TEMPERATURE = 1  # Target temperature (tenths °C)
    # Fan speed (0-100, 999 = Auto). 0 sets 0% (it does not turn the fan off;
    # that is FAN_STATE); values outside 0-100 are clamped, per Rixen's (#72)
    FAN_SPEED = 2
    ENGINE_ADD_HEAT = 3  # Engine add heat
    ELECTRIC_HEAT = 4  # Electric heat
    FURNACE = 5  # Furnace
    HOT_WATER = 6  # Hot water
    ENGINE_PREHEAT = 7  # Engine pre-heat
    FAN_STATE = 8  # Fan state
    THERMOSTAT_STATE = 9  # Thermostat state
    HEATED_FLOORS = 10  # Heated floors
    AUX = 11  # Aux


@dataclass
class RixensHeaterData:
    """Heater-specific data from the <heater1> element."""

    heat_on: bool  # Furnace commanded state (0 = Off, 1 = On)
    battery_voltage: float  # Battery voltage reading (scale undocumented, see #72)
    # ECU lifetime operating time in minutes. The docs say "hours"; Rixen's
    # confirmed minutes (their web portal shows hours), see #72
    runtime: int
    pid_speed: int  # PID controller speed/effort
    flame_temp: float  # Furnace flame temperature. Note: Divide by 100 for °C
    inlet_temp: float  # Glycol inlet temperature. Note: Divide by 100 for °C
    outlet_temp: float  # Glycol outlet temperature. Note: Divide by 100 for °C
    # Docs: "Altitude reading from mbed"; values are atmospheric pressure in hPa, see #72
    atmospheric_pressure: float
    dosing_pump: float  # Dosing pump (Hz); raw value is divided by 10, see #72
    burner_motor: int  # Burner motor speed
    # Eberspacher defined state (0-40, 200 error state), see HEATER_STATES
    heater_state: int
    glow_pin: int  # Glow pin (percent)
    # Furnace in preheat mode (This is an Eberspacher feature, not to be
    # confused with Rixen Preheat Engine)
    preheat: int
    faults: dict[str, int]


@dataclass
class RixensSettings:
    """Settings data from the <settings> element."""

    setpoint: float  # Target cabin temperature. Note: Divide by 10 for °C
    # "Off", a manual speed percentage (0-100) or "Auto" (not 999), per Rixen's
    fan_speed: str
    pump_state: bool  # Circulation pump operational state (0 = Off, 1 = On)
    fan_state: bool  # Air handler fan operational state (0 = Off, 1 = On)
    # "<x> button showing in Rixen web portal (0 = Off, 1 = On)"
    floor_enable: bool
    electric_enable: bool
    engine_enable: bool
    preheat_enable: bool
    aux_enable: bool
    fan_enabled: bool  # Air handler fan toggle state (0 = Off, 1 = On)
    therm_enabled: bool  # Thermostat toggle state (0 = Off, 1 = On)
    # Docs: "Comfort Hot tank status: 0 = Off, 1 = Warming, 2 = Ready (122°F),
    # 3 = Max (158°F)". The tank status is in glycolstate instead; Rixen's say
    # this field may no longer be used, see #72
    glycol: int
    # Bitmask of active heat sources: furnace = 4, electric = 2, engine = 1
    # (confirmed by Rixen's). Live data also sets 8 while floor heat is
    # active, which their answer does not cover, see #72
    heatsources: int
    # Hardware state of each heat source (0 = Off, 1 = ready, 2 = active)
    aux_src: int
    floor_src: int
    furnace_src: int
    electric_src: int
    engine_src: int
    cnst_heat: int  # Hot Water mode state (0 = Off, 1 = On)


@dataclass
class RixensData:
    """Data from the root of status.xml."""

    version: str  # Hardware and firmware version string
    heat_version: str  # Heating logic version string
    uptime: int  # Controller awake time in seconds (Resets on power cycle)
    system_heat: bool  # Overall system heat state (0 = Off, 1 = On)
    # Eberspacher defined state (0-40, 200 error state), see HEATER_STATES
    heater_state: int
    zone2_state: int  # State of zone 2
    zone3_state: int  # State of zone 3
    engine_state: int  # Engine add heat enabled (0 = Off, 1 = On)
    # Glycol tank up to temp. The docs say "0 = No, 1 = Yes"; Rixen's added
    # 2: 0 = No, 1 = Yes (yellow dot, 120-160°F), 2 = Yes (red dot, above
    # 160°F), see #72
    glycol_state: int
    # Current cabin temperature in °C, None when no sensor is connected
    current_temp: float | None
    # Current cabin humidity in %, None when no sensor is connected
    current_humidity: float | None
    heater: RixensHeaterData
    settings: RixensSettings


class RixensApiError(Exception):
    """Exception for Rixens API errors."""


class RixensConnectionError(RixensApiError):
    """Exception for connection errors."""


class RixensApi:
    """API client for Rixens devices."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        port: int = 80,
    ) -> None:
        """Initialize the API client."""
        self._host = host
        self._port = port
        self._session = session
        self._base_url = f"http://{host}:{port}" if port != 80 else f"http://{host}"

    async def _request(self, path: str, retry: bool = True) -> str:
        """Make a request to the device with retry logic.

        Args:
            path: API path to request
            retry: Whether to retry on failure (default: True)

        Returns:
            Response text from the device

        Raises:
            RixensConnectionError: If all retries fail
        """
        url = f"{self._base_url}{path}"
        retries = MAX_RETRIES if retry else 1

        for attempt in range(retries):
            try:
                async with asyncio.timeout(DEFAULT_TIMEOUT):
                    async with self._session.get(url) as response:
                        response.raise_for_status()
                        if attempt > 0:
                            _LOGGER.info(
                                "Successfully connected to %s after %d retry attempt(s)",
                                url,
                                attempt,
                            )
                        return await response.text()
            except (TimeoutError, aiohttp.ClientError) as err:
                if isinstance(err, TimeoutError):
                    error_msg = f"Timeout connecting to {url}"
                else:
                    error_msg = f"Error connecting to {url}: {err}"

                if attempt < retries - 1:
                    delay = RETRY_DELAY * (attempt + 1)
                    _LOGGER.warning(
                        "%s (attempt %d/%d), retrying in %ds...",
                        error_msg,
                        attempt + 1,
                        retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                _LOGGER.error("%s after %d attempts", error_msg, retries)
                raise RixensConnectionError(
                    f"{error_msg} after {retries} attempts"
                ) from err

        raise AssertionError("unreachable")  # pragma: no cover

    async def test_connection(self) -> bool:
        """Test the connection to the device."""
        try:
            await self.get_status()
            return True
        except RixensApiError:
            return False

    async def get_status(self) -> RixensData:
        """Get the current status from the device (GET /status.xml)."""
        response = await self._request("/status.xml")
        return self._parse_status(response)

    def _parse_status(self, xml_text: str) -> RixensData:
        """Parse the status XML response.

        The XML includes Wi-Fi credentials (key, infra_pass); never log it.
        """
        try:
            root = ElementTree.fromstring(_BARE_AMPERSAND.sub("&amp;", xml_text))
        except ElementTree.ParseError as err:
            raise RixensApiError(f"Failed to parse status XML: {err}") from err

        def find(tag: str) -> ElementTree.Element:
            # A missing section parses as empty, so every field gets its default
            elem = root.find(tag)
            return elem if elem is not None else ElementTree.Element(tag)

        def get_text(parent: ElementTree.Element, tag: str, default: str = "0") -> str:
            elem = parent.find(tag)
            return elem.text if elem is not None and elem.text else default

        def get_int(parent: ElementTree.Element, tag: str, default: int = 0) -> int:
            try:
                return int(get_text(parent, tag, str(default)))
            except ValueError:
                return default

        def get_float(
            parent: ElementTree.Element, tag: str, default: float = 0.0
        ) -> float:
            try:
                return float(get_text(parent, tag, str(default)))
            except ValueError:
                return default

        def get_bool(parent: ElementTree.Element, tag: str) -> bool:
            return get_int(parent, tag) == 1

        heater1 = find("heater1")
        heater_data = RixensHeaterData(
            heat_on=get_bool(heater1, "heaton"),
            battery_voltage=get_int(heater1, "battv") / 10.0,
            runtime=get_int(heater1, "runtime"),
            pid_speed=get_int(heater1, "pidspeed"),
            flame_temp=get_int(heater1, "flametemp") / 100.0,
            inlet_temp=get_int(heater1, "inlettemp") / 100.0,
            outlet_temp=get_int(heater1, "outlettemp") / 100.0,
            atmospheric_pressure=get_float(heater1, "altitude"),
            dosing_pump=get_int(heater1, "dosingpump") / 10.0,
            burner_motor=get_int(heater1, "burnermotor"),
            heater_state=get_int(heater1, "heaterstate"),
            glow_pin=get_int(heater1, "glowpin"),
            preheat=get_int(heater1, "preheat"),
            faults={},
        )

        for fault in find("heater1-faults").findall("fault"):
            name = get_text(fault, "name", "")
            if name:
                heater_data.faults[name] = get_int(fault, "value")

        settings_elem = find("settings")
        fan_speed = get_text(settings_elem, "fanspeed", DEVICE_FAN_AUTO)
        # Firmware reports "Auto"; the docs specify 999 = Auto, so accept both
        if fan_speed == str(FAN_SPEED_AUTO):
            fan_speed = DEVICE_FAN_AUTO

        settings = RixensSettings(
            setpoint=get_int(settings_elem, "setpoint", 200) / 10.0,
            fan_speed=fan_speed,
            pump_state=get_bool(settings_elem, "pumpstate"),
            fan_state=get_bool(settings_elem, "fanstate"),
            floor_enable=get_bool(settings_elem, "floorenable"),
            electric_enable=get_bool(settings_elem, "electricenable"),
            engine_enable=get_bool(settings_elem, "engineenable"),
            preheat_enable=get_bool(settings_elem, "preheatenable"),
            aux_enable=get_bool(settings_elem, "auxenable"),
            fan_enabled=get_bool(settings_elem, "fanenabled"),
            therm_enabled=get_bool(settings_elem, "thermenabled"),
            glycol=get_int(settings_elem, "glycol"),
            heatsources=get_int(settings_elem, "heatsources"),
            aux_src=get_int(settings_elem, "auxsrc"),
            floor_src=get_int(settings_elem, "floorsrc"),
            furnace_src=get_int(settings_elem, "furnacesrc"),
            electric_src=get_int(settings_elem, "electricsrc"),
            engine_src=get_int(settings_elem, "enginesrc"),
            cnst_heat=get_int(settings_elem, "cnstheat"),
        )

        raw_temp = get_int(root, "currenttemp")
        # Docs field table says "percentage", but the overview and real data
        # are tenths %RH, see #72
        raw_humidity = get_int(root, "currenthumidity")

        return RixensData(
            version=get_text(root, "version", "Unknown"),
            heat_version=get_text(root, "heatversion", "Unknown"),
            uptime=get_int(root, "uptime"),
            system_heat=get_bool(root, "systemheat"),
            heater_state=get_int(root, "heaterstate"),
            zone2_state=get_int(root, "zone2state"),
            zone3_state=get_int(root, "zone3state"),
            engine_state=get_int(root, "enginestate"),
            glycol_state=get_int(root, "glycolstate"),
            current_temp=None if raw_temp == NO_SENSOR_TEMP else raw_temp / 10.0,
            current_humidity=None
            if raw_humidity == NO_SENSOR_HUMIDITY
            else raw_humidity / 10.0,
            heater=heater_data,
            settings=settings,
        )

    async def send_command(self, command: Command, value: int) -> None:
        """Send a command (GET /interface.cgi?act=<id>&val=<int>).

        Booleans are sent as 0/1.
        """
        await self._request(f"/interface.cgi?act={int(command)}&val={int(value)}")

    async def set_temperature(self, temperature: float) -> None:
        """Set the target temperature in Celsius.

        Docs: "Celsius to API value: val = Math.round(C * 10)". JavaScript's
        Math.round rounds halves up, unlike Python's round().
        """
        await self.send_command(
            Command.TARGET_TEMPERATURE, math.floor(temperature * 10 + 0.5)
        )
