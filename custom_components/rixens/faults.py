"""Heater fault codes for the Rixens integration.

status.xml reports faults in <heater1-faults> as AF (active fault) and F1-F5
(stored faults, F1 most recent). The official API docs do not describe these
fields. The values are the classic numeric Eberspächer fault codes (0-255).

Descriptions and error classes come from Eberspächer's fault code table for
the Hydronic S3 CS (repair instructions 25.2696.95.2682.0D, 05.2020), which
lists faults only as P-codes. Each P-code is matched to its numeric code using
the pairs published at
https://www.butlertechnik.com/eberspacher-fault-codes-for-airtronic-and-espar-hydronic-heaters

P-codes with no published numeric code (e.g. water pump faults P000250-P000259)
are not listed and report FAULT_OTHER until a real fault shows their value.
The mapping is unconfirmed by Rixen's (see #76); the raw code is always exposed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .api import RixensData

# heaterstate value documented as "200 error state"
HEATER_STATE_ERROR = 200

# Raw value that does not name a fault. Seen as AF=255 in the manufacturer's
# sample with the heater off and no battery voltage; treated as "no data".
FAULT_NO_DATA = 255

FAULT_NONE = "no_fault"
FAULT_OTHER = "other"

# Error classes from the Hydronic S3 CS fault code table
CLASS_SERVICE = "service"
CLASS_UNDERVOLTAGE = "undervoltage"
CLASS_OVERVOLTAGE = "overvoltage"
CLASS_FUEL = "fuel_supply_or_pump"
CLASS_WATER = "water_circuit_or_pump"
CLASS_LOCKED = "overheat_heater_locked"
CLASS_RESTRICTED = "restricted_operation"

FAULT_CLASSES = [
    CLASS_SERVICE,
    CLASS_UNDERVOLTAGE,
    CLASS_OVERVOLTAGE,
    CLASS_FUEL,
    CLASS_WATER,
    CLASS_LOCKED,
    CLASS_RESTRICTED,
]


@dataclass(frozen=True)
class FaultInfo:
    """A known fault code."""

    key: str  # Translation key and enum sensor state
    p_code: str | None  # Eberspächer diagnostic code, as shown by EasyScan
    fault_class: str | None  # Error class from the Hydronic S3 CS table


FAULT_CODES: dict[int, FaultInfo] = {
    0: FaultInfo(FAULT_NONE, None, None),
    6: FaultInfo("air_pressure_sensor", "P000143", CLASS_RESTRICTED),
    10: FaultInfo("overvoltage", "P000310/P000311", CLASS_OVERVOLTAGE),
    11: FaultInfo("undervoltage", "P000312/P000313", CLASS_UNDERVOLTAGE),
    12: FaultInfo("overheating", "P000115", CLASS_WATER),
    14: FaultInfo("overheating_risk", "P000114", CLASS_SERVICE),
    15: FaultInfo("overheating_lockout", "P00011A", CLASS_LOCKED),
    17: FaultInfo("overheating_hardware", "P000116", CLASS_WATER),
    19: FaultInfo("glow_plug_ignition_energy_low", "P000213", CLASS_SERVICE),
    20: FaultInfo("glow_plug_open", "P000210", CLASS_SERVICE),
    21: FaultInfo("glow_plug_short", "P000211", CLASS_SERVICE),
    22: FaultInfo("glow_plug_short_to_positive", "P000212", CLASS_SERVICE),
    34: FaultInfo("burner_motor_blocked", "P000223", CLASS_SERVICE),
    35: FaultInfo("burner_motor_current_high", "P000224", CLASS_SERVICE),
    47: FaultInfo("metering_pump_short", "P000201", CLASS_FUEL),
    48: FaultInfo("metering_pump_open", "P000200", CLASS_FUEL),
    49: FaultInfo("metering_pump_short_to_positive", "P000202", CLASS_FUEL),
    50: FaultInfo("start_lockout", "P00012B", CLASS_SERVICE),
    51: FaultInfo("cold_air_timeout", "P00010A", CLASS_SERVICE),
    52: FaultInfo("start_failed", "P00012A", CLASS_FUEL),
    53: FaultInfo("flame_cutout", "P000126", CLASS_SERVICE),
    54: FaultInfo("flame_cutout", "P000127", CLASS_SERVICE),
    55: FaultInfo("flame_cutout", "P000128", CLASS_SERVICE),
    56: FaultInfo("flame_cutout", "P000129", CLASS_SERVICE),
    57: FaultInfo("flame_cutout_start", "P000125", CLASS_SERVICE),
    64: FaultInfo("flame_sensor_open", "P000120", CLASS_SERVICE),
    65: FaultInfo("flame_sensor_short", "P000121", CLASS_SERVICE),
    71: FaultInfo("water_outlet_sensor_open", "P000100", CLASS_SERVICE),
    72: FaultInfo("water_outlet_sensor_short", "P000101", CLASS_SERVICE),
    73: FaultInfo("water_outlet_sensor_short_to_positive", "P000102", CLASS_SERVICE),
    74: FaultInfo("overheating_detection_defective", "P000300", CLASS_SERVICE),
    81: FaultInfo("can_communication_error", "P000307", CLASS_SERVICE),
    87: FaultInfo("water_inlet_sensor_open", "P000110", CLASS_SERVICE),
    88: FaultInfo("water_inlet_sensor_short", "P000111", CLASS_SERVICE),
    89: FaultInfo("water_inlet_sensor_short_to_positive", "P000112", CLASS_SERVICE),
    90: FaultInfo("watchdog_reset", "P000301/P000302", CLASS_SERVICE),
    91: FaultInfo("too_many_resets", "P000304", CLASS_SERVICE),
    92: FaultInfo("control_box_defective", "P000330", CLASS_SERVICE),
    93: FaultInfo("control_box_defective", "P000331", CLASS_SERVICE),
    94: FaultInfo("control_box_defective", "P000332", CLASS_SERVICE),
    95: FaultInfo("control_box_not_calibrated", "P000305", CLASS_SERVICE),
    98: FaultInfo("second_cutout_defective", "P000306", CLASS_SERVICE),
    99: FaultInfo("output_stage_lockout", "P000303", CLASS_SERVICE),
}

# Every state a fault enum sensor can report, in a stable order
FAULT_OPTIONS: list[str] = [
    *dict.fromkeys(info.key for info in FAULT_CODES.values()),
    FAULT_OTHER,
]

STORED_FAULT_NAMES = ("F1", "F2", "F3", "F4", "F5")


def fault_key(code: int | None) -> str | None:
    """Return the fault name for a raw code, or None when there is no data."""
    if code is None or code == FAULT_NO_DATA:
        return None
    info = FAULT_CODES.get(code)
    return info.key if info else FAULT_OTHER


def fault_attributes(code: int | None) -> dict[str, str | int | None]:
    """Return the raw code with its P-code and error class, where known."""
    info = FAULT_CODES.get(code) if code is not None else None
    return {
        "code": code,
        "p_code": info.p_code if info else None,
        "fault_class": info.fault_class if info else None,
    }


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
