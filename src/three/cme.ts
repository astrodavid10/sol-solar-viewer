// =====================================================================
// Coronal mass ejections — the cone model, drawn
// =====================================================================
// A CME is the one thing in this app that is genuinely an EVENT: the field
// lines breathe, the wind streams, the surface rotates, but a CME happens once
// and leaves. So it is also the only layer that is invisible most of the time
// and has to earn its presence in the few hours it is live.
//
// WHY THIS SHAPE IS NOT A STYLIZATION. What is drawn is a cone with a spherical
// cap — the "ice cream cone" — expanding self-similarly along a fixed axis. That
// is not an artist's impression of a CME: it is the CONE MODEL (Zhao 2002, Xie
// 2004), the model operational forecasters FIT to coronagraph pairs, and
// `half_angle_deg` + `dir_ecl` + `speed_kms` in `events/events.json` are
// literally that fit's parameters as CCMC's analysts published them. Drawing
// anything else would be inventing structure the catalog does not contain;
// drawing this is showing the guest the same object SWPC's own forecast is built
// on. HANDOFF §6 ruled real per-event MHD out on size alone (~89 MB for one
// usable CME state against 1.55 MB for the whole PFSS product) — this is the
// alternative it recommended, and it costs about 50 KB of runtime-built
// buffers, shared by every event, and two draw calls per eruption.
//
// The cone is drawn as a CLOUD OF PARTICLES plus one smooth shock shell, not as
// a shaded envelope — see the long note above buildCloudGeometry for why the
// envelope was thrown away after four rounds of tuning.
//
// WHAT IS DELIBERATELY NOT DRAWN. The front only appears at 2.2 R_sun, LASCO
// C2's inner edge, because that is where a height-time fit can begin — below it
// nobody measured anything. Particles still trail back toward the surface (a CME
// is rooted, and that much is certain) and the flare flash marks where it
// started, but the front's growth through the low corona is not animated because
// it was not observed. Same principle as the far-side fade in offLimb.ts.
//
// Geometry lives in R_sun units and the group carries the R_sun→AU scale, the
// same convention as fieldLines.ts and solarWind.ts (footgun 2's rSunAu).
//
// THE CONE GROUP MUST NOT CARRY THE CARRINGTON QUATERNION (footgun 25). A CME
// propagates along a fixed INERTIAL direction and `dir_ecl` is already in
// ecliptic J2000, the scene's frame; Carrington rotation is 14.18 deg/day, so a
// Carrington-parented cone would swing 42.5 deg across the 72 h window — right
// on one frame and wildly wrong at the other end of the scrubber. The surface
// flash is the opposite case: it is anchored to a sunspot region, so it lives in
// a child group that DOES mirror the quaternion, exactly as solarWind.ts does.
//
// No WWT imports (footgun 12).

import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Group,
  Mesh,
  Points,
  Quaternion,
  ShaderMaterial,
  Sphere,
  Vector3,
} from "three";

import type { SolarEvent } from "../data/events";
import { FLAT_SIDE } from "./winding";

export interface CmeLayerOptions {
  /** Sun radius in AU as WWT draws it — the group scale (footgun 2). */
  rSunAu: number;
}

export interface CmeLayer {
  /** Add to the stage's scene. Carries the R_sun→AU scale. */
  object3d: Group;
  /** The events in the current window. Rebuilds the meshes; call rarely. */
  setEvents: (events: SolarEvent[]) => void;
  /**
   * The SAME slerped Carrington→ecliptic quaternion the field lines use. Applied
   * ONLY to the surface flash — never to the cones (footgun 25, and the module
   * header).
   */
  setQuaternion: (q: Quaternion) => void;
  /** Redraw for the moment under the playhead. Cheap: uniforms only. */
  update: (sceneUnix: number) => void;
  /**
   * Half the drawing-buffer height, in device pixels — the cloud's particles
   * are sized the way solarWind.ts sizes its own (`size * scale / |z|`), so they
   * need the same number.
   */
  setPixelScale: (value: number) => void;
  setVisible: (value: boolean) => void;
  /** How many eruptions are currently drawing anything — for `?debug=1`. */
  liveCount: () => number;
  dispose: () => void;
}

// ---------------------------------------------------------------------
// The transit: radius as a function of scene time
// ---------------------------------------------------------------------

/**
 * LASCO C2's inner edge, and so the radius DONKI's `startTime` refers to: the
 * first appearance a height-time fit can be anchored on. Not the surface.
 */
const R_ONSET = 2.2;

/** DONKI's reference height — `time21_5_unix` is the crossing of this. */
const R_215 = 21.5;

/** Stop drawing here. Past this a CME is interplanetary, not coronal. */
const R_MAX = 55;

