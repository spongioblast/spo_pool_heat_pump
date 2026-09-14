"""Home Assistant integration tests. Skip the suite if HA cannot import."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ha = pytest.importorskip("homeassistant")

from homeassistant.const import CONF_HOST  # noqa: E402
from homeassistant.exceptions import HomeAssistantError  # noqa: E402

from homeassistant.components.climate import ClimateEntityFeature, HVACAction, HVACMode  # noqa: E402

from spo_pool_heat_pump.climate import PoolHeatPumpClimate  # noqa: E402
from spo_pool_heat_pump.config_flow import PoolHeatPumpConfigFlow  # noqa: E402
from spo_pool_heat_pump.const import CONF_PORT, STALE_SECONDS  # noqa: E402
from spo_pool_heat_pump.coordinator import PoolHeatPumpCoordinator  # noqa: E402
from spo_pool_heat_pump.drivers.base import HeatPumpState  # noqa: E402
from spo_pool_heat_pump.drivers.pc1002_bus import Pc1002BusDriver  # noqa: E402
from spo_pool_heat_pump.modbus_rtu import encode_fc03, parse_frame  # noqa: E402
from spo_pool_heat_pump.profiles import load_profile  # noqa: E402


def test_stale_seconds_covers_board_pause() -> None:
    assert STALE_SECONDS == 15.0


def test_config_flow_mocked_detect() -> None:
    async def run() -> None:
        flow = PoolHeatPumpConfigFlow()
        flow.hass = MagicMock()

        async def run_job(func, *args):
            return func(*args)

        flow.hass.async_add_executor_job = run_job
        result = await flow.async_step_user(None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"
        with (
            patch("spo_pool_heat_pump.config_flow.TcpRtuClient"),
            patch(
                "spo_pool_heat_pump.config_flow.detect_profile",
                AsyncMock(return_value=("mida_cosma_pc1002", {"fw_display": 713})),
            ),
        ):
            result = await flow.async_step_user({CONF_HOST: "10.0.0.8", CONF_PORT: 8899})
        assert result["type"] == "form"
        assert result["step_id"] == "profile"
        assert flow._suggested == "mida_cosma_pc1002"
        assert "MIDA Cosma" in result["description_placeholders"]["detect_note"]
        assert "713" in result["description_placeholders"]["detect_note"]

    asyncio.run(run())


def test_coordinator_stale_marks_unavailable() -> None:
    async def run() -> None:
        hass = MagicMock()
        hass.loop = asyncio.get_running_loop()
        entry = MagicMock()
        entry.data = {"host": "10.0.0.8", "port": 8899, "profile": "mida_cosma_pc1002"}
        entry.options = {}
        entry.unique_id = "uid"
        entry.title = "Pump"
        entry.entry_id = "e1"
        coord = PoolHeatPumpCoordinator(hass, entry, MagicMock())
        coord.async_set_updated_data = lambda state: setattr(coord, "data", state)
        errors: list[Exception] = []

        def _err(exc: Exception) -> None:
            errors.append(exc)
            coord.last_update_success = False

        coord.async_set_update_error = _err
        state = HeatPumpState(available=True, serial="B99")
        with patch("spo_pool_heat_pump.coordinator.STALE_SECONDS", 0.05):
            coord._push(state)
            assert coord.state.available is True
            await asyncio.sleep(0.12)
        assert coord.state.available is False
        assert errors

    asyncio.run(run())


def test_coordinator_stale_waits_out_pending_writes() -> None:
    async def run() -> None:
        hass = MagicMock()
        hass.loop = asyncio.get_running_loop()
        entry = MagicMock()
        entry.data = {"host": "10.0.0.8", "port": 8899, "profile": "mida_cosma_pc1002"}
        entry.options = {}
        entry.unique_id = "uid"
        entry.title = "Pump"
        entry.entry_id = "e1"
        coord = PoolHeatPumpCoordinator(hass, entry, MagicMock())
        coord.async_set_updated_data = lambda state: setattr(coord, "data", state)
        errors: list[Exception] = []
        coord.async_set_update_error = errors.append
        state = HeatPumpState(available=True, serial="B99", mode="heat")
        coord.driver.pending.mark("mode", 2)
        with patch("spo_pool_heat_pump.coordinator.STALE_SECONDS", 0.05):
            coord._push(state)
            await asyncio.sleep(0.12)
        assert coord.state.available is True
        assert errors == []
        coord.driver.pending.discard("mode")
        with patch("spo_pool_heat_pump.coordinator.STALE_SECONDS", 0.05):
            coord._push(state)
            await asyncio.sleep(0.12)
        assert coord.state.available is False
        assert errors

    asyncio.run(run())


def test_coordinator_stale_kicks_transport_reconnect() -> None:
    """A silent bus reconnects the socket every window, pending write or not."""

    async def run() -> None:
        hass = MagicMock()
        hass.loop = asyncio.get_running_loop()
        entry = MagicMock()
        entry.data = {"host": "10.0.0.8", "port": 8899, "profile": "mida_cosma_pc1002"}
        entry.options = {}
        entry.unique_id = "uid"
        entry.title = "Pump"
        entry.entry_id = "e1"
        client = MagicMock()
        client.reconnect = AsyncMock()
        coord = PoolHeatPumpCoordinator(hass, entry, client)
        coord.async_set_updated_data = lambda state: setattr(coord, "data", state)
        coord.async_set_update_error = lambda exc: None
        state = HeatPumpState(available=True, serial="B99", mode="heat")
        coord.driver.pending.mark("mode", 2)
        with patch("spo_pool_heat_pump.coordinator.STALE_SECONDS", 0.05):
            coord._push(state)
            await asyncio.sleep(0.07)
            assert client.reconnect.await_count == 1
            assert coord.state.available is True
            await asyncio.sleep(0.05)
            assert client.reconnect.await_count == 2
            coord._push(state)  # a frame arrived: timer restarts, no extra kick
            await asyncio.sleep(0.02)
            assert client.reconnect.await_count == 2
        coord._stale_handle.cancel()

    asyncio.run(run())


def test_coordinator_stale_does_not_reconnect_while_frames_arrive() -> None:
    """Polls / page pushes keep the socket; only a dead line redials."""

    async def run() -> None:
        hass = MagicMock()
        hass.loop = asyncio.get_running_loop()
        entry = MagicMock()
        entry.data = {"host": "10.0.0.8", "port": 8899, "profile": "mida_cosma_pc1002"}
        entry.options = {}
        entry.unique_id = "uid"
        entry.title = "Pump"
        entry.entry_id = "e1"
        client = MagicMock()
        client.reconnect = AsyncMock()
        client.send = AsyncMock()
        coord = PoolHeatPumpCoordinator(hass, entry, client)
        coord.async_set_updated_data = lambda state: setattr(coord, "data", state)
        coord.async_set_update_error = lambda exc: None
        state = HeatPumpState(available=True, serial="B99")
        poll = encode_fc03(2, 3001, 30)
        with patch("spo_pool_heat_pump.coordinator.STALE_SECONDS", 0.05):
            coord._push(state)
            for _ in range(4):
                await coord.async_on_frame(poll)
                await asyncio.sleep(0.03)
            assert client.reconnect.await_count == 0
            assert coord.state.available is False
            await asyncio.sleep(0.06)
            assert client.reconnect.await_count == 1
        coord._stale_handle.cancel()

    asyncio.run(run())


def test_startup_settings_refresh_runs_on_every_write_path() -> None:
    # Slave 2 needs the one-shot read too: the board pushes pages to the panels
    # only on change, so 1091 would otherwise stay unseeded after a restart.
    async def run() -> None:
        hass = MagicMock()
        hass.loop = asyncio.get_running_loop()
        entry = MagicMock()
        entry.data = {"host": "10.0.0.8", "port": 8899, "profile": "mida_cosma_pc1002"}
        entry.options = {}
        entry.unique_id = "uid"
        entry.title = "Pump"
        entry.entry_id = "e1"
        coord = PoolHeatPumpCoordinator(hass, entry, MagicMock())
        coord.driver.refresh_settings = AsyncMock()
        assert coord.driver.write_path == "slave2"
        await coord._async_refresh_settings_once()
        coord.driver.refresh_settings.assert_awaited_once()
        coord.driver.write_path = "dtu_99"
        coord.driver.refresh_settings.reset_mock()
        await coord._async_refresh_settings_once()
        coord.driver.refresh_settings.assert_awaited_once()

    asyncio.run(run())


def test_dump_only_climate_has_no_write_features() -> None:
    coord = MagicMock()
    coord.profile = load_profile("unknown_dump_only")
    coord.unique_id = "uid"
    coord.state = HeatPumpState(available=True, values={"dump_only": True})
    coord.last_update_success = True
    coord.device_name = "Pump"
    entity = PoolHeatPumpClimate(coord)
    assert entity.hvac_modes == [HVACMode.OFF]
    assert entity.supported_features == ClimateEntityFeature(0)
    assert entity.extra_state_attributes.get("dump_only") is True
    assert entity.extra_state_attributes.get("activity") == "Dump only"
    with pytest.raises(HomeAssistantError):
        asyncio.run(entity.async_turn_on())
    with pytest.raises(HomeAssistantError):
        asyncio.run(entity.async_set_hvac_mode(HVACMode.OFF))


def test_climate_preheating_when_pump_warming() -> None:
    coord = MagicMock()
    coord.profile = load_profile("mida_cosma_pc1002")
    coord.unique_id = "uid"
    coord.state = HeatPumpState(
        available=True,
        power=True,
        mode="heat",
        t_inlet=24.0,
        setpoint=28.0,
        outputs={"water_pump": True, "compressor": False},
    )
    coord.last_update_success = True
    coord.device_name = "Pump"
    entity = PoolHeatPumpClimate(coord)
    assert entity.hvac_action == HVACAction.PREHEATING


def test_climate_turn_on_writes_power_only() -> None:
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    driver = Pc1002BusDriver(load_profile("mida_cosma_pc1002"), send, "dtu_99")  # asserts raw frames
    coord = MagicMock()
    coord.driver = driver
    coord.profile = driver.profile
    coord.unique_id = "uid"
    coord.state = HeatPumpState(available=True, power=False)
    coord.last_update_success = True
    coord.device_name = "Pump"
    entity = PoolHeatPumpClimate(coord)
    asyncio.run(entity.async_turn_on())
    starts = [parse_frame(f).start for f in sent]
    assert starts == [1011, 1014]
    assert parse_frame(sent[0]).values == [1]


def test_on_frame_does_not_block_on_flag_reread() -> None:
    """The flag re-read only exists off the slave-2 path (as the second panel we
    are pushed every page); exercise it on the DTU path."""
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    async def run() -> None:
        hass = MagicMock()
        hass.loop = asyncio.get_running_loop()
        entry = MagicMock()
        entry.data = {"host": "10.0.0.8", "port": 8899, "profile": "mida_cosma_pc1002"}
        entry.options = {"write_path": "dtu_99"}
        entry.unique_id = "uid"
        entry.title = "Pump"
        entry.entry_id = "e1"
        client = MagicMock()
        client.send = send
        coord = PoolHeatPumpCoordinator(hass, entry, client)
        coord.driver._last_3011 = 0
        from spo_pool_heat_pump.modbus_rtu import encode_fc06

        await asyncio.wait_for(coord.async_on_frame(encode_fc06(1, 3011, 4)), 0.2)
        assert coord.driver._pending_flag_pages is None
        await asyncio.sleep(0.05)
        assert sent
        parsed = parse_frame(sent[0])
        assert parsed is not None
        assert parsed.start == 1001

    asyncio.run(run())


def test_flag_refresh_cancelled_on_stop() -> None:
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)
        await asyncio.sleep(10)

    async def run() -> None:
        hass = MagicMock()
        hass.loop = asyncio.get_running_loop()
        entry = MagicMock()
        entry.data = {"host": "10.0.0.8", "port": 8899, "profile": "mida_cosma_pc1002"}
        entry.options = {"write_path": "dtu_99"}
        entry.unique_id = "uid"
        entry.title = "Pump"
        entry.entry_id = "e1"
        client = MagicMock()
        client.send = send
        client.stop = AsyncMock()
        coord = PoolHeatPumpCoordinator(hass, entry, client)
        coord.driver._last_3011 = 0
        from spo_pool_heat_pump.modbus_rtu import encode_fc06

        await coord.async_on_frame(encode_fc06(1, 3011, 4))
        await asyncio.sleep(0.05)
        assert sent
        count = len(sent)
        await coord.async_stop()
        await asyncio.sleep(0.05)
        assert len(sent) == count
        assert not coord._flag_tasks

    asyncio.run(run())
