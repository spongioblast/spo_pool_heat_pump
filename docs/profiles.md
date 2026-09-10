# Adding a heat pump profile

A profile is one JSON file under `custom_components/spo_pool_heat_pump/profiles/`. No Python for a same-family pump.

Copy `mida_cosma_pc1002.json`, name the file `{brand}_{product}_{family}.json`, change `identity.id` to match, keep the same register keys the climate card needs, add CRC-valid `fixtures.frames`, drop a dump next to `../protocol-analysis/dumps/`. A new talk pattern (not 2001 sniff, not FC03 poll) needs a new `HeatPumpDriver` class — do not invent a third decode path.

The contract is `profiles/schema.json`. Tests run `jsonschema` on every shipped file. `../protocol-analysis/protocol.json` is the Cosma lab notebook, not a shipped file.

## Naming (one badge, one family)

Do not put several companies in `model`. The verified unit is a **MIDA Cosma** (Midas; booklet `MIDA.Cosma 13/20/28/35`). AquaTemp is the **app / DTU**, not the heat pump. PHNIX made the PC1002 board. Hayward / Welldana / Warmpool are other badges on the same family. `COSMO` was a misread of Cosma.

| Field | Meaning | Example |
| --- | --- | --- |
| `brand` | Name on the case / invoice | `MIDA` |
| `model` | That brand’s product line only | `Cosma` |
| `family` | Shared controller / talk pattern | `pc1002` |
| `oem` | Who made the board (optional) | `PHNIX` |
| `app` | Cloud / DTU app (optional) | `AquaTemp` |
| `also_sold_as` | Other badges, same map (optional) | `["Warmpool", "ECPI"]` |

HA device manufacturer = `brand`, model = `model`. Fault JSON `_faults_pc1002.json` is keyed by **family**, not brand. Profile file and `identity.id` are `{brand}_{product}_{family}` (lowercase, spaces to `_`). Drop a repeated segment (`hayward_pc1002`, not `hayward_pc1002_pc1002`).

## Required top-level keys

- `identity` — naming above, plus `verification` (`verified` | `community` | `experimental`) and `source`
- `link` — `baud`, `parity`, `stop_bits`, `slaves`
- `driver` — `type`: `pc1002_bus`, `poll_master`, or `listen_only` (dump-only, no map)
- `modes` — subset of `heat`, `cool`, `auto` (climate HVAC modes come from this)
- `enums` — especially `mode` (MIDA Cosma is 0 cool / 1 heat / 2 auto; some Fairland maps invert this)
- `registers` — typed rows. Core climate/card keys stay on `HeatPumpState`; extra keys go to `state.values`

## Register vocabulary

`type` is one of `u16`, `i16`, `bool`, `enum`, `bits`, `faults`, `ascii`, `bcd_hms`. Fairland coil maps may add `transform: fairland_temp`. Protocol `bitfield` becomes `bits`.

```json
"setpoint": { "reg": 2013, "write": 1013, "type": "i16", "scale": 0.1, "unit": "°C" },
"t_suction": { "reg": 2045, "type": "i16", "scale": 0.1, "unit": "°C",
  "entity": { "platform": "sensor", "device_class": "temperature", "category": "diagnostic", "enabled": false } },
"outputs": { "reg": 2019, "type": "bits", "bits": { "compressor": 0, "water_pump": 1 } },
"faults": { "regs": [2074, 2075, 2076, 2077], "type": "faults", "file": "_faults_pc1002.json" },
"clock": { "reg": 3015, "count": 3, "type": "bcd_hms" }
```

An `entity` block creates a disabled diagnostic without new Python. Every such key (or bit name) needs a `strings.json` entry.

Climate modes come from `modes`. Sensors and switches appear when the register key exists (`silent`, `power_kw`, timer `*_h` / `*_min`, …).

`hz_max` may point at service-menu keys (`h08_max_freq_heat`, `h09_max_freq_cool`) and must include a numeric `default` per mode.

## Driver

`pc1002_bus` sniffs `driver.broadcast` (`start` / `qty`, required). `write_targets` lists `dtu_99` / `slave2` / `panel_1`. Mini lists DTU and slave 2 — pick slave 2 when there is no WiFi module. `driver.settings.pages` are the one-shot FC03 service-menu reads. `settings.flags` (3011 bits) re-reads those pages when the panel says they changed. Cosma and Hayward also set `power_also_write: [1014]`.

`poll_master` uses `driver.reads`: `{name, fc, slave, start, qty}`. IPS Pro outputs must use `block` / `offset` so coil polls decode. The integration option **Modbus slave (H37)** overrides `poll_slave` and every `reads[].slave` (Fairland CN13 default 50). Do not point `faults.file` at `_faults_pc1002.json` unless a dump proved those bits. CN13 keeps the 2074–2077 words and shows raw `reg.bit` codes until someone maps them.

`listen_only` is the **Unknown heat pump — dump only** profile. It does not decode or write. The climate entity stays available so the card Settings → **Bus dump** can record raw RS-485. After you have a dump, **Configure** that same entry and pick a real profile (or add a new JSON). Do not Add the integration a second time on the same DR164 — one TCP client only. Detection offers dump-only when the 5 s listen and the slave 50 / slave 1 probes see nothing.