/** km per R_sun, for turning a speed into a transit time. */
const KM_PER_R_SUN = 695700;

/** Used only when DONKI published neither a 21.5 R_sun time nor a speed. */
const FALLBACK_SPEED_KMS = 600;

export interface CmeTransit {
  /** Scene time the front reaches R_ONSET. */
  startUnix: number;
  /** Scene time it reaches R_MAX, i.e. when the layer goes quiet again. */
  endUnix: number;
  /** Seconds per R_sun of climb — constant, see below. */
  secondsPerRSun: number;
}

/**
 * When this CME is on screen, and how fast it climbs.
 *
 * CONSTANT speed, from DONKI's own two timestamps: `start_unix` at R_ONSET and
 * `time21_5_unix` at 21.5 R_sun. Using the published pair rather than the
 * published `speed_kms` is deliberate — measured against the four CMEs in the
 * live 2026-08-23 window, the speed implied by the timestamps runs 6-19% above
 * the reported speed, because the reported one is a plane-of-sky linear fit and
 * the timestamps bracket a real accelerating climb. Neither is "wrong"; the
 * timestamps are the pair that make the animation land where the catalog says
 * the CME was, which is what a scrubber demands. `speed_kms` is still what the
 * card quotes to the guest, because that is the number DONKI headlines.
 *
 * Returns null for a CME with no direction — it can be marked on the timeline
 * but not drawn (see events.ts's note on a missing `dir_ecl`).
 */
export function cmeTransit(event: SolarEvent): CmeTransit | null {
  if (!event.dirEcl) { return null; }
  const start = event.unix;
  const t215 = event.time215Unix;
  let perRSun: number;
  if (t215 && t215 > start) {
    perRSun = (t215 - start) / (R_215 - R_ONSET);
  } else {
    const speed = event.speedKms && event.speedKms > 0 ? event.speedKms : FALLBACK_SPEED_KMS;
    perRSun = KM_PER_R_SUN / speed;
  }
  return {
    startUnix: start,
    endUnix: start + perRSun * (R_MAX - R_ONSET),
    secondsPerRSun: perRSun,
  };
}

/**
 * Leading-edge height at `unix`, in R_sun — or 0 when this CME is not on screen
 * at that moment. Extrapolated past 21.5 R_sun at the same rate, which is the
 * standard assumption once a CME is out of the acceleration region.
 */
export function cmeRadius(event: SolarEvent, unix: number): number {
  const transit = cmeTransit(event);
  if (!transit) { return 0; }
  if (unix < transit.startUnix || unix > transit.endUnix) { return 0; }
  return R_ONSET + (unix - transit.startUnix) / transit.secondsPerRSun;
}

/**
 * Where a replay stops, in R_sun. NOT the 21.5 the catalog times, and not the
 * 55 the layer will draw to if a guest keeps scrubbing.
 *
 * A cloud and the Sun that threw it cannot both be prominent in one frame: at a
 * 45 deg half angle — the widest in the live catalog — the front spans about
 * 18 R_sun across by the time it reaches 26, so framing all of it shrinks the
 * Sun to a dot and the eruption loses the thing it erupted FROM. Measured at the
 * screen, 13 is where both still read. It also keeps the replay to the chapter
 * worth watching: for the 1329 km/s event that is the first 1.6 hours, the
 * flash and the lift-off, rather than 4 hours of a fading smudge coasting
 * off-frame. The cloud carries on past it for anyone who scrubs.
 */
const REPLAY_TO_R_SUN = 13;

/** Lead-in before the front appears, so the flare that drove it is on screen. */
const REPLAY_LEAD_S = 30 * 60;

export interface CmeReplayWindow {
  fromUnix: number;
  toUnix: number;
  /** How many solar radii the camera should frame to watch this. */
  framedRadiusRSun: number;
}

/**
 * The scene-time window a replay should cover, and how wide to frame it.
 *
 * Lives here rather than in the component because it is the same arithmetic as
 * the drawing: one place knows what R_ONSET and 21.5 R_sun mean.
 *
 * `framedRadiusRSun` frames a little less than the full height the replay
 * reaches, so the front is crossing the edge of frame as it ends rather than
 * shrinking into the middle of it.
 */
export function cmeReplayWindow(event: SolarEvent): CmeReplayWindow | null {
  const transit = cmeTransit(event);
  if (!transit) { return null; }
  return {
    fromUnix: transit.startUnix - REPLAY_LEAD_S,
    toUnix: transit.startUnix + transit.secondsPerRSun * (REPLAY_TO_R_SUN - R_ONSET),
    framedRadiusRSun: REPLAY_TO_R_SUN * 0.85,
  };
}

