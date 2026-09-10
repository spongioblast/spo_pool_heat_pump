"""Parse cosmo_watch RS-485 dump logs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

TS = re.compile(r"^\[(?P<ts>[^\]]+)\] t\+\s*(?P<t>[\d.]+)s\s+(?P<n>\d+) bytes")


@dataclass
class Packet:
    t: float
    data: bytes


def read_dump(path: Path) -> list[Packet]:
    packets: list[Packet] = []
    t = 0.0
    hex_parts: list[str] = []
    grabbing = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TS.match(line)
        if m:
            if grabbing and hex_parts:
                packets.append(Packet(t, bytes(int(x, 16) for x in hex_parts if len(x) == 2)))
            grabbing = True
            t = float(m.group("t"))
            hex_parts = []
            continue
        if grabbing and line.strip() and not line.startswith("#"):
            left = line.split("|")[0]
            hex_parts.extend(p for p in left.split() if len(p) == 2)
    if grabbing and hex_parts:
        packets.append(Packet(t, bytes(int(x, 16) for x in hex_parts if len(x) == 2)))
    return packets
