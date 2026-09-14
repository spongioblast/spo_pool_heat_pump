# Development

Protocol, write path, DR164 timing, tests, and the simulator. Install and everyday use stay in the [README](../README.md). Adding a profile: [profiles.md](profiles.md). Local Home Assistant: [ha-docker/README.md](../ha-docker/README.md).

HACS installs only `custom_components/spo_pool_heat_pump`. `tools/`, `tests/`, `ha-docker/`, and `card-src/` are not shipped.

## Simulator, tests, card

```bash
python -m tools.simulator --host 0.0.0.0 --port 8899 --profile mida_cosma_pc1002
```

```bash
pip install -r requirements_test.txt
pytest
```

HA-dependent tests skip unless `homeassistant` is installed. Dump-replay and Cosma-notebook tests skip unless the sibling lab folder `../protocol-analysis/` is present — that folder is not in this repo and is not published.

HA-dependent tests (`test_ha`, `test_config_flow`, `test_resolve`, part of `test_listen_only`) inside the Home Assistant image: [ha-docker/README.md](../ha-docker/README.md).

Rebuild the Lovelace card after editing `card-src/`:

```bash
cd card-src && npm ci && npm run build
```

Dump replay (wire-fidelity, not the state model) is lab-only.

## Detection

Setup listens ~5 s for a `2001×90` broadcast. Firmware **713/772** → MIDA Cosma; Mini firmware at word **2017** → PHNIX Mini; any other `2001` → Hayward (the user can override). Silent bus probes slave 50 FC03 `1011×3`, then slave 1 FC01 coil 0. If nothing matches, the picker suggests **dump only**. Old ids (`cosmo_pc1002`, `phnix_mini_rs485`, `fairland_legacy_coils`) still load.

## PC1002 write protocol

On the PC1002 bus the **main board is the Modbus master**. Every 1.7 s cycle it polls the wired display (slave 1), an optional second display (slave 2) and slave 66 for their 3001×30 status page, then broadcasts the 2001×90 status map. It pushes the settings pages 1001 / 1091 / 1181 and 3001×11 to every slave that answers and expects the normal FC16 echo as an acknowledgement. A display changes a setting by raising a bit in word **3011** of its 3001 reply that says *what* changed (`0x0004` → page 1001: power, mode, quiet, timers; `0x0040` → the setpoints 1135–1137 in page 1091; `0x0020` → the timer words 1150–1159 in page 1091); the board reads that page back ~0.35 s later, applies it, re-pushes it to all slaves and clears the flag. The bit has to be the right one: a setpoint flagged as `0x0020` made the board re-read the wired display's page instead and keep the display's copy. Measured on the wired display in the recorded dumps and on the live bus (2026-09-14).

Two words are easy to get wrong. Broadcast word **2012 is the direction the board is running** (heat or cool) — it never reports auto; the selected mode is word **1012** in page 1001, so the entity reads its mode from the page and exposes 2012 as *Running as* in Settings. The working setpoint is the **per-mode word** 1135 (cool) / 1136 (heat) / 1137 (auto), which the board mirrors into broadcast 2013 and swaps itself on a mode change; word 1013 in page 1001 is panel-owned and lags 2013 for minutes, so it is neither written nor trusted.

Default writes therefore go through the **Second panel (slave 2)** path: Home Assistant answers the slave 2 polls with the serial, acknowledges the board's page pushes (which also refresh the page copies), and when you change something it overlays the register in its copy of the page, raises the same 3011 bit the display would, and lets the board read it back. The bit drops as soon as the page is served, exactly like the display does (a bit left up makes the board re-read the page every cycle and commit nothing). The board's 3001 sync that follows every read by ~0.85 s tells whether the read got through: `0` on every success, and an echo of our bit when our reply did not make it — the board then falls back to the wired display's page. On that echo Home Assistant raises the bit again at the next poll, at most twice per write (about 1 in 12 writes needed it on the live bus). The board does **not** push 1001 / 1091 / 1181 to the panels every cycle: on the DR164 dumps of 2026-09-14 a page went to slave 1 / 2 only right after it changed (1091 to slave 2: 0, 5 and 1 times in three 15-minute windows), while the roughly once-a-minute pushes go to the WiFi module (slave 99). Without the acknowledgements the board retries each push twice per cycle forever and ignores the panel's flag — that is how an earlier build broke writes after the first one. Writes to page 1181 have no known flag bit and are not delivered.

