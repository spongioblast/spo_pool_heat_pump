"""One-shot v1 → v2 profile converter. Not shipped in the integration."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "custom_components/spo_pool_heat_pump/profiles"


def spec_v2(key: str, spec: dict) -> dict:
    out = {k: v for k, v in spec.items() if k not in ("kind", "signed", "bits_file", "meanings_file")}
    kind = spec.get("kind")
    if kind == "bool":
        out["type"] = "bool"
    elif kind == "bool_nonzero":
        out["type"] = "bool"
        out["nonzero"] = True
    elif kind == "serial":
        out["type"] = "ascii"
        out.setdefault("count", 7)
    elif spec.get("enum"):
        out["type"] = "enum"
    elif key == "outputs" or spec.get("bits"):
        out["type"] = "bits"
        if spec.get("bits"):
            out["bits"] = spec["bits"]
    elif key == "faults":
        out["type"] = "faults"
        fname = spec.get("bits_file") or spec.get("file") or spec.get("meanings_file")
        if fname:
            out["file"] = fname
        if spec.get("regs") is not None:
            out["regs"] = spec["regs"]
        if spec.get("codes"):
            out["codes"] = spec["codes"]
    elif spec.get("transform") == "fairland_temp":
        out.setdefault("type", "u16")
    elif spec.get("signed") or spec.get("type") == "i16":
        out["type"] = "i16"
    else:
        out.setdefault("type", "u16")
    return out


def convert_profile(raw: dict) -> dict:
    ident = dict(raw["identity"])
    driver = dict(raw["driver"])
    if "display" in (driver.get("detect") or {}):
        det = dict(driver["detect"])
        if "display" in det:
            det["fw_display"] = det.pop("display")
        if "main" in det:
            det["fw_main"] = det.pop("main")
        driver["detect"] = det
    if raw["driver"]["type"] == "pc1002_bus" and raw.get("installer"):
        inst = raw["installer"]
        pages = list(inst.get("pages") or [])
        if not any(p.get("start") == 3001 for p in pages):
            pages = pages + [{"start": 3001, "qty": 30}]
        driver["broadcast"] = {"start": 2001, "qty": 90}
        driver["settings"] = {
            "slave": int((inst.get("read") or {}).get("slave", 1)),
            "pages": pages,
            "idle_s": (inst.get("read") or {}).get("idle_s", 0.05),
            "timeout_s": (inst.get("read") or {}).get("timeout_s", 0.8),
        }
    if raw.get("poll"):
        driver["reads"] = raw["poll"]
    registers = {key: spec_v2(key, spec) for key, spec in raw["map"].items()}
    caps = raw.get("capabilities") or {}
    modes = ["heat"]
    if caps.get("cool"):
        modes.append("cool")
    if caps.get("auto"):
        modes.append("auto")
    hz = raw.get("hz_max")
    if isinstance(hz, dict) and "default" not in hz:
        hz = {
            "heat": "h08_max_freq_heat",
            "cool": "h09_max_freq_cool",
            "default": hz,
        }
    out: dict = {
        "identity": ident,
        "link": {
            "baud": raw["link"]["baud"],
            "parity": raw["link"]["parity"],
            "stop_bits": raw["link"].get("stop_bits") or raw["link"].get("stopbits") or 1,
            "slaves": raw["link"].get("slaves") or {},
        },
        "driver": driver,
        "modes": modes,
        "enums": raw.get("enums") or {},
        "registers": registers,
    }
    if raw.get("installer"):
        inst = raw["installer"]
        out["service_menu"] = {"file": inst.get("params_file") or inst.get("file") or "_service_menu_pc1002.json"}
        if inst.get("params"):
            out["service_menu"]["overrides"] = inst["params"]
    if hz:
        out["hz_max"] = hz
    frames = {k: v for k, v in (raw.get("example_frames") or {}).items() if k != "note" and " " in str(v)}
    out["fixtures"] = {"frames": frames}
    if "dumps/" in ident.get("source", ""):
        out["fixtures"]["dump"] = "protocol-analysis/dumps/20260906_104432"
    note = (raw.get("example_frames") or {}).get("note")
    if note:
        out["notes"] = note
    return out


def main() -> None:
    for path in sorted(PROFILES.glob("*.json")):
        if path.name.startswith("_") or path.name == "schema.json":
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if "registers" in raw:
            continue
        converted = convert_profile(raw)
        path.write_text(json.dumps(converted, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("converted", path.name)


if __name__ == "__main__":
    main()
