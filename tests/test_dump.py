from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from conftest import PROTOCOL_ANALYSIS, requires_replay
from dump_log import read_dump
from spo_pool_heat_pump.dump import (
    DumpDirFull,
    DumpInvalidDuration,
    DumpInvalidName,
    DumpRecorder,
    delete_dump_file,
    dir_used_bytes,
    hex_ascii,
    list_dump_files,
    safe_dump_name,
)
from spo_pool_heat_pump.modbus_rtu import encode_fc16, find_frames

def _recorder(tmp_path: Path, **kw) -> DumpRecorder:
    opts = dict(
        directory=tmp_path,
        source="dr164 10.0.0.8:8899",
        profile="mida_cosma_pc1002",
        note="pressed Cool",
        duration_s=900,
    )
    opts.update(kw)
    return DumpRecorder(**opts)


def test_hex_ascii_matches_rs485_dump() -> None:
    data = bytes(range(20))
    lines = hex_ascii(data)
    assert lines[0].startswith("  00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F")
    assert lines[0].endswith("| ................")
    assert "10 11 12 13" in lines[1]


def test_round_trip_read_dump(tmp_path: Path) -> None:
    rx = encode_fc16(0, 2001, [0] * 90)
    tx = encode_fc16(99, 1011, [1])
    rec = _recorder(tmp_path)
    rec.start()
    rec.rx(rx)
    rec.tx(tx)
    rec.stop()
    log = next(tmp_path.glob("*.log"))
    packets = read_dump(log)
    assert [p.data for p in packets] == [rx, tx]
    raw = next(tmp_path.glob("*.bin")).read_bytes()
    assert raw == rx
    text = log.read_text(encoding="utf-8")
    assert "# dir=tx" in text
    assert "# note=pressed Cool" in text
    assert "# source=dr164 10.0.0.8:8899" in text


def test_tx_comment_does_not_break_parser(tmp_path: Path) -> None:
    frame = encode_fc16(0, 2001, [7] * 90)
    rec = _recorder(tmp_path, include_writes=True)
    rec.start()
    rec.tx(encode_fc16(99, 1013, [280]))
    rec.rx(frame)
    rec.stop()
    packets = read_dump(next(tmp_path.glob("*.log")))
    assert packets[-1].data == frame


def test_bin_is_inbound_only(tmp_path: Path) -> None:
    rec = _recorder(tmp_path)
    rec.start()
    rec.rx(b"\x01\x02")
    rec.tx(b"\x03\x04")
    rec.stop()
    assert next(tmp_path.glob("*.bin")).read_bytes() == b"\x01\x02"


@requires_replay
def test_load_bus_finds_broadcast(tmp_path: Path) -> None:
    if str(PROTOCOL_ANALYSIS) not in sys.path:
        sys.path.insert(0, str(PROTOCOL_ANALYSIS))
    from dump_replay_server import load_bus

    rec = _recorder(tmp_path)
    rec.start()
    rec.rx(encode_fc16(0, 2001, list(range(90))))
    rec.stop()
    broadcasts, _pages = load_bus(next(tmp_path.glob("*.log")))
    assert broadcasts
    frames = find_frames(broadcasts[0])
    assert frames[0].start == 2001
    assert frames[0].qty == 90


def test_duration_auto_stop(tmp_path: Path) -> None:
    rec = _recorder(tmp_path, duration_s=1)
    rec.start()
    rec._t0 = time.monotonic() - 2
    rec.rx(b"\xaa")
    rec.flush()
    assert rec.running is False
    assert rec.stop_reason == "duration"


def test_session_cap_stops_until_stop(tmp_path: Path) -> None:
    rec = _recorder(tmp_path, duration_s=0, rotate_bytes=120, keep_files=2)
    rec.start()
    for _ in range(30):
        rec.rx(bytes(40))
        rec.flush()
        if not rec.running:
            break
    assert rec.running is False
    assert rec.stop_reason == "session_cap"
    assert rec._part >= 2


def test_dir_full_refuses_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("spo_pool_heat_pump.dump.DIR_CAP_BYTES", 8)
    (tmp_path / "filler.bin").write_bytes(b"0123456789")
    rec = _recorder(tmp_path)
    with pytest.raises(DumpDirFull):
        rec.start()
    assert dir_used_bytes(tmp_path) >= 8


def test_path_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(DumpInvalidName):
        safe_dump_name("../secret.log")
    with pytest.raises(DumpInvalidName):
        safe_dump_name("a/b.log")
    rec = _recorder(tmp_path)
    rec.start()
    rec.rx(b"\x01")
    rec.stop()
    name = next(tmp_path.glob("*.log")).name
    delete_dump_file(tmp_path, name)
    assert list_dump_files(tmp_path) == []
    with pytest.raises(DumpInvalidName):
        delete_dump_file(tmp_path, "../x.log")


def test_invalid_duration() -> None:
    with pytest.raises(DumpInvalidDuration):
        DumpRecorder(Path("."), source="x", profile="y", duration_s=7201)


def test_list_includes_note(tmp_path: Path) -> None:
    rec = _recorder(tmp_path, note="Cool click")
    rec.start()
    rec.rx(b"\x00")
    rec.stop()
    rows = list_dump_files(tmp_path)
    assert len(rows) == 1
    assert rows[0]["note"] == "Cool click"


def test_tcp_tee_records_rx(tmp_path: Path) -> None:
    from spo_pool_heat_pump.transport.tcp import TcpRtuClient

    rec = _recorder(tmp_path)
    rec.start()
    client = TcpRtuClient("127.0.0.1", 1)
    client.recorder = rec
    import asyncio

    asyncio.run(client._emit(encode_fc16(0, 2001, [1] * 90)))
    rec.stop()
    assert read_dump(next(tmp_path.glob("*.log")))
