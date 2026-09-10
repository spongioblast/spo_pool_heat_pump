import { html, type TemplateResult } from "lit";
import type { HassWS } from "./parameters";

export type DumpFile = {
  name: string;
  bin: string | null;
  size: number;
  started: string | null;
  note: string;
  kind: string;
};

export type DumpStatus = {
  running: boolean;
  started: string | null;
  bytes: number;
  elapsed_s: number;
  remaining_s: number | null;
  duration_s: number | null;
  note: string;
  include_writes: boolean;
  stop_reason: string | null;
  files: DumpFile[];
  limits: {
    rotate_bytes: number;
    keep_files: number;
    session_cap_bytes: number;
    dir_cap_bytes: number;
    max_duration_s: number;
    dir_used: number;
    dir_remaining: number;
  };
};

export type DumpView = {
  pane: "params" | "dump";
  minutes: number;
  untilStop: boolean;
  note: string;
  includeWrites: boolean;
  helpOpen: boolean;
  status: DumpStatus | null;
  error: string;
  busy: boolean;
};

type HassDump = HassWS & {
  auth?: { data?: { access_token?: string } };
};

export function emptyDumpView(): DumpView {
  return {
    pane: "params",
    minutes: 15,
    untilStop: false,
    note: "",
    includeWrites: true,
    helpOpen: false,
    status: null,
    error: "",
    busy: false,
  };
}

