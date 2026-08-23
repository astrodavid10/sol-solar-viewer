// =====================================================================
// ?debug=1 helpers — the registration check
// =====================================================================
// The single most important visual check in this project (plan M-W4): a
// wireframe sphere at exactly R_SUN_AU must sit EXACTLY on the sphere WWT
// draws, at every zoom and every orientation.
//
//   - wireframe slightly larger/smaller than WWT's Sun  → units bug
//     (R_SUN_AU wrong, or solarSystemScale ≠ 1 — footgun 2)
//   - wireframe SLIDES off centre while orbiting        → tracked-object bug
//     (something called setTrackedObject — footgun 1)
//   - wireframe drifts on window resize                 → sizing bug in the
//     three-wwt drawing-buffer sync
//
// The axis triad tells you the frame is the one we think it is: +Z must point at
// the ecliptic north pole, and the field lines' polar footpoints should cluster
// around it (tilted by the 7.25° solar axis).
//
// No WWT imports (CLAUDE.md footgun 12).

import {
  BufferAttribute,
  BufferGeometry,
  Group,
  Line,
  LineBasicMaterial,
  LineSegments,
  SphereGeometry,
  WireframeGeometry,
} from "three";

export interface DebugHelpers {
  group: Group;
  dispose: () => void;
}

const AXIS_COLORS = [0xff4444, 0x44ff66, 0x5599ff];

function axisLine(axis: number, lengthAu: number): Line {
  const positions = new Float32Array(6);
  positions[3 + axis] = lengthAu;
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(positions, 3));
  const material = new LineBasicMaterial({
    color: AXIS_COLORS[axis],
    transparent: true,
    opacity: 0.75,
    depthWrite: false,
  });
  return new Line(geometry, material);
}

export function createDebugHelpers(rSunAu: number, axisLengthAu = 0.1): DebugHelpers {
  const group = new Group();

  // 0.4% above the surface and depth-test OFF: at exactly rSunAu the gauge
  // z-fights WWT's own Sun and loses (user-reported invisible). The offset is
  // far below what any registration bug would produce (the tracked-object bug
  // slides by ~a full radius; a units bug is >10%), so the check keeps its
  // teeth — and with no depth test the grid also stays visible over the
  // texture at every orientation.
  const sphere = new SphereGeometry(rSunAu * 1.004, 24, 16);
  const wireframe = new WireframeGeometry(sphere);
  sphere.dispose();
  const wireMaterial = new LineBasicMaterial({
    color: 0x66ccff,
    transparent: true,
    opacity: 0.35,
    depthWrite: false,
    depthTest: false,
  });
  const wire = new LineSegments(wireframe, wireMaterial);
  wire.renderOrder = 30;
  group.add(wire);

  // +X red, +Y green, +Z blue (the ecliptic north pole).
  for (let axis = 0; axis < 3; axis++) {
    group.add(axisLine(axis, axisLengthAu));
  }

  return {
    group,

    dispose(): void {
      group.traverse((node) => {
        const holder = node as unknown as {
          geometry?: { dispose?: () => void };
          material?: { dispose?: () => void };
        };
        holder.geometry?.dispose?.();
        holder.material?.dispose?.();
      });
      group.clear();
    },
  };
}
