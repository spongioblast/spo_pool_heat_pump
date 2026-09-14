# Changelog

## Unreleased

- Optimistic writes: power, mode, setpoint, quiet and timer changes show immediately instead of after the next broadcast (2–4 s). Values stay flagged in `pending_writes` and the card pulses them until the heat pump echoes them; unconfirmed writes revert after 8 s with a warning. Polled (Fairland) profiles get the same, confirmed by the next poll cycle
- Profile JSON is read once in an executor and cached; no more "Detected blocking call to read_text / scandir" warnings from config and options flows
- `setup.html` merged into the README and removed; config-flow texts link to the README on GitHub
- Write path always defaults to **DTU slave 99** (the factory-app frame; a no-op without a module). Slave 2 is opt-in — it adds a second master to the bus and impersonates the second panel
- Detection listens for the full window instead of stopping at the first 2001 broadcast, and reports slave 99 as "heard / not heard" rather than claiming the module is absent

## 1.1.0

First public release of **SPO Pool Heat Pump**.

- HACS custom integration for inverter pool heat pumps on Modbus RTU over RS-485 via a USR-DR164 transparent TCP Server
- Verified MIDA Cosma / PC1002 map; community profiles for Hayward, PHNIX Mini, Fairland CN13 / IPS Pro
- Native climate, sensors, switches, and timer numbers; service-menu rows stay in the card Settings dialog
- Bundled Circuit / Section Lovelace card
- Service-menu writes off by default
