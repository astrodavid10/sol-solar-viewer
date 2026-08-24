// =====================================================================
// Spacecraft ephemeris — baked trails + optional live "now" dot
// =====================================================================
// Two sources, in priority order:
//
//   1. `data/ephem/spacecraft.json` (same origin, from the pipeline's Horizons
//      bake): ±30 days at 6 h = 241 epochs of heliocentric mean-ecliptic-J2000
//      AU positions. That IS the frame the three scene is built in, so the
//      numbers go straight in with no rotation (the step into WWT's own frame
//      happens once, on the camera — three/worldFrame.ts). Only source for the
//      trails — Horizons has no CORS, and swhv.oma.be takes ONE epoch per call.
//
//   2. swhv.oma.be/position (CORS *) for a fresher now-dot. Returns HEEQ
//      spherical, so it goes through solarFrames.heeqToWorld(). Entirely
//      optional: a timeout or a schema change silently leaves the interpolated
//      Horizons position in place.
//
// WWT- and three-free by design (CLAUDE.md footgun 12).

import { AU_KM, R_SUN_KM, Vec3, heeqToWorld, julianDate } from "./solarFrames";

/** Milliseconds before we give up on the live position service. */
const LIVE_TIMEOUT_MS = 6000;

const LIVE_ENDPOINT = "https://swhv.oma.be/position";

export interface SpacecraftBody {
  id: string;
  name: string;
  /** Hex color from the pipeline (dome palette). */
  color: string;
  /** 3n heliocentric ecliptic-J2000 AU — flattened for three.js. */
  positions: Float32Array;
  /** Distance in PHYSICAL solar radii per epoch (what we show the guest). */
  rRsun: Float32Array;
  rRsunNow: number;
  rRsunMin: number;
}

export interface SpacecraftEphemeris {
  /** Unix seconds, strictly increasing, length n. */
  epochs: Float64Array;
  /** Index of the epoch nearest the pipeline run — the middle of the span. */
  nowIndex: number;
  stepHours: number;
  bodies: SpacecraftBody[];
  /** Earth-orbiting missions with no heliocentric identity of their own. */
  atEarth: { id: string; name: string; note: string }[];
}

/* eslint-disable @typescript-eslint/naming-convention -- pipeline JSON keys */
interface RawBody {
  id: string;
  name: string;
  color: string;
  xyz_au: number[][];
  r_rsun: number[];
  r_rsun_now: number;
  r_rsun_min: number;
}

interface RawEphem {
  epochs_unix: number[];
  now_index: number;
  step_hours: number;
  bodies: RawBody[];
  at_earth?: { id: string; name: string; note: string }[];
}
/* eslint-enable @typescript-eslint/naming-convention */

// ---------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------

/**
 * Fetch and flatten the baked ephemeris. Resolves to null (never throws) when
 * the product is absent — the 3D view simply has no spacecraft that session.
 */
export async function loadSpacecraft(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<SpacecraftEphemeris | null> {
  let raw: RawEphem;
  try {
    const url = new URL("ephem/spacecraft.json", baseUrl).href;
    const response = await fetch(url, { signal });
    if (!response.ok) { return null; }
    raw = await response.json() as RawEphem;
  } catch (err) {
    if (signal?.aborted) { throw err; }
    console.warn("[spacecraft] ephemeris unavailable:", err);
    return null;
  }

  const epochsRaw = raw.epochs_unix ?? [];
  if (epochsRaw.length < 2 || !raw.bodies?.length) { return null; }

  const epochs = new Float64Array(epochsRaw);
  const bodies: SpacecraftBody[] = raw.bodies.map((body) => {
    const n = Math.min(body.xyz_au.length, epochs.length);
    const positions = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const p = body.xyz_au[i];
      positions[i * 3] = p[0];
      positions[i * 3 + 1] = p[1];
      positions[i * 3 + 2] = p[2];
    }
    return {
      id: body.id,
      name: body.name,
      color: body.color || "#ffffff",
      positions,
      rRsun: new Float32Array(body.r_rsun ?? []),
      rRsunNow: body.r_rsun_now,
      rRsunMin: body.r_rsun_min,
    };
  });

  return {
    epochs,
    nowIndex: Math.min(Math.max(raw.now_index ?? 0, 0), epochs.length - 1),
    stepHours: raw.step_hours ?? 6,
    bodies,
    atEarth: raw.at_earth ?? [],
  };
}

// ---------------------------------------------------------------------
// Interpolation
// ---------------------------------------------------------------------

/** Index of the epoch at or before `unixSec` (clamped to the span). */
function bracket(epochs: Float64Array, unixSec: number): number {
  const last = epochs.length - 1;
  if (unixSec <= epochs[0]) { return 0; }
  if (unixSec >= epochs[last]) { return last - 1; }
  let lo = 0;
  let hi = last;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (epochs[mid] <= unixSec) { lo = mid; } else { hi = mid; }
  }
  return lo;
}