/**
 * How much of its peak brightness an eruption has left at height r, 0-1.
 *
 * A NORMALIZED curve, deliberately: the cloud and the shock scale it by very
 * different amounts (see CLOUD_ALPHA and SHOCK_ALPHA) because one is three
 * thousand overlapping particles and the other is a single surface. They shared
 * a multiplier once, and calibrating the cloud down to 0.028 took the shock down
 * with it until it was invisible.
 *
 * A coronagraph CME dims fast: the Thomson-scattered signal follows the
 * electron density, which drops as the cloud expands into a volume growing like
 * r^3 while its mass stays put. This is not that integral — it is a curve with
 * the same shape, normalized so the onset reads at full strength, chosen so a
 * CME is unmistakable at 3 R_sun and a faint ghost at 40.
 */
function brightnessAt(r: number): number {
  const dim = 1 / (1 + Math.pow(r / 9, 1.4));
  // Fade in over the first fifth of a solar radius of climb, so a CME arrives
  // rather than blinking on, and out over the last quarter of the drawn range.
  const arrive = Math.min(1, (r - R_ONSET) / 0.2);
  const leave = Math.min(1, (R_MAX - r) / (R_MAX * 0.25));
  return Math.max(0, dim * arrive * leave);
}

/**
 * Alpha of ONE cloud particle at the eruption's brightest, before the fragment's
 * own falloff — so a few thousand of them stack to something visible.
 *
 * MEASURED, not chosen, and swept twice. First from 1.0 down — 1.0, 0.14 and
 * 0.06 all gave a solid white mass, 0.028 was where it became gas — and then
 * again after CLOUD_POINT_FRAC's unit fix took every particle off the 64 px
 * ceiling: a fifth of the fill area needs the alpha back up, and 0.17 is where
 * the cloud reads as billowing plasma with a bright leading edge rather than
 * either a grey smudge (0.03) or cotton wool (0.22). Additive blending has no
 * highlight rolloff, so the whole difference between "plasma" and "poster paint"
 * lives in this one number — re-sweep it if the point size or count changes.
 */
const CLOUD_ALPHA = 0.17;

// ---------------------------------------------------------------------
// The cloud: particles, not a surface
// ---------------------------------------------------------------------
// This started as a shaded cone-and-cap SURFACE and went through four rounds of
// tuning at the screen before being thrown away, so the reasoning is worth
// keeping: a 45 deg half-angle envelope at 7-13 R_sun is an enormous smooth
// sheet, and a smooth sheet lit by any shading model reads as GLASS OR METAL,
// never as gas. Limb brightening got it as far as a bright crescent with a hard
// dark wedge behind it — better, and still obviously a solid object.
//
// Plasma reads as plasma when it is made of many faint overlapping things. So
// the cloud is a few thousand additive points distributed through the shell,
// which is also the cheaper option (3,000 vertices against ~2,000 triangles),
// has no silhouette to give the game away, and reuses the point-sprite pattern
// solarWind.ts already proved on this stage — including its hard-won `abs(mv.z)`
// (footgun 20).
//
// The points are placed in the SAME normalized (u, v, s) coordinates the
// envelope used, so the half angle stays a uniform and the whole cloud still
// expands self-similarly by changing one float. Nothing is uploaded per frame.
//
// A deliberate leftover: the SHOCK is still a smooth surface (below). At its low
// alpha a broad smooth shell is exactly right — it reads as a pressure front,
// the one part of an eruption that really is a thin continuous surface.

/** How many points make the cloud. 3,000 is where it stops looking sparse. */
const CLOUD_POINTS = 3000;

/** Fraction of them in the leading shell rather than the trailing legs. */
const SHELL_FRACTION = 0.72;

/**
 * Point diameter as a fraction of the cloud's own height, so the grain grows
 * with the cloud and the fog stays a fog instead of thinning to a sprinkle.
 * Same convention as solarWind's POINT_SIZE_R_SUN: our shader uses three's
 * `size * scale / |z|`, which omits the 1/tan(fov/2) factor, so this is 2.414x
 * the true world size at WWT's fixed vertical FOV (footgun 11).
 *
 * It is multiplied by `rSunAu` where the uniform is set, and that conversion is
 * NOT optional: `uRadius` is in R_sun but `mv.z` is in AU, and without it the
 * shader computed a want of 986 px against a 64 px ceiling — every one of the
 * three thousand particles pinned to maximum size at every zoom. Exactly
 * footgun 20's symptom from a different cause, with the same two consequences:
 * 12.3M fragments a frame of pure overdraw (measured 3000 x 64^2, a real risk
 * on a phone), and a cloud that never got finer as the guest pulled back.
 *
 * 0.235 is then what keeps the fog looking like fog once the units are right —
 * about 28 px per particle at the replay framing on a desktop, 11 px on a phone,
 * which is still a 9x overlap and a fifth of the fill cost.
 */
