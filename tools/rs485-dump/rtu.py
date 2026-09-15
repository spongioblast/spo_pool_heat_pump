"""Optional Modbus RTU scan. The dump itself does not assume this protocol."""

from __future__ import annotations

import struct

FC_NAMES = {
    1: "FC01",
    2: "FC02",
    3: "FC03",
    4: "FC04",
    5: "FC05",
    6: "FC06",
    15: "FC15",
    16: "FC16",
}


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def crc_ok(frame: bytes) -> bool:
    if len(frame) < 4:
        return False
    return (frame[-2] | (frame[-1] << 8)) == crc16(frame[:-2])


def possible_lens(buf: bytes, i: int) -> list[int]:
    n = len(buf) - i
    if n < 4:
        return []
    fc = buf[i + 1]
    lens: list[int] = []
    if fc in (0x01, 0x02, 0x03, 0x04):
        lens.append(8)
        if n >= 3:
            bc = buf[i + 2]
            if 1 <= bc <= 250:
                lens.append(3 + bc + 2)
    elif fc in (0x05, 0x06):
        lens.append(8)
    elif fc == 0x0F:
        if n >= 7:
            bc = buf[i + 6]
            if 1 <= bc <= 250:
                lens.append(7 + bc + 2)
        lens.append(8)
    elif fc == 0x10:
        if n >= 7:
            bc = buf[i + 6]
            if 1 <= bc <= 250:
                lens.append(7 + bc + 2)
        lens.append(8)
    elif fc & 0x80:
        lens.append(5)
    for extra in (5, 6, 7, 8, 9):
        if extra not in lens:
            lens.append(extra)
    return [length for length in lens if 4 <= length <= n]


def scan_frames(buf: bytes) -> list[tuple[int, bytes]]:
    frames: list[tuple[int, bytes]] = []
    i = 0
    n = len(buf)
    while i < n - 3:
        found = False
        for length in possible_lens(buf, i):
            cand = buf[i : i + length]
            if crc_ok(cand):
                frames.append((i, cand))
                i += length
                found = True
                break
        if not found:
            i += 1
    return frames


def decode(frame: bytes) -> dict:
    addr, fc = frame[0], frame[1]
    info: dict = {
        "slave": addr,
        "fc": fc,
        "len": len(frame),
        "hex": frame.hex(" ").upper(),
    }
    if fc & 0x80:
        info["kind"] = "exception"
        info["ex"] = frame[2] if len(frame) > 2 else None
        return info
    if fc in (1, 2, 3, 4):
        if len(frame) == 8:
            start, qty = struct.unpack(">HH", frame[2:6])
            info.update(kind="req", start=start, qty=qty)
        elif len(frame) >= 5:
            bc = frame[2]
            data = frame[3 : 3 + bc]
            regs: list[int] = []
            if fc in (3, 4) and bc % 2 == 0:
                regs = list(struct.unpack(">" + "H" * (bc // 2), data))
            info.update(kind="rsp", bytecount=bc, values=regs)
        else:
            info["kind"] = "unknown"
    elif fc in (5, 6):
        reg, val = struct.unpack(">HH", frame[2:6])
        info.update(kind="write", start=reg, value=val)
    elif fc == 0x10:
        if len(frame) == 8:
            start, qty = struct.unpack(">HH", frame[2:6])
            info.update(kind="write_rsp", start=start, qty=qty)
        elif len(frame) >= 9:
            start, qty, bc = struct.unpack(">HHB", frame[2:7])
            data = frame[7 : 7 + bc]
            regs = []
            if bc % 2 == 0:
                regs = list(struct.unpack(">" + "H" * (bc // 2), data))
            info.update(kind="write_req", start=start, qty=qty, values=regs)
        else:
            info["kind"] = "unknown"
    else:
        info["kind"] = "other"
    return info


def format_rtu(frame: bytes, names: dict[int, str] | None = None) -> str | None:
    if not crc_ok(frame):
        return None
    d = decode(frame)
    fc = d["fc"]
    label = FC_NAMES.get(fc & 0x7F, f"FC{fc:02X}")
    if fc & 0x80:
        return f"  RTU  slave={d['slave']} {label} exception={d.get('ex')}"
    kind = d.get("kind")
    start = d.get("start")
    qty = d.get("qty")
    extra = ""
    if start is not None:
        name = (names or {}).get(start)
        extra = f" start={start}" + (f" ({name})" if name else "")
        if qty is not None:
            extra += f" qty={qty}"
        if "value" in d:
            extra += f" value={d['value']}"
        elif d.get("values"):
            shown = d["values"][:6]
            extra += f" values={shown}" + ("…" if len(d["values"]) > 6 else "")
    return f"  RTU  slave={d['slave']} {label} {kind}{extra}"
