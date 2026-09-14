# Local Home Assistant (Docker)

Developer only — not installed by HACS. Protocol and pytest notes: [docs/development.md](../docs/development.md). Throwaway HA on port **8124**. A sidecar runs the **state-model simulator** on **8899**, so you can add the integration and exercise the Settings dialog without touching the live DR164.

Dump replay is lab-only (sibling `../protocol-analysis/`, not in this repo). The compose stack uses the state-model simulator instead.

```bash
# from pool-heatpump/, in WSL:
docker compose -f ha-docker/docker-compose.yml up -d
python3 ha-docker/win_proxy.py
```

On this Windows PC, `http://127.0.0.1:8124` does **not** reach WSL Docker.
Use the WSL address instead (first run: create a user):

```bash
wsl hostname -I
# then open http://<first-ip>:8124
```

`ha-docker/win_proxy.py` listens on 8124 in WSL and forwards into HA. The proxy
must be running; Docker's own published ports are not visible from the browser.

**Add integration → SPO Pool Heat Pump**

- Host: `replay`
- Port: `8899`

Host `replay` is the compose service name (HA talks to it on the Docker network). Do not enter your real DR164 IP here if production HA is already connected.

Stop: from `pool-heatpump/`, `docker compose -f ha-docker/docker-compose.yml down`

HA-dependent unit tests (`test_ha.py`, `test_config_flow.py`, `test_resolve.py`, part of `test_listen_only.py`) skip locally without the `homeassistant` package. Run them in the HA image:

```bash
docker run --rm --entrypoint sh \
  -v "$PWD":/repo -w /repo -e PYTHONPATH=/repo/custom_components \
  ghcr.io/home-assistant/home-assistant:stable \
  /repo/ha-docker/_run_ha_tests.sh
```

Local `pytest` prints those as `SKIPPED` (`importorskip`) so a missing HA env is visible.
