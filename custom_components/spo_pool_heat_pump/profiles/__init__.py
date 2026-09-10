"""Profile loader — JSON is data, not code."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROFILES_DIR = Path(__file__).resolve().parent

# Filename = {brand}_{product}_{family}. Old ids still load.
PROFILE_ALIASES = {
    "cosmo_pc1002": "mida_cosma_pc1002",
    "phnix_mini_rs485": "phnix_mini_pc1002",
    "fairland_legacy_coils": "fairland_ips_pro_coils",
}

REQUIRED_TOP = ("identity", "link", "driver", "modes", "enums", "registers")
REQUIRED_IDENTITY = ("id", "brand", "model", "verification")
CORE_KEYS = {
    "power",
    "mode",
    "setpoint",
    "setpoint_heat",
    "setpoint_cool",
    "setpoint_auto",
    "silent",
    "t_inlet",
    "t_outlet",
    "t_ambient",
    "comp_hz",
    "power_kw",
    "energy_24h_kwh",
    "fan_rpm",
    "outputs",
    "faults",
    "serial",
    "fw_display",
    "fw_main",
    "clock",
}


class ProfileError(ValueError):
    pass


def _require(obj: dict, keys: tuple[str, ...], where: str) -> None:
    missing = [k for k in keys if k not in obj]
    if missing:
        raise ProfileError(f"{where} missing {missing}")


def resolve_profile_id(profile_id: str) -> str:
    return PROFILE_ALIASES.get(profile_id, profile_id)


def migrate_profile_fields(data: dict[str, Any], options: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Rewrite stored profile ids to the current filename id."""
    new_data = dict(data)
    new_options = dict(options or {})
    changed = False
    for store in (new_data, new_options):
        old = store.get("profile")
        if not old:
            continue
        canon = resolve_profile_id(str(old))
        if canon != old:
            store["profile"] = canon
            changed = True
    return new_data, new_options, changed


