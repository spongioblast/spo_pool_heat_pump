from __future__ import annotations

import asyncio

from spo_pool_heat_pump.drivers.detect import detect_profile, detect_reason
from spo_pool_heat_pump.modbus_rtu import encode_fc01_reply, encode_fc03_reply, encode_fc16, parse_frame


class FakeClient:
    def __init__(self, listen: list[bytes] | None = None, replies: dict[int, bytes] | None = None) -> None:
        self.listen = listen or []
        self.replies = replies or {}
        self.sent: list[bytes] = []
        self._on = None

    async def start(self, on_frame) -> None:
        self._on = on_frame
        for frame in self.listen:
            result = on_frame(frame)
            if asyncio.iscoroutine(result):
                await result

    async def send(self, frame: bytes) -> None:
        self.sent.append(frame)
        parsed = parse_frame(frame)
        if parsed and parsed.slave in self.replies and self._on:
            result = self._on(self.replies[parsed.slave])
            if asyncio.iscoroutine(result):
                await result

    async def stop(self) -> None:
        return None


def _broadcast(*, display: int = 0, main: int = 0, mini: int = 0) -> bytes:
    values = [0] * 90
    values[16] = mini
    values[83] = main
    values[88] = display
    return encode_fc16(0, 2001, values)


def test_detect_marks_slave99() -> None:
    client = FakeClient(listen=[_broadcast(display=713, main=772), encode_fc16(99, 1011, [1])])
    _profile, extra = asyncio.run(detect_profile(client, timeout=0.01, probe_wait=0.01))
    assert extra.get("slave99") is True


def test_detect_cosmo_from_firmware() -> None:
    client = FakeClient(listen=[_broadcast(display=713, main=772)])
    profile, extra = asyncio.run(detect_profile(client, timeout=0.01, probe_wait=0.01))
    assert profile == "mida_cosma_pc1002"
    assert extra["fw_display"] == 713


def test_detect_hayward_other_firmware() -> None:
    client = FakeClient(listen=[_broadcast(display=800, main=100)])
    profile, _extra = asyncio.run(detect_profile(client, timeout=0.01, probe_wait=0.01))
    assert profile == "hayward_pc1002"


def test_detect_phnix_from_mini_fw() -> None:
    client = FakeClient(listen=[_broadcast(mini=100)])
    profile, _extra = asyncio.run(detect_profile(client, timeout=0.01, probe_wait=0.01))
    assert profile == "phnix_mini_pc1002"


def test_detect_cn13_probe() -> None:
    client = FakeClient(replies={50: encode_fc03_reply(50, [1, 1, 310])})
    profile, extra = asyncio.run(detect_profile(client, timeout=0.01, probe_wait=0.01))
    assert profile == "fairland_pc1004_cn13"
    assert extra.get("slave50") is True
    assert parse_frame(client.sent[0]).slave == 50


def test_detect_legacy_coil_probe() -> None:
    client = FakeClient(replies={1: encode_fc01_reply(1, [True])})
    profile, extra = asyncio.run(detect_profile(client, timeout=0.01, probe_wait=0.01))
    assert profile == "fairland_ips_pro_coils"
    assert extra.get("slave1") is True


def test_detect_reason_explains_suggestion() -> None:
    note = detect_reason("mida_cosma_pc1002", {"broadcast": {}, "fw_display": 713})
    assert "MIDA Cosma" in note
    assert "713" in note
    hay = detect_reason("hayward_pc1002", {"broadcast": {}, "fw_display": 800})
    assert "Hayward" in hay
    assert "other firmware" in hay
    cn13 = detect_reason("fairland_pc1004_cn13", {"slave50": True})
    assert "Slave 50" in cn13


def test_detect_silent_bus_suggests_dump_only() -> None:
    client = FakeClient()
    profile, extra = asyncio.run(detect_profile(client, timeout=0.01, probe_wait=0.01))
    assert profile == "unknown_dump_only"
    assert extra.get("dump_only") is True
    note = detect_reason(profile, extra)
    assert "Dump-only" in note
