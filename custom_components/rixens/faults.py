"""Heater fault codes for the Rixens integration.

status.xml reports faults in <heater1-faults> as AF (active fault) and F1-F5
(stored faults, F1 most recent). The official API docs do not describe these
fields or their codes, so the names below are the classic numeric Eberspächer
fault codes where two public references agree:

- https://www.pfjones.co.uk/advice-centre/eberspacher-advice/eberspacher-fault-codes.html
- https://www.butlertechnik.com/eberspacher-fault-codes-for-airtronic-and-espar-hydronic-heaters

They have not been confirmed by Rixen's (see #76). Codes not listed map to
FAULT_OTHER, and the raw code is always exposed alongside the name.
"""

from __future__ import annotations

from .api import RixensData

# heaterstate value documented as "200 error state"
HEATER_STATE_ERROR = 200

# Raw value that does not name a fault. Seen as AF=255 in the manufacturer's
# sample with the heater off and no battery voltage; treated as "no data".
FAULT_NO_DATA = 255

FAULT_NONE = "no_fault"
FAULT_OTHER = "other"

FAULT_CODES: dict[int, str] = {
    0: FAULT_NONE,
    10: "overvoltage",
    11: "undervoltage",
    12: "overheating",
    14: "overheating_sensor_difference",
    15: "overheating_lockout",
    17: "overheating_hardware",
    20: "glow_plug_open",
    21: "glow_plug_short",
    22: "glow_plug_short_to_positive",
    47: "metering_pump_short",
    48: "metering_pump_open",
    49: "metering_pump_short_to_positive",
    50: "start_lockout",
    52: "start_failed",
    53: "flame_cutout",
    54: "flame_cutout",
    55: "flame_cutout",
    56: "flame_cutout",
    60: "room_sensor_open",
    61: "room_sensor_short",
    64: "flame_sensor_open",
    65: "flame_sensor_short",
    71: "overheating_sensor_open",
    72: "overheating_sensor_short",
    74: "control_box_defective",
    90: "control_box_defective",
    92: "control_box_defective",
    93: "control_box_defective",
    94: "control_box_defective",
    95: "control_box_defective",
    97: "control_box_defective",
    98: "control_box_defective",
    99: "too_many_resets",
}

# Every state a fault enum sensor can report, in a stable order
FAULT_OPTIONS: list[str] = [*dict.fromkeys(FAULT_CODES.values()), FAULT_OTHER]

STORED_FAULT_NAMES = ("F1", "F2", "F3", "F4", "F5")


def fault_key(code: int | None) -> str | None:
    """Return the fault name for a raw code, or None when there is no data."""
    if code is None or code == FAULT_NO_DATA:
        return None
    return FAULT_CODES.get(code, FAULT_OTHER)


def is_fault(code: int | None) -> bool:
    """Return True if a raw code names an actual fault."""
    return fault_key(code) not in (None, FAULT_NONE)


def active_fault_code(data: RixensData) -> int | None:
    """Return the raw active fault code (AF), or None if not reported."""
    return data.heater.faults.get("AF")


def stored_fault_codes(data: RixensData) -> list[int]:
    """Return the raw stored fault codes, most recent (F1) first."""
    faults = data.heater.faults
    return [faults[name] for name in STORED_FAULT_NAMES if name in faults]