So the page copies are seeded by a one-shot FC03 read of the wired display (slave 1) once at startup, and the board's pushes keep them fresh afterwards. A write to a page that is still empty (the startup read timed out, or Home Assistant just restarted) first waits `PAGE_SEED_WAIT_S` (3.0 s) for a push, then reads that one page once more; only if that fails too does it raise `SettingsUnseeded` instead of inventing a page. `spo_pool_heat_pump.refresh_service_menu` is the same read, on demand. A build that skipped the startup read (03b4f19) could not change the setpoint after a restart until someone touched the panel. What is *not* done on slave 2 is re-reading the display whenever 3011 changes — that re-read after a failed page read collided with the board's next frame on the USB tap.

**WiFi module (slave 99)** sends one FC16 frame addressed to the factory module. On this bus, `1012` (mode) is forwarded and the board adopts it in ~1.5 s; `1013` (setpoint) and `1076` (quiet) are acked by the module and ignored by the board. With no module on the bus nobody answers. **Panel address 1** is unproven. Both stay selectable under Configure; leave the default on slave 2.

Fairland CN13 / IPS Pro use `poll_master` (HA is the master). Set **Modbus slave (H37)** if the unit is not on the profile default (CN13 50, IPS Pro 1). Pending confirmation is the next poll cycle; the timeout is `2 × interval + 4` s.

## Deadline and transport

The board gives up on a slave-2 page read after ~340 ms of silence (measured 0.326–0.356 s on page 1001 and 1091). The wired display's first byte lands at 201–218 ms. Through a DR164 the typical first byte is 230–234 ms — about 30 ms of pack + LAN on top of the display, still ~100 ms of slack. A WiFi retransmit on a through-the-house link can push the reply to 550–800 ms; the board has already echoed the flag and then re-reads the wired display. Home Assistant answers a request in 0–1 ms once it sees it, emits a complete CRC-valid frame without waiting another 20 ms, and will not transmit a solicited reply that is already more than 200 ms old (a late 185-byte answer collides with the board's next frame). `TCP_NODELAY` is on. Remaining spikes are the radio; an Ethernet RS-485 gateway (same transparent TCP Server mode) or USB-on-the-HA-host is the durable fix if misses persist.

Serial USB and Modbus-TCP gateways are not available in v1.

## Optimistic writes and availability

A slave 2 write is picked up at the board's next slave 2 poll, read back ~0.35 s later and shows in the following broadcast — a panel change reached the broadcast after a median 3.1 s and at most ~4 s in the recorded dumps. Home Assistant applies writes optimistically: the entity shows the new value immediately and lists it in the climate attribute `pending_writes`; the card pulses the affected control while it is in flight. The pulse stops when the board confirms the value — a broadcast echo for power/quiet, or the settings-page push for mode, timers and (on slave 2) the setpoint. If the pump has not echoed it after 12 s (20 s for a page-confirmed value) the value reverts to what the device reports and a warning is logged (`write silent=True not confirmed …`) — a rejected write is never left on screen. Mode and timers only exist in a settings page, which the board pushes back to the panels one round after applying it (8–10 s measured). The setpoint is written into page 1091 but shown from broadcast word 2013, and the two do not move together: on the live bus the board pushed the page back with the new value 8.6 s after the write while 2013 kept the old value for 21 s (its post-commit pause stretches the broadcast gap). So a setpoint counts as accepted as soon as either source carries it — the pulse stops at the page push and the new value stays on screen until 2013 follows, instead of falling back to the old number for a few seconds in between. The entity stays available through the board's own ~6 s silence after it adopts a change (broadcasts can be 14 s apart); it is marked unavailable only after 15 s with no pending write. A bus with **no frame of any kind** for 15 s also makes Home Assistant drop and re-open the TCP socket: after a DR164 reboot or a WiFi dropout the old socket is half-open — the module has forgotten it, no FIN or RST ever arrives, and slave-2 writes only touch the socket when the board polls — so without that redial the entity would stay unavailable indefinitely (seen 2026-09-14: 7 min and counting after a module restart). Board polls and unchanged page pushes keep the socket; only a dead line redials. This applies to the card, Core tiles, the phone app and automations alike.

