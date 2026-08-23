// =====================================================================
// Flares and CMEs — the moments something happened
// =====================================================================
// `data/events/events.json` is CCMC's DONKI catalog digested by the pipeline
// (see pipeline/events/export.py). It is the only source that gives an
// eruption a PLACE and a DIRECTION: NOAA's `xray-flares-latest.json`, which
// this app already shows in the stats row, reports class and timing but has no
// source location at all.
//
// This module is the UI's reader. Like regions.ts and spacecraft.ts it stays
// free of three and WWT imports (CLAUDE.md footgun 12), so the same events can
// mark the disk view's timeline later without touching the 3D code.
//
// Two things about the data that shape the API below:
//
//   - `dirEcl` is already a unit vector in ECLIPTIC J2000, the app's world
//     frame, and must be used with NO further rotation. In particular it must
//     NOT be handed the Carrington quaternion the field lines carry: a CME
//     travels along a fixed inertial direction, and Carrington rotation is
//     14.18 deg/day, so a Carrington-parented CME would swing 42.5 deg across
//     the 72 h window (CLAUDE.md footgun 25).
//   - `arNumber` is the NOAA SRS number; DONKI's own is 10000 higher and the
//     pipeline has already subtracted it (footgun 23). `arIndex` addresses
//     `ar/regions.json` — and -1 is NORMAL, not an error: DONKI keeps
//     reporting a region for days after it has rotated off the disk.

export type SolarEventKind = "flare" | "cme";

/** A CME's arrival somewhere, as WSA-ENLIL predicted it. */
export interface CmeImpact {
  /** "Earth", "STEREO A", … exactly as DONKI spells it. */
  location: string;
  arrivalUnix: number | null;
  isGlancingBlow: boolean;
}

export interface SolarEvent {
  /** DONKI's own activity id, e.g. "2026-08-23T00:12:00-CME-001". */
  id: string;
  kind: SolarEventKind;
  /** Peak for a flare, first appearance for a CME. The time it goes on the track. */
  unix: number;
  /** NOAA SRS region number, or null when DONKI did not attribute one. */
  arNumber: number | null;
  /** Index into `ar/regions.json`; -1 when that region is not currently listed. */
  arIndex: number;
  /** DONKI's page for this event, for the curious (and for us, when debugging). */
  donkiLink: string;
  /** Other events DONKI associates with this one — a flare's CME, or vice versa. */
  linked: string[];

  // --- flare only ---
  /** GOES class exactly as reported, e.g. "M8.1". Empty when unknown. */
  cls?: string;
  beginUnix?: number | null;
  endUnix?: number | null;
  /** Stonyhurst string, e.g. "N05E80". Absent for a backside event. */
  sourceLocation?: string;
  sourceLatDeg?: number;
  /** Carrington longitude of the source, for pinning to the rotating surface. */
  sourceCarrLonDeg?: number;

  // --- CME only ---
  speedKms?: number;
  halfAngleDeg?: number;
  /** Unit vector, ecliptic J2000. See the header — apply NO rotation. */
  dirEcl?: [number, number, number];
  /** When the leading edge crossed 21.5 R_sun, DONKI's reference height. */
  time215Unix?: number | null;
  isEarthDirected?: boolean;
  impacts?: CmeImpact[];
}

export interface SolarEvents {
  events: SolarEvent[];
  counts: { flares: number; cmes: number; xClass: number; fastCmes: number };
  /** Hours of history the product covers — matches the field-line window. */
  windowHours: number;
  /** DONKI's own "prototyping quality / research context" wording. */
  disclaimer: string;
  generatedUnix: number;
  /** "degraded" when the pipeline served a cached DONKI response. */
  status: string;
}

/** A CME at or above this is "fast" — the same threshold the pipeline counts on. */
export const FAST_CME_KMS = 800;

/* eslint-disable @typescript-eslint/naming-convention -- pipeline JSON keys */
interface RawImpact {
  location?: string;
  arrival_unix?: number | null;
  is_glancing_blow?: boolean;
}

