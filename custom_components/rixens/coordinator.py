"""DataUpdateCoordinator for Rixens integration."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RixensApi, RixensApiError, RixensData
from .const import CONF_PORT, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=8)
MAX_FAILED_UPDATES_BEFORE_UNAVAILABLE = 6  # Keep last data for ~48s (6 * 8s)
COMMAND_REFRESH_DELAY = 1.0  # Seconds to wait after a command before refreshing


class RixensCoordinator(DataUpdateCoordinator[RixensData]):
    """Coordinator for Rixens data updates."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.config_entry = entry
        self.api = RixensApi(
            host=entry.data[CONF_HOST],
            port=entry.data.get(CONF_PORT, DEFAULT_PORT),
            session=async_get_clientsession(hass),
        )
        self._failed_update_count = 0
        self._last_successful_update: datetime | None = None
        self._is_available = True
        self._command_refresh_unsub: CALLBACK_TYPE | None = None

    async def _async_update_data(self) -> RixensData:
        """Fetch data from API with graceful degradation."""
        try:
            data = await self.api.get_status()
            # Successful update - reset counters
            if self._failed_update_count > 0:
                _LOGGER.info(
                    "Successfully reconnected to Rixens device after %d failed attempts",
                    self._failed_update_count,
                )
            self._failed_update_count = 0
            self._last_successful_update = datetime.now()
            self._is_available = True
            return data
        except RixensApiError as err:
            self._failed_update_count += 1

            # Keep last good data for a while before marking unavailable
            if self._failed_update_count <= MAX_FAILED_UPDATES_BEFORE_UNAVAILABLE:
                if self.data:
                    _LOGGER.warning(
                        "Failed to update Rixens device (attempt %d/%d), keeping last known state: %s",
                        self._failed_update_count,
                        MAX_FAILED_UPDATES_BEFORE_UNAVAILABLE,
                        err,
                    )
                    # Return last good data to keep entities available
                    return self.data

            # Too many failures - mark as unavailable
            if self._is_available:
                _LOGGER.error(
                    "Rixens device unavailable after %d failed updates. Last successful update: %s",
                    self._failed_update_count,
                    self._last_successful_update,
                )
                self._is_available = False

            raise UpdateFailed(
                f"Error communicating with Rixens device: {err}"
            ) from err

    @callback
    def async_refresh_after_command(self) -> None:
        """Schedule a refresh shortly after a user-initiated command.

        Command responses are not authoritative and reading status.xml
        immediately can race the device applying the change, so wait briefly.
        Each call restarts the timer, so rapid successive commands collapse into
        a single refresh after the last one. Bypasses the request debouncer.
        """
        self._cancel_command_refresh()
        self._command_refresh_unsub = async_call_later(
            self.hass, COMMAND_REFRESH_DELAY, self._async_command_refresh
        )

    def _cancel_command_refresh(self) -> None:
        """Cancel a pending post-command refresh."""
        if self._command_refresh_unsub is not None:
            self._command_refresh_unsub()
            self._command_refresh_unsub = None

    async def _async_command_refresh(self, _now: datetime) -> None:
        """Refresh after the post-command delay."""
        self._command_refresh_unsub = None
        await self.async_refresh()

    async def async_shutdown(self) -> None:
        """Cancel pending timers on shutdown."""
        self._cancel_command_refresh()
        await super().async_shutdown()

    @property
    def is_available(self) -> bool:
        """Return if the device is available."""
        return self._is_available