## DR164 work mode (why the user recipe is that)

Firmware **V1.0.15** / web **1.0.08**, measured 2026-09-14.

**Pack Interval 20** is the factory value and must stay there. At **10** this firmware flushes the first 16 bytes of every frame on their own and the rest ~185 ms later, which cut the 189-byte broadcast into two halves 94 % of the time on the live bus. At 20, roughly 97 % of broadcasts arrived intact; the rest were radio truncations, not that 16-byte FIFO split.

**Event** has no web switch. With Event on the DR164 writes ASCII `+EVENT=SOCKA_ON` / `SOCKA_OFF` onto the RS-485 bus on every TCP connect/disconnect (seen on the USB tap). Network-AT is UDP port **48899**: send `www.usr.cn` (it answers `IP,MAC,USR-DR164`), then `+ok` with **no line ending** — without that acknowledgement the module ignores every command — then within 30 s `AT+EVENT=off\r\n` and `AT+Z\r\n`. `AT+EVENT\r\n` reads it back (`+ok=off`). `AT+WSLQ\r\n` shows the WiFi signal; below ~50 % expect missed page-read deadlines. Serial `+++`/`a` AT entry is not usable here — the bus is never quiet. Same sequence: `python tools/dr164_event_off.py <ip>` (or `tools\dr164_event_off.cmd` on Windows).

`AT+EVENT=off` and pack 20 must persist across a module reboot. One TCP client only on port 8899.

## Dump vs USB reader

The card **Bus dump** writes the same `.log` / `.bin` dialect as `protocol-analysis/rs485_dump.py` (hex + ASCII, `# idle`, timestamps, optional `# dir=tx`). Feed a `.log` into `analyze_modbus.py` or `dump_replay_server.py` in that lab folder.

That is enough to **map registers** on a new pump (dump-only profile, one action at a time, photos). It is not a passive tap:

| | USB `rs485_dump` / `cosmo_watch` | DR164 + HA dump |
| --- | --- | --- |
| What it timestamps | UART bytes on the wire | TCP packets after pack + WiFi + LAN |
| Idle gaps | Real RS-485 silence | Arrival jitter |
| Listen-only | Yes (RTS low) | No — HA is the only TCP client; slave-2 replies go out this socket |
| Long frames | One UART stream | Split or truncated if pack is 10 or the radio drops |
| Collisions | Visible as overlapping bytes | Gateway buffers mash TX + RX |
| How long | Until you stop | 2 h / ~40 MB session, 200 MB folder |

Board deadlines (340 ms), display first-byte (201–218 ms), and collisions were measured on the USB tap. The DR164 dump cannot replace that for timing work.

## Why not Home Assistant’s Modbus integration?

The heat pump **is** Modbus RTU. We still do not use Core’s **Modbus** integration (and do not set the DR164 to **Modbus gateway**).

Core Modbus — and gateway mode on the DR164 — assume Home Assistant is the only master: poll a slave, get a reply. On Cosma / PC1002 the **outdoor board already masters** the line: it polls the display panels and **broadcasts** the 2001×90 map; this integration **listens** and **answers as the second panel (slave 2)** when the board polls it. A second poller on the same RS-485 would collide with that.

The DR164 must stay a **transparent TCP byte pipe** (raw RTU, 20 ms idle framing). Core Modbus-over-TCP wants MBAP / gateway framing. This client also drops non-CRC noise (heartbeat) and waits for a quiet gap before TX.

Fairland CN13 / IPS Pro *are* polled, but still through this client so one integration, one socket, and the same write / dump / card path. Do not add both.
