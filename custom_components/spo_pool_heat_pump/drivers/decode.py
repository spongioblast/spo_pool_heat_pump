"""Apply a profile register map to a register dict / named poll blocks."""

from __future__ import annotations

from typing import Any

from ..profiles import (
    decode_bcd_hms,
    decode_faults,
    decode_outputs,
    decode_serial,
    decode_value,
    fault_meanings,
    profile_registers,
    resolve_hz_max,
)
from .base import HeatPumpState


def apply_map(
    profile: dict[str, Any],
    regs: dict[int, int],
    blocks: dict[str, list[int]] | None = None,
    settings: dict[int, int] | None = None,
) -> HeatPumpState:
    enums = profile.get("enums", {})
    ident = profile["identity"]
    state = HeatPumpState(
        available=True,
        manufacturer=ident.get("brand", ""),
        model=ident.get("model", ""),
        raw=dict(regs),
    )
    state.values = state.extras
    mapping = profile_registers(profile)
    blocks = blocks or {}
    settings = settings or {}

    def raw_for(spec: dict[str, Any]) -> int | None:
        if "reg" in spec and spec["reg"] in regs:
            return regs[spec["reg"]]
        if "block" in spec:
            data = blocks.get(spec["block"], [])
            off = spec.get("offset", 0)
            if 0 <= off < len(data):
                return data[off]
        write = spec.get("write")
        if write is not None and int(write) in settings:
            return settings[int(write)]
        if spec.get("reg") is not None and int(spec["reg"]) in settings:
            return settings[int(spec["reg"])]
        return None

    def words_for(start: int, count: int) -> list[int] | None:
        words: list[int] = []
        for i in range(count):
            addr = start + i
            if addr in regs:
                words.append(regs[addr])
            elif addr in settings:
                words.append(settings[addr])
            else:
                return None
        return words

    for key, spec in mapping.items():
        typ = spec.get("type")
        if typ == "bits":
            raw = raw_for(spec)
            if raw is not None:
                decoded = decode_outputs(raw, spec.get("bits") or {})
                if hasattr(state, key):
                    setattr(state, key, decoded)
                else:
                    state.extras[key] = decoded
            continue
        if typ == "faults":
            words = {int(r): regs.get(int(r), 0) for r in spec.get("regs", [])}
            state.faults = decode_faults(words, spec)
            state.fault_texts = fault_meanings(state.faults, spec)
            continue
        if typ == "ascii":
            start = int(spec.get("reg", 2001))
            count = int(spec.get("count", 7))
            sequential = words_for(start, count)
            if sequential is not None:
                state.serial = decode_serial(sequential)
            elif start in regs:
                state.serial = decode_serial([regs.get(start + i, 0) for i in range(count)])
            continue
        if typ == "bcd_hms":
            start = int(spec["reg"])
            count = int(spec.get("count", 3))
            words = words_for(start, count)
            if words is not None:
                state.clock = decode_bcd_hms(words)
            continue
        raw = raw_for(spec)
        if raw is None:
            continue
        value = decode_value(spec, raw, enums)
        if hasattr(state, key):
            setattr(state, key, value)
        else:
            state.extras[key] = value

    for key, spec in (profile.get("service_menu") or {}).get("params", {}).items():
        raw = raw_for(spec)
        if raw is None:
            continue
        state.extras[key] = decode_value(spec, raw, enums)

    state.hz_max = resolve_hz_max(profile, state.mode, state.extras)
    return state
