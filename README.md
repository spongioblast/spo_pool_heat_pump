# SPO Pool Heat Pump (Modbus RTU over RS-485 via USR-DR164)

Home Assistant custom integration **SPO Pool Heat Pump** for inverter pool heat pumps that speak **Modbus RTU on RS-485**. A live **MIDA Cosma** (PC1002) is verified; the other shipped profiles still need a live test. Transport is a **USR-DR164** in transparent TCP Server mode. This is the Modbus client; do not add Home Assistant’s core Modbus integration.

Requires Home Assistant 2026.6.0 or later.

The integration creates a Device with native `climate`, sensors, switches and timer numbers. Service-menu values are not Home Assistant entities — they live in the card Settings dialog (and an optional standalone settings card). A bundled Lovelace card draws the water path (Circuit or Section — pick one in the card editor).

This file is the user guide. Protocol, write path, DR164 timing, tests, and the simulator: [docs/development.md](docs/development.md). Adding a profile: [docs/profiles.md](docs/profiles.md).

## Which heat pumps

AquaTemp on the phone does **not** prove this wire map. The outdoor board has to speak one of the RS-485 patterns below.

**Works (verified).** **MIDA Cosma** 13 / 20 / 28 / 35 — PHNIX PC1002 board. Home Assistant talks as a second display. Reads and everyday writes (mode, heat setpoint, quiet; the same path also does power, timers, and the other modes) were measured on a live Cosma. Same profile if the case says **Azuro** or **Mountfield** and setup detects that bus.

**Same bus — needs a live test.** **Hayward**, **Oasis**, **Warmpool**, **ECPI**, **irriPool**. Oasis publishes the PC1002 inverter manual; the others are the Hayward ESPHome bus. Pick this when setup heard the Cosma-style broadcast but did not pick Cosma. Not run on this integration.

**Shipped maps — untested here.** Different talk or different registers. Leave **Allow changing service settings** off.

| Case / badges | Profile | What is missing |
| --- | --- | --- |
| PHNIX Mini / SuperMini / SpecialLine, Thermotec | `phnix_mini_pc1002` | Same-looking registers; bits and setpoints differ from Cosma. |
| Fairland / Norsup CN13 | `fairland_pc1004_cn13` | Polled unit, slave **50** (menu H37). Community list; no dump here. |
| Fairland IPS Pro / InverX / IPHCR | `fairland_ips_pro_coils` | Polled unit, slave **1**, old coil map. Community YAML; no dump here. |

**Not this wire.** Hayward EnergyLine Pro / Trevium / Majestic / CPAC, Poolex Dreamline (NET) or Jetline, Welldana Aquagreen / EasyLine, PHNIX MegaLine, MIDA Joy / Poolsana InverPro, Fairland iGarden / Tuya SmartPool. Different bus or cloud only.

**Unknown.** Pick **Unknown heat pump — dump only** and capture from the card Settings. That records RS-485 bytes so a profile can be added later. It does not decode or write.

Badge → profile table: [docs/profiles.md](docs/profiles.md).

## What it looks like

Circuit is the default schematic. Section is the cutaway. Both follow the Home Assistant theme (light / dark) and shrink the facts row on a narrow column.

**Circuit — heating**

![Circuit schematic, heating, light and dark](docs/images/card-circuit-heating.png)

**Circuit — cooling**

![Circuit schematic, cooling, light and dark](docs/images/card-circuit-cooling.png)

**Section — heating**

![Section schematic, heating, light and dark](docs/images/card-section-heating.png)

**Section — cooling**

![Section schematic, cooling, light and dark](docs/images/card-section-cooling.png)

## Install the integration

This is a **HACS custom integration**, not a Home Assistant Core add-on. It is not in the HACS default store. Install it from GitHub.

### HACS (recommended)

