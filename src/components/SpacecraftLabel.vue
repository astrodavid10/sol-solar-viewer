<template>
  <button
    type="button"
    class="spacecraft-label no-select"
    :class="{ 'is-selected': selected }"
    :style="chipStyle"
    :aria-label="`${name}, ${detail}`"
    @click="$emit('select')"
  >
    <span class="sl-dot" :style="{ background: color }"></span>
    <span class="sl-text">
      <span class="sl-name">{{ name }}</span>
      <span class="sl-detail">{{ detail }}</span>
    </span>
  </button>
</template>

<script lang="ts">
import { defineComponent } from "vue";

/**
 * A DOM chip pinned to a projected world position.
 *
 * DOM rather than a three.js sprite for three reasons: text stays crisp at any
 * device pixel ratio, the tap target can be 44 px regardless of zoom, and
 * hit-testing is the browser's job instead of a raycaster in the frame loop.
 *
 * Positioning goes through translate3d so the browser keeps the chip on the
 * compositor — at 20 updates a second, `left`/`top` would relayout the overlay.
 */
export default defineComponent({
  name: "SpacecraftLabel",

  props: {
    name: {
      type: String,
      required: true,
    },
    detail: {
      type: String,
      default: "",
    },
    color: {
      type: String,
      default: "#ffffff",
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
      // The marker dot sits at (x, y); the chip hangs to the upper right of it.
      return {
        transform: `translate3d(${Math.round(this.x)}px, ${Math.round(this.y)}px, 0)`,
      };
    },
  },
});
</script>

<style lang="less" scoped>
.spacecraft-label {
  position: absolute;
  top: 0;
  left: 0;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  // Vertically centered on the marker, extending to the right of it.
  min-height: 44px;
  margin: -22px 0 0 -10px;
  padding: 0 0.55rem 0 0.35rem;
  // A 20%-white hairline on a 62%-opaque near-black chip disappeared over the
  // bright limb, which is exactly where these labels tend to sit. More opaque
  // backing and a brighter edge, so the chip reads against both the black sky
  // and the Sun.
  border: 1px solid rgba(var(--sol-select-rgb), 0.34);
  border-radius: 999px;
  /* Alpha raised from 0.82 with the blur removed: it is what actually makes the
     text legible, and it costs nothing per frame.

     NO backdrop-filter here, deliberately. A backdrop-filter is recomputed
     whenever its BACKDROP changes, and the backdrop is a WebGL canvas
     repainting at the full frame rate -- so four of these chips were being
     re-blurred every frame, and they are also the elements that MOVE every
     frame. That is the reported "framerate feels low on the labels as we drag
     around the Sun". HANDOFF's own design spec already said as much: "NO
     backdrop-filter -- a solid plate doesn't need it, and blur is the most
     expensive thing in the overlay". Blur belongs on panels that sit still. */
  background: rgba(9, 2, 24, 0.92);
  color: var(--sol-text);
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
  pointer-events: auto;
  -webkit-tap-highlight-color: transparent;
  transition: border-color 160ms ease, background 160ms ease;

  &.is-selected {
    border-color: var(--sol-select);
    background: rgba(40, 31, 63, 0.92);
  }
}

.sl-dot {
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  box-shadow: 0 0 6px currentColor;
}

.sl-text {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}

.sl-name {
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.sl-detail {
  color: var(--sol-text-dim);
  font-size: 0.64rem;
}

// The chip can land anywhere, including on the disk. A tight shadow costs
// nothing and keeps the text legible without darkening the chip further.
.sl-name,
.sl-detail {
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.85);
}
</style>
