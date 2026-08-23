// =====================================================================
// Solar wind — particles streaming out along the OPEN field lines
// =====================================================================
// The open lines are the story the PFSS model tells that a picture of the Sun
// cannot: these are the field lines that never come back, and the wind runs
// along them. Uniformly seeding particles over the open lines needs no
// weighting to look right — open lines cluster where coronal holes are, so the
// outflow concentrates there by itself.
//
// Why the CPU updates positions: at 1,200-3,000 particles the whole update is
// ~3,000 polyline samples per frame (a binary search over ~28 vertices plus a
// lerp) and one 36 KB buffer upload. A GPU formulation would need the paths in
// a DataTexture and would still have to be rebuilt whenever the frame changes,
// so it would buy nothing but a shader that is much harder to be sure of.
//
// Geometry lives in the SAME Carrington R_sun space as fieldLines.ts, and this
// group mirrors that group's scale and quaternion rather than parenting under
// it — nesting would make the wind vanish whenever the guest switched the
// field lines off.
//
// No WWT imports (CLAUDE.md footgun 12).

import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  DynamicDrawUsage,
  Group,
  Points,
  Quaternion,
  ShaderMaterial,
  Sphere,
  Vector3,
} from "three";

import type { OpenLinePath } from "./fieldLines";

export interface SolarWindOptions {
  /** Sun radius in AU as WWT draws it — the group scale (footgun 2). */
  rSunAu: number;
  /** Particle budget. Defaults to the pointer-based budget below. */
  count?: number;
}

export interface SolarWind {
  /** Add to the stage's scene. Carries the R_sun→AU scale and the orientation. */
  object3d: Group;
  /** Swap in a new integer frame's open lines (see fieldLines.openLinePaths). */
  setFrameData: (paths: OpenLinePath[]) => void;
  /** Live SWPC wind speed, km/s — scales the visual speed only. */
  setSpeedKms: (kms: number) => void;
  /** The SAME slerped Carrington→ecliptic quaternion the field lines use. */
  setQuaternion: (q: Quaternion) => void;
  /** Half the drawing-buffer height, in device pixels (point-size scaling). */
  setPixelScale: (value: number) => void;
  tick: (dtSeconds: number) => void;
  setVisible: (value: boolean) => void;
  dispose: () => void;
}

// ---------------------------------------------------------------------
// Tunables
// ---------------------------------------------------------------------

/** Fine pointer (desktop/tablet with a mouse): the full budget. */
const COUNT_FINE = 3000;

/** Coarse pointer — a phone, where fill rate is the scarce resource. */
const COUNT_COARSE = 1200;

/** Where a particle's run ends and it respawns at a footpoint. */
const OUTER_R_SUN = 6;

/** Solar wind speed → seconds for the whole 1 → 6 R_sun run. Anchors from the
 *  brief: 300 km/s is gentle, 800 km/s is brisk. Linear between, clamped. */
const SPEED_SLOW_KMS = 300;
const SPEED_FAST_KMS = 800;
const RUN_SECONDS_SLOW = 14;
const RUN_SECONDS_FAST = 6;
const RUN_SECONDS_MIN = 4.5;
const RUN_SECONDS_MAX = 20;

/** Speed spread between particles, so they don't move as a rigid comb. */
const JITTER = 0.12;

/** Fade in over the first 5% of the run, out over the last 15%. */
const FADE_IN = 0.05;
const FADE_OUT = 0.15;

/** Nothing draws below this radius: the footpoint is inside the sun surface
 *  sphere (1.001 R_sun) and a particle popping out of it looks like a glitch. */
const SPAWN_R_SUN = 1.02;

/** Full brightness by here — a 6% radial ramp above SPAWN_R_SUN. */
const SPAWN_FADE_R_SUN = 1.08;

