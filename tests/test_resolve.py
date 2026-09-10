"""Coordinator resolve / service targeting. Skip if HA cannot import."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

ha = pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError  # noqa: E402

from spo_pool_heat_pump.const import DOMAIN  # noqa: E402
from spo_pool_heat_pump.coordinator import PoolHeatPumpCoordinator  # noqa: E402
from spo_pool_heat_pump.services import _coordinator  # noqa: E402


def _entry(entry_id: str, unique_id: str, *, live: bool = True) -> SimpleNamespace:
    entry = SimpleNamespace(entry_id=entry_id)
    if live:
        entry.runtime_data = SimpleNamespace(unique_id=unique_id)
    return entry


def _hass(entries: list) -> MagicMock:
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = entries
    return hass


def test_unknown_entity_id_does_not_fall_through() -> None:
    live = _entry("e1", "uid-1")
    hass = _hass([live])
    entity_reg = MagicMock()
    entity_reg.async_get.return_value = None
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=entity_reg):
        assert PoolHeatPumpCoordinator.resolve(hass, entity_id="climate.gone") is None
        assert PoolHeatPumpCoordinator._matches(hass, entity_id="climate.gone") == []


def test_no_ids_one_live_entry_resolves() -> None:
    live = _entry("e1", "uid-1")
    hass = _hass([live])
    assert PoolHeatPumpCoordinator.resolve(hass) is live.runtime_data


def test_dead_entry_skipped() -> None:
    dead = SimpleNamespace(entry_id="e0")
    live = _entry("e1", "uid-1")
    hass = _hass([dead, live])
    assert PoolHeatPumpCoordinator.resolve(hass) is live.runtime_data


def test_device_id_two_entries_multiple() -> None:
    first = _entry("e1", "same-uid")
    second = _entry("e2", "same-uid")
    hass = _hass([first, second])
    device = SimpleNamespace(identifiers={(DOMAIN, "same-uid")})
    device_reg = MagicMock()
    device_reg.async_get.return_value = device
    with patch("homeassistant.helpers.device_registry.async_get", return_value=device_reg):
        found = PoolHeatPumpCoordinator._matches(hass, device_id="dev-1")
        assert len(found) == 2
        call = SimpleNamespace(data={"device_id": "dev-1"})
        with pytest.raises(HomeAssistantError) as err:
            _coordinator(hass, call)
        assert err.value.translation_key == "multiple_entries"
