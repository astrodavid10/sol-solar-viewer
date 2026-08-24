// =====================================================================
// Sun surface — our own sphere over WWT's, in three modes
// =====================================================================
// WWT draws the Sun as one flat texture that never changes. This module puts a
// sphere 0.1% ABOVE it so ours wins the depth test, and paints it with either
//
//   "sdo"        our pipeline's AIA Carrington map (data/texture/texture.json),
//   "synthetic"  animated granulation + the real sunspot positions,
//   "wwt"        nothing at all (hidden; the engine's own texture shows).
//
// The sphere is opaque (depthWrite AND depthTest on, transparent OFF) because
// its other job is occlusion: far-side field lines must disappear behind it
// exactly as they do behind WWT's own sphere.
//
// ---------------------------------------------------------------------
// THE FRAME (get this wrong by 90 deg and everything below is decoration)
// ---------------------------------------------------------------------
// Our LOCAL frame is the one the PFSS vertices already live in, verified
// against the pipeline (pipeline/pfss/seeds.py:seed_xyz_solrad and the
// astropy cartesian of HeliographicCarrington):
//
//     x = r cos(lat) cos(lon)     lon 0   -> +X
//     y = r cos(lat) sin(lon)     lon 90  -> +Y
//     z = r sin(lat)              lat +90 -> +Z (north)
//
// Measured, not assumed: dequantizing f18.bin and taking atan2(y, x) /
// asin(z/r) at each line's footpoint reproduces topology.bin's own
// seed_lon_u16 / seed_lat_cdeg to 0.01 deg (harness probe-frame.js), and the
// per-AR seed clusters land on ar/regions.json's carr_lon_deg to 0.4 deg.
//
// three r185's SphereGeometry (node_modules/three/src/geometries/
// SphereGeometry.js) generates
//
//     vertex = ( -sin(theta) cos(phi), cos(theta), sin(theta) sin(phi) )
//     u = phi / 2pi          v_uv = 1 - theta / pi
//
// so in GEOMETRY space u=0 sits at -X, u grows -X -> +Z -> +X -> -Z, and the
// texture's TOP row (v_uv = 1, theta = 0) is +Y. The plate-carree contract we
// have to satisfy is u = lon/360 (increasing eastward) and top row = +90 lat.
// Solving for the rotation M with M(-cos l, 0, sin l) = (cos l, sin l, 0) and
// M(0,1,0) = (0,0,1) gives columns [-X, +Z, +Y]:
//
//     M = [ -1  0  0 ; 0  0  1 ; 0  1  0 ]      det = +1
//
// which is a 180 deg turn about (0, 1, 1)/sqrt(2) — GEOM_TO_CARR below. It goes
// on the MESH, so the group above it carries only the same Carrington->ecliptic
// quaternion the field lines use, and texture features therefore sit under
// their own field lines by construction. The synthetic shader applies the same
// swap arithmetically (vec3(-p.x, p.z, p.y)) to get Carrington-local
// coordinates for the sunspots, so both modes share one convention.
//
// No WWT imports (CLAUDE.md footgun 12): the camera position arrives through
// setCameraPosition() from stage.ts's camera.

import {
  Group,
  Mesh,
  MeshBasicMaterial,
  Quaternion,
  RepeatWrapping,
  SRGBColorSpace,
  ShaderMaterial,
  SphereGeometry,
  Texture,
  TextureLoader,
  Vector3,
  WebGLRenderer,
} from "three";

import { SOLID_SIDE } from "./winding";

export type SunSurfaceMode = "sdo" | "synthetic" | "wwt";

/** One sunspot group, straight from `ar/regions.json`. */
export interface SunSpot {
  lonDeg: number;
  latDeg: number;
  /** Corrected area in millionths of a hemisphere (SRS "area_uh"). */
  areaUh: number;
  isComplex: boolean;
}

export interface SunSurfaceOptions {
  /** Sun radius in AU as WWT draws it (footgun 2). */
  rSunAu: number;
  /** `data/` under the deployed app, as `dataBaseUrl()` returns it. */
  dataBaseUrl: string;
  /** Requested mode; the effective mode falls back to "synthetic" with no texture. */
  mode?: SunSurfaceMode;
  /** SDO product code to paint ("0171", "HMIB", ...). Falls back to whatever
   *  the manifest's top-level (default) layer is when this one is absent. */
  channel?: string;
  /** Paint the Carrington longitude markers (`?debug=1`). */
  debug?: boolean;
  /**
   * The renderer whose GL context will actually receive the high-res
   * texture. Used ONLY to read `gl.getParameter(gl.MAX_TEXTURE_SIZE)` for
   * `hasHighRes()` (many mobile GPUs cap at 4096; TEX_HIRES_W is 8192 --
   * see pipeline/config.py). Omitting it makes `hasHighRes()` always
   * report false: refusing an untested GPU is the safe default, not a
   * guess at one that might not fit.
   */
  renderer?: WebGLRenderer;
}

/**
 * One time-aligned Carrington map: the sphere as it looked at one slot of the
 * PFSS timeline.
 *
 * `targetIso` is the slot's grid time and is the KEY — it is what the file name
 * encodes and what the field-line frames share. `obsIso` is when the photons
 * actually arrived, which is within half a slot for a history frame and simply
 * "as fresh as possible" for the newest one.
 */
export interface SunTextureFrame {
  index: number;
  targetIso: string;
  /** `targetIso` as a unix second, for nearest-match against the playhead. */
  targetUnix: number;
  /** Absolute URL, already cache-busted. */
  url: string;
  width: number;
  height: number;
  obsIso: string;
  subEarthCarrLonDeg: number;
  subEarthLatDeg: number;
}

/**
 * One channel's OPT-IN high-resolution newest-frame map (`texture.json`'s
 * per-layer `high_res` block, schema `sol.texture/4`). NEWEST FRAME ONLY --
 * there is no history sequence at this size, so there is exactly one of
 * these per channel, never an array.
 */
export interface SunHighRes {
  /** Absolute URL, already cache-busted. */
  url: string;
  width: number;
  height: number;
  bytes: number;
  obsIso: string;
  subEarthCarrLonDeg: number;
  subEarthLatDeg: number;
}

/** What `texture/texture.json` tells us, normalized.
 *
 *  The scalar sub-Earth / obs fields describe the ACTIVE frame, not the
 *  manifest — `adoptTexture` rewrites them every time a frame is swapped in, so
 *  `subEarthFrame()` and `unobservedFraction()` stay in step with the pixels
 *  actually on the sphere without either of them knowing frames exist. */
export interface SunTextureInfo {
  /** Absolute URL of the image, already cache-busted. */
  url: string;
  obsIso: string;
  subEarthCarrLonDeg: number;
  /** Heliographic latitude of the sub-Earth point (B0) when the map was made. */
  subEarthLatDeg: number;
  /** Absolute URL of this channel's off-limb crop, or "" when absent. */
  offLimbUrl: string;
  /** How far the crop reaches from Sun center, in R_sun. */
  offLimbHalfWidthRSun: number;
  /** How the pipeline filled the hemisphere Earth cannot see ("quiet"). */
  farSide: string;
  generatedUnix: number;
  /** The SDO product code this image actually is. */
  channel: string;
  /** Human label the pipeline published for it ("Magnetic Map"). */
  label: string;
  /** Every channel texture.json publishes, in manifest order (default first). */
  available: string[];
  /**
   * This channel's time-aligned maps, OLDEST FIRST, newest last.
   *
   * Empty for a schema-2 manifest, in which case there is exactly one map and
   * the scrubber cannot change the imagery — which is the behavior this field
   * exists to replace, kept working so an older published tree still renders.
   * Slots the pipeline could not source are ABSENT rather than duplicated, so
   * this array is not necessarily evenly spaced; `frameForUnix` picks nearest.
   */
  frames: SunTextureFrame[];
  /** Index into `frames` of the map currently on the sphere; -1 before load. */
  activeFrame: number;
  /**
   * This channel's opt-in high-res newest-frame map, or null when the
   * pipeline was not run with `--with-hires` for it (or its build failed).
   * Describes what is AVAILABLE, not what is on screen -- see
   * `SunSurface.highResActive()` for that.
   */
  highRes: SunHighRes | null;
}

