"""Listen 5 s, then probe. Returns (profile_id, extra)."""

from __future__ import annotations

import asyncio
from typing import Any

from ..const import DETECT_LISTEN_S
from ..modbus_rtu import encode_fc01, encode_fc03, parse_frame


class DetectFailed(Exception):
    """No CRC-valid broadcast and no probe answer."""


def detect_reason(profile_id: str | None, extra: dict[str, Any]) -> str:
    """One-line why the picker is pre-selected."""
    from ..profiles import choice_map

    label = choice_map().get(profile_id or "", profile_id or "unknown")
    if extra.get("fw_display") == 713 or extra.get("fw_main") == 772:
        why = "Heard the 2001 broadcast; firmware 713/772 matches MIDA Cosma."
    elif extra.get("fw_mini") and not extra.get("fw_display"):
        why = "Mini firmware at register 2017 — PHNIX Mini layout."
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
    got = asyncio.Event()

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
            got.set()
        if parsed.slave == 99:
            seen["slave99"] = True
        if parsed.kind == "reply":
            if parsed.slave == 50:
                seen["slave50"] = True
            if parsed.slave == 1:
                seen["slave1"] = True

    await client.start(on_frame)
    try:
        try:
            await asyncio.wait_for(got.wait(), timeout)
        except TimeoutError:
            pass
        if "broadcast" in seen:
            display, main, mini = seen.get("fw_display"), seen.get("fw_main"), seen.get("fw_mini")
            if mini and not display:
                return "phnix_mini_pc1002", seen
            if display == 713 or main == 772:
                return "mida_cosma_pc1002", seen
            return "hayward_pc1002", seen

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
