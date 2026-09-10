import { html, type TemplateResult } from "lit";
import type { CardConfig } from "./editor";
import {
  commitParameter,
  emptyParametersView,
  fetchCatalog,
  renderParameterBrowser,
  type HassWS,
  type ParamRow,
  type ParametersView,
} from "./parameters";
import {
  deleteDump,
  downloadDump,
  fetchDumpStatus,
  renderDumpPanel,
  startDump,
  stopDump,
  type DumpView,
} from "./dump";

type SettingsHass = HassWS & { auth?: { data?: { access_token?: string } } };

export type SettingsHost = {
  hass?: SettingsHass;
  _config: CardConfig;
  _params: ParametersView;
  _dump: DumpView;
  _host: ParameterHost;
};

export class ParameterHost {
  view: ParametersView = emptyParametersView();
  private risk = { current: false };
  private _gen = 0;

  apply(host: { _params: ParametersView }, patch: Partial<ParametersView>) {
    host._params = { ...host._params, ...patch };
    this.view = host._params;
  }

  load(hass: SettingsHass | undefined, entity: string | undefined, host: { _params: ParametersView }) {
    if (!hass || !entity) return;
    const g = ++this._gen;
    void fetchCatalog(hass, entity, (patch) => {
      if (g !== this._gen) return;
      this.apply(host, patch);
    });
  }

  commit(
    hass: SettingsHass | undefined,
    entity: string | undefined,
    host: { _params: ParametersView },
    row: ParamRow,
    value: unknown,
  ) {
    if (!hass || !entity) return;
    void commitParameter(hass, entity, row, value, host._params, (patch) => this.apply(host, patch), this.risk);
  }
}

export class SettingsPanel {
  private timer: number | null = null;
  private _gen = 0;

  applyDump(host: SettingsHost, patch: Partial<DumpView>) {
    host._dump = { ...host._dump, ...patch };
  }

  private applyDumpIf(host: SettingsHost, g: number, patch: Partial<DumpView>) {
    if (g !== this._gen) return;
    this.applyDump(host, patch);
  }

  refreshDump(host: SettingsHost) {
    if (!host.hass || !host._config.entity) return;
    const g = this._gen;
    void fetchDumpStatus(host.hass, host._config.entity, (patch) => this.applyDumpIf(host, g, patch));
  }

  startPoll(host: SettingsHost) {
    if (this.timer != null) {
      window.clearInterval(this.timer);
      this.timer = null;
    }
    this.timer = window.setInterval(() => {
      if (host._dump.pane === "dump" || host._dump.status?.running) this.refreshDump(host);
    }, 2000);
  }

  stopPoll() {
    this._gen++;
    if (this.timer != null) {
      window.clearInterval(this.timer);
      this.timer = null;
    }
  }

  tabs(host: SettingsHost): TemplateResult {
    return html`
      <div class="settings-tabs">
        <button class=${host._dump.pane === "params" ? "on" : ""} @click=${() => this.applyDump(host, { pane: "params" })}>Parameters</button>
        <button class=${host._dump.pane === "dump" ? "on" : ""} @click=${() => { this.applyDump(host, { pane: "dump" }); this.refreshDump(host); }}>Bus dump</button>
      </div>
    `;
  }

  body(host: SettingsHost): TemplateResult {
    if (host._dump.pane === "dump") {
      return renderDumpPanel({
        view: host._dump,
        onMinutes: (value) => this.applyDump(host, { minutes: value }),
        onUntilStop: (value) => this.applyDump(host, { untilStop: value }),
        onNote: (value) => this.applyDump(host, { note: value }),
        onWrites: (value) => this.applyDump(host, { includeWrites: value }),
        onHelp: () => this.applyDump(host, { helpOpen: !host._dump.helpOpen }),
        onStart: () => {
          if (!host.hass || !host._config.entity) return;
          const g = this._gen;
          void startDump(host.hass, host._config.entity, host._dump, (patch) => this.applyDumpIf(host, g, patch));
        },
        onStop: () => {
          if (!host.hass || !host._config.entity) return;
          const g = this._gen;
          void stopDump(host.hass, host._config.entity, (patch) => this.applyDumpIf(host, g, patch));
        },
        onDelete: (name) => {
          if (!host.hass || !host._config.entity) return;
          const g = this._gen;
          void deleteDump(host.hass, host._config.entity, name, (patch) => this.applyDumpIf(host, g, patch));
        },
        onDownload: (name) => {
          if (!host.hass) return;
          const g = this._gen;
          void downloadDump(host.hass, name).catch((err) => this.applyDumpIf(host, g, { error: String(err) }));
        },
      });
    }
    return renderParameterBrowser({
      config: host._config,
      view: host._params,
      onFilter: (value) => { host._params = { ...host._params, filter: value }; },
      onGroup: (value) => { host._params = { ...host._params, group: value }; },
      onCommit: (row, value) => host._host.commit(host.hass, host._config.entity, host, row, value),
      onPending: (key, value) => {
        host._params = { ...host._params, pending: { ...host._params.pending, [key]: value } };
      },
    });
  }
}
