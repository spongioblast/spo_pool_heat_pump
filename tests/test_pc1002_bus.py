from __future__ import annotations

from pathlib import Path

import pytest
from dump_log import read_dump
from spo_pool_heat_pump.drivers.decode import apply_map
from spo_pool_heat_pump.drivers.pc1002_bus import Pc1002BusDriver
from spo_pool_heat_pump.modbus_rtu import crc_ok, encode_fc16, parse_frame
from spo_pool_heat_pump.profiles import load_profile

from conftest import DUMPS, requires_dumps

pytestmark = requires_dumps

DUMP = DUMPS / "20260906_104432.log"
DUMP_LOGS = [
    DUMPS / "20260904_091719.log",
    DUMPS / "20260905_132144.log",
    DUMPS / "20260906_104432.log",
]


def first_broadcast(path: Path = DUMP):
    for pkt in read_dump(path):
        if len(pkt.data) >= 9 and pkt.data[0] == 0 and pkt.data[1] == 0x10:
            if crc_ok(pkt.data):
                return pkt.data
    raise AssertionError(f"no 2001 frame in {path.name}")


@pytest.mark.parametrize("dump", DUMP_LOGS, ids=lambda p: p.name)
def test_dump_broadcast_decodes(dump: Path) -> None:
    frame = first_broadcast(dump)
    parsed = parse_frame(frame)
    assert parsed is not None
    assert parsed.start == 2001
    assert parsed.qty == 90
    profile = load_profile("mida_cosma_pc1002")
    regs = {2001 + i: v for i, v in enumerate(parsed.values)}
    state = apply_map(profile, regs)
    assert state.serial
    assert state.t_inlet is not None
    assert 10 < state.t_inlet < 40
    assert state.t_outlet is not None
    assert state.t_ambient is not None
    if dump.name == "20260906_104432.log":
        assert state.serial.startswith("B992604135232")


async def _send(_frame: bytes) -> None:
    return None


def test_driver_handle_broadcast() -> None:
    driver = Pc1002BusDriver(load_profile("mida_cosma_pc1002"), _send, "dtu_99")
    driver.handle_frame(first_broadcast())
    state = driver.state
    assert state.available
    assert state.serial


def test_find_frames_on_dump_broadcast() -> None:
    from spo_pool_heat_pump.modbus_rtu import find_frames

    frame = first_broadcast()
    found = find_frames(b"\xde\xad" + frame + b"\x00")
    assert any(f.start == 2001 and f.qty == 90 for f in found)


def test_write_power_on_frame(monkeypatch) -> None:
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    driver = Pc1002BusDriver(load_profile("mida_cosma_pc1002"), send, "dtu_99")
    import asyncio

    asyncio.run(driver.set_power(True))
    from spo_pool_heat_pump.modbus_rtu import bytes_to_hex

    assert bytes_to_hex(sent[0]) == "63 10 03 F3 00 01 02 00 01 F1 31"


def test_hayward_power_also_writes_1014() -> None:
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    driver = Pc1002BusDriver(load_profile("hayward_pc1002"), send, "dtu_99")
    import asyncio

    asyncio.run(driver.set_power(True))
    assert len(sent) == 2
    from spo_pool_heat_pump.modbus_rtu import parse_frame

    assert parse_frame(sent[1]).start == 1014


def test_timer_extras_survive_broadcast() -> None:
    import asyncio

    from spo_pool_heat_pump.modbus_rtu import encode_fc03, encode_fc03_reply, encode_fc16

    driver = Pc1002BusDriver(load_profile("mida_cosma_pc1002"), _send, "dtu_99")
    driver.handle_frame(first_broadcast())
    assert driver.state.available
    asyncio.run(driver.write_register("timer1_on", 1))
    assert driver.state.extras.get("timer1_on") is True
    driver.handle_frame(first_broadcast())
    assert driver.state.extras.get("timer1_on") is True

    driver.handle_frame(encode_fc16(99, 1150, [7]))
    assert driver.state.extras.get("timer1_on_h") == 7
    driver.handle_frame(first_broadcast())
    assert driver.state.extras.get("timer1_on_h") == 7

    driver.handle_frame(encode_fc03(1, 1091, 90))
    values = [0] * 90
    values[45] = 310  # 1136
    driver.handle_frame(encode_fc03_reply(1, values))
    assert driver.state.setpoint_heat == 31.0


def test_set_mode_writes_only_1012() -> None:
    """The board swaps the working setpoint itself on a mode change; 1013 is panel-owned."""
    import asyncio

    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    driver = Pc1002BusDriver(load_profile("mida_cosma_pc1002"), send, "dtu_99")
    driver.handle_frame(first_broadcast())
    driver.settings.put(1136, 310)
    driver._publish(driver.state.raw)
    sent.clear()
    asyncio.run(driver.set_mode("heat"))
    frames = [parse_frame(f) for f in sent]
    assert [(f.start, list(f.values)) for f in frames] == [(1012, [1])]


def test_selected_mode_comes_from_page_1001_not_broadcast_2012() -> None:
    """Broadcast 2012 is the running direction (never auto); page word 1012 is the selection."""
    driver = Pc1002BusDriver(load_profile("mida_cosma_pc1002"), _send, "dtu_99")
    driver.handle_frame(first_broadcast())  # 2012 = 1 (heat) in the fixture
    assert driver.state.mode == "heat"
    assert driver.state.values.get("active_mode") == "heat"
    page = [0] * 90
    page[11] = 2  # 1012 = auto selected on the panel
    driver.handle_frame(encode_fc16(1, 1001, page))
    assert driver.state.mode == "auto"
    assert driver.state.values.get("active_mode") == "heat"
    assert driver.state.auto_is_heating() is True


