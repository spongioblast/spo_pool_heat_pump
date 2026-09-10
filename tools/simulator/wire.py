"""Encode SimUnit by walking the profile map — inverse of apply_map."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from spo_pool_heat_pump.modbus_rtu import encode_fc16
from spo_pool_heat_pump.const import BROADCAST_QTY, BROADCAST_START
from spo_pool_heat_pump.profiles import (
    decode_value,
    encode_value,
    service_menu_params,
    lookup_write_spec,
    profile_registers,
)

from .state import SimUnit


def encode_ascii(text: str, count: int) -> list[int]:
    raw = text.encode("ascii", "replace")[: count * 2].ljust(count * 2, b"\x00")
    return [int.from_bytes(raw[i : i + 2], "big") for i in range(0, len(raw), 2)]


def encode_bcd_hms(clock: datetime) -> list[int]:
    def bcd(n: int) -> int:
        return ((n // 10) << 4) | (n % 10)

    return [bcd(clock.hour % 24), bcd(clock.minute % 60), bcd(clock.second % 60)]


def pack_bits(bits: dict[str, int], values: dict[str, bool]) -> int:
    word = 0
    for name, bit in bits.items():
        if values.get(name):
            word |= 1 << int(bit)
    return word


def write_index(profile: dict[str, Any]) -> dict[int, str]:
    idx: dict[int, str] = {}
    for key, spec in {**profile_registers(profile), **service_menu_params(profile)}.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("write") is not None:
            idx[int(spec["write"])] = key
        if spec.get("reg") is not None:
            idx.setdefault(int(spec["reg"]), key)
    return idx


def _put_word(regs: dict[int, int], blocks: dict[str, list[int]], spec: dict[str, Any], raw: int) -> None:
    if "reg" in spec:
        regs[int(spec["reg"])] = raw & 0xFFFF
    if "block" in spec:
        name = str(spec["block"])
        off = int(spec.get("offset", 0))
        block = blocks.setdefault(name, [])
        while len(block) <= off:
            block.append(0)
        block[off] = raw & 0xFFFF


def encode_maps(unit: SimUnit) -> tuple[dict[int, int], dict[str, list[int]], dict[int, int]]:
    profile = unit.profile
    enums = profile.get("enums") or {}
    regs: dict[int, int] = {}
    blocks: dict[str, list[int]] = {}
    settings = dict(unit.settings)
    mapping = profile_registers(profile)

    for key, spec in mapping.items():
        typ = spec.get("type")
        if typ == "faults":
            for reg in spec.get("regs") or []:
                regs[int(reg)] = unit.fault_words.get(int(reg), 0) & 0xFFFF
            continue
        if typ == "ascii":
            start = int(spec.get("reg", 2001))
            count = int(spec.get("count", 7))
            for i, word in enumerate(encode_ascii(unit.serial or "", count)):
                regs[start + i] = word
            continue
        if typ == "bcd_hms":
            start = int(spec["reg"])
            for i, word in enumerate(encode_bcd_hms(unit.clock)):
                settings[start + i] = word
                regs[start + i] = word
            continue
        if typ == "bits":
            raw = pack_bits(spec.get("bits") or {}, unit.outputs if key == "outputs" else (unit.get_value(key) or {}))
            _put_word(regs, blocks, spec, raw)
            continue
        value = unit.get_value(key)
        if value is None:
            continue
        raw = encode_value(spec, value, enums) & 0xFFFF
        _put_word(regs, blocks, spec, raw)
        write = spec.get("write")
        if write is not None:
            settings[int(write)] = raw

    if "coils" in blocks and blocks["coils"]:
        if unit.power:
            blocks["coils"][0] = blocks["coils"][0] | 1
        elif not unit.outputs.get("compressor"):
            blocks["coils"][0] = blocks["coils"][0] & ~1

    for key, spec in service_menu_params(profile).items():
        value = unit.extras.get(key, spec.get("default"))
        if value is None:
            continue
        settings[int(spec["reg"])] = encode_value(spec, value, enums) & 0xFFFF

    return regs, blocks, settings


def encode_broadcast_words(unit: SimUnit, start: int = BROADCAST_START, qty: int = BROADCAST_QTY) -> list[int]:
    regs, _, _ = encode_maps(unit)
    return [regs.get(start + i, 0) & 0xFFFF for i in range(qty)]


def encode_broadcast_frame(unit: SimUnit) -> bytes:
    return encode_fc16(0, BROADCAST_START, encode_broadcast_words(unit))


def settings_page(unit: SimUnit, start: int, qty: int) -> list[int]:
    _, _, settings = encode_maps(unit)
    return [settings.get(start + i, 0) & 0xFFFF for i in range(qty)]


def apply_write(unit: SimUnit, start: int, values: list[int]) -> None:
    idx = write_index(unit.profile)
    enums = unit.profile.get("enums") or {}
    for i, raw in enumerate(values):
        addr = int(start) + i
        word = int(raw) & 0xFFFF
        unit.settings[addr] = word
        key = idx.get(addr)
        if not key:
            continue
        try:
            spec = lookup_write_spec(unit.profile, key)
        except KeyError:
            continue
        decoded = decode_value(spec, word, enums)
        unit.set_value(key, decoded)
    unit.sync_extras()


def apply_coil_write(unit: SimUnit, coil: int, on: bool) -> None:
    apply_write(unit, coil, [1 if on else 0])


def block_words(unit: SimUnit, name: str, start: int, qty: int) -> list[int]:
    _, blocks, _ = encode_maps(unit)
    data = list(blocks.get(name) or [])
    while len(data) < start + qty:
        data.append(0)
    return [int(x) & 0xFFFF for x in data[start : start + qty]]


def coil_bits(unit: SimUnit, start: int, qty: int) -> list[bool]:
    words = block_words(unit, "coils", 0, start + qty)
    return [bool(w) for w in words[start : start + qty]]
