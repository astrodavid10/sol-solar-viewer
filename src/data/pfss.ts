// =====================================================================
// PFSS field-line loader — index.json → manifest → topology → frames
// =====================================================================
// Deliberately free of BOTH @wwtelescope/* and three imports (CLAUDE.md
// footgun 12): this module turns HTTP responses into plain typed arrays and
// hands them out. That keeps the binary parsing testable in a bare Node
// harness (`fetch` and `DataView` are the only platform APIs used) and keeps
// the renderer swappable.
//
// Wire formats (little-endian) are specified in the plan's DATA CONTRACT and
// produced by pipeline/pfss/export.py. Both are fixed-layout, so every field
// offset below is arithmetic on the header counts — no per-record seeking.
//
//   topology.bin  "SOLTOPO1"  u32 nLines, nVertsTotal, nBgLines, reserved
//                             char[8] seedSetId
//                             u32 lineOffset[nLines+1]
//                             i16 seedLatCdeg[nLines]
//                             u16 seedLonU16[nLines]
//                             i16 arIndex[nLines]
//
//   fNN.bin       "SOLPFRM1"  u32 frameIndex, nLines, nVertsTotal, magUnix,
//                             u32 reserved x2
//                             u16 xyz[nVertsTotal*3]   (interleaved, normalized;
//                                                       R_sun = q/65535*5.2 - 2.6,
//                                                       rotating Carrington frame)
//                             i8  polarity[nLines]     (0 closed, ±1 open — PER FRAME)
//                             u8  valid[nLines]
//
// Load order is NEWEST FIRST (manifest render_hints.load_order): the guest sees
// "now" as soon as the first frame lands and the look-back fills in behind it.

const TOPOLOGY_MAGIC = "SOLTOPO1";
const FRAME_MAGIC = "SOLPFRM1";
const HEADER_BYTES = 32;
const MAX_CONCURRENT_FRAMES = 3;

/** Linear RGB triple in 0..1, straight from the manifest's render hints. */
export type Rgb = [number, number, number];

/** THREE-compatible quaternion order: [x, y, z, w]. */
export type Quat = [number, number, number, number];

export type ProductStatus = "ok" | "degraded" | "stale" | "absent" | "failed";

// ---------------------------------------------------------------------
// Normalized (camelCase) shapes the app actually works with
// ---------------------------------------------------------------------

export interface PfssRenderHints {
  /** Dome palette: same colors the planetarium show uses. */
  closed: Rgb;
  openPos: Rgb;
  openNeg: Rgb;
  /** Source-surface radius (R_sun) — the outer end of the opacity ramp. */
  rss: number;
  /** Minimum opacity a closed line fades to at the source surface. */
  closedFloor: number;
  /** Which frame to show first (newest). */
  recommendedFirstFrame: number;
}

export interface PfssFrameMeta {
  index: number;
  url: string;
  bytes: number;
  targetIso: string;
  magIso: string;
  magUnix: number;
  magAgeHours: number;
  l0Deg: number;
  b0Deg: number;
  pDeg: number;
  hciRotDeg: number;
  /** Carrington → ecliptic J2000 as a quaternion (convention-free; slerpable). */
  quat: Quat;
  nValid: number;
  reused: boolean;
}

export interface PfssManifest {
  generatedUnix: number;
  windowHours: number;
  frameSpacingHours: number;
  newestMagIso: string;
  newestMagAgeHours: number;
  nLines: number;
  nVertsTotal: number;
  nBgLines: number;
  /** Dequantization: `rSun = q / 65535 * scale + offset`. */
  quantScale: number;
  quantOffset: number;
  hints: PfssRenderHints;
  /** Oldest → newest, as published. */
  frames: PfssFrameMeta[];
}

export interface PfssTopology {
  nLines: number;
  nVertsTotal: number;
  nBgLines: number;
  seedSetId: string;
  /** nLines+1 entries; line i owns vertices [lineOffset[i], lineOffset[i+1]). */
  lineOffset: Uint32Array;
  seedLatCdeg: Int16Array;
  seedLonU16: Uint16Array;
  /** -1 = background seed, else the index into ar/regions.json. */
  arIndex: Int16Array;
}

export interface PfssFrame {
  index: number;
  magUnix: number;
  magIso: string;
  quat: Quat;
  /** nVertsTotal*3, normalized uint16 — upload as-is (BufferAttribute normalized). */
  xyzU16: Uint16Array;
  /** Per LINE, per FRAME: 0 closed, +1 open positive, -1 open negative. */
  polarity: Int8Array;
  /** Per LINE, per FRAME: 0 = dead seed (degenerate geometry, draw nothing). */
  valid: Uint8Array;
}

export interface PfssLoadOptions {
  onManifest?: (manifest: PfssManifest) => void;
  onTopology?: (topology: PfssTopology) => void;
  onFrame?: (frame: PfssFrame) => void;
  signal?: AbortSignal;
}

