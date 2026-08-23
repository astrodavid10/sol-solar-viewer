// =====================================================================
// Live space-weather stats
// =====================================================================
// Design constraints that shaped this file:
//
//  * A guest opens the app for 40 seconds, on a phone, on venue wifi. So:
//    every source is fetched independently and a failure in one never blanks
//    the others; a 6-second AbortController keeps a hung endpoint from holding
//    the row empty; and the last good values are written through to
//    localStorage so a returning guest sees numbers on the FIRST frame, dimmed
//    and honestly labeled "as of 3:20 AM" when they're stale.
//  * Total transfer budget is single-digit KB — all five endpoints are tiny.
//  * TTLs match how fast each number actually moves: wind/flare 5 minutes,
//    Kp and the NOAA scales 30 minutes, the pipeline's daily snapshot 6 hours.
//
// Not `Promise.allSettled`: tsconfig targets es2019 (lib es2019), where that
// method isn't declared. `settle()` below is the same idea in two lines.

import { reactive, ref } from "vue";

import {
  FlareInfo,
  KP_URL,
  MAG_FIELD_URL,
  MagInfo,
  Parsed,
  SCALES_URL,
  ScaleInfo,
  WIND_SPEED_URL,
  XRAY_FLARES_URL,
  parseFlares,
  parseKp,
  parseMagField,
  parseScales,
  parseTimeTag,
  parseWindSpeed,
} from "./swpc";

/** One measured quantity plus everything the UI needs to be honest about it. */
export interface StatField<T> {
  value: T | null;
  /** Observation time as SWPC reported it (ISO-ish string), if any. */
  timeTag: string | null;
  /** Observation time in epoch ms — what the freshness dot uses. */
  observedMs: number | null;
  /** Last fetch attempt succeeded. */
  ok: boolean;
  /** When we last got this value (epoch ms) — 0 if never. */
  fetchedAt: number;
}

/**
 * One GOES flare inside the pipeline's look-back window, as
 * `summary.json`'s `flaresWindow.events[]` reports it.
 */
export interface FlareEvent {
  /** GOES class string, e.g. "M8.1". Empty only if the pipeline omitted it. */
  cls: string;
  beginIso: string;
  peakIso: string;
  /** Peak time in unix SECONDS — the axis the time scrubber marks. */
  peakUnix: number;
}

/** The pipeline's `flaresWindow`: a look-back span and the flares inside it. */
export interface FlareWindow {
  /** Length of the window in hours; 0 when the snapshot doesn't say. */
  hours: number;
  /** Flares inside it, oldest first. */
  events: FlareEvent[];
}

/** Sunspot number + active-region count, from the pipeline's daily digest. */
export interface SnapshotInfo {
  sunspotNumber: number | null;
  activeRegions: number | null;
  /**
   * Which month `sunspotNumber` belongs to ("2026-07"), when the pipeline says.
   * The international sunspot number is a MONTHLY mean — it is not a count of
   * what is on the disk today — and this app is called "the Sun Right Now", so
   * the UI has to be able to say which month it is quoting. Empty when unknown.
   */
  sunspotMonth: string;
}

export interface SolarStats {
  flare: StatField<FlareInfo>;
  wind: StatField<number>;
  mag: StatField<MagInfo>;
  kp: StatField<number>;
  scales: StatField<ScaleInfo>;
  snapshot: StatField<SnapshotInfo>;
  /**
   * The flare LIST, deliberately a field of its own rather than more fields on
   * `snapshot`. Both come out of one fetch of summary.json, but they answer to
   * different contracts: `snapshot` is null until it finds a sunspot number,
   * and the 3D view's flare marks must not depend on that verdict (nor change
   * it — the disk view's Sunspots chip reads "daily count" precisely while
   * `snapshot.value` is null). Absent in older snapshots, and then this field
   * simply never gains a value.
   */
  flareHistory: StatField<FlareWindow>;
}

export interface SolarStatsApi {
  stats: SolarStats;
  state: StatsState;
  refresh: (force?: boolean) => Promise<void>;
}

