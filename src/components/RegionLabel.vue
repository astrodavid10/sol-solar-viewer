<template>
  <button
    type="button"
    class="region-label no-select"
    :class="[`is-${variant}`, { 'is-selected': selected }]"
    :style="chipStyle"
    :aria-label="ariaLabel"
    @click="$emit('select')"
  >
    <span v-if="glyph" class="rl-glyph" aria-hidden="true">{{ glyph }}</span>
    <span v-else class="rl-ring" aria-hidden="true"></span>
    <span class="rl-text">{{ label }}</span>
  </button>
</template>

<script lang="ts">
import { defineComponent } from "vue";

/**
 * A chip pinned to a point ON the Sun's surface — an active region, or the
 * sub-Earth point.
 *
 * A sibling of SpacecraftLabel rather than a prop on it: the two mark different
 * KINDS of thing (a body out in space at a distance vs. a place on the sphere),
 * so they carry different content (no distance, no mission color), different
 * weight (a ring on the surface, not a glowing dot in the dark) and a different
 * anchor (centered on the point, because the point is a location the guest can
 * see under it). What they share — translate3d positioning on the compositor at
 * 20 Hz, a 44 px tap target regardless of zoom, DOM text that stays crisp at any
 * DPR — is the pattern, not the component.
 *
 * `variant` is the whole styling story: "region" is content (accent ring, a
 * region a guest can tap and read about), "earth" is orientation furniture
 * (dimmer, quieter, one line to say).
 */
export default defineComponent({
  name: "RegionLabel",

  props: {
    label: {
      type: String,
      required: true,
    },
    /** "region" for an active region, "earth" for the sub-Earth marker. */
    variant: {
      type: String as () => "region" | "earth",
      default: "region",
    },
    /** Rendered in place of the ring when set (the sub-Earth ⊕). */
    glyph: {
      type: String,
      default: "",
    },
    /** Screen-reader text; falls back to the visible label. */
    description: {
      type: String,
      default: "",
    },
    /** CSS pixels from the top-left of the stage. */
    x: {
      type: Number,
      default: 0,
    },
    y: {
      type: Number,
      default: 0,
    },
    selected: {
      type: Boolean,
      default: false,
    },
  },

  emits: ["select"],

  computed: {
    chipStyle(): Record<string, string> {
      // The ring (or glyph) is centered on the projected point; the text hangs
      // to the right of it. translate3d keeps the chip on the compositor —
      // left/top would relayout the whole overlay 20 times a second.
      return {
        transform: `translate3d(${Math.round(this.x)}px, ${Math.round(this.y)}px, 0)`,
      };
    },

    ariaLabel(): string {
      return this.description || this.label;
    },
  },
});
</script>

<style lang="less" scoped>
.region-label {
  position: absolute;
  top: 0;
  left: 0;
  display: flex;
  align-items: center;
  gap: 0.3rem;
  // 44 px of tap target, with the marker itself centered on the projected point:
  // half the height up, and left by (padding-left + half the marker).
  min-height: 44px;
  margin: -22px 0 0 -11px;
  padding: 0 0.5rem 0 0.35rem;
  border: 1px solid rgba(245, 244, 240, 0.22);
  border-radius: 999px;
  // These chips sit ON the photosphere, which is the brightest thing on screen.
  // Measured against WCAG 2.1 relative luminance, NOTHING survives naked there:
  // the app's text at 1.10:1, gold at 1.54:1, dim text at 2.22:1. Legibility
  // over the Sun has to come from a PLATE, never from a colour choice — the
  // whole argument of HANDOFF §8.3's last table. This plate composites to
  // #241E33 over a white disk, where the text below measures 14.6:1.
  //
  // A solid plate on purpose rather than a blurred one: the backdrop is a canvas
  // repainting every frame and these chips MOVE every frame, so a
  // backdrop-filter here costs a blur per chip per frame (footgun 39).
  background: rgba(9, 2, 24, 0.86);
  color: var(--sol-text);
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
  pointer-events: auto;
  -webkit-tap-highlight-color: transparent;
  transition: border-color 160ms ease, background 160ms ease;

  &.is-selected {
    border-color: var(--sol-accent);
    background: rgba(40, 31, 63, 0.92);
  }
}

.rl-ring {
  flex: 0 0 auto;
  box-sizing: border-box;
  width: 10px;
  height: 10px;
  border: 2px solid var(--sol-accent);
  border-radius: 50%;
  // The Sun behind these is the brightest thing on screen, so the ring gets a
  // dark halo instead of a glow — a glow would vanish into the photosphere.
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.55), 0 0 5px rgba(0, 0, 0, 0.7);
}

.rl-text {
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.01em;
  // Same reason as the ring's halo: dark text-shadow, not a bright one.
  text-shadow: 0 0 4px rgba(0, 0, 0, 0.85), 0 1px 2px rgba(0, 0, 0, 0.9);
}

// Active regions are content: accent RING, full-strength label.
//
// The label text used to be gold, which measured **1.54:1 on the photosphere** —
// the worst contrast anywhere in the app, and by definition sitting exactly
// where it was worst. Gold now lives in the ring only, where it is a 2 px shape
// against a dark halo rather than 11 px letterforms against the Sun.
//
// This also takes colour out of the role of sole carrier, which it should never
// have had: the RING means "active region" and the ⊕ GLYPH means "sub-Earth", so
// the two chip kinds are distinguishable without seeing hue at all.
.is-region {
  .rl-text {
    color: var(--sol-text);
  }
}

// The sub-Earth marker is orientation furniture. Dimmer than the regions on
// purpose — it answers a question the guest hasn't asked yet.
.is-earth {
  opacity: 0.62;

  .rl-glyph {
    flex: 0 0 auto;
    width: 12px;
    font-size: 0.8rem;
    line-height: 1;
    text-align: center;
    color: var(--sol-text-dim);
    text-shadow: 0 0 4px rgba(0, 0, 0, 0.9);
  }

  .rl-text {
    color: var(--sol-text-dim);
    font-weight: 600;
  }

  &.is-selected {
    opacity: 1;
  }
}
</style>