export interface PfssLoadResult {
  status: ProductStatus;
  /** True when the pipeline flagged the product old enough to caveat. */
  stale: boolean;
  /** Age of the newest magnetogram in hours, when known. */
  staleHours: number | null;
  manifest: PfssManifest | null;
  topology: PfssTopology | null;
  framesLoaded: number;
  /** Human-readable reason when status is absent/failed (console only). */
  reason?: string;
}

// ---------------------------------------------------------------------
// Raw pipeline JSON. Keys are the pipeline's snake_case, by contract.
// ---------------------------------------------------------------------

/* eslint-disable @typescript-eslint/naming-convention -- pipeline JSON keys */
interface RawProduct {
  url: string;
  status: ProductStatus;
  stale: boolean;
  age_hours: number | null;
  data_age_hours?: number | null;
  frames?: number;
}

interface RawIndex {
  generated_unix: number;
  products: Record<string, RawProduct | undefined>;
}

interface RawFrame {
  index: number;
  url: string;
  bytes: number;
  target_iso: string;
  mag_iso: string;
  mag_unix: number;
  mag_age_hours: number;
  l0_deg: number;
  b0_deg: number;
  p_deg: number;
  hci_rot_deg: number;
  quat_carr_to_ecl: number[];
  n_valid: number;
  reused: boolean;
}

interface RawManifest {
  generated_unix: number;
  window_hours: number;
  frame_spacing_hours: number;
  newest_mag_iso: string;
  newest_mag_age_hours: number;
  geometry: {
    n_lines: number;
    n_verts_total: number;
    n_bg_lines: number;
    topology_url: string;
  };
  quantization: { xyz: { scale: number; offset: number } };
  render_hints: {
    colors: { closed: number[]; open_pos: number[]; open_neg: number[] };
    opacity_model: { rss: number; closed_floor: number };
    recommended_first_frame?: number;
  };
  frames: RawFrame[];
}
/* eslint-enable @typescript-eslint/naming-convention */

// ---------------------------------------------------------------------
// Binary helpers
// ---------------------------------------------------------------------

function readAscii(view: DataView, byteOffset: number, length: number): string {
  let out = "";
  for (let i = 0; i < length; i++) {
    const code = view.getUint8(byteOffset + i);
    if (code === 0) { break; }
    out += String.fromCharCode(code);
  }
  return out;
}

// Typed-array views onto the response buffer are zero-copy, but only when the
// byte offset happens to be a multiple of the element size. The fixed formats
// above always are; the slice() fallback keeps a future header change from
// turning into a RangeError on a guest's phone.
function viewU32(buffer: ArrayBuffer, byteOffset: number, count: number): Uint32Array {
  if (byteOffset % 4 === 0) { return new Uint32Array(buffer, byteOffset, count); }
  return new Uint32Array(buffer.slice(byteOffset, byteOffset + count * 4));
}

function viewI16(buffer: ArrayBuffer, byteOffset: number, count: number): Int16Array {
  if (byteOffset % 2 === 0) { return new Int16Array(buffer, byteOffset, count); }
  return new Int16Array(buffer.slice(byteOffset, byteOffset + count * 2));
}

function viewU16(buffer: ArrayBuffer, byteOffset: number, count: number): Uint16Array {
  if (byteOffset % 2 === 0) { return new Uint16Array(buffer, byteOffset, count); }
  return new Uint16Array(buffer.slice(byteOffset, byteOffset + count * 2));
}

/** Parse `topology.bin`. Throws with a specific message on any mismatch. */
export function parseTopology(buffer: ArrayBuffer): PfssTopology {
  if (buffer.byteLength < HEADER_BYTES) {
    throw new Error(`topology.bin too short (${buffer.byteLength} B)`);
  }
  const view = new DataView(buffer);
  const magic = readAscii(view, 0, 8);
  if (magic !== TOPOLOGY_MAGIC) {
    throw new Error(`topology.bin bad magic "${magic}"`);
  }

  const nLines = view.getUint32(8, true);
  const nVertsTotal = view.getUint32(12, true);
  const nBgLines = view.getUint32(16, true);
  const seedSetId = readAscii(view, 24, 8);

  let at = HEADER_BYTES;
  const lineOffset = viewU32(buffer, at, nLines + 1);
  at += (nLines + 1) * 4;
  const seedLatCdeg = viewI16(buffer, at, nLines);
  at += nLines * 2;
  const seedLonU16 = viewU16(buffer, at, nLines);
  at += nLines * 2;
  const arIndex = viewI16(buffer, at, nLines);
  at += nLines * 2;

  if (buffer.byteLength !== at) {
    throw new Error(`topology.bin length ${buffer.byteLength} B, expected ${at} B`);
  }
  if (lineOffset[nLines] !== nVertsTotal) {
    throw new Error(`topology.bin lineOffset[${nLines}]=${lineOffset[nLines]} != nVertsTotal ${nVertsTotal}`);
  }

  return { nLines, nVertsTotal, nBgLines, seedSetId, lineOffset, seedLatCdeg, seedLonU16, arIndex };
}