export interface StatsState {
  /** A refresh pass is in flight. */
  loading: boolean;
  /** Epoch ms of the last completed pass. */
  lastPass: number;
  /** At least one source has ever produced a value (else: show nothing yet). */
  anyValue: boolean;
  /** Values came from localStorage and nothing has refreshed yet. */
  fromCache: boolean;
}

// --- tunables -------------------------------------------------------------

const REQUEST_TIMEOUT_MS = 6000;
const POLL_MS = 5 * 60 * 1000;
const TTL_FAST_MS = 5 * 60 * 1000;      // flare, wind, mag
const TTL_SLOW_MS = 30 * 60 * 1000;     // kp, scales
const TTL_SNAPSHOT_MS = 6 * 60 * 60 * 1000;
/** Past this age the UI dims the numbers and shows "as of h:mm". */
export const STALE_MS = 30 * 60 * 1000;
const STORAGE_KEY = "sol:stats:v1";

// --- module singleton state ----------------------------------------------

function emptyField<T>(): StatField<T> {
  return { value: null, timeTag: null, observedMs: null, ok: false, fetchedAt: 0 };
}

const stats = reactive<SolarStats>({
  flare: emptyField<FlareInfo>(),
  wind: emptyField<number>(),
  mag: emptyField<MagInfo>(),
  kp: emptyField<number>(),
  scales: emptyField<ScaleInfo>(),
  snapshot: emptyField<SnapshotInfo>(),
  flareHistory: emptyField<FlareWindow>(),
});

const state = reactive<StatsState>({
  loading: false,
  lastPass: 0,
  anyValue: false,
  fromCache: false,
});

const initialized = ref(false);

// --- fetch plumbing -------------------------------------------------------

async function fetchJson(url: string): Promise<unknown> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, { signal: controller.signal, cache: "no-store" });
    if (!response.ok) { throw new Error(`HTTP ${response.status}`); }
    return await response.json();
  } finally {
    window.clearTimeout(timer);
  }
}

/** Promise.allSettled in miniature: never rejects, resolution is "did it work". */
async function settle(task: Promise<void>): Promise<void> {
  try {
    await task;
  } catch {
    // Deliberately silent: a dead endpoint is a normal Tuesday for SWPC, and
    // the UI already communicates staleness through the freshness dot.
  }
}

function commit<T>(field: StatField<T>, parsed: Parsed<T> | null): void {
  if (parsed === null) {
    field.ok = false;
    return;
  }
  field.value = parsed.value;
  field.timeTag = parsed.timeTag;
  field.observedMs = parseTimeTag(parsed.timeTag) ?? Date.now();
  field.ok = true;
  field.fetchedAt = Date.now();
  state.anyValue = true;
  state.fromCache = false;
}

function isFresh(field: StatField<unknown>, ttl: number): boolean {
  return field.value !== null && field.fetchedAt > 0 && Date.now() - field.fetchedAt < ttl;
}

// --- pipeline daily snapshot ---------------------------------------------

/**
 * data/stats/summary.json is published by the Python pipeline. It is ABSENT in
 * a plain `yarn serve` (and on a fresh deploy before the first data run) — a
 * 404 here is a normal condition, not an error, and shows up as "—" on the
 * sunspot chip with no error UI anywhere.
 *
 * Key names are probed rather than assumed: the pipeline's exporter is being
 * written in parallel (M-P5), and the contract in the plan names the contents
 * ("monthly SSN, AR count") without pinning the JSON spelling.
 */
function snapshotUrl(): string {
  return new URL("data/stats/summary.json", document.baseURI).href;
}

