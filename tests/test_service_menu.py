from __future__ import annotations

import asyncio

import pytest
from dump_log import read_dump
from spo_pool_heat_pump.const import WRITE_PATH_SLAVE2, service_menu_writes_enabled, suggested_write_path
from spo_pool_heat_pump.drivers.pc1002_bus import Pc1002BusDriver
from spo_pool_heat_pump.drivers.slave2 import SettingsUnseeded
from spo_pool_heat_pump.modbus_rtu import crc_ok, encode_fc03, encode_fc03_reply, encode_fc16, parse_frame
from spo_pool_heat_pump.profiles import load_profile, validate_service_menu_write

from conftest import DUMPS, requires_dumps

pytestmark = requires_dumps

DUMP = DUMPS / "20260906_104432.log"


def first_broadcast() -> bytes:
    for pkt in read_dump(DUMP):
        if len(pkt.data) >= 9 and pkt.data[0] == 0 and pkt.data[1] == 0x10 and crc_ok(pkt.data):
            return pkt.data
    raise AssertionError("no 2001 frame")


def _short_service_menu(profile: dict) -> dict:
    profile["service_menu"] = {
        "read": {"slave": 1, "timeout_s": 0.02},
        "pages": [{"start": 1001, "qty": 90}],
        "params": profile["service_menu"]["params"],
    }
    return profile


def test_seeded_slave2_overlay_keeps_other_words() -> None:
    profile = load_profile("mida_cosma_pc1002")
    driver = Pc1002BusDriver(profile, lambda _f: None, WRITE_PATH_SLAVE2)
    values = [7] * 90
    driver.slave2.seed_page(1001, values)
    driver.slave2.queue_write(1020, 30)
    reply = driver.maybe_slave2_reply(encode_fc03(2, 1001, 90))
    parsed = parse_frame(reply)
    assert parsed is not None
    assert parsed.values[19] == 30
    assert parsed.values[0] == 7
    assert parsed.values[18] == 7


def test_unseeded_slave2_does_not_reply_zeros() -> None:
    profile = _short_service_menu(load_profile("mida_cosma_pc1002"))
    driver = Pc1002BusDriver(profile, lambda _f: None, WRITE_PATH_SLAVE2)
    assert driver.maybe_slave2_reply(encode_fc03(2, 1001, 90)) is None
    with pytest.raises(SettingsUnseeded):
        asyncio.run(driver.set_mode("heat"))
    assert driver.maybe_slave2_reply(encode_fc03(2, 1001, 90)) is None


def test_refresh_settings_fills_extras_and_survives_2001() -> None:
    profile = _short_service_menu(load_profile("mida_cosma_pc1002"))
    driver: Pc1002BusDriver | None = None

    async def send(frame: bytes) -> None:
        req = parse_frame(frame)
        assert req is not None and driver is not None
        values = [0] * 90
        values[19] = 25  # 1020 H06
        driver.handle_frame(encode_fc03_reply(1, values))

    driver = Pc1002BusDriver(profile, send, WRITE_PATH_SLAVE2)
    driver.handle_frame(first_broadcast())
    assert asyncio.run(driver.refresh_settings()) is True
    assert driver.state.extras.get("h06_min_freq_heat") == 25
    assert driver.slave2.seeded_1001 is True
    driver.handle_frame(first_broadcast())
    assert driver.state.extras.get("h06_min_freq_heat") == 25


def test_sniff_fc16_seeds_slave2() -> None:
    profile = load_profile("mida_cosma_pc1002")
    driver = Pc1002BusDriver(profile, lambda _f: None, WRITE_PATH_SLAVE2)
    values = [3] * 90
    values[19] = 40
    driver.handle_frame(encode_fc16(1, 1001, values))
    assert driver.slave2.seeded_1001 is True
    reply = parse_frame(driver.maybe_slave2_reply(encode_fc03(2, 1001, 90)))
    assert reply.values[19] == 40


def test_slave2_page_1181_seed_and_write() -> None:
    profile = load_profile("mida_cosma_pc1002")
    driver = Pc1002BusDriver(profile, lambda _f: None, WRITE_PATH_SLAVE2)
    driver.slave2.seed_page(1181, [4] * 90)
    assert driver.slave2.page_seeded(1191) is True
    driver.slave2.queue_write(1191, 12)
    reply = parse_frame(driver.maybe_slave2_reply(encode_fc03(2, 1181, 90)))
    assert reply is not None
    assert reply.values[10] == 12
    assert reply.values[0] == 4


def test_hayward_power_also_write_on_slave2() -> None:
    profile = load_profile("hayward_pc1002")
    driver = Pc1002BusDriver(profile, lambda _f: None, WRITE_PATH_SLAVE2)
    driver.slave2.seed_page(1001, [0] * 90)
    asyncio.run(driver.set_power(True))
    assert driver.slave2.block_1001[10] == 1  # 1011
    assert driver.slave2.block_1001[13] == 1  # 1014


def test_write_path_choices_follow_targets() -> None:
    from spo_pool_heat_pump.const import write_path_choices

    mini = write_path_choices(load_profile("phnix_mini_pc1002"))
    assert list(mini) == ["dtu_99", "slave2"]
    cosma = write_path_choices(load_profile("mida_cosma_pc1002"))
    hayward = write_path_choices(load_profile("hayward_pc1002"))
    assert list(cosma) == ["dtu_99", "slave2", "panel_1"]
    assert list(hayward) == ["dtu_99", "slave2", "panel_1"]


def test_suggested_write_path_no_dtu() -> None:
    assert suggested_write_path("pc1002_bus", {}) == WRITE_PATH_SLAVE2
    assert suggested_write_path("pc1002_bus", {"slave99": True}) == "dtu_99"


def test_service_menu_write_option_gate() -> None:
    profile = load_profile("mida_cosma_pc1002")
    assert service_menu_writes_enabled({}, {}) is False
    with pytest.raises(PermissionError):
        validate_service_menu_write(profile, False, "h06_min_freq_heat")
    spec = validate_service_menu_write(profile, True, "h06_min_freq_heat")
    assert spec["reg"] == 1020
    with pytest.raises(KeyError):
        validate_service_menu_write(profile, True, "h02_mode_type_or_restrictor")


def test_settings_absorb_ignores_interleaved_3001_request() -> None:
    from spo_pool_heat_pump.drivers.settings import SettingsCache
    from spo_pool_heat_pump.modbus_rtu import encode_fc03, encode_fc03_reply, parse_frame

    cache = SettingsCache()
    cache.expect_reply(1001, slave=1, qty=90)
    cache.absorb_frame(parse_frame(encode_fc03(1, 3001, 30)))
    cache.absorb_frame(parse_frame(encode_fc03_reply(1, [9] * 90)))
    assert cache.page_3001 is None
    assert 1001 not in cache.regs

    matched = SettingsCache()
    matched.expect_reply(1001, slave=1, qty=90)
    assert matched.absorb_frame(parse_frame(encode_fc03_reply(1, [9] * 90))) is True
    assert matched.regs[1001] == 9
    assert matched.regs[1090] == 9
    assert matched.page_3001 is None
    assert matched.take_page() == (1001, [9] * 90)


def test_cosmo_service_menu_params_loaded() -> None:
    profile = load_profile("mida_cosma_pc1002")
    params = profile["service_menu"]["params"]
    assert "h06_min_freq_heat" in params
    assert "temperature_unit" in params
    assert params["h06_min_freq_heat"]["writable"] is True
