// =====================================================================
// World → CSS pixels, with an occlusion test against the Sun
// =====================================================================
// Spacecraft labels are DOM chips, not sprites: text stays crisp at any DPR,
// tap targets can be 44 px regardless of zoom, and there is no raycaster in the
// frame loop. All this file does is project a handful of points and decide
// whether the Sun is in the way.
//
// No WWT imports (CLAUDE.md footgun 12) — the camera comes from stage.ts.

import { Camera, Matrix4, Vector3 } from "three";

export interface ProjectTarget {
  id: string;
  position: Vector3;
}

export interface Projected {
  id: string;
  /** CSS pixels from the top-left of the canvas. */
  xCss: number;
  yCss: number;
  /** On screen, in front of the camera, and not hidden by the Sun. */
  visible: boolean;
}

// Scratch vectors — this runs ~20x/second, so nothing is allocated per call.
const scratchNdc = new Vector3();
const scratchCamera = new Vector3();
const scratchToBody = new Vector3();
const scratchToOrigin = new Vector3();

/** Camera world position, read from `matrixWorld` without mutating anything. */
export function cameraPosition(camera: Camera, out: Vector3 = new Vector3()): Vector3 {
  return out.setFromMatrixPosition(camera.matrixWorld as Matrix4);
}

/**
 * Project `targets` into CSS pixel coordinates of a `widthCss` x `heightCss`
 * viewport.
 *
 * Occlusion: a body is hidden when it sits inside the Sun's angular disc AS
 * SEEN FROM THE CAMERA and is farther away than the Sun's centre. The angular
 * test alone would hide a spacecraft passing in FRONT of the disc, which is
 * exactly when guests most want the label.
 */
export function projectTargets(
  camera: Camera,
  widthCss: number,
  heightCss: number,
  targets: ProjectTarget[],
  occluderRadius: number,
  out: Projected[] = [],
): Projected[] {
  out.length = 0;
  if (!(widthCss > 0) || !(heightCss > 0)) { return out; }

  // Read the position straight out of matrixWorld. NOT getWorldPosition():
  // that calls updateWorldMatrix(), which for a parent-less camera does an
  // unconditional `matrixWorld.copy(matrix)` — and this camera's matrixWorld is
  // written from WWT's view matrix every frame while `matrix` is never touched,
  // so one call would reset the camera to the origin and the whole overlay with it.
  cameraPosition(camera, scratchCamera);
  const cameraDistance = scratchCamera.length();
  // asin is only defined once we're outside the sphere; the zoom clamp keeps us
  // at 1.43 R_sun minimum, but a resize race could momentarily say otherwise.
  const sunAngle = cameraDistance > occluderRadius
    ? Math.asin(occluderRadius / cameraDistance)
    : Math.PI;

  scratchToOrigin.copy(scratchCamera).negate();
  if (cameraDistance > 0) { scratchToOrigin.multiplyScalar(1 / cameraDistance); }

  for (const target of targets) {
    scratchNdc.copy(target.position).project(camera);

    const onScreen = scratchNdc.z > -1 && scratchNdc.z < 1
      && scratchNdc.x > -1.2 && scratchNdc.x < 1.2
      && scratchNdc.y > -1.2 && scratchNdc.y < 1.2;

    scratchToBody.copy(target.position).sub(scratchCamera);
    const bodyDistance = scratchToBody.length();
    let occluded = false;
    if (bodyDistance > 0 && bodyDistance > cameraDistance) {
      scratchToBody.multiplyScalar(1 / bodyDistance);
      const cosAngle = Math.max(-1, Math.min(1, scratchToBody.dot(scratchToOrigin)));
      occluded = Math.acos(cosAngle) < sunAngle;
    }

    out.push({
      id: target.id,
      xCss: (scratchNdc.x * 0.5 + 0.5) * widthCss,
      yCss: (-scratchNdc.y * 0.5 + 0.5) * heightCss,
      visible: onScreen && !occluded,
    });
  }

  return out;
}
