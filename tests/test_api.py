"""Tests for the Rixens API client."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.rixens.api import (
    Command,
    RixensApi,
    RixensApiError,
    RixensConnectionError,
    RixensData,
)

from .conftest import SAMPLE_XML, SAMPLE_XML_1_208

BASE_URL = "http://192.168.1.1"


@pytest.fixture
def http() -> AiohttpClientMocker:
    """HTTP mocker from Home Assistant's test helpers."""
    return AiohttpClientMocker()


@pytest.fixture
async def api(http: AiohttpClientMocker) -> AsyncIterator[RixensApi]:
    """Create a RixensApi backed by an aiohttp session bound to ``http``."""
    session = http.create_session(asyncio.get_running_loop())
    yield RixensApi(host="192.168.1.1", session=session)
    await session.close()


def _in_order(url: str, *responses: dict) -> object:
    """Side effect that answers successive requests with ``responses``."""
    queue = iter(responses)

    async def side_effect(method, _url, _data):
        return AiohttpClientMockResponse(method, URL(url), **next(queue))

    return side_effect


def _parse(xml: str) -> RixensData:
    api = RixensApi(host="192.168.1.1", session=MagicMock(spec=aiohttp.ClientSession))
    return api._parse_status(xml)


# ---------------------------------------------------------------------------
# Construction & URL building
# ---------------------------------------------------------------------------


