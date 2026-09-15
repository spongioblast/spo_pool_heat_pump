"""The existing RS-485 dump dialect (.log + .bin). Protocol-agnostic hex."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

TS = re.compile(r"^\[(?P<ts>[^\]]+)\] t\+\s*(?P<t>[\d.]+)s\s+(?P<n>\d+) bytes")


def hex_ascii(data: bytes, width: int = 16) -> list[str]:
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"  {hex_part:<{width * 3}} | {ascii_part}")
    return lines


def dump_header(
    *,
    port: str,
    baud: int,
    data_bits: int,
    parity: str,
    stop_bits: str | int,
    gap_s: float,
    note: str = "",
    extra: str = "",
) -> str:
    started = dt.datetime.now().isoformat(timespec="milliseconds")
    lines = [
        "# raw RS-485 dump",
        f"# port={port} {baud} {data_bits}{parity}{stop_bits}",
        f"# started={started}",
        f"# gap_s={gap_s}",
    ]
    if note:
        lines.append(f"# note={note}")
    if extra:
        lines.append(extra if extra.startswith("#") else f"# {extra}")
    return "\n".join(lines) + "\n\n"


def format_chunk(
    data: bytes,
    *,
    rel_s: float,
    idle_s: float | None,
    when: dt.datetime | None = None,
) -> str:
    wall = (when or dt.datetime.now()).isoformat(timespec="milliseconds")
    parts: list[str] = []
    if idle_s is not None:
        parts.append(f"# idle {idle_s * 1000:.1f} ms")
    parts.append(f"[{wall}] t+{rel_s:9.3f}s  {len(data)} bytes")
    parts.extend(hex_ascii(data))
    parts.append("")
    return "\n".join(parts) + "\n"


@dataclass
class Chunk:
    t: float
    data: bytes
    wall: str | None = None


def read_log(path: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    t = 0.0
    wall: str | None = None
    hex_parts: list[str] = []
    grabbing = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TS.match(line)
        if m:
            if grabbing and hex_parts:
                chunks.append(
                    Chunk(t, bytes(int(x, 16) for x in hex_parts if len(x) == 2), wall)
                )
            grabbing = True
            t = float(m.group("t"))
            wall = m.group("ts")
            hex_parts = []
            continue
        if grabbing and line.strip() and not line.startswith("#"):
            left = line.split("|")[0]
            hex_parts.extend(p for p in left.split() if len(p) == 2)
    if grabbing and hex_parts:
        chunks.append(Chunk(t, bytes(int(x, 16) for x in hex_parts if len(x) == 2), wall))
    return chunks


def header_fields(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("# "):
            if line.startswith("["):
                break
            continue
        if "=" in line:
            key, _, val = line[2:].partition("=")
            out[key.strip()] = val.strip()
    return out
