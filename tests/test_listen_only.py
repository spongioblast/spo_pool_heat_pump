from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from spo_pool_heat_pump.const import merge_entry_options
from spo_pool_heat_pump.drivers.base import HeatPumpState
from spo_pool_heat_pump.drivers.listen_only import DumpOnlyWriteError, ListenOnlyDriver
from spo_pool_heat_pump.drivers import build_driver
from spo_pool_heat_pump.profiles import load_profile


def test_build_listen_only_driver() -> None:
    profile = load_profile("unknown_dump_only")
    driver = build_driver(profile, lambda _f: None, "dtu_99")
    assert isinstance(driver, ListenOnlyDriver)
    asyncio.run(driver.async_start())
    assert driver.state.available is True
    assert driver.state.values.get("dump_only") is True
    assert driver.state.card_status() == "Dump only"


def test_listen_only_refuses_writes() -> None:
    driver = ListenOnlyDriver(load_profile("unknown_dump_only"), lambda _f: None)
    with pytest.raises(DumpOnlyWriteError):
        asyncio.run(driver.set_power(True))
    with pytest.raises(DumpOnlyWriteError):
        asyncio.run(driver.set_setpoint(28.0))
    with pytest.raises(DumpOnlyWriteError):
        asyncio.run(driver.write_register("power", 1))


def test_listen_only_handle_frame_does_not_reply() -> None:
    driver = ListenOnlyDriver(load_profile("unknown_dump_only"), lambda _f: None)
    asyncio.run(driver.async_start())
    assert driver.handle_frame(b"\x00\x10") is None


def test_merge_entry_options_drops_write_path_on_dump_only() -> None:
    data = {"profile": "mida_cosma_pc1002", "write_path": "dtu_99"}
    merged = merge_entry_options(data, {"write_path": "dtu_99"}, {"profile": "unknown_dump_only"})
    assert merged["profile"] == "unknown_dump_only"
    assert "write_path" not in merged
    assert "poll_slave" not in merged


def test_dump_only_status_on_state() -> None:
    state = HeatPumpState(available=True, values={"dump_only": True})
    assert state.card_status() == "Dump only"


def test_listen_only_set_available() -> None:
    states: list[HeatPumpState] = []
    driver = ListenOnlyDriver(load_profile("unknown_dump_only"), lambda _f: None, states.append)
    asyncio.run(driver.async_start())
    assert driver.state.available is True
    driver.set_available(False)
    assert driver.state.available is False
    assert driver.state.values.get("dump_only") is True
    driver.set_available(True)
    assert driver.state.available is True
    assert [s.available for s in states] == [True, False, True]


def test_listen_only_coordinator_follows_tcp() -> None:
    pytest.importorskip("homeassistant")
    from spo_pool_heat_pump.coordinator import PoolHeatPumpCoordinator

    async def run() -> None:
        hass = MagicMock()
        hass.loop = asyncio.get_running_loop()
        entry = MagicMock()
        entry.data = {"host": "10.0.0.8", "port": 8899}
        entry.options = {"profile": "unknown_dump_only"}
        entry.unique_id = "uid"
        entry.title = "Pump"
        entry.entry_id = "e1"
        client = MagicMock()
        client.connected = False
        client.start = AsyncMock()
        client.send = MagicMock()
        coord = PoolHeatPumpCoordinator(hass, entry, client)
        coord.async_set_updated_data = lambda state: setattr(coord, "data", state)
        await coord.async_start()
        assert coord.driver.state.available is False
        client.connected = True
        coord._on_tcp_connection(True)
        assert coord.driver.state.available is True
        coord._on_tcp_connection(False)
        assert coord.driver.state.available is False

    asyncio.run(run())
