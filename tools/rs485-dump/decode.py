"""Stream scoring (framed vs smear) and optional live register-change lines."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from rtu import decode, scan_frames

# Printed only after every baud that actually spoke still looks like a smear.
# Silence is not this — a quiet bus is normal.
RS232_HINT = """\
Looks like noise, not a serial bus. On the UTS-T02, set the switch to RS485
(not RS232). RX should blink, TX should stay dark. If it is already on
RS485, swap A and B.
"""


@dataclass
class StreamScore:
    kind: str  # silent | inconclusive | framed | smear
    bytes_n: int
    chunks: int
    crc_frames: int
    covered: int = 0
    note: str = ""


def score_chunks(chunks: list[bytes], *, min_bytes: int = 64) -> StreamScore:
    """Judge a stream from idle-framed chunks. Quiet time does not count.

    Framed: CRC-valid Modbus RTU, or repeating chunk sizes (non-Modbus buses).
    Smear: bytes arrived but no structure — wrong baud or RS232 switch.
    Silent / inconclusive: not enough bytes yet; keep the default baud.
    """
    raw = b"".join(chunks)
    n = len(raw)
    if n == 0:
        return StreamScore("silent", 0, 0, 0, note="no bytes")
    frames = scan_frames(raw)
    covered = sum(len(fr) for _off, fr in frames)
    if n < min_bytes:
        return StreamScore(
            "inconclusive",
            n,
            len(chunks),
            len(frames),
            covered,
            note="waiting for more bytes",
        )
    if frames and (len(frames) >= 2 or covered >= min(32, n // 4)):
        return StreamScore("framed", n, len(chunks), len(frames), covered, note="CRC-valid RTU")
    if len(chunks) >= 3:
        sizes = [len(c) for c in chunks]
        top_size, top_n = Counter(sizes).most_common(1)[0]
        if top_n >= 3 and 4 <= top_size <= 400:
            return StreamScore(
                "framed",
                n,
                len(chunks),
                len(frames),
                covered,
                note=f"repeating {top_size}-byte chunks",
            )
    return StreamScore("smear", n, len(chunks), len(frames), covered, note="unstructured bytes")


@dataclass
class ChangeWatch:
    """Remember last seen holding/coil words so the console can print CHG."""

    last: dict[tuple[int, int], int] = field(default_factory=dict)
    names: dict[int, str] = field(default_factory=dict)

    def note_frame(self, frame: bytes) -> list[str]:
        lines: list[str] = []
        d = decode(frame)
        start = d.get("start")
        values = d.get("values")
        if start is None or not values:
            if "value" in d and start is not None:
                values = [int(d["value"])]
            else:
                return lines
        slave = int(d["slave"])
        for i, val in enumerate(values):
            reg = int(start) + i
            key = (slave, reg)
            prev = self.last.get(key)
            self.last[key] = int(val)
            if prev is not None and prev != int(val):
                name = self.names.get(reg, "")
                tag = f" {name}" if name else ""
                lines.append(f"  CHG  slave={slave} {reg}{tag} {prev} -> {val}")
        return lines


def profile_names(profile_id: str) -> dict[int, str]:
    """Best-effort labels from a shipped profile JSON. Empty if unavailable."""
    names: dict[int, str] = {}
    try:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        sys_path = root / "custom_components"
        if str(sys_path) not in sys.path:
            sys.path.insert(0, str(sys_path))
        from spo_pool_heat_pump.profiles import load_profile

        profile = load_profile(profile_id)
    except Exception:
        return names
    for key, spec in (profile.get("registers") or {}).items():
        if not isinstance(spec, dict):
            continue
        if "reg" in spec:
            names[int(spec["reg"])] = str(key)
        block = spec.get("block")
        offset = spec.get("offset")
        if block is not None and offset is not None:
            names[int(block) + int(offset)] = str(key)
    return names
