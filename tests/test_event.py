"""Tests for the Rixens event platform."""

from __future__ import annotations

from unittest.mock import patch

from custom_components.rixens.event import (
    EVENT_FAULT_DETECTED,
    RixensHeaterFaultEvent,
)

from .conftest import make_rixens_data


def _update(entity: RixensHeaterFaultEvent, mock_coordinator, af: int | None) -> None:
    faults = {} if af is None else {"AF": af}
    mock_coordinator.data = make_rixens_data(faults=faults)
    entity._handle_coordinator_update()


class TestHeaterFaultEvent:
    """Tests for the heater fault event entity."""

    def _make(self, mock_coordinator) -> RixensHeaterFaultEvent:
        entity = RixensHeaterFaultEvent(mock_coordinator)
        entity.async_write_ha_state = lambda: None  # not added to hass
        return entity

    def test_unique_id_and_event_types(self, mock_coordinator):
        entity = self._make(mock_coordinator)
        assert entity._attr_unique_id == "test_entry_id_heater_fault_event"
        assert entity.event_types == [EVENT_FAULT_DETECTED]

    def test_fires_when_fault_appears(self, mock_coordinator):
        entity = self._make(mock_coordinator)
        with patch.object(entity, "_trigger_event") as trigger:
            _update(entity, mock_coordinator, 48)
        trigger.assert_called_once_with(
            EVENT_FAULT_DETECTED,
            {
                "code": 48,
                "p_code": "P000200",
                "fault_class": "fuel_supply_or_pump",
                "fault": "metering_pump_open",
            },
        )

    def test_does_not_refire_for_same_fault(self, mock_coordinator):
        entity = self._make(mock_coordinator)
        with patch.object(entity, "_trigger_event") as trigger:
            _update(entity, mock_coordinator, 48)
            _update(entity, mock_coordinator, 48)
        assert trigger.call_count == 1

    def test_fires_again_after_clear(self, mock_coordinator):
        entity = self._make(mock_coordinator)
        with patch.object(entity, "_trigger_event") as trigger:
            _update(entity, mock_coordinator, 48)
            _update(entity, mock_coordinator, 0)
            _update(entity, mock_coordinator, 48)
        assert trigger.call_count == 2

    def test_fires_when_fault_changes(self, mock_coordinator):
        entity = self._make(mock_coordinator)
        with patch.object(entity, "_trigger_event") as trigger:
            _update(entity, mock_coordinator, 48)
            _update(entity, mock_coordinator, 52)
        assert [c.args[1]["code"] for c in trigger.call_args_list] == [48, 52]

    def test_ignores_no_fault_and_no_data(self, mock_coordinator):
        entity = self._make(mock_coordinator)
        with patch.object(entity, "_trigger_event") as trigger:
            for af in (0, 255, None):
                _update(entity, mock_coordinator, af)
        trigger.assert_not_called()

    def test_fault_active_at_startup_does_not_fire(self, mock_coordinator):
        mock_coordinator.data = make_rixens_data(faults={"AF": 48})
        entity = self._make(mock_coordinator)
        with patch.object(entity, "_trigger_event") as trigger:
            _update(entity, mock_coordinator, 48)
        trigger.assert_not_called()

    def test_no_coordinator_data(self, mock_coordinator):
        mock_coordinator.data = None
        entity = self._make(mock_coordinator)
        with patch.object(entity, "_trigger_event") as trigger:
            entity._handle_coordinator_update()
        trigger.assert_not_called()