function pickNumber(source: unknown, keys: string[]): number | null {
  if (typeof source !== "object" || source === null) { return null; }
  const dict = source as Record<string, unknown>;
  for (const key of keys) {
    const raw = dict[key];
    if (typeof raw === "number" && Number.isFinite(raw)) { return raw; }
    if (typeof raw === "string" && raw.trim() !== "") {
      const n = Number(raw);
      if (Number.isFinite(n)) { return n; }
    }
    if (Array.isArray(raw)) { return raw.length; }
    // The pipeline publishes every MEASURED quantity as an object carrying its
    // own provenance -- `sunspotNumber: {month, smoothed, value}`,
    // `f107: {time_iso, value}` -- because a bare number cannot say when it was
    // measured or which month it belongs to. Unwrap `value` rather than
    // special-casing each field: this reader is deliberately shape-tolerant,
    // and NOT handling the publisher's own idiom is what left the Sunspots
    // chip permanently blank while every alias key below "looked" covered.
    if (raw !== null && typeof raw === "object") {
      const inner = (raw as Record<string, unknown>)["value"];
      if (typeof inner === "number" && Number.isFinite(inner)) { return inner; }
      if (typeof inner === "string" && inner.trim() !== "") {
        const n = Number(inner);
        if (Number.isFinite(n)) { return n; }
      }
    }
  }
  return null;
}

function pickString(source: unknown, keys: string[]): string {
  if (typeof source !== "object" || source === null) { return ""; }
  const dict = source as Record<string, unknown>;
  for (const key of keys) {
    const raw = dict[key];
    if (typeof raw === "string" && raw.trim() !== "") { return raw; }
  }
  return "";
}

function parseFlareEvent(raw: unknown): FlareEvent | null {
  if (typeof raw !== "object" || raw === null) { return null; }
  const peakIso = pickString(raw, ["peak_iso", "peakIso"]);
  // peak_unix is what the pipeline publishes; the ISO string is the fallback so
  // an exporter that drops the epoch field doesn't blank the whole track.
  const isoMs = peakIso ? Date.parse(peakIso) : Number.NaN;
  const peakUnix = pickNumber(raw, ["peak_unix", "peakUnix"])
    ?? (Number.isFinite(isoMs) ? isoMs / 1000 : null);
  if (peakUnix === null) { return null; }
  return {
    cls: pickString(raw, ["class", "cls", "flare_class"]),
    beginIso: pickString(raw, ["begin_iso", "beginIso"]),
    peakIso,
    peakUnix,
  };
}

/**
 * `summary.json` → the flare window. Returns null when the snapshot has no
 * `flaresWindow` (every snapshot published before the pipeline grew one) or
 * when it holds no readable events — the same "no value" signal every other
 * parser in this file uses, which leaves the field at its empty state instead
 * of claiming a quiet Sun.
 */
function parseFlareHistory(json: unknown): Parsed<FlareWindow> | null {
  if (typeof json !== "object" || json === null) { return null; }
  const dict = json as Record<string, unknown>;
  const raw = dict["flaresWindow"] ?? dict["flares_window"];
  if (typeof raw !== "object" || raw === null) { return null; }
  const inner = raw as Record<string, unknown>;
  const list = Array.isArray(inner["events"]) ? inner["events"] as unknown[] : [];
  const events: FlareEvent[] = [];
  list.forEach((entry) => {
    const event = parseFlareEvent(entry);
    if (event) { events.push(event); }
  });
  if (!events.length) { return null; }
  // Oldest first, regardless of how the exporter ordered them: the marks are
  // drawn along a time axis and a stable order keeps Vue's keyed diff cheap.
  events.sort((a, b) => a.peakUnix - b.peakUnix);

  const generated = dict["generated"] ?? dict["generated_iso"] ?? dict["date"];
  return {
    value: { hours: pickNumber(inner, ["hours", "window_hours"]) ?? 0, events },
    timeTag: typeof generated === "string" ? generated : null,
  };
}

/**
 * GOES class → a single comparable number. The letter is a decade of X-ray
 * flux (A < B < C < M < X, each 10x the last) and the digits are the mantissa
 * within it, so "M1.0" is exactly ten times "C1.0" on this scale. Unparseable
 * classes sort last (0) rather than throwing off the ordering.
 */
