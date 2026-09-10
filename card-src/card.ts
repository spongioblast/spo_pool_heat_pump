import { LitElement, html, unsafeCSS, type PropertyValues } from "lit";
import hostCss from "./host.css";
import waveCss from "./wave3.css";
import { accent, circuitSvg, f1, flow, sectionSvg, type CardState } from "./drawing";
import {
  PoolHeatPumpCardEditor,
  PoolHeatPumpSettingsCardEditor,
  animationEnabled,
  settingsEnabled,
  type CardConfig,
} from "./editor";
import {
  emptyParametersView,
  isAdmin,
  type HassWS,
  type ParametersView,
} from "./parameters";
import { emptyDumpView, type DumpView } from "./dump";
import { ParameterHost, SettingsPanel } from "./settings-panel";

const styles = `${hostCss}\n${waveCss}`;
const NUDGE_DEBOUNCE_MS = 1000;
const NUDGE_STICK_MS = 5000;

type HassState = { state: string; attributes: Record<string, unknown>; entity_id: string };
type Hass = HassWS & {
  states: Record<string, HassState>;
  entities?: Record<string, { device_id?: string; translation_key?: string; platform?: string }>;
  callService: (domain: string, service: string, data: Record<string, unknown>) => void;
  auth?: { data?: { access_token?: string } };
};

const MINUS = html`<svg viewBox="0 0 24 24"><path d="M6 12h12"/></svg>`;
const PLUS = html`<svg viewBox="0 0 24 24"><path d="M12 6v12M6 12h12"/></svg>`;
const PW = html`<svg viewBox="0 0 24 24"><path d="M12 3v9"/><path d="M6.3 6.3a8 8 0 1 0 11.4 0"/></svg>`;
const FEATHER = html`<svg viewBox="0 0 24 24"><path d="M20.2 12.2a6 6 0 0 0-8.5-8.5L5 10.5V19h8.5z"/><path d="M16 8 2 22"/><path d="M17.5 15H9"/></svg>`;
const TUNE = html`<svg viewBox="0 0 24 24"><path d="M4 8h9M17 8h3"/><circle cx="15" cy="8" r="2"/><path d="M4 16h3M11 16h9"/><circle cx="9" cy="16" r="2"/></svg>`;

const STATUS_ACTION: Record<string, CardState["action"]> = {
  "Warming up": "warmup",
  Starting: "precool",
  Heating: "heating",
  Cooling: "cooling",
  Off: "off",
  "Dump only": "off",
};

function num(st?: HassState): number | null {
  if (!st || st.state === "unavailable" || st.state === "unknown") return null;
  const n = Number(st.state);
  return Number.isFinite(n) ? n : null;
}

function firstClimate(hass: Hass): string | undefined {
  return (
    Object.keys(hass.states || {}).find((id) => id.startsWith("climate.") && hass.entities?.[id]?.platform === "spo_pool_heat_pump") ||
    Object.keys(hass.states || {}).find((id) => id.startsWith("climate."))
  );
}