export interface SunSurface {
  /** Add to the stage's scene. Carries the Carrington orientation. */
  object3d: Group;
  setMode: (mode: SunSurfaceMode) => void;
  /** Paint a different SDO channel. No-op if it is already the active one. */
  setChannel: (channel: string) => void;
  /**
   * Show the map nearest this wall-clock time, so the imagery, the sunspots and
   * the field lines all describe the same hour.
   *
   * SNAPS to a frame rather than cross-fading, following the precedent already
   * set by the solar wind (rebuilt only when `floor(playhead)` changes) rather
   * than the field lines (blended on the GPU by `uMix`). A cross-fade would
   * need a second sampler injected into the material and twice the resident
   * texture memory; snapping at the 4 h slot boundary is what the DATA
   * resolution actually supports.
   *
   * No-op when the manifest has no `frames` array, or when the nearest frame is
   * already the active one.
   */
  setFrameTime: (unixSeconds: number) => void;
  /**
   * True when the active map is the newest one, i.e. the playhead is at "now".
   *
   * The off-limb billboard is a photograph of the corona AS SEEN FROM EARTH
   * RIGHT NOW (footgun 29) and there is only ever one of them, so drawing it
   * around a three-day-old sphere would pair today's prominences with an older
   * photosphere. Callers use this to hide it while scrubbed.
   */
  atNewestFrame: () => boolean;
  /** What we are actually drawing (never "sdo" until a texture has loaded). */
  effectiveMode: () => SunSurfaceMode;
  /** The SAME slerped Carrington->ecliptic quaternion the field lines use. */
  setQuaternion: (q: Quaternion) => void;
  /** World-space camera position, for per-fragment limb darkening. */
  setCameraPosition: (position: Vector3) => void;
  /** Sunspot groups from `ar/regions.json` (first 8 by area). */
  setSpots: (spots: SunSpot[]) => void;
  /** Null until the SDO texture has loaded. */
  textureInfo: () => SunTextureInfo | null;
  /**
   * True when the ACTIVE channel published a high-res newest-frame map AND
   * it fits this GPU's MAX_TEXTURE_SIZE (many mobile GPUs cap at 4096;
   * TEX_HIRES_W is 8192 -- pipeline/config.py). Callers show/hide the
   * opt-in toggle based on this. `setHighRes(true)` when this is false is a
   * harmless no-op, not an error.
   */
  hasHighRes: () => boolean;
  /**
   * Guest opt-in for the high-res newest-frame map. OFF by default (a
   * phone guest who never calls this pays zero extra bytes and zero extra
   * GPU memory -- the JPEG and its ~134 MB decoded RGBA texture, 8192x4096,
   * are fetched ONLY once this is true).
   *
   * Takes effect immediately when the playhead is on the newest frame and
   * `hasHighRes()` is true; otherwise the request is remembered and applied
   * automatically the moment both become true (the playhead returns to
   * "now" via `setFrameTime`, or a `setChannel` switch lands on a channel
   * that published one). Disabling it falls back to whatever normal-res
   * frame is logically active, the same frame the scrubber would show.
   */
  setHighRes: (enabled: boolean) => void;
  /**
   * True while the high-res map is the one ACTUALLY painted on the sphere
   * right now -- both the toggle is on and the playhead is on the newest
   * frame. Distinct from `hasHighRes()`, which only says the option exists;
   * this is what a caller checks to show e.g. a "4K" badge.
   */
  highResActive: () => boolean;
  /**
   * This device's `MAX_TEXTURE_SIZE`, or 0 if unknown (no `renderer` was
   * passed to `createSunSurface`, or the query failed). Exposed for a
   * caller that wants to explain WHY the toggle is hidden rather than just
   * hiding it.
   */
  maxTextureSize: () => number;
  /**
   * Sub-Earth direction and projected solar north, in WORLD space, for the
   * off-limb billboard. Both are carried through this group's own Carrington
   * quaternion, so the billboard cannot drift out of step with the sphere it
   * sits around. False when no texture has loaded.
   */
  subEarthFrame: (dir: Vector3, up: Vector3) => boolean;
  /**
   * How much of what the guest is looking at was never observed: 0 facing the
   * Earth-lit hemisphere, 1 facing the far side, feathered across the same band
   * the shader dims. Null in synthetic mode or before a texture loads, because
   * then there is no observation to be honest about.
   */
  unobservedFraction: () => number | null;
  tick: (dtSeconds: number) => void;
  setVisible: (value: boolean) => void;
  dispose: () => void;
}

// ---------------------------------------------------------------------
// Tunables
// ---------------------------------------------------------------------

/** Radial offset above WWT's sphere. 0.1% is far below anything a units bug
 *  would produce, and enough to win the depth test at every zoom. */
const SURFACE_SCALE = 1.001;

const SEGMENTS_W = 96;
const SEGMENTS_H = 64;

/** Up to this many sunspot groups reach the shader (uniform array size). */
const MAX_SPOTS = 8;

/**
 * GPU memory allowed for decoded Carrington maps, in bytes.
 *
 * A BYTE budget rather than a frame count, because the frames are not the same
 * size: the newest map is 4096x2048 (32 MB as RGBA, before mipmaps) and every
 * history frame is 2048x1024 (8 MB). Counting frames would either allow four
 * newest maps or throw away three history frames for every one of them.
 *
 * 40 MB buys the newest map alone (the state most guests never leave), or five
 * history frames, or the newest plus one — and because it is a plain LRU with no
 * pinning, scrubbing back naturally evicts the big one and buys the guest four
 * more history frames instead. Peak transient is ~48 MB, crossing over.
 *
 * NOT YET MEASURED ON A PHONE. If a mid-range device runs out of texture
 * memory, this is the number to lower; the JPEGs stay in the HTTP cache, so a
 * smaller budget costs a decode on revisit, never a download.
 */
const TEXTURE_BUDGET_BYTES = 40e6;

/** RGBA bytes a decoded map occupies, before mipmaps. */
function textureBytes(width: number, height: number): number {
  // A frame whose manifest entry omitted its size is charged the newest map's
  // cost, which is the conservative direction: under-charging would let the
  // budget be exceeded silently.
  if (!width || !height) { return 32e6; }
  return width * height * 4;
}

/**
 * Granulation cell size, in degrees of heliographic arc. Real granules are
 * ~1 arcsec (0.03 deg) and would alias into gray mush on a phone, so this is a
 * deliberate stylization: 2.1 deg puts ~85 cells across the visible disc, which
 * reads as "boiling surface" at both phone and dome scale.
 */
const CELL_DEG = 2.1;

/** Domain frequency for a unit sphere: one cell per radian-ish. */
const CELL_FREQ = 180 / (Math.PI * CELL_DEG);

/**
 * Granulation evolution. The two animated octaves have their noise domain
 * pushed around a small Lissajous loop, and the offsets are computed on the
 * CPU (two vec3 uniforms) rather than from a `uTime` in the shader. Three
 * reasons, all of which bit the first draft:
 *
 *   - EXACTLY periodic: 12 s and 8 s share a 24 s cycle, so uTime can wrap
 *     with no visible pop. A linear `+= v*t` drift has to wrap sometime, and
 *     wherever it wraps the whole surface re-randomizes in one frame.
 *   - BOUNDED domain: the noise argument never leaves ±(cellFreq + 1), so the
 *     hash keeps its entropy. A linear drift walks off to thousands after an
 *     hour, and highp float fract() quantizes there — the shimmer slowly dies
 *     on a kiosk that has been up all day.
 *   - Free: six sin() calls per FRAME instead of per fragment.
 *
 * Amplitudes are ~0.35-0.5 of a cell, so a cell is meaningfully rebuilt over
 * one period: gentle churn, not boiling.
 */
const DRIFT_PERIOD_A = 12;
const DRIFT_PERIOD_B = 8;
const DRIFT_CYCLE = 24;
const DRIFT_AMP_A = 0.35;
const DRIFT_AMP_B = 0.5;

/** Channel painted when nothing asks for another one — the pipeline's own
 *  default layer (config.TEX_CHANNELS[0]). */
const DEFAULT_CHANNEL = "0171";

/**
 * Where the observed band ends, in radians. These MIRROR the pipeline's
 * TEX_FEATHER_DEG = (75, 90): the map itself cross-fades observation into the
 * far-side fill across that same span, so dimming across it means the darkening
 * lands exactly where the honesty of the pixels does. Change them together.
 */
const OBSERVED_INNER_RAD = (75 * Math.PI) / 180;
const OBSERVED_OUTER_RAD = (90 * Math.PI) / 180;

