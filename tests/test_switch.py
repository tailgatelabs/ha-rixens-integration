"""Tests for the Rixens switch platform."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.rixens.api import Command
from custom_components.rixens.optimistic import OPTIMISTIC_TIMEOUT
from custom_components.rixens.switch import (
    SWITCH_DESCRIPTIONS,
    RixensSwitch,
    RixensSwitchEntityDescription,
)

from .conftest import make_rixens_data, sent_commands


class TestSwitchDescriptions:
    """Tests for switch entity descriptions."""

    def test_all_descriptions_have_required_fns(self):
        for desc in SWITCH_DESCRIPTIONS:
            assert callable(desc.value_fn)
            assert isinstance(desc.command, Command)

    def test_hot_water_keeps_continuous_heat_key(self):
        """The hot water switch keeps its original key so unique_id is stable."""
        desc = next(d for d in SWITCH_DESCRIPTIONS if d.translation_key == "hot_water")
        assert desc.key == "continuous_heat"
        assert desc.command == Command.HOT_WATER

    def test_description_keys_unique(self):
        keys = [d.key for d in SWITCH_DESCRIPTIONS]
        assert len(keys) == len(set(keys))


class TestSwitchEntity:
    """Tests for the RixensSwitch entity class."""

    def _make_switch(self, mock_coordinator, key: str = "furnace"):
        desc = next(d for d in SWITCH_DESCRIPTIONS if d.key == key)
        return RixensSwitch(mock_coordinator, desc)

    def test_unique_id(self, mock_coordinator):
        switch = self._make_switch(mock_coordinator)
        assert switch._attr_unique_id == "test_entry_id_furnace"

    # --- Furnace ---

    def test_furnace_on(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(furnace_src=2)
        switch = self._make_switch(mock_coordinator, "furnace")
        assert switch.is_on is True

    def test_furnace_off(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(furnace_src=0)
        switch = self._make_switch(mock_coordinator, "furnace")
        assert switch.is_on is False

    async def test_furnace_turn_on(self, mock_coordinator):
        switch = self._make_switch(mock_coordinator, "furnace")
        await switch.async_turn_on()
        assert sent_commands(mock_coordinator.api) == [(Command.FURNACE, True)]
        mock_coordinator.async_refresh_after_command.assert_called_once()
        # Optimistic: shown on immediately, before the device confirms it
        assert switch.is_on is True

    async def test_optimistic_state_cleared_when_confirmed(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(furnace_src=0)
        switch = self._make_switch(mock_coordinator, "furnace")
        await switch.async_turn_on()
        # Stale poll still shows off: keep the commanded value
        assert switch.is_on is True
        # Device confirms
        mock_coordinator.data = make_rixens_data(furnace_src=2)
        assert switch.is_on is True
        # Later device-side change is no longer masked
        mock_coordinator.data = make_rixens_data(furnace_src=0)
        assert switch.is_on is False

    async def test_optimistic_state_expires(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(furnace_src=0)
        switch = self._make_switch(mock_coordinator, "furnace")
        await switch.async_turn_on()
        with patch("custom_components.rixens.optimistic.time.monotonic") as mono:
            mono.return_value = time.monotonic() + OPTIMISTIC_TIMEOUT + 1
            assert switch.is_on is False

    async def test_furnace_turn_off(self, mock_coordinator):
        switch = self._make_switch(mock_coordinator, "furnace")
        await switch.async_turn_off()
        assert sent_commands(mock_coordinator.api) == [(Command.FURNACE, False)]

    # --- Floor heat ---

    def test_floor_heat_on(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(floor_src=2)
        switch = self._make_switch(mock_coordinator, "floor_heat")
        assert switch.is_on is True

    def test_floor_heat_off(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(floor_src=0)
        switch = self._make_switch(mock_coordinator, "floor_heat")
        assert switch.is_on is False

    async def test_floor_heat_turn_on(self, mock_coordinator):
        switch = self._make_switch(mock_coordinator, "floor_heat")
        await switch.async_turn_on()
        assert sent_commands(mock_coordinator.api) == [(Command.HEATED_FLOORS, True)]

    async def test_floor_heat_turn_off(self, mock_coordinator):
        switch = self._make_switch(mock_coordinator, "floor_heat")
        await switch.async_turn_off()
        assert sent_commands(mock_coordinator.api) == [(Command.HEATED_FLOORS, False)]

    # --- Electric heat ---

    def test_electric_heat_on(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(electric_src=1)
        switch = self._make_switch(mock_coordinator, "electric_heat")
        assert switch.is_on is True

    def test_electric_heat_off(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(electric_src=0)
        switch = self._make_switch(mock_coordinator, "electric_heat")
        assert switch.is_on is False

    async def test_electric_heat_turn_on(self, mock_coordinator):
        switch = self._make_switch(mock_coordinator, "electric_heat")
        await switch.async_turn_on()
        assert sent_commands(mock_coordinator.api) == [(Command.ELECTRIC_HEAT, True)]

    async def test_electric_heat_turn_off(self, mock_coordinator):
        switch = self._make_switch(mock_coordinator, "electric_heat")
        await switch.async_turn_off()
        assert sent_commands(mock_coordinator.api) == [(Command.ELECTRIC_HEAT, False)]

    # --- Continuous heat ---

    def test_continuous_heat_on(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(cnst_heat=2)
        switch = self._make_switch(mock_coordinator, "continuous_heat")
        assert switch.is_on is True

    def test_continuous_heat_off(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(cnst_heat=0)
        switch = self._make_switch(mock_coordinator, "continuous_heat")
        assert switch.is_on is False

    async def test_continuous_heat_turn_on(self, mock_coordinator):
        switch = self._make_switch(mock_coordinator, "continuous_heat")
        await switch.async_turn_on()
        assert sent_commands(mock_coordinator.api) == [(Command.HOT_WATER, True)]

    async def test_continuous_heat_turn_off(self, mock_coordinator):
        switch = self._make_switch(mock_coordinator, "continuous_heat")
        await switch.async_turn_off()
        assert sent_commands(mock_coordinator.api) == [(Command.HOT_WATER, False)]

    # --- No data ---

    def test_is_on_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        switch = self._make_switch(mock_coordinator, "furnace")
        assert switch.is_on is None

    def test_all_switches_instantiate(self, mock_coordinator):
        """Verify all switch descriptions can create entities."""
        for desc in SWITCH_DESCRIPTIONS:
            switch = RixensSwitch(mock_coordinator, desc)
            assert switch.is_on is not None or mock_coordinator.data is None