class PoolHeatPumpCard extends LitElement {
  static styles = unsafeCSS(styles);
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
    _params: { state: true },
    _dialogOpen: { state: true },
    _targetLocal: { state: true },
    _dump: { state: true },
  };
  hass?: Hass;
  _config: CardConfig = {};
  _params: ParametersView = emptyParametersView();
  _dump: DumpView = emptyDumpView();
  _dialogOpen = false;
  _targetLocal: number | null = null;
  private _svgId = `ph${Math.random().toString(36).slice(2, 8)}`;
  private _host = new ParameterHost();
  private _settings = new SettingsPanel();
  private _sibEntities?: Hass["entities"];
  private _sibDevice?: string;
  private _sibIds: string[] = [];
  private _nudgeTimer: number | null = null;
  private _nudgeClearTimer: number | null = null;

  static getConfigElement() {
    return document.createElement("spo-pool-heat-pump-card-editor");
  }

  static getStubConfig(hass: Hass) {
    const stub: CardConfig & { type: string } = {
      type: "custom:spo-pool-heat-pump-card",
      schematic: "circuit",
      animation: true,
      settings: true,
    };
    const climate = firstClimate(hass);
    if (climate) stub.entity = climate;
    return stub;
  }

  setConfig(config: CardConfig) {
    this._config = { schematic: "circuit", ...config };
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, rows: 8, min_columns: 6, min_rows: 6 };
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._nudgeTimer != null) {
      window.clearTimeout(this._nudgeTimer);
      this._nudgeTimer = null;
      if (this._targetLocal != null) {
        this.call("climate", "set_temperature", { temperature: this._targetLocal });
      }
    }
    if (this._nudgeClearTimer != null) {
      window.clearTimeout(this._nudgeClearTimer);
      this._nudgeClearTimer = null;
    }
    this._settings.stopPoll();
  }

  protected shouldUpdate(changed: PropertyValues): boolean {
    if (changed.has("_config") || changed.has("_params") || changed.has("_dialogOpen") || changed.has("_targetLocal") || changed.has("_dump")) {
      return true;
    }
    if (changed.has("hass")) {
      return this._hassRelevantChanged(changed.get("hass") as Hass | undefined, this.hass);
    }
    return true;
  }

  protected willUpdate(_changed: PropertyValues) {
    if (this._targetLocal == null) return;
    const climate = this.hass?.states[this._config.entity || ""];
    const ha = Number(climate?.attributes.temperature ?? NaN);
    const step = Number(climate?.attributes.target_temp_step ?? 0.5) || 0.5;
    if (Number.isFinite(ha) && Math.abs(ha - this._targetLocal) < step / 2) {
      this._targetLocal = null;
      if (this._nudgeClearTimer != null) {
        window.clearTimeout(this._nudgeClearTimer);
        this._nudgeClearTimer = null;
      }
    }
  }

  private _hassRelevantChanged(oldHass: Hass | undefined, hass: Hass | undefined): boolean {
    if (!oldHass || !hass) return true;
    if (oldHass.user !== hass.user || oldHass.entities !== hass.entities) return true;
    const entity = this._config.entity;
    if (!entity) return oldHass.states !== hass.states;
    for (const id of [entity, ...this.siblingIds(hass, entity)]) {
      if (oldHass.states[id] !== hass.states[id]) return true;
    }
    return false;
  }

  /** Sibling ids from the entity registry; cached until hass.entities is replaced. */
  private siblingIds(hass: Hass, entityId: string): string[] {
    const entities = hass.entities;
    const device = entities?.[entityId]?.device_id;
    if (!device) return [];
    if (this._sibEntities === entities && this._sibDevice === device) return this._sibIds;
    const ids: string[] = [];
    for (const [eid, em] of Object.entries(entities || {})) {
      if (em?.device_id === device) ids.push(eid);
    }
    this._sibEntities = entities;
    this._sibDevice = device;
    this._sibIds = ids;
    return ids;
  }

  private siblings(hass: Hass, entityId: string): Record<string, HassState> {
    const out: Record<string, HassState> = {};
    for (const eid of this.siblingIds(hass, entityId)) {
      const st = hass.states[eid];
      if (!st) continue;
      const em = hass.entities?.[eid];
      out[em?.translation_key || eid.split(".").pop() || eid] = st;
    }
    return out;
  }

  private view(): CardState | null {
    const hass = this.hass;
    const entity = this._config.entity;
    if (!hass || !entity) return null;
    const climate = hass.states[entity];
    if (!climate) return null;
    const sib = this.siblings(hass, entity);
    const available = climate.state !== "unavailable";
    const mode = climate.state === "heat_cool" ? "auto" : climate.state;
    const power = available && climate.state !== "off";
    const silent = climate.attributes.preset_mode === "silent";
    const faultSt = sib.fault;
    const fault = faultSt?.state === "on"
      ? String(faultSt.attributes.code || climate.attributes.fault || "fault")
      : (climate.attributes.fault ? String(climate.attributes.fault) : null);
    const faultText = fault
      ? String(climate.attributes.fault_text || faultSt?.attributes.text || "")
      : "";
    const liveInlet = Number(climate.attributes.current_temperature ?? NaN);
    const sensorInlet = num(sib.inlet);
    const inlet = sensorInlet ?? (Number.isFinite(liveInlet) ? liveInlet : null);
    const outlet = num(sib.outlet);
    const ambient = num(sib.ambient);
    const haSetpoint = Number(climate.attributes.temperature ?? NaN);
    const setpoint = this._targetLocal ?? (Number.isFinite(haSetpoint) ? haSetpoint : NaN);
    const kw = num(sib.power);
    const kwh24 = num(sib.energy_24h);
    const pct = num(sib.compressor);
    const fanRpm = num(sib.fan);
    const caps = {
      cool: Array.isArray(climate.attributes.hvac_modes) && (climate.attributes.hvac_modes as string[]).includes("cool"),
      auto: Array.isArray(climate.attributes.hvac_modes) && (climate.attributes.hvac_modes as string[]).includes("heat_cool"),
      silent: Array.isArray(climate.attributes.preset_modes) && (climate.attributes.preset_modes as string[]).includes("silent"),
      power: kw != null,
      energy: kwh24 != null,
      compressor: pct != null,
      ambient: ambient != null,
      fan: fanRpm != null,
    };
    const status = !available ? "No data" : String(climate.attributes.activity || "No data");
    const action = STATUS_ACTION[status] || "idle";
    // Flow follows the real pump output; the compressor states imply it when the
    // pump binary sensor is missing from the profile.
    const pump = sib.pump_running ? sib.pump_running.state === "on"
      : action === "heating" || action === "cooling" || action === "warmup" || action === "precool";
    return {
      available, power, mode, action,
      inlet: inlet != null && Number.isFinite(inlet) ? inlet : null,
      inletLive: Number.isFinite(liveInlet) ? liveInlet : (inlet != null && Number.isFinite(inlet) ? inlet : null),
      outlet, ambient,
      setpoint: Number.isFinite(setpoint) ? setpoint : null,
      kw, kwh24, pct, fanRpm, silent, pump, fault, faultText: faultText || null, status,
      cop: (() => {
        const raw = Number(climate.attributes.cop);
        return Number.isFinite(raw) && raw !== 0 ? raw : null;
      })(),
      dumpOnly: climate.attributes.dump_only === true || status === "Dump only",
      caps,
    };
  }

  private call(domain: string, service: string, data: Record<string, unknown>) {
    this.hass?.callService(domain, service, { entity_id: this._config.entity, ...data });
  }

  private setMode(mode: string) {
    const hvac = mode === "auto" ? "heat_cool" : mode;
    this.call("climate", "set_hvac_mode", { hvac_mode: hvac });
  }

  private nudge(delta: number) {
    const climate = this.hass?.states[this._config.entity || ""];
    const min = Number(climate?.attributes.min_temp ?? 8);
    const max = Number(climate?.attributes.max_temp ?? 40);
    const step = Number(climate?.attributes.target_temp_step ?? 0.5) || 0.5;
    const current = this._targetLocal ?? Number(climate?.attributes.temperature ?? NaN);
    if (!Number.isFinite(current)) return;
    const stepped = Math.round((current + delta) / step) * step;
    this._targetLocal = Math.min(max, Math.max(min, stepped));
    if (this._nudgeClearTimer != null) {
      window.clearTimeout(this._nudgeClearTimer);
      this._nudgeClearTimer = null;
    }
    if (this._nudgeTimer != null) window.clearTimeout(this._nudgeTimer);
    this._nudgeTimer = window.setTimeout(() => {
      this._nudgeTimer = null;
      if (this._targetLocal == null) return;
      this.call("climate", "set_temperature", { temperature: this._targetLocal });
      this._nudgeClearTimer = window.setTimeout(() => {
        this._nudgeClearTimer = null;
        this._targetLocal = null;
      }, NUDGE_STICK_MS);
    }, NUDGE_DEBOUNCE_MS);
  }

  private openSettings() {
    this._dialogOpen = true;
    if (this.view()?.dumpOnly) {
      this._dump = { ...this._dump, pane: "dump" };
    }
    this._host.load(this.hass, this._config.entity, this);
    this._settings.refreshDump(this);
    this._settings.startPoll(this);
  }

  private closeSettings() {
    this._dialogOpen = false;
    this._settings.stopPoll();
  }

  private openMoreInfo() {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        bubbles: true,
        composed: true,
        detail: { entityId: this._config.entity },
      }),
    );
  }

  protected render() {
    const s = this.view();
    if (!s) return html`<ha-card class="card"><div class="w3">No climate entity</div></ha-card>`;
    const f = flow(s);
    const schematic = this._config.schematic === "section" ? "section" : "circuit";
    const drawing = schematic === "section" ? sectionSvg(s, this._svgId) : circuitSvg(s, this._svgId);
    const facts: [string, string, string][] = [];
    if (s.caps.power) facts.push(["Power", f1(s.kw), "kW"]);
    if (s.caps.energy) facts.push(["Last 24 h", f1(s.kwh24), "kWh"]);
    if (s.caps.compressor) facts.push(["Compressor", String(s.pct ?? "–"), "%"]);
    if (s.caps.fan) facts.push(["Fan", s.fanRpm == null ? "–" : String(s.fanRpm), "rpm"]);
    const modes = ["heat", ...(s.caps.auto ? ["auto"] : []), ...(s.caps.cool ? ["cool"] : [])];
    const showTune = settingsEnabled(this._config) && isAdmin(this.hass);
    return html`
      <ha-card class="card ${schematic}"
        data-available=${s.available}
        data-action=${s.available && s.power ? (s.action === "warmup" ? "heating" : s.action === "precool" ? "cooling" : s.action) : "off"}
        data-pump=${s.pump && s.power && s.available}
        data-silent=${s.silent}
        data-flow=${animationEnabled(this._config)}
        style=${`--inC:${f.inC};--outC:${f.outC};--accent:${accent(s)};`}>
        <div class="w3 ${schematic}">
          <div class="top">
            <span class="eyebrow" @click=${() => this.openMoreInfo()}>Pool temperature</span>
            <div class="status-block">
              <span class="eyebrow status"><i></i>${s.status}</span>
              ${s.fault && s.faultText ? html`<span class="fault-why">${s.faultText}</span>` : ""}
            </div>
          </div>
          <div class="hero">
            <div class="big"><span class="num">${f1(s.inletLive ?? s.inlet)}</span><span class="unit">°C</span></div>
            ${s.dumpOnly
              ? html`<div class="target"><span class="eyebrow">No map</span><span class="val">Use Settings → Bus dump</span></div>`
              : html`<div class="target">
              <span class="eyebrow">Target</span>
              <button class="ib" title="Lower target" @click=${() => this.nudge(-0.5)}>${MINUS}</button>
              <span class="val"><span class="num">${f1(s.setpoint)}</span><span class="unit">°</span></span>
              <button class="ib" title="Raise target" @click=${() => this.nudge(0.5)}>${PLUS}</button>
            </div>`}
          </div>
          ${drawing}
          <div class="facts">${facts.map(([k, v, u]) => html`<div class="fact"><div class="v">${v}<small>${u}</small></div><span class="eyebrow">${k}</span></div>`)}</div>
          <div class="modes">
            ${s.dumpOnly ? "" : html`<div class="seg">${modes.map((m) => html`<button class=${s.power && s.mode === m ? "on" : ""} @click=${() => this.setMode(m)}>${m === "heat" ? "Heat" : m === "cool" ? "Cool" : "Auto"}</button>`)}</div>`}
            <span class="sp"></span>
            ${showTune ? html`<button class="ib params-open" title="Heat pump settings" @click=${() => this.openSettings()}>${TUNE}</button>` : ""}
            ${s.dumpOnly || !s.caps.silent ? "" : html`<button class="ib quiet ${s.silent ? "on" : ""}" title="Quiet mode"
              @click=${() => this.call("climate", "set_preset_mode", { preset_mode: s.silent ? "none" : "silent" })}>${FEATHER}</button>`}
            ${s.dumpOnly ? "" : html`<button class="ib pw ${s.power ? "on" : ""}" title="Power"
              @click=${() => this.call("climate", s.power ? "turn_off" : "turn_on", {})}>${PW}</button>`}
          </div>
          ${s.available ? "" : html`<div class="stale"><span><i></i>No data from heat pump for 8 s</span></div>`}
        </div>
      </ha-card>
      ${this._dialogOpen ? html`
        <ha-dialog open hideActions @closed=${() => this.closeSettings()}>
          <span slot="heading">Settings</span>
          ${this._settings.tabs(this)}
          ${this._settings.body(this)}
        </ha-dialog>
      ` : ""}
    `;
  }
}

