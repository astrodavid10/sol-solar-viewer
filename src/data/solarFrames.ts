// =====================================================================
// Solar reference frames — pure math, no engine
// =====================================================================
// Everything the 3D view needs to place solar-physics data in WWT's world
// frame: heliocentric ecliptic J2000, AU, Sun at the origin, +Z toward the
// ecliptic north pole.
//
// This module is deliberately free of BOTH @wwtelescope/* and three imports
// (CLAUDE.md footgun 12): numbers in, numbers out. That keeps it testable in a
// plain Node harness and keeps the door open for a pure-three.js stage.
//
// The pipeline ships exact per-frame orientation matrices/quaternions in
// pfss/manifest.json — those are what the renderer actually uses. The formulas
// here are the INDEPENDENT cross-check (see b0DegApprox) plus the frame
// arithmetic needed for data that arrives in HEEQ spherical coordinates
// (the live swhv.oma.be spacecraft positions).

import { EARTH, eclipticPositionAU, julianDate, julianDateNow } from "./planets";

export { julianDate, julianDateNow };

/** Sun radius in AU **as WWT draws it** — the engine's `getAdjustedPlanetRadius(0)`.
 *
 *  NOT the physical 695,700 km (which would be 0.00465047 AU). The 0.15%
 *  difference is plainly visible as field-line footpoints floating above or
 *  sinking below the rendered surface, so this number must match the engine's,
 *  not reality's (CLAUDE.md footgun 2).
 */
export const R_SUN_AU = 0.004645784;

/** Astronomical unit in km — for the swhv.oma.be position API, which reports km. */
export const AU_KM = 1.495978707e8;

/** PHYSICAL solar radius in km (IAU 2015 nominal).
 *
 *  Deliberately separate from R_SUN_AU above: this one is for NUMBERS WE SHOW
 *  THE GUEST ("97 R☉"), and it's what the pipeline's `r_rsun` fields use, so
 *  quoting distances with it agrees with JPL Horizons to the digit. R_SUN_AU is
 *  0.1% smaller and exists only so geometry lands on the sphere WWT draws.
 *  Using either one for the other's job is a bug (CLAUDE.md footgun 2).
 */
export const R_SUN_KM = 695700;

/** Solar rotation-axis tilt to the ecliptic (deg). IAU / Carrington value. */
export const SOLAR_AXIS_TILT_DEG = 7.25173;

/** Ascending node of the solar equator on the ecliptic at J2000 (deg). */
export const SOLAR_AXIS_NODE_J2000_DEG = 75.76576;

/** Drift of that node, deg/year (general precession). */
const SOLAR_AXIS_NODE_DRIFT_DEG_PER_YEAR = 0.01397;

const D2R = Math.PI / 180;
const R2D = 180 / Math.PI;
const J2000 = 2451545.0;

export type Vec3 = [number, number, number];

/** Orthonormal right-handed basis, each vector expressed in ecliptic J2000. */
export interface Basis {
  x: Vec3;
  y: Vec3;
  z: Vec3;
}

// ---------------------------------------------------------------------
// Small vector helpers (tuples — no three.js Vector3 down here)
// ---------------------------------------------------------------------

function norm(v: Vec3): Vec3 {
  const n = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
  if (!(n > 0)) { return [0, 0, 1]; }
  return [v[0] / n, v[1] / n, v[2] / n];
}

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

// ---------------------------------------------------------------------
// Solar rotation axis
// ---------------------------------------------------------------------

/** Ascending node of the solar equator at `jd`, in degrees. */
export function solarAxisNodeDeg(jd: number): number {
  const years = (jd - J2000) / 365.25;
  return SOLAR_AXIS_NODE_J2000_DEG + SOLAR_AXIS_NODE_DRIFT_DEG_PER_YEAR * years;
}

/**
 * Unit vector along the Sun's north rotation axis, in ecliptic J2000.
 *
 * For a plane with ascending node Ω and inclination i the normal is
 * (sin i sin Ω, −sin i cos Ω, cos i) — which reduces to the ecliptic pole at
 * i = 0 and is perpendicular to the node direction (cos Ω, sin Ω, 0).
 */
