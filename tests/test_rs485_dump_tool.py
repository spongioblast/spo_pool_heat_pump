"""tools/rs485-dump: dialect, RTU scan, analyze, framed-vs-smear scoring."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import DUMPS, requires_dumps
from spo_pool_heat_pump.modbus_rtu import encode_fc03, encode_fc03_reply, encode_fc16

TOOL = Path(__file__).resolve().parents[1] / "tools" / "rs485-dump"
if str(TOOL) not in sys.path:
    sys.path.insert(0, str(TOOL))

from analyze import analyze_path  # noqa: E402
from decode import RS232_HINT, score_chunks  # noqa: E402
from format import dump_header, format_chunk, hex_ascii, read_log  # noqa: E402
from rtu import crc_ok, format_rtu, scan_frames  # noqa: E402


def test_dump_defaults_are_the_documented_ones() -> None:
    import dump as dump_mod

    assert dump_mod.DEFAULT_BAUD == 9600
    assert dump_mod.DEFAULT_PARITY == "N"
    assert dump_mod.DEFAULT_GAP_S == 0.020
    assert dump_mod.PROBE_BAUDS == (9600, 4800, 19200)
    assert dump_mod.SCORE_AFTER_BYTES == 64
    assert dump_mod.DEFAULT_RTS == 0


def test_hex_ascii_matches_ha_dump() -> None:
    data = bytes(range(20))
    lines = hex_ascii(data)
    assert lines[0].startswith("  00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F")
    assert lines[0].endswith("| ................")


def test_log_round_trip(tmp_path: Path) -> None:
    req = encode_fc03(1, 3001, 30)
    rsp = encode_fc03_reply(1, list(range(30)))
    text = dump_header(
        port="COM4",
        baud=9600,
        data_bits=8,
        parity="N",
        stop_bits=1,
        gap_s=0.02,
        note="panel heat 30",
    )
    text += format_chunk(req, rel_s=0.0, idle_s=None)
    text += format_chunk(rsp, rel_s=0.35, idle_s=0.35)
    log = tmp_path / "t.log"
    log.write_text(text, encoding="utf-8")
    chunks = read_log(log)
    assert [c.data for c in chunks] == [req, rsp]
    assert "# raw RS-485 dump" in text
    assert "# port=COM4 9600 8N1" in text
    assert "# note=panel heat 30" in text


def test_rtu_overlay_on_cosma_shaped_fixture() -> None:
    req = encode_fc03(2, 3001, 30)
    bc = encode_fc16(0, 2001, [0] * 90)
    raw = req + bc
    frames = [fr for _off, fr in scan_frames(raw)]
    assert req in frames
    assert any(crc_ok(fr) and fr[0] == 0 and fr[1] == 0x10 for fr in frames)
    line = format_rtu(req)
    assert line is not None
    assert "slave=2" in line and "FC03" in line and "3001" in line


def test_analyze_reports_chunks_without_crc(tmp_path: Path) -> None:
    noise = bytes(range(1, 80))
    text = dump_header(
        port="COM4", baud=9600, data_bits=8, parity="N", stop_bits=1, gap_s=0.02
    )
    text += format_chunk(noise, rel_s=1.0, idle_s=None)
    log = tmp_path / "noise.log"
    log.write_text(text, encoding="utf-8")
    info = analyze_path(log)
    assert info["chunks"] == 1
    assert info["bytes"] == len(noise)
    assert info["rtu_frames"] == 0


def test_analyze_finds_poll_and_broadcast(tmp_path: Path) -> None:
    req = encode_fc03(1, 3001, 30)
    rsp = encode_fc03_reply(1, [7] * 30)
    bc = encode_fc16(0, 2001, [3] * 90)
    text = dump_header(
        port="COM4", baud=9600, data_bits=8, parity="N", stop_bits=1, gap_s=0.02
    )
    for i, frame in enumerate((req, rsp, bc)):
        text += format_chunk(frame, rel_s=float(i), idle_s=None)
    log = tmp_path / "ok.log"
    log.write_text(text, encoding="utf-8")
    info = analyze_path(log)
    assert info["rtu_frames"] >= 3
    assert 1 in info["slaves"] and 0 in info["slaves"]
    assert info["broadcasts"] >= 1
    assert any(row[0] == 1 and row[2] == 3001 for row in info["polls"])


def test_score_silent_and_inconclusive() -> None:
    assert score_chunks([], min_bytes=64).kind == "silent"
    assert score_chunks([b"\x01\x02"], min_bytes=64).kind == "inconclusive"


def test_score_framed_from_crc() -> None:
    req = encode_fc03(1, 3001, 30)
    rsp = encode_fc03_reply(1, list(range(30)))
    score = score_chunks([req, rsp], min_bytes=64)
    assert score.kind == "framed"
    assert score.crc_frames >= 2


def test_score_framed_from_repeating_sizes() -> None:
    chunk = bytes([0xD1, 0x31] + [0x00] * 14)
    score = score_chunks([chunk] * 5, min_bytes=64)
    assert score.kind == "framed"
    assert "repeating" in score.note


def test_score_smear_is_unstructured() -> None:
    # One irregular blob, no repeating sizes, no CRC — RS232-switch / wrong baud.
    score = score_chunks([bytes([0xAA] * 80)], min_bytes=64)
    assert score.kind == "smear"
    assert "RS485" in RS232_HINT


@requires_dumps
def test_analyze_optional_lab_dump() -> None:
    log = DUMPS / "20260906_104432.log"
    if not log.is_file():
        pytest.skip("lab dump missing")
    info = analyze_path(log)
    assert info["chunks"] > 10
    assert info["rtu_frames"] > 0
