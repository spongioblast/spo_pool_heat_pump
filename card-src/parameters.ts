import { html, type TemplateResult } from "lit";
import type { CardConfig } from "./editor";

export type ParamRow = {
  key: string;
  label: string;
  group: string;
  group_label?: string;
  app?: string | null;
  unit?: string | null;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  type: string;
  options?: string[] | null;
  tier: "safe" | "service_menu" | "readonly";
  value: unknown;
  default?: unknown;
};

export type ParamPayload = {
  parameters: ParamRow[];
  service_menu_writes: boolean;
  verification?: string;
  profile?: string;
  groups?: string[];
};

export type ParametersView = {
  filter: string;
  group: string;
  data: ParamPayload | null;
  error: string;
  busy: boolean;
  pending: Record<string, string>;
};

export type HassWS = {
  callWS?: (msg: Record<string, unknown>) => Promise<ParamPayload & { ok?: boolean }>;
  user?: { is_admin?: boolean };
};

export const SERVICE_MENU_RISK =
  "⚠ These service settings can damage or brick the unit. Do not change them unless you know the OEM values.";
export const SERVICE_MENU_DISABLED = "Enable changing service settings in the integration options first";
export const SERVICE_MENU_OPTIONS_HINT =
  "⚠ Service settings stay locked. Enable them in the integration options only if you know the OEM values — wrong H/F/D numbers can brick the unit.";

export function isAdmin(hass?: HassWS): boolean {
  return hass?.user?.is_admin === true;
}

export function emptyParametersView(): ParametersView {
  return { filter: "", group: "", data: null, error: "", busy: false, pending: {} };
}

