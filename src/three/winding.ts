// =====================================================================
// Triangle winding under WWT's camera
// =====================================================================
// WWT's render context is a port of the original Direct3D code and builds its
// matrices with Matrix3d.lookAtLH + Matrix3d.perspectiveFovLH — LEFT-handed,
// D3D convention (clip w = +z_view, depth range [0,1]). three.js assumes the
// OpenGL right-handed convention (clip w = -z_view, depth [-1,1]).
//
// three-wwt/utils.ts hands those matrices to the three camera verbatim (only
// transposed from row-vector to column-vector layout), which is what keeps our
// geometry registered with WWT's own rendering. But it also means the
// world -> clip transform three is drawing with is ORIENTATION-REVERSING
// relative to the one three assumes:
//
//     det(P_wwt)   = +w*h*zn*zf/(zf-zn)   > 0     (perspectiveFovLH)
//     det(P_three) = -w*h*2*zn*zf/(zf-zn) < 0     (ordinary RH perspective)
//     det(V)       = +1 in both conventions (lookAtLH's rotation rows
//                    (xaxis, yaxis, zaxis) form a right-handed orthonormal set)
//
// Measured, not assumed: at fov=pi/4, aspect=0.5, zn=1e-4, zf=1 the two
// determinants are +1.166e-3 and -2.332e-3.
//
// A negative determinant flips the signed area of every triangle in window
// space, so GL's fixed winding rule sees our front faces as back faces.
// three cannot compensate on its own: WebGLRenderer decides winding with
//
//     const frontFaceCW = ( object.isMesh && object.matrixWorld.determinantAffine() < 0 );
//
// which looks at the OBJECT only and never at the camera. So with three's
// defaults (frontFace CCW, cullFace BACK) every solid mesh we draw through
// WWT's camera gets its front faces culled and its back faces kept.
//
// Symptoms this caused, all from this one cause:
//   - the Sun's SDO / synthetic texture was visible "through" the sphere: what
//     you were looking at was the INSIDE of the far hemisphere;
//   - that surface looked dark, because sunSurface's limb term
//     `mu = max(dot(normalize(vWorld), view), 0.08)` is negative on a back
//     face, clamps to 0.08, and pow(0.08, 0.6) = 0.21 -> 21% brightness;
//   - the sun-glow halo and the spacecraft marker dots vanished entirely:
//     three's Sprite quad is wound CCW and SpriteMaterial defaults to
//     FrontSide, so the flip culled every sprite in the scene.
//
// The fix is per-material, because `side` is the only winding knob three
// exposes. Lines and Points have no winding and are unaffected.
//
// No WWT imports (CLAUDE.md footgun 12): this file states a fact about the
// matrices the stage is fed, and assertWinding() re-derives that fact at
// runtime from the camera itself, so if WWT ever switches to RH matrices we
// get a console warning instead of a silently inside-out Sun.

import { BackSide, DoubleSide, FrontSide } from "three";
import type { Camera, Side } from "three";

/** True while the stage is driven by WWT's left-handed D3D matrices. */
export const CAMERA_REVERSES_WINDING = true;

/**
 * `side` for a solid, single-sided mesh (the Sun sphere). BackSide under the
 * flip, which is three's supported way to say "invert this material's winding"
 * — it costs nothing and keeps one triangle per fragment, unlike DoubleSide.
 */
export const SOLID_SIDE: Side = CAMERA_REVERSES_WINDING ? BackSide : FrontSide;

/**
 * `side` for flat, camera-facing geometry (sprites). DoubleSide disables face
 * culling altogether, which is both correct and free for a single quad, and
 * survives a future convention change without another edit here.
 */
export const FLAT_SIDE: Side = DoubleSide;

/**
 * Does this camera's world->clip transform reverse orientation? Recomputed
 * from the live matrices, so it reflects whatever WWT actually handed us.
 */
export function cameraReversesWinding(camera: Camera): boolean {
  return camera.projectionMatrix.determinant()
    * camera.matrixWorldInverse.determinant() > 0;
}

let warned = false;

/**
 * One-shot check that CAMERA_REVERSES_WINDING still matches reality. Called
 * from stage.ts on the first frame that has real matrices (WWT's camera is
 * identity until the first render, and det(identity) = 1 would be a false
 * positive, so a degenerate projection is ignored).
 */
export function assertWinding(camera: Camera): void {
  if (warned) { return; }
  const p = camera.projectionMatrix.determinant();
  if (p === 0 || Math.abs(p) > 0.5) { return; }  // not a real perspective matrix yet
  warned = true;
  const actual = cameraReversesWinding(camera);
  if (actual !== CAMERA_REVERSES_WINDING) {
    console.warn(
      `[winding] camera winding is ${actual ? "" : "NOT "}reversed, but `
      + `CAMERA_REVERSES_WINDING is ${CAMERA_REVERSES_WINDING}. Solid meshes will `
      + "render inside-out and sprites may disappear; see src/three/winding.ts.");
  }
}
