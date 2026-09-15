#!/usr/bin/env python3
"""Listen-only USB RS-485 dump. Start with no arguments; it writes a .log.

Never transmits. RTS stays low so the UTS-T02 does not drive the bus.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from pathlib import Path

from decode import RS232_HINT, ChangeWatch, profile_names, score_chunks
from format import dump_header, format_chunk
from rtu import format_rtu, scan_frames

# --- defaults (change here if the pump is already known) -------------------
# Serial. Most PHNIX / Hayward / Cosma boards are 9600 8N1. Poolstar cousins
# are 4800. Set DEFAULT_BAUD if you already know; --baud overrides for one run.
DEFAULT_BAUD = 9600
DEFAULT_DATA_BITS = 8
DEFAULT_PARITY = "N"  # N / E / O
DEFAULT_STOP_BITS = "1"
DEFAULT_GAP_S = 0.020  # idle that starts a new .log chunk
DEFAULT_POLL_S = 0.01
DEFAULT_RTS = 0  # 0 = receive; USB-RS485 adapters use RTS as DE
DEFAULT_DTR = 0

# Tried only when we already have bytes that look like noise, or with --probe-baud.
PROBE_BAUDS = (9600, 4800, 19200)
# Need this many RX bytes before we dare call the stream framed vs smear.
# Quiet time does not count. 64 B is a couple of Cosma polls, not a 2 s timer.
SCORE_AFTER_BYTES = 64
# How long a probe baud may wait for those bytes. Silence = inconclusive, skip.
PROBE_WAIT_S = 15.0

# UTS-T02 (WCH CH343G) first; then other USB-UART chips used on RS-485 dongles.
PREFERRED_VID_PID = {
    (0x1A86, 0x55D3),  # WCH CH343 / UTS-T02
    (0x1A86, 0x7523),  # CH340
    (0x1A86, 0x5523),  # CH341
    (0x1A86, 0x55D4),  # CH9102
    (0x0403, 0x6001),  # FTDI FT232
    (0x0403, 0x6014),  # FTDI FT232H
    (0x0403, 0x6015),  # FTDI FT-X
    (0x10C4, 0xEA60),  # Silicon Labs CP210x
    (0x067B, 0x2303),  # Prolific PL2303
    (0x067B, 0x23A3),  # Prolific PL2303TA
}

HERE = Path(__file__).resolve().parent
DEFAULT_OUTDIR = HERE / "dumps"

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - live capture only
    serial = None
    list_ports = None


def port_label(info) -> str:
    vidpid = f"{info.vid:04X}:{info.pid:04X}" if info.vid is not None else "no-vid"
    desc = info.description or info.device
    return f"{info.device}  {vidpid}  {desc}"


def usb_serial_ports():
    return [p for p in list_ports.comports() if p.vid is not None]


def autodetect_port() -> str:
    ports = usb_serial_ports()
    if not ports:
        raise SystemExit(
            "no USB serial dongle found (only built-in COM ports, or nothing plugged in)"
        )
    exact = [p for p in ports if (p.vid, p.pid) == (0x1A86, 0x55D3)]
    preferred = [p for p in ports if (p.vid, p.pid) in PREFERRED_VID_PID]
    candidates = exact or preferred or ports
    if len(candidates) > 1:
        print("multiple USB serial devices; pass --port COM#\n")
        for p in ports:
            mark = "  <--- candidate" if p in candidates else ""
            print(f"  {port_label(p)}{mark}")
        raise SystemExit(2)
    chosen = candidates[0]
    print(f"detected  {port_label(chosen)}")
    return chosen.device


def list_serial_ports() -> int:
    print("serial ports:\n")
    any_usb = False
    for p in list_ports.comports():
        kind = "USB" if p.vid is not None else "built-in"
        print(f"  {port_label(p)}  [{kind}]")
        any_usb = any_usb or p.vid is not None
    if not any_usb:
        print("\nno USB serial dongle found")
    return 0


def _need_serial() -> None:
    if serial is None:
        raise SystemExit("pyserial is required: pip install -r tools/rs485-dump/requirements.txt")


def open_port(args: argparse.Namespace, baud: int | None = None):
    _need_serial()
    parity_map = {
        "N": serial.PARITY_NONE,
        "E": serial.PARITY_EVEN,
        "O": serial.PARITY_ODD,
        "M": serial.PARITY_MARK,
        "S": serial.PARITY_SPACE,
    }
    stop_map = {
        "1": serial.STOPBITS_ONE,
        "1.5": serial.STOPBITS_ONE_POINT_FIVE,
        "2": serial.STOPBITS_TWO,
    }
    ser = serial.Serial(
        port=args.port,
        baudrate=baud if baud is not None else args.baud,
        bytesize=args.data_bits,
        parity=parity_map[args.parity],
        stopbits=stop_map[str(args.stop_bits)],
        timeout=args.poll,
        rtscts=False,
        dsrdtr=False,
        xonxoff=False,
    )
    # USB-RS485 adapters use RTS as DE. pyserial often leaves RTS high,
    # which drives the bus and turns the capture into noise.
    ser.rts = bool(args.rts)
    ser.dtr = bool(args.dtr)
    return ser


def _print_chunk(text: str, data: bytes, *, modbus_only: bool, watch: ChangeWatch) -> None:
    if not modbus_only:
        print(text, end="")
    for _off, frame in scan_frames(data):
        line = format_rtu(frame, watch.names)
        if line:
            print(line)
        for chg in watch.note_frame(frame):
            print(chg)


def _collect_sample(ser, gap_s: float, need_bytes: int, max_s: float) -> list[bytes]:
    """Idle-frame a short sample. Silent for max_s → empty list (inconclusive)."""
    chunks: list[bytes] = []
    buf = bytearray()
    last_rx: float | None = None
    deadline = time.monotonic() + max_s
    got = 0
    while time.monotonic() < deadline and got < need_bytes:
        chunk = ser.read(ser.in_waiting or 1)
        now = time.monotonic()
        if chunk:
            if buf and last_rx is not None and (now - last_rx) >= gap_s:
                chunks.append(bytes(buf))
                got += len(buf)
                buf.clear()
            buf.extend(chunk)
            last_rx = now
        elif buf and last_rx is not None and (now - last_rx) >= gap_s:
            chunks.append(bytes(buf))
            got += len(buf)
            buf.clear()
    if buf:
        chunks.append(bytes(buf))
    return chunks


def _try_other_bauds(args: argparse.Namespace, current: int) -> int | None:
    print("stream looks unstructured; trying other bauds (silence is skipped)\n")
    spoke_smear = 0
    for baud in PROBE_BAUDS:
        if baud == current:
            continue
        ser = open_port(args, baud)
        try:
            sample = _collect_sample(ser, args.gap, SCORE_AFTER_BYTES, PROBE_WAIT_S)
        finally:
            ser.close()
        score = score_chunks(sample, min_bytes=SCORE_AFTER_BYTES)
        print(
            f"  {baud:>6}  {score.kind:13}  {score.bytes_n:5} bytes  "
            f"{score.crc_frames} CRC  {score.note}"
        )
        if score.kind == "framed":
            return baud
        if score.kind == "smear":
            spoke_smear += 1
    if spoke_smear:
        print()
        print(RS232_HINT)
    return None


def dump(args: argparse.Namespace) -> int:
    os.makedirs(args.outdir, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    bin_path = Path(args.outdir) / f"{stamp}.bin"
    log_path = Path(args.outdir) / f"{stamp}.log"
    baud = args.baud
    watch = ChangeWatch(names=profile_names(args.profile) if args.profile else {})
    ser = open_port(args, baud)

    print(f"port      {args.port}")
    print(f"settings  {baud} {args.data_bits}{args.parity}{args.stop_bits}")
    print(f"gap       {args.gap * 1000:.1f} ms idle starts a new frame")
    print(f"raw       {bin_path}")
    print(f"log       {log_path}")
    print("listening  waiting for the bus is normal — Ctrl+C to stop\n")

    total = 0
    frames = 0
    buf = bytearray()
    scored_chunks: list[bytes] = []
    scored = bool(args.baud_locked)
    frame_t0: float | None = None
    last_rx: float | None = None
    t_start = time.monotonic()

    with bin_path.open("wb") as raw, log_path.open("w", encoding="utf-8", newline="\n") as log:
        log.write(
            dump_header(
                port=args.port,
                baud=baud,
                data_bits=args.data_bits,
                parity=args.parity,
                stop_bits=args.stop_bits,
                gap_s=args.gap,
                note=args.note,
            )
        )
        log.flush()

        def flush_frame() -> bytes | None:
            nonlocal buf, frame_t0, frames, total
            if not buf:
                return None
            rel = (frame_t0 or time.monotonic()) - t_start
            block = bytes(buf)
            text = format_chunk(block, rel_s=rel, idle_s=None)
            log.write(text)
            log.flush()
            raw.write(block)
            raw.flush()
            _print_chunk(text, block, modbus_only=args.modbus_only, watch=watch)
            frames += 1
            total += len(block)
            buf.clear()
            frame_t0 = None
            return block

        def start_idle(now: float) -> None:
            if last_rx is None:
                return
            idle = now - last_rx
            line = f"# idle {idle * 1000:.1f} ms\n"
            log.write(line)
            if not args.modbus_only:
                print(line, end="")

        try:
            while True:
                chunk = ser.read(ser.in_waiting or 1)
                now = time.monotonic()
                if chunk:
                    if not buf:
                        start_idle(now)
                        frame_t0 = now
                    buf.extend(chunk)
                    last_rx = now
                    if args.no_gap:
                        flushed = flush_frame()
                        if flushed is not None and not scored:
                            scored_chunks.append(flushed)
                    # score after enough bytes
                    if not scored and total + len(buf) >= SCORE_AFTER_BYTES:
                        if buf:
                            preview = scored_chunks + [bytes(buf)]
                        else:
                            preview = scored_chunks
                        verdict = score_chunks(preview, min_bytes=SCORE_AFTER_BYTES)
                        if verdict.kind == "framed":
                            scored = True
                        elif verdict.kind == "smear" and not args.baud_locked:
                            flushed = flush_frame()
                            if flushed is not None:
                                scored_chunks.append(flushed)
                            ser.close()
                            winner = _try_other_bauds(args, baud)
                            if winner is not None:
                                baud = winner
                                args.baud = winner
                                log.write(
                                    f"# baud now {baud} {args.data_bits}{args.parity}{args.stop_bits}\n"
                                )
                                log.flush()
                                print(f"using {baud} {args.data_bits}{args.parity}{args.stop_bits}\n")
                            ser = open_port(args, baud)
                            scored = True
                            last_rx = None
                            frame_t0 = None
                elif buf and last_rx is not None and (now - last_rx) >= args.gap:
                    flushed = flush_frame()
                    if flushed is not None and not scored:
                        scored_chunks.append(flushed)
                        if sum(len(c) for c in scored_chunks) >= SCORE_AFTER_BYTES:
                            verdict = score_chunks(scored_chunks, min_bytes=SCORE_AFTER_BYTES)
                            if verdict.kind == "framed":
                                scored = True
                            elif verdict.kind == "smear" and not args.baud_locked:
                                ser.close()
                                winner = _try_other_bauds(args, baud)
                                if winner is not None:
                                    baud = winner
                                    args.baud = winner
                                    log.write(
                                        f"# baud now {baud} {args.data_bits}{args.parity}{args.stop_bits}\n"
                                    )
                                    log.flush()
                                    print(f"using {baud} {args.data_bits}{args.parity}{args.stop_bits}\n")
                                else:
                                    # keep capturing at the original baud so the log is still useful
                                    pass
                                ser = open_port(args, baud)
                                scored = True
                                last_rx = None
                                frame_t0 = None
        except KeyboardInterrupt:
            flush_frame()
            print(f"\nstopped  {frames} frames, {total} bytes")
            print(f"raw      {bin_path}")
            print(f"log      {log_path}")
        finally:
            ser.close()
    return 0


def probe_only(args: argparse.Namespace) -> int:
    print(f"baud probe on {args.port} (need {SCORE_AFTER_BYTES} bytes or {PROBE_WAIT_S:.0f}s each)\n")
    print("touch the panel if the bus is idle — silence is not a verdict\n")
    for baud in PROBE_BAUDS:
        ser = open_port(args, baud)
        try:
            sample = _collect_sample(ser, args.gap, SCORE_AFTER_BYTES, PROBE_WAIT_S)
        finally:
            ser.close()
        score = score_chunks(sample, min_bytes=SCORE_AFTER_BYTES)
        print(
            f"  {baud:>6}  {score.kind:13}  {score.bytes_n:5} bytes  "
            f"{score.crc_frames} CRC  {score.note}"
        )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Listen-only USB RS-485 dump (UTS-T02). Writes a raw .log."
    )
    p.add_argument("--port", default=None, help="COM port (default: autodetect UTS-T02 / USB UART)")
    p.add_argument("--list-ports", action="store_true", help="list serial ports and exit")
    p.add_argument(
        "--baud",
        type=int,
        default=None,
        help=f"lock this baud (default {DEFAULT_BAUD}; skips the noise probe)",
    )
    p.add_argument("--parity", default=DEFAULT_PARITY, choices=list("NEOMS"))
    p.add_argument("--data-bits", type=int, default=DEFAULT_DATA_BITS, choices=[5, 6, 7, 8])
    p.add_argument("--stop-bits", default=DEFAULT_STOP_BITS, choices=["1", "1.5", "2"])
    p.add_argument("--gap", type=float, default=DEFAULT_GAP_S, help="idle seconds to split frames")
    p.add_argument("--poll", type=float, default=DEFAULT_POLL_S, help="serial read timeout")
    p.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    p.add_argument("--note", default="", help="stored in the .log header")
    p.add_argument("--no-gap", action="store_true", help="log every read immediately")
    p.add_argument(
        "--probe-baud",
        action="store_true",
        help="score PROBE_BAUDS on purpose, then exit (touch the panel if idle)",
    )
    p.add_argument("--rts", type=int, choices=[0, 1], default=DEFAULT_RTS)
    p.add_argument("--dtr", type=int, choices=[0, 1], default=DEFAULT_DTR)
    p.add_argument("--modbus-only", action="store_true", help="hide hex; print CRC-valid RTU only")
    p.add_argument("--profile", default=None, help="optional shipped profile id for CHG names")
    p.add_argument("--replay", default=None, help="print a .log (and RTU lines) instead of opening a port")
    args = p.parse_args()
    args.baud_locked = args.baud is not None
    if args.baud is None:
        args.baud = DEFAULT_BAUD

    if args.replay:
        return replay_log(Path(args.replay), args)

    _need_serial()
    if args.list_ports:
        return list_serial_ports()
    if not args.port:
        args.port = autodetect_port()
    if args.probe_baud:
        return probe_only(args)
    return dump(args)


def replay_log(path: Path, args: argparse.Namespace) -> int:
    from format import read_log

    if not path.is_file():
        raise SystemExit(f"not a file: {path}")
    watch = ChangeWatch(names=profile_names(args.profile) if args.profile else {})
    for chunk in read_log(path):
        text = format_chunk(chunk.data, rel_s=chunk.t, idle_s=None)
        _print_chunk(text, chunk.data, modbus_only=args.modbus_only, watch=watch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
