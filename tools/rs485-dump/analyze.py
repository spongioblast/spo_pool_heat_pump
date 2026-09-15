#!/usr/bin/env python3
"""Offline view of an RS-485 dump: hex stats always, Modbus maps if CRC frames exist."""

from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

from format import header_fields, read_log
from rtu import decode, scan_frames


def analyze_path(path: Path) -> dict:
    chunks = read_log(path)
    raw = b"".join(c.data for c in chunks)
    frames = [(off, fr, decode(fr)) for off, fr in scan_frames(raw)]
    duration = (chunks[-1].t - chunks[0].t) if len(chunks) >= 2 else 0.0
    sizes = collections.Counter(len(c.data) for c in chunks)
    fc_hist = collections.Counter((d["slave"], d["fc"], d.get("kind")) for _o, _f, d in frames)
    polls = collections.Counter()
    writes = collections.Counter()
    pages = collections.Counter()
    broadcasts = 0
    latest: dict[tuple[int, int], int] = {}
    pending: dict[int, dict] = {}
    for _off, _fr, d in frames:
        kind = d.get("kind")
        slave = d["slave"]
        if kind == "req" and "start" in d:
            polls[(slave, d["fc"], d["start"], d["qty"])] += 1
            pending[slave] = d
        if kind in ("write", "write_req"):
            writes[(slave, d["fc"], d.get("start"), d.get("qty"))] += 1
            if d.get("values") and d.get("start") is not None:
                for i, val in enumerate(d["values"]):
                    latest[(slave, d["start"] + i)] = val
        if kind == "write_req" and slave == 0:
            broadcasts += 1
            pages[(slave, d.get("start"), d.get("qty"))] += 1
        if kind == "rsp" and slave in pending and d.get("values") is not None:
            req = pending.pop(slave)
            start = req.get("start")
            if start is not None:
                pages[(slave, start, req.get("qty"))] += 1
                for i, val in enumerate(d["values"]):
                    latest[(slave, start + i)] = val
    return {
        "file": path.name,
        "header": header_fields(path),
        "duration_s": duration,
        "bytes": len(raw),
        "chunks": len(chunks),
        "chunk_sizes": sizes.most_common(12),
        "rtu_frames": len(frames),
        "fc_hist": [(*k, n) for k, n in fc_hist.most_common()],
        "polls": [(*k, n) for k, n in polls.most_common()],
        "writes": [(*k, n) for k, n in writes.most_common()],
        "pages": [(*k, n) for k, n in pages.most_common()],
        "broadcasts": broadcasts,
        "latest_n": len(latest),
        "slaves": sorted({d["slave"] for _o, _f, d in frames}),
    }


def print_report(info: dict) -> None:
    hdr = info["header"]
    print(f"{info['file']}")
    if hdr:
        print(f"  header   {hdr}")
    print(
        f"  {info['duration_s']:.1f}s  {info['bytes']} bytes  "
        f"{info['chunks']} chunks  {info['rtu_frames']} CRC-valid RTU"
    )
    print(f"  common chunk sizes: {info['chunk_sizes']}")
    if not info["rtu_frames"]:
        print("  no Modbus RTU frames (wrong baud, or not Modbus) — keep the .log")
        return
    print(f"  slaves   {info['slaves']}")
    print("  FC counts:")
    for slave, fc, kind, n in info["fc_hist"][:20]:
        print(f"    slave={slave:3}  FC{fc:02X}  {kind:10}  n={n}")
    if info["polls"]:
        print("  polls (who reads what):")
        for slave, fc, start, qty, n in info["polls"]:
            print(f"    slave={slave:3}  FC{fc}  start={start} qty={qty}  n={n}")
    if info["writes"]:
        print("  writes:")
        for slave, fc, start, qty, n in info["writes"]:
            print(f"    slave={slave:3}  FC{fc:02X}  start={start} qty={qty}  n={n}")
    if info["broadcasts"]:
        print(f"  slave-0 FC16 (broadcast-like): {info['broadcasts']}")
    if info["pages"]:
        print("  unique start/qty:")
        for slave, start, qty, n in info["pages"][:20]:
            print(f"    slave={slave:3}  start={start} qty={qty}  n={n}")


def main() -> int:
    p = argparse.ArgumentParser(description="Summarise an RS-485 dump (.log)")
    p.add_argument("log", nargs="+", type=Path, help=".log file(s)")
    args = p.parse_args()
    for path in args.log:
        if not path.is_file():
            print(f"not a file: {path}", file=sys.stderr)
            return 2
        print_report(analyze_path(path))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
