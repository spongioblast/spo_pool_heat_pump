# Changelog

## Unreleased

- **Setpoint and mode writes fixed on the PC1002 bus** (quiet already worked). The setpoint now goes to the per-mode word (1135 cool / 1136 heat / 1137 auto) with the display's setpoint flag `0x0040`; it was tagged with the timer flag `0x0020`, which made the board re-read the wired display's page and keep the old value. Word 1013 is no longer written (panel-owned, not the working setpoint). Mode is read from page word 1012 instead of broadcast 2012, which only ever reports the running direction — a pump set to auto on the panel showed as heat, so switching it to auto was a no-op. The board's running direction is exposed as read-only *Running as* (`active_mode`). A mode write is also no longer confirmed by our own settings cache; only the board's page push or broadcast confirms it. Values that are confirmed by a page push (mode, timers) get a 20 s revert timeout instead of 12 s, since the push lands 8–10 s after the write
- **Writes fixed on the PC1002 bus.** The main board is the Modbus master and treats Home Assistant as the second display panel. The slave 2 responder now acknowledges the board's page pushes (FC16 echo) like a real panel — without that the board retried every push twice per cycle forever (cycle 1.7 s → 6.7 s) and ignored our change flag, so only the very first write after a restart went through. It also raises exactly the 3011 bits the wired display uses (`0x0004` page 1001, `0x0020`/`0x0040` page 1091) instead of `0x8004`, and keeps a queued value in its page copy until the board pushes it back, so a push of the old page cannot wipe it. Measured on the live bus 2026-09-14 and in the recorded dumps
- Write path defaults to **Second panel (slave 2)** for all PC1002 profiles. **WiFi module (slave 99)** and **Panel address 1** remain selectable but are unverified / unproven; slave 99 does nothing when no module is on the bus
- Optimistic writes: power, mode, setpoint, quiet and timer changes show immediately instead of after the next broadcast (2–4 s). Values stay flagged in `pending_writes` and the card pulses them until the heat pump echoes them; unconfirmed writes revert after 12 s with a warning. Polled (Fairland) profiles get the same, confirmed by the next poll cycle
- Profile JSON is read once in an executor and cached; no more "Detected blocking call to read_text / scandir" warnings from config and options flows
- `setup.html` merged into the README and removed; config-flow texts link to the README on GitHub
- Detection listens for the full window instead of stopping at the first 2001 broadcast, and reports slave 99 as "heard / not heard" rather than claiming the module is absent

## 1.1.0

First public release of **SPO Pool Heat Pump**.

- HACS custom integration for inverter pool heat pumps on Modbus RTU over RS-485 via a USR-DR164 transparent TCP Server
- Verified MIDA Cosma / PC1002 map; community profiles for Hayward, PHNIX Mini, Fairland CN13 / IPS Pro
- Native climate, sensors, switches, and timer numbers; service-menu rows stay in the card Settings dialog
- Bundled Circuit / Section Lovelace card
- Service-menu writes off by default