const CLOUD_POINT_FRAC = 0.235;

/** Pixel ceiling. Generous: near the Sun a fog particle SHOULD be big. */
const CLOUD_POINT_MAX = 64;

/**
 * A tiny LCG rather than Math.random, so every guest and every screenshot gets
 * the same cloud. The shape of a specific eruption should not change between
 * two looks at it.
 */
function lcg(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

/**
 * The cloud's points, in normalized coordinates.
 *
 * (u, v, s) rides in the `position` attribute — u = fraction of the half angle,
 * v = azimuth, s = fraction of the leading-edge height — which is a deliberate
 * abuse of the name: three sizes the draw from `position.count`, so putting the
 * real data there costs nothing, where a dummy `position` of zeros alongside
 * three custom attributes would waste 36 KB per cloud. Nothing reads it as a
 * position: `boundingSphere` is set by hand and the vertex shader unpacks it.
 */
function buildCloudGeometry(): BufferGeometry {
  const xyz = new Float32Array(CLOUD_POINTS * 3);
  const seeds = new Float32Array(CLOUD_POINTS);
  const random = lcg(20260824);
  for (let i = 0; i < CLOUD_POINTS; i++) {
    const shell = i < CLOUD_POINTS * SHELL_FRACTION;
    // Angle from the axis: a mild bias toward the axis, which is where a real
    // flux rope's mass sits. (Exact equal-area sampling would need the half
    // angle, and that is a uniform — it is not known here.)
    const u = shell ? Math.pow(random(), 0.6) : 0.78 + 0.22 * random();
    const v = random() * Math.PI * 2;
    // The shell is a thick front; the legs trail back down toward the Sun.
    const s = shell ? 1 - 0.18 * Math.pow(random(), 1.8) : 0.12 + 0.75 * random();
    xyz[i * 3] = u;
    xyz[i * 3 + 1] = v;
    xyz[i * 3 + 2] = s;
    seeds[i] = 0.45 + 0.55 * random();
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(xyz, 3));
  geometry.setAttribute("aSeed", new BufferAttribute(seeds, 1));
  geometry.boundingSphere = new Sphere(new Vector3(0, 0, 0), R_MAX);
  return geometry;
}

const CLOUD_VERTEX = `
attribute float aSeed;

uniform float uHalfAngle;
uniform float uRadius;
uniform float uSize;
uniform float uSizeMax;
uniform float uPixelScale;

varying float vAlpha;

void main() {
  // position is (u, v, s), not a position — see buildCloudGeometry.
  float a = position.x * uHalfAngle;
  float sa = sin(a);
  vec3 dir = vec3(sa * cos(position.y), sa * sin(position.y), cos(a));
  vec4 mv = modelViewMatrix * vec4(dir * (uRadius * position.z), 1.0);
  gl_Position = projectionMatrix * mv;

  // abs(), NOT -mv.z: WWT's view matrix is left-handed, so view-space z is
  // POSITIVE in front of the camera (footgun 20). solarWind.ts has the long
  // version of this comment and the bug it caused.
  float want = uSize * uRadius * uPixelScale / max(abs(mv.z), 1e-9);
  gl_PointSize = clamp(want, 1.0, uSizeMax);

  // Denser and brighter toward the leading edge and toward the axis: the front
  // is where the swept-up material piles up.
  float front = smoothstep(0.55, 1.0, position.z);
  float axis = 1.0 - 0.55 * position.x;
  vAlpha = aSeed * axis * (0.25 + 0.75 * front);
}
`;

const CLOUD_FRAGMENT = `
uniform vec3 uColor;
uniform float uOpacity;

varying float vAlpha;

void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r2 = dot(d, d);
  if (r2 > 0.25) { discard; }
  // A soft edge is the whole point: a hard-edged dot at 30+ px reads as a
  // bubble, and a few thousand bubbles read as bubble wrap.
  float soft = pow(1.0 - smoothstep(0.0, 0.25, r2), 1.6);
  float a = vAlpha * soft * uOpacity;
  if (a <= 0.002) { discard; }
  gl_FragColor = vec4(uColor, a);
}
`;

// ---------------------------------------------------------------------
// The shock: a smooth envelope, and the one surface left
// ---------------------------------------------------------------------
// A fast CME drives a shock ahead of itself — wider than the cloud, and a thin
// continuous pressure front rather than a body of plasma. That makes it the one
// part of an eruption a smooth SURFACE describes honestly, so it stayed one when
// the cloud became particles.
//
// Positions are computed in the VERTEX SHADER from two normalized coordinates,
// which is what lets one geometry serve every event: the half angle (12-45 deg
// in the live catalog) and the height are uniforms, so it never rebuilds a
// buffer — it changes two floats.
//
//   aU  0 on the axis → 1 at the shell's edge
//   aV  azimuth, radians
//
// The tessellation is what it is because the SILHOUETTE is the whole effect: at
// the widest half angle in the catalog, 40 azimuth steps left visible flat
// facets around the edge of a front 26 R_sun across.

const AZIMUTH_STEPS = 64;
const CAP_RINGS = 14;

function buildShockGeometry(): BufferGeometry {
  const u: number[] = [];
  const v: number[] = [];
  const index: number[] = [];
  const stride = AZIMUTH_STEPS + 1;

  for (let ring = 0; ring <= CAP_RINGS; ring++) {
    const uu = ring / CAP_RINGS;
    for (let step = 0; step <= AZIMUTH_STEPS; step++) {
      u.push(uu);
      v.push((step / AZIMUTH_STEPS) * Math.PI * 2);
    }
  }
  for (let ring = 0; ring < CAP_RINGS; ring++) {
    for (let step = 0; step < AZIMUTH_STEPS; step++) {
      const a = ring * stride + step;
      const b = a + 1;
      const c = a + stride;
      const d = c + 1;
      index.push(a, c, b, b, c, d);
    }
  }

  const geometry = new BufferGeometry();
  geometry.setAttribute("aU", new BufferAttribute(new Float32Array(u), 1));
  geometry.setAttribute("aV", new BufferAttribute(new Float32Array(v), 1));
  geometry.setIndex(index);
  // three needs SOMETHING to frustum-cull against, and there are no positions
  // to compute it from — every vertex is placed in the shader. R_MAX is the
  // furthest any front reaches, so a sphere that size is always conservative.
  geometry.boundingSphere = new Sphere(new Vector3(0, 0, 0), R_MAX);
  return geometry;
}

const SHOCK_VERTEX = `
attribute float aU;
attribute float aV;

uniform float uHalfAngle;
uniform float uRadius;

varying float vU;
varying float vEdge;

void main() {
  float a = aU * uHalfAngle;
  float sa = sin(a);
  // Centred on the Sun, so the front expands self-similarly: the cone model.
  vec3 dir = vec3(sa * cos(aV), sa * sin(aV), cos(a));
  vec4 mv = modelViewMatrix * vec4(dir * uRadius, 1.0);

  // LIMB BRIGHTENING. A thin shell is bright where the line of sight skims
  // ALONG it and nearly invisible face-on, which is why a shock front reads as
  // a rim rather than a dome. The normal of a sphere about the Sun IS the radial
  // direction, so there is nothing to look up.
  //
  // The camera sits at the ORIGIN of view space whichever way it faces, so the
  // direction to it is -mv.xyz in ANY convention — the one piece of view-space
  // maths footgun 20's sign flip cannot break (that footgun is about code that
  // assumes the camera looks down -z and negates a DEPTH). The abs() covers the
  // normal, whose sign does depend on the reversed winding.
  vec3 toEye = normalize(-mv.xyz);
  vEdge = 1.0 - abs(dot(normalize(normalMatrix * dir), toEye));

  vU = aU;
  gl_Position = projectionMatrix * mv;
}
`;

const SHOCK_FRAGMENT = `
uniform vec3 uColor;
uniform float uOpacity;

varying float vU;
varying float vEdge;

void main() {
  // 5.5, measured at the screen. At the 2.6 this started on, a front this wide
  // (up to 78 deg) is seen near-edge-on across its whole extent, so the term was
  // large everywhere and the shell filled in as a solid dome. A sharp exponent
  // keeps only the rim, which is all a shock should ever be.
  float limb = pow(clamp(vEdge, 0.0, 1.0), 5.5);
  // Feathered to nothing at the aperture: a hard circular edge is the single
  // thing that would give away that this is a piece of geometry.
  float a = limb * smoothstep(0.0, 0.9, 1.0 - vU) * uOpacity;
  if (a <= 0.002) { discard; }
  gl_FragColor = vec4(uColor, a);
}
`;

/**
 * White, not red or orange, for two independent reasons. Physically, a
 * coronagraph sees a CME by Thomson scattering of ordinary photospheric light,
 * so white IS its colour. And by the palette's own guard-rail (HANDOFF §8): the
 * inbound-field orange sits at hue 20 deg and the X-flare marker at 6 deg, which
 * converge under deuteranopia — a third warm hue on top of the gold Sun and the
 * blue field lines would be indefensible. Brightness carries the drama instead.
 */
const CLOUD_COLOR = new Vector3(1, 0.955, 0.9);

/**
 * The shock ahead of the cloud: wider, fainter, cooler. Real — a fast CME drives
 * one, which is why the catalog's fast events are the ones with SEPs attached —
 * and it is what gives the eruption a leading edge to sweep past the frame.
 */
const SHOCK_COLOR = new Vector3(0.72, 0.82, 1);
const SHOCK_LEAD = 1.12;
const SHOCK_WIDEN = 1.8;
const SHOCK_MAX_HALF_ANGLE = (78 * Math.PI) / 180;

/**
 * The shock is ONE surface, so its alpha is a normal alpha — nothing like
 * CLOUD_ALPHA's per-particle sliver. It is a rim seen through a sharp limb term,
 * so most of the shell renders far below this.
 */
const SHOCK_ALPHA = 0.5;

// ---------------------------------------------------------------------
// The flare flash
// ---------------------------------------------------------------------
// A billboard built in the VERTEX shader rather than a Sprite or a Points
// sprite: Sprites need their `side` flipped under WWT's reversed winding
// (footgun 19) and gl_PointSize is capped by the driver — some mobile GL
// implementations stop at 63 px, which is smaller than this flash wants to be.
// Offsetting the corners in view space has neither problem.

const FLASH_VERTEX = `
uniform vec3 uCenter;
uniform float uSize;

varying vec2 vCorner;

void main() {
  vec4 mv = modelViewMatrix * vec4(uCenter, 1.0);
  // position.xy is the unit corner, -1..1 (see buildFlashGeometry).
  // uSize is in AU, not R_sun: modelViewMatrix has already applied the group's
  // R_sun→AU scale to uCenter, so the offset has to be in the scaled space.
  mv.xy += position.xy * uSize;
  vCorner = position.xy;
  gl_Position = projectionMatrix * mv;
}
`;

const FLASH_FRAGMENT = `
uniform vec3 uColor;
uniform float uOpacity;

varying vec2 vCorner;

void main() {
  // A WIDE hot kernel, not a point. This was pow(1 - d*2.1, 6) with a faint
  // halo, which put the saturating part of the flash in the middle ~4 pixels —
  // and an additive warm glow that does not SATURATE is invisible on the
  // photosphere: HANDOFF §8 measured white on the bare disk at 1.10:1, the
  // lowest contrast in the whole app. A flare has to clip to white to read at
  // all, so the kernel now covers most of the quad and peaks at 1.75, well past
  // the point where gold plus this lands outside the display's gamut.
  float d = length(vCorner);
  float glow = pow(max(0.0, 1.0 - d), 2.0);
  float core = pow(max(0.0, 1.0 - d * 1.25), 4.0);
  float a = (glow * 0.35 + core * 1.4) * uOpacity;
  if (a <= 0.002) { discard; }
  gl_FragColor = vec4(uColor, a);
}
`;

const FLASH_COLOR = new Vector3(1, 0.88, 0.66);

/** Just off the surface, so the sphere occludes it from the far side. */
const FLASH_R_SUN = 1.015;

/**
 * Half-width of the flash quad at C1.0, R_sun. Scales with the class.
 *
 * Not to scale, and it cannot be: a flare's bright ribbons are a few tens of
 * megametres, well under a twentieth of a solar radius, which at the resting
 * framing is a handful of pixels hidden under a field line. This is the size at
 * which a guest can see WHERE it happened — the same compromise the region
 * markers already make.
 */
const FLASH_SIZE_R_SUN = 0.22;

/**
 * How long a flare's flash lingers after its peak when DONKI gave no end time,
 * seconds. Real flares decay over tens of minutes; 25 is a middle C/M value.
 */
const FLASH_DECAY_S = 25 * 60;

/**
 * A unit quad whose corners ride in `position`, NOT in a custom attribute.
 *
 * This was `aCorner` and the mesh silently never drew — three did not render it
 * at all (the material was never even compiled), because a Mesh whose geometry
 * has no `position` attribute is not something the renderer will draw, however
 * complete the custom attributes and the index are. It costs one float per
 * vertex to be conventional about it, and the failure mode it avoids is the
 * worst kind: no error, no warning, nothing on screen.
 */
function buildFlashGeometry(): BufferGeometry {
  const corners = new Float32Array([
    -1, -1, 0,
    1, -1, 0,
    1, 1, 0,
    -1, 1, 0,
  ]);
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(corners, 3));
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  geometry.boundingSphere = new Sphere(new Vector3(0, 0, 0), FLASH_R_SUN * 2);
  return geometry;
}

