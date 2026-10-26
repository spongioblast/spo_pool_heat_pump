# Waveshare RS485 TO ETH (wired gateway)

A wired alternative to the USR-DR164. The integration only needs a **transparent TCP Server**: raw Modbus RTU bytes in and out, nothing added. Waveshare's RS485 TO ETH serial servers do that in their default mode, over Ethernet instead of WiFi, with an isolated RS-485 port.

**Status: should work, not live-tested.** Nobody has run one on a live Cosma yet. If you do, open an [issue](https://github.com/spongioblast/spo_pool_heat_pump/issues/new) with a short [Bus dump](../README.md#bus-dump) — working or not.

Models: **4-CH RS485 TO ETH (B)** and **4-CH RS485 TO POE ETH (B)** ([wiki](https://www.waveshare.com/wiki/4-CH_RS485_TO_POE_ETH_(B))). The single-channel **RS485 TO ETH (B)** ([manual](https://files.waveshare.com/upload/4/4d/RS485-to-eth-b-user-manual-EN-v1.33.pdf)) has the same settings. On a 4-channel unit use **one** channel for the heat pump; the steps below use channel 1.

## Wire it

Same tap as the DR164: in parallel on the factory WiFi / DTU port, do not cut the panel cable.

| Waveshare | Heat-pump port |
| --- | --- |
| 485-1 **A** | **A** |
| 485-1 **B** | **B** |
| RS-485 ground of that channel, if it has one | **G** |
| Power **+ / −** (DC 6–45 V on the 4-CH) | **+ / G** (12 V), or a separate supply / PoE |

Check the label on your unit for the power range. If you are unsure the pump's 12 V can carry it, use a separate supply or the PoE version. Leave any 120 Ω terminator off while the wired panel is connected. Swap A and B if every frame fails CRC.

## Configure it

Use **Vircom** (Waveshare's tool; finds the unit even on another subnet) or the web UI at the unit's IP. After a 5 s reset the IP is `192.168.1.254`. Give it a static IP or a DHCP reservation on the Home Assistant LAN.

Channel 1:

| Setting | Value |
| --- | --- |
| Work mode | **TCP Server** |
| Port | **4196** (channels 2–4: 4197–4199) |
| Baud / data / parity / stop | **9600 / 8 / None / 1** |
| Flow control | None |
| Conversion (transfer) protocol | **None** — transparent |
| Packet length | **1400** |
| Packet interval | Small — about **10–20 ms** (the DR164 runs 20) |

Under **More Advanced Settings**, everything off:

- **Send MAC address when TCP is established** — off
- **Registration package** / REAL_COM — off
- **Send parameters at regular intervals** — off
- **RS485 multi-host** and **RS485 bus conflict detection** — off

Why these matter:

- **Not "Modbus TCP ↔ RTU"** (port 502). That expects Modbus TCP framing, which this integration does not speak, and its default storage mode polls the bus on its own. On a Cosma-style bus the outdoor board is already the master; a second poller collides.
- **Packet interval** is how long the unit waits for a quiet gap before forwarding serial bytes. Too long and every board poll reaches Home Assistant late, so the slave-2 reply misses the board's ~340 ms page-read window and writes snap back.
- **Multi-host** queues and reschedules traffic, which delays the same replies.
- **One TCP client.** In TCP Server mode the unit accepts up to 30 connections and copies every bus byte to all of them; anything any client sends goes onto the bus. Only Home Assistant connects. No Core Modbus, no Modbus proxy, no second app on that port.

LEDs: **Link** blue = Home Assistant is connected. **ACT** blue = bus data reaching the network (should flicker constantly on a Cosma). ACT only green = Home Assistant sent but nothing comes back — baud or A/B.

## Add it to Home Assistant

Same as the [README](../README.md#add-it-to-home-assistant), with:

- **Host** = the Waveshare's reserved IP. **Port** = **4196** (or the channel you used).
- After setup, **Configure** → turn off **Reboot DR164 if the bus stays silent**. That recovery talks USR's UDP protocol; a Waveshare does not answer it. If you leave it on, Home Assistant gives up after three unanswered tries and logs why.

Profile, write path (**Second panel (slave 2)**), and service settings are the same as on a DR164.

## Dumps

- **Card Bus dump** works the same. It records what the TCP socket delivers, whatever the gateway, in the same `.log` format. Timestamps are still TCP arrival, but on Ethernet they sit much closer to the wire than through a DR164 on WiFi. Home Assistant is still a bus participant, so it is not a full copy of the cable.
- **USB dump** is unchanged: [RS-485 ModBus dump](../tools/rs485-dump/README.md). It is still the reference for timing, collisions, and new pumps. For deep debugging run both at once, as in the README.
- Do not use a second Waveshare channel or a second TCP client as a "tap". Use the listen-only USB stick.

## Troubleshooting

| Symptom | What to try |
| --- | --- |
| Cannot connect | Reserved IP, channel port (4196…), Work mode TCP Server, nothing else connected to that port |
| Connected, entities unavailable | ACT never blue: swap A/B, confirm 9600 8N1, conversion protocol None |
| Every frame fails CRC | Swap A/B. Confirm 9600 / 8 / None / 1 |
| Writes pulse, then snap back | Lower the packet interval. Multi-host and conflict detection off. Write path slave 2 |
| Log: "never answered the USR-DR164 search" | Expected on a Waveshare. Turn off **Reboot DR164 if the bus stays silent** |