class TestRixensApiInit:
    """Tests for RixensApi initialization."""

    def _make(self, **kwargs) -> RixensApi:
        session = MagicMock(spec=aiohttp.ClientSession)
        return RixensApi(host="192.168.1.1", session=session, **kwargs)

    def test_default_port(self):
        assert self._make()._base_url == BASE_URL

    def test_port_80_no_port_in_url(self):
        assert self._make(port=80)._base_url == BASE_URL

    def test_custom_port(self):
        assert self._make(port=8080)._base_url == "http://192.168.1.1:8080"

    def test_session_stored(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        api = RixensApi(host="192.168.1.1", session=session)
        assert api._session is session


# ---------------------------------------------------------------------------
# _request & retry logic
# ---------------------------------------------------------------------------


class TestRequest:
    """Tests for HTTP request handling with retries."""

    async def test_successful_request(self, api, http):
        http.get(f"{BASE_URL}/status.xml", text=SAMPLE_XML)
        result = await api._request("/status.xml")
        assert "<version>" in result

    async def test_timeout_raises_connection_error(self, api, http):
        http.get(f"{BASE_URL}/status.xml", exc=TimeoutError())
        with pytest.raises(RixensConnectionError, match="Timeout"):
            await api._request("/status.xml")
        assert http.call_count == 3

    async def test_client_error_raises_connection_error(self, api, http):
        exc = aiohttp.ClientError("connection refused")
        http.get(f"{BASE_URL}/status.xml", exc=exc)
        with pytest.raises(RixensConnectionError, match="Error connecting"):
            await api._request("/status.xml")
        assert http.call_count == 3

    async def test_retry_then_success(self, api, http):
        url = f"{BASE_URL}/status.xml"
        http.get(
            url,
            side_effect=_in_order(url, {"exc": TimeoutError()}, {"text": "<ok/>"}),
        )
        result = await api._request("/status.xml")
        assert result == "<ok/>"
        assert http.call_count == 2

    async def test_no_retry_when_disabled(self, api, http):
        http.get(f"{BASE_URL}/status.xml", exc=TimeoutError())
        with pytest.raises(RixensConnectionError):
            await api._request("/status.xml", retry=False)
        assert http.call_count == 1

    async def test_http_error_status(self, api, http):
        http.get(f"{BASE_URL}/status.xml", status=500)
        with pytest.raises(RixensConnectionError):
            await api._request("/status.xml")


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------


class TestTestConnection:
    """Tests for the test_connection method."""

    async def test_returns_true_on_success(self, api, http):
        http.get(f"{BASE_URL}/status.xml", text=SAMPLE_XML)
        assert await api.test_connection() is True

    async def test_returns_false_on_failure(self, api, http):
        http.get(f"{BASE_URL}/status.xml", exc=TimeoutError())
        assert await api.test_connection() is False


# ---------------------------------------------------------------------------
# get_status & _parse_status
# ---------------------------------------------------------------------------


class TestParseStatus:
    """Tests for XML parsing of the HW2-1.205 sample."""

    def test_parses_sample_xml(self):
        data = _parse(SAMPLE_XML)
        assert data.version == "HW2-1.205 2025_11_20 RIXENS"
        assert data.heat_version == "1.06 2025-11-21 PID"
        assert data.uptime == 146691
        assert data.system_heat is True
        assert data.heater_state == 20
        assert data.current_temp == 17.1
        assert data.current_humidity == 14.5

    def test_heater_data(self):
        h = _parse(SAMPLE_XML).heater
        assert h.heat_on is True
        assert h.battery_voltage == 12.5
        assert h.runtime == 114236
        assert h.pid_speed == 73
        assert h.flame_temp == 145.25
        assert h.inlet_temp == 70.75
        assert h.outlet_temp == 73.0
        assert h.atmospheric_pressure == 997.2
        assert h.dosing_pump == 1.6
        assert h.burner_motor == 3532
        assert h.glow_pin == 0
        assert h.preheat == 0

    def test_faults(self):
        data = _parse(SAMPLE_XML)
        assert data.heater.faults == {"AF": 0, "F1": 0}

    def test_settings(self):
        s = _parse(SAMPLE_XML).settings
        assert s.setpoint == 18.0
        assert s.fan_speed == "Auto"
        assert s.pump_state is True
        assert s.fan_state is True
        assert s.floor_enable is True
        assert s.electric_enable is True
        assert s.glycol == 0
        assert s.furnace_src == 2
        assert s.electric_src == 0
        assert s.engine_src == 0
        assert s.floor_src == 2

    def test_invalid_xml_raises_api_error(self):
        with pytest.raises(RixensApiError, match="Failed to parse"):
            _parse("not xml at all <<<")

    def test_missing_heater1_element(self):
        xml = (
            "<response><version>1.0</version><currenttemp>200</currenttemp></response>"
        )
        data = _parse(xml)
        assert data.heater.heat_on is False
        assert data.heater.battery_voltage == 0.0
        assert data.heater.faults == {}
        assert data.current_temp == 20.0

    def test_missing_settings_element(self):
        data = _parse("<response><version>1.0</version></response>")
        assert data.settings.setpoint == 20.0
        assert data.settings.fan_speed == "Auto"
        assert data.settings.furnace_src == 0

    def test_empty_text_defaults(self):
        xml = """<response>
        <version></version>
        <currenttemp></currenttemp>
        <heater1><heaton></heaton><battv></battv></heater1>
        <settings><setpoint></setpoint></settings>
        </response>"""
        data = _parse(xml)
        assert data.version == "Unknown"  # empty text triggers default
        assert data.current_temp == 0.0

    def test_glycol_is_int(self):
        """settings.glycol is parsed as an int, not a bool."""
        xml = "<response><settings><glycol>3</glycol></settings></response>"
        assert _parse(xml).settings.glycol == 3

    def test_glycolstate_is_tank_status(self):
        """glycolstate carries the 0-2 Comfort Hot tank status."""
        xml = "<response><glycolstate>1</glycolstate></response>"
        assert _parse(xml).glycol_state == 1

    def test_fanspeed_999_is_auto(self):
        xml = "<response><settings><fanspeed>999</fanspeed></settings></response>"
        assert _parse(xml).settings.fan_speed == "Auto"

    def test_fanspeed_numeric_passthrough(self):
        xml = "<response><settings><fanspeed>40</fanspeed></settings></response>"
        assert _parse(xml).settings.fan_speed == "40"

    def test_escaped_entities_untouched(self):
        xml = "<response><version>A&amp;B &#38; C</version></response>"
        assert _parse(xml).version == "A&B & C"

    async def test_get_status_integration(self, api, http):
        http.get(f"{BASE_URL}/status.xml", text=SAMPLE_XML)
        data = await api.get_status()
        assert isinstance(data, RixensData)
        assert data.version == "HW2-1.205 2025_11_20 RIXENS"


class TestParseStatusManufacturerSample:
    """Tests for the manufacturer's HW2-1.208 sample from the official docs."""

    def test_parses_despite_bare_ampersand(self):
        """<infra_ssid>R&DRouter</infra_ssid> is not escaped by the device."""
        data = _parse(SAMPLE_XML_1_208)
        assert data.version == "HW2-1.208 2026_05_11 RIXENS"
        assert data.heat_version == "1.07 2026-04-25"

    def test_no_sensor_sentinels_are_none(self):
        """currenttemp=-9990 and currenthumidity=-999 mean no sensor."""
        data = _parse(SAMPLE_XML_1_208)
        assert data.current_temp is None
        assert data.current_humidity is None

    def test_settings(self):
        s = _parse(SAMPLE_XML_1_208).settings
        assert s.setpoint == 23.9
        assert s.fan_speed == "95"
        assert s.therm_enabled is True
        assert s.engine_enable is True
        assert s.floor_enable is False
        assert s.cnst_heat == 0

    def test_heater_and_faults(self):
        data = _parse(SAMPLE_XML_1_208)
        assert data.heater.atmospheric_pressure == 986.0
        assert data.heater.faults == {
            "AF": 255,
            "F1": 0,
            "F2": 0,
            "F3": 0,
            "F4": 0,
            "F5": 0,
        }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


class TestCommands:
    """Tests for device commands."""

    def test_documented_command_ids(self):
        assert {c.name: c.value for c in Command} == {
            "TARGET_TEMPERATURE": 1,
            "FAN_SPEED": 2,
            "ENGINE_ADD_HEAT": 3,
            "ELECTRIC_HEAT": 4,
            "FURNACE": 5,
            "HOT_WATER": 6,
            "ENGINE_PREHEAT": 7,
            "FAN_STATE": 8,
            "THERMOSTAT_STATE": 9,
            "HEATED_FLOORS": 10,
            "AUX": 11,
        }

    @pytest.mark.parametrize(
        ("command", "value", "query"),
        [
            (Command.FAN_SPEED, 50, "act=2&val=50"),
            (Command.FAN_SPEED, 999, "act=2&val=999"),
            (Command.ELECTRIC_HEAT, True, "act=4&val=1"),
            (Command.FURNACE, True, "act=5&val=1"),
            (Command.FURNACE, False, "act=5&val=0"),
            (Command.HOT_WATER, True, "act=6&val=1"),
            (Command.FAN_STATE, False, "act=8&val=0"),
            (Command.HEATED_FLOORS, True, "act=10&val=1"),
        ],
    )
    async def test_send_command(self, api, http, command, value, query):
        http.get(f"{BASE_URL}/interface.cgi?{query}", text="OK")
        await api.send_command(command, value)
        assert http.call_count == 1

    @pytest.mark.parametrize(
        ("celsius", "raw"),
        [
            (22.5, 225),
            # Docs examples: 75°F -> 239, 80°F -> 267, 85°F -> 294
            ((75 - 32) / 1.8, 239),
            ((80 - 32) / 1.8, 267),
            ((85 - 32) / 1.8, 294),
            # Halves round up, like JavaScript's Math.round
            (22.25, 223),
        ],
    )
    async def test_set_temperature_rounds(self, api, http, celsius, raw):
        http.get(f"{BASE_URL}/interface.cgi?act=1&val={raw}", text="OK")
        await api.set_temperature(celsius)
        assert http.call_count == 1
