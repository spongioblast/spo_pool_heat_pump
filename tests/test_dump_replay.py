from __future__ import annotations

import sys

import pytest

from conftest import HAS_REPLAY, HA_ROOT, PROTOCOL_ANALYSIS, requires_replay

pytestmark = requires_replay

if not HAS_REPLAY:
    pytest.skip("lab dump_replay_server.py not present (standalone clone)", allow_module_level=True)

sys.path.insert(0, str(PROTOCOL_ANALYSIS))
sys.path.insert(0, str(HA_ROOT / "custom_components"))

from dump_replay_server import paint_broadcast, painted, remember_write  # noqa: E402
from spo_pool_heat_pump.modbus_rtu import encode_fc16, encode_fc16_reply, parse_frame  # noqa: E402


def test_write_1011_paints_broadcast_2011() -> None:
    overlays: dict[int, int] = {}
    remember_write(overlays, 1011, [1])
    raw = encode_fc16(0, 2001, [0] * 90)
    out = paint_broadcast(raw, overlays)
    frame = parse_frame(out)
    assert frame is not None
    assert frame.values[10] == 1


def test_page_read_uses_overlay() -> None:
    overlays: dict[int, int] = {}
    remember_write(overlays, 1013, [310])
    words = painted(1001, [0] * 90, overlays)
    assert words[12] == 310


def test_fc16_ack() -> None:
    frame = parse_frame(encode_fc16_reply(99, 1011, 1))
    assert frame is not None
    assert frame.function == 16
    assert frame.slave == 99
    assert frame.start == 1011
    assert frame.qty == 1
