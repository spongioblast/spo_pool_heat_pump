from __future__ import annotations

import asyncio
import time

from spo_pool_heat_pump.const import apply_runtime_overrides, merge_entry_options, migrate_entry_storage
from spo_pool_heat_pump.drivers.decode import apply_map
from spo_pool_heat_pump.drivers.poll_master import PollMasterDriver
from spo_pool_heat_pump.modbus_rtu import encode_exception, encode_fc01_reply, encode_fc03_reply, parse_frame
from spo_pool_heat_pump.profiles import load_profile


def test_cn13_poll_roundtrip() -> None:
    sent: list[bytes] = []
    driver: PollMasterDriver | None = None

    async def send(frame: bytes) -> None:
        sent.append(frame)
        req = parse_frame(frame)
        assert req is not None
        assert driver is not None
        if req.start == 1011:
            driver.handle_frame(encode_fc03_reply(50, [1, 1, 310]))
            return
        values = [0] * 70
        values[0] = 1
        values[1] = 1
        values[2] = 310
        values[35] = 225  # 2046
        values[63] = 1 << 9  # 2074 bit9
        driver.handle_frame(encode_fc03_reply(50, values))

    profile = load_profile("fairland_pc1004_cn13")
    driver = PollMasterDriver(profile, send)
    asyncio.run(driver.poll_once())
    assert parse_frame(sent[0]).start == 1011
    asyncio.run(driver.poll_once())
    assert driver.state.power is True
    assert driver.state.mode == "heat"
    assert driver.state.faults == ["2074.9"]


def test_cn13_setpoint_fc06_is_28c_not_double_encoded() -> None:
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    driver = PollMasterDriver(load_profile("fairland_pc1004_cn13"), send)
    asyncio.run(driver.set_setpoint(28.0))
    parsed = parse_frame(sent[0])
    assert parsed is not None
    assert parsed.function == 6
    assert parsed.slave == 50
    assert parsed.start == 1013
    assert parsed.values == [280]


def test_ips_pro_setpoint_fc06_is_fairland_temp_once() -> None:
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    driver = PollMasterDriver(load_profile("fairland_ips_pro_coils"), send)
    asyncio.run(driver.set_setpoint(28.0))
    parsed = parse_frame(sent[0])
    assert parsed is not None
    assert parsed.function == 6
    assert parsed.slave == 1
    assert parsed.start == 3
    assert parsed.values == [116]


def test_ips_pro_outputs_from_coil_block() -> None:
    profile = load_profile("fairland_ips_pro_coils")
    state = apply_map(profile, {}, {"coils": [1, 0, 0, 0, 0, 0, 0, 0]})
    assert state.outputs["compressor"] is True
    state_off = apply_map(profile, {}, {"coils": [0, 0, 0, 0, 0, 0, 0, 0]})
    assert state_off.outputs["compressor"] is False

    sent: list[bytes] = []
    driver: PollMasterDriver | None = None

    async def send(frame: bytes) -> None:
        sent.append(frame)
        req = parse_frame(frame)
        assert req is not None and driver is not None
        if req.function == 1:
            driver.handle_frame(encode_fc01_reply(1, [True, False, False, False, False, False, False, False]))
        else:
            driver.handle_frame(encode_fc03_reply(1, [0] * 32))

    driver = PollMasterDriver(profile, send)
    asyncio.run(driver.poll_once())
    asyncio.run(driver.poll_once())
    asyncio.run(driver.poll_once())
    assert driver.state.outputs.get("compressor") is True


def test_poll_slave_override_rewrites_reads() -> None:
    profile = apply_runtime_overrides(load_profile("fairland_pc1004_cn13"), {"poll_slave": 60}, {})
    assert profile["driver"]["poll_slave"] == 60
    assert all(spec["slave"] == 60 for spec in profile["driver"]["reads"])
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)
        req = parse_frame(frame)
        assert req is not None
        driver.handle_frame(encode_fc03_reply(60, [1, 1, 310]))

    driver = PollMasterDriver(profile, send)
    asyncio.run(driver.poll_once())
    assert parse_frame(sent[0]).slave == 60
    asyncio.run(driver.set_setpoint(28.0))
    assert parse_frame(sent[-1]).slave == 60
    assert parse_frame(sent[-1]).start == 1013


