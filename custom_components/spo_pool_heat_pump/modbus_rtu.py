"""Modbus RTU framing shared by every driver. No pymodbus."""

from __future__ import annotations

import struct
from dataclasses import dataclass

FC_READ_COILS = 1
FC_READ_DISCRETE = 2
FC_READ_HOLDING = 3
FC_READ_INPUT = 4
FC_WRITE_COIL = 5
FC_WRITE_SINGLE = 6
FC_WRITE_MULTI = 16


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def append_crc(body: bytes) -> bytes:
    crc = crc16(body)
    return body + bytes((crc & 0xFF, crc >> 8))


def crc_ok(frame: bytes) -> bool:
    if len(frame) < 4:
        return False
    return (frame[-2] | (frame[-1] << 8)) == crc16(frame[:-2])


def i16(value: int) -> int:
    return value - 65536 if value >= 32768 else value


def u16(value: int) -> int:
    return value & 0xFFFF


def pack_regs(values: list[int]) -> bytes:
    return b"".join(struct.pack(">H", u16(v)) for v in values)


def unpack_regs(data: bytes) -> list[int]:
    if len(data) % 2:
        data = data[:-1]
    return list(struct.unpack(">" + "H" * (len(data) // 2), data))


def encode_fc03(slave: int, start: int, qty: int) -> bytes:
    return append_crc(bytes((slave, FC_READ_HOLDING)) + struct.pack(">HH", start, qty))


def encode_fc01(slave: int, start: int, qty: int) -> bytes:
    return append_crc(bytes((slave, FC_READ_COILS)) + struct.pack(">HH", start, qty))


def encode_fc04(slave: int, start: int, qty: int) -> bytes:
    return append_crc(bytes((slave, FC_READ_INPUT)) + struct.pack(">HH", start, qty))


def encode_fc06(slave: int, register: int, value: int) -> bytes:
    return append_crc(bytes((slave, FC_WRITE_SINGLE)) + struct.pack(">HH", register, u16(value)))


def encode_fc05(slave: int, coil: int, on: bool) -> bytes:
    return append_crc(bytes((slave, FC_WRITE_COIL)) + struct.pack(">HH", coil, 0xFF00 if on else 0x0000))


def encode_fc16(slave: int, start: int, values: list[int]) -> bytes:
    payload = pack_regs(values)
    body = bytes((slave, FC_WRITE_MULTI)) + struct.pack(">HHB", start, len(values), len(payload)) + payload
    return append_crc(body)


def encode_fc16_reply(slave: int, start: int, qty: int) -> bytes:
    return append_crc(bytes((slave, FC_WRITE_MULTI)) + struct.pack(">HH", start, qty))


def encode_exception(slave: int, function: int, code: int) -> bytes:
    return append_crc(bytes((slave, function | 0x80, code & 0xFF)))


def encode_fc03_reply(slave: int, values: list[int]) -> bytes:
    payload = pack_regs(values)
    return append_crc(bytes((slave, FC_READ_HOLDING, len(payload))) + payload)


def encode_fc04_reply(slave: int, values: list[int]) -> bytes:
    payload = pack_regs(values)
    return append_crc(bytes((slave, FC_READ_INPUT, len(payload))) + payload)


def encode_fc01_reply(slave: int, bits: list[bool]) -> bytes:
    nbytes = (len(bits) + 7) // 8
    data = bytearray(nbytes)
    for i, bit in enumerate(bits):
        if bit:
            data[i // 8] |= 1 << (i % 8)
    return append_crc(bytes((slave, FC_READ_COILS, nbytes)) + bytes(data))


@dataclass(slots=True)
class RtuFrame:
    slave: int
    function: int
    start: int | None
    qty: int | None
    values: list[int]
    raw: bytes
    kind: str  # request, reply, write, unknown


def parse_frame(frame: bytes) -> RtuFrame | None:
    if not crc_ok(frame) or len(frame) < 4:
        return None
    slave, func = frame[0], frame[1]
    body = frame[2:-2]

    if func == FC_WRITE_MULTI and len(body) == 4:
        start, qty = struct.unpack(">HH", body)
        return RtuFrame(slave, func, start, qty, [], frame, "write")

    if func == FC_WRITE_MULTI and len(body) >= 5:
        start, qty, bc = struct.unpack(">HHB", body[:5])
        if len(body) >= 5 + bc:
            return RtuFrame(slave, func, start, qty, unpack_regs(body[5 : 5 + bc]), frame, "write")

    if func in (FC_READ_HOLDING, FC_READ_INPUT, FC_READ_COILS, FC_READ_DISCRETE):
        if len(body) == 4:
            start, qty = struct.unpack(">HH", body)
            return RtuFrame(slave, func, start, qty, [], frame, "request")
        if body:
            bc = body[0]
            data = body[1 : 1 + bc]
            if func in (FC_READ_COILS, FC_READ_DISCRETE):
                bits = []
                for i in range(bc * 8):
                    bits.append(bool(data[i // 8] & (1 << (i % 8))))
                return RtuFrame(slave, func, None, None, [int(b) for b in bits], frame, "reply")
            return RtuFrame(slave, func, None, None, unpack_regs(data), frame, "reply")

    if func in (FC_WRITE_SINGLE, FC_WRITE_COIL) and len(body) == 4:
        start, value = struct.unpack(">HH", body)
        return RtuFrame(slave, func, start, 1, [value], frame, "write")

    if func & 0x80 and len(body) == 1:
        return RtuFrame(slave, func, None, None, [body[0]], frame, "exception")

    return RtuFrame(slave, func, None, None, [], frame, "unknown")


def find_frames(buf: bytes) -> list[RtuFrame]:
    """Walk a byte stream and yield CRC-valid RTU frames. Non-CRC noise is dropped."""
    found: list[RtuFrame] = []
    i = 0
    n = len(buf)
    while i < n - 3:
        # Minimum RTU is 4 bytes; try plausible lengths from this offset.
        matched = False
        for length in _candidate_lengths(buf, i):
            chunk = buf[i : i + length]
            parsed = parse_frame(chunk)
            if parsed:
                found.append(parsed)
                i += length
                matched = True
                break
        if not matched:
            i += 1
    return found


def _candidate_lengths(buf: bytes, i: int) -> list[int]:
    n = len(buf) - i
    if n < 4:
        return []
    func = buf[i + 1]
    lengths = {8, 8}  # typical 8-byte request / FC06
    if func & 0x80:
        lengths.add(5)
    if func == FC_WRITE_MULTI and n >= 9:
        qty = int.from_bytes(buf[i + 4 : i + 6], "big")
        bc = buf[i + 6] if i + 6 < len(buf) else 0
        lengths.add(9 + bc)
        # also trust declared qty
        lengths.add(9 + qty * 2)
    if func in (FC_READ_HOLDING, FC_READ_INPUT) and n >= 5:
        bc = buf[i + 2]
        lengths.add(5 + bc)
    if func in (FC_READ_COILS, FC_READ_DISCRETE) and n >= 5:
        bc = buf[i + 2]
        lengths.add(5 + bc)
    return sorted(l for l in lengths if 4 <= l <= n)


def hex_to_bytes(text: str) -> bytes:
    return bytes(int(p, 16) for p in text.replace(",", " ").split() if p)


def bytes_to_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)