/**
 * How dark the unobserved hemisphere goes. Not to black: the far side still has
 * to read as part of the same Sun, and a black hemisphere looks like a bug
 * rather than a statement. 0.45 is enough that the terminator is unmistakable
 * while the shape stays legible.
 */
const FAR_SIDE_DIM = 0.45;

// Reused per call; unobservedFraction runs on the DOM-label cadence (~10 Hz),
// not per frame, but allocating two vectors for a dot product is still silly.
const scratchSubEarth = new Vector3();
const scratchView = new Vector3();

/** How often `texture.json` is re-checked while the 3D view is mounted. */
const TEXTURE_POLL_MS = 30 * 60 * 1000;

/** Sunspot angular radius from SRS area: r_deg = max(1.5, sqrt(area_uh)*0.35). */
function spotRadiusDeg(areaUh: number): number {
  return Math.max(1.5, Math.sqrt(Math.max(0, areaUh)) * 0.35);
}

/**
 * Geometry axes -> Carrington local axes (see the header). A 180 deg rotation
 * about (0, 1, 1)/sqrt(2): +Y_geom -> +Z_carr (texture top row -> north pole)
 * and the u=0 meridian -> +X_carr (Carrington longitude 0).
 */
const GEOM_TO_CARR = new Quaternion(0, Math.SQRT1_2, Math.SQRT1_2, 0);

// ---------------------------------------------------------------------
// Shaders (GLSL ES 1.00 — three's ShaderMaterial default, accepted verbatim
// by WebGL2, same as fieldLines.ts)
// ---------------------------------------------------------------------

const VERTEX_SHADER = `
varying vec3 vCarr;
varying vec3 vWorld;

void main() {
  // The CPU-side GEOM_TO_CARR rotation, done arithmetically: columns
  // [-X, +Z, +Y]. Keeping both copies of one 3x3 swap is deliberate: the
  // mesh needs it as a quaternion, the shader needs it per vertex, and a
  // uniform mat3 would let the two drift apart silently.
  vCarr = normalize(vec3(-position.x, position.z, position.y));
  vec4 world = modelMatrix * vec4(position, 1.0);
  vWorld = world.xyz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const FRAGMENT_SHADER = `
#define MAX_SPOTS ${MAX_SPOTS}

uniform vec3 uDriftA;
uniform vec3 uDriftB;
uniform vec3 uCameraPos;
uniform float uCellFreq;
uniform int uSpotCount;
uniform vec3 uSpotDir[MAX_SPOTS];
uniform vec2 uSpotShape[MAX_SPOTS];

varying vec3 vCarr;
varying vec3 vWorld;