def test_poll_slave_override_does_not_mutate_source() -> None:
    original = load_profile("fairland_pc1004_cn13")
    apply_runtime_overrides(original, {"poll_slave": 60}, {})
    assert original["driver"]["poll_slave"] == 50
    assert original["driver"]["reads"][0]["slave"] == 50


def test_poll_slave_override_ignored_on_pc1002() -> None:
    profile = apply_runtime_overrides(load_profile("mida_cosma_pc1002"), {"poll_slave": 60}, {})
    assert profile["driver"]["type"] == "pc1002_bus"
    assert "poll_slave" not in profile["driver"]


def test_merge_entry_options_drops_poll_slave_on_pc1002() -> None:
    data = {"profile": "fairland_pc1004_cn13", "poll_slave": 60}
    options = {"poll_slave": 60, "poll_interval": 10}
    merged = merge_entry_options(data, options, {"profile": "mida_cosma_pc1002", "write_path": "dtu_99"})
    assert "poll_slave" not in merged
    assert "poll_interval" not in merged
    assert merged["profile"] == "mida_cosma_pc1002"


def test_merge_entry_options_resets_slave_when_profile_changes() -> None:
    data = {"profile": "fairland_pc1004_cn13", "poll_slave": 60}
    options = {"profile": "fairland_pc1004_cn13", "poll_slave": 60}
    merged = merge_entry_options(data, options, {"profile": "fairland_ips_pro_coils", "poll_slave": 60})
    assert merged["poll_slave"] == 1
    assert merged["poll_interval"] == 10


def test_migrate_entry_storage_moves_settings_to_options() -> None:
    data, options, changed = migrate_entry_storage(
        {
            "host": "10.0.0.8",
            "port": 8899,
            "profile": "mida_cosma_pc1002",
            "write_path": "dtu_99",
            "name": "Pool",
            "service_menu_writes": False,
        },
        {},
    )
    assert changed is True
    assert data == {"host": "10.0.0.8", "port": 8899}
    assert options["profile"] == "mida_cosma_pc1002"
    assert options["write_path"] == "dtu_99"
    assert options["service_menu_writes"] is False
    assert "name" not in data
    assert "name" not in options


def test_migrate_entry_storage_keeps_existing_options() -> None:
    data, options, changed = migrate_entry_storage(
        {"host": "10.0.0.8", "port": 8899, "profile": "old", "write_path": "dtu_99"},
        {"profile": "mida_cosma_pc1002"},
    )
    assert changed is True
    assert data == {"host": "10.0.0.8", "port": 8899}
    assert options["profile"] == "mida_cosma_pc1002"
    assert options["write_path"] == "dtu_99"


def test_migrate_entry_storage_noop_when_already_split() -> None:
    data, options, changed = migrate_entry_storage(
        {"host": "10.0.0.8", "port": 8899},
        {"profile": "mida_cosma_pc1002"},
    )
    assert changed is False
    assert data == {"host": "10.0.0.8", "port": 8899}
    assert options == {"profile": "mida_cosma_pc1002"}


def test_merge_entry_options_keeps_slave_on_same_profile() -> None:
    data = {"profile": "fairland_pc1004_cn13", "poll_slave": 50}
    options = {}
    merged = merge_entry_options(data, options, {"profile": "fairland_pc1004_cn13", "poll_slave": 60})
    assert merged["poll_slave"] == 60


def test_poll_exception_unblocks() -> None:
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)
        req = parse_frame(frame)
        assert req is not None
        driver.handle_frame(encode_exception(50, 3, 2))

    driver = PollMasterDriver(load_profile("fairland_pc1004_cn13"), send)
    started = time.monotonic()
    asyncio.run(driver.poll_once(wait_s=0.8))
    assert time.monotonic() - started < 0.4
    assert sent


def test_poll_exception_fails_settings_refresh() -> None:
    profile = load_profile("fairland_pc1004_cn13")
    profile["service_menu"] = {"pages": [{"start": 1001, "qty": 1}], "read": {"slave": 50, "timeout_s": 0.8}}
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)
        driver.handle_frame(encode_exception(50, 3, 2))

    driver = PollMasterDriver(profile, send)
    started = time.monotonic()
    assert asyncio.run(driver.refresh_settings()) is False
    assert time.monotonic() - started < 0.4
    assert sent
