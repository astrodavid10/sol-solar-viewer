// =====================================================================
// PFSS field lines — one geometry, 13 frames, morphed on the GPU
// =====================================================================
// The whole 48-hour animation is ONE indexed BufferGeometry. What changes per
// frame is which BufferAttributes are bound to it:
//
//   position  → frame A vertex positions (normalized uint16, Carrington R_sun)
//   aPosB     → frame B vertex positions
//   aMetaA/B  → per-vertex RGBA: rgb = topology colour, a = validity + class
//   uMix      → 0..1 within the pair
//
// Advancing a frame is therefore four setAttribute() calls and a uniform write —
// no buffer uploads, no CPU vertex work. Each frame's attributes are built once
// on arrival and cached; 13 frames × 19,328 verts × (6 + 4) bytes ≈ 2.5 MB of
// GPU buffers total.
//
// Why this is legal at all: the pipeline guarantees FIXED TOPOLOGY (seed i is
// row i in every frame, dead seeds padded with a repeated vertex) and keeps
// vertices in the ROTATING Carrington frame, so consecutive frames differ only
// by real field evolution. Carrington rotation (2.36°/frame) lives entirely in
// the group quaternion, slerped from the manifest's `quat_carr_to_ecl`.
//
// No WWT imports (CLAUDE.md footgun 12).

import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Group,
  LineSegments,
  Quaternion,
  ShaderMaterial,
  Sphere,
  Vector3,
} from "three";

import type { PfssFrame, Rgb } from "../data/pfss";

/** Animation speed: 13 frames ≈ 10 s for the whole 48 h loop. */
export const SECONDS_PER_FRAME = 0.8;

export interface FieldLinesOptions {
  /** Sun radius in AU as WWT draws it — the group scale (footgun 2). */
  rSunAu: number;
  /** Total frames the manifest promises (not how many have loaded). */
  frameCount: number;
  nLines: number;
  nVertsTotal: number;
  /** nLines+1 prefix sums from topology.bin. */
  lineOffset: Uint32Array;
  colors: { closed: Rgb; openPos: Rgb; openNeg: Rgb };
  /** Dequantization from the manifest: `rSun = q/65535 * scale + offset`. */
  quantScale: number;
  quantOffset: number;
  /** Opacity model. */
  rss: number;
  closedFloor: number;
}

/**
 * One OPEN field line of a single frame, dequantized — the solar wind's
 * source path (see `openLinePaths`).
 */
export interface OpenLinePath {
  /** Line index in topology space. Stable across frames (seed i is row i in
   *  every frame), so a consumer can keep a particle on its own line. */
  line: number;
  /** nVerts*3 interleaved xyz in Carrington R_sun, footpoint FIRST. */
  xyz: Float32Array;
  /** +1 or -1, this frame's polarity for the line. */
  polarity: number;
}

export interface FieldLines {
  /** Add to the stage's scene. Carries the R_sun→AU scale and the orientation. */
  group: Group;
  /** Build and cache GPU attributes for one decoded frame. */
  addFrame: (frame: PfssFrame) => void;
  /** Total frames decoded so far. */
  loadedCount: () => number;
  /** Oldest index of the contiguous newest-first run we can animate. */
  loadedFrom: () => number;
  /** Current playhead, in fractional frame indices. */
  time: () => number;
  /** Frame A of the current pair, i.e. the integer frame under the playhead. */
  frameIndex: () => number;
  /**
   * The integer frame's OPEN, VALID lines, dequantized to R_sun and oriented
   * footpoint→outward. Allocates, so callers rebuild only when `frameIndex()`
   * changes — NOT per uMix tick.
   */
  openLinePaths: () => OpenLinePath[];
  /** Paint every line one flat colour instead of the polarity palette. */
  setMonochrome: (on: boolean) => void;
  setTime: (frames: number) => void;
  /** Advance the playhead by `dtSec` of wall clock, looping. */
  advance: (dtSec: number) => void;
  /** Global multiplier, for layer fades. */
  setOpacity: (value: number) => void;
  setVisible: (value: boolean) => void;
  /** Re-create GPU attributes after a context loss (arrays are retained). */
  rebuild: () => void;
  dispose: () => void;
}