// Hash-based value noise (no sin(): mobile drivers disagree about its
// precision, and a sin-hash bands visibly on Adreno).
float hash13(vec3 p) {
  p = fract(p * 0.3183099 + vec3(0.71, 0.113, 0.419));
  p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float vnoise(vec3 x) {
  vec3 i = floor(x);
  vec3 f = fract(x);
  vec3 u = f * f * (3.0 - 2.0 * f);
  float n000 = hash13(i);
  float n100 = hash13(i + vec3(1.0, 0.0, 0.0));
  float n010 = hash13(i + vec3(0.0, 1.0, 0.0));
  float n110 = hash13(i + vec3(1.0, 1.0, 0.0));
  float n001 = hash13(i + vec3(0.0, 0.0, 1.0));
  float n101 = hash13(i + vec3(1.0, 0.0, 1.0));
  float n011 = hash13(i + vec3(0.0, 1.0, 1.0));
  float n111 = hash13(i + vec3(1.0, 1.0, 1.0));
  return mix(
    mix(mix(n000, n100, u.x), mix(n010, n110, u.x), u.y),
    mix(mix(n001, n101, u.x), mix(n011, n111, u.x), u.y),
    u.z);
}

void main() {
  vec3 n = normalize(vCarr);

  // --- granulation ---------------------------------------------------
  // Two low-frequency samples warp the domain so the cells are irregular
  // instead of a visible lattice; the third warp component is -(w1+w2) so the
  // distortion has no net drift direction.
  float w1 = vnoise(n * 2.6 + 3.7) - 0.5;
  float w2 = vnoise(n * 2.6 + 11.3) - 0.5;
  vec3 warp = vec3(w1, w2, -(w1 + w2)) * 0.8;
  vec3 q = n * uCellFreq + warp;

  // Evolution: the two animated octaves ride opposing Lissajous loops
  // (uDriftA/uDriftB, computed per frame on the CPU; see DRIFT_PERIOD_A) so
  // cells build and fade over ~8-12 s without the whole field appearing to
  // flow one way. The finest octave is static, which keeps the texture from
  // sparkling. See CELL_DEG for the spatial half of the stylization.
  float g = 0.55 * vnoise(q + uDriftA)
          + 0.30 * vnoise(q * 2.1 + uDriftB)
          + 0.15 * vnoise(q * 4.3 + 7.0);

  // Deep orange lanes -> #ff8a2b embers -> #ffd27a gold, with a hot cap on the
  // brightest granules. Written straight to gl_FragColor, which for a
  // ShaderMaterial is already in the renderer's output space (no
  // <colorspace_fragment> include), so these ARE the sRGB values.
  vec3 lane = vec3(0.72, 0.26, 0.05);
  vec3 ember = vec3(1.00, 0.541, 0.169);
  vec3 gold = vec3(1.00, 0.824, 0.478);
  vec3 hot = vec3(1.00, 0.96, 0.86);
  vec3 color = mix(lane, ember, smoothstep(0.05, 0.45, g));
  color = mix(color, gold, smoothstep(0.45, 0.85, g));
  color = mix(color, hot, smoothstep(0.88, 1.0, g) * 0.5);

  // Supergranulation-scale mottling, free: reuse the warp noise.
  color *= 0.94 + 0.12 * (w1 + 0.5);

  // --- sunspots ------------------------------------------------------
  // Chord instead of acos(dot): for the 1.5-6 deg radii here the chord length
  // |n - d| matches the arc to better than 0.05%, and costs a subtract.
  float spots = 1.0;
  for (int i = 0; i < MAX_SPOTS; i++) {
    if (i >= uSpotCount) { break; }
    float radius = uSpotShape[i].x;
    float weight = uSpotShape[i].y;
    float t = length(n - uSpotDir[i]) / max(radius, 1e-4);
    float inner = 1.0 - smoothstep(0.50, 0.78, t);
    float outer = 1.0 - smoothstep(0.86, 1.06, t);
    float ring = smoothstep(1.00, 1.14, t) * (1.0 - smoothstep(1.14, 1.45, t));
    float f = mix(1.0, 0.60, outer * weight);
    f = mix(f, 0.25, inner * weight);
    spots *= f * (1.0 + 0.16 * ring * weight);
  }
  color *= spots;

  // --- poles + limb --------------------------------------------------
  color *= mix(1.0, 0.80, pow(abs(n.z), 4.0));

  // Limb darkening from the REAL view direction, so it tracks the camera as
  // the guest orbits. mu is floored so the limb goes deep amber, not black:
  // the sun glow sprite sits on top of exactly this ring.
  vec3 view = normalize(uCameraPos - vWorld);
  float mu = max(dot(normalize(vWorld), view), 0.08);
  color *= pow(mu, 0.6);

  gl_FragColor = vec4(color, 1.0);
}
`;

// ---------------------------------------------------------------------
// texture.json
// ---------------------------------------------------------------------

/* eslint-disable @typescript-eslint/naming-convention -- pipeline JSON keys */
interface RawOffLimb {
  url?: string;
  half_width_rsun?: number;
}

interface RawFrame {
  index?: number;
  target_iso?: string;
  url?: string;
  bytes?: number;
  width?: number;
  height?: number;
  obs_iso?: string;
  sub_earth_carr_lon_deg?: number;
  sub_earth_lat_deg?: number;
}

interface RawHighRes {
  url?: string;
  width?: number;
  height?: number;
  bytes?: number;
  obs_iso?: string;
  sub_earth_carr_lon_deg?: number;
  sub_earth_lat_deg?: number;
  source_url?: string;
}

interface RawLayer {
  channel?: string;
  label?: string;
  sub_earth_lat_deg?: number;
  off_limb?: RawOffLimb;
  wavelength_angstrom?: number | null;
  far_side?: string;
  url?: string;
  obs_iso?: string;
  sub_earth_carr_lon_deg?: number;
  /** schema sol.texture/3: one map per PFSS timeline slot, OLDEST FIRST. */
  frames?: RawFrame[];
  /** schema sol.texture/4: opt-in, newest-frame-only, absent unless the
   *  pipeline ran with --with-hires and this channel's build succeeded. */
  high_res?: RawHighRes;
}

interface RawTexture {
  url?: string;
  /** schema sol.texture/2 and up: one entry per published channel, default
   *  FIRST. The top-level fields still describe that default layer's NEWEST
   *  frame, so a reader that ignores this array is still correct — just
   *  single-channel and always showing "now". */
  layers?: RawLayer[];
  width?: number;
  height?: number;
  obs_iso?: string;
  sub_earth_carr_lon_deg?: number;
  /** Published as a WORD ("quiet"), not a flag — how the far side was filled. */
  far_side?: string | boolean;
  lon_at_u0_deg?: number;
  north_up?: boolean;
  generated_unix?: number;
  wavelength_angstrom?: number | null;
  channel?: string;
  label?: string;
  sub_earth_lat_deg?: number;
  off_limb?: RawOffLimb;
}

interface RawRegion {
  lat_deg?: number;
  carr_lon_deg?: number;
  area_uh?: number;
  is_complex?: boolean;
}

interface RawRegions {
  regions?: RawRegion[];
}
/* eslint-enable @typescript-eslint/naming-convention */

/**
 * Fetch `ar/regions.json` and turn it into sunspots. Lives here rather than in
 * src/data/ because this module is the only consumer and the area→radius model
 * belongs next to the shader that draws it. Absent product → no spots, which
 * is a Sun with a quiet surface, not an error.
 */
async function fetchSpots(baseUrl: string, signal?: AbortSignal): Promise<SunSpot[]> {
  let raw: RawRegions;
  try {
    const response = await fetch(
      new URL("ar/regions.json", baseUrl).href, { signal, cache: "no-store" });
    if (!response.ok) { return []; }
    raw = await response.json() as RawRegions;
  } catch {
    return [];
  }
  const regions = Array.isArray(raw?.regions) ? raw.regions : [];
  const spots: SunSpot[] = [];
  regions.forEach((region) => {
    const lonDeg = region.carr_lon_deg;
    const latDeg = region.lat_deg;
    if (typeof lonDeg !== "number" || typeof latDeg !== "number") { return; }
    spots.push({
      lonDeg,
      latDeg,
      areaUh: typeof region.area_uh === "number" ? region.area_uh : 0,
      isComplex: !!region.is_complex,
    });
  });
  return spots;
}

/**
 * Fetch and normalize `texture/texture.json`.
 *
 * A 404 is a NORMAL condition, not an error: the texture product is optional
 * (index.json ships `"texture": {"status": "absent"}` until the pipeline stage
 * runs) and a plain `yarn serve` with no `public/data/texture/` must fall back
 * to the synthetic surface in silence. Same contract as
 * useSolarStats' stats/summary.json.
 */
async function fetchTextureInfo(
  baseUrl: string,
  channel: string,
  signal?: AbortSignal,
): Promise<SunTextureInfo | null> {
  const manifestUrl = new URL("texture/texture.json", baseUrl).href;
  let raw: RawTexture;
  try {
    const response = await fetch(manifestUrl, { signal, cache: "no-store" });
    if (!response.ok) { return null; }
    raw = await response.json() as RawTexture;
  } catch {
    return null;
  }
  if (!raw || typeof raw.url !== "string" || raw.url === "") { return null; }

  // The one contract term the geometry depends on. The published product says
  // `lon_at_u0_deg: 0` and `north_up: true`; if a future run ever changes
  // either, this mapping is wrong and the synthetic surface is the honest
  // fallback — silently drawing a rotated Sun would be worse.
  if (typeof raw.lon_at_u0_deg === "number" && Math.abs(raw.lon_at_u0_deg) > 0.5) {
    console.warn(`[sunSurface] texture lon_at_u0_deg is ${raw.lon_at_u0_deg}, not 0 — `
      + "this build maps texture column u=0 to Carrington longitude 0; staying synthetic.");
    return null;
  }
  if (raw.north_up === false) {
    console.warn("[sunSurface] texture is not north-up; staying synthetic.");
    return null;
  }

  const generatedUnix = typeof raw.generated_unix === "number" ? raw.generated_unix : 0;

  // The top-level fields ARE the default layer (see RawTexture.layers), so a
  // single-channel manifest needs no special case — it is a one-entry list.
  /* eslint-disable @typescript-eslint/naming-convention -- pipeline JSON keys */
  const published: RawLayer[] = Array.isArray(raw.layers) && raw.layers.length
    ? raw.layers.filter((layer) => typeof layer?.url === "string" && layer.url !== "")
    : [{
      channel: typeof raw.channel === "string" ? raw.channel : "",
      label: typeof raw.label === "string" ? raw.label : "",
      url: raw.url,
      obs_iso: raw.obs_iso,
      sub_earth_carr_lon_deg: raw.sub_earth_carr_lon_deg,
      sub_earth_lat_deg: raw.sub_earth_lat_deg,
      off_limb: raw.off_limb,
    }];
  /* eslint-enable @typescript-eslint/naming-convention */
  const available = published
    .map((layer) => layer.channel)
    .filter((c): c is string => typeof c === "string" && c !== "");

  // Asking for a channel this run did not publish is NORMAL — one AIA channel
  // can fail while the others succeed (cli.run_texture skips it) — so fall back
  // to the default rather than showing nothing.
  const chosen = published.find((layer) => layer.channel === channel) ?? published[0];
  if (!chosen || typeof chosen.url !== "string" || chosen.url === "") { return null; }

  // Cache-bust on the pipeline's own generation stamp: file names are stable
  // across runs, so without this a phone would keep showing yesterday's Sun.
  // Applied to the off-limb crop too — it is regenerated on the same cadence.
  const withStamp = (u: URL): URL => {
    if (generatedUnix) { u.searchParams.set("v", String(generatedUnix)); }
    return u;
  };

  const imageUrl = withStamp(new URL(chosen.url, manifestUrl));

  // One map per PFSS timeline slot. A frame whose target_iso does not parse is
  // dropped rather than guessed at: it is the KEY the playhead matches on, and
  // a frame at the wrong time is worse than a missing one — the app falls back
  // to the nearest good frame either way.
  const frames: SunTextureFrame[] = (Array.isArray(chosen.frames) ? chosen.frames : [])
    .map((frame): SunTextureFrame | null => {
      if (typeof frame?.url !== "string" || frame.url === "") { return null; }
      const targetUnix = Date.parse(String(frame.target_iso)) / 1000;
      if (!Number.isFinite(targetUnix)) { return null; }
      return {
        index: 0,
        targetIso: String(frame.target_iso),
        targetUnix,
        url: withStamp(new URL(frame.url, manifestUrl)).href,
        width: typeof frame.width === "number" ? frame.width : 0,
        height: typeof frame.height === "number" ? frame.height : 0,
        obsIso: typeof frame.obs_iso === "string" ? frame.obs_iso : "",
        subEarthCarrLonDeg: typeof frame.sub_earth_carr_lon_deg === "number"
          ? frame.sub_earth_carr_lon_deg
          : Number.NaN,
        subEarthLatDeg: typeof frame.sub_earth_lat_deg === "number"
          ? frame.sub_earth_lat_deg
          : 0,
      };
    })
    .filter((frame): frame is SunTextureFrame => frame !== null)
    // Sort by target rather than trusting the published order, then renumber:
    // `index` has to agree with the position in THIS array, because a slot the
    // pipeline could not source is absent and would otherwise leave a hole.
    .sort((a, b) => a.targetUnix - b.targetUnix)
    .map((frame, i) => ({ ...frame, index: i }));

  // The scalar fields describe the frame that will be shown FIRST, which is the
  // newest — same as a schema-2 manifest, so nothing changes until the guest
  // actually scrubs.
  const newest = frames.length ? frames[frames.length - 1] : null;

  /* eslint-disable-next-line @typescript-eslint/naming-convention -- pipeline JSON keys */
  const rawHighRes = chosen.high_res;
  const highRes: SunHighRes | null = (typeof rawHighRes?.url === "string"
    && rawHighRes.url !== ""
    && typeof rawHighRes.width === "number"
    && typeof rawHighRes.height === "number")
    ? {
      url: withStamp(new URL(rawHighRes.url, manifestUrl)).href,
      width: rawHighRes.width,
      height: rawHighRes.height,
      bytes: typeof rawHighRes.bytes === "number" ? rawHighRes.bytes : 0,
      obsIso: typeof rawHighRes.obs_iso === "string" ? rawHighRes.obs_iso : "",
      subEarthCarrLonDeg: typeof rawHighRes.sub_earth_carr_lon_deg === "number"
        ? rawHighRes.sub_earth_carr_lon_deg
        : Number.NaN,
      subEarthLatDeg: typeof rawHighRes.sub_earth_lat_deg === "number"
        ? rawHighRes.sub_earth_lat_deg
        : 0,
    }
    : null;

  return {
    url: newest ? newest.url : imageUrl.href,
    obsIso: newest ? newest.obsIso
      : (typeof chosen.obs_iso === "string" ? chosen.obs_iso : ""),
    subEarthCarrLonDeg: newest ? newest.subEarthCarrLonDeg
      : (typeof chosen.sub_earth_carr_lon_deg === "number"
        ? chosen.sub_earth_carr_lon_deg
        : Number.NaN),
    subEarthLatDeg: newest ? newest.subEarthLatDeg
      : (typeof chosen.sub_earth_lat_deg === "number"
        ? chosen.sub_earth_lat_deg
        : 0),
    offLimbUrl: typeof chosen.off_limb?.url === "string" && chosen.off_limb.url
      ? withStamp(new URL(chosen.off_limb.url, manifestUrl)).href
      : "",
    offLimbHalfWidthRSun: typeof chosen.off_limb?.half_width_rsun === "number"
      ? chosen.off_limb.half_width_rsun
      : 0,
    farSide: typeof raw.far_side === "string" ? raw.far_side : (raw.far_side ? "present" : ""),
    generatedUnix,
    channel: typeof chosen.channel === "string" ? chosen.channel : "",
    label: typeof chosen.label === "string" ? chosen.label : "",
    available,
    frames,
    activeFrame: newest ? newest.index : -1,
    highRes,
  };
}

/**
 * The frame whose slot is nearest `unixSeconds`, or null when there are none.
 *
 * Nearest rather than floor: slots are 4 h apart and a playhead between two of
 * them is genuinely closer to one. Frames the pipeline could not source are
 * simply absent, so this also does the right thing across a gap in the archive
 * (measured: the SDO browse tree for 2026-08-21 stops at 12:42 UT in every
 * channel, which leaves three slots empty) — it lands on the nearest frame that
 * exists instead of showing nothing.
 */
function frameForUnix(frames: SunTextureFrame[], unixSeconds: number): SunTextureFrame | null {
  if (!frames.length || !Number.isFinite(unixSeconds)) { return null; }
  let best = frames[0];
  let bestGap = Math.abs(frames[0].targetUnix - unixSeconds);
  for (let i = 1; i < frames.length; i++) {
    const gap = Math.abs(frames[i].targetUnix - unixSeconds);
    if (gap < bestGap) {
      best = frames[i];
      bestGap = gap;
    }
  }
  return best;
}

/**
 * `gl.getParameter(gl.MAX_TEXTURE_SIZE)` for the renderer that will actually
 * receive the high-res texture, or 0 when unknown.
 *
 * Read from the LIVE renderer rather than assumed: many mobile GPUs cap at
 * 4096 and TEX_HIRES_W is 8192 (pipeline/config.py), so this is a real wall,
 * not a formality. No throwaway-canvas fallback when `renderer` is omitted
 * -- a scratch WebGL context can report a different limit than the one
 * actually in use (a software fallback context, a different power
 * preference), and guessing wrong in the OPTIMISTIC direction is exactly
 * the failure mode hard constraint 1 exists to prevent. 0 means
 * `hasHighRes()` is always false, which is the safe reading of "unknown".
 */
function detectMaxTextureSize(renderer?: WebGLRenderer): number {
  if (!renderer) { return 0; }
  try {
    const gl = renderer.getContext();
    const size = gl.getParameter(gl.MAX_TEXTURE_SIZE) as unknown;
    return typeof size === "number" && size > 0 ? size : 0;
  } catch {
    return 0;
  }
}

// ---------------------------------------------------------------------
// Layer
// ---------------------------------------------------------------------

export function createSunSurface(options: SunSurfaceOptions): SunSurface {
  const geometry = new SphereGeometry(
    options.rSunAu * SURFACE_SCALE, SEGMENTS_W, SEGMENTS_H);

  const spotDir = new Float32Array(MAX_SPOTS * 3);
  const spotShape = new Float32Array(MAX_SPOTS * 2);

  const synthetic = new ShaderMaterial({
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    uniforms: {
      uDriftA: { value: new Vector3() },
      uDriftB: { value: new Vector3() },
      uCameraPos: { value: new Vector3(0, 0, 1) },
      uCellFreq: { value: CELL_FREQ },
      uSpotCount: { value: 0 },
      uSpotDir: { value: spotDir },
      uSpotShape: { value: spotShape },
    },
    // Opaque, and it writes depth: this sphere is what hides the far-side
    // field lines (the whole point of the shared-canvas target, footgun 4).
    transparent: false,
    depthTest: true,
    depthWrite: true,
    // WWT's camera reverses winding, so FrontSide would cull the near
    // hemisphere and leave us looking at the inside of the far one — which is
    // exactly what "the texture shows through the Sun, and it's dark" was.
    // See src/three/winding.ts.
    side: SOLID_SIDE,
  });

  // AIA is self-luminous, so the SDO mode is deliberately unlit — a
  // MeshBasicMaterial reproduces the disc view's own look exactly.
  // Uniforms shared with the injected far-side dimming below. Held here (not
  // in a ShaderMaterial) because MeshBasicMaterial + onBeforeCompile keeps
  // three's color management: the map is an sRGB texture, and a hand-rolled
  // ShaderMaterial writing gl_FragColor would have to redo the sRGB->linear
  // sample and the output encoding by hand, which is exactly the kind of thing
  // that silently ships a washed-out Sun.
  const farSide = {
    // (l0 radians, sin(B0), cos(B0)) — everything the spherical law of cosines
    // needs, precomputed so the shader does no trig on constants.
    uSubEarth: { value: new Vector3(0, 0, 1) },
    // Feather half-angles in RADIANS, matching the pipeline's TEX_FEATHER_DEG.
    uObserved: { value: new Vector3(OBSERVED_INNER_RAD, OBSERVED_OUTER_RAD, 0) },
    uFarDim: { value: FAR_SIDE_DIM },
  };

  const sdo = new MeshBasicMaterial({
    transparent: false,
    depthTest: true,
    depthWrite: true,
    side: SOLID_SIDE,
  });

  /**
   * Darken the hemisphere Earth cannot see.
   *
   * The map is a Carrington plate carree, so a fragment's heliographic
   * position falls straight out of its uv: lon = u*360, lat = (v-0.5)*180
   * (three's default flipY puts v=1 at the image's top row, which the pipeline
   * writes as +90 lat). The angular distance to the sub-Earth point is then one
   * spherical law of cosines, with no varying to thread through the vertex
   * stage and no extra attribute.
   *
   * Why do it at all: for the EUV channels the far side is a stylized
   * quiet-Sun fill, and for the two HMI products a flat neutral one. Neither is
   * an observation, and at full brightness both read as though they were.
   * Dimming says "we don't know this half" in the one language a picture has.
   */
  sdo.onBeforeCompile = (shader) => {
    shader.uniforms.uSubEarth = farSide.uSubEarth;
    shader.uniforms.uObserved = farSide.uObserved;
    shader.uniforms.uFarDim = farSide.uFarDim;
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>
        uniform vec3 uSubEarth;
        uniform vec3 uObserved;
        uniform float uFarDim;`)
      .replace("#include <map_fragment>", `#include <map_fragment>
        {
          float lon = vMapUv.x * 6.283185307179586;
          float lat = (vMapUv.y - 0.5) * 3.141592653589793;
          float cosd = sin(lat) * uSubEarth.y
                     + cos(lat) * uSubEarth.z * cos(lon - uSubEarth.x);
          float ang = acos(clamp(cosd, -1.0, 1.0));
          float far = smoothstep(uObserved.x, uObserved.y, ang);
          diffuseColor.rgb *= mix(1.0, uFarDim, far);
        }`);
  };

  // Explicit union: the two modes swap `mesh.material` in place, which is
  // cheaper and simpler than two meshes sharing one geometry.
  const mesh = new Mesh<SphereGeometry, ShaderMaterial | MeshBasicMaterial>(geometry, synthetic);
  mesh.quaternion.copy(GEOM_TO_CARR);
  mesh.frustumCulled = false;
  // Opaque, so three draws it before every transparent layer regardless; the
  // explicit 0 documents that the field lines (renderOrder 10) come after.
  mesh.renderOrder = 0;

  const group = new Group();
  group.add(mesh);

  let requested: SunSurfaceMode = options.mode ?? "sdo";
  /** Channel the guest has asked for; the manifest decides what we get. */
  let channel = options.channel ?? DEFAULT_CHANNEL;
  /** Seconds into the granulation cycle (wraps at DRIFT_CYCLE, seamlessly). */
  let clock = 0;
  let texture: Texture | null = null;
  let info: SunTextureInfo | null = null;
  let visible = true;
  let destroyed = false;
  let poll = 0;
  const abort = new AbortController();
  const loader = new TextureLoader();
  // Same-origin in every deployment we have (Pages and the dev server both
  // serve data/ from the app's own origin), but an anonymous request keeps the
  // texture CORS-clean if the data tree ever moves to a CDN.
  loader.crossOrigin = "anonymous";

  // --- opt-in high-res newest-frame map (hard constraints 1, 2, 4) --------
  // Read once: a real driver limit does not change over a page's lifetime,
  // and detectMaxTextureSize() does a getParameter() round-trip that has no
  // business running on a hot path.
  const maxTextureSize = detectMaxTextureSize(options.renderer);
  /** Guest opt-in, remembered independently of whether it is applicable
   *  RIGHT NOW (wrong channel, scrubbed off newest) so it re-applies the
   *  moment it becomes applicable again. Default OFF (hard constraint 4). */
  let hiresWanted = false;
  /** True while the hi-res map is the one actually painted on the sphere. */
  let hiresOnScreen = false;
  let hiresLoading = false;
  /**
   * The one resident high-res texture, if any -- deliberately NOT part of
   * the `resident` LRU above.
   *
   * An 8192x4096 RGBA texture is ~134 MB (hard constraint 2), more than 3x
   * TEXTURE_BUDGET_BYTES by itself. Folding it into the shared LRU would
   * mean either it evicts every prefetched history frame the instant a
   * guest opts in (defeating the scrub-ahead prefetch for no reason -- nothing
   * scrubbing does needs the hi-res map to be evicted), or -- once a second
   * texture is resident -- it becomes eligible for eviction itself under
   * budget pressure while still on screen, which the "never evict the frame
   * on screen" rule only protects when it is the LRU's SOLE entry. Since it
   * is single-purpose (one channel, the newest slot, opt-in), it gets its
   * own one-slot cache instead: at most one resident at a time, disposed
   * explicitly on replace or teardown, and never counted against
   * TEXTURE_BUDGET_BYTES because it can never be an LRU eviction candidate.
   */
  let hiresTexture: Texture | null = null;
  let hiresUrl: string | null = null;

  function effective(): SunSurfaceMode {
    if (requested === "sdo" && !texture) { return "synthetic"; }
    return requested;
  }

  function applyMode(): void {
    const mode = effective();
    // The mesh renders in EVERY mode: our shared-canvas pass clears WWT's
    // depth buffer (see three-wwt/setupThreeWWT.ts — WWT's own depth values
    // proved untrustworthy and were occluding this sphere entirely), so this
    // sphere is now the only thing that makes far-side field lines hide
    // behind the Sun. In "wwt" (Plain) mode it therefore stays visible but
    // writes DEPTH ONLY (colorWrite off): the engine's own texture shows
    // through while occlusion keeps working.
    mesh.visible = visible;
    mesh.material = mode === "sdo" ? sdo : synthetic;
    const paint = mode !== "wwt";
    sdo.colorWrite = paint;
    synthetic.colorWrite = paint;
  }

  /**
   * Decoded maps we are holding, keyed on URL, in LEAST-RECENTLY-USED ORDER.
   *
   * This replaces "exactly one resident texture, always" — which was correct
   * when there was one map per channel and is wrong now that scrubbing walks a
   * 19-frame sequence: disposing on every step would re-decode 8 MB per slot
   * crossed, on the main thread, while the guest is dragging.
   *
   * A JS Map iterates in insertion order, so re-inserting on every hit makes
   * the first entry the least recently used and eviction is `keys().next()`.
   */
  const resident = new Map<string, Texture>();
  let residentBytes = 0;
  /**
   * The wall-clock time the caller last asked for, or null for "newest".
   *
   * Kept so a CHANNEL switch lands on the same moment in time: without it,
   * switching from Coronal Loops to Magnetic Map while scrubbed three days back
   * would jump to now, which reads as the scrubber breaking.
   */
  let wantUnix: number | null = null;
  /** Prefetches in flight, so two scrub steps do not request the same map. */
  const pending = new Set<string>();

  function touchResident(url: string, tex: Texture, bytes: number): void {
    if (resident.has(url)) {
      resident.delete(url);
      resident.set(url, tex);
      return;
    }
    resident.set(url, tex);
    residentBytes += bytes;
    // Never evict the map currently on the sphere, whatever the budget says:
    // dropping it would blank the Sun to satisfy an accounting rule.
    while (residentBytes > TEXTURE_BUDGET_BYTES && resident.size > 1) {
      const oldestUrl = resident.keys().next().value as string | undefined;
      if (oldestUrl === undefined || oldestUrl === url) { break; }
      const oldest = resident.get(oldestUrl);
      resident.delete(oldestUrl);
      if (oldest) {
        residentBytes -= textureBytes(
          (oldest.image as { width?: number } | undefined)?.width ?? 0,
          (oldest.image as { height?: number } | undefined)?.height ?? 0);
        oldest.dispose();
      }
    }
    if (residentBytes < 0) { residentBytes = 0; }
  }

  /** Where Earth was when the map now on screen was made -- drives the
   *  far-side dimming in sdo's fragment shader (onBeforeCompile above). */
  function applyFarSide(l0Deg: number, latDeg: number): void {
    const l0 = Number.isFinite(l0Deg) ? l0Deg : 0;
    const b0 = (latDeg * Math.PI) / 180;
    (farSide.uSubEarth.value as Vector3).set(
      (l0 * Math.PI) / 180, Math.sin(b0), Math.cos(b0));
  }

  /** True once the manifest has no `frames` (schema-2: one map, and it IS
   *  the newest) or the active frame is the last one. The single source for
   *  both the exported `atNewestFrame()` and the hi-res gate below, so they
   *  can never disagree about what "newest" means. */
  function isAtNewestFrame(): boolean {
    if (!info || !info.frames.length) { return true; }
    return info.activeFrame === info.frames.length - 1;
  }

  function hiresFits(meta: SunHighRes | null): meta is SunHighRes {
    return !!meta && maxTextureSize > 0
      && meta.width <= maxTextureSize && meta.height <= maxTextureSize;
  }

  function disposeHighRes(): void {
    hiresTexture?.dispose();
    hiresTexture = null;
    hiresUrl = null;
  }

  /** Paint the (already loaded) high-res texture over whatever normal-res
   *  paint adoptTexture just did. Does NOT touch `info`'s own url/obsIso/
   *  sub-earth fields -- those keep describing the normal-res frame (see
   *  `SunSurface.textureInfo`'s doc), so `checkTexture`'s "has the manifest
   *  actually changed" comparison stays meaningful while hi-res is showing.
   *  `subEarthFrame`/`unobservedFraction` read the hi-res map's OWN
   *  sub-earth point instead, via `activeSubEarthDeg` below. */
  function paintHighRes(tex: Texture, meta: SunHighRes): void {
    if (destroyed) { return; }
    tex.colorSpace = SRGBColorSpace;
    tex.wrapS = RepeatWrapping;
    tex.anisotropy = 4;
    tex.needsUpdate = true;
    sdo.map = tex;
    sdo.needsUpdate = true;
    applyFarSide(meta.subEarthCarrLonDeg, meta.subEarthLatDeg);
    hiresOnScreen = true;
  }

  function loadHighRes(meta: SunHighRes): void {
    if (hiresLoading) { return; }
    if (hiresTexture && hiresUrl === meta.url) {
      // Already decoded (guest toggled off and back on, or scrubbed away
      // from "now" and straight back) -- paint synchronously.
      paintHighRes(hiresTexture, meta);
      return;
    }
    hiresLoading = true;
    loader.load(
      meta.url,
      (loaded) => {
        hiresLoading = false;
        if (destroyed) {
          loaded.dispose();
          return;
        }
        disposeHighRes();      // at most one resident at a time (see above)
        hiresTexture = loaded;
        hiresUrl = meta.url;
        paintHighRes(loaded, meta);
      },
      undefined,
      () => {
        hiresLoading = false;
        // Nothing to say to the guest: the normal-res frame adoptTexture
        // already painted stays up, which is the honest fallback.
        console.warn(`[sunSurface] high-res texture unavailable: ${meta.url}`);
      },
    );
  }

  /**
   * Load and paint the active channel's high-res map IF the guest opted in,
   * it fits this GPU, and the playhead is on the newest slot -- otherwise a
   * no-op, leaving whatever normal-res paint just happened alone.
   *
   * Called at the tail of every `adoptTexture` (so scrubbing off the newest
   * slot falls back to the normal frame automatically: adoptTexture already
   * repainted it before this runs and finds nothing to override) and from
   * `setHighRes(true)`.
   */
  function applyHighRes(): void {
    if (destroyed || !info) { return; }
    if (hiresWanted && isAtNewestFrame() && hiresFits(info.highRes)) {
      loadHighRes(info.highRes);
    }
  }

  /** The sub-earth point of whatever is ACTUALLY painted right now, for
   *  subEarthFrame()/unobservedFraction() -- the hi-res map's own value
   *  while it is on screen (see paintHighRes), the normal frame's otherwise.
   *  Never more than ~0.05 deg apart in practice (both are "the newest
   *  usable browse frame", fetched minutes apart at worst), but there is no
   *  reason to be sloppy about which one a fragment shader and a billboard
   *  orientation actually agree with. */
  function activeSubEarthDeg(): { lonDeg: number; latDeg: number } | null {
    if (!info) { return null; }
    if (hiresOnScreen && info.highRes) {
      return { lonDeg: info.highRes.subEarthCarrLonDeg, latDeg: info.highRes.subEarthLatDeg };
    }
    return { lonDeg: info.subEarthCarrLonDeg, latDeg: info.subEarthLatDeg };
  }

  function adoptTexture(next: Texture, meta: SunTextureInfo): void {
    if (destroyed) {
      next.dispose();
      return;
    }
    next.colorSpace = SRGBColorSpace;
    // The plate-carree map is seamless in longitude, and the pole rows of
    // SphereGeometry carry a half-texel u offset — repeat, so those triangles
    // wrap instead of smearing the last column.
    next.wrapS = RepeatWrapping;
    next.anisotropy = 4;
    next.needsUpdate = true;

    texture = next;
    info = meta;
    sdo.map = next;
    touchResident(meta.url, next,
      textureBytes(
        (next.image as { width?: number } | undefined)?.width ?? 0,
        (next.image as { height?: number } | undefined)?.height ?? 0));

    // Per-texture, not per-frame: the observed band belongs to the image, so
    // a future per-frame texture sequence gets the sweeping terminator for
    // free.
    applyFarSide(meta.subEarthCarrLonDeg, meta.subEarthLatDeg);

    sdo.needsUpdate = true;
    // No dispose here any more: `touchResident` owns every decoded map's
    // lifetime, so stepping back to a frame we just left is free.
    applyMode();
    // A normal-res frame just got painted, so any hi-res override on screen
    // is stale until applyHighRes() re-asserts it (still wanted, still on
    // the newest slot) -- which is exactly how scrubbing off "now" falls
    // back to the normal frame with no separate code path.
    hiresOnScreen = false;
    applyHighRes();
  }

  function loadTexture(next: SunTextureInfo): void {
    const held = resident.get(next.url);
    if (held) {
      // Already decoded. Adopting it synchronously is what makes scrubbing back
      // across frames we have seen feel instant rather than re-decoding 8 MB.
      adoptTexture(held, next);
      return;
    }
    loader.load(
      next.url,
      (loaded) => adoptTexture(loaded, next),
      undefined,
      () => {
        // The manifest promised an image that isn't there. Nothing to say to
        // the guest — the synthetic surface, or the frame already up, stays.
        console.warn(`[sunSurface] texture image unavailable: ${next.url}`);
      },
    );
  }

  /**
   * Decode a frame into the ring without putting it on the sphere.
   *
   * Called for the neighbors of wherever the playhead lands, so a scrub that
   * keeps going in the same direction finds its next frame already decoded. The
   * budget is what bounds this: a prefetch that would evict the frame on screen
   * cannot happen, because `touchResident` never evicts the active map.
   */
  function prefetchFrame(frame: SunTextureFrame | undefined): void {
    if (!frame || resident.has(frame.url) || pending.has(frame.url)) { return; }
    pending.add(frame.url);
    loader.load(
      frame.url,
      (loaded) => {
        pending.delete(frame.url);
        if (destroyed) {
          loaded.dispose();
          return;
        }
        loaded.colorSpace = SRGBColorSpace;
        loaded.wrapS = RepeatWrapping;
        loaded.anisotropy = 4;
        touchResident(frame.url, loaded,
          textureBytes(frame.width, frame.height));
      },
      undefined,
      () => { pending.delete(frame.url); },
    );
  }

  /** Apply one frame of the active channel to the sphere. */
  function showFrame(frame: SunTextureFrame): void {
    if (!info) { return; }
    const meta: SunTextureInfo = {
      ...info,
      url: frame.url,
      obsIso: frame.obsIso,
      subEarthCarrLonDeg: frame.subEarthCarrLonDeg,
      subEarthLatDeg: frame.subEarthLatDeg,
      activeFrame: frame.index,
    };
    loadTexture(meta);
    // Both neighbors, not just the direction of travel: the playhead reverses
    // constantly while a guest drags, and a wrong guess costs a decode at
    // exactly the moment they are watching.
    prefetchFrame(info.frames[frame.index - 1]);
    prefetchFrame(info.frames[frame.index + 1]);
  }

  async function checkTexture(): Promise<void> {
    const next = await fetchTextureInfo(options.dataBaseUrl, channel, abort.signal);
    if (destroyed || !next) { return; }
    if (info && next.generatedUnix === info.generatedUnix && next.url === info.url) { return; }
    // Adopt the manifest first (so `info.frames` exists), then honor whatever
    // playhead the caller last asked for. Doing it in this order is what lets a
    // 30-minute poll or a channel switch land back on the scrubbed moment
    // instead of snapping the guest to "now" underneath their finger.
    info = next;
    const wanted = wantUnix === null ? null : frameForUnix(next.frames, wantUnix);
    if (wanted) {
      showFrame(wanted);
    } else {
      loadTexture(next);
    }
  }

  // --- ?debug=1: Carrington longitude markers ----------------------------
  // Four dots on the equator at lon 0/90/180/270 IN THE LOCAL FRAME, so they
  // are the ground truth the texture is checked against. What to look for:
  //
  //   1. In "Artist" mode the four dots must be 90 deg apart on the equator
  //      and the sunspots must sit under the dense AR field-line bundles
  //      (today: lon 167, 48, 173, 40 — two pairs ~120 deg apart).
  //   2. Switching Artist <-> Live SDO must not MOVE any feature: the bright
  //      AIA plage has to land on the same bundles the dark spots did.
  //   3. The red dot (lon 0) and the +X axis of the debug triad, both rotated
  //      by the same group quaternion, must coincide.
  //
  // The numeric half of the check is in SolarView3D.assertTextureFacing():
  // the texture's own sub_earth_carr_lon_deg must point at Earth.
  const markers: Mesh[] = [];

  function buildMarkers(): void {
    const colors = [0xff3333, 0x33ff66, 0x3388ff, 0xffcc33];
    const radius = options.rSunAu * 0.03;
    const sphere = new SphereGeometry(radius, 10, 8);
    for (let i = 0; i < 4; i++) {
      const lon = (i * Math.PI) / 2;
      // depthTest off on purpose, exactly as debug.ts's wireframe: all four
      // dots have to be visible at once to check the 90 deg spacing, which
      // means seeing the two on the far side through the Sun.
      const material = new MeshBasicMaterial(
        { color: colors[i], depthTest: false, side: SOLID_SIDE });
      const dot = new Mesh(sphere, material);
      const r = options.rSunAu * 1.01;
      dot.position.set(r * Math.cos(lon), r * Math.sin(lon), 0);
      dot.renderOrder = 31;
      markers.push(dot);
      group.add(dot);
    }
  }

  function applySpots(spots: SunSpot[]): void {
    const chosen = spots
      .slice()
      .sort((a, b) => b.areaUh - a.areaUh)
      .slice(0, MAX_SPOTS);
    // Zero the whole array first: a shrinking region list must not leave a
    // stale spot painted on the surface. This also makes the unused slots
    // no-ops in the shader independently of uSpotCount (weight 0 → factor 1).
    spotDir.fill(0);
    spotShape.fill(0);
    chosen.forEach((spot, i) => {
      const lon = (spot.lonDeg * Math.PI) / 180;
      const lat = (spot.latDeg * Math.PI) / 180;
      const cl = Math.cos(lat);
      spotDir[i * 3] = cl * Math.cos(lon);
      spotDir[i * 3 + 1] = cl * Math.sin(lon);
      spotDir[i * 3 + 2] = Math.sin(lat);
      spotShape[i * 2] = (spotRadiusDeg(spot.areaUh) * Math.PI) / 180;
      // Complex (beta-gamma-delta) groups are the big ragged dark ones; a
      // simple alpha spot is small and gray, so it darkens less.
      spotShape[i * 2 + 1] = spot.isComplex ? 1 : 0.8;
    });
    // No uniformsNeedUpdate: three-wwt calls renderer.resetState() before every
    // render (setupThreeWWT.ts), which nulls the cached program, so
    // ShaderMaterial uniforms are re-uploaded every frame anyway — the same
    // mechanism fieldLines.ts's per-frame uMix relies on.
    synthetic.uniforms.uSpotCount.value = chosen.length;
  }

  if (options.debug) { buildMarkers(); }

  applyMode();
  void checkTexture();
  void fetchSpots(options.dataBaseUrl, abort.signal).then((spots) => {
    if (!destroyed && spots.length) { applySpots(spots); }
  });
  poll = window.setInterval(() => {
    if (document.visibilityState === "visible") { void checkTexture(); }
  }, TEXTURE_POLL_MS);

  return {
    object3d: group,

    setMode(mode: SunSurfaceMode): void {
      requested = mode;
      applyMode();
    },

    setChannel(next: string): void {
      if (!next || next === channel) { return; }
      channel = next;
      // Residency is a shared byte budget across channels AND frames now (see
      // TEXTURE_BUDGET_BYTES), not "one texture, always" — a 19-frame sequence
      // makes that old rule pathological, because every scrub step would
      // re-decode. Switching channel keeps the current playhead: checkTexture
      // re-reads the manifest and then re-seeks to `wantUnix`.
      void checkTexture();
    },

    setFrameTime(unixSeconds: number): void {
      if (!Number.isFinite(unixSeconds)) { return; }
      wantUnix = unixSeconds;
      if (!info || !info.frames.length) { return; }
      const frame = frameForUnix(info.frames, unixSeconds);
      if (!frame || frame.index === info.activeFrame) { return; }
      showFrame(frame);
    },

    // No frames array means a schema-2 manifest: there is exactly one map and
    // it IS the newest, so the off-limb billboard belongs with it. The one
    // implementation lives in isAtNewestFrame() so this and applyHighRes()'s
    // gate can never disagree about what "newest" means.
    atNewestFrame: isAtNewestFrame,

    effectiveMode: effective,

    setQuaternion(q: Quaternion): void {
      group.quaternion.copy(q);
    },

    setCameraPosition(position: Vector3): void {
      (synthetic.uniforms.uCameraPos.value as Vector3).copy(position);
    },

    setSpots: applySpots,

    textureInfo: () => info,

    hasHighRes: () => hiresFits(info?.highRes ?? null),

    setHighRes(enabled: boolean): void {
      if (hiresWanted === enabled) { return; }
      hiresWanted = enabled;
      if (!info) { return; }
      if (enabled) {
        applyHighRes();
        return;
      }
      if (hiresOnScreen) {
        // Revert to whatever normal-res frame is logically active -- the
        // same frame the scrubber would already be showing had hi-res never
        // been on. `info.url` still names it (paintHighRes never touches
        // info), and it is virtually certain still resident: nothing evicts
        // it from the LRU while parked on "now" with hi-res painted over it
        // (no OTHER touchResident call happens in between), so this is a
        // synchronous re-paint, not a re-fetch.
        hiresOnScreen = false;
        loadTexture(info);
      }
    },

    highResActive: () => hiresOnScreen,

    maxTextureSize: () => maxTextureSize,

    subEarthFrame(dir: Vector3, up: Vector3): boolean {
      const sub = activeSubEarthDeg();
      if (!sub) { return false; }
      const l0 = (sub.lonDeg * Math.PI) / 180;
      const b0 = (sub.latDeg * Math.PI) / 180;
      dir.set(Math.cos(b0) * Math.cos(l0), Math.cos(b0) * Math.sin(l0), Math.sin(b0))
        .applyQuaternion(group.quaternion);
      // Solar north in the same frame is simply +Z of the Carrington basis.
      up.set(0, 0, 1).applyQuaternion(group.quaternion);
      // Project out the along-view part so "up" is what up means for a picture.
      const along = up.dot(dir);
      up.addScaledVector(dir, -along);
      if (up.lengthSq() < 1e-12) { return false; }
      up.normalize();
      return true;
    },

    unobservedFraction(): number | null {
      if (effective() !== "sdo" || !info) { return null; }
      const camera = synthetic.uniforms.uCameraPos.value as Vector3;
      if (camera.lengthSq() === 0) { return null; }
      const sub = activeSubEarthDeg();
      if (!sub) { return null; }
      // Sub-Earth direction in the SAME local frame the texture is mapped in,
      // then carried into world space by the group's Carrington quaternion —
      // the one the field lines set. Doing it through the group rather than
      // recomputing an ecliptic vector means this cannot drift out of step
      // with what is actually drawn.
      const l0 = (sub.lonDeg * Math.PI) / 180;
      const b0 = (sub.latDeg * Math.PI) / 180;
      scratchSubEarth
        .set(Math.cos(b0) * Math.cos(l0), Math.cos(b0) * Math.sin(l0), Math.sin(b0))
        .applyQuaternion(group.quaternion);
      scratchView.copy(camera).normalize();
      const angle = Math.acos(
        Math.min(1, Math.max(-1, scratchSubEarth.dot(scratchView))));
      const t = (angle - OBSERVED_INNER_RAD) / (OBSERVED_OUTER_RAD - OBSERVED_INNER_RAD);
      const clamped = Math.min(1, Math.max(0, t));
      return clamped * clamped * (3 - 2 * clamped);
    },

    tick(dtSeconds: number): void {
      if (!Number.isFinite(dtSeconds)) { return; }
      // 24 s is the common multiple of both drift periods, so this wrap is
      // exact: the surface at t and t+24 s is the same surface.
      clock = (clock + Math.max(0, dtSeconds)) % DRIFT_CYCLE;
      const a = (2 * Math.PI * clock) / DRIFT_PERIOD_A;
      const b = (2 * Math.PI * clock) / DRIFT_PERIOD_B;
      (synthetic.uniforms.uDriftA.value as Vector3)
        .set(Math.sin(a), Math.sin(a + 2.1), Math.sin(a + 4.2))
        .multiplyScalar(DRIFT_AMP_A);
      (synthetic.uniforms.uDriftB.value as Vector3)
        .set(Math.sin(b + 1.3), Math.sin(b + 3.4), Math.sin(b + 5.5))
        .multiplyScalar(DRIFT_AMP_B);
    },

    setVisible(value: boolean): void {
      visible = value;
      applyMode();
    },

    dispose(): void {
      destroyed = true;
      window.clearInterval(poll);
      abort.abort();
      markers.forEach((dot) => {
        (dot.material as MeshBasicMaterial).dispose();
      });
      // One shared geometry across the four markers, disposed once.
      if (markers.length) { markers[0].geometry.dispose(); }
      group.clear();
      geometry.dispose();
      synthetic.dispose();
      sdo.dispose();
      // Every decoded map, not just the one on the sphere: the LRU may be
      // holding several frames, and leaking them across a stage teardown is how
      // you end up with GPU memory that never comes back.
      resident.forEach((tex) => tex.dispose());
      resident.clear();
      residentBytes = 0;
      pending.clear();
      texture?.dispose();
      texture = null;
      // Not part of `resident` (see its declaration above), so it needs its
      // own disposal or it leaks a ~134 MB texture per teardown.
      disposeHighRes();
      hiresOnScreen = false;
    },
  };
}
