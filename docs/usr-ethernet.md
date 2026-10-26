# USR-DR134 / USR-DR302 (wired gateways)

USR's Ethernet siblings of the DR164. Same idea: a **transparent TCP Server** that passes raw Modbus RTU bytes between the pump's RS-485 port and Home Assistant, over a cable instead of WiFi.

**Status: should work, not live-tested.** Nobody has run one on a live pump with this integration yet. If you do, open an [issue](https://github.com/spongioblast/spo_pool_heat_pump/issues/new) with a short [Bus dump](../README.md#bus-dump) — working or not.

| | USR-DR134 | USR-DR302 |
| --- | --- | --- |
| Manual | [DR132/134](https://www.pusr.com/uploads/20250124/57fbba66ef75af78cf72c900bc464d8d.pdf) | [DR302](https://www.pusr.com/download/User%20Manual/USR-DR302-User-Manual.pdf) |
| Power | DC 5–24 V | DC 5–36 V |
| RS-485 terminals | RX/A, TX/B, GND | A, B, GND |
| Factory IP / login | `192.168.0.7`, `admin` / `admin` | `192.168.0.7`, `admin` / `admin` |
| Factory mode | TCP **client**, 115200 8N1 | TCP **client**, 115200 8N1 |
| Search / setup tool | USR Ethernet tool | USR-M0 setup software |

Both ship in the wrong mode for this integration. Change everything below before you add it to Home Assistant.

## Wire it

Same tap as the DR164: in parallel on the factory WiFi / DTU port, do not cut the panel cable.

| Gateway | Heat-pump port |
| --- | --- |
| **A** (DR134: RX/A) | **A** |
| **B** (DR134: TX/B) | **B** |
| **GND** | **G** |
| Power **+ / −** | **+ / G** (12 V), or a separate supply |

The pump's 12 V is in range for both. Leave any 120 Ω terminator off while the wired panel is connected. Swap A and B if every frame fails CRC.

## Configure it

Plug it into the LAN, find it with the USR tool or browse to `192.168.0.7` (put your PC on `192.168.0.x` if needed). Log in, change the password, then give it a static IP or a DHCP reservation on the Home Assistant LAN.

**Serial / port page:**

| Setting | Value |
| --- | --- |
| Baud / data / parity / stop | **9600 / 8 / None / 1** (factory is 115200) |
| Work mode | **TCP Server** (factory is TCP client) |
| Local port | **8899** — matches the integration default; any free port works |
| Max clients | **1** |
| On too many clients | **Kick** the old one |
| Packing time | DR134: about **10–20 ms**. DR302: factory 4-byte time is fine, or 10–20 ms |
| Packing length | DR134: **1024**. DR302: **1024** (factory) |

**Everything else off:**

- **Modbus gateway / Modbus TCP**, **Modbus polling**, **custom polling** — off
- **MQTT**, **Edge gateway**, **HTTP client**, **USR Cloud** — off
- **Heartbeat** (both serial and network) — off
- **Register packet** (MAC / custom / cloud) — off
- **Similar RFC2217** — off
- DR302: **UART set parameter** — off
- **Buffered / cached data before connect: clear** (DR302 factory keeps it)

Why these matter:

- **TCP Server, not Modbus.** The integration speaks raw RTU on the socket. Modbus TCP mode expects a different framing, and the polling options make the gateway poll the bus itself. On a Cosma-style bus the outdoor board is already the master; a second poller collides.
- **Serial heartbeat** sends bytes onto the RS-485 bus on a timer. **Register packets** insert bytes into the stream.
- **Cached data.** While Home Assistant is disconnected the gateway can keep bus bytes in a buffer and hand them over on connect. Those old board polls would look fresh; answering them late collides with the board's next frame. Clear the buffer on connect.
- **UART set parameter** lets the gateway take configuration commands from the serial side. A busy bus is no place for that.
- **Packing time** is how long the gateway waits for a quiet gap before forwarding. Too long and board polls reach Home Assistant late, the slave-2 reply misses the board's ~340 ms page-read window, and writes snap back.
- **One client, kick the old one.** Only Home Assistant connects. Kick lets Home Assistant's redial replace its own stale connection after a LAN blip instead of being refused. No Core Modbus, no Modbus proxy, no second app on that port.

Optional: **No data restart** (DR134 system page, DR302 timeout restart) set to a few minutes makes the gateway reboot itself if the bus goes dead. Only use it on a bus that is never quiet, like the Cosma's constant broadcasts.

LEDs: **LINK** on = Home Assistant is connected. **COM** blinking = bus traffic (constant on a Cosma). COM dark = baud, A/B, or wiring.

## Add it to Home Assistant

Same as the [README](../README.md#add-it-to-home-assistant), with:

- **Host** = the gateway's reserved IP. **Port** = the local port you set (8899 above).
- After setup, **Configure** → turn off **Reboot DR164 if the bus stays silent**. That recovery uses the DR164's WiFi-module AT protocol; these Ethernet units use a different setup protocol. If you leave it on, Home Assistant gives up after three unanswered tries and logs why.

Profile, write path (**Second panel (slave 2)**), and service settings are the same as on a DR164.

## Dumps

- **Card Bus dump** works the same. It records what the TCP socket delivers, whatever the gateway, in the same `.log` format. On Ethernet the timestamps sit much closer to the wire than through a DR164 on WiFi. Home Assistant is still a bus participant, so it is not a full copy of the cable — except with the **Unknown heat pump — dump only** profile, which never transmits.
- **USB dump** is unchanged: [RS-485 ModBus dump](../tools/rs485-dump/README.md). It is still the reference for timing, collisions, and new pumps.

## Troubleshooting

| Symptom | What to try |
| --- | --- |
| Cannot connect | Work mode TCP Server (factory is client), reserved IP, local port, max clients not taken by another app |
| Connected, entities unavailable | COM dark: 9600 8N1 (factory is 115200), swap A/B |
| Every frame fails CRC | Swap A/B. Confirm 9600 / 8 / None / 1 |
| Writes pulse, then snap back | Lower the packing time. Cached data cleared on connect. Write path slave 2 |
| Log: "never answered the USR-DR164 search" | Expected on these units. Turn off **Reboot DR164 if the bus stays silent** |
