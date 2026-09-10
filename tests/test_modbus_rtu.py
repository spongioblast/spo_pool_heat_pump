from __future__ import annotations

import json
from pathlib import Path

import pytest

from spo_pool_heat_pump.modbus_rtu import (
    bytes_to_hex,
    crc_ok,
    encode_exception,
    encode_fc01,
    encode_fc03,
    encode_fc16,
    find_frames,
    hex_to_bytes,
    parse_frame,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "custom_components/spo_pool_heat_pump/profiles/mida_cosma_pc1002.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["power_on", "power_off", "mode_heat", "mode_cool", "mode_auto", "silent_on", "heat_setpoint_31c", "active_setpoint_31c"])
def test_example_write_frames_crc(name: str) -> None:
    frame = hex_to_bytes(PROFILE["fixtures"]["frames"][name])
    assert crc_ok(frame)
    parsed = parse_frame(frame)
    assert parsed is not None
    assert parsed.slave == 99
    assert parsed.function == 16
    assert parsed.qty == 1


def test_encode_matches_app_power_on() -> None:
    frame = encode_fc16(99, 1011, [1])
    assert bytes_to_hex(frame) == PROFILE["fixtures"]["frames"]["power_on"].upper()


def test_encode_probe_frames() -> None:
    assert crc_ok(encode_fc03(50, 1011, 3))
    assert crc_ok(encode_fc01(1, 0, 1))
    fairland = json.loads((ROOT / "custom_components/spo_pool_heat_pump/profiles/fairland_pc1004_cn13.json").read_text(encoding="utf-8"))
    legacy = json.loads((ROOT / "custom_components/spo_pool_heat_pump/profiles/fairland_ips_pro_coils.json").read_text(encoding="utf-8"))
    assert bytes_to_hex(encode_fc03(50, 1011, 3)) == fairland["fixtures"]["frames"]["probe_slave50"]
    assert bytes_to_hex(encode_fc01(1, 0, 1)) == legacy["fixtures"]["frames"]["probe_coil0"]


def test_noise_dropped() -> None:
    noise = bytes.fromhex("DEADBEEF") + encode_fc16(99, 1011, [0])
    found = find_frames(noise)
    assert len(found) == 1
    assert found[0].start == 1011


def test_exception_frame_is_parsed() -> None:
    frame = encode_exception(50, 3, 2)
    parsed = parse_frame(frame)
    assert parsed is not None
    assert parsed.kind == "exception"
    assert parsed.slave == 50
    assert parsed.values == [2]
    found = find_frames(b"\xde\xad" + frame + b"\x00")
    assert any(f.kind == "exception" for f in found)
