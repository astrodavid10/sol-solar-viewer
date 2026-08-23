<template>
  <div class="layer-panel no-select" role="dialog" aria-label="Layers">
    <button
      v-for="row in rows"
      :key="row.key"
      type="button"
      class="lp-row"
      :aria-pressed="layers[row.key]"
      @click="toggle(row.key)"
    >
      <span class="lp-switch" :class="{ 'is-on': layers[row.key] }">
        <span class="lp-knob"></span>
      </span>
      <span class="lp-text">
        <span class="lp-label">{{ row.label }}</span>
        <span class="lp-hint">{{ row.hint }}</span>
      </span>
    </button>

    <!-- Same switch as the layer rows above, because it is the same kind of
         question: on or off. Off is not "no color" — it is one flat electric
         blue, so the field still reads as a single structure. -->
    <button
      type="button"
      class="lp-row"
      :aria-pressed="polarityOn"
      @click="togglePolarity"
    >
      <span class="lp-switch" :class="{ 'is-on': polarityOn }">
        <span class="lp-knob"></span>
      </span>
      <span class="lp-text">
        <span class="lp-label">Polarity</span>
        <span class="lp-hint">Color the field lines by magnetic direction</span>
      </span>
    </button>

    <div class="lp-group" role="radiogroup" aria-label="Surface">
      <span class="lp-group-label">Surface</span>
      <div class="lp-segments">
        <button
          v-for="option in surfaces"
          :key="option.key"
          type="button"
          class="lp-segment"
          :class="{ 'is-on': surfaceKey === option.key }"
          role="radio"
          :aria-checked="surfaceKey === option.key"
          @click="pickSurface(option.key)"
        >{{ option.label }}</button>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent } from "vue";

import { product } from "../data/sdoCatalog";
import {
  LayerFlags,
  TextureChannel,
  fieldColorMode,
  layers,
  surfaceMode,
  textureChannel,
} from "../state/useAppState";

interface Row {
  key: keyof LayerFlags;
  label: string;
  hint: string;
}

/**
 * One row of the Surface control. A channel entry paints that AIA wavelength
 * from the pipeline's Carrington map; "artist" is the synthetic surface.
 * Collapsing "which channel" and "real vs stylized" into one control is
 * deliberate — they are the same question to a guest ("what am I looking at"),
 * and two segmented controls in a phone popover is one too many.
 */
type SurfaceKey = TextureChannel | "artist";

interface SurfaceOption {
  key: SurfaceKey;
  label: string;
}

// Ordered by how much each one changes the picture, most first.
const ROWS: Row[] = [
  { key: "fieldLines", label: "Magnetic field", hint: "The Sun's field lines, last 72 hours" },
  { key: "wind", label: "Solar wind", hint: "Particles streaming out along the open lines" },
  { key: "spacecraft", label: "Spacecraft", hint: "Parker Solar Probe and Solar Orbiter" },
  { key: "orbits", label: "Planet orbits", hint: "Rings showing where the planets travel" },
  { key: "glow", label: "Corona glow", hint: "Soft halo around the Sun" },
];

// "Live SDO" is the default and falls back to "Artist" on its own while no
// texture has been published, so the guest never lands on an empty option.
//
// The engine's own flat Sun ("wwt") is deliberately NOT offered: it is a static
// texture that never changes and reads as a worse version of "Artist". The mode
// still exists in SurfaceMode because sunSurface uses it internally — in that
// mode the sphere renders depth-only, and it is the authoritative occluder for
// far-side field lines (CLAUDE.md footgun 18), so it must not be deleted.
/**
 * The five published channels, plus the synthetic surface.
 *
 * Labels come from `sdoCatalog` rather than being written again here: the
 * texture channel codes ARE that catalog's product ids, so one table names
 * every SDO product in the app and the two can never drift apart.
 */
const TEXTURE_CHANNELS: TextureChannel[] = ["HMIIC", "0304", "0171", "0193", "HMIB"];

const SURFACES: SurfaceOption[] = [
  ...TEXTURE_CHANNELS.map((key) => ({ key, label: product(key).label })),
  { key: "artist" as const, label: "Artist" },
];

/**
 * Plain switches, deliberately not Vuetify's: this popover has to sit inside the
 * app's own CSS-variable scope (a teleported overlay loses the --sol-* tokens)
 * and every target has to clear 44 px on a phone held one-handed.
 */
export default defineComponent({
  name: "LayerPanel",

  setup() {
    return { layers, surfaceMode, fieldColorMode, textureChannel };
  },

  computed: {
    rows(): Row[] {
      return ROWS;
    },

    surfaces(): SurfaceOption[] {
      return SURFACES;
    },

    /** The switch is on when the polarity palette is in use. */
    polarityOn(): boolean {
      return this.fieldColorMode === "polarity";
    },

    /** Which segment reads as selected. "sdo" is shown as its channel. */
    surfaceKey(): SurfaceKey {
      return this.surfaceMode === "sdo" ? this.textureChannel : "artist";
    },

  },

  methods: {
    toggle(key: keyof LayerFlags): void {
      this.layers[key] = !this.layers[key];
    },

    pickSurface(key: SurfaceKey): void {
      if (key === "artist") {
        this.surfaceMode = "synthetic";
        return;
      }
      this.textureChannel = key;
      this.surfaceMode = "sdo";
    },

    togglePolarity(): void {
      this.fieldColorMode = this.polarityOn ? "blue" : "polarity";
    },
  },
});
</script>

<style lang="less" scoped>
.layer-panel {
  display: flex;
  flex-direction: column;
  min-width: 15rem;
  padding: var(--sol-panel-pad);
  border: var(--sol-panel-border);
  border-radius: var(--sol-panel-radius);
  background: var(--sol-surface);
  box-shadow: var(--sol-panel-shadow);
}

.lp-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  min-height: 44px;
  padding: 0.3rem 0.5rem;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: var(--sol-text);
  text-align: left;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;

  &:active {
    background: rgba(255, 255, 255, 0.06);
  }
}

.lp-switch {
  flex: 0 0 auto;
  position: relative;
  width: 34px;
  height: 20px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.16);
  transition: background 160ms ease;

  &.is-on {
    background: rgba(255, 200, 80, 0.55);
  }
}

.lp-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #f5efe2;
  transition: transform 160ms ease;

  .is-on & {
    transform: translateX(14px);
  }
}

.lp-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.lp-label {
  font-size: 0.85rem;
  font-weight: 600;
}

.lp-hint {
  color: var(--sol-text-dim);
  font-size: 0.68rem;
  line-height: 1.25;
}

.lp-group {
  padding: 0.35rem 0.5rem 0.4rem;
  border-top: 1px solid rgba(255, 255, 255, 0.09);
  margin-top: 0.2rem;
}

.lp-group-label {
  display: block;
  margin-bottom: 0.3rem;
  font-size: 0.85rem;
  font-weight: 600;
}

.lp-segments {
  display: flex;
  gap: 0.25rem;
}

// 44 px tall, as everywhere else in this panel: a one-handed guest gets the
// same target here as on the switches above.
.lp-segment {
  flex: 1 1 0;
  min-height: 44px;
  padding: 0 0.2rem;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 9px;
  background: transparent;
  color: var(--sol-text-dim);
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;

  &.is-on {
    border-color: var(--sol-accent);
    background: rgba(255, 200, 80, 0.16);
    color: var(--sol-text);
  }
}
</style>