export function flareMagnitude(cls: string): number {
  const letter = (cls || "").charAt(0).toUpperCase();
  // The empty check is not redundant: "ABCMX".indexOf("") is 0, so a classless
  // event would otherwise rank as a full A-class flare.
  const decade = letter === "" ? -1 : "ABCMX".indexOf(letter);
  if (decade < 0) { return 0; }
  const mantissa = Number.parseFloat(cls.slice(1));
  return Math.pow(10, decade) * (Number.isFinite(mantissa) && mantissa > 0 ? mantissa : 1);
}

/** Everything at or above this decade is always marked (M and X). */
const ALWAYS_MARK_MAGNITUDE = 1000;

/**
 * Thin a flare list down to something a phone-width track can carry.
 *
 * Every M and X event survives — those are the ones a guest came to see, and
 * there are rarely more than a handful in three days. The remaining slots up to
 * `maxMarks` go to the STRONGEST of the rest; 29 C-class diamonds would carpet
 * the track and hide the two that matter. Returns a new array in time order.
 */
export function thinFlareEvents(events: FlareEvent[], maxMarks = 10): FlareEvent[] {
  const strong: FlareEvent[] = [];
  const rest: FlareEvent[] = [];
  events.forEach((event) => {
    if (flareMagnitude(event.cls) >= ALWAYS_MARK_MAGNITUDE) {
      strong.push(event);
    } else {
      rest.push(event);
    }
  });
  const budget = Math.max(0, maxMarks - strong.length);
  const filler = rest
    .slice()
    .sort((a, b) => flareMagnitude(b.cls) - flareMagnitude(a.cls))
    .slice(0, budget);
  return strong.concat(filler).sort((a, b) => a.peakUnix - b.peakUnix);
}

function parseSnapshot(json: unknown): Parsed<SnapshotInfo> | null {
  if (typeof json !== "object" || json === null) { return null; }
  const dict = json as Record<string, unknown>;
  const nested = dict["sun"] ?? dict["summary"] ?? dict["stats"];

  const sunspotNumber =
    // "sunspotNumber" is what stats/export.py actually writes; the rest are
    // tolerated aliases. Keep the real one FIRST so the working path is the
    // obvious one when reading this.
    pickNumber(dict, ["sunspotNumber", "sunspot_number", "ssn", "monthly_ssn", "smoothed_ssn"]) ??
    pickNumber(nested, ["sunspotNumber", "sunspot_number", "ssn", "monthly_ssn"]);

  const activeRegions =
    // Likewise: "activeRegionCount" is the published name. Its absence from
    // this list is why the chip stayed blank even once the sunspot number was
    // readable -- parseSnapshot returns null only when BOTH are missing, so
    // two independent misses looked like one silent failure.
    pickNumber(dict, ["activeRegionCount", "active_region_count", "ar_count",
      "active_regions", "n_regions", "regions"]) ??
    pickNumber(nested, ["activeRegionCount", "active_region_count", "ar_count",
      "active_regions", "regions"]);

  if (sunspotNumber === null && activeRegions === null) { return null; }

  const spotBlock = dict["sunspotNumber"];
  const sunspotMonth = (spotBlock !== null && typeof spotBlock === "object"
    && typeof (spotBlock as Record<string, unknown>)["month"] === "string")
    ? (spotBlock as Record<string, string>)["month"]
    : "";

  const generated = dict["generated"] ?? dict["generated_iso"] ?? dict["date"];
  return {
    value: { sunspotNumber, activeRegions, sunspotMonth },
    timeTag: typeof generated === "string" ? generated : null,
  };
}

// --- refresh --------------------------------------------------------------

/**
 * Fetch everything whose TTL has expired. `force` ignores the TTLs (used by
 * the manual retry link in the stats row).
 */
