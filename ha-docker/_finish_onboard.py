from __future__ import annotations

import json
import urllib.request

BASE = "http://127.0.0.1:18123"
CLIENT = f"{BASE}/"


def post(path: str, body: dict | None = None, token: str | None = None, form: bool = False):
    if form:
        data = "&".join(f"{k}={v}" for k, v in body.items()).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    else:
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
        return resp.status, json.loads(raw) if raw else {}


def get(path: str):
    req = urllib.request.Request(BASE + path, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
        return resp.status, json.loads(raw) if raw.startswith("[") or raw.startswith("{") else raw


status, onboard = get("/api/onboarding")
print("onboarding", status, onboard)

status, flow = post("/auth/login_flow", {"client_id": CLIENT, "handler": ["homeassistant", None], "redirect_uri": CLIENT})
print("flow", status, flow)
status, done = post(f"/auth/login_flow/{flow['flow_id']}", {"username": "admin", "password": "adminadmin", "client_id": CLIENT})
print("login", status, done)
status, tok = post("/auth/token", {"grant_type": "authorization_code", "code": done["result"], "client_id": CLIENT}, form=True)
print("token", status, list(tok))
token = tok["access_token"]
status, integ = post("/api/onboarding/integration", {"client_id": CLIENT, "redirect_uri": CLIENT}, token)
print("integration", status, integ)
status, onboard = get("/api/onboarding")
print("onboarding after", status, onboard)
