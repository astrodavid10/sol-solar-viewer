// =====================================================================
// Spacecraft trails and markers
// =====================================================================
// Per body: a solid line for where it has been, a dashed line for where it is
// going, and a small additive dot at "now". Text is DOM (see project.ts +
// SpacecraftLabel.vue) — crisp at any DPR, tappable at 44 px, no raycaster.
//
// Positions arrive as heliocentric ecliptic-J2000 AU, which is the frame the
// whole three scene is built in, so nothing is transformed here (the step into
// WWT's own frame happens once, on the camera — three/worldFrame.ts).
//
// No WWT imports (CLAUDE.md footgun 12).

import {
  AdditiveBlending,
  CanvasTexture,
  Color,
  Group,
  Sprite,
  SpriteMaterial,
  Vector3,
} from "three";

import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";

import { FLAT_SIDE } from "./winding";

const DOT_TEXTURE_SIZE = 64;

/** Marker angular size as a fraction of the camera distance — keeps the dot the
 *  same size on screen whether we're 1.5 R_sun or 1 AU out. */
const MARKER_ANGULAR_SCALE = 0.022;

/**
 * Orbit CORE opacity. Raised again now that the lines have real width and a
 * dark casing under them: at 0.55/0.30 they were compensating for being
 * sub-pixel, and a properly-wide line at that opacity just looks washed out.
 * The past arc stays clearly dominant over the dashed future one — that contrast
 * is what says "this part already happened" without a legend.
 */
const PAST_OPACITY = 0.90;
const FUTURE_OPACITY = 0.55;

// Line widths in CSS PIXELS. See setResolution for why that distinction matters.
//
// These used to be LineBasicMaterial, which on WebGL renders exactly ONE DEVICE
// pixel however you set `linewidth` -- three.js ignores it. On a DPR-3 phone
// that is 0.33 CSS px, which is why the orbits did not "pop", and why the two
// opacity values above had already been lifted once (0.38/0.22 -> 0.55/0.30)
// without helping: no opacity can fix a sub-pixel line.
//
// The two-pass structure is the cartographic road-casing trick, and it is the
// same dual-contrast idea the labels use: a DARK casing wins over the bright
// photosphere, the coloured core wins over the black sky, so one treatment works
// on both backgrounds where no single colour can.
const PAST_CASING_PX = 5.0;
const PAST_CORE_PX = 2.0;
const FUTURE_CASING_PX = 4.0;
const FUTURE_CORE_PX = 1.6;
const CASING_COLOR = 0x05010f;
const PAST_CASING_OPACITY = 0.55;
const FUTURE_CASING_OPACITY = 0.40;

// Dash size is in WORLD units (AU) scaled by dashScale, so this could not be
// copied from the old LineDashedMaterial values -- it had to be retuned. The
// arcs span tenths of an AU.
const DASH_SIZE = 0.02;
const GAP_SIZE = 0.02;

export interface TrailInput {
  id: string;
  color: string;
  /** 3n flattened ecliptic-AU positions. */
  positions: Float32Array;
  /** Split point between the solid past and the dashed future. */
  nowIndex: number;
  /** Earth gets a marker but no trail — WWT already draws its orbit. */
  drawTrail: boolean;
}

export interface SpacecraftTrails {
  group: Group;
  /** Move a body's marker (called every frame from the stage tick). */
  /** Framebuffer size + CSS width, for screen-space line widths. */
  setResolution: (bufferWidth: number, bufferHeight: number, cssWidth: number) => void;
  setMarker: (id: string, x: number, y: number, z: number) => void;
  /** World position of a marker, for DOM label projection. */
  marker: (id: string) => Vector3 | null;
  /** Keep marker dots a constant apparent size. */
  updateMarkerScale: (cameraDistanceAu: number) => void;
  setVisible: (value: boolean) => void;
  dispose: () => void;
}

/** Soft round dot, drawn locally (no external image ⇒ no CORS). */
function dotTexture(): CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = DOT_TEXTURE_SIZE;
  canvas.height = DOT_TEXTURE_SIZE;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const half = DOT_TEXTURE_SIZE / 2;
    const gradient = ctx.createRadialGradient(half, half, 0, half, half, half);
    gradient.addColorStop(0.0, "rgba(255,255,255,1)");
    gradient.addColorStop(0.35, "rgba(255,255,255,0.85)");
    gradient.addColorStop(0.7, "rgba(255,255,255,0.18)");
    gradient.addColorStop(1.0, "rgba(255,255,255,0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, DOT_TEXTURE_SIZE, DOT_TEXTURE_SIZE);
  }
  return new CanvasTexture(canvas);
}

/**
 * One arc as a LineGeometry (the instanced-quad kind Line2 draws).
 *
 * `setPositions` wants a plain number array, and it builds the start/end
 * attribute pairs itself — so unlike a BufferGeometry this cannot share the
 * caller's Float32Array, and the copy is unavoidable. It happens once per body
 * per load, not per frame.
 */
function sliceGeometry(positions: Float32Array, start: number, end: number): LineGeometry | null {
  const count = end - start;
  if (count < 2) { return null; }
  const geometry = new LineGeometry();
  geometry.setPositions(Array.from(positions.slice(start * 3, end * 3)));
  return geometry;
}

/**
 * One Line2 pass.
 *
 * `side: FLAT_SIDE` is NOT optional. Line2 draws instanced quads, and WWT's
 * camera reverses triangle winding (footgun 19) — with three's default
 * FrontSide every one of these would be culled outright, exactly as it culled
 * the sun glow and the spacecraft marker sprites.
 *
 * `resolution` is deliberately left at its default here and set by
 * setResolution() instead: getting it from the wrong source is footgun 16, and
 * having exactly one place that writes it is how that stays true.
 */