interface GpuFrame {
  index: number;
  magUnix: number;
  quaternion: Quaternion;
  /** Retained for rebuild() after a WebGL context loss. */
  xyzU16: Uint16Array;
  metaU8: Uint8Array;
  /** Retained per-line, per-frame classes — openLinePaths() needs them
   *  unblended (the meta attribute's alpha channel is for the shader). */
  polarity: Int8Array;
  valid: Uint8Array;
  position: BufferAttribute;
  meta: BufferAttribute;
}

// ---------------------------------------------------------------------
// Shaders
// ---------------------------------------------------------------------
// GLSL ES 1.00 — three's default for ShaderMaterial, and accepted verbatim by
// WebGL2 contexts. `position`, `projectionMatrix` and `modelViewMatrix` come
// from three's non-raw prefix, so they are deliberately not redeclared.
//
// Both position attributes are NORMALIZED uint16, so the /65535 of the decode
// formula is already done by the GPU: only scale + offset remain.

/**
 * The single colour used when the polarity palette is switched off — the app's
 * own --sol-accent2 "open-field blue" (#5fb8ff), so the monochrome field reads
 * as the same blue the rest of the UI uses for open field.
 */
const MONO_COLOR: [number, number, number] = [0.373, 0.722, 1.0];

const VERTEX_SHADER = `
attribute vec3 aPosB;
attribute vec4 aMetaA;
attribute vec4 aMetaB;

uniform float uMix;
uniform float uScale;
uniform float uOffset;
uniform float uRss;
uniform float uClosedFloor;
uniform float uOpacity;
uniform float uMono;
uniform vec3 uMonoColor;

varying vec3 vColor;
varying float vAlpha;

void main() {
  vec3 p = mix(position, aPosB, uMix) * uScale + uOffset;
  float r = length(p);

  // Manifest opacity_model: t = (r-1)/(rss-1); closed lines fade to a floor so
  // the low arcades stay readable, open lines fade right out at the source
  // surface so the corona doesn't end in a hard edge.
  float t = clamp((r - 1.0) / max(uRss - 1.0, 1e-3), 0.0, 1.0);
  float aClosed = max(uClosedFloor, 1.0 - (1.0 - uClosedFloor) * t);
  float aOpen = clamp(1.0 - t, 0.0, 1.0);

  // meta.a packs two things: 0.0 = dead seed, 0.502 = valid open,
  // 1.0 = valid closed. Interpolating it directly would blur the classes, so
  // we separate the validity ramp (which SHOULD cross-fade, ~4 lines per frame
  // pair appear or die) from the class flag (which should not).
  float visA = step(0.01, aMetaA.a);
  float visB = step(0.01, aMetaB.a);
  float vis = mix(visA, visB, uMix);
  vec4 meta = mix(aMetaA, aMetaB, uMix);
  float closed = step(0.7, meta.a / max(vis, 1e-3));

  // Polarity palette (dome colours, baked per vertex) or one flat colour.
  // A uniform mix rather than a rebuilt attribute: the colour lives in a
  // NORMALIZED uint8 vertex attribute shared by both frames of the pair, so
  // re-baking it would mean re-uploading every vertex on a toggle.
  vColor = mix(meta.rgb, uMonoColor, uMono);
  vAlpha = vis * mix(aOpen, aClosed, closed) * uOpacity;

  gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
}
`;

const FRAGMENT_SHADER = `
varying vec3 vColor;
varying float vAlpha;

void main() {
  if (vAlpha < 0.01) { discard; }
  // Premultiplied — see material.premultipliedAlpha. Dead vertices contribute
  // nothing even before the discard, so a padded seed can never draw a ray to
  // the Sun's centre.
  gl_FragColor = vec4(vColor * vAlpha, vAlpha);
}
`;

// ---------------------------------------------------------------------
// Geometry
// ---------------------------------------------------------------------