export async function refresh(force = false): Promise<void> {
  if (state.loading) { return; }
  state.loading = true;

  const tasks: Promise<void>[] = [];

  if (force || !isFresh(stats.flare, TTL_FAST_MS)) {
    tasks.push(settle(fetchJson(XRAY_FLARES_URL).then((j) => commit(stats.flare, parseFlares(j)))));
  }
  if (force || !isFresh(stats.wind, TTL_FAST_MS)) {
    tasks.push(settle(fetchJson(WIND_SPEED_URL).then((j) => commit(stats.wind, parseWindSpeed(j)))));
  }
  if (force || !isFresh(stats.mag, TTL_FAST_MS)) {
    tasks.push(settle(fetchJson(MAG_FIELD_URL).then((j) => commit(stats.mag, parseMagField(j)))));
  }
  if (force || !isFresh(stats.kp, TTL_SLOW_MS)) {
    tasks.push(settle(fetchJson(KP_URL).then((j) => commit(stats.kp, parseKp(j)))));
  }
  if (force || !isFresh(stats.scales, TTL_SLOW_MS)) {
    tasks.push(settle(fetchJson(SCALES_URL).then((j) => commit(stats.scales, parseScales(j)))));
  }
  // ONE fetch, two fields: the daily digest and the flare list live in the same
  // file and share its TTL, but they commit independently so a missing sunspot
  // number can't take the flare marks down with it (and vice versa).
  if (force
    || !isFresh(stats.snapshot, TTL_SNAPSHOT_MS)
    || !isFresh(stats.flareHistory, TTL_SNAPSHOT_MS)) {
    tasks.push(settle(fetchJson(snapshotUrl()).then((j) => {
      commit(stats.snapshot, parseSnapshot(j));
      commit(stats.flareHistory, parseFlareHistory(j));
    })));
  }

  await Promise.all(tasks);

  state.loading = false;
  state.lastPass = Date.now();
  save();
}

// --- localStorage write-through ------------------------------------------
// Guests come back (the QR code is on a card they took home). Rendering the
// last known numbers immediately, dimmed, beats an empty grid.

function save(): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(stats));
  } catch {
    // Private-mode Safari throws on setItem. The app is fully functional
    // without the cache, so there is nothing to report.
  }
}

function restoreField<T>(field: StatField<T>, raw: unknown): void {
  if (typeof raw !== "object" || raw === null) { return; }
  const dict = raw as Record<string, unknown>;
  if (dict["value"] === undefined || dict["value"] === null) { return; }
  field.value = dict["value"] as T;
  field.timeTag = typeof dict["timeTag"] === "string" ? dict["timeTag"] : null;
  field.observedMs = typeof dict["observedMs"] === "number" ? dict["observedMs"] : null;
  field.fetchedAt = typeof dict["fetchedAt"] === "number" ? dict["fetchedAt"] : 0;
  // ok stays false until a live fetch confirms it — the UI treats a restored
  // value as "last known", not "current".
  field.ok = false;
  state.anyValue = true;
  state.fromCache = true;
}

function load(): void {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return;
  }
  if (!raw) { return; }
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    restoreField(stats.flare, parsed["flare"]);
    restoreField(stats.wind, parsed["wind"]);
    restoreField(stats.mag, parsed["mag"]);
    restoreField(stats.kp, parsed["kp"]);
    restoreField(stats.scales, parsed["scales"]);
    restoreField(stats.snapshot, parsed["snapshot"]);
    // A restored flare list can be a day old. That is harmless by construction:
    // TimeScrubber drops every event outside the frame window it is given, so
    // stale marks disappear rather than lying about when they happened.
    restoreField(stats.flareHistory, parsed["flareHistory"]);
  } catch {
    // Corrupt or older-format cache: ignore it and fetch fresh.
  }
}

// --- lifecycle ------------------------------------------------------------

function startPolling(): void {
  // Both the interval and the visibility hook are gated on visibility so a
  // phone in a pocket costs nothing.
  window.setInterval(() => {
    if (document.visibilityState === "visible") { void refresh(); }
  }, POLL_MS);

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") { void refresh(); }
  });
}

/**
 * Reactive space-weather stats. The underlying state is a module singleton, so
 * every caller shares one set of requests regardless of how many components
 * mount.
 */
export function useSolarStats(): SolarStatsApi {
  if (!initialized.value) {
    initialized.value = true;
    load();
    void refresh();
    startPolling();
  }
  return { stats, state, refresh };
}