/** Parse one `fNN.bin`. `expect` cross-checks the geometry against topology. */
export function parseFrame(
  buffer: ArrayBuffer,
  expect?: { nLines: number; nVertsTotal: number },
): { index: number; magUnix: number; xyzU16: Uint16Array; polarity: Int8Array; valid: Uint8Array } {
  if (buffer.byteLength < HEADER_BYTES) {
    throw new Error(`frame too short (${buffer.byteLength} B)`);
  }
  const view = new DataView(buffer);
  const magic = readAscii(view, 0, 8);
  if (magic !== FRAME_MAGIC) {
    throw new Error(`frame bad magic "${magic}"`);
  }

  const index = view.getUint32(8, true);
  const nLines = view.getUint32(12, true);
  const nVertsTotal = view.getUint32(16, true);
  const magUnix = view.getUint32(20, true);

  if (expect && (nLines !== expect.nLines || nVertsTotal !== expect.nVertsTotal)) {
    throw new Error(
      `frame ${index} geometry ${nLines}x${nVertsTotal} != topology ${expect.nLines}x${expect.nVertsTotal}`);
  }

  let at = HEADER_BYTES;
  const xyzU16 = viewU16(buffer, at, nVertsTotal * 3);
  at += nVertsTotal * 3 * 2;
  const polarity = new Int8Array(buffer, at, nLines);
  at += nLines;
  const valid = new Uint8Array(buffer, at, nLines);
  at += nLines;

  if (buffer.byteLength !== at) {
    throw new Error(`frame ${index} length ${buffer.byteLength} B, expected ${at} B`);
  }

  return { index, magUnix, xyzU16, polarity, valid };
}

// ---------------------------------------------------------------------
// JSON normalization
// ---------------------------------------------------------------------

function rgb(value: number[] | undefined, fallback: Rgb): Rgb {
  if (!value || value.length < 3) { return fallback; }
  return [value[0], value[1], value[2]];
}

function quat(value: number[] | undefined): Quat {
  if (!value || value.length < 4) { return [0, 0, 0, 1]; }
  return [value[0], value[1], value[2], value[3]];
}

export function normalizeManifest(raw: RawManifest): PfssManifest {
  const geometry = raw.geometry;
  const hints = raw.render_hints;
  const frames: PfssFrameMeta[] = (raw.frames ?? []).map((f) => ({
    index: f.index,
    url: f.url,
    bytes: f.bytes,
    targetIso: f.target_iso,
    magIso: f.mag_iso,
    magUnix: f.mag_unix,
    magAgeHours: f.mag_age_hours,
    l0Deg: f.l0_deg,
    b0Deg: f.b0_deg,
    pDeg: f.p_deg,
    hciRotDeg: f.hci_rot_deg,
    quat: quat(f.quat_carr_to_ecl),
    nValid: f.n_valid,
    reused: !!f.reused,
  }));
  frames.sort((a, b) => a.index - b.index);

  const recommended = hints?.recommended_first_frame;
  return {
    generatedUnix: raw.generated_unix,
    windowHours: raw.window_hours,
    frameSpacingHours: raw.frame_spacing_hours,
    newestMagIso: raw.newest_mag_iso,
    newestMagAgeHours: raw.newest_mag_age_hours,
    nLines: geometry.n_lines,
    nVertsTotal: geometry.n_verts_total,
    nBgLines: geometry.n_bg_lines,
    quantScale: raw.quantization.xyz.scale,
    quantOffset: raw.quantization.xyz.offset,
    hints: {
      closed: rgb(hints?.colors?.closed, [1, 0.85, 0.2]),
      openPos: rgb(hints?.colors?.open_pos, [0.3, 0.55, 1]),
      openNeg: rgb(hints?.colors?.open_neg, [1, 0.4, 0.1]),
      rss: hints?.opacity_model?.rss ?? 2.5,
      closedFloor: hints?.opacity_model?.closed_floor ?? 0.25,
      recommendedFirstFrame: typeof recommended === "number"
        ? recommended
        : Math.max(0, frames.length - 1),
    },
    frames,
  };
}

// ---------------------------------------------------------------------
// Fetching
// ---------------------------------------------------------------------

/** `data/` under the deployed app — same origin, so no CORS anywhere. */
export function dataBaseUrl(): string {
  return new URL("data/", document.baseURI).href;
}

function bust(url: string, version: number): string {
  return `${url}${url.indexOf("?") >= 0 ? "&" : "?"}v=${version}`;
}

