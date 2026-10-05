// Footgun 47: WWT's solar-system world frame is ecliptic J2000 with Y and Z
// swapped -- a mirror, det = -1. The two "handedness-preserving" rotations
// that look like the fix are both wrong.
import { Vector3 } from "three";
import { describe, expect, it } from "vitest";

import { ECLIPTIC_TO_WWT } from "../../src/three/worldFrame";

describe("ECLIPTIC_TO_WWT", () => {
  it("is the Y/Z swap, a mirror with determinant -1, and its own inverse", () => {
    expect(ECLIPTIC_TO_WWT.determinant()).toBe(-1);
    const v = new Vector3(1, 2, 3).applyMatrix4(ECLIPTIC_TO_WWT);
    expect(v.toArray()).toEqual([1, 3, 2]);
    expect(v.applyMatrix4(ECLIPTIC_TO_WWT).toArray()).toEqual([1, 2, 3]);
  });

  it("maps a prograde orbit's angular momentum to -Y, the signature measured from WWT's own planets", () => {
    const r = new Vector3(1, 0, 0).applyMatrix4(ECLIPTIC_TO_WWT);
    const v = new Vector3(0, 1, 0).applyMatrix4(ECLIPTIC_TO_WWT);   // ecliptic h = r x v = +Z
    const h = new Vector3().crossVectors(r, v);
    expect(h.y).toBeCloseTo(-1, 12);
  });
});
