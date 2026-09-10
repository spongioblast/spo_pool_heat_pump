import { LitElement, html, css } from "lit";

type Hass = { states: Record<string, unknown> };
export type CardConfig = {
  entity?: string;
  schematic?: string;
  animation?: boolean;
  flow_animation?: boolean;
  settings?: boolean;
  parameters_groups?: string[];
};

export function animationEnabled(config: CardConfig): boolean {
  if (config.animation !== undefined) return config.animation !== false;
  if (config.flow_animation !== undefined) return config.flow_animation !== false;
  return true;
}

export function settingsEnabled(config: CardConfig): boolean {
  return config.settings !== false;
}

export class PoolHeatPumpCardEditor extends LitElement {
  static styles = css`
    .row { display: grid; gap: 12px; padding: 4px 0 16px; }
    ha-select, ha-entity-picker, ha-formfield { width: 100%; }
  `;
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
  };
  hass?: Hass;
  _config: CardConfig = {};

  setConfig(config: CardConfig) {
    this._config = { schematic: "circuit", ...config };
  }

  private change(patch: Partial<CardConfig>) {
    const next = { ...this._config, ...patch };
    if (patch.animation !== undefined) delete next.flow_animation;
    this._config = next;
    this.dispatchEvent(new CustomEvent("config-changed", { bubbles: true, composed: true, detail: { config: this._config } }));
  }

  protected render() {
    return html`
      <div class="row">
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this._config.entity || ""}
          .includeDomains=${["climate"]}
          label="Climate entity"
          @value-changed=${(e: CustomEvent) => this.change({ entity: e.detail.value })}
        ></ha-entity-picker>
        <ha-select
          label="Schematic"
          .value=${this._config.schematic || "circuit"}
          @selected=${(e: Event) => {
            const t = e.target as { value?: string };
            if (t.value) this.change({ schematic: t.value });
          }}
          @closed=${(e: Event) => e.stopPropagation()}
        >
          <ha-list-item value="circuit">Circuit (open basin)</ha-list-item>
          <ha-list-item value="section">Section (cutaway)</ha-list-item>
        </ha-select>
        <ha-formfield alignEnd spaceBetween label="Animation">
          <ha-switch
            .checked=${animationEnabled(this._config)}
            @change=${(e: Event) => {
              const t = e.target as { checked?: boolean };
              this.change({ animation: t.checked !== false });
            }}
          ></ha-switch>
        </ha-formfield>
        <ha-formfield alignEnd spaceBetween label="Show heat pump settings">
          <ha-switch
            .checked=${settingsEnabled(this._config)}
            @change=${(e: Event) => {
              const t = e.target as { checked?: boolean };
              this.change({ settings: t.checked !== false });
            }}
          ></ha-switch>
        </ha-formfield>
      </div>
    `;
  }
}

export class PoolHeatPumpSettingsCardEditor extends LitElement {
  static styles = css`
    .row { display: grid; gap: 12px; padding: 4px 0 16px; }
    ha-entity-picker { width: 100%; }
  `;
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
  };
  hass?: Hass;
  _config: CardConfig = {};

  setConfig(config: CardConfig) {
    this._config = { ...config };
  }

  private change(patch: Partial<CardConfig>) {
    this._config = { ...this._config, ...patch };
    this.dispatchEvent(new CustomEvent("config-changed", { bubbles: true, composed: true, detail: { config: this._config } }));
  }

  protected render() {
    return html`
      <div class="row">
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this._config.entity || ""}
          .includeDomains=${["climate"]}
          label="Climate entity"
          @value-changed=${(e: CustomEvent) => this.change({ entity: e.detail.value })}
        ></ha-entity-picker>
      </div>
    `;
  }
}
