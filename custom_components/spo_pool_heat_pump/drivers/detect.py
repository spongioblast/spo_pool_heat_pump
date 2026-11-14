"""Listen the full window, then probe if silent. Returns (profile_id, extra).

``extra["slave99"]`` means DTU traffic was *heard* in the window. Its absence
is not proof there is no module — the DTU only speaks in bursts.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..const import DETECT_LISTEN_S
from ..modbus_rtu import encode_fc01, encode_fc03, parse_frame


class DetectFailed(Exception):
    """No CRC-valid broadcast and no probe answer."""


def _heard_words(extra: dict[str, Any]) -> dict[int, int]:
    words = dict(extra.get("broadcast") or {})
    for key, reg in (("fw_display", 2089), ("fw_main", 2084), ("fw_mini", 2017)):
        if extra.get(key) is not None:
            words.setdefault(reg, int(extra[key]))
    return words


def detect_reason(profile_id: str | None, extra: dict[str, Any]) -> str:
    """One-line why the picker is pre-selected."""
    from ..profiles import choice_map, detect_rule_matches, load_profile

    label = choice_map().get(profile_id or "", profile_id or "unknown")
    rule: dict[str, Any] = {}
    if profile_id:
        try:
            rule = (load_profile(profile_id).get("driver") or {}).get("detect") or {}
        except Exception:  # noqa: BLE001 - unknown id: no rule, generic text
            rule = {}
    words = _heard_words(extra)
    if "broadcast" in extra and detect_rule_matches(rule, words):
        named = sorted({*(rule.get("any") or {}), *(rule.get("all") or {}), *(rule.get("nonzero") or [])})
        shown = ", ".join(f"{reg}={words.get(int(reg), 0)}" for reg in named)
        why = f"Heard the 2001 broadcast; firmware words {shown} match this profile."
    elif "broadcast" in extra:
        why = "Heard a 2001 broadcast with other firmware. Default is the Hayward-family map."
    elif extra.get("slave50"):
        why = "Slave 50 answered a poll — Fairland/Norsup CN13."
    elif extra.get("slave1"):
        why = "Slave 1 answered a coil probe — older Fairland IPS Pro."
    elif extra.get("dump_only") or profile_id == "unknown_dump_only":
        why = "No matching broadcast or probe. Dump-only records the bus so you can add a real profile later."
    else:
        why = "Could not classify the bus; pick from the list."
    return f"Suggested: {label}. {why}"


async def detect_profile(
    client: Any,
    timeout: float = DETECT_LISTEN_S,
    probe_wait: float = 0.4,
) -> tuple[str, dict[str, Any]]:
    seen: dict[str, Any] = {}

    async def on_frame(frame: bytes) -> None:
        parsed = parse_frame(frame)
        if parsed is None:
            return
        if parsed.function == 16 and parsed.slave == 0 and parsed.start == 2001:
            regs = {2001 + i: v for i, v in enumerate(parsed.values)}
            seen["broadcast"] = regs
            seen["fw_display"] = regs.get(2089)
            seen["fw_main"] = regs.get(2084)
            seen["fw_mini"] = regs.get(2017)
        if parsed.slave == 99:
            seen["slave99"] = True
        if parsed.kind == "reply":
            if parsed.slave == 50:
                seen["slave50"] = True
            if parsed.slave == 1:
                seen["slave1"] = True

    await client.start(on_frame)
    try:
        # Listen for the whole window, not just until the first broadcast:
        # slave 99 (DTU) traffic is bursty and would otherwise be missed.
        await asyncio.sleep(timeout)
        if "broadcast" in seen:
            from ..profiles import match_broadcast_profile

            return match_broadcast_profile(seen["broadcast"]) or "hayward_pc1002", seen

        await client.send(encode_fc03(50, 1011, 3))
        await asyncio.sleep(probe_wait)
        if seen.get("slave50"):
            return "fairland_pc1004_cn13", seen
        await client.send(encode_fc01(1, 0, 1))
        await asyncio.sleep(probe_wait)
        if seen.get("slave1"):
            return "fairland_ips_pro_coils", seen
        seen["dump_only"] = True
        return "unknown_dump_only", seen
    finally:
        await client.stop()
