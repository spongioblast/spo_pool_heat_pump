"""One-shot onboard + add SPO Pool Heat Pump against the local docker HA."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:18123"
CLIENT = f"{BASE}/"


def req(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict | str]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            raw = resp.read()
            text = raw.decode()
            if not text:
                return resp.status, {}
            try:
                return resp.status, json.loads(text)
            except json.JSONDecodeError:
                return resp.status, text
    except urllib.error.HTTPError as err:
        raw = err.read().decode()
        try:
            return err.code, json.loads(raw)
        except json.JSONDecodeError:
            return err.code, raw


def token_from_code(code: str) -> str:
    body = (
        f"grant_type=authorization_code&code={code}&client_id={CLIENT}"
    ).encode()
    request = urllib.request.Request(
        BASE + "/auth/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    return payload["access_token"]


def main() -> int:
    status, onboard = req("GET", "/api/onboarding")
    print("onboarding", status, onboard)
    needs_user = False
    if status == 200 and isinstance(onboard, list):
        needs_user = any(step.get("step") == "user" and not step.get("done") for step in onboard)
    elif status == 200 and isinstance(onboard, dict):
        needs_user = not onboard.get("onboarded", True)
    if needs_user:
        status, users = req(
            "POST",
            "/api/onboarding/users",
            {
                "client_id": CLIENT,
                "name": "Owner",
                "username": "admin",
                "password": "adminadmin",
                "language": "en",
            },
        )
        print("users", status, users)
        if status != 200:
            return 1
        token = token_from_code(users["auth_code"])
        status, core = req(
            "POST",
            "/api/onboarding/core_config",
            {
                "client_id": CLIENT,
                "location_name": "Home",
                "language": "en",
                "country": "DE",
                "timezone": "Europe/Berlin",
                "currency": "EUR",
                "unit_system": "metric",
            },
            token,
        )
        print("core_config", status, core)
        status, analytics = req("POST", "/api/onboarding/analytics", {}, token)
        print("analytics", status, analytics)
        status, integ = req("POST", "/api/onboarding/integration", {"client_id": CLIENT}, token)
        print("integration", status, integ)
    else:
        status, login = req(
            "POST",
            "/auth/login_flow",
            {"client_id": CLIENT, "handler": ["homeassistant", None], "redirect_uri": CLIENT},
        )
        print("login_flow", status, login)
        if status != 200:
            return 1
        flow_id = login["flow_id"]
        status, done = req(
            "POST",
            f"/auth/login_flow/{flow_id}",
            {"username": "admin", "password": "adminadmin", "client_id": CLIENT},
        )
        print("login", status, done)
        if status != 200 or "result" not in done:
            return 1
        token = token_from_code(done["result"])

    status, flow = req(
        "POST",
        "/api/config/config_entries/flow",
        {"handler": "spo_pool_heat_pump", "show_advanced_options": False},
        token,
    )
    print("flow start", status, flow)
    if status != 200:
        return 1
    flow_id = flow["flow_id"]
    status, step = req(
        "POST",
        f"/api/config/config_entries/flow/{flow_id}",
        {"host": "replay", "port": 8899},
        token,
    )
    print("user", status, json.dumps(step)[:800])
    if step.get("type") == "form" and step.get("step_id") == "profile":
        status, step = req(
            "POST",
            f"/api/config/config_entries/flow/{flow_id}",
            {"profile": step.get("data_schema", [{}])[0].get("default") or "mida_cosma_pc1002"},
            token,
        )
        print("profile", status, json.dumps(step)[:800])
    if step.get("type") == "form" and step.get("step_id") == "options_setup":
        payload = {"name": "Pool heat pump"}
        names = {field.get("name") for field in step.get("data_schema") or [] if isinstance(field, dict)}
        if "write_path" in names:
            payload["write_path"] = "slave2"
        if "service_menu_writes" in names:
            payload["service_menu_writes"] = False
        status, step = req(
            "POST",
            f"/api/config/config_entries/flow/{flow_id}",
            payload,
            token,
        )
        print("options", status, json.dumps(step)[:800])
    if step.get("type") != "create_entry":
        print("FAILED", step)
        return 1
    print("created", step.get("title"), step.get("result"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