async function fetchJson<T>(url: string, signal?: AbortSignal, noStore = false): Promise<T> {
  const response = await fetch(url, { signal, cache: noStore ? "no-store" : "default" });
  if (!response.ok) { throw new Error(`${response.status} for ${url}`); }
  return await response.json() as T;
}

async function fetchBuffer(url: string, signal?: AbortSignal): Promise<ArrayBuffer> {
  const response = await fetch(url, { signal });
  if (!response.ok) { throw new Error(`${response.status} for ${url}`); }
  return await response.arrayBuffer();
}

/** Bounded-concurrency worker pool preserving start order, not finish order. */
async function pool<T>(items: T[], limit: number, work: (item: T) => Promise<void>): Promise<void> {
  let next = 0;
  const lanes: Promise<void>[] = [];
  for (let lane = 0; lane < Math.min(limit, items.length); lane++) {
    lanes.push((async () => {
      for (;;) {
        const i = next;
        next += 1;
        if (i >= items.length) { return; }
        await work(items[i]);
      }
    })());
  }
  await Promise.all(lanes);
}

function absent(reason: string): PfssLoadResult {
  return {
    status: "absent",
    stale: true,
    staleHours: null,
    manifest: null,
    topology: null,
    framesLoaded: 0,
    reason,
  };
}

/**
 * Load the whole PFSS product, streaming results out through callbacks so the
 * renderer can show the newest frame while the look-back is still arriving.
 *
 * Never rejects for "the data isn't there" — a dev checkout with no
 * `public/data/` resolves to status `"absent"` and the 3D view just says field
 * lines are unavailable. It DOES reject on AbortError so callers can bail.
 */
export async function loadPfss(baseUrl: string, opts: PfssLoadOptions = {}): Promise<PfssLoadResult> {
  const signal = opts.signal;

  let index: RawIndex;
  try {
    index = await fetchJson<RawIndex>(new URL("index.json", baseUrl).href, signal, true);
  } catch (err) {
    if (signal?.aborted) { throw err; }
    return absent(`index.json unavailable: ${String(err)}`);
  }

  const product = index.products?.pfss;
  if (!product || !product.url || product.status === "absent" || product.status === "failed") {
    return absent(`index.json reports pfss ${product ? product.status : "missing"}`);
  }

  const version = index.generated_unix || 0;
  const manifestUrl = new URL(product.url, baseUrl).href;
  const staleHours = product.data_age_hours ?? product.age_hours ?? null;

  let manifest: PfssManifest;
  try {
    const raw = await fetchJson<RawManifest>(bust(manifestUrl, version), signal);
    manifest = normalizeManifest(raw);
  } catch (err) {
    if (signal?.aborted) { throw err; }
    return absent(`manifest unavailable: ${String(err)}`);
  }
  opts.onManifest?.(manifest);

  let topology: PfssTopology;
  try {
    const topologyUrl = new URL("topology.bin", manifestUrl).href;
    topology = parseTopology(await fetchBuffer(bust(topologyUrl, version), signal));
  } catch (err) {
    if (signal?.aborted) { throw err; }
    return {
      status: "failed",
      stale: true,
      staleHours,
      manifest,
      topology: null,
      framesLoaded: 0,
      reason: `topology unavailable: ${String(err)}`,
    };
  }
  opts.onTopology?.(topology);

  // Newest first (manifest render_hints.load_order): the guest gets "now"
  // immediately, and the 72-hour look-back fills in behind it.
  const order = manifest.frames.slice().sort((a, b) => b.index - a.index);
  const expect = { nLines: topology.nLines, nVertsTotal: topology.nVertsTotal };
  let framesLoaded = 0;

  await pool(order, MAX_CONCURRENT_FRAMES, async (meta) => {
    if (signal?.aborted) { return; }
    try {
      const url = new URL(meta.url, manifestUrl).href;
      const parsed = parseFrame(await fetchBuffer(bust(url, version), signal), expect);
      framesLoaded += 1;
      opts.onFrame?.({
        index: meta.index,
        magUnix: parsed.magUnix || meta.magUnix,
        magIso: meta.magIso,
        quat: meta.quat,
        xyzU16: parsed.xyzU16,
        polarity: parsed.polarity,
        valid: parsed.valid,
      });
    } catch (err) {
      if (signal?.aborted) { return; }
      // One bad frame is a gap in the animation, not a dead view.
      console.warn(`[pfss] frame ${meta.index} skipped:`, err);
    }
  });

  const status: ProductStatus = framesLoaded === 0
    ? "failed"
    : (product.stale ? "stale" : product.status);

  return {
    status,
    stale: !!product.stale || status === "degraded" || framesLoaded < manifest.frames.length,
    staleHours,
    manifest,
    topology,
    framesLoaded,
  };
}