/**
 * Point size in R_sun of world space. Our shader follows three's points
 * convention, gl_PointSize = size * scale / |z_view|, which omits the
 * 1/tan(fov/2) factor — so this constant is 2.414x the true world size at
 * WWT's fixed π/4 vertical FOV (footgun 11).
 *
 * Calibrated so the dot sits AT the POINT_SIZE_MAX ceiling at the home framing
 * (d ≈ 6.8 R_sun) on the small end of the range — uPixelScale is half the
 * drawing-buffer height, ≈450 in a desktop window and ≈844 on a phone, and
 * `want = POINT_SIZE_R_SUN * uPixelScale / 6.8`. At 0.09 that is 6.0 px on
 * desktop and 11 px (clamped to 6) on a phone. So near the Sun the wind looks
 * exactly as it did when the z-sign bug pinned every dot to the ceiling, and
 * the size — and with it the alpha falloff — only starts to bite as the guest
 * pulls back past the home framing, which is the one place it was too bright.
 * This is the knob to turn if the dots want to be finer or coarser.
 */
const POINT_SIZE_R_SUN = 0.09;

/** gl_PointSize ceiling, and the reference the thinning is measured against. */
const POINT_SIZE_MAX = 6;

/**
 * Never thin below this fraction of the particle budget, however far the guest
 * pulls back. The wind is one of the few things still moving at that distance,
 * and a Sun with no outflow at all reads as "broken", not as "far away".
 */
const MIN_KEEP = 0.10;

/** Pale blue-white: the open-field blue pulled most of the way to white so the
 *  wind reads as a separate thing from the lines it flows along. */
const COLOR: [number, number, number] = [0.70, 0.83, 1.0];

/** Per-particle peak alpha. Additive, so this is a contribution, not a colour:
 *  what the guest sees where streams overlap is the sum. */
const ALPHA = 0.5;

function defaultCount(): number {
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    try {
      if (window.matchMedia("(pointer: coarse)").matches) { return COUNT_COARSE; }
    } catch {
      // Old WebViews throw on an unsupported media feature; assume desktop.
    }
  }
  return COUNT_FINE;
}

/** Seconds for one 1 → 6 R_sun run at `kms` of real solar wind. */
export function runSecondsFor(kms: number): number {
  if (!Number.isFinite(kms) || kms <= 0) { return RUN_SECONDS_SLOW; }
  const t = (kms - SPEED_SLOW_KMS) / (SPEED_FAST_KMS - SPEED_SLOW_KMS);
  const seconds = RUN_SECONDS_SLOW + t * (RUN_SECONDS_FAST - RUN_SECONDS_SLOW);
  return Math.min(Math.max(seconds, RUN_SECONDS_MIN), RUN_SECONDS_MAX);
}

// ---------------------------------------------------------------------
// Shaders (GLSL ES 1.00, as in fieldLines.ts)
// ---------------------------------------------------------------------

const VERTEX_SHADER = `
attribute float aAlpha;
attribute float aRank;

uniform float uSize;
uniform float uSizeMax;
uniform float uMinKeep;
uniform float uPixelScale;

varying float vAlpha;

void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;

  // abs(), NOT -mv.z. WWT builds its view matrix with Matrix3d.lookAtLH, so
  // view-space +z points AWAY from the camera and mv.z is POSITIVE in front of
  // it — the opposite of the OpenGL convention three's own points shader
  // assumes. With -mv.z the max() always won and want was garbage, so the
  // clamp pinned EVERY particle to the ceiling at EVERY zoom. See
  // src/three/winding.ts for the same handedness biting face culling.
  float want = uSize * uPixelScale / max(abs(mv.z), 1e-9);
  gl_PointSize = clamp(want, 1.0, uSizeMax);

  // Pull back and the whole 1-6 R_sun stream compresses into fewer pixels, so
  // additively blended dots stack into a white blob. THIN THE POPULATION
  // rather than dimming it: every surviving particle keeps its full alpha, so
  // the wind stays made of visible dots instead of turning into a grey haze.
  //
  // aRank is a fixed random value per particle, so the same particles drop out
  // at the same zoom every time — no flicker, and no frame-to-frame popping as
  // the guest pinches. Keeping a fraction (want/uSizeMax)^2 holds the number of
  // dots per SCREEN PIXEL roughly constant, because the stream's screen area
  // falls off as the square of the same quantity that drives point size.
  float keep = max((want / uSizeMax) * (want / uSizeMax), uMinKeep);
  if (aRank > keep) {
    // Behind the near plane in clip space: clipped before rasterization, so a
    // culled particle costs nothing but this vertex.
    gl_Position = vec4(0.0, 0.0, 2.0, 1.0);
    vAlpha = 0.0;
    return;
  }
  vAlpha = aAlpha;
}
`;