class PoolHeatPumpSettingsCard extends LitElement {
  static styles = unsafeCSS(styles);
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
    _params: { state: true },
    _dump: { state: true },
  };
  hass?: Hass;
  _config: CardConfig = {};
  _params: ParametersView = emptyParametersView();
  _dump: DumpView = emptyDumpView();
  private _host = new ParameterHost();
  private _settings = new SettingsPanel();
  private _loadedFor = "";

  static getConfigElement() {
    return document.createElement("spo-pool-heat-pump-settings-card-editor");
  }

  static getStubConfig(hass: Hass) {
    const stub: CardConfig & { type: string } = { type: "custom:spo-pool-heat-pump-settings-card" };
    const climate = firstClimate(hass);
    if (climate) stub.entity = climate;
    return stub;
  }

  setConfig(config: CardConfig) {
    this._config = { ...config };
    this._loadedFor = "";
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._settings.stopPoll();
  }

  getCardSize() {
    return 12;
  }

  getGridOptions() {
    return { columns: 12, rows: 12, min_columns: 6, min_rows: 4 };
  }

  protected updated() {
    const entity = this._config.entity || "";
    if (!isAdmin(this.hass) || !this.hass || !entity || this._loadedFor === entity) return;
    this._settings.stopPoll();
    this._loadedFor = entity;
    this._host.load(this.hass, entity, this);
    this._settings.refreshDump(this);
    this._settings.startPoll(this);
  }

  protected render() {
    if (!isAdmin(this.hass)) {
      return html`<ha-card class="params-card"><div class="w3">Administrator only</div></ha-card>`;
    }
    if (!this._config.entity) {
      return html`<ha-card class="params-card"><div class="w3">No climate entity</div></ha-card>`;
    }
    return html`
      <ha-card class="params-card">
        <div class="params-card-head">
          <span class="eyebrow">Settings</span>
          <button class="params-refresh" ?disabled=${this._params.busy} @click=${() => {
            this._loadedFor = "";
            this._host.load(this.hass, this._config.entity, this);
            this._settings.refreshDump(this);
          }}>Refresh</button>
        </div>
        ${this._settings.tabs(this)}
        ${this._settings.body(this)}
      </ha-card>
    `;
  }
}

