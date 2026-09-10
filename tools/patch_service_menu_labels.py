"""Add label / min / max / default to service-menu catalog rows."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "custom_components/spo_pool_heat_pump/profiles/_service_menu_pc1002.json"

# Observed Cosma dump values (raw). Used as default when present.
OBS = {
    1020: 25, 1021: 25, 1022: 90, 1023: 55, 1024: 20, 1135: 270, 1136: 310,
    1137: 310, 1140: 80, 1141: 350, 1142: 150, 1143: 350, 1145: 0,
}


def bounds(spec: dict) -> tuple[float, float]:
    unit = spec.get("unit") or ""
    if spec.get("min") is not None and spec.get("max") is not None:
        return float(spec["min"]), float(spec["max"])
    if unit in ("°C", "C"):
        return -30, 80
    if unit == "Hz":
        return 0, 120
    if unit == "bar":
        return 0, 50
    if unit == "h":
        return 0, 23
    if unit == "min":
        return 0, 600
    if unit == "rpm":
        return 0, 2000
    if unit == "A":
        return 0, 50
    return -1000, 10000


def label_for(key: str, spec: dict) -> str:
    if spec.get("label"):
        return str(spec["label"])
    rest = key.split("_", 1)[1] if "_" in key else key
    return rest.replace("_", " ")


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    for key, spec in data.items():
        if not isinstance(spec, dict) or key.startswith("_"):
            continue
        spec["label"] = label_for(key, spec)
        if spec.get("writable"):
            lo, hi = bounds(spec)
            spec.setdefault("min", lo)
            spec.setdefault("max", hi)
            reg = spec.get("reg")
            scale = float(spec.get("scale") or 1)
            if reg in OBS:
                raw = OBS[reg]
                spec.setdefault("default", raw * scale if scale != 1 else raw)
            spec.setdefault("type", "i16" if spec.get("signed") else "u16")
    PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("patched", PATH.name)


if __name__ == "__main__":
    main()