const FRAGMENT_SHADER = `
uniform vec3 uColor;

varying float vAlpha;

void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r2 = dot(d, d);
  if (r2 > 0.25 || vAlpha < 0.004) { discard; }
  // Soft round dot: a hard square is unmistakable at these sizes.
  float soft = 1.0 - smoothstep(0.02, 0.25, r2);
  gl_FragColor = vec4(uColor, vAlpha * soft);
}
`;

// ---------------------------------------------------------------------
// Per-line run geometry
// ---------------------------------------------------------------------

interface WindPath {
  /** Line index in topology space — the identity that survives a frame swap. */
  line: number;
  xyz: Float32Array;
  count: number;
  /** Cumulative arc length, `count` entries, cum[0] = 0. */
  cum: Float32Array;
  /** Arc length of the traced polyline. */
  traced: number;
  /** traced + the radial extension out to OUTER_R_SUN. */
  total: number;
  /** Last vertex and the unit direction of the last segment (radial at r_ss). */
  exitX: number;
  exitY: number;
  exitZ: number;
  dirX: number;
  dirY: number;
  dirZ: number;
}

function buildPath(path: OpenLinePath, line: number): WindPath | null {
  const xyz = path.xyz;
  const count = Math.floor(xyz.length / 3);
  if (count < 2) { return null; }

  const cum = new Float32Array(count);
  for (let v = 1; v < count; v++) {
    const a = (v - 1) * 3;
    const b = v * 3;
    const dx = xyz[b] - xyz[a];
    const dy = xyz[b + 1] - xyz[a + 1];
    const dz = xyz[b + 2] - xyz[a + 2];
    cum[v] = cum[v - 1] + Math.sqrt(dx * dx + dy * dy + dz * dz);
  }
  const traced = cum[count - 1];
  if (!(traced > 0)) { return null; }

  const tail = (count - 1) * 3;
  const prev = (count - 2) * 3;
  let dx = xyz[tail] - xyz[prev];
  let dy = xyz[tail + 1] - xyz[prev + 1];
  let dz = xyz[tail + 2] - xyz[prev + 2];
  const step = Math.sqrt(dx * dx + dy * dy + dz * dz);
  if (step > 0) {
    dx /= step;
    dy /= step;
    dz /= step;
  } else {
    // Degenerate tail: fall back to straight-up radial.
    const r = Math.sqrt(
      xyz[tail] * xyz[tail] + xyz[tail + 1] * xyz[tail + 1] + xyz[tail + 2] * xyz[tail + 2]) || 1;
    dx = xyz[tail] / r;
    dy = xyz[tail + 1] / r;
    dz = xyz[tail + 2] / r;
  }

  const rEnd = Math.sqrt(
    xyz[tail] * xyz[tail] + xyz[tail + 1] * xyz[tail + 1] + xyz[tail + 2] * xyz[tail + 2]);
  // PFSS forces the field radial at the source surface, so the last segment
  // already points outward and this extension is a straight continuation.
  const extend = Math.max(0, OUTER_R_SUN - rEnd);

  return {
    line,
    xyz,
    count,
    cum,
    traced,
    total: traced + extend,
    exitX: xyz[tail],
    exitY: xyz[tail + 1],
    exitZ: xyz[tail + 2],
    dirX: dx,
    dirY: dy,
    dirZ: dz,
  };
}

