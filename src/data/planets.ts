// =====================================================================
// Solar-system orbital data + Keplerian math
// =====================================================================
// Adapted from exo-sonification's tuningForkData.ts (sonification pieces
// removed). Positions are HELIOCENTRIC ECLIPTIC (J2000) Cartesian vectors in
// AU — x toward the vernal equinox, z toward the ecliptic north pole,
// right-handed. That is the frame the three.js scene is built in, NOT the one
// WWT's engine renders in (which has Y and Z swapped — see
// solarFrames.eclipticToWwtWorld and three/worldFrame.ts).

const D2R = Math.PI / 180;
const J2000 = 2451545.0; // Julian date of the J2000.0 epoch

export interface OrbitBody {
  name: string;
  a: number;          // semi-major axis (AU)
  e: number;          // eccentricity
  iDeg: number;       // inclination to the ecliptic (deg)
  omDeg: number;      // longitude of ascending node Ω (deg)
  wDeg: number;       // argument of perihelion ω (deg)
  m0Deg: number;      // mean anomaly at J2000 (deg)
  periodDays: number; // orbital period (days)
}

// ---------------------------------------------------------------------
// Julian date helpers
// ---------------------------------------------------------------------
export function julianDate(date: Date): number {
  return date.getTime() / 86400000 + 2440587.5;
}
export function julianDateNow(): number {
  return julianDate(new Date());
}

// ---------------------------------------------------------------------
// Kepler solver + ecliptic position
// ---------------------------------------------------------------------
function solveKepler(meanAnomRad: number, e: number): number {
  let meanAnom = meanAnomRad % (2 * Math.PI);
  if (meanAnom < 0) meanAnom += 2 * Math.PI;
  let eccAnom = e < 0.8 ? meanAnom : Math.PI;
  for (let it = 0; it < 60; it++) {
    const d = (eccAnom - e * Math.sin(eccAnom) - meanAnom) / (1 - e * Math.cos(eccAnom));
    eccAnom -= d;
    if (Math.abs(d) < 1e-9) break;
  }
  return eccAnom;
}

// Heliocentric ecliptic (J2000) Cartesian position in AU at Julian date `jd`.
export function eclipticPositionAU(b: OrbitBody, jd: number): [number, number, number] {
  const n = 360 / b.periodDays;                        // deg/day mean motion
  const meanAnom = (b.m0Deg + n * (jd - J2000)) * D2R; // mean anomaly (rad)
  const eccAnom = solveKepler(meanAnom, b.e);
  // Position in the orbital plane
  const xo = b.a * (Math.cos(eccAnom) - b.e);
  const yo = b.a * Math.sqrt(1 - b.e * b.e) * Math.sin(eccAnom);
  return rotateToEcliptic(xo, yo, b);
}

function rotateToEcliptic(xo: number, yo: number, b: OrbitBody): [number, number, number] {
  const cO = Math.cos(b.omDeg * D2R), sO = Math.sin(b.omDeg * D2R);
  const cI = Math.cos(b.iDeg * D2R),  sI = Math.sin(b.iDeg * D2R);
  const cW = Math.cos(b.wDeg * D2R),  sW = Math.sin(b.wDeg * D2R);
  const x = (cO * cW - sO * sW * cI) * xo + (-cO * sW - sO * cW * cI) * yo;
  const y = (sO * cW + cO * sW * cI) * xo + (-sO * sW + cO * cW * cI) * yo;
  const z = (sW * sI) * xo + (cW * sI) * yo;
  return [x, y, z];
}

// Static orbit path (one full revolution) sampled as ecliptic-AU vertices.
export function orbitSampleVerticesAU(b: OrbitBody, segments = 160): [number, number, number][] {
  const out: [number, number, number][] = [];
  for (let k = 0; k <= segments; k++) {
    const eccAnom = (k / segments) * 2 * Math.PI;
    const xo = b.a * (Math.cos(eccAnom) - b.e);
    const yo = b.a * Math.sqrt(1 - b.e * b.e) * Math.sin(eccAnom);
    out.push(rotateToEcliptic(xo, yo, b));
  }
  return out;
}

// ---------------------------------------------------------------------
// Real solar-system bodies (8 planets, JPL approximate J2000 elements,
// valid 1800-2050; ω = ϖ − Ω, M0 = L − ϖ, P = 365.25·a^1.5 d)
// ---------------------------------------------------------------------
function planet(name: string, a: number, e: number, iDeg: number, omDeg: number, varpiDeg: number, lonDeg: number): OrbitBody {
  return {
    name, a, e, iDeg, omDeg,
    wDeg: varpiDeg - omDeg,
    m0Deg: lonDeg - varpiDeg,
    periodDays: 365.25 * Math.pow(a, 1.5),
  };
}

export const SOLAR_SYSTEM_BODIES: OrbitBody[] = [
  planet("Mercury", 0.38709927, 0.20563593,  7.00497902,  48.33076593,  77.45779628, 252.25032350),
  planet("Venus",   0.72333566, 0.00677672,  3.39467605,  76.67984255, 131.60246718, 181.97909950),
  planet("Earth",   1.00000261, 0.01671123, -0.00001531,   0.0,        102.93768193, 100.46457166),
  planet("Mars",    1.52371034, 0.09339410,  1.84969142,  49.55953891, -23.94362959,  -4.55343205),
  planet("Jupiter", 5.20288700, 0.04838624,  1.30439695, 100.47390909,  14.72847983,  34.39644051),
  planet("Saturn",  9.53667594, 0.05386179,  2.48599187, 113.66242448,  92.59887831,  49.95424423),
  planet("Uranus", 19.18916464, 0.04725744,  0.77263783,  74.01692503, 170.95427630, 313.23810451),
  planet("Neptune",30.06992276, 0.00859048,  1.77004347, 131.78422574,  44.96476227, -55.12002969),
];

export const EARTH: OrbitBody = SOLAR_SYSTEM_BODIES[2];

// Outermost orbital radius in a body list — used by the camera to frame a set
// of bodies (real aphelion for eccentric bodies).
export function maxOrbitRadiusAU(bodies: OrbitBody[]): number {
  return bodies.reduce((m, b) => Math.max(m, b.a * (1 + b.e)), 0);
}
