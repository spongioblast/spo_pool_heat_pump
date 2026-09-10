import { html, svg, nothing, type TemplateResult } from "lit";

export type CardState = {
  available: boolean;
  power: boolean;
  mode: string;
  action: string;
  inlet: number | null;
  inletLive: number | null;
  outlet: number | null;
  ambient: number | null;
  setpoint: number | null;
  kw: number | null;
  kwh24: number | null;
  pct: number | null;
  fanRpm: number | null;
  silent: boolean;
  pump: boolean;
  fault: string | null;
  faultText: string | null;
  status: string;
  cop: number | null;
  dumpOnly: boolean;
  caps: { cool: boolean; auto: boolean; silent: boolean; power: boolean; energy: boolean; compressor: boolean; ambient: boolean; fan: boolean };
};

const COLD = "#38b6ff", WARM = "#ff8a3d", NEUT = "#7fb2c9";
const OFFC = "color-mix(in srgb, var(--primary-text-color) 22%, transparent)";

export function flow(s: CardState) {
  const on = s.available && s.power && s.pump;
  if (!on) return { inC: OFFC, outC: OFFC };
  const d = (s.outlet ?? 0) - (s.inlet ?? 0);
  if (Math.abs(d) < 0.15) return { inC: NEUT, outC: NEUT };
  return d > 0 ? { inC: COLD, outC: WARM } : { inC: WARM, outC: COLD };
}

export function accent(s: CardState): string {
  if (s.fault) return "#e53935";
  if (!s.available || !s.power) return "var(--state-climate-off-color)";
  if (s.action === "heating" || s.action === "warmup") return "var(--state-climate-heat-color)";
  if (s.action === "cooling" || s.action === "precool") return "var(--state-climate-cool-color)";
  return "var(--state-climate-idle-color)";
}

