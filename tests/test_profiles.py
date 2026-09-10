from __future__ import annotations

import json
from pathlib import Path

import pytest

from spo_pool_heat_pump.profiles import (
    REQUIRED_TOP,
    ProfileError,
    choice_label,
    decode_bcd_hms,
    decode_faults,
    decode_value,
    encode_value,
    service_menu_params,
    iter_profiles,
    load_profile,
    migrate_profile_fields,
    profile_frames,
    profile_registers,
    resolve_hz_max,
    resolve_profile_id,
    validate_profile,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "custom_components/spo_pool_heat_pump/profiles"
SCHEMA = PROFILES / "schema.json"
STRINGS = ROOT / "custom_components/spo_pool_heat_pump/strings.json"


def test_no_removed_installer_entity_metadata() -> None:
    root = ROOT / "custom_components/spo_pool_heat_pump"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    icons = json.loads((root / "icons.json").read_text(encoding="utf-8"))
    entity = strings["entity"]
    assert "select" not in entity
    assert "installer_param" not in entity["sensor"]
    assert "installer_param" not in entity["number"]
    icon_entity = icons["entity"]
    assert "select" not in icon_entity
    assert "installer_param" not in icon_entity.get("sensor", {})
    assert "installer_param" not in icon_entity.get("number", {})


def test_strings_match_english_translation() -> None:
    root = ROOT / "custom_components/spo_pool_heat_pump"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    english = json.loads((root / "translations/en.json").read_text(encoding="utf-8"))
    assert strings == english


def test_schema_matches_loader_contract() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert set(schema["required"]) == set(REQUIRED_TOP)
    assert "map" not in schema["properties"]
    assert "capabilities" not in schema["properties"]
    assert schema["properties"]["registers"]["additionalProperties"]["additionalProperties"] is False
    assert schema["additionalProperties"] is False
    assert schema["properties"]["identity"]["properties"]["verification"]["enum"] == [
        "verified",
        "community",
        "experimental",
    ]
    assert schema["properties"]["driver"]["properties"]["type"]["enum"] == [
        "pc1002_bus",
        "poll_master",
        "listen_only",
    ]


def test_schema_rejects_kind() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    raw = json.loads((PROFILES / "mida_cosma_pc1002.json").read_text(encoding="utf-8"))
    raw["registers"]["setpoint"]["kind"] = "i16"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, schema)


def test_schema_rejects_pc1002_without_broadcast() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    raw = json.loads((PROFILES / "phnix_mini_pc1002.json").read_text(encoding="utf-8"))
    del raw["driver"]["broadcast"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, schema)


def test_all_profiles_validate() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    profiles = iter_profiles()
    ids = {p["identity"]["id"] for p in profiles}
    assert ids == {
        "mida_cosma_pc1002",
        "hayward_pc1002",
        "phnix_mini_pc1002",
        "fairland_pc1004_cn13",
        "fairland_ips_pro_coils",
        "unknown_dump_only",
    }
    for path in sorted(PROFILES.glob("*.json")):
        if path.name == "schema.json" or path.name.startswith("_"):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.validate(raw, schema)
        for leftover in ("map", "capabilities", "example_frames", "stopbits", "listen_only", "write_slave"):
            assert leftover not in raw, f"{path.name} still has {leftover}"
        for spec in (raw.get("registers") or {}).values():
            assert "kind" not in spec
            assert "bits_file" not in spec
            assert "params_file" not in spec
            file_name = spec.get("file")
            if file_name:
                assert (PROFILES / file_name).is_file()
        menu_file = (raw.get("service_menu") or {}).get("file")
        if menu_file:
            assert (PROFILES / menu_file).is_file()
    for p in profiles:
        validate_profile(p)
        if p["driver"]["type"] == "listen_only":
            assert p["identity"]["id"] == "unknown_dump_only"
            assert not profile_registers(p)
            continue
        assert profile_frames(p)
        if p["driver"]["type"] == "pc1002_bus":
            broadcast = p["driver"]["broadcast"]
            assert "start" in broadcast and "qty" in broadcast


