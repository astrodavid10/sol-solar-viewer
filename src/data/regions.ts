// =====================================================================
// Active regions — the Sun's story anchors
// =====================================================================
// `data/ar/regions.json` is NOAA's daily Solar Region Summary digested by the
// pipeline: one entry per numbered region with its Carrington position, spot
// area, Mount Wilson magnetic class, and how many PFSS field lines our own
// model rooted there.
//
// three/sunSurface.ts already fetches this product, but it only wants three
// fields (lon, lat, area) to paint sunspots, and its area→radius model belongs
// next to its shader. This module is the UI's reader: it keeps every field a
// guest-facing card talks about plus the plain-English phrasing, and — like
// spacecraft.ts — stays free of three and WWT imports (CLAUDE.md footgun 12)
// so the numbers could be shown in the disk view too.

import { Vec3 } from "./solarFrames";

export interface SolarRegion {
  /** NOAA region number, e.g. 4513. */
  number: number;
  /** Heliographic latitude, degrees, +north. */
  latDeg: number;
  /** Carrington longitude, degrees. */
  carrLonDeg: number;
  /** Corrected spot area in millionths of a solar hemisphere (SRS "area_uh"). */
  areaUh: number;
  /** Mount Wilson class exactly as the SRS spells it, e.g. "Beta-Gamma-Delta". */
  magType: string;
  /** The pipeline's verdict: gamma/delta complexity worth flagging. */
  isComplex: boolean;
  nSpots: number;
  /** PFSS field lines seeded in this region (how much of the 3D view is "its"). */
  seedCount: number;
}

/* eslint-disable @typescript-eslint/naming-convention -- pipeline JSON keys */
interface RawRegion {
  number?: number;
  lat_deg?: number;
  carr_lon_deg?: number;
  area_uh?: number;
  mag_type?: string;
  is_complex?: boolean;
  n_spots?: number;
  seed_count?: number;
}

interface RawRegions {
  regions?: RawRegion[];
}
/* eslint-enable @typescript-eslint/naming-convention */

function num(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

/**
 * Fetch and normalize `ar/regions.json`.
 *
 * A 404 is a NORMAL condition, not an error: the product is optional (a plain
 * `yarn serve` with no `public/data/ar/` is a Sun with no labelled regions,
 * which is also what a genuinely spotless Sun looks like). Resolves to an empty
 * array on any failure and never throws — the caller checks its own destroyed
 * flag rather than distinguishing an abort from a bad gateway.
 */
export async function loadRegions(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<SolarRegion[]> {
  let raw: RawRegions;
  try {
    const response = await fetch(
      new URL("ar/regions.json", baseUrl).href, { signal, cache: "no-store" });
    if (!response.ok) { return []; }
    raw = await response.json() as RawRegions;
  } catch {
    return [];
  }
  const list = Array.isArray(raw?.regions) ? raw.regions : [];
  const out: SolarRegion[] = [];
  list.forEach((region) => {
    // A region with no position cannot be placed on the sphere, and one with no
    // number cannot be named — either way there is nothing to show.
    if (typeof region.carr_lon_deg !== "number" || typeof region.lat_deg !== "number") { return; }
    if (typeof region.number !== "number") { return; }
    out.push({
      number: region.number,
      latDeg: region.lat_deg,
      carrLonDeg: region.carr_lon_deg,
      areaUh: num(region.area_uh),
      magType: typeof region.mag_type === "string" ? region.mag_type : "",
      isComplex: !!region.is_complex,
      nSpots: num(region.n_spots),
      seedCount: num(region.seed_count),
    });
  });
  return out;
}

/**
 * Carrington LOCAL unit vector for a region, scaled by `radius`:
 *
 *     x = r cos(lat) cos(lon)
 *     y = r cos(lat) sin(lon)
 *     z = r sin(lat)          (+Z north)
 *
 * The same frame the PFSS vertices and the sun surface live in (see the header
 * of three/sunSurface.ts), so the caller turns it into world coordinates with
 * exactly the quaternion those layers use and nothing else.
 */
export function regionVector(region: SolarRegion, radius: number, out: Vec3 = [0, 0, 0]): Vec3 {
  const lon = (region.carrLonDeg * Math.PI) / 180;
  const lat = (region.latDeg * Math.PI) / 180;
  const cl = Math.cos(lat);
  out[0] = radius * cl * Math.cos(lon);
  out[1] = radius * cl * Math.sin(lon);
  out[2] = radius * Math.sin(lat);
  return out;
}

// ---------------------------------------------------------------------
// Friendly copy
// ---------------------------------------------------------------------

/**
 * Earth's silhouette in the SRS unit. A hemisphere of the Sun is 3.04e12 km²
 * and Earth's disc is 1.27e8 km², so one Earth cross-section is ~169 millionths
 * of a hemisphere — the anchor every guest already has for "how big is a
 * sunspot group".
 */
const EARTH_SILHOUETTE_UH = 169;

/**
 * Spot area as a multiple of Earth's disc. Below half an Earth the ratio stops
 * meaning anything to a guest (and the SRS quantizes area to 10 µH anyway), so
 * it becomes a comparison instead of a number.
 */
export function describeRegionArea(areaUh: number): string {
  const earths = areaUh / EARTH_SILHOUETTE_UH;
  if (!(earths >= 0.5)) { return "smaller than Earth"; }
  return `${earths.toFixed(1)} × Earth's cross-section`;
}

/**
 * Mount Wilson class in plain language. Only the two words that matter to a
 * guest are read out of the class string: a DELTA means opposite polarities
 * sharing one penumbra (that is where the big flares come from), and a GAMMA
 * means the polarities are mixed rather than cleanly split.
 */
export function describeRegionMagnetism(magType: string): string {
  const type = magType.toLowerCase();
  if (type.indexOf("delta") >= 0) {
    return "a tangled, flare-prone magnetic knot (delta class)";
  }
  if (type.indexOf("gamma") >= 0) {
    return "a complex magnetic region";
  }
  return "a simple magnetic region";
}