/**
 * GOES class → a linear-ish size multiplier. A single letter is a factor of ten
 * in energy, which is far too much to give to a radius, so this is deliberately
 * compressed: X is about twice C, not a thousand times.
 */
function flashScale(cls: string): number {
  const letter = cls.charAt(0).toUpperCase();
  const digits = parseFloat(cls.slice(1));
  const step = Number.isFinite(digits) ? Math.min(Math.max(digits, 1), 9.9) : 1;
  const base = letter === "X" ? 2 : letter === "M" ? 1.5 : letter === "C" ? 1.1 : 0.8;
  return base * (0.82 + 0.18 * Math.log10(step * 1.2 + 1) / Math.log10(12.9));
}

/** 0-1 brightness of a flare's flash at `unix`. */
function flashGlowAt(event: SolarEvent, unix: number): number {
  const peak = event.unix;
  const begin = event.beginUnix ?? peak - 10 * 60;
  const end = event.endUnix ?? peak + FLASH_DECAY_S;
  if (unix < begin || unix > end) { return 0; }
  if (unix <= peak) {
    const rise = peak > begin ? (unix - begin) / (peak - begin) : 1;
    // Ease in: flares brighten fast near the peak, not linearly.
    return Math.pow(Math.max(0, rise), 2.2);
  }
  const fall = end > peak ? 1 - (unix - peak) / (end - peak) : 0;
  return Math.max(0, fall);
}