1. **HACS → ⋮ → Custom repositories**.
2. Repository: [https://github.com/spongioblast/spo_pool_heat_pump](https://github.com/spongioblast/spo_pool_heat_pump)
3. Type: **Integration** → Add.
4. HACS → search **SPO Pool Heat Pump** → **Download**.
5. If GitHub has a **Release** (for example `1.1.0`), HACS installs that. If there is no release, it follows `main`.
6. **Restart** Home Assistant.

The Lovelace card is included. Do not add a Lovelace resource for it.

Then wire the DR164 (next three sections) and **Settings → Devices & services → Add integration → SPO Pool Heat Pump**. Host = reserved DR164 IP, port `8899`.

### Manual install

Copy **only** `custom_components/spo_pool_heat_pump` into `<config>/custom_components/` and restart. Then add the integration the same way. Do not copy `tools/`, `tests/`, `ha-docker/`, or `card-src/` — HACS does not install those either.

## 1. Wire the DR164

The factory WiFi / DTU port already carries all four pins the DR164 needs — **+**, **A**, **B**, **G** — so the DR164 runs in parallel on that same port and takes its power from the pump's 12 V rail. No separate PSU. Four wires, straight across, one per pin. Do not cut the panel cable.

![DR164 + / A / B / G wired in parallel on the heat-pump WiFi / RS-485 port](docs/images/dr164-parallel-tap.png)


| DR164       | Heat-pump bus                                              |
| ----------- | ---------------------------------------------------------- |
| `DC+` / `+` | `+` — 12 V rail, shared with the WiFi module               |
| `A / RX`    | `A`                                                        |
| `B / TX`    | `B`                                                        |
| `GND` / `G` | `G` — common ground; a separate `DC−` screw also goes here |


Swap A and B if every frame fails CRC. The DR164 accepts 5–36 V, so the pump's 12 V is in range.

A factory WiFi / DTU module can stay plugged in or not. The default write path does not use it.

## 2. Add the DR164 to the network

1. Power the DR164. Phone joins the open AP `USR-DR164-xxxx`.
2. Open `http://10.10.100.254` → `admin` / `admin`. Change that password before it sits on the home LAN.
3. Set **STA** Wi-Fi to the home SSID. Apply and wait for the reboot onto the LAN.
4. Reserve the DHCP lease (or set a static IP) on the same subnet as Home Assistant.
5. Leave the phone AP. Browse to that reserved IP to finish work-mode setup.

Home Assistant and the DR164 must be on the same LAN. One TCP client only — do not point a second app at port 8899 at the same time.

## 3. Set the work mode, then add it in Home Assistant

On the DR164 web UI (save and restart after these pages):

1. **Serial Setting:** **9600 8N1**, CTSRTS Disable, Pack Interval **20** (leave the factory value — do not set 10), Pack Size **1400**, Com Heart **OFF**, ModBUS Enabled **OFF**.
2. **Net Setting → Socket A:** **TCP-Server**, Port **8899**, Net heart **OFF**, Reg Set **OFF**. Not Modbus gateway, MQTT, HTTP or PUSR cloud.
3. **Event off** (there is no web switch). From any UDP tool on the LAN, to the DR164 IP port **48899**:
   1. Send `www.usr.cn` (it answers `IP,MAC,USR-DR164`).
   2. Send `+ok` (no line ending).
   3. Within 30 s send `AT+EVENT=off\r\n`, then `AT+Z\r\n`.
   Check with `AT+EVENT\r\n` (`+ok=off`).

   Or from this repository (Python 3, nothing to install): `python tools/dr164_event_off.py 192.168.x.x` — on Windows, `tools\dr164_event_off.cmd 192.168.x.x`. No IP lists modules that answer a broadcast. `--check` queries only.

Then **Settings → Devices & services → Add integration → SPO Pool Heat Pump**. Host = the reserved DR164 IP, port `8899`. Setup listens a few seconds and pre-selects a profile — keep it unless [Which heat pumps](#which-heat-pumps) says the name on the case is a different family.

Leave **Write path** on **Second panel (slave 2)**. It works with or without the factory WiFi module. **WiFi module (slave 99)** only changes mode on this bus. **Panel address 1** is unproven. If the bus does not match a shipped map, pick **Unknown heat pump — dump only**. Fairland CN13 / IPS Pro: confirm **Modbus slave (H37)** (CN13 default 50, IPS Pro usually 1). Leave **Allow changing service settings** off.

If the reserved IP or port changes later, use **Reconfigure** (host and port only). Profile, write path, and H37 stay under **Configure**. Do not add Home Assistant’s core **Modbus** integration or set the DR164 to Modbus gateway.

## Options


| Parameter                       | Where             | What it is                                                                 |
| ------------------------------- | ----------------- | -------------------------------------------------------------------------- |
| Host                            | Add / Reconfigure | Reserved LAN IP of the USR-DR164                                           |
| Port                            | Add / Reconfigure | Socket A port (factory `8899`)                                             |
| Profile                         | Add / Configure   | How the unit talks (Cosma, Mini, Hayward, CN13, IPS Pro, or dump only)     |
| Write path                      | Add / Configure   | Keep **Second panel (slave 2)**. Slave 99 is mode-only on this bus         |
| Modbus slave (H37)              | Add / Configure   | Fairland poll address. CN13 default 50, IPS Pro usually 1                  |
| Poll interval                   | Add / Configure   | Seconds between Fairland polls. Cosma / Mini ignore this                   |
| Allow changing service settings | Add / Configure   | Off by default. Required before H/F/D writes                               |
| Use manual flow for COP         | Configure         | Local COP from flow × ΔT × power; not written to the bus                   |
| Water flow (m³/h)               | Configure         | Circulation used for that COP. `0` means unused                            |


## Dashboard card

```yaml
type: custom:spo-pool-heat-pump-card
entity: climate.pool_heat_pump
schematic: circuit    # or section
animation: true       # pipes, plume, surface, and fan; false freezes all motion
settings: true        # sliders icon opens Settings; false hides it
# parameters_groups: [H, F]   # optional: only these service-menu/status groups
```

The sliders icon (next to Quiet and Power) opens Settings. Safe writes (power, mode, setpoint, timers, COP flow) edit inline. H/F/D service-menu rows stay locked until **Allow changing service settings** is on. Pin the same catalog with `custom:spo-pool-heat-pump-settings-card` if you want it always visible.

The card shows the new value immediately and pulses until the pump confirms it. If nothing comes back, it reverts (about 12 s; mode and timers wait about 20 s). A few seconds of unavailable after a change is the board committing — wait. Do not re-add the integration.

COP is drawn under the unit only when it is non-zero: a value the board publishes, or a calculated value from the manual flow, ΔT, and electrical power. ΔT stays on the left.

The card is registered automatically. After install, **restart Home Assistant, then reload the browser tab** (F5, or open a new tab). Do not add a Lovelace resource for the card — a second load duplicates it in Add to dashboard and can leave the view on Configuration error.

If **Add to dashboard** search for “SPO Pool Heat Pump” shows only Manual YAML:

1. Reload the browser tab after the restart (a tab open before the restart never ran the card module).
2. Open `/spo_pool_heat_pump/spo-pool-heat-pump-card.js` — it must be JavaScript, HTTP 200.
3. View source of `/` and confirm it contains `import("/spo_pool_heat_pump/spo-pool-heat-pump-card.js`.
4. Do not add a Dashboard resource.

Until the extra module runs, you can still add the card in YAML:

```yaml
views:
  - title: Pool
    cards:
      - type: custom:spo-pool-heat-pump-card
        entity: climate.pool_heat_pump
        schematic: circuit
        animation: true
        settings: true
      - type: custom:spo-pool-heat-pump-settings-card
        entity: climate.pool_heat_pump
      - type: thermostat
        entity: climate.pool_heat_pump
      - type: entities
        entities:
          - switch.pool_heat_pump_quiet
          - sensor.pool_heat_pump_inlet
          - sensor.pool_heat_pump_outlet
          - sensor.pool_heat_pump_energy_total
```

## Settings

The sliders icon opens this dialog. Groups, in order:

**Control** — everyday list (power, mode, setpoints, quiet, COP flow):

![Settings dialog, Control group, light and dark](docs/images/dialog-control.png)

**Timers** — on/off and quiet windows:

![Settings dialog, Timers group, light and dark](docs/images/dialog-timers.png)

### Service settings

**Allow changing service settings** is an integration option (first-run setup, or later **Configure** on the device). It is off by default. Leave it off unless you know the OEM numbers.

When off, the Settings dialog still *shows* H/F/D (and other special-menu) values but will not write them. When on, those rows become editable and the first write in a session asks for confirmation. Wrong H, F, or D values can damage or brick the heat pump — compressor limits, EEV, defrost, and similar installer parameters. Safe everyday writes (power, mode, setpoint, quiet, timers) do not need this option.

**System (H)** — the special / service menu. Values are visible; writes stay locked until the option is on:

![Settings dialog, System (H) service menu, light and dark](docs/images/dialog-service.png)

### Bus dump

A dump is a raw copy of the RS-485 bytes Home Assistant sees on the DR164. Use it to map a new model or an unknown register. Sliders icon → Settings → **Bus dump** (or `spo_pool_heat_pump.start_dump`). Files land in `config/spo_pool_heat_pump_dumps/*.log`. Timed runs are 1–120 min; Until I stop still ends at ~40 MB. The folder refuses a new capture above ~200 MB.

![Settings dialog, Bus dump tab, light and dark](docs/images/dialog-dump.png)

The **?** on that tab is the full checklist. In short:

1. Start the capture first. Write in the note what you are about to do.
2. One action at a time; wait a few seconds.
3. Use the heat-pump panel **and** the phone app if both exist. Leave the factory WiFi / DTU plugged in.
4. Power, Heat/Cool/Auto and each mode’s setpoint, quiet/timers, every on-screen menu. Let the unit actually run.
5. After each change, screenshot the app or photo the panel (menu name and the value). Name files with clock time or the dump note.
6. Download the `.log` and keep the pictures with it.

Do not change H/F/D service values unless you know the OEM numbers.

## Actions

These are integration actions (`spo_pool_heat_pump.*`). The card Settings dialog covers dump and service-menu work for everyday use.

### Start bus dump

`spo_pool_heat_pump.start_dump` captures raw RS-485 bytes from the DR164.


| Field                    | Required | Description                                                 |
| ------------------------ | -------- | ----------------------------------------------------------- |
| `duration`               | no       | Seconds. `0` runs until the ~40 MB cap or Stop. Default 900 |
| `note`                   | no       | Stored in the dump header (what you are about to do)        |
| `include_writes`         | no       | Also record bytes Home Assistant sends. Default on          |
| `entry_id` / `device_id` | no       | Which heat pump, if more than one                           |


### Stop bus dump

`spo_pool_heat_pump.stop_dump` closes the running capture.


| Field                    | Required | Description                       |
| ------------------------ | -------- | --------------------------------- |
| `entry_id` / `device_id` | no       | Which heat pump, if more than one |


### Refresh service menu

`spo_pool_heat_pump.refresh_service_menu` re-reads the service-menu pages. Use it if those rows are empty after setup.


| Field                    | Required | Description                       |
| ------------------------ | -------- | --------------------------------- |
| `entry_id` / `device_id` | no       | Which heat pump, if more than one |


### Set service setting

`spo_pool_heat_pump.set_service_menu` writes one H/F/D (or other special-menu) key. **Allow changing service settings** must be on. Wrong values can damage the unit.


| Field                    | Required | Description                            |
| ------------------------ | -------- | -------------------------------------- |
| `key`                    | yes      | Parameter id, e.g. `h06_min_freq_heat` |
| `value`                  | yes      | New value                              |
| `entry_id` / `device_id` | no       | Which heat pump, if more than one      |


## Remove the integration

**Settings → Devices & services → SPO Pool Heat Pump → Delete.** The device and its entities go with the entry.

Files in `config/spo_pool_heat_pump_dumps/` are not deleted. Remove those captures yourself if you no longer want them.

## Troubleshooting


| Symptom                                 | What to try                                                                                                      |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Cannot connect / add-integration fails  | Reserved IP, Socket A = TCP Server on 8899, pump powered. Then swap RS-485 A/B                                   |
| Every frame fails CRC / no data         | Swap A and B. Confirm UART 9600 8N1 and Pack Interval 20                                                         |
| Already configured                      | This DR164 already has an entry. Open that one, or **Reconfigure** its host/port                                 |
| Entities unavailable                    | One HA client only on port 8899. If the IP changed, **Reconfigure**. A short pause after a write is normal — wait |
| Dump folder full                        | `config/spo_pool_heat_pump_dumps/` is over ~200 MB. Delete old files from the card dump list                     |
| Writes pulse, then snap back            | Write path must be **Second panel (slave 2)**. Slave 99 is mode-only. Dump-only never writes. Weak WiFi: Event off, Pack 20, Ethernet if it persists |
| Service-menu write refused              | Enable **Allow changing service settings** under Configure                                                       |
| Core Modbus / DR164 “Modbus gateway”    | Do not add those                                                                                                 |
| Add to dashboard only shows Manual YAML | Reload the tab after the restart. Confirm the card JS URL is 200. Do not add a Lovelace resource                  |


## License

MIT. See [LICENSE](LICENSE). Releases: [CHANGELOG.md](CHANGELOG.md). Use at your own risk on a live RS-485 bus. One HA writer. Listen-only first.
