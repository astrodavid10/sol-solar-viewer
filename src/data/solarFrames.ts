// =====================================================================
// Solar reference frames — pure math, no engine
// =====================================================================
// Everything the 3D view needs to place solar-physics data: heliocentric
// ecliptic J2000, AU, Sun at the origin, +Z toward the ecliptic north pole,
// right-handed. That is the frame the pipeline publishes in, the frame the
// three.js scene is built in, and the frame every vector below is expressed
// in.
//
// It is NOT the frame WWT's engine renders in — see eclipticToWwtWorld at the
// bottom of this file, which is where that difference is stated and where the
// evidence for it lives.
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
 * latitude — both radians) → ecliptic-J2000 AU, i.e. the frame the three.js
 * scene is built in. This is the shape swhv.oma.be/position returns
 * (`kind=latitudinal`).
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
// WWT's world frame — the one thing in this file that is not our own
// ---------------------------------------------------------------------

/**
 * Heliocentric ecliptic J2000 → WWT's solar-system WORLD frame.
 *
 *     (x, y, z)_wwt = (X, Z, Y)_ecliptic
 *
 * so WWT's ecliptic NORTH POLE is +Y, its ecliptic plane is X-Z, and the frame
 * is LEFT-HANDED with respect to physical space (det = -1). Its own inverse.
 *
 * Worth reading twice, because four sessions of this project were built on its
 * opposite and shipped a Sun tilted 90 deg out of the ecliptic and mirrored
 * (CLAUDE.md footgun 47, HANDOFF risk 5). Two things follow:
 *
 *  1. +Y is the pole, not "an arbitrary pair of points in the ecliptic plane"
 *     as footgun 26 used to claim. WWT's camera `lat`/`lng` really are
 *     ecliptic latitude and longitude — which is exactly where a sane camera
 *     parameterization puts its poles.
 *  2. The map is a MIRROR, not a rotation, and that is not a bug in WWT. The
 *     engine renders with left-handed D3D matrices (footgun 19), so a
 *     left-handed world frame and an orientation-reversing projection cancel
 *     and the picture comes out physically correct. Hand WWT a properly
 *     right-handed copy of the solar system and it draws a MIRROR IMAGE —
 *     which is what made the Sun look like it was rotating backwards. The two
 *     "handedness-preserving 90 deg rotations about X" that look like the
 *     obvious fix would each leave that half of the bug in place.
 *
 * HOW IT WAS ESTABLISHED (2026-08-24), because "verified numerically, not
 * visually" is how the original error survived. The engine builds ALL of its
 * planet and orbit geometry with exactly two steps (@wwtelescope/engine
 * src/index.js, Planets.updatePlanetLocations / updateOrbits):
 *
 *     v = Coordinates.raDecTo3dAu(RA, dec, r)   // = (cos.cos, SIN DEC, sin.cos)
 *     v.rotateX(Planets._obliquity)
 *
 * `raDecTo3dAu` puts declination in Y, i.e. it already writes the equatorial
 * triple in the swapped layout, and the rotateX then carries equatorial to
 * ecliptic within it. Pushing arbitrary ecliptic vectors through the engine's
 * own functions returns (x, z, y) to 9e-8 — the residual being only the
 * engine's truncated `RC = 3.1415927/180`.
 *
 * The SIGN was settled two ways, neither by eye:
 *
 *  * POSITION, against INCLINED orbits. WWT's own ephemeris vs our Kepler
 *    elements for six planets: residuals against (x, z, y) are ephemeris-sized
 *    (0.002 AU Earth, 0.05 AU Jupiter), while against (x, -z, y) the
 *    out-of-plane component is wrong by twice the true offset — 0.79 AU on
 *    Saturn, 0.11 AU on Jupiter. Earth alone cannot decide this; a planet out
 *    of the ecliptic can.
 *  * HANDEDNESS, against orbital MOTION. Finite-difference WWT's own planet
 *    positions and take r x v with the ordinary right-handed cross product. In
 *    our ecliptic frame that gives +Z for every planet (prograde, as it must
 *    be); in WWT's world frame it gives -Y for every planet, while the
 *    ecliptic pole maps to +Y. `h_world = -M(h_ecliptic)` is the signature of
 *    det(M) = -1.
 *
 * WHERE IT IS APPLIED: nowhere in the three.js scene — see
 * `three/worldFrame.ts`, which folds the same swap into the three CAMERA so
 * the whole scene can stay in true ecliptic J2000. This tuple form exists for
 * code that talks to WWT's own camera in WWT's own coordinates and therefore
 * cannot: currently only `wwt/sunStage.ts`.
 */
export function eclipticToWwtWorld(v: Vec3): Vec3 {
  return [v[0], v[2], v[1]];
}

// ---------------------------------------------------------------------
// Misc conversions used by the UI
// ---------------------------------------------------------------------

/** AU → solar radii, using the SAME R_sun the renderer uses. */
export function auToRSun(au: number): number {
  return au / R_SUN_AU;
}
