// Footguns 19 and 47 together: WWT renders with lookAtLH + perspectiveFovLH
// (orientation-reversing), and its solar-system world frame is ecliptic with
// Y and Z swapped (a mirror). The swap is folded into the three camera, so the
// two cancel and CAMERA_REVERSES_WINDING is false. Losing either half turns
// every solid mesh inside out, which cost four sessions to find. The matrices
// here come from the ENGINE'S OWN functions, not a transcription.
import { Matrix3d, Vector3d } from "@wwtelescope/engine";
import { PerspectiveCamera } from "three";
import { describe, expect, it } from "vitest";

import { wwtMatrixToTHREE } from "../../src/three/three-wwt/utils";
import { CAMERA_REVERSES_WINDING, cameraReversesWinding } from "../../src/three/winding";
import { ECLIPTIC_TO_WWT } from "../../src/three/worldFrame";

function wwtCamera(withFrameSwap: boolean): PerspectiveCamera {
  const proj = Matrix3d.perspectiveFovLH(Math.PI / 4, 0.5, 1e-4, 10);
  const view = Matrix3d.lookAtLH(
    Vector3d.create(0.01, 0.02, -0.03), Vector3d.create(0, 0, 0), Vector3d.create(0, 1, 0));
  const camera = new PerspectiveCamera();
  camera.projectionMatrix.copy(wwtMatrixToTHREE(proj));
  camera.matrixWorldInverse.copy(wwtMatrixToTHREE(view));
  if (withFrameSwap) { camera.matrixWorldInverse.multiply(ECLIPTIC_TO_WWT); }
  return camera;
}

describe("triangle winding through WWT's camera", () => {
  it("matches CAMERA_REVERSES_WINDING with the frame swap folded in (as updateTHREECamera does)", () => {
    expect(cameraReversesWinding(wwtCamera(true))).toBe(CAMERA_REVERSES_WINDING);
    expect(CAMERA_REVERSES_WINDING).toBe(false);
  });

  it("reverses without the swap, which is footgun 19's inside-out Sun", () => {
    expect(cameraReversesWinding(wwtCamera(false))).toBe(true);
  });
});