def test_cn13_faults_are_not_cosma_booklet() -> None:
    spec = profile_registers(load_profile("fairland_pc1004_cn13"))["faults"]
    assert "file" not in spec
    assert not spec.get("bits")
    assert decode_faults({2074: 1 << 9}, spec) == ["2074.9"]


def test_pc1002_bus_requires_broadcast() -> None:
    profile = load_profile("phnix_mini_pc1002")
    del profile["driver"]["broadcast"]
    with pytest.raises(ProfileError, match="broadcast"):
        validate_profile(profile)


def test_identity_is_one_badge() -> None:
    cosmo = load_profile("mida_cosma_pc1002")["identity"]
    assert cosmo["id"] == "mida_cosma_pc1002"
    assert cosmo["brand"] == "MIDA"
    assert cosmo["model"] == "Cosma"
    assert cosmo["family"] == "pc1002"
    assert cosmo["oem"] == "PHNIX"
    assert cosmo["app"] == "AquaTemp"
    assert "/" not in cosmo["model"]
    hayward = load_profile("hayward_pc1002")["identity"]
    assert hayward["brand"] == "Hayward"
    assert hayward["model"] == "PC1002"
    assert "Warmpool" in hayward["also_sold_as"]
    assert "Oasis" in hayward["also_sold_as"]
    assert "Azuro" in cosmo["also_sold_as"]
    assert "Oasis" in choice_label(load_profile("hayward_pc1002"))
    assert "Azuro" in choice_label(load_profile("mida_cosma_pc1002"))
    assert "slave 50" in choice_label(load_profile("fairland_pc1004_cn13"))
    assert "dump only" in choice_label(load_profile("unknown_dump_only"))


def test_old_profile_ids_still_load() -> None:
    assert resolve_profile_id("cosmo_pc1002") == "mida_cosma_pc1002"
    assert load_profile("cosmo_pc1002")["identity"]["id"] == "mida_cosma_pc1002"
    data, options, changed = migrate_profile_fields({"profile": "phnix_mini_rs485"}, {})
    assert changed is True
    assert data["profile"] == "phnix_mini_pc1002"
    assert load_profile("fairland_legacy_coils")["identity"]["id"] == "fairland_ips_pro_coils"


def test_cosmo_mode_enum() -> None:
    p = load_profile("mida_cosma_pc1002")
    mode = profile_registers(p)["mode"]
    assert decode_value(mode, 1, p["enums"]) == "heat"
    assert encode_value(mode, "auto", p["enums"]) == 2


def test_cosmo_setpoint_28_encodes_280() -> None:
    p = load_profile("mida_cosma_pc1002")
    spec = profile_registers(p)["setpoint"]
    assert encode_value(spec, 28, p["enums"]) == 280
    assert decode_value(spec, 280, p["enums"]) == 28.0


def test_fairland_legacy_mode_inverted() -> None:
    p = load_profile("fairland_ips_pro_coils")
    mode = profile_registers(p)["mode"]
    assert decode_value(mode, 0, p["enums"]) == "auto"
    assert decode_value(mode, 2, p["enums"]) == "cool"


def test_fairland_temp_transform() -> None:
    spec = {"transform": "fairland_temp", "type": "u16"}
    assert decode_value(spec, 120, {}) == 30.0
    assert encode_value(spec, 30.0, {}) == 120


def test_silent_nonzero() -> None:
    spec = {"type": "bool", "nonzero": True}
    assert decode_value(spec, 256, {}) is True
    assert decode_value(spec, 0, {}) is False


