"""Tests for the Rixens heater fault code helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.rixens.api import RixensApi
from custom_components.rixens.faults import (
    FAULT_CODES,
    FAULT_OPTIONS,
    active_fault_code,
    fault_key,
    is_fault,
    stored_fault_codes,
)

from .conftest import SAMPLE_XML_1_208, make_rixens_data


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "no_fault"),
        (10, "overvoltage"),
        (55, "flame_cutout"),
        (94, "control_box_defective"),
        (123, "other"),
        (255, None),
        (None, None),
    ],
)
def test_fault_key(code, expected):
    assert fault_key(code) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [(0, False), (255, False), (None, False), (48, True), (123, True)],
)
def test_is_fault(code, expected):
    assert is_fault(code) is expected


def test_options_cover_every_code_once():
    assert set(FAULT_OPTIONS) == {*FAULT_CODES.values(), "other"}
    assert len(FAULT_OPTIONS) == len(set(FAULT_OPTIONS))


def test_stored_faults_in_order_and_skip_missing():
    data = make_rixens_data(faults={"AF": 0, "F1": 52, "F3": 11})
    assert active_fault_code(data) == 0
    assert stored_fault_codes(data) == [52, 11]


def test_manufacturer_sample_has_no_fault():
    """The 1.208 sample (heater off, no battery) reports AF=255: no data."""
    data = RixensApi("x", MagicMock())._parse_status(SAMPLE_XML_1_208)
    assert active_fault_code(data) == 255
    assert not is_fault(active_fault_code(data))
    assert stored_fault_codes(data) == [0, 0, 0, 0, 0]
