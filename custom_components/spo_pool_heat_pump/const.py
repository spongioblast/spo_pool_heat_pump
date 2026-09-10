"""Constants for the spo_pool_heat_pump integration."""

from __future__ import annotations

import copy

DOMAIN = "spo_pool_heat_pump"
DEFAULT_PORT = 8899
DEFAULT_NAME = "Pool heat pump"
STALE_SECONDS = 8.0
IDLE_FRAME_S = 0.020
SENSOR_PUBLISH_INTERVAL_S = 15.0
DETECT_LISTEN_S = 5.0
BROADCAST_START = 2001
BROADCAST_QTY = 90

CONF_PORT = "port"
CONF_HOST = "host"
CONF_PROFILE = "profile"
CONF_WRITE_PATH = "write_path"
CONF_POLL_INTERVAL = "poll_interval"
CONF_POLL_SLAVE = "poll_slave"
CONF_NAME = "name"
CONF_SERVICE_MENU_WRITES = "service_menu_writes"
CONF_MANUAL_COP_FLOW = "manual_cop_flow"
CONF_WATER_FLOW_M3H = "water_flow_m3h"

# Connection identity stays on ConfigEntry.data. Everything else is options.
ENTRY_OPTION_KEYS = (
    CONF_PROFILE,
    CONF_WRITE_PATH,
    CONF_POLL_INTERVAL,
    CONF_POLL_SLAVE,
    CONF_SERVICE_MENU_WRITES,
    CONF_MANUAL_COP_FLOW,
    CONF_WATER_FLOW_M3H,
)

RELOAD_OPTION_KEYS = (
    CONF_PROFILE,
    CONF_WRITE_PATH,
    CONF_POLL_INTERVAL,
    CONF_POLL_SLAVE,
    CONF_SERVICE_MENU_WRITES,
)

COP_KW_PER_M3H_K = 1.163
WATER_FLOW_MIN = 0.1
WATER_FLOW_MAX = 66.0

WRITE_PATH_DTU = "dtu_99"
WRITE_PATH_SLAVE2 = "slave2"
WRITE_PATH_PANEL = "panel_1"

PLATFORMS = ["climate", "sensor", "binary_sensor", "switch", "number"]


WRITE_PATH_LABELS = {
    WRITE_PATH_DTU: "DTU slave 99 (when the WiFi module is present)",
    WRITE_PATH_SLAVE2: "Slave 2 responder (no DTU / no WiFi module)",
    WRITE_PATH_PANEL: "Panel address 1 (unproven)",
}
WRITE_PATH_LABELS_SHORT = {
    WRITE_PATH_DTU: "DTU slave 99",
    WRITE_PATH_SLAVE2: "Slave 2 (no DTU / no WiFi module)",
    WRITE_PATH_PANEL: "Panel address 1 (unproven)",
}


def write_path_choices(profile: dict, *, short: bool = False) -> dict[str, str]:
    labels = WRITE_PATH_LABELS_SHORT if short else WRITE_PATH_LABELS
    targets = (profile.get("driver") or {}).get("write_targets") or [WRITE_PATH_DTU]
    return {key: labels[key] for key in targets if key in labels}


def suggested_write_path(driver_type: str, extra: dict) -> str:
    if extra.get("slave99"):
        return WRITE_PATH_DTU
    if driver_type == "pc1002_bus":
        return WRITE_PATH_SLAVE2
    return WRITE_PATH_DTU


def service_menu_writes_enabled(data: dict, options: dict | None = None) -> bool:
    opts = options or {}
    return bool(opts.get(CONF_SERVICE_MENU_WRITES, data.get(CONF_SERVICE_MENU_WRITES, False)))


def reload_option_fingerprint(data: dict, options: dict | None = None) -> tuple:
    opts = options or {}
    return tuple(opts.get(key, data.get(key)) for key in RELOAD_OPTION_KEYS)


def apply_runtime_overrides(profile: dict, data: dict, options: dict | None = None) -> dict:
    """Overlay entry options onto a loaded profile (poll slave / H37)."""
    opts = options or {}
    raw = opts.get(CONF_POLL_SLAVE, data.get(CONF_POLL_SLAVE))
    if raw is None or profile.get("driver", {}).get("type") != "poll_master":
        return profile
    slave = int(raw)
    profile = copy.deepcopy(profile)
    profile["driver"]["poll_slave"] = slave
    for spec in profile["driver"].get("reads") or []:
        spec["slave"] = slave
    menu = profile.get("service_menu")
    if menu:
        menu.setdefault("read", {})["slave"] = slave
    return profile


def migrate_entry_storage(data: dict, options: dict | None = None) -> tuple[dict, dict, bool]:
    """Move settings out of data into options. Keep host/port in data."""
    new_data = dict(data)
    new_options = dict(options or {})
    changed = False
    for key in ENTRY_OPTION_KEYS:
        if key in new_data:
            if key not in new_options:
                new_options[key] = new_data[key]
            new_data.pop(key, None)
            changed = True
    if CONF_NAME in new_data:
        new_data.pop(CONF_NAME, None)
        changed = True
    return new_data, new_options, changed


def merge_entry_options(data: dict, options: dict, user_input: dict) -> dict:
    """Keep poll-slave / interval only on poll_master profiles; reset them when the profile changes."""
    from .profiles import load_profile, resolve_profile_id

    merged = {**options, **user_input}
    selected = resolve_profile_id(merged.get(CONF_PROFILE) or data.get(CONF_PROFILE))
    previous = resolve_profile_id(options.get(CONF_PROFILE) or data.get(CONF_PROFILE))
    profile = load_profile(selected)
    if profile["driver"]["type"] != "poll_master":
        merged.pop(CONF_POLL_SLAVE, None)
        merged.pop(CONF_POLL_INTERVAL, None)
        if profile["driver"]["type"] == "listen_only":
            merged.pop(CONF_WRITE_PATH, None)
        return merged
    if selected != previous:
        merged[CONF_POLL_SLAVE] = int(profile["driver"].get("poll_slave", 1))
        merged[CONF_POLL_INTERVAL] = int(profile["driver"].get("poll_interval", 10))
    elif CONF_POLL_SLAVE not in user_input:
        merged[CONF_POLL_SLAVE] = int(profile["driver"].get("poll_slave", 1))
    merged.pop(CONF_WRITE_PATH, None)
    return merged

PRESET_SILENT = "silent"

CARD_URL_PATH = "/spo_pool_heat_pump/spo-pool-heat-pump-card.js"
CARD_STATIC_DIR = "/spo_pool_heat_pump"