/**
 * Linear interpolation of a body's position at `unixSec`, written into `out`.
 * 6 h steps over a smooth heliocentric arc: the chord error is well under a
 * screen pixel at any zoom we allow, so a spline buys nothing.
 */
export function positionAt(
  body: SpacecraftBody,
  epochs: Float64Array,
  unixSec: number,
  out: Vec3 = [0, 0, 0],
): Vec3 {
  const last = epochs.length - 1;
  if (unixSec <= epochs[0] || unixSec >= epochs[last]) {
    const i = unixSec <= epochs[0] ? 0 : last;
    out[0] = body.positions[i * 3];
    out[1] = body.positions[i * 3 + 1];
    out[2] = body.positions[i * 3 + 2];
    return out;
  }
  const i = bracket(epochs, unixSec);
  const t = (unixSec - epochs[i]) / (epochs[i + 1] - epochs[i]);
  for (let k = 0; k < 3; k++) {
    const a = body.positions[i * 3 + k];
    const b = body.positions[(i + 1) * 3 + k];
    out[k] = a + (b - a) * t;
  }
  return out;
}

/** Interpolated distance in PHYSICAL solar radii — the number we show. */
export function rSunAt(body: SpacecraftBody, epochs: Float64Array, unixSec: number): number {
  if (!body.rRsun.length) { return body.rRsunNow; }
  const last = Math.min(epochs.length, body.rRsun.length) - 1;
  if (unixSec <= epochs[0]) { return body.rRsun[0]; }
  if (unixSec >= epochs[last]) { return body.rRsun[last]; }
  const i = bracket(epochs, unixSec);
  const t = (unixSec - epochs[i]) / (epochs[i + 1] - epochs[i]);
  return body.rRsun[i] + (body.rRsun[i + 1] - body.rRsun[i]) * t;
}

// ---------------------------------------------------------------------
// Live now-dot (optional)
// ---------------------------------------------------------------------

/** swhv target names for the bodies we can refresh live. */
const LIVE_TARGETS: Record<string, string> = {
  psp: "PSP",
  solo: "SOLO",
  stereoa: "STEREO Ahead",
};

export interface LivePosition {
  id: string;
  /** Heliocentric ecliptic-J2000 AU — the three scene's frame. */
  world: Vec3;
  rAu: number;
  rSun: number;
}

/**
 * One epoch, one body, from swhv.oma.be. Never throws: on any failure the
 * caller keeps interpolating the baked ephemeris, which is accurate to well
 * under a pixel anyway — this is a freshness nicety, not a dependency.
 */
export async function fetchLivePosition(
  bodyId: string,
  when: Date,
  timeoutMs = LIVE_TIMEOUT_MS,
): Promise<LivePosition | null> {
  const target = LIVE_TARGETS[bodyId];
  if (!target) { return null; }

  // The service wants a bare ISO instant with no trailing "Z".
  const utc = when.toISOString().slice(0, 19);
  const url = `${LIVE_ENDPOINT}?utc=${encodeURIComponent(utc)}`
    + `&observer=SUN&target=${target}&ref=HEEQ&kind=latitudinal`;

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) { return null; }
    const payload = await response.json() as { result?: Record<string, number[]>[] };
    const entry = payload.result?.[0];
    if (!entry) { return null; }
    const triple = Object.values(entry)[0];
    if (!triple || triple.length < 3) { return null; }

    const [distKm, lonRad, latRad] = triple;
    if (!Number.isFinite(distKm) || distKm <= 0) { return null; }

    const rAu = distKm / AU_KM;
    const world = heeqToWorld(rAu, lonRad, latRad, julianDate(when));
    return { id: bodyId, world, rAu, rSun: distKm / R_SUN_KM };
  } catch {
    // Timeout, CORS hiccup, schema drift — all the same to us.
    return null;
  } finally {
    window.clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------
// Friendly copy
// ---------------------------------------------------------------------

/** Mercury's perihelion in solar radii — the "closer than Mercury" threshold. */
const MERCURY_PERIHELION_RSUN = 83;

/**
 * Plain-English context for a distance. Guests have no intuition for solar
 * radii, so every number gets an anchor they do have.
 */
export function describeDistance(rSun: number): string {
  if (rSun < MERCURY_PERIHELION_RSUN) { return "closer to the Sun than Mercury"; }
  if (rSun < 150) { return "between Mercury and Venus"; }
  if (rSun < 200) { return "about as far out as Venus"; }
  if (rSun < 235) { return "about as far from the Sun as we are"; }
  return "farther from the Sun than Earth";
}

const BLURBS: Record<string, string> = {
  psp: "The fastest human-made object — it flies through the Sun's corona.",
  solo: "ESA's Sun observer, taking the closest-ever pictures of our star.",
  stereoa: "Watching the Sun from a different angle than Earth since 2006 — it sees storms coming before we do.",
  earth: "",
};

export function bodyBlurb(bodyId: string): string {
  return BLURBS[bodyId] ?? "";
}