def test_hz_max_from_h08() -> None:
    p = load_profile("mida_cosma_pc1002")
    assert resolve_hz_max(p, "heat", {}) == 90
    assert resolve_hz_max(p, "heat", {"h08_max_freq_heat": 80}) == 80
    assert resolve_hz_max(p, "cool", {"h09_max_freq_cool": 40}) == 40
    from spo_pool_heat_pump.drivers.decode import apply_map

    state = apply_map(p, {2012: 1, 2021: 40}, settings={1022: 80})
    assert state.hz_max == 80
    assert state.compressor_pct == 50


def test_bcd_hms_clock() -> None:
    assert decode_bcd_hms([0x15, 0x22, 0x30]) == "15:22:30"
    p = load_profile("mida_cosma_pc1002")
    from spo_pool_heat_pump.drivers.decode import apply_map

    state = apply_map(p, {}, settings={3015: 0x16, 3016: 0x21, 3017: 0x00})
    assert state.clock == "16:21:00"


def _hex_frame(text: str) -> bool:
    parts = text.split()
    return bool(parts) and all(len(p) == 2 and all(c in "0123456789ABCDEF" for c in p.upper()) for p in parts)


def test_all_example_frames_crc() -> None:
    from spo_pool_heat_pump.modbus_rtu import crc_ok, hex_to_bytes

    for profile in iter_profiles():
        for name, hex_s in profile_frames(profile).items():
            if not isinstance(hex_s, str) or not _hex_frame(hex_s):
                continue
            assert crc_ok(hex_to_bytes(hex_s)), f"{profile['identity']['id']} {name}"


def test_service_menu_writable_has_bounds() -> None:
    params = service_menu_params(load_profile("mida_cosma_pc1002"))
    for key, spec in params.items():
        if not spec.get("writable"):
            continue
        assert spec.get("label"), key
        assert spec.get("min") is not None, key
        assert spec.get("max") is not None, key


HARDCODED_TRANSLATION_KEYS = {
    "climate": {"climate"},
    "sensor": {
        "inlet",
        "outlet",
        "ambient",
        "power",
        "energy_24h",
        "energy_total",
        "compressor",
        "compressor_hz",
        "fan",
        "coil",
        "exhaust",
        "fw_display",
        "fw_main",
        "fw_mini",
        "panel_clock",
        "cop_display",
    },
    "switch": {"silent", "silent_timer", "timer1_on", "timer1_off", "timer2_on", "timer2_off"},
    "number": {
        "silent_timer_start_h",
        "silent_timer_stop_h",
        "timer1_on_h",
        "timer1_on_min",
        "timer1_off_h",
        "timer1_off_min",
        "timer2_on_h",
        "timer2_on_min",
        "timer2_off_h",
        "timer2_off_min",
    },
    "binary_sensor": {"compressor_running", "pump_running", "fault"},
}


def test_profile_entity_keys_have_strings() -> None:
    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    entity = strings["entity"]
    for platform, keys in HARDCODED_TRANSLATION_KEYS.items():
        for key in keys:
            assert key in entity[platform], f"missing strings entity.{platform}.{key}"
    for profile in iter_profiles():
        for key, spec in profile_registers(profile).items():
            ent = spec.get("entity") or {}
            platform = ent.get("platform")
            if not platform:
                continue
            if platform == "binary_sensor" and spec.get("type") == "bits":
                for bit_name in spec.get("bits") or {}:
                    assert bit_name in entity["binary_sensor"], (
                        f"{profile['identity']['id']} binary_sensor.{bit_name}"
                    )
            else:
                assert key in entity[platform], f"{profile['identity']['id']} {platform}.{key}"


def test_cosmo_protocol_extras_present() -> None:
    regs = profile_registers(load_profile("mida_cosma_pc1002"))
    assert regs["t_suction"]["reg"] == 2045
    assert regs["switches"]["reg"] == 2034
    assert load_profile("mida_cosma_pc1002")["driver"]["power_also_write"] == [1014]
    flags = load_profile("mida_cosma_pc1002")["driver"]["settings"]["flags"]
    assert flags["reg"] == 3011
    assert flags["bits"]["4"] == 1001