interface RawEvent {
  id?: string;
  kind?: string;
  peak_unix?: number;
  start_unix?: number;
  begin_unix?: number | null;
  end_unix?: number | null;
  class?: string;
  ar_number?: number | null;
  ar_index?: number;
  donki_link?: string;
  linked?: string[];
  source_location?: string;
  source_lat_deg?: number;
  source_carr_lon_deg?: number;
  speed_kms?: number;
  half_angle_deg?: number;
  dir_ecl?: number[];
  time21_5_unix?: number | null;
  is_earth_directed?: boolean;
  impacts?: RawImpact[];
}

interface RawEvents {
  events?: RawEvent[];
  counts?: { flares?: number; cmes?: number; x_class?: number; fast_cmes?: number };
  window_hours?: number;
  disclaimer?: string;
  generated_unix?: number;
  status?: string;
}
/* eslint-enable @typescript-eslint/naming-convention */

function num(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function optNum(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function normalize(raw: RawEvent): SolarEvent | null {
  const id = typeof raw.id === "string" ? raw.id : "";
  const kind = raw.kind === "cme" ? "cme" : raw.kind === "flare" ? "flare" : null;
  if (!id || !kind) { return null; }

  const unix = kind === "flare" ? num(raw.peak_unix) : num(raw.start_unix);
  if (!unix) { return null; }

  const base: SolarEvent = {
    id,
    kind,
    unix,
    arNumber: optNum(raw.ar_number),
    arIndex: typeof raw.ar_index === "number" ? raw.ar_index : -1,
    donkiLink: typeof raw.donki_link === "string" ? raw.donki_link : "",
    linked: Array.isArray(raw.linked) ? raw.linked.filter((v) => typeof v === "string") : [],
  };

  if (kind === "flare") {
    base.cls = typeof raw.class === "string" ? raw.class : "";
    base.beginUnix = optNum(raw.begin_unix);
    base.endUnix = optNum(raw.end_unix);
    if (typeof raw.source_location === "string") { base.sourceLocation = raw.source_location; }
    if (typeof raw.source_lat_deg === "number") { base.sourceLatDeg = raw.source_lat_deg; }
    if (typeof raw.source_carr_lon_deg === "number") {
      base.sourceCarrLonDeg = raw.source_carr_lon_deg;
    }
    return base;
  }

  base.speedKms = num(raw.speed_kms);
  base.halfAngleDeg = num(raw.half_angle_deg);
  base.time215Unix = optNum(raw.time21_5_unix);
  base.isEarthDirected = !!raw.is_earth_directed;
  // A CME with no usable direction is still worth marking on the timeline; it
  // just cannot be drawn in 3D. Leave dirEcl undefined rather than faking one.
  const dir = raw.dir_ecl;
  if (Array.isArray(dir) && dir.length === 3 && dir.every((c) => Number.isFinite(c))) {
    base.dirEcl = [dir[0], dir[1], dir[2]];
  }
  base.impacts = Array.isArray(raw.impacts)
    ? raw.impacts.map((hit) => ({
      location: typeof hit.location === "string" ? hit.location : "",
      arrivalUnix: optNum(hit.arrival_unix),
      isGlancingBlow: !!hit.is_glancing_blow,
    }))
    : [];
  return base;
}

/**
 * Fetch and normalize `events/events.json`.
 *
 * A 404 is a NORMAL condition, not an error: the product is optional, a plain
 * `yarn serve` with no `public/data/events/` must simply show no marks, and a
 * DONKI outage can leave it absent. Same contract as regions.ts and
 * useSolarStats' summary.json. An EMPTY event list is also normal — the Sun
 * really does go quiet, and that is data, not failure.
 */
export async function loadEvents(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<SolarEvents | null> {
  let raw: RawEvents;
  try {
    const response = await fetch(new URL("events/events.json", baseUrl).href,
      { signal, cache: "no-store" });
    if (!response.ok) { return null; }
    raw = await response.json() as RawEvents;
  } catch {
    return null;
  }
  if (!raw || typeof raw !== "object") { return null; }

  const events: SolarEvent[] = [];
  for (const entry of (Array.isArray(raw.events) ? raw.events : [])) {
    const built = normalize(entry);
    if (built) { events.push(built); }
  }
  events.sort((a, b) => a.unix - b.unix);

  return {
    events,
    counts: {
      flares: num(raw.counts?.flares),
      cmes: num(raw.counts?.cmes),
      xClass: num(raw.counts?.x_class),
      fastCmes: num(raw.counts?.fast_cmes),
    },
    windowHours: num(raw.window_hours, 72),
    disclaimer: typeof raw.disclaimer === "string" ? raw.disclaimer : "",
    generatedUnix: num(raw.generated_unix),
    status: typeof raw.status === "string" ? raw.status : "ok",
  };
}

// ---------------------------------------------------------------------
// Guest-facing phrasing
// ---------------------------------------------------------------------

/** Headline for the card: "M8.1 flare" / "Fast CME". */
export function eventTitle(event: SolarEvent): string {
  if (event.kind === "flare") {
    return event.cls ? `${event.cls} flare` : "Solar flare";
  }
  const speed = event.speedKms ?? 0;
  if (speed >= FAST_CME_KMS) { return "Fast eruption"; }
  return "Eruption";
}

/**
 * Speed in the units a guest thinks in. Kilometers per second is the number
 * scientists use and is meaningless to most people, so it is followed by
 * something with a scale they own — million mph.
 */
export function describeCmeSpeed(speedKms: number): string {
  if (!(speedKms > 0)) { return ""; }
  const mph = (speedKms * 2236.936) / 1e6;
  return `${Math.round(speedKms).toLocaleString()} km/s — ${mph.toFixed(1)} million mph`;
}

/**
 * What a flare's GOES class actually means. The letters are a base-10 scale
 * (each is 10x the last), which is the single most useful thing to say.
 */
export function describeFlareClass(cls: string): string {
  const letter = (cls || "").charAt(0).toUpperCase();
  if (letter === "X") { return "The strongest class — ten times an M."; }
  if (letter === "M") { return "A medium flare; ten times a C."; }
  if (letter === "C") { return "A common, small flare."; }
  if (letter === "B" || letter === "A") { return "A very small flare."; }
  return "";
}

/** "heading roughly toward Earth" / "heading away from Earth". */
export function describeCmeAim(event: SolarEvent): string {
  if (event.isEarthDirected) { return "Heading toward Earth."; }
  return "Heading away from Earth — no impact expected here.";
}

/** The soonest predicted Earth arrival, if WSA-ENLIL expects one. */
export function earthArrivalUnix(event: SolarEvent): number | null {
  let soonest: number | null = null;
  for (const hit of event.impacts ?? []) {
    if (!hit.location.toLowerCase().startsWith("earth")) { continue; }
    if (hit.arrivalUnix === null) { continue; }
    if (soonest === null || hit.arrivalUnix < soonest) { soonest = hit.arrivalUnix; }
  }
  return soonest;
}

/**
 * Thin a busy window down to the marks worth showing.
 *
 * Keeps the most significant events rather than the most recent: X-class
 * flares and fast CMEs first, then everything else by size. Mirrors
 * useSolarStats.thinFlareEvents, which does the same job for the NOAA flare
 * history — a 72 h window can hold 40+ DONKI events and a track of 40 diamonds
 * is a texture, not information.
 */
export function thinEvents(events: SolarEvent[], maxMarks = 12): SolarEvent[] {
  if (events.length <= maxMarks) { return events.slice(); }
  const score = (e: SolarEvent): number => {
    if (e.kind === "cme") {
      // Speed in km/s maps onto the flare scale below well enough to rank the
      // two kinds against each other: 2000 km/s scores like a mid X.
      return (e.speedKms ?? 0) / 200;
    }
    const cls = e.cls ?? "";
    const letter = cls.charAt(0).toUpperCase();
    const mag = parseFloat(cls.slice(1)) || 1;
    const base = letter === "X" ? 10 : letter === "M" ? 1 : letter === "C" ? 0.1 : 0.01;
    return base * mag;
  };
  return events
    .slice()
    .sort((a, b) => score(b) - score(a))
    .slice(0, maxMarks)
    .sort((a, b) => a.unix - b.unix);
}