function mb(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtTime(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m ? `${m}m ${r}s` : `${r}s`;
}

async function callDump(hass: HassDump, type: string, extra: Record<string, unknown> = {}) {
  if (!hass.callWS) throw new Error("WebSocket unavailable");
  return hass.callWS({ type, ...extra }) as Promise<DumpStatus>;
}

export async function fetchDumpStatus(
  hass: HassDump,
  entity: string,
  apply: (patch: Partial<DumpView>) => void,
) {
  try {
    const status = await callDump(hass, "spo_pool_heat_pump/dump/status", { entity_id: entity });
    apply({ status, error: "" });
  } catch (err) {
    apply({ error: err instanceof Error ? err.message : String(err) });
  }
}

export async function startDump(
  hass: HassDump,
  entity: string,
  view: DumpView,
  apply: (patch: Partial<DumpView>) => void,
) {
  apply({ busy: true, error: "" });
  try {
    const minutes = Math.min(120, Math.max(1, Number(view.minutes) || 15));
    const status = await callDump(hass, "spo_pool_heat_pump/dump/start", {
      entity_id: entity,
      duration_s: view.untilStop ? 0 : minutes * 60,
      note: view.note,
      include_writes: view.includeWrites,
    });
    apply({ status, busy: false });
  } catch (err) {
    apply({ busy: false, error: err instanceof Error ? err.message : String(err) });
  }
}

export async function stopDump(
  hass: HassDump,
  entity: string,
  apply: (patch: Partial<DumpView>) => void,
) {
  apply({ busy: true, error: "" });
  try {
    const status = await callDump(hass, "spo_pool_heat_pump/dump/stop", { entity_id: entity });
    apply({ status, busy: false });
  } catch (err) {
    apply({ busy: false, error: err instanceof Error ? err.message : String(err) });
  }
}

export async function deleteDump(
  hass: HassDump,
  entity: string,
  name: string,
  apply: (patch: Partial<DumpView>) => void,
) {
  if (!window.confirm(`Delete ${name} and its .bin?`)) return;
  apply({ busy: true, error: "" });
  try {
    const status = await callDump(hass, "spo_pool_heat_pump/dump/delete", { entity_id: entity, name });
    apply({ status, busy: false });
  } catch (err) {
    apply({ busy: false, error: err instanceof Error ? err.message : String(err) });
  }
}

export async function downloadDump(hass: HassDump, name: string) {
  const token = hass.auth?.data?.access_token;
  const resp = await fetch(`/api/spo_pool_heat_pump/dumps/${encodeURIComponent(name)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error(`Download failed (${resp.status})`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

export function renderDumpPanel(args: {
  view: DumpView;
  onMinutes: (value: number) => void;
  onUntilStop: (value: boolean) => void;
  onNote: (value: string) => void;
  onWrites: (value: boolean) => void;
  onHelp: () => void;
  onStart: () => void;
  onStop: () => void;
  onDelete: (name: string) => void;
  onDownload: (name: string) => void;
}): TemplateResult {
  const view = args.view;
  const st = view.status;
  const limits = st?.limits;
  const running = Boolean(st?.running);
  return html`
    <div class="dump-panel">
      <div class="dump-head">
        <span class="dump-title">What to capture</span>
        <button class="dump-help-btn ${view.helpOpen ? "on" : ""}" title="What is a bus dump?" aria-label="What is a bus dump?" aria-expanded=${view.helpOpen} @click=${args.onHelp}>?</button>
      </div>
      ${view.helpOpen ? html`
        <div class="dump-help">
          <p>This records the raw RS-485 bytes Home Assistant sees on the DR164 — the same format we used to map the Cosma. A later dump is how a new model or an unknown register gets decoded.</p>
          <p><strong>Start the capture first</strong>, then act. Write in the note what you are about to do. One action at a time; wait a few seconds so the frames stay separable.</p>
          <p>Use the <strong>heat-pump panel and the phone app</strong> if both exist. They write different registers (panel vs DTU slave 99). Leave the factory WiFi / DTU plugged in.</p>
          <p><strong>Screenshot the phone app</strong> after each change (the page you just used), or <strong>photo the heat-pump display</strong> if there is no app or the change was on the panel. The picture should show the menu name and the value (H03, target 28 °C, Quiet on). Name files with clock time or the dump note so they line up with timestamps in the <code>.log</code>. One photo per action. Attach those images with the downloaded log when asking for a new profile or an unknown register.</p>
          <p>Work through everything that should appear on the wire:</p>
          <ul>
            <li>Power on and off.</li>
            <li>Heat, Cool, Auto — then change the target in each mode (they keep separate setpoints).</li>
            <li>Quiet / quiet timer, and the on/off timers.</li>
            <li>Every on-screen menu (H, F, D, E, P, R, timers). Open each page. Change a value, wait, put it back if you do not want to keep it.</li>
            <li>Screenshot / photo after every change.</li>
            <li>Let the unit actually run: pump pre-run, compressor start, reach the setpoint, go idle. Cooling as well as heating if the unit can.</li>
          </ul>
          <p>Do not change H/F/D service values unless you know the OEM numbers — those can damage the unit. Then download the <code>.log</code>.</p>
        </div>
      ` : ""}
      ${running
        ? html`
            <div class="params-note">
              Recording · ${mb(st?.bytes || 0)} · ${fmtTime(st?.elapsed_s)}
              ${st?.duration_s ? html` · ${fmtTime(st.remaining_s)} left` : html` · until stop`}
            </div>
            <button class="dump-btn" ?disabled=${view.busy} @click=${args.onStop}>Stop now</button>
          `
        : html`
            <label class="dump-field">Duration (minutes)
              <input
                class="params-input dump-minutes"
                type="number"
                min="1"
                max="120"
                .value=${String(view.minutes)}
                ?disabled=${view.untilStop}
                @change=${(e: Event) => args.onMinutes(Number((e.target as HTMLInputElement).value))}
              />
            </label>
            <label class="dump-check">
              <input type="checkbox" .checked=${view.untilStop} @change=${(e: Event) => args.onUntilStop((e.target as HTMLInputElement).checked)} />
              Until I stop
            </label>
            <label class="dump-field">Note
              <input class="params-filter" type="text" maxlength="200" .value=${view.note} @input=${(e: Event) => args.onNote((e.target as HTMLInputElement).value)} />
            </label>
            <label class="dump-check">
              <input type="checkbox" .checked=${view.includeWrites} @change=${(e: Event) => args.onWrites((e.target as HTMLInputElement).checked)} />
              Include HA writes
            </label>
            <button class="dump-btn" ?disabled=${view.busy} @click=${args.onStart}>Start capture</button>
          `}
      ${view.error ? html`<div class="params-error">${view.error}</div>` : ""}
      <div class="params-note">
        Timed run 1–120 min. Until I stop still ends at ${mb(limits?.session_cap_bytes || 40 * 1024 * 1024)}
        (${mb(limits?.rotate_bytes || 8 * 1024 * 1024)} × ${limits?.keep_files || 5} files).
        Dumps folder ${mb(limits?.dir_used || 0)} / ${mb(limits?.dir_cap_bytes || 200 * 1024 * 1024)}.
        One dump at a time.
      </div>
      <div class="params-count">${st?.files?.length || 0} captures</div>
      <div class="dump-files">
        ${(st?.files || []).map(
          (file) => html`
            <div class="dump-file">
              <div>
                <div class="params-label">${file.name}</div>
                <div class="params-note">${mb(file.size)}${file.note ? ` · ${file.note}` : ""}${file.started ? ` · ${file.started}` : ""}</div>
              </div>
              <div class="dump-actions">
                <button class="dump-link" @click=${() => args.onDownload(file.name)}>Download log</button>
                ${file.bin ? html`<button class="dump-link" @click=${() => args.onDownload(file.bin!)}>Download bin</button>` : ""}
                <button class="dump-link" @click=${() => args.onDelete(file.name)}>Delete</button>
              </div>
            </div>
          `,
        )}
      </div>
      <div class="params-note">
        Feed the .log into analyze_modbus.py or dump_replay_server.py.
      </div>
    </div>
  `;
}
