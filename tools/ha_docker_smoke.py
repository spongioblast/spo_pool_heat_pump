"""Onboard the throwaway HA and add spo_pool_heat_pump against the dump replay."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = os.environ.get("HA_HOST", "127.0.0.1")
PORT = int(os.environ.get("HA_PORT", "8124"))
BASE = f"http://{HOST}:{PORT}"
CLIENT_ID = f"{BASE}/"
USER = "dev"
PASSWORD = "dev-spo"


def _json(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict | list:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Origin": BASE},
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def wait_http(timeout: float = 180) -> None:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/api/onboarding", timeout=5) as resp:
                if resp.status == 200:
                    print("HA HTTP is up")
                    return
        except Exception as err:  # noqa: BLE001
            last = str(err)
        time.sleep(2)
    raise SystemExit(f"HA did not become ready: {last}")


def _onboarding_steps() -> dict[str, bool]:
    try:
        status = _json("GET", "/api/onboarding")
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return {"user": True, "core_config": True, "analytics": True, "integration": True}
        raise
    if isinstance(status, list):
        return {str(row.get("step")): bool(row.get("done")) for row in status}
    if isinstance(status, dict) and status.get("done") is True:
        return {"user": True, "core_config": True, "analytics": True, "integration": True}
    return {}


def onboard() -> str:
    steps = _onboarding_steps()
    if steps.get("user"):
        print("onboarding user already exists")
        token = login()
    else:
        user = _json(
            "POST",
            "/api/onboarding/users",
            {
                "client_id": CLIENT_ID,
                "name": "Dev",
                "username": USER,
                "password": PASSWORD,
                "language": "en",
            },
        )
        if user.get("auth_code"):
            token = exchange(user["auth_code"])
        else:
            token = user.get("access_token") or login()
    remaining = {
        "core_config": (
            "/api/onboarding/core_config",
            {
                "client_id": CLIENT_ID,
                "latitude": 52.52,
                "longitude": 13.405,
                "elevation": 0,
                "unit_system": "metric",
                "location_name": "SPO test",
                "time_zone": "Europe/Berlin",
                "currency": "EUR",
                "country": "DE",
            },
        ),
        "analytics": ("/api/onboarding/analytics", {"client_id": CLIENT_ID}),
        "integration": (
            "/api/onboarding/integration",
            {"client_id": CLIENT_ID, "redirect_uri": CLIENT_ID},
        ),
    }
    for step, (path, body) in remaining.items():
        if steps.get(step):
            continue
        try:
            _json("POST", path, body, token=token)
        except urllib.error.HTTPError as err:
            print(f"{path} -> {err.code} {err.read()[:300]!r}")
    return token if _looks_like_jwt(token) else login()


def _looks_like_jwt(token: str) -> bool:
    return token.count(".") >= 2 or len(token) > 40


def exchange(auth_code: str) -> str:
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": CLIENT_ID,
        }
    ).encode()
    req = urllib.request.Request(
        BASE + "/auth/token",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        out = json.loads(resp.read())
    return str(out["access_token"])


def login() -> str:
    flow = _json(
        "POST",
        "/auth/login_flow",
        {
            "client_id": CLIENT_ID,
            "handler": ["homeassistant", None],
            "redirect_uri": CLIENT_ID,
        },
    )
    flow_id = flow["flow_id"]
    result = _json(
        "POST",
        f"/auth/login_flow/{flow_id}",
        {"username": USER, "password": PASSWORD, "client_id": CLIENT_ID},
    )
    if "result" not in result:
        raise SystemExit(f"login failed: {result}")
    return exchange(result["result"])


def rest_flow(token: str) -> None:
    created = _json(
        "POST",
        "/api/config/config_entries/flow",
        {"handler": "spo_pool_heat_pump", "show_advanced_options": False},
        token=token,
    )
    flow_id = created["flow_id"]
    print("flow", created.get("step_id"), created.get("type"))
    result = created
    for user_input in (
        {"host": "replay", "port": 8899},
        {"profile": "mida_cosma_pc1002"},
        {"name": "Pool heat pump", "write_path": "dtu_99", "service_menu_writes": False},
    ):
        result = _json(
            "POST",
            f"/api/config/config_entries/flow/{flow_id}",
            user_input,
            token=token,
        )
        print("step", result.get("step_id") or result.get("type"), result.get("title") or "")
        if result.get("type") == "create_entry":
            break
        if result.get("type") == "abort":
            raise SystemExit(f"flow aborted: {result}")
        if result.get("errors"):
            raise SystemExit(f"flow errors: {result}")
    time.sleep(4)
    states = _json("GET", "/api/states", token=token)
    if not isinstance(states, list):
        raise SystemExit(f"states failed: {states}")
    entities = [
        s["entity_id"]
        for s in states
        if str(s.get("entity_id", "")).startswith(("climate.pool", "sensor.pool", "binary_sensor.pool", "switch.pool"))
    ]
    print("entities", len(entities))
    for eid in sorted(entities)[:24]:
        print(" ", eid)
    climate = next((s for s in states if str(s.get("entity_id", "")).startswith("climate.pool")), None)
    if climate:
        print("climate", climate.get("state"), climate.get("attributes", {}).get("current_temperature"))
    if not entities:
        raise SystemExit("integration added but no pool_* entities yet")


def main() -> None:
    wait_http()
    token = onboard()
    print("token ok")
    rest_flow(token)


if __name__ == "__main__":
    main()
