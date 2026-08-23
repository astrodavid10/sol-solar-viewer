// =====================================================================
// Off-limb annulus — the part of a solar image that is not on the sphere
// =====================================================================
// The Carrington map wrapped round sunSurface's sphere is a map of the
// SURFACE. Everything outside the limb — prominences, low coronal loops, the
// inner corona — is dropped by that reprojection, and it cannot simply be put
// back: off-limb structure is genuinely three-dimensional, and a disk image
// records only its projection onto the sky as seen from Earth. We have no
// model of its depth.
//
// So it comes back as what it actually is: a picture, on a flat plane, correct
// from one viewpoint. The pipeline ships a square crop centred on the fitted
// disk centre with the disk itself blacked out (pipeline/texture/export.py,
// build_offlimb), and this draws it as a camera-facing billboard sized so the
// blacked-out hole lands exactly on the sphere's silhouette.
//
// The honesty problem, and what we do about it: the crop is only true when the
// camera is where SDO is. Rotate away and it becomes a photograph of the
// corona pasted flat across a Sun now seen from the side — a confident-looking
// lie about structure we do not know. So it FADES OUT with the angle from the
// sub-Earth direction, and by the time the guest has orbited far enough to
// notice the geometry is wrong, it is gone and the 3D field lines are carrying
// the explanation instead. That transition is the honest version of the
// feature, not a compromise on it.
//
// Additive blending, so the blacked-out disk contributes nothing and needs no
// alpha channel — which is why the pipeline can ship a JPEG rather than a PNG
// several times the size.
//
// No WWT imports (CLAUDE.md footgun 12).

import {
  AdditiveBlending,
  Group,
  Matrix4,
  Mesh,
  PlaneGeometry,
  Quaternion,
  ShaderMaterial,
  SRGBColorSpace,
  Texture,
  Vector3,
} from "three";

import { FLAT_SIDE } from "./winding";

export interface OffLimbOptions {
  /** Sun radius in AU as WWT draws it (footgun 2). */
  rSunAu: number;
}

export interface OffLimbLayer {
  object3d: Group;
  /**
   * Point the billboard at the camera and set its fade.
   *
   * `subEarth` is the sub-Earth direction in WORLD space — the same vector
   * sunSurface derives for its far-side dimming. `up` keeps solar north up in
   * the plane, so the crop is not rolled relative to the sphere under it.
   */
  update: (cameraPos: Vector3, subEarth: Vector3, up: Vector3) => void;
  /** Swap in a channel's crop. `halfWidthRSun` comes from the manifest. */
  setTexture: (texture: Texture, halfWidthRSun: number) => void;
  setVisible: (value: boolean) => void;
  dispose: () => void;
}

/**
 * Fully visible until the camera is this far from the sub-Earth direction,
 * gone by the outer angle.
 *
 * 25 deg is roughly where the flatness starts to be readable as wrong against
 * the sphere's own curvature; by 55 deg the guest is clearly looking at the Sun
 * from the side and a flat corona would be nonsense. Generous rather than
 * tight, because the fade itself is the thing worth seeing.
 */
const FADE_INNER_DEG = 25;
const FADE_OUTER_DEG = 55;

const VERTEX_SHADER = `
varying vec2 vUv;

void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const FRAGMENT_SHADER = `
uniform sampler2D uMap;
uniform float uOpacity;

varying vec2 vUv;

void main() {
  vec3 c = texture2D(uMap, vUv).rgb;
  // Additive: the pipeline blacked out the disk, so those texels contribute
  // nothing and the sphere shows through untouched. No alpha channel needed.
  gl_FragColor = vec4(c * uOpacity, 1.0);
}
`;

export function createOffLimb(options: OffLimbOptions): OffLimbLayer {
  // A unit quad; the mesh is scaled to the crop's real extent in setTexture,
  // because that extent differs per instrument (AIA reaches ~1.28 R_sun, HMI
  // ~1.09) and arrives as data rather than a constant.
  const geometry = new PlaneGeometry(2, 2);

  const material = new ShaderMaterial({
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    uniforms: {
      uMap: { value: null as Texture | null },
      uOpacity: { value: 0 },
    },
    transparent: true,
    blending: AdditiveBlending,
    // Additive already ignores the black disk, and depth-writing a full quad
    // across the Sun would punch a hole in everything behind it.
    depthWrite: false,
    // Depth-TEST on: the sphere is the authoritative occluder (footgun 18), so
    // the half of the annulus behind the Sun is correctly hidden.
    depthTest: true,
    side: FLAT_SIDE,
  });

  const mesh = new Mesh(geometry, material);
  mesh.frustumCulled = false;
  // Behind the field lines (10) and the wind (11): this is backdrop, and the
  // structure the guest is meant to read sits on top of it.
  mesh.renderOrder = 1;
  mesh.visible = false;

  const group = new Group();
  group.add(mesh);

  let texture: Texture | null = null;
  let visible = true;
  const forward = new Vector3();
  const right = new Vector3();
  const trueUp = new Vector3();
  const quat = new Quaternion();
  // Hoisted: update() runs on the label cadence, and allocating a Matrix4 per
  // call to build one orientation would be pure garbage.
  const basisMatrix = new Matrix4();

  function applyVisible(): void {
    mesh.visible = visible && texture !== null
      && (material.uniforms.uOpacity.value as number) > 0.004;
  }

  return {
    object3d: group,

    setTexture(next: Texture, halfWidthRSun: number): void {
      next.colorSpace = SRGBColorSpace;
      next.needsUpdate = true;
      const previous = texture;
      texture = next;
      material.uniforms.uMap.value = next;
      // The crop spans +/- halfWidthRSun from Sun centre, and the quad is 2
      // units across, so this scale puts the blacked-out hole exactly on the
      // sphere's silhouette.
      mesh.scale.setScalar(halfWidthRSun * options.rSunAu);
      previous?.dispose();
      applyVisible();
    },

    update(cameraPos: Vector3, subEarth: Vector3, up: Vector3): void {
      if (!texture) { return; }

      forward.copy(cameraPos).normalize();
      const cos = Math.min(1, Math.max(-1, forward.dot(subEarth)));
      const angleDeg = (Math.acos(cos) * 180) / Math.PI;
      const t = (angleDeg - FADE_INNER_DEG) / (FADE_OUTER_DEG - FADE_INNER_DEG);
      const clamped = Math.min(1, Math.max(0, t));
      // Smoothstep, so the crop dissolves rather than switching off.
      material.uniforms.uOpacity.value = 1 - clamped * clamped * (3 - 2 * clamped);

      // Face the camera with solar north up. Built as an explicit orthonormal
      // basis rather than lookAt(): three's lookAt would roll the plane freely
      // and the crop has to stay square with the sphere's own north.
      right.crossVectors(up, forward);
      if (right.lengthSq() < 1e-12) { applyVisible(); return; }
      right.normalize();
      trueUp.crossVectors(forward, right).normalize();
      basisMatrix.makeBasis(right, trueUp, forward);
      quat.setFromRotationMatrix(basisMatrix);
      mesh.quaternion.copy(quat);

      applyVisible();
    },

    setVisible(value: boolean): void {
      visible = value;
      applyVisible();
    },

    dispose(): void {
      group.clear();
      geometry.dispose();
      material.dispose();
      texture?.dispose();
      texture = null;
    },
  };
}
