"""Keep shipped pc1002 registers honest against the Cosma lab notebook."""

from __future__ import annotations

import json

from spo_pool_heat_pump.profiles import iter_profiles, profile_registers

from conftest import HA_ROOT, HAS_PROTOCOL, PROTOCOL as PROTOCOL_PATH, requires_protocol

PROTOCOL = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8")) if HAS_PROTOCOL else {}
NOTEBOOK = PROTOCOL.get("registers") or {}


def _addrs(spec: dict) -> list[int]:
    addrs: list[int] = []
    if "reg" in spec:
        start = int(spec["reg"])
        count = int(spec.get("count") or 1)
        addrs.extend(start + i for i in range(count if spec.get("type") in ("ascii", "bcd_hms") else 1))
    if "write" in spec:
        addrs.append(int(spec["write"]))
    addrs.extend(int(r) for r in spec.get("regs") or [])
    return addrs


def _check_addr(profile_id: str, key: str, addr: int, spec: dict, verified_only: bool) -> None:
    row = NOTEBOOK.get(str(addr))
    assert row, f"{profile_id} {key} {addr} missing from protocol.json"
    if verified_only:
        allowed = ("verified",) if spec.get("type") != "faults" else ("verified", "oem_family")
        assert row.get("confidence") in allowed, (
            f"{profile_id} {key} {addr} cites {row.get('confidence')}"
        )
    if "scale" in spec and "scale" in row:
        assert float(row["scale"]) == float(spec["scale"]), f"{key} {addr} scale"
    proto_unit = row.get("unit")
    prof_unit = spec.get("unit")
    if proto_unit and prof_unit:
        assert proto_unit == prof_unit, f"{key} {addr} unit"
    if row.get("type") == "bitfield":
        assert spec.get("type") == "bits", f"{key} {addr} should be bits"


def test_protocol_json_not_shipped() -> None:
    shipped = HA_ROOT / "custom_components/spo_pool_heat_pump"
    assert not (shipped / "protocol.json").exists()
    assert not list(shipped.rglob("protocol.json"))


@requires_protocol
def test_pc1002_registers_bind_to_protocol() -> None:
    for profile in iter_profiles():
        if profile["identity"].get("family") != "pc1002":
            continue
        ident = profile["identity"]["id"]
        verified_only = profile["identity"]["verification"] == "verified"
        for key, spec in profile_registers(profile).items():
            for addr in _addrs(spec):
                _check_addr(ident, key, addr, spec, verified_only)
        for addr in profile.get("driver", {}).get("power_also_write") or []:
            _check_addr(ident, "power_also_write", int(addr), {}, verified_only)
