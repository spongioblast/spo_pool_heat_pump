"""EvoHeat Evo Fusion-i: PC1002 bus with its own panel flags (dump 20261104_121425).

The wired display raised 3011 = 0x0001 for power / mode / 1013, 0x0004 for quiet
1076 and 0x0041 for a setpoint (1013 in page 1001 + 1135-1137 in page 1091).
Broadcast 2013 stays 0, so the target is page word 1013.
"""

from __future__ import annotations

import asyncio

from spo_pool_heat_pump.const import WRITE_PATH_SLAVE2
from spo_pool_heat_pump.drivers.pc1002_bus import Pc1002BusDriver
from spo_pool_heat_pump.modbus_rtu import encode_fc03, encode_fc16, hex_to_bytes, parse_frame
from spo_pool_heat_pump.profiles import load_profile

PROFILE_ID = "evoheat_evo_fusion_i_pc1002"


def _frames() -> dict[str, bytes]:
    frames = load_profile(PROFILE_ID)["fixtures"]["frames"]
    return {name: hex_to_bytes(hex_s) for name, hex_s in frames.items()}


def make_driver(profile_id: str = PROFILE_ID) -> Pc1002BusDriver:
    async def send(_frame: bytes) -> None:
        return None

    driver = Pc1002BusDriver(load_profile(profile_id), send, WRITE_PATH_SLAVE2)
    frames = _frames()
    for name in ("page_1001_heat_28", "page_1091_heat_28", "broadcast_heating"):
        driver.handle_frame(frames[name])
    return driver


def poll_flags(driver: Pc1002BusDriver) -> int:
    reply = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
    assert reply is not None
    return reply.values[10]


def test_dump_frames_decode() -> None:
    state = make_driver().state
    assert state.available
    assert state.power is True
    assert state.mode == "heat"
    assert state.t_inlet == 26.0
    assert state.t_outlet == 27.5
    assert state.setpoint == 28.0, "target is page word 1013; broadcast 2013 is 0"
    assert state.get("setpoint_heat") == 28.0
    assert state.get("setpoint_cool") == 26.5
    assert state.outputs["compressor"] is True
    assert state.serial.startswith("WF2401080151")
    assert state.fw_main == 156


def test_power_uses_panel_bit_0x0001() -> None:
    driver = make_driver()
    asyncio.run(driver.set_power(False))
    page = driver.slave2.block_1001
    assert page[1011 - 1001] == 0
    assert page[1014 - 1001] == 0
    assert poll_flags(driver) == 0x0001


def test_quiet_uses_panel_bit_0x0004() -> None:
    driver = make_driver()
    asyncio.run(driver.set_silent(True))
    assert driver.slave2.block_1001[1076 - 1001] == 1
    assert poll_flags(driver) == 0x0004


def test_setpoint_writes_mode_word_and_1013_like_the_panel() -> None:
    driver = make_driver()
    asyncio.run(driver.set_setpoint(27.5))
    assert driver.slave2.block_1091[1136 - 1091] == 275
    assert driver.slave2.block_1001[1013 - 1001] == 275
    assert poll_flags(driver) == 0x0041
    assert driver.state.setpoint == 27.5

    # The board reads 1001 first, then 1091 — the remaining bit stays up.
    driver.handle_frame(encode_fc03(2, 1001, 90))
    assert poll_flags(driver) == 0x0040
    driver.handle_frame(encode_fc03(2, 1091, 90))
    assert poll_flags(driver) == 0


def test_setpoint_for_other_mode_leaves_1013_alone() -> None:
    driver = make_driver()
    asyncio.run(driver.set_setpoint(25.0, which="setpoint_cool"))
    assert driver.slave2.block_1091[1135 - 1091] == 250
    assert driver.slave2.block_1001[1013 - 1001] == 280
    assert poll_flags(driver) == 0x0040


def test_mode_change_copies_new_mode_setpoint_into_1013() -> None:
    driver = make_driver()
    asyncio.run(driver.set_mode("cool"))
    page = driver.slave2.block_1001
    assert page[1012 - 1001] == 0
    assert page[1013 - 1001] == 265, "1135 cool from the board's 1091 page"
    assert poll_flags(driver) == 0x0001
    assert driver.state.setpoint == 26.5


def test_board_writes_to_slave4_do_not_touch_settings() -> None:
    # sebr 20261118_112422: the board ramps a device on slave 4 with
    # FC16 1011×3 [on, speed, 0]. Those are not panel words 1011-1013.
    driver = make_driver()
    for values in ([1, 580, 0], [1, 400, 0], [0, 0, 0]):
        driver.handle_frame(encode_fc16(4, 1011, values))
    assert driver.state.setpoint == 28.0
    assert driver.state.mode == "heat"
    assert driver.slave2.block_1001[1013 - 1001] == 280


def test_cosma_keeps_its_bits_and_never_writes_1013() -> None:
    driver = make_driver("mida_cosma_pc1002")
    asyncio.run(driver.set_mode("cool"))
    assert driver.slave2.block_1001[1013 - 1001] == 280
    assert poll_flags(driver) == 0x0004
    asyncio.run(driver.set_setpoint(27.5, which="setpoint_heat"))
    assert driver.slave2.block_1001[1013 - 1001] == 280
    assert driver.slave2.flags_3011 & 0x0040