/**
 * Static index buffer: one LINE segment per consecutive vertex pair, for EVERY
 * line including the currently-invalid ones.
 *
 * Skipping invalid lines here would be wrong — `valid` is a PER-FRAME flag
 * (measured: ~4 lines flip between adjacent frames), and this index is built
 * once. Invalid lines are degenerate (the pipeline repeats the last good
 * vertex) and get alpha 0 from their meta attribute, so they cost a handful of
 * zero-length primitives and nothing else.
 */
function buildLineIndex(
  lineOffset: Uint32Array,
  nLines: number,
  nVertsTotal: number,
): Uint16Array | Uint32Array {
  let segments = 0;
  for (let i = 0; i < nLines; i++) {
    segments += Math.max(0, lineOffset[i + 1] - lineOffset[i] - 1);
  }
  const indices = nVertsTotal > 65535
    ? new Uint32Array(segments * 2)
    : new Uint16Array(segments * 2);

  let write = 0;
  for (let i = 0; i < nLines; i++) {
    const end = lineOffset[i + 1];
    for (let v = lineOffset[i]; v + 1 < end; v++) {
      indices[write] = v;
      indices[write + 1] = v + 1;
      write += 2;
    }
  }
  return indices;
}

function toByte(value: number): number {
  return Math.max(0, Math.min(255, Math.round(value * 255)));
}

/**
 * Expand per-LINE polarity/validity into the per-VERTEX RGBA meta attribute.
 * Runs once per frame on arrival (≈19k vertices — under a millisecond).
 */
function buildMeta(
  frame: PfssFrame,
  options: FieldLinesOptions,
): Uint8Array {
  const { lineOffset, nLines, nVertsTotal, colors } = options;
  const meta = new Uint8Array(nVertsTotal * 4);

  const closed: [number, number, number] = [toByte(colors.closed[0]), toByte(colors.closed[1]), toByte(colors.closed[2])];
  const openPos: [number, number, number] = [toByte(colors.openPos[0]), toByte(colors.openPos[1]), toByte(colors.openPos[2])];
  const openNeg: [number, number, number] = [toByte(colors.openNeg[0]), toByte(colors.openNeg[1]), toByte(colors.openNeg[2])];

  for (let i = 0; i < nLines; i++) {
    const polarity = frame.polarity[i];
    const rgb = polarity === 0 ? closed : (polarity > 0 ? openPos : openNeg);
    // 255 = valid + closed, 128 = valid + open, 0 = dead seed.
    const alpha = frame.valid[i] ? (polarity === 0 ? 255 : 128) : 0;
    const end = lineOffset[i + 1];
    for (let v = lineOffset[i]; v < end; v++) {
      const at = v * 4;
      meta[at] = rgb[0];
      meta[at + 1] = rgb[1];
      meta[at + 2] = rgb[2];
      meta[at + 3] = alpha;
    }
  }
  return meta;
}

// ---------------------------------------------------------------------
// Layer
// ---------------------------------------------------------------------

