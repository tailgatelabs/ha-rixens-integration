"""Tests for the Rixens entity icon translations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

COMPONENT = Path(__file__).parent.parent / "custom_components" / "rixens"
ICONS = json.loads((COMPONENT / "icons.json").read_text())["entity"]
STRINGS = json.loads((COMPONENT / "strings.json").read_text())["entity"]


@pytest.mark.parametrize(
    ("platform", "key"),
    [(platform, key) for platform, keys in ICONS.items() for key in keys],
)
def test_icon_matches_translation(platform, key):
    """Every icon entry targets a real translation key and its known states."""
    assert key in STRINGS[platform]
    icon = ICONS[platform][key]
    assert icon["default"].startswith("mdi:")
    known_states = STRINGS[platform][key].get("state")
    for state, state_icon in icon.get("state", {}).items():
        assert state_icon.startswith("mdi:")
        if known_states is not None:
            assert state in known_states