/**
 * Carrington lat/lon in degrees → a unit vector in the frame the field lines
 * are traced in. Matches the pipeline's own convention: +Z is the solar
 * rotation axis and longitude opens right-handed about it, which is what makes
 * a flare land under the sunspot group the surface texture shows.
 */
function carringtonUnit(latDeg: number, lonDeg: number, out: Vector3): Vector3 {
  const lat = (latDeg * Math.PI) / 180;
  const lon = (lonDeg * Math.PI) / 180;
  const c = Math.cos(lat);
  return out.set(c * Math.cos(lon), c * Math.sin(lon), Math.sin(lat));
}

// ---------------------------------------------------------------------

interface ConeMesh {
  event: SolarEvent;
  cloud: Points;
  shock: Mesh;
}

interface FlashMesh {
  event: SolarEvent;
  mesh: Mesh;
}

const AXIS_Z = new Vector3(0, 0, 1);

export function createCmeLayer(options: CmeLayerOptions): CmeLayer {
  const group = new Group();
  group.name = "cme";
  group.scale.setScalar(options.rSunAu);

  // Two children, and the split is the whole of footgun 25: cones are inertial,
  // the flash is bolted to a rotating surface.
  const inertial = new Group();
  inertial.name = "cme-inertial";
  const carrington = new Group();
  carrington.name = "cme-carrington";
  group.add(inertial, carrington);

  const cloudGeometry = buildCloudGeometry();
  const shockGeometry = buildShockGeometry();
  const flashGeometry = buildFlashGeometry();
  const cones: ConeMesh[] = [];
  const flashes: FlashMesh[] = [];
  const axis = new Vector3();
  let pixelScale = 450;
  let live = 0;

  // Both layers share this: additive, no depth WRITE, but depth TEST on. The Sun
  // is the authoritative occluder and clears the depth buffer every pass
  // (footgun 18), so testing against it is what correctly hides the half of a
  // backside eruption that is behind the disk — while not writing depth is what
  // lets three thousand overlapping particles all contribute instead of the
  // nearest one winning. `side` from winding.ts because WWT's camera reverses
  // triangle winding (footgun 19) — DoubleSide for a shell we look through.
  function additive(uniforms: Record<string, { value: unknown }>,
    vertexShader: string, fragmentShader: string): ShaderMaterial {
    return new ShaderMaterial({
      uniforms,
      vertexShader,
      fragmentShader,
      transparent: true,
      blending: AdditiveBlending,
      depthTest: true,
      depthWrite: false,
      side: FLAT_SIDE,
    });
  }

  function makeCloud(): Points {
    const points = new Points(cloudGeometry, additive({
      uHalfAngle: { value: 0.4 },
      uRadius: { value: 0 },
      uColor: { value: CLOUD_COLOR.clone() },
      uOpacity: { value: 0 },
      // R_sun → AU here, because the shader divides by a view-space z in AU.
      // See CLOUD_POINT_FRAC for what happened when this was missing.
      uSize: { value: CLOUD_POINT_FRAC * options.rSunAu },
      uSizeMax: { value: CLOUD_POINT_MAX },
      uPixelScale: { value: pixelScale },
    }, CLOUD_VERTEX, CLOUD_FRAGMENT));
    points.visible = false;
    return points;
  }

  function makeShock(): Mesh {
    const mesh = new Mesh(shockGeometry, additive({
      uHalfAngle: { value: 0.7 },
      uRadius: { value: 0 },
      uColor: { value: SHOCK_COLOR.clone() },
      uOpacity: { value: 0 },
    }, SHOCK_VERTEX, SHOCK_FRAGMENT));
    mesh.visible = false;
    return mesh;
  }

  function clear(): void {
    cones.forEach((cone) => {
      inertial.remove(cone.cloud, cone.shock);
      (cone.cloud.material as ShaderMaterial).dispose();
      (cone.shock.material as ShaderMaterial).dispose();
    });
    cones.length = 0;
    flashes.forEach((flash) => {
      carrington.remove(flash.mesh);
      (flash.mesh.material as ShaderMaterial).dispose();
    });
    flashes.length = 0;
    live = 0;
  }

  return {
    object3d: group,

    setEvents(events: SolarEvent[]): void {
      clear();
      events.forEach((event) => {
        if (event.kind === "cme") {
          const dir = event.dirEcl;
          if (!dir || !cmeTransit(event)) { return; }  // no direction: not drawable
          const cloud = makeCloud();
          const shock = makeShock();
          // dir_ecl is ALREADY in the scene's frame. This is the only rotation the
          // eruption ever gets, it is set once, and it must never be composed
          // with the Carrington quaternion (footgun 25).
          axis.set(dir[0], dir[1], dir[2]).normalize();
          const q = new Quaternion().setFromUnitVectors(AXIS_Z, axis);
          cloud.quaternion.copy(q);
          shock.quaternion.copy(q);
          inertial.add(cloud, shock);
          cones.push({ event, cloud, shock });
          return;
        }
        // A flare only gets a flash if DONKI said WHERE it happened. Most do;
        // a backside event does not, and inventing a spot for it would put a
        // bright patch on a region that never flared.
        if (event.sourceCarrLonDeg === undefined || event.sourceLatDeg === undefined) {
          return;
        }
        const material = new ShaderMaterial({
          uniforms: {
            uCenter: {
              value: carringtonUnit(event.sourceLatDeg, event.sourceCarrLonDeg, new Vector3())
                .multiplyScalar(FLASH_R_SUN),
            },
            uSize: {
              value: FLASH_SIZE_R_SUN * flashScale(event.cls ?? "") * options.rSunAu,
            },
            uColor: { value: FLASH_COLOR.clone() },
            uOpacity: { value: 0 },
          },
          vertexShader: FLASH_VERTEX,
          fragmentShader: FLASH_FRAGMENT,
          transparent: true,
          blending: AdditiveBlending,
          depthTest: true,
          depthWrite: false,
          side: FLAT_SIDE,
        });
        const mesh = new Mesh(flashGeometry, material);
        mesh.visible = false;
        // The quad is placed in view space, so its object-space bounds say
        // nothing about where it lands on screen: culling it would drop it at
        // the worst moment.
        mesh.frustumCulled = false;
        carrington.add(mesh);
        flashes.push({ event, mesh });
      });
    },

    setQuaternion(q: Quaternion): void {
      carrington.quaternion.copy(q);
    },

    update(sceneUnix: number): void {
      live = 0;
      cones.forEach(({ event, cloud, shock }) => {
        const r = cmeRadius(event, sceneUnix);
        const dim = r > 0 ? brightnessAt(r) : 0;
        const on = dim > 0.01;
        cloud.visible = on;
        shock.visible = on;
        if (!on) { return; }
        live += 1;
        const half = ((event.halfAngleDeg ?? 25) * Math.PI) / 180;
        const cloudUniforms = (cloud.material as ShaderMaterial).uniforms;
        cloudUniforms.uHalfAngle.value = half;
        cloudUniforms.uRadius.value = r;
        cloudUniforms.uOpacity.value = dim * CLOUD_ALPHA;
        cloudUniforms.uPixelScale.value = pixelScale;
        const shockUniforms = (shock.material as ShaderMaterial).uniforms;
        shockUniforms.uHalfAngle.value = Math.min(half * SHOCK_WIDEN, SHOCK_MAX_HALF_ANGLE);
        shockUniforms.uRadius.value = r * SHOCK_LEAD;
        shockUniforms.uOpacity.value = dim * SHOCK_ALPHA;
      });

      flashes.forEach(({ event, mesh }) => {
        const glow = flashGlowAt(event, sceneUnix);
        mesh.visible = glow > 0.004;
        if (!mesh.visible) { return; }
        live += 1;
        (mesh.material as ShaderMaterial).uniforms.uOpacity.value = glow;
      });
    },

    setVisible(value: boolean): void {
      group.visible = value;
    },

    setPixelScale(value: number): void {
      pixelScale = value;
    },

    liveCount(): number {
      return live;
    },

    dispose(): void {
      clear();
      cloudGeometry.dispose();
      shockGeometry.dispose();
      flashGeometry.dispose();
    },
  };
}
