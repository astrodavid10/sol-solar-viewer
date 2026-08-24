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
      <!-- A SECTION HEADER, not another row label.
           It used to be `font-size: 0.85rem; font-weight: 600` -- byte for byte
           the same as `.lp-label` on the switch rows -- while sitting 43.6 px to
           their LEFT, because a row's label starts after the 34 px switch and
           its 0.6 rem gap (0.5rem + 34px + 0.6rem = 51.6 px) and this one
           started at the bare 0.5 rem = 8 px. Identical styling at a different
           indent is the worst of both readings: it looks like a peer of the
           rows and lines up with nothing.
           `.sol-section-head` is the global class (src/assets/sol.less) that
           carries the brand kit's own convention for this -- letterspaced caps
           over a thin rule -- so it now reads unmistakably as a heading, and it
           matches every other section heading in the app rather than being
           this component's private invention. -->
      <span class="sol-section-head">Surface</span>
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
// `min-height: 0` is cheap insurance in the spirit of footgun 28: the
// wrapper this panel sits in now caps its own height with `max-height` +
// `overflow-y: auto` (`.sv-layer-popover`, SolarView3D.vue -- E4), a hard
// length rather than a flexible track share, so the cap holds regardless of
// this flex column's own content height. Kept anyway so this panel matches
// the rest of the codebase's scrollable-panel pattern, in case that wrapper
// is ever changed to a flexible (`1fr`/`flex: 1`) allocation instead.
.layer-panel {
  display: flex;
  flex-direction: column;
  min-width: 15rem;
  min-height: 0;
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
    background: var(--sol-hover);
  }

  // Keyboard focus was invisible here: the rows have `border: none` and no
  // outline rule, so tabbing through the panel gave no indication of position.
  &:focus-visible {
    outline: 2px solid var(--sol-select);
    outline-offset: -2px;
  }
}

.lp-switch {
  flex: 0 0 auto;
  position: relative;
  width: 34px;
  height: 20px;
  border-radius: 999px;
  // Off, but VISIBLE: at --sol-hairline's 0.16 the track measured 1.24:1
  // against the panel, i.e. very nearly invisible -- a switch you cannot see
  // until you turn it on. 0.28 brings it to 1.56:1, which reads as a track.
  background: rgba(148, 155, 175, 0.28);
  transition: background 160ms ease;

  // "On" is a brand NEUTRAL, not gold. A gold switch sat inches from gold
  // closed-field lines meaning something entirely different -- and gold on a
  // deep ground is the exact pairing that read as LSU. See the palette note in
  // src/assets/sol.less.
  //
  // 0.55, not the 0.42 first tried: measured, 0.42 gave only a 2.88:1 change
  // between on and off, under the 3.0 a state change needs to be unmistakable.
  // 0.55 gives 3.45:1. Higher would be clearer still, but the track then
  // approaches the white knob and the knob is what says WHICH way the switch
  // is thrown -- at 0.55 the knob still holds 3.29:1 against the lit track, and
  // its dark ring below covers the rest.
  &.is-on {
    background: rgba(var(--sol-select-rgb), 0.55);
  }
}

.lp-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  // The knob rides ON the track, so a fill contrast of 3.29:1 against the lit
  // track is doing only half the work -- the dark ring is the other half, and
  // it measures 5.59:1 against that same track. Belt and braces, because the
  // knob's POSITION is the only thing that says which way the switch is thrown.
  background: var(--sol-text);
  box-shadow: 0 0 0 1px var(--sol-casing), 0 1px 2px rgba(0, 0, 0, 0.5);
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

// Same 0.5rem horizontal padding as `.lp-row`, so the group's left edge and
// the rows' left edges are the same line. The vertical padding used to be
// 0.35/0.4rem against the rows' 0.3rem -- three different numbers for one
// rhythm. One number now.
.lp-group {
  padding: 0.3rem 0.5rem;
  margin-top: 0.45rem;
}

.lp-segments {
  display: flex;
  // One row of six on the desktop rail; on a phone the popover is capped at
  // the viewport (SolarView3D's `.sv-layer-popover` max-width) and six
  // don't fit -- "Chromosphere" alone is ~72px of unbreakable text, so six
  // segments' min-content is 392px against ~272px of 320px-viewport popover.
  gap: 0.3rem;
  flex-wrap: wrap;
}


// 44 px tall, as everywhere else in this panel: a one-handed guest gets the
// same target here as on the switches above.
.lp-segment {
  flex: 1 1 0;
  min-height: 44px;
  padding: 0 0.2rem;
  border: 1px solid var(--sol-hairline);
  border-radius: 9px;
  background: transparent;
  color: var(--sol-text-dim);
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;

  &:focus-visible {
    outline: 2px solid var(--sol-select);
    outline-offset: -2px;
  }

  // Selected reads as "lit", not "gold": a brighter border, a faint neutral
  // fill and full-strength text. Three signals rather than one hue, so it
  // survives being seen by someone who cannot separate the hues at all.
  &.is-on {
    border-color: rgba(var(--sol-select-rgb), 0.75);
    background: rgba(var(--sol-select-rgb), 0.14);
    color: var(--sol-text);
  }
}

// Below the rail breakpoint (sol.vue's WIDE_QUERY, 900px) this renders only
// inside `.sv-layer-popover`, which is now capped at the viewport width
// (SolarView3D.vue) -- six segments' min-content is 392px, so they must wrap.
// Basis 30% forces an even 3+3 and `flex-grow: 1` fills each row; 30% of the
// 320px viewport's ~270px content box is ~81px, which holds "Chromosphere"
// (~72px of unbreakable text at 0.72rem). Without the wrap the row shrank
// every segment to 38px and clipped all six labels.
// MUST come after the `.lp-segment` rule above: its `flex: 1 1 0` shorthand
// resets flex-basis, and at equal specificity source order decides.
@media (max-width: 899px) {
  .lp-segment {
    flex-basis: 30%;
    min-width: 0;
  }
}
</style>