export function sunPoleEcliptic(jd: number): Vec3 {
  const i = SOLAR_AXIS_TILT_DEG * D2R;
  const om = solarAxisNodeDeg(jd) * D2R;
  return [Math.sin(i) * Math.sin(om), -Math.sin(i) * Math.cos(om), Math.cos(i)];
}

// ---------------------------------------------------------------------
// HEEQ (Heliocentric Earth Equatorial)
// ---------------------------------------------------------------------

/**
 * HEEQ basis expressed in ecliptic J2000: z along the solar rotation axis,
 * x toward the Sun→Earth direction with the axial component removed (i.e. the
 * central meridian as seen from Earth), y completing the right-handed set.
 *
 * Cross-check against the pipeline's `mat3_heeq_to_ecliptic_j2000` (whose
 * COLUMNS are exactly these three vectors — the manifest is row-major and
 * right-multiplies column vectors).
 */
export function heeqBasis(jd: number): Basis {
  const z = sunPoleEcliptic(jd);
  const earth = eclipticPositionAU(EARTH, jd);
  const d = dot(earth, z);
  const x = norm([earth[0] - d * z[0], earth[1] - d * z[1], earth[2] - d * z[2]]);
  return { x, y: cross(z, x), z };
}

/**
 * HEEQ spherical (r in AU, longitude from the central meridian, heliographic
 * latitude — both radians) → ecliptic-J2000 AU, i.e. WWT world coordinates.
 * This is the shape swhv.oma.be/position returns (`kind=latitudinal`).
 */
export function heeqToWorld(rAU: number, lonRad: number, latRad: number, jd: number): Vec3 {
  const b = heeqBasis(jd);
  const cl = Math.cos(latRad);
  const ex = cl * Math.cos(lonRad);
  const ey = cl * Math.sin(lonRad);
  const ez = Math.sin(latRad);
  return [
    rAU * (ex * b.x[0] + ey * b.y[0] + ez * b.z[0]),
    rAU * (ex * b.x[1] + ey * b.y[1] + ez * b.z[1]),
    rAU * (ex * b.x[2] + ey * b.y[2] + ez * b.z[2]),
  ];
}

// ---------------------------------------------------------------------
// B0 — the independent orientation assertion
// ---------------------------------------------------------------------

/**
 * Apparent geometric ecliptic longitude of the Sun (deg), low-precision
 * series (NOAA / Astronomical Almanac "Approximate Solar Coordinates").
 * Good to ~0.01°, which is an order of magnitude better than the 0.05°
 * tolerance of the b0 assertion below.
 */
export function sunEclipticLongitudeDeg(jd: number): number {
  const n = jd - J2000;
  const meanLon = 280.460 + 0.9856474 * n;
  const meanAnom = (357.528 + 0.9856003 * n) * D2R;
  return meanLon + 1.915 * Math.sin(meanAnom) + 0.020 * Math.sin(2 * meanAnom);
}

/**
 * Heliographic latitude of the sub-Earth point (B0), degrees:
 * sin B0 = sin(λ_sun − Ω) · sin i.
 *
 * Used ONLY by the `?debug=1` assertion against the manifest's own `b0_deg`
 * (computed independently by sunpy in the pipeline). A sign error in the
 * frame conventions shows up here as a degrees-scale disagreement instead of
 * as "everything is subtly rotated" three milestones later.
 */
export function b0DegApprox(jd: number): number {
  const lam = sunEclipticLongitudeDeg(jd);
  const om = solarAxisNodeDeg(jd);
  const i = SOLAR_AXIS_TILT_DEG * D2R;
  return Math.asin(Math.sin((lam - om) * D2R) * Math.sin(i)) * R2D;
}

// ---------------------------------------------------------------------
// Misc conversions used by the UI
// ---------------------------------------------------------------------

/** AU → solar radii, using the SAME R_sun the renderer uses. */
export function auToRSun(au: number): number {
  return au / R_SUN_AU;
}