function linePass(
  geometry: LineGeometry,
  color: Color | number,
  widthPx: number,
  opacity: number,
  dashed: boolean,
  renderOrder: number,
): { line: Line2; material: LineMaterial } {
  const material = new LineMaterial({
    color: new Color(color).getHex(),
    linewidth: widthPx,
    transparent: true,
    opacity,
    depthWrite: false,
    side: FLAT_SIDE,
    dashed,
    dashSize: DASH_SIZE,
    gapSize: GAP_SIZE,
  });
  material.userData.cssWidth = widthPx;
  const line = new Line2(geometry, material);
  line.renderOrder = renderOrder;
  // Required for dashes; harmless otherwise, and cheap (once per load).
  line.computeLineDistances();
  return { line, material };
}

export function createSpacecraftTrails(inputs: TrailInput[]): SpacecraftTrails {
  const group = new Group();
  const texture = dotTexture();
  const markers = new Map<string, Sprite>();
  /** Every LineMaterial, so setResolution can reach all of them. */
  const materials: LineMaterial[] = [];
  const disposables: { dispose: () => void }[] = [texture];
  let widthScale = 1;

  for (const input of inputs) {
    const color = new Color(input.color);
    const total = Math.floor(input.positions.length / 3);
    const split = Math.min(Math.max(input.nowIndex, 0), total - 1);

    if (input.drawTrail) {
      // Past: solid, brighter — this is the part guests can reason about.
      // Casing first and BELOW (lower renderOrder), core on top.
      const pastGeometry = sliceGeometry(input.positions, 0, split + 1);
      if (pastGeometry) {
        const casing = linePass(pastGeometry, CASING_COLOR, PAST_CASING_PX,
          PAST_CASING_OPACITY, false, 10);
        const core = linePass(pastGeometry, color, PAST_CORE_PX,
          PAST_OPACITY, false, 11);
        group.add(casing.line, core.line);
        materials.push(casing.material, core.material);
        disposables.push(pastGeometry, casing.material, core.material);
      }

      // Future: dashed, dimmer.
      const futureGeometry = sliceGeometry(input.positions, split, total);
      if (futureGeometry) {
        const casing = linePass(futureGeometry, CASING_COLOR, FUTURE_CASING_PX,
          FUTURE_CASING_OPACITY, true, 10);
        const core = linePass(futureGeometry, color, FUTURE_CORE_PX,
          FUTURE_OPACITY, true, 11);
        group.add(casing.line, core.line);
        materials.push(casing.material, core.material);
        disposables.push(futureGeometry, casing.material, core.material);
      }
    }

    const markerMaterial = new SpriteMaterial({
      map: texture,
      color,
      blending: AdditiveBlending,
      transparent: true,
      // Without this the marker dots are culled outright (winding.ts).
      side: FLAT_SIDE,
      // Depth-tested so the dot disappears behind the Sun in step with its DOM
      // label (project.ts does the same test geometrically). With
      // `?three=overlay` there is no shared depth buffer, so the dot stays
      // visible — that is the documented cost of the escape hatch (footgun 4).
      depthTest: true,
      depthWrite: false,
    });
    const marker = new Sprite(markerMaterial);
    marker.renderOrder = 20;
    const start = split * 3;
    marker.position.set(input.positions[start], input.positions[start + 1], input.positions[start + 2]);
    group.add(marker);
    markers.set(input.id, marker);
    disposables.push(markerMaterial);
  }

  return {
    group,

    /**
     * Tell the line shader how big the framebuffer is.
     *
     * Line2 expands its quads in a vertex shader, so screen-space width is
     * meaningless to it without this — and it MUST come from
     * `gl.drawingBufferWidth/Height`, not `gl.canvas.width/height`. The vendored
     * three-wwt shim reports the canvas in CSS px on DPR > 1 screens (footgun
     * 16), so feeding it the canvas would make every width wrong by the device
     * pixel ratio. `stage.bufferSize()` is the correct source and already
     * returns exactly this.
     *
     * `cssWidth` converts the declared CSS-pixel widths into the DEVICE pixels
     * the shader actually works in. Without it a 2 px line would draw 2 device
     * px — 0.67 CSS px on a DPR-3 phone, i.e. back to the sub-pixel problem
     * this replaced, just less obviously.
     */
    setResolution(bufferWidth: number, bufferHeight: number, cssWidth: number): void {
      if (!(bufferWidth > 0) || !(bufferHeight > 0)) { return; }
      const scale = cssWidth > 0 ? bufferWidth / cssWidth : 1;
      const changed = Math.abs(scale - widthScale) > 1e-3;
      widthScale = scale;
      materials.forEach((material) => {
        material.resolution.set(bufferWidth, bufferHeight);
        if (changed) {
          // Re-derive from the declared CSS width rather than multiplying the
          // live value, which would compound on every resize.
          const base = material.userData.cssWidth as number | undefined;
          if (base !== undefined) { material.linewidth = base * scale; }
        }
      });
    },

    setMarker(id: string, x: number, y: number, z: number): void {
      markers.get(id)?.position.set(x, y, z);
    },

    marker(id: string): Vector3 | null {
      return markers.get(id)?.position ?? null;
    },

    updateMarkerScale(cameraDistanceAu: number): void {
      const size = Math.max(1e-4, cameraDistanceAu * MARKER_ANGULAR_SCALE);
      markers.forEach((sprite) => sprite.scale.set(size, size, 1));
    },

    setVisible(value: boolean): void {
      group.visible = value;
    },

    dispose(): void {
      group.clear();
      markers.clear();
      disposables.forEach((d) => d.dispose());
    },
  };
}