def test_mode_write_is_not_confirmed_by_our_own_cache() -> None:
    """Confirmation must come from the board pushing page 1001, not from settings.put."""
    import asyncio

    driver = Pc1002BusDriver(load_profile("mida_cosma_pc1002"), _send, "dtu_99")
    driver.handle_frame(first_broadcast())
    page = [0] * 90
    page[11] = 1
    driver.handle_frame(encode_fc16(1, 1001, page))
    asyncio.run(driver.set_mode("auto"))
    assert driver.state.mode == "auto"
    assert "mode" in driver.state.pending
    assert driver.settings.regs.get(1012) == 1  # cache still says what the board said
    driver.handle_frame(
        first_broadcast()
    )  # 2012 stays 1: does not confirm, does not revert
    assert driver.state.mode == "auto"
    assert "mode" in driver.state.pending
    page[11] = 2
    driver.handle_frame(encode_fc16(1, 1001, page))  # board pushes the adopted page
    assert driver.state.mode == "auto"
    assert driver.state.pending == []


def test_3011_flags_queue_page_reread() -> None:
    driver = Pc1002BusDriver(load_profile("mida_cosma_pc1002"), _send, "dtu_99")
    driver._last_3011 = 0
    driver.settings.put(3011, 4)
    driver._maybe_queue_flag_reread()
    assert driver._pending_flag_pages == [1001]
    driver._pending_flag_pages = None
    driver.settings.put(3011, 32768)
    driver._maybe_queue_flag_reread()
    assert driver._pending_flag_pages == "all"


def test_set_setpoint_writes_the_per_mode_word_only() -> None:
    """Heat mode: the wired display changes 1136 (flag 0x0040) and nothing else."""
    import asyncio

    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    driver = Pc1002BusDriver(load_profile("mida_cosma_pc1002"), send, "dtu_99")
    driver.handle_frame(first_broadcast())  # heat
    asyncio.run(driver.set_setpoint(30.5))
    frames = [parse_frame(f) for f in sent]
    assert [(f.start, list(f.values)) for f in frames] == [(1136, [305])]
    # Optimistic on the working setpoint, confirmed by broadcast 2013.
    assert driver.state.setpoint == 30.5
    assert "setpoint" in driver.state.pending
    regs = dict(driver.state.raw)
    regs[2013] = 305
    driver._publish(regs)
    assert driver.state.setpoint == 30.5
    assert "setpoint" not in driver.state.pending


def test_set_setpoint_after_mode_cool_writes_cool_word() -> None:
    import asyncio

    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    driver = Pc1002BusDriver(load_profile("mida_cosma_pc1002"), send, "dtu_99")
    driver.handle_frame(first_broadcast())
    asyncio.run(driver.set_mode("cool"))
    # Optimistic: the state shows "cool" immediately, flagged pending until the board echoes it.
    assert driver.state.mode == "cool"
    assert "mode" in driver.state.pending
    sent.clear()
    asyncio.run(driver.set_setpoint(26.0))
    starts = [parse_frame(f).start for f in sent]
    assert starts == [1135]
    assert driver.state.setpoint == 26.0
    # A broadcast that still says heat neither confirms nor reverts the pending mode.
    driver.handle_frame(first_broadcast())
    assert driver.state.mode == "cool"
    sent.clear()
    asyncio.run(driver.set_setpoint(27.0))
    assert [parse_frame(f).start for f in sent] == [1135]
    regs = dict(driver.state.raw)
    regs[2012] = 0
    regs[2013] = 270
    driver._publish(regs)
    assert driver.state.mode == "cool"
    assert driver.state.setpoint == 27.0
    assert driver.state.pending == []


def test_set_setpoint_falls_back_to_1013_without_per_mode_words() -> None:
    import asyncio

    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    driver = Pc1002BusDriver(load_profile("phnix_mini_pc1002"), send, "dtu_99")
    driver.handle_frame(first_broadcast())
    asyncio.run(driver.set_setpoint(28.0))
    assert [(parse_frame(f).start, list(parse_frame(f).values)) for f in sent] == [
        (1013, [280])
    ]


def test_overlapping_refresh_settings_serialized() -> None:
    import asyncio

    from spo_pool_heat_pump.modbus_rtu import encode_fc03_reply

    profile = load_profile("mida_cosma_pc1002")
    profile["service_menu"] = {
        "read": {"slave": 1, "timeout_s": 0.4},
        "pages": [{"start": 1001, "qty": 90}, {"start": 1091, "qty": 90}],
        "params": profile["service_menu"]["params"],
    }
    driver: Pc1002BusDriver | None = None

    async def send(frame: bytes) -> None:
        req = parse_frame(frame)
        assert req is not None and driver is not None
        values = [0] * int(req.qty or 90)
        if req.start == 1001:
            values[19] = 25
        elif req.start == 1091:
            values[45] = 310
        await asyncio.sleep(0.02)
        driver.handle_frame(encode_fc03_reply(1, values))

    driver = Pc1002BusDriver(profile, send, "dtu_99")
    driver.handle_frame(first_broadcast())

    async def run() -> None:
        ok1, ok2 = await asyncio.gather(
            driver.refresh_settings(), driver.refresh_settings()
        )
        assert ok1 is True and ok2 is True
        assert driver.settings.regs.get(1020) == 25
        assert driver.settings.regs.get(1136) == 310

    asyncio.run(run())
