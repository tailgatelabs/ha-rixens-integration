"""Optimistic state helper for user-initiated commands."""

from __future__ import annotations

import time

# Command responses are not authoritative, so an assumed value is only shown
# until the device reports it back via status.xml, or until this many seconds
# pass (covers a command the device silently ignored).
OPTIMISTIC_TIMEOUT = 10.0


class OptimisticState[T]:
    """Holds a commanded value until the device reports it (or it expires)."""

    def __init__(self, timeout: float = OPTIMISTIC_TIMEOUT) -> None:
        """Initialize with nothing pending."""
        self._timeout = timeout
        self._pending = False
        self._value: T | None = None
        self._deadline = 0.0

    def set(self, value: T) -> None:
        """Assume ``value`` until the device confirms it."""
        self._value = value
        self._deadline = time.monotonic() + self._timeout
        self._pending = True

    def clear(self) -> None:
        """Drop any pending value."""
        self._pending = False
        self._value = None

    def resolve(self, actual: T | None) -> T | None:
        """Return the value to show given the device-reported ``actual``.

        The pending value wins until ``actual`` matches it or it expires.
        """
        if not self._pending:
            return actual
        if actual == self._value or time.monotonic() >= self._deadline:
            self.clear()
            return actual
        return self._value
