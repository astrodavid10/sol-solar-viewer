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
 * so they carry different content (no distance, no mission colour), different
 * weight (a ring on the surface, not a glowing dot in the dark) and a different
 * anchor (centred on the point, because the point is a location the guest can
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
      // The ring (or glyph) is centred on the projected point; the text hangs
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
  // 44 px of tap target, with the marker itself centred on the projected point:
  // half the height up, and left by (padding-left + half the marker).
  min-height: 44px;
  margin: -22px 0 0 -11px;
  padding: 0 0.5rem 0 0.35rem;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--sol-text);
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
  pointer-events: auto;
  -webkit-tap-highlight-color: transparent;
  transition: border-color 160ms ease, background 160ms ease;

  &.is-selected {
    border-color: var(--sol-accent);
    background: rgba(30, 22, 6, 0.85);
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

// Active regions are content: accent ring, full-strength label.
.is-region {
  .rl-text {
    color: var(--sol-accent);
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