`fixtures.frames` are CRC-valid hex strings. Optional `fixtures.dump` points at a repo dump.

## Faults and service-menu catalogs

`faults.file` is `_faults_pc1002.json`. `bits` decode the bus. `booklet` texts load into meanings; `bit: null` rows cannot appear from a register until a dump proves the bit. Aliases (`F51` → `F051`, `P82` → `P082`) resolve Welldana spellings. Booklet F19 is the inverter temperature probe (bit `2076.3`).

PC1002 profiles add `service_menu.file` (`_service_menu_pc1002.json`). Writable rows have `label`, `min`, `max`, `default`. Writes stay off until the `service_menu_writes` option.

The card Settings dialog (and optional `spo-pool-heat-pump-settings-card`) plus `spo_pool_heat_pump/parameters/*` WebSocket commands build one catalog from `registers` + `service_menu.params`. Risk tiers are derived: a register with `write` is `safe`; a writable service-menu row is `service_menu`; everything else is `readonly`. `group` and `app` are display metadata. Service-menu values are not Home Assistant entities. The panel clock (3015–3017) is read-only.

`tools/simulator` (in this repo, not installed by HACS) encodes a live `SimUnit` by walking that same map (the inverse of `apply_map`) so a new profile key cannot drift from the integration. Seed settings pages from service-menu `default` values. Dump-accurate replay is lab-only (`../protocol-analysis/`, not published with this repo).

## Checklist for a PR

1. One JSON file named `{brand}_{product}_{family}.json` (`identity.id` matches).
2. A dump or published map in `source`.
3. `fixtures.frames` that profile tests can CRC-check.
4. No leftover v1 keys (`map`, `capabilities`, `example_frames`, `kind`, `bits_file`, `params_file`).
5. Mark `community` until someone with the hardware confirms.

## Shipped profiles

| id | Brand | Model | Family | Verification |
| --- | --- | --- | --- | --- |
| `mida_cosma_pc1002` | MIDA | Cosma | pc1002 | verified (dump 20260906_104432; booklet Cosma 13) |
| `hayward_pc1002` | Hayward | PC1002 | pc1002 | community |
| `phnix_mini_pc1002` | PHNIX | Mini | pc1002 | community |
| `fairland_pc1004_cn13` | Fairland | PC1004 CN13 | pc1004 | community |
| `fairland_ips_pro_coils` | Fairland | IPS Pro | fairland_coils | community |
| `unknown_dump_only` | Unknown | Dump only | listen | experimental (no map) |

Detection: 5 s listen for a 2001×90 broadcast. Firmware 713/772 → MIDA Cosma; Mini firmware at 2017 → PHNIX Mini; any other 2001 → Hayward (user can override). Silent bus probes slave 50 FC03 1011×3, then slave 1 FC01 coil 0. If nothing matches, the picker suggests **dump only**. Old ids (`cosmo_pc1002`, `phnix_mini_rs485`, `fairland_legacy_coils`) still load.

## Same bus, no extra JSON

A new file is only for a **different map or talk pattern**. Same-board badges go in `also_sold_as`. Pick the family profile:

| Badge on the case | Pick |
| --- | --- |
| MIDA Cosma, Azuro, Mountfield | `mida_cosma_pc1002` |
| Hayward, Oasis, Warmpool, ECPI, irriPool | `hayward_pc1002` |
| PHNIX Mini / SuperMini / SpecialLine, Thermotec | `phnix_mini_pc1002` |
| Fairland / Norsup CN13 (slave 50, poll) | `fairland_pc1004_cn13` |
| Fairland IPS Pro / InverX / IPHCR (old coils) | `fairland_ips_pro_coils` |
| Not listed / silent or unknown bus | `unknown_dump_only` |

Oasis publishes the PC1002 inverter manual. Azuro R32 (Mountfield) sniffs the same `2001×90` broadcast and slave-2 slot. Warmpool / ECPI / irriPool are the Hayward ESPHome bus.

## Do not add (different wire)

AquaTemp on the phone does **not** prove this RS-485 map.

| Seen as | Why not |
| --- | --- |
| Hayward EnergyLine Pro, Trevium, Majestic, CPAC, Poolex Dreamline (NET) | PC1000/PC1001 single-wire `NET`, not Modbus |
| Poolex Jetline, Poolstar D1 | Custom UART frames, not 10xx/20xx |
| Welldana Aquagreen | Different Modbus (inverter slave `0xAA`) |
| Welldana EasyLine, PHNIX commercial / MegaLine | Unproven or 4800 / other addresses |
| MIDA Joy, Poolsana InverPro | AquaTemp **cloud**; some boards are PC1001 |
| Fairland iGarden, Tuya SmartPool, Warmlink house R290 | Cloud / other T-maps |

Do not invent a bus COP. Register 2040 is shown only when the controller publishes a non-zero value. A calculated COP from a user-typed m³/h flow is a Home Assistant option, not a profile register. Do not add cloud APIs here. Do not pour `protocol.json` into a profile — cite only the registers Home Assistant uses.