function fmt(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "on" : "off";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function displayValue(row: ParamRow): string {
  const text = fmt(row.value);
  return row.unit && text !== "—" ? `${text} ${row.unit}` : text;
}

function matches(row: ParamRow, filter: string): boolean {
  if (!filter) return true;
  const q = filter.toLowerCase();
  return [row.key, row.label, row.app || "", row.group, String(row.value ?? "")]
    .join(" ")
    .toLowerCase()
    .includes(q);
}

function grouped(payload: ParamPayload, filter: string, only?: string[]): [string, ParamRow[]][] {
  const wanted = only && only.length ? new Set(only.map(String)) : null;
  const order = payload.groups && payload.groups.length
    ? payload.groups
    : [...new Set(payload.parameters.map((r) => r.group))];
  const out: [string, ParamRow[]][] = [];
  for (const group of order) {
    if (wanted && !wanted.has(group)) continue;
    const rows = payload.parameters.filter((r) => r.group === group && matches(r, filter));
    if (rows.length) out.push([group, rows]);
  }
  return out;
}

export async function fetchCatalog(
  hass: HassWS,
  entity: string,
  apply: (patch: Partial<ParametersView>) => void,
): Promise<void> {
  if (!hass.callWS) {
    apply({ error: "WebSocket API unavailable", busy: false });
    return;
  }
  apply({ busy: true, error: "" });
  try {
    // Cached catalog first, then a bus re-read so the dialog is not empty while pages load.
    const listed = await hass.callWS({ type: "spo_pool_heat_pump/parameters/list", entity_id: entity });
    apply({ data: listed, busy: false, pending: {} });
    const refreshed = await hass.callWS({ type: "spo_pool_heat_pump/parameters/refresh", entity_id: entity });
    if (refreshed?.parameters) apply({ data: refreshed, busy: false, pending: {} });
  } catch (err) {
    apply({ busy: false, error: err instanceof Error ? err.message : String(err) });
  }
}

export async function commitParameter(
  hass: HassWS,
  entity: string,
  row: ParamRow,
  value: unknown,
  view: ParametersView,
  apply: (patch: Partial<ParametersView>) => void,
  riskOk: { current: boolean },
): Promise<boolean> {
  if (row.tier === "service_menu") {
    if (!view.data?.service_menu_writes) {
      apply({ error: SERVICE_MENU_DISABLED });
      return false;
    }
    if (!riskOk.current && !window.confirm(SERVICE_MENU_RISK)) return false;
    riskOk.current = true;
  }
  if (!hass.callWS) {
    apply({ error: "WebSocket API unavailable" });
    return false;
  }
  apply({ busy: true, error: "" });
  try {
    const data = await hass.callWS({
      type: "spo_pool_heat_pump/parameters/set",
      entity_id: entity,
      key: row.key,
      value,
    });
    const patched = data.parameters
      ? {
          ...data,
          parameters: data.parameters.map((item) => (item.key === row.key ? { ...item, value } : item)),
        }
      : data;
    apply({ data: patched, busy: false, pending: {} });
    return true;
  } catch (err) {
    apply({ busy: false, error: err instanceof Error ? err.message : String(err) });
    return false;
  }
}

export function renderParameterBrowser(args: {
  config: CardConfig;
  view: ParametersView;
  onFilter: (value: string) => void;
  onGroup: (value: string) => void;
  onCommit: (row: ParamRow, value: unknown) => void;
  onPending: (key: string, value: string) => void;
}): TemplateResult {
  const view = args.view;
  const groups = view.data ? grouped(view.data, view.filter, args.config.parameters_groups) : [];
  const selected = view.group && groups.some(([name]) => name === view.group) ? view.group : groups[0]?.[0] || "";
  const rows = groups.find(([name]) => name === selected)?.[1] || [];
  const locked = view.data && !view.data.service_menu_writes;
  return html`
    <div class="params-browser">
      <input
        class="params-filter"
        type="search"
        placeholder="Filter"
        .value=${view.filter}
        @input=${(e: Event) => args.onFilter((e.target as HTMLInputElement).value)}
      />
      ${groups.length > 1
        ? html`<select
            class="params-groups"
            .value=${selected}
            @change=${(e: Event) => args.onGroup((e.target as HTMLSelectElement).value)}
          >
            ${groups.map(([group, items]) => html`<option value=${group} ?selected=${group === selected}>${items[0]?.group_label || group} (${items.length})</option>`)}
          </select>`
        : ""}
      ${locked ? html`<div class="params-note">${SERVICE_MENU_OPTIONS_HINT}</div>` : ""}
      ${view.busy ? html`<div class="params-note">Reading…</div>` : ""}
      ${view.error ? html`<div class="params-error">${view.error}</div>` : ""}
      ${view.data
        ? html`<div class="params-count">${view.data.parameters.length} parameters${selected ? ` · ${groups.find(([name]) => name === selected)?.[1][0]?.group_label || selected}` : ""}</div>`
        : ""}
      <div class="params-rows">
        ${rows.map((row) => renderRow(row, view, args.onCommit, args.onPending))}
      </div>
    </div>
  `;
}

function renderRow(
  row: ParamRow,
  view: ParametersView,
  onCommit: (row: ParamRow, value: unknown) => void,
  onPending: (key: string, value: string) => void,
): TemplateResult {
  const left = row.app ? `${row.label} · ${row.app}` : row.label;
  const locked = row.tier === "readonly" || (row.tier === "service_menu" && !view.data?.service_menu_writes);
  const reason = row.tier === "service_menu" && !view.data?.service_menu_writes ? SERVICE_MENU_DISABLED : "";
  if (locked) {
    return html`<div class="params-row ${row.tier}">
      <span class="params-label" title=${reason || row.key}>${left}</span>
      <span class="params-val" title=${reason}>${displayValue(row)}</span>
    </div>`;
  }
  const pending = view.pending[row.key];
  const current = pending !== undefined ? pending : row.value == null ? "" : String(row.value);
  if (row.options && row.options.length && row.type !== "u16") {
    return html`<div class="params-row ${row.tier}">
      <span class="params-label">${left}</span>
      <select
        class="params-input"
        .value=${current}
        @change=${(e: Event) => onCommit(row, (e.target as HTMLSelectElement).value)}
      >
        ${row.options.map((opt) => html`<option value=${opt} ?selected=${String(row.value) === opt}>${opt}</option>`)}
      </select>
    </div>`;
  }
  if (row.type === "bool") {
    const on = current === "true" || current === "on" || current === "1";
    return html`<div class="params-row ${row.tier}">
      <span class="params-label">${left}</span>
      <select class="params-input" .value=${on ? "true" : "false"}
        @change=${(e: Event) => onCommit(row, (e.target as HTMLSelectElement).value === "true")}>
        <option value="false">off</option>
        <option value="true">on</option>
      </select>
    </div>`;
  }
  return html`<div class="params-row ${row.tier}">
    <span class="params-label">${left}</span>
    <span class="params-edit">
      <input
        class="params-input"
        type="number"
        step=${row.step ?? 1}
        min=${row.min ?? ""}
        max=${row.max ?? ""}
        .value=${current}
        @input=${(e: Event) => onPending(row.key, (e.target as HTMLInputElement).value)}
        @change=${(e: Event) => onCommit(row, (e.target as HTMLInputElement).value)}
        @keydown=${(e: KeyboardEvent) => {
          if (e.key === "Enter") onCommit(row, (e.target as HTMLInputElement).value);
        }}
      />
      ${row.unit ? html`<small>${row.unit}</small>` : ""}
    </span>
  </div>`;
}