export function createFieldLines(options: FieldLinesOptions): FieldLines {
  const geometry = new BufferGeometry();
  const indices = buildLineIndex(options.lineOffset, options.nLines, options.nVertsTotal);
  geometry.setIndex(new BufferAttribute(indices, 1));

  // Positions live in normalized-integer space until the vertex shader
  // dequantizes them, so three's own bounding sphere would be nonsense. Give it
  // a generous one and turn culling off — the layer is always on screen anyway.
  geometry.boundingSphere = new Sphere(new Vector3(0, 0, 0), options.rss * 2);

  const material = new ShaderMaterial({
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    uniforms: {
      uMix: { value: 0 },
      uScale: { value: options.quantScale },
      uOffset: { value: options.quantOffset },
      uRss: { value: options.rss },
      uClosedFloor: { value: options.closedFloor },
      uMono: { value: 0 },
      uMonoColor: { value: new Vector3(...MONO_COLOR) },
      uOpacity: { value: 1 },
    },
    transparent: true,
    // depthTest keeps WWT's Sun sphere in front of far-side lines (the whole
    // point of the shared-canvas target); depthWrite off so overlapping lines
    // add instead of z-fighting.
    depthTest: true,
    depthWrite: false,
    blending: AdditiveBlending,
    // REQUIRED, and easy to miss: the fragment shader below already multiplies
    // colour by alpha. three picks the blend function from THIS flag — true
    // gives glBlendFunc(ONE, ONE), false gives (SRC_ALPHA, ONE), which would
    // multiply by alpha a second time. The visible symptom of getting it wrong
    // is an alpha-squared falloff: the closed-line floor renders at 0.0625
    // instead of 0.25 and the whole corona looks washed out.
    premultipliedAlpha: true,
  });

  const lines = new LineSegments(geometry, material);
  lines.frustumCulled = false;
  lines.renderOrder = 10;

  const group = new Group();
  group.scale.setScalar(options.rSunAu);
  group.add(lines);

  const frames = new Array<GpuFrame | null>(options.frameCount).fill(null);
  let loaded = 0;
  let from = options.frameCount;
  let playhead = Math.max(0, options.frameCount - 1);
  let boundA = -1;
  let boundB = -1;

  function makeAttributes(gpu: GpuFrame): void {
    gpu.position = new BufferAttribute(gpu.xyzU16, 3, true);
    gpu.meta = new BufferAttribute(gpu.metaU8, 4, true);
  }

  function bind(indexA: number, indexB: number): void {
    const a = frames[indexA];
    const b = frames[indexB];
    if (!a || !b) { return; }
    if (indexA === boundA && indexB === boundB) { return; }
    geometry.setAttribute("position", a.position);
    geometry.setAttribute("aPosB", b.position);
    geometry.setAttribute("aMetaA", a.meta);
    geometry.setAttribute("aMetaB", b.meta);
    boundA = indexA;
    boundB = indexB;
  }

  /** Apply `playhead`: pick the pair, set uMix, slerp the orientation. */
  function apply(): void {
    const last = options.frameCount - 1;
    if (from > last) { return; }

    const clamped = Math.min(Math.max(playhead, from), last);
    playhead = clamped;

    const indexA = Math.min(Math.floor(clamped), last);
    const indexB = Math.min(indexA + 1, last);
    const fraction = indexB === indexA ? 0 : clamped - indexA;

    bind(indexA, indexB);
    const a = frames[indexA];
    const b = frames[indexB];
    if (!a || !b) { return; }

    material.uniforms.uMix.value = fraction;
    group.quaternion.slerpQuaternions(a.quaternion, b.quaternion, fraction);
  }

  /** Frame A of the pair the playhead currently straddles; -1 if none loaded. */
  function currentIndexA(): number {
    const last = options.frameCount - 1;
    if (from > last) { return -1; }
    const clamped = Math.min(Math.max(playhead, from), last);
    return Math.min(Math.floor(clamped), last);
  }

  /** Longest run of loaded frames ending at the newest — what we can animate. */
  function recomputeLoadedFrom(): void {
    let k = options.frameCount;
    while (k > 0 && frames[k - 1]) { k -= 1; }
    from = k;
  }

  return {
    group,

    addFrame(frame: PfssFrame): void {
      if (frame.index < 0 || frame.index >= options.frameCount) { return; }
      if (frames[frame.index]) { return; }

      const gpu: GpuFrame = {
        index: frame.index,
        magUnix: frame.magUnix,
        quaternion: new Quaternion(frame.quat[0], frame.quat[1], frame.quat[2], frame.quat[3]).normalize(),
        xyzU16: frame.xyzU16,
        metaU8: buildMeta(frame, options),
        polarity: frame.polarity,
        valid: frame.valid,
        // Replaced immediately by makeAttributes; typed here to avoid a
        // nullable field that every later read would have to guard.
        position: null as unknown as BufferAttribute,
        meta: null as unknown as BufferAttribute,
      };
      makeAttributes(gpu);

      frames[frame.index] = gpu;
      loaded += 1;
      const wasEmpty = from >= options.frameCount;
      recomputeLoadedFrom();

      // First frame in is the newest (load_order: newest_first) — park there,
      // because the app is fundamentally about "now".
      if (wasEmpty) { playhead = frame.index; }
      apply();
    },

    loadedCount: () => loaded,
    loadedFrom: () => from,
    time: () => playhead,
    frameIndex: currentIndexA,

    /**
     * Dequantize the current frame's open lines for the solar-wind layer.
     *
     * Orientation matters and is NOT uniform in the file: the pipeline traces
     * along +B, so an open-POSITIVE line arrives footpoint-first while an
     * open-NEGATIVE one arrives source-surface-first. Measured on f18.bin
     * (harness probe-order.js): 100/100 open+ have r increasing, 0/55 open-
     * do, and every open line's radial minimum is at one END of the polyline
     * (never in the middle), so "reverse when r[0] > r[last]" is exact rather
     * than a heuristic.
     */
    setMonochrome(on: boolean): void {
      material.uniforms.uMono.value = on ? 1 : 0;
    },

    openLinePaths(): OpenLinePath[] {
      const index = currentIndexA();
      const gpu = index >= 0 ? frames[index] : null;
      if (!gpu) { return []; }

      const { lineOffset, nLines, quantScale, quantOffset } = options;
      const out: OpenLinePath[] = [];
      for (let i = 0; i < nLines; i++) {
        const polarity = gpu.polarity[i];
        if (!gpu.valid[i] || polarity === 0) { continue; }
        const start = lineOffset[i];
        const end = lineOffset[i + 1];
        const count = end - start;
        if (count < 2) { continue; }

        const xyz = new Float32Array(count * 3);
        for (let v = 0; v < count; v++) {
          const src = (start + v) * 3;
          const dst = v * 3;
          xyz[dst] = (gpu.xyzU16[src] / 65535) * quantScale + quantOffset;
          xyz[dst + 1] = (gpu.xyzU16[src + 1] / 65535) * quantScale + quantOffset;
          xyz[dst + 2] = (gpu.xyzU16[src + 2] / 65535) * quantScale + quantOffset;
        }

        const rFirst = Math.sqrt(xyz[0] * xyz[0] + xyz[1] * xyz[1] + xyz[2] * xyz[2]);
        const tail = (count - 1) * 3;
        const rLast = Math.sqrt(
          xyz[tail] * xyz[tail] + xyz[tail + 1] * xyz[tail + 1] + xyz[tail + 2] * xyz[tail + 2]);
        if (rFirst > rLast) {
          for (let v = 0; v < count >> 1; v++) {
            const a = v * 3;
            const b = (count - 1 - v) * 3;
            for (let k = 0; k < 3; k++) {
              const swap = xyz[a + k];
              xyz[a + k] = xyz[b + k];
              xyz[b + k] = swap;
            }
          }
        }
        out.push({ line: i, xyz, polarity });
      }
      return out;
    },

    setTime(value: number): void {
      if (!Number.isFinite(value)) { return; }
      playhead = value;
      apply();
    },

    advance(dtSec: number): void {
      const last = options.frameCount - 1;
      if (from >= last) { return; }
      const span = last - from;
      let next = playhead + dtSec / SECONDS_PER_FRAME;
      if (next > last) {
        // Loop back to the oldest loaded frame, keeping the sub-frame phase so
        // the animation doesn't stutter at the seam.
        next = from + ((next - from) % span);
      }
      playhead = next;
      apply();
    },

    setOpacity(value: number): void {
      material.uniforms.uOpacity.value = Math.max(0, Math.min(1, value));
    },

    setVisible(value: boolean): void {
      group.visible = value;
    },

    rebuild(): void {
      for (const gpu of frames) {
        if (gpu) { makeAttributes(gpu); }
      }
      boundA = -1;
      boundB = -1;
      apply();
    },

    dispose(): void {
      group.clear();
      geometry.dispose();
      material.dispose();
      frames.fill(null);
    },
  };
}
