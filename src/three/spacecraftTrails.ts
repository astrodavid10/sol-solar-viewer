// =====================================================================
// Spacecraft trails and markers
// =====================================================================
// Per body: a solid line for where it has been, a dashed line for where it is
// going, and a small additive dot at "now". Text is DOM (see project.ts +
// SpacecraftLabel.vue) — crisp at any DPR, tappable at 44 px, no raycaster.
//
// Positions arrive as heliocentric ecliptic-J2000 AU, which is WWT's world
// frame verbatim, so nothing is transformed here.
//
// No WWT imports (CLAUDE.md footgun 12).

import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  CanvasTexture,
  Color,
  Group,
  Line,
  LineBasicMaterial,
  LineDashedMaterial,
  Sprite,
  SpriteMaterial,
  Vector3,
} from "three";

import { FLAT_SIDE } from "./winding";

const DOT_TEXTURE_SIZE = 64;

/** Marker angular size as a fraction of the camera distance — keeps the dot the
 *  same size on screen whether we're 1.5 R_sun or 1 AU out. */
const MARKER_ANGULAR_SCALE = 0.022;

/**
 * Orbit line opacity. These sit on a black sky as 1 px lines, so they were
 * losing the fight against the Sun's glow at the far end of the trail; the
 * numbers below are a deliberate lift from 0.38 / 0.22. The past arc stays
 * clearly dominant over the dashed future one — that contrast is what says
 * "this part already happened" without a legend.
 */
const PAST_OPACITY = 0.55;
const FUTURE_OPACITY = 0.30;

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

function sliceGeometry(positions: Float32Array, start: number, end: number): BufferGeometry | null {
  const count = end - start;
  if (count < 2) { return null; }
  const slice = positions.slice(start * 3, end * 3);
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(slice, 3));
  return geometry;
}

export function createSpacecraftTrails(inputs: TrailInput[]): SpacecraftTrails {
  const group = new Group();
  const texture = dotTexture();
  const markers = new Map<string, Sprite>();
  const disposables: { dispose: () => void }[] = [texture];

  for (const input of inputs) {
    const color = new Color(input.color);
    const total = Math.floor(input.positions.length / 3);
    const split = Math.min(Math.max(input.nowIndex, 0), total - 1);

    if (input.drawTrail) {
      // Past: solid, brighter — this is the part guests can reason about.
      const pastGeometry = sliceGeometry(input.positions, 0, split + 1);
      if (pastGeometry) {
        const pastMaterial = new LineBasicMaterial({
          color,
          transparent: true,
          opacity: PAST_OPACITY,
          depthWrite: false,
        });
        group.add(new Line(pastGeometry, pastMaterial));
        disposables.push(pastGeometry, pastMaterial);
      }

      // Future: dashed, dimmer. Dash size is in world units (AU) and the arcs
      // span tenths of an AU, so the dashes have to be small.
      const futureGeometry = sliceGeometry(input.positions, split, total);
      if (futureGeometry) {
        const futureMaterial = new LineDashedMaterial({
          color,
          transparent: true,
          opacity: FUTURE_OPACITY,
          depthWrite: false,
          dashSize: 0.012,
          gapSize: 0.012,
        });
        const futureLine = new Line(futureGeometry, futureMaterial);
        // Required for LineDashedMaterial — without it every dash is drawn.
        futureLine.computeLineDistances();
        group.add(futureLine);
        disposables.push(futureGeometry, futureMaterial);
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