const f1 = (x: number | null) => (x == null ? "–" : (Math.round(x * 10) / 10).toFixed(1));
const wave = (x0: number, x1: number, y: number, amp = 3, seg = 12) => {
  let d = `M${x0} ${y}`;
  for (let x = x0; x < x1; x += seg) d += ` q${seg / 2} ${-amp} ${seg} 0`;
  return d;
};
const pipe = (d: string, cls: string) => svg`
  <path class="tube ${cls}" d=${d}/>
  <path class="core ${cls}" d=${d}/>
  <path class="dots" d=${d}/>
`;
const vent = (cx: number, cy: number, r: number) => svg`<g class="vent">
  <circle class="g-disk" cx=${cx} cy=${cy} r=${r + 1.2}/>
  <circle class="g-ring" cx=${cx} cy=${cy} r=${r}/>
  <g transform="translate(${cx} ${cy})"><g class="fanwrap">${[0, 120, 240].map((a) => svg`<path class="petal" transform="rotate(${a})" d=${`M0 0 C ${r * 0.28} ${-r * 0.42}, ${r * 0.7} ${-r * 0.55}, ${r * 0.76} ${-r * 0.1} C ${r * 0.55} ${r * 0.08}, ${r * 0.28} ${r * 0.18}, 0 0 Z`}/>`)}</g></g>
  <circle class="hub" cx=${cx} cy=${cy} r=${r * 0.15}/>
</g>`;
const radiator = (id: string, x: number, yIn: number, yOut: number, w: number, n = 6) => {
  const top = yOut, bot = yIn, left = x, right = x + w;
  const inset = 7, span = right - left - inset * 2;
  const tubes = Array.from({ length: n }, (_, i) => {
    const tx = (left + inset + (n === 1 ? 0 : (span * i) / (n - 1))).toFixed(1);
    return svg`<path class="rad-glow" d=${`M${tx} ${bot} V${top}`} stroke=${`url(#${id})`}/><path class="rad-tube" d=${`M${tx} ${bot} V${top}`} stroke=${`url(#${id})`}/>`;
  });
  const fn = n * 2;
  const fins = Array.from({ length: fn }, (_, i) => {
    const fx = (left + 6 + ((right - left - 12) * i) / (fn - 1)).toFixed(1);
    return svg`<path class="fin" d=${`M${fx} ${bot - 1} V${top + 1}`}/>`;
  });
  const mid = (left + inset + span * 0.5).toFixed(1);
  return svg`
    <defs><linearGradient id=${id} gradientUnits="userSpaceOnUse" x1="0" y1=${bot} x2="0" y2=${top}>
      <stop offset="0" stop-color="var(--inC)"/><stop offset=".2" stop-color="var(--inC)"/>
      <stop offset=".65" stop-color="var(--outC)"/><stop offset="1" stop-color="var(--outC)"/>
    </linearGradient></defs>
    <g class="rad"><g class="fins">${fins}</g>${tubes}
      <path class="manifold in" d=${`M${left} ${bot} H${right}`}/><path class="manifold out" d=${`M${left} ${top} H${right}`}/>
      <path class="dots rise" d=${`M${mid} ${bot} V${top}`}/></g>`;
};
const port = (x: number, y: number, cls: string) => svg`<circle class="port ${cls}" cx=${x} cy=${y} r="3.2"/>`;
const plume = (id: string, cx: number, cy: number, rx: number, ry: number, clipD: string) => svg`
  <defs>
    <radialGradient id=${id}>
      <stop offset="0" stop-color="var(--outC)" stop-opacity=".55"/>
      <stop offset="1" stop-color="var(--outC)" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="${id}c">${svg`<path d=${clipD}/>`}</clipPath>
  </defs>
  <g clip-path=${`url(#${id}c)`}><ellipse class="plume" cx=${cx} cy=${cy} rx=${rx} ry=${ry} fill=${`url(#${id})`} style=${`transform-origin:${cx}px ${cy}px`}/></g>
`;

function tone(s: CardState, which: "in" | "out") {
  const f = flow(s);
  if (f.inC === OFFC || f.inC === NEUT) return "";
  const heating = f.outC === WARM;
  return (which === "in") === heating ? "cool" : "warm";
}

function portLbl(s: CardState, which: "in" | "out", x: number, yCap: number, yVal: number) {
  const cap = which === "in" ? "In" : "Out";
  const val = `${f1(which === "in" ? s.inlet : s.outlet)}°`;
  return svg`<text class="k halo" x=${x} y=${yCap} text-anchor="end">${cap}</text><text class="v halo ${tone(s, which)}" x=${x} y=${yVal} text-anchor="end">${val}</text>`;
}

function airMark(s: CardState, x: number, y: number) {
  if (!s.caps.ambient) return nothing;
  return svg`<text class="k" x=${x} y=${y} text-anchor="middle">air</text><text class="v" x=${x} y=${y + 18} text-anchor="middle">${f1(s.ambient)}°</text>`;
}

function dtMark(s: CardState, x: number, y: number) {
  const d = s.pump && s.power && s.outlet != null && s.inlet != null ? s.outlet - s.inlet : null;
  const t = d == null ? "–" : `${d >= 0 ? "+" : ""}${f1(d)}°`;
  return svg`<text class="k halo" x=${x} y=${y} text-anchor="end">ΔT ${t}</text>`;
}

function copMark(s: CardState, x: number, y: number) {
  if (s.cop == null || s.cop === 0) return nothing;
  return svg`<text class="k halo" x=${x} y=${y} text-anchor="middle">COP ${f1(s.cop)}</text>`;
}

export function circuitSvg(s: CardState, uid = "ph"): TemplateResult {
  const yIn = 112, yOut = 76, xPort = 308;
  const L = 18, R = 183, yRim = 62, yW = 69, yB = 130, r = 14;
  const inD = `M${R} ${yIn} H${xPort}`;
  const outD = `M${xPort} ${yOut} H${R}`;
  const surface = wave(L, R, yW, 2, 11);
  const body = `${surface} V${yB - r} Q${R} ${yB} ${R - r} ${yB} H${L + r} Q${L} ${yB} ${L} ${yB - r} Z`;
  const walls = `M${L} ${yRim} V${yB - r} Q${L} ${yB} ${L + r} ${yB} H${R - r} Q${R} ${yB} ${R} ${yB - r} V${yRim}`;
  return html`<svg class="dwg" viewBox="0 32 420 132">
    <defs><clipPath id="${uid}basin"><rect x=${L} y=${yRim} width=${R - L} height=${yB - yRim}/></clipPath></defs>
    <path class="water" d=${body}/>
    ${plume(`${uid}pl`, R - 6, yOut, 40, 15, body)}
    <path class="wall" d=${walls}/>
    <g clip-path="url(#${uid}basin)"><path class="thin surface" d=${wave(L - 11, R + 11, yW, 2, 11)}/></g>
    ${airMark(s, (L + R) / 2, 42)}
    <rect class="ln unitfill" x="304" y="58" width="100" height="72" rx="16"/>
    <circle class="led" cx="394" cy="68" r="2.1"/>
    ${radiator(`${uid}rad`, xPort, yIn, yOut, 40, 6)}
    ${vent(370, 94, 18)}
    ${pipe(inD, "in")}${pipe(outD, "out")}${port(xPort, yIn, "in")}${port(xPort, yOut, "out")}
    ${portLbl(s, "out", 300, 44, 62)}${portLbl(s, "in", 300, 134, 152)}${dtMark(s, 300, 98)}${copMark(s, 354, 148)}
  </svg>`;
}

export function sectionSvg(s: CardState, uid = "ph"): TemplateResult {
  const yIn = 86, yOut = 56, xPort = 302;
  const inD = `M208 146 H236 Q250 146 250 132 V100 Q250 ${yIn} 264 ${yIn} H${xPort}`;
  const outD = `M${xPort} ${yOut} H250 Q236 ${yOut} 236 70 V98 Q236 108 222 108 H208`;
  const waterD = "M18 100 H208 V154 H18 Z";
  return html`<svg class="dwg" viewBox="0 18 420 140">
    <path class="soil" d="M208 96 H420 V154 H208 Z"/>
    <path class="thin grade" d="M0 96 H18"/>
    <rect class="deck-slab" x="208" y="93" width="212" height="5" rx="1"/>
    <path class="water" d=${waterD}/>
    ${plume(`${uid}pl`, 202, 108, 38, 15, waterD)}
    <path class="wall" d="M18 96 V154 H208 V98"/>
    <defs><clipPath id="${uid}basin"><rect x="18" y="96" width="190" height="58"/></clipPath></defs>
    <g clip-path="url(#${uid}basin)"><path class="thin surface" d=${wave(8, 218, 100, 2, 10)}/></g>
    <path class="nozzle out" d="M208 104 L216 108 L208 112 Z"/>
    ${airMark(s, 113, 70)}
    <rect class="ln unitfill" x="300" y="36" width="98" height="58" rx="12"/>
    <path class="foot" d="M310 94 V96 H320 V94 M378 94 V96 H388 V94"/>
    <circle class="led" cx="388" cy="46" r="2"/>
    ${radiator(`${uid}rad`, xPort, yIn, yOut, 34, 5)}
    ${vent(372, 65, 14.5)}
    ${pipe(inD, "in")}${pipe(outD, "out")}${port(xPort, yIn, "in")}${port(xPort, yOut, "out")}
    ${portLbl(s, "in", 296, 103, 118)}${portLbl(s, "out", 296, 32, 47)}${dtMark(s, 296, 75)}${copMark(s, 349, 110)}
  </svg>`;
}

export { f1 };