def load_profile(profile_id: str) -> dict[str, Any]:
    profile_id = resolve_profile_id(profile_id)
    path = PROFILES_DIR / f"{profile_id}.json"
    if not path.exists() or not _is_profile_path(path):
        raise ProfileError(f"unknown profile {profile_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    _resolve_service_menu(data)
    _resolve_faults(data)
    validate_profile(data)
    ident_id = data["identity"]["id"]
    if ident_id != profile_id:
        raise ProfileError(f"identity.id {ident_id} != file {profile_id}")
    return data


def _is_profile_path(path: Path) -> bool:
    return path.suffix == ".json" and path.name != "schema.json" and not path.name.startswith("_")


FORBIDDEN_TOP = ("map", "capabilities", "example_frames", "poll", "stopbits")


def profile_registers(profile: dict[str, Any]) -> dict[str, Any]:
    return profile.get("registers") or profile.get("map") or {}


def profile_polls(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return list(profile.get("driver", {}).get("reads") or profile.get("poll") or [])


def profile_frames(profile: dict[str, Any]) -> dict[str, Any]:
    fixtures = profile.get("fixtures") or {}
    return fixtures.get("frames") or profile.get("example_frames") or {}


def is_bool_spec(spec: dict[str, Any]) -> bool:
    return spec.get("type") == "bool" or spec.get("kind") in ("bool", "bool_nonzero")


def resolve_hz_max(profile: dict[str, Any], mode: str, extras: dict[str, Any]) -> int:
    hz = profile.get("hz_max") or {}
    if not isinstance(hz, dict):
        return 90
    named = hz.get(mode)
    if isinstance(named, str) and named in extras:
        try:
            return int(extras[named])
        except (TypeError, ValueError):
            pass
    default = hz.get("default") if isinstance(hz.get("default"), dict) else hz
    if isinstance(default, dict):
        value = default.get(mode, default.get("heat", 90))
        if isinstance(value, (int, float)):
            return int(value)
    return 90


def _resolve_service_menu(data: dict[str, Any]) -> None:
    block = data.get("service_menu")
    settings = (data.get("driver") or {}).get("settings") or {}
    if not block and not settings:
        return
    block = dict(block or {})
    data["service_menu"] = block
    params_file = block.get("file")
    if params_file:
        raw = json.loads((PROFILES_DIR / params_file).read_text(encoding="utf-8"))
        merged = dict(raw)
        merged.update(block.get("overrides") or {})
        block["params"] = merged
    if settings.get("pages"):
        block["pages"] = settings["pages"]
        block.setdefault(
            "read",
            {
                "slave": settings.get("slave", 1),
                "idle_s": settings.get("idle_s", 0.05),
                "timeout_s": settings.get("timeout_s", 0.8),
            },
        )


def _resolve_faults(data: dict[str, Any]) -> None:
    spec = profile_registers(data).get("faults")
    if not isinstance(spec, dict):
        return
    bits: dict[str, Any] = {}
    fname = spec.get("file") or spec.get("bits_file") or spec.get("meanings_file")
    if fname:
        raw = json.loads((PROFILES_DIR / fname).read_text(encoding="utf-8"))
        if isinstance(raw.get("bits"), dict):
            bits.update({k: v for k, v in raw["bits"].items() if not str(k).startswith("_")})
        else:
            bits.update({k: v for k, v in raw.items() if not str(k).startswith("_")})
        if isinstance(raw.get("booklet"), dict):
            spec["booklet"] = raw["booklet"]
        if isinstance(raw.get("aliases"), dict):
            spec["aliases"] = raw["aliases"]
    bits.update(spec.get("bits") or {})
    spec["bits"] = bits
    codes: dict[str, str] = {}
    meanings: dict[str, str] = {}
    sources: dict[str, str] = {}
    for key, val in bits.items():
        if isinstance(val, dict):
            code = str(val.get("code") or key)
            codes[key] = code
            if val.get("text"):
                meanings[code] = str(val["text"])
            if val.get("source"):
                sources[code] = str(val["source"])
        elif isinstance(val, str) and "." in key:
            codes[key] = val
        elif isinstance(val, str):
            meanings[key] = val
    for key, val in (spec.get("codes") or {}).items():
        if isinstance(val, str):
            codes.setdefault(key, val)
        elif isinstance(val, dict) and val.get("code"):
            codes.setdefault(key, str(val["code"]))
    meanings.update(spec.get("meanings") or {})
    for code, row in (spec.get("booklet") or {}).items():
        if isinstance(row, dict) and row.get("text"):
            meanings.setdefault(str(code), str(row["text"]))
    spec["codes"] = codes
    spec["meanings"] = meanings
    spec["sources"] = sources


def choice_label(profile: dict[str, Any]) -> str:
    """Dropdown text: badge, aliases, how it talks, verification."""
    ident = profile["identity"]
    name = f"{ident['brand']} {ident['model']}"
    also = ident.get("also_sold_as") or []
    if also:
        name += " — also " + ", ".join(also)
    fam = ident.get("family")
    if profile["driver"]["type"] == "listen_only":
        return "Unknown heat pump — dump only (experimental)"
    if fam == "pc1004":
        name += " · slave 50"
    elif fam == "fairland_coils":
        name += " · coil map"
    return f"{name} ({ident['verification']})"


def choice_map() -> dict[str, str]:
    return {p["identity"]["id"]: choice_label(p) for p in iter_profiles()}


def iter_profiles() -> list[dict[str, Any]]:
    out = []
    for path in sorted(PROFILES_DIR.glob("*.json")):
        if not _is_profile_path(path):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        _resolve_service_menu(data)
        _resolve_faults(data)
        validate_profile(data)
        out.append(data)
    return out


def profiles_for_driver(driver: str) -> list[dict[str, Any]]:
    return [p for p in iter_profiles() if p["driver"]["type"] == driver]


def validate_profile(data: dict[str, Any]) -> None:
    leftover = [k for k in FORBIDDEN_TOP if k in data]
    if leftover:
        raise ProfileError(f"v1 keys still present {leftover}")
    _require(data, REQUIRED_TOP, "profile")
    _require(data["identity"], REQUIRED_IDENTITY, "identity")
    if data["identity"]["verification"] not in ("verified", "community", "experimental"):
        raise ProfileError("identity.verification")
    if data["driver"]["type"] not in ("pc1002_bus", "poll_master", "listen_only"):
        raise ProfileError("driver.type")
    for key, spec in profile_registers(data).items():
        if not isinstance(spec, dict):
            raise ProfileError(f"register {key} is not an object")
        if "kind" in spec:
            raise ProfileError(f"register {key} uses kind; use type")
        if spec.get("type") not in (
            "u16",
            "i16",
            "bool",
            "enum",
            "bits",
            "faults",
            "ascii",
            "bcd_hms",
            None,
        ):
            raise ProfileError(f"register {key} type {spec.get('type')}")
    menu = data.get("service_menu")
    if menu and menu.get("params"):
        params = menu["params"]
        overlap = set(params) & CORE_KEYS
        if overlap:
            raise ProfileError(f"service_menu keys collide with registers {overlap}")
        for key, spec in params.items():
            if "reg" not in spec:
                raise ProfileError(f"service_menu {key} missing reg")
    if data["driver"]["type"] == "pc1002_bus":
        broadcast = (data.get("driver") or {}).get("broadcast") or {}
        if "start" not in broadcast or "qty" not in broadcast:
            raise ProfileError("pc1002_bus missing driver.broadcast start/qty")
        if menu and not menu.get("pages"):
            raise ProfileError("service_menu missing pages")


def service_menu_params(profile: dict[str, Any]) -> dict[str, Any]:
    return (profile.get("service_menu") or {}).get("params") or {}


def lookup_write_spec(profile: dict[str, Any], name: str) -> dict[str, Any]:
    spec = profile_registers(profile).get(name)
    if spec:
        return spec
    spec = service_menu_params(profile).get(name)
    if spec:
        return spec
    raise KeyError(name)


def write_address(spec: dict[str, Any]) -> int:
    if "write" in spec:
        return int(spec["write"])
    return int(spec["reg"])


def validate_service_menu_write(profile: dict[str, Any], enabled: bool, key: str) -> dict[str, Any]:
    if not enabled:
        raise PermissionError("service menu writes disabled")
    spec = service_menu_params(profile).get(key)
    if not spec or not spec.get("writable"):
        raise KeyError(key)
    return spec


def decode_value(spec: dict[str, Any], raw: int, enums: dict[str, dict[str, str]]) -> Any:
    if spec.get("transform") == "fairland_temp":
        return (raw - 96) / 2 + 18
    if is_bool_spec(spec):
        if spec.get("nonzero") or spec.get("kind") == "bool_nonzero":
            return raw != 0
        return bool(raw)
    enum_name = spec.get("enum")
    if spec.get("type") == "enum" or enum_name:
        table = enums.get(enum_name or "", {})
        return table.get(str(int(raw)), str(int(raw)))
    signed = spec.get("type") == "i16" or spec.get("signed", False)
    value: float | int = raw - 65536 if signed and raw >= 32768 else raw
    scale = spec.get("scale", 1)
    if scale and scale != 1:
        value = value * scale
    return value


def encode_value(spec: dict[str, Any], value: Any, enums: dict[str, dict[str, str]]) -> int:
    enum_name = spec.get("enum")
    if spec.get("type") == "enum" or enum_name:
        table = enums.get(enum_name or "", {})
        inv = {v: int(k) for k, v in table.items()}
        if value in inv:
            return inv[value]
        return int(value)
    if is_bool_spec(spec):
        return 1 if value else 0
    if spec.get("transform") == "fairland_temp":
        return int(round((float(value) - 18) * 2 + 96))
    scale = spec.get("scale", 1)
    if scale and scale != 1:
        return int(round(float(value) / scale))
    return int(value)


def decode_bcd_hms(words: list[int]) -> str | None:
    if len(words) < 3:
        return None
    parts: list[str] = []
    for raw in words[:3]:
        lo = int(raw) & 0xFF
        tens, ones = (lo >> 4) & 0xF, lo & 0xF
        if tens > 9 or ones > 9:
            return None
        parts.append(f"{tens * 10 + ones:02d}")
    return ":".join(parts)


def decode_panel_clock(page: list[int] | None) -> str | None:
    if not page or len(page) < 17:
        return None
    return decode_bcd_hms(page[14:17])


def decode_serial(regs: list[int], start: int = 0, count: int = 7) -> str:
    raw = b"".join(int(r).to_bytes(2, "big") for r in regs[start : start + count])
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace")


def decode_outputs(raw: int, bits: dict[str, int]) -> dict[str, bool]:
    return {name: bool(raw & (1 << bit)) for name, bit in bits.items()}


def _fault_bit_entries(spec: dict[str, Any]) -> list[tuple[int, int, str]]:
    entries: list[tuple[int, int, str]] = []
    for key, label in (spec.get("codes") or {}).items():
        if isinstance(label, dict):
            label = label.get("code") or key
        reg_s, _, bit_s = key.partition(".")
        if not bit_s:
            continue
        entries.append((int(reg_s), int(bit_s), str(label)))
    entries.sort()
    return entries


def decode_faults(words: dict[int, int], spec: dict[str, Any]) -> list[str]:
    found: list[str] = []
    mapped: set[tuple[int, int]] = set()
    for reg, bit, label in _fault_bit_entries(spec):
        mapped.add((reg, bit))
        if words.get(reg, 0) & (1 << bit):
            found.append(label)
    leftovers: list[str] = []
    for reg, word in words.items():
        if not word:
            continue
        for bit in range(16):
            if word & (1 << bit) and (int(reg), bit) not in mapped:
                leftovers.append(f"{reg}.{bit}")
    if found or leftovers:
        return found + leftovers
    return []


def _alias_code(code: str, spec: dict[str, Any]) -> str:
    aliases = spec.get("aliases") or {}
    return str(aliases.get(code, code))


def fault_meanings(codes: list[str], spec: dict[str, Any]) -> list[str]:
    table = spec.get("meanings") or {}
    out: list[str] = []
    for code in codes:
        key = _alias_code(code, spec)
        out.append(str(table.get(code) or table.get(key) or ""))
    return out


def fault_source(code: str, spec: dict[str, Any]) -> str | None:
    sources = spec.get("sources") or {}
    return sources.get(code) or sources.get(_alias_code(code, spec))


def booklet_unmapped(spec: dict[str, Any]) -> list[str]:
    booklet = spec.get("booklet") or {}
    return [code for code, row in booklet.items() if isinstance(row, dict) and not row.get("bit")]