// ---------------------------------------------------------------------
// Layer
// ---------------------------------------------------------------------

export function createSolarWind(options: SolarWindOptions): SolarWind {
  const count = Math.max(1, Math.floor(options.count ?? defaultCount()));

  const positions = new Float32Array(count * 3);
  const alphas = new Float32Array(count);
  const positionAttribute = new BufferAttribute(positions, 3);
  const alphaAttribute = new BufferAttribute(alphas, 1);
  positionAttribute.setUsage(DynamicDrawUsage);
  alphaAttribute.setUsage(DynamicDrawUsage);

  // Fixed random rank per particle, uploaded once — the zoom thinning keeps
  // everything below a cutoff, so a STABLE rank is what makes particles drop
  // out smoothly instead of twinkling. Never rewritten.
  const ranks = new Float32Array(count);
  for (let i = 0; i < count; i++) { ranks[i] = Math.random(); }

  const geometry = new BufferGeometry();
  geometry.setAttribute("position", positionAttribute);
  geometry.setAttribute("aAlpha", alphaAttribute);
  geometry.setAttribute("aRank", new BufferAttribute(ranks, 1));
  // Positions are in R_sun and move every frame, so three's own bounding
  // sphere would be both wrong and recomputed for nothing.
  geometry.boundingSphere = new Sphere(new Vector3(0, 0, 0), OUTER_R_SUN * 1.1);

  const material = new ShaderMaterial({
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    uniforms: {
      uSize: { value: POINT_SIZE_R_SUN * options.rSunAu },
      uSizeMax: { value: POINT_SIZE_MAX },
      uMinKeep: { value: MIN_KEEP },
      uPixelScale: { value: 400 },
      uColor: { value: new Vector3(COLOR[0], COLOR[1], COLOR[2]) },
    },
    transparent: true,
    // depthTest so the Sun (and our own surface sphere) hides the far-side
    // wind; depthWrite off so particles never occlude the field lines.
    depthTest: true,
    depthWrite: false,
    blending: AdditiveBlending,
    // NOT premultiplied (unlike fieldLines): with this flag false three picks
    // glBlendFunc(SRC_ALPHA, ONE), which is exactly the multiply the fragment
    // shader would otherwise have to do by hand.
    premultipliedAlpha: false,
  });

  const points = new Points(geometry, material);
  points.frustumCulled = false;
  // After the field lines (10), so the wind adds on top of them.
  points.renderOrder = 11;

  const group = new Group();
  group.scale.setScalar(options.rSunAu);
  group.add(points);

  let paths: WindPath[] = [];
  /** line index → slot in `paths`, for keeping particles on their own line
   *  when the frame changes. */
  let slotOfLine = new Map<number, number>();
  let runSeconds = runSecondsFor(0);

  /** Slot each particle is riding, and the line index behind it. */
  const slot = new Int32Array(count);
  const line = new Int32Array(count);
  /** Position along the run, 0..1. */
  const phase = new Float32Array(count);
  /** Per-particle speed multiplier. */
  const jitter = new Float32Array(count);

  for (let i = 0; i < count; i++) {
    slot[i] = -1;
    line[i] = -1;
    phase[i] = Math.random();
    jitter[i] = 1 + (Math.random() * 2 - 1) * JITTER;
  }

  function assignRandom(i: number): void {
    if (!paths.length) {
      slot[i] = -1;
      line[i] = -1;
      return;
    }
    const next = Math.min(paths.length - 1, Math.floor(Math.random() * paths.length));
    slot[i] = next;
    line[i] = paths[next].line;
  }

  /** Write particle `i`'s world position and alpha from its phase. */
  function place(i: number): void {
    const at = i * 3;
    const path = slot[i] >= 0 ? paths[slot[i]] : undefined;
    if (!path) {
      alphas[i] = 0;
      return;
    }

    const d = phase[i] * path.total;
    let x: number;
    let y: number;
    let z: number;

    if (d >= path.traced) {
      const over = d - path.traced;
      x = path.exitX + path.dirX * over;
      y = path.exitY + path.dirY * over;
      z = path.exitZ + path.dirZ * over;
    } else {
      // Binary search the cumulative arc length: ~5 steps at 28 vertices.
      const cum = path.cum;
      let lo = 0;
      let hi = path.count - 1;
      while (hi - lo > 1) {
        const mid = (lo + hi) >> 1;
        if (cum[mid] <= d) { lo = mid; } else { hi = mid; }
      }
      const span = cum[hi] - cum[lo];
      const t = span > 0 ? (d - cum[lo]) / span : 0;
      const a = lo * 3;
      const b = hi * 3;
      x = path.xyz[a] + (path.xyz[b] - path.xyz[a]) * t;
      y = path.xyz[a + 1] + (path.xyz[b + 1] - path.xyz[a + 1]) * t;
      z = path.xyz[a + 2] + (path.xyz[b + 2] - path.xyz[a + 2]) * t;
    }

    positions[at] = x;
    positions[at + 1] = y;
    positions[at + 2] = z;

    const p = phase[i];
    const fadeIn = p < FADE_IN ? p / FADE_IN : 1;
    const fadeOut = p > 1 - FADE_OUT ? (1 - p) / FADE_OUT : 1;
    const r = Math.sqrt(x * x + y * y + z * z);
    const spawn = Math.min(
      Math.max((r - SPAWN_R_SUN) / (SPAWN_FADE_R_SUN - SPAWN_R_SUN), 0), 1);
    alphas[i] = ALPHA * fadeIn * fadeOut * spawn;
  }

  return {
    object3d: group,

    setFrameData(next: OpenLinePath[]): void {
      const rebuilt: WindPath[] = [];
      const map = new Map<number, number>();
      next.forEach((path) => {
        const built = buildPath(path, path.line);
        if (!built) { return; }
        map.set(built.line, rebuilt.length);
        rebuilt.push(built);
      });
      paths = rebuilt;
      slotOfLine = map;

      // Topology is fixed (seed i is row i in every frame), so a particle can
      // stay on ITS OWN line across a frame change and only move by the field's
      // real evolution. Only the handful of lines that stopped being open each
      // frame need a new home.
      for (let i = 0; i < count; i++) {
        const found = slotOfLine.get(line[i]);
        if (found === undefined) {
          assignRandom(i);
        } else {
          slot[i] = found;
        }
        place(i);
      }
      positionAttribute.needsUpdate = true;
      alphaAttribute.needsUpdate = true;
    },

    setSpeedKms(kms: number): void {
      runSeconds = runSecondsFor(kms);
    },

    setQuaternion(q: Quaternion): void {
      group.quaternion.copy(q);
    },

    setPixelScale(value: number): void {
      if (value > 0) { material.uniforms.uPixelScale.value = value; }
    },

    tick(dtSeconds: number): void {
      if (!group.visible || !paths.length) { return; }
      if (!Number.isFinite(dtSeconds) || dtSeconds <= 0) { return; }

      const step = dtSeconds / runSeconds;
      for (let i = 0; i < count; i++) {
        let p = phase[i] + step * jitter[i];
        if (p >= 1) {
          // Keep the remainder so the stream stays evenly spaced instead of
          // pulsing once per run.
          p -= Math.floor(p);
          phase[i] = p;
          assignRandom(i);
        } else {
          phase[i] = p;
        }
        place(i);
      }
      positionAttribute.needsUpdate = true;
      alphaAttribute.needsUpdate = true;
    },

    setVisible(value: boolean): void {
      group.visible = value;
    },

    dispose(): void {
      group.clear();
      geometry.dispose();
      material.dispose();
      paths = [];
      slotOfLine.clear();
    },
  };
}