function defineEl(name: string, ctor: CustomElementConstructor) {
  if (!customElements.get(name)) customElements.define(name, ctor);
}

defineEl("spo-pool-heat-pump-card", PoolHeatPumpCard);
defineEl("spo-pool-heat-pump-card-editor", PoolHeatPumpCardEditor);
defineEl("spo-pool-heat-pump-settings-card", PoolHeatPumpSettingsCard);
defineEl("spo-pool-heat-pump-settings-card-editor", PoolHeatPumpSettingsCardEditor);

function getEntitySuggestion(hass: Hass, entityId: string) {
  if (!entityId.startsWith("climate.")) return null;
  const platform = hass.entities?.[entityId]?.platform;
  if (platform && platform !== "spo_pool_heat_pump") return null;
  return {
    config: {
      type: "custom:spo-pool-heat-pump-card",
      entity: entityId,
      schematic: "circuit",
      animation: true,
      settings: true,
    },
  };
}

type CustomCardsWindow = { customCards: object[] };
const win = window as unknown as CustomCardsWindow;
win.customCards = win.customCards || [];
win.customCards.push({
  type: "spo-pool-heat-pump-card",
  name: "SPO Pool Heat Pump",
  description: "Circuit / section schematic for the SPO Pool Heat Pump climate entity",
  preview: true,
  getEntitySuggestion,
});
win.customCards.push({
  type: "spo-pool-heat-pump-settings-card",
  name: "SPO Pool Heat Pump settings",
  description: "Full register and service-menu catalog for a SPO Pool Heat Pump climate entity",
  preview: false,
});
