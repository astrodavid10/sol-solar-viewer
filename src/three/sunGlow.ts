// =====================================================================
// Sun glow — an additive sprite with a procedurally drawn gradient
// =====================================================================
// WWT's Sun sphere is a flat texture with no atmosphere, which reads as a
// billiard ball once field lines are arcing off it. A soft additive halo sells
// "this thing is on fire" for one draw call.
//
// The texture is drawn on OUR OWN canvas — no image is loaded, so there is
// nothing for CORS to refuse (CLAUDE.md footgun 6 bites any textured approach
// that reaches for sdo.gsfc.nasa.gov).
//
// No WWT imports (CLAUDE.md footgun 12).

import {
  AdditiveBlending,
  CanvasTexture,
  Sprite,
  SpriteMaterial,
  SRGBColorSpace,
} from "three";

import { FLAT_SIDE } from "./winding";

const TEXTURE_SIZE = 256;

/** Halo radius as a multiple of R_sun. */
const DEFAULT_RADII = 3;

export interface SunGlow {
  sprite: Sprite;
  setVisible: (value: boolean) => void;
  dispose: () => void;
}

/**
 * Warm-white core falling to transparent. The stops are deliberately front-
 * loaded: a linear ramp over 3 R_sun washes out the low closed arcades, which
 * are the most interesting part of the picture.
 */
function drawGradient(): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = TEXTURE_SIZE;
  canvas.height = TEXTURE_SIZE;
  const ctx = canvas.getContext("2d");
  if (!ctx) { return canvas; }

  const half = TEXTURE_SIZE / 2;
  // The sprite is 2*radii R_sun across, so the Sun's own limb sits at
  // 1/radii of the gradient radius (0.33 at the default 3 R_sun). The stops
  // are shaped so the brightest part of the halo lands just inside that limb
  // and has mostly decayed by 0.6 — enough to give the Sun an atmosphere,
  // little enough that the low closed arcades (the most interesting part of
  // the picture) still read against it under additive blending.
  const gradient = ctx.createRadialGradient(half, half, 0, half, half, half);
  gradient.addColorStop(0.00, "rgba(255, 246, 224, 0.30)");
  gradient.addColorStop(0.30, "rgba(255, 232, 175, 0.26)");
  gradient.addColorStop(0.42, "rgba(255, 198, 110, 0.11)");
  gradient.addColorStop(0.65, "rgba(255, 165, 66, 0.035)");
  gradient.addColorStop(1.00, "rgba(255, 150, 50, 0.0)");

  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, TEXTURE_SIZE, TEXTURE_SIZE);
  return canvas;
}

export function createSunGlow(rSunAu: number, radii = DEFAULT_RADII): SunGlow {
  const texture = new CanvasTexture(drawGradient());
  texture.colorSpace = SRGBColorSpace;

  const material = new SpriteMaterial({
    map: texture,
    blending: AdditiveBlending,
    transparent: true,
    // WWT's left-handed matrices reverse triangle winding, and three's Sprite
    // quad is wound CCW — with SpriteMaterial's default FrontSide the halo was
    // culled away entirely. See src/three/winding.ts.
    side: FLAT_SIDE,
    // The halo must surround the Sun sphere, so it cannot be depth-tested
    // against it — additive blending keeps it from hiding anything.
    depthTest: false,
    depthWrite: false,
  });

  const sprite = new Sprite(material);
  const size = 2 * radii * rSunAu;
  sprite.scale.set(size, size, 1);
  // Drawn before the field lines so the lines read on top of the halo.
  sprite.renderOrder = -1;

  return {
    sprite,

    setVisible(value: boolean): void {
      sprite.visible = value;
    },

    dispose(): void {
      material.dispose();
      texture.dispose();
    },
  };
}
