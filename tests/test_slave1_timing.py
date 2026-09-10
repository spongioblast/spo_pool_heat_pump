"""Measure slave-1 request→reply gap and slave-2 wait from the dump."""

from __future__ import annotations

from dump_log import read_dump
from spo_pool_heat_pump.drivers.slave2 import Slave2Responder
from spo_pool_heat_pump.modbus_rtu import encode_fc03, parse_frame

from conftest import DUMPS, requires_dumps

pytestmark = requires_dumps

DUMP = DUMPS / "20260906_104432.log"


def test_slave1_reply_margin() -> None:
    packets = read_dump(DUMP)
    gaps = []
    waits2 = []
    for i, pkt in enumerate(packets[:-1]):
        if len(pkt.data) < 8:
            continue
        parsed = parse_frame(pkt.data) if len(pkt.data) >= 4 else None
        nxt = packets[i + 1]
        if pkt.data[:2] == b"\x01\x03" and len(pkt.data) == 8:
            gaps.append(nxt.t - pkt.t)
        if pkt.data[:2] == b"\x02\x03" and len(pkt.data) == 8:
            waits2.append(nxt.t - pkt.t)
    assert gaps, "no slave-1 FC03 requests"
    median = sorted(gaps)[len(gaps) // 2]
    # Observed ~93 ms. Must stay well under a 500 ms board timeout.
    assert 0.03 < median < 0.25
    if waits2:
        assert sorted(waits2)[len(waits2) // 2] > 0.35


def test_slave2_answers_3001() -> None:
    resp = Slave2Responder()
    resp.block_3001[0] = 0x4239
    req = encode_fc03(2, 3001, 30)
    reply = resp.reply(req)
    assert reply is not None
    parsed = parse_frame(reply)
    assert parsed is not None
    assert parsed.slave == 2
    assert parsed.kind == "reply"
    assert parsed.values[0] == 0x4239
