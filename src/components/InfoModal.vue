<template>
  <!-- Hand-rolled rather than v-dialog: this sheet has to sit under the same
       CSS-variable scope as the rest of the app (a teleported Vuetify overlay
       loses --sol-* tokens), and it needs to scroll on a short phone. -->
  <component
    :is="inline ? 'section' : 'div'"
    :class="inline ? 'im-inline' : 'modal im-backdrop'"
    @click.self="inline || $emit('close')"
  >
    <div
      class="im-panel"
      :role="inline ? undefined : 'dialog'"
      :aria-modal="inline ? undefined : 'true'"
      aria-label="About Sol"
    >
      <!-- No close button inline: on a desktop rail this is a permanent
           column, not something the guest opened and has to dismiss. -->
      <button
        v-if="!inline"
        type="button"
        class="im-close close-icon"
        aria-label="Close"
        @click="$emit('close')"
      >
        <font-awesome-icon icon="times" />
      </button>

      <h2 class="im-title">What am I looking at?</h2>

      <!-- Guest copy. Plain sentences, one idea each, in the voice of a
           docent standing next to the screen. Say what a thing IS before
           saying what it means, and name a caveat (the far side, the DONKI
           catalog) in the same tone as everything else rather than in a
           footnote. -->
      <p class="im-body">
        The Sun, as it looks today. The pictures come from NASA's Solar
        Dynamics Observatory, a satellite that has photographed the Sun every
        few seconds since 2010. We wrap its newest images around a globe you
        can spin, and the timeline lets you roll the last three days back and
        forth.
      </p>

      <p class="im-body">
        Each surface is the Sun in a different color of light. Each color comes
        from gas at a different temperature, so picking a surface picks how deep
        into the Sun's atmosphere you are looking.
      </p>

      <h3 class="im-subtitle">Six ways to see the Sun</h3>
      <ul class="im-list">
        <li><strong>Visible Sun</strong> is the Sun in ordinary light. The dark specks are sunspots. Some are bigger than Earth.</li>
        <li><strong>Chromosphere</strong> is the thin layer just above the surface. Look along the edge for prominences, arcs of gas held up by magnetism.</li>
        <li><strong>Coronal Loops</strong> shows ultraviolet light from gas caught along the Sun's magnetic field. The loops trace the field itself.</li>
        <li><strong>Hot Corona</strong> is the outer atmosphere, at over a million degrees. The dark patches are coronal holes, where the solar wind escapes.</li>
        <li><strong>Magnetic Map</strong> shows the magnetic field at the surface. Light patches point one way and dark patches the other. The field lines you can turn on grow out of these.</li>
        <li><strong>Artist</strong> is a drawing, not a photograph. It makes the shape of the magnetic model easier to see.</li>
      </ul>

      <!-- Say this plainly rather than let a photorealistic globe imply more
           than it should: this app's culture is to state data-provenance
           caveats in guest copy rather than let a confident-looking picture
           speak for itself. -->
      <p class="im-body">
        SDO can only photograph the side of the Sun that faces Earth. Spin the
        globe around and the far side is filled in, not photographed: a quiet
        invented texture for the three ultraviolet views, and plain gray for
        Visible Sun and Magnetic Map.
      </p>

      <h3 class="im-subtitle">How to use it</h3>
      <ul class="im-list">
        <li><strong>Drag</strong> to spin the Sun. <strong>Pinch</strong> to zoom in on a sunspot, or out until the inner planets come into view.</li>
        <li><strong>Surface</strong> picks which picture is painted on the globe.</li>
        <li><strong>Magnetic field</strong> draws the Sun's field lines from a model we run on the last three days of magnetic maps. <strong>Polarity</strong> colors them by direction. Off, they are all one blue.</li>
        <li><strong>Spacecraft</strong> and <strong>Planet orbits</strong> show where Parker Solar Probe, Solar Orbiter and the planets are right now. Tap a label to read about it.</li>
        <li>The <strong>numbered labels</strong> on the disk are active regions, the sunspot groups NOAA is tracking. Tap one for details.</li>
        <li>The <strong>timeline</strong> runs back three days. The marks on it are flares and coronal mass ejections. Tap one to jump to it.</li>
        <li>The <strong>numbers</strong> are live space weather from NOAA. Tap one to see what it means.</li>
      </ul>

      <p class="im-fine">
        The flare and CME marks come from NASA's DONKI catalog, which is a
        research database and not an official forecast. For the forecast, see
        NOAA's Space Weather Prediction Center below.
      </p>

      <!-- Real links: on a phone they go to the source, and on the lobby
           touchscreen installKioskGuards() intercepts every one of them and
           shows a QR code instead of navigating the exhibit away. -->
      <h3 class="im-subtitle">Where the data comes from</h3>
      <ul class="im-list im-credits">
        <li>
          <a href="https://sdo.gsfc.nasa.gov/" target="_blank" rel="noopener"><strong>NASA SDO</strong></a>
          took every picture on the globe: ultraviolet from its AIA telescopes,
          visible light and magnetism from HMI.
        </li>
        <li>
          <a href="https://ccmc.gsfc.nasa.gov/tools/DONKI/" target="_blank" rel="noopener"><strong>NASA CCMC DONKI</strong></a>
          is the catalog of flares and CMEs behind the timeline marks.
        </li>
        <li>
          <a href="https://www.swpc.noaa.gov/" target="_blank" rel="noopener"><strong>NOAA Space Weather Prediction Center</strong></a>
          issues the official space-weather forecast and supplies the live numbers.
        </li>
        <li>
          <a href="https://gong.nso.edu/" target="_blank" rel="noopener"><strong>GONG / NSO</strong></a>
          measures the surface magnetic field our field-line model starts from.
        </li>
      </ul>

      <p class="im-fine">
        Never look at the Sun directly, with or without a telescope.
      </p>

      <p class="im-fine">Created by A. David Weigel.</p>

      <!-- The institutional lockup goes FIRST and stays one unit: the brand kit
           requires that the planetarium wordmark never appear without the USSRC
           logo, which is why these two are a single image and not two. See
           THIRD-PARTY.md. Below it, the toolkit credits get a row each. -->
      <div class="im-logos">
        <a
          class="im-logo-link"
          href="https://www.rocketcenter.com/INTUITIVEPlanetarium"
          target="_blank"
          rel="noopener"
          aria-label="INTUITIVE Planetarium at the U.S. Space &amp; Rocket Center"
        >
          <img
            class="im-logo im-logo-ip"
            src="../assets/ip-ussrc.png"
            alt="INTUITIVE Planetarium at the U.S. Space &amp; Rocket Center"
          >
        </a>

        <a
          class="im-attr"
          href="https://www.cosmicds.cfa.harvard.edu/"
          target="_blank"
          rel="noopener"
        >
          <img class="im-attr-mark" src="../assets/logo_cosmicds.png" alt="CosmicDS">
          <span>Interactive developed using the CosmicDS toolkit</span>
        </a>

        <a
          class="im-attr"
          href="https://worldwidetelescope.org/"
          target="_blank"
          rel="noopener"
        >
          <img class="im-attr-mark" src="../assets/logo_wwt.png" alt="WorldWide Telescope">
          <span>Powered by WorldWide Telescope</span>
        </a>
      </div>
    </div>
  </component>
</template>

<script lang="ts">
import { defineComponent } from "vue";

export default defineComponent({
  name: "InfoModal",

  props: {
    /**
     * Render as a permanent column instead of an overlay. Used by the desktop
     * rail, where there is room to keep this open and no sense in making the
     * guest dismiss it.
     */
    inline: {
      type: Boolean,
      default: false,
    },
  },

  emits: ["close"],
});
</script>

<style lang="less" scoped>
.im-backdrop {
  z-index: 60;
  padding: 1rem;
  align-items: flex-start;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

// The rail column: this is the one that scrolls, so the layers and stats
// below it keep their place no matter how long the copy gets.
// The rail's scrolling column. `height: 100%` plus `min-height: 0` on BOTH
// the container and the panel is what actually lets an internally-scrolling
// flex item exist — without the min-height:0 the panel's content sets a floor
// on its size, it grows past the grid row, and it clipped mid-sentence with no
// scrollbar while the layers panel below drew over the top of it.
.im-inline {
  display: flex;
  height: 100%;
  min-height: 0;
  overflow: hidden;

  .im-panel {
    flex: 1 1 auto;
    min-height: 0;
    // Fill the rail column: `width: min(100%, 32rem)` is a modal constraint,
    // and in a 35% column it made this panel narrower than its neighbors.
    width: 100%;
    max-width: none;
    margin: 0;
    overflow-y: auto;
    // -webkit-overflow-scrolling for momentum on touch laptops/tablets that
    // land in the wide layout.
    -webkit-overflow-scrolling: touch;
  }
}

.im-panel {
  position: relative;
  width: min(100%, 32rem);
  margin: auto;
  padding: var(--sol-panel-pad);
  border: var(--sol-panel-border);
  border-radius: var(--sol-panel-radius);
  background: var(--sol-surface);
  color: var(--sol-text);
  box-shadow: var(--sol-panel-shadow);
}

.im-close {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--sol-text-dim);
  font-size: 1.1rem;
  cursor: pointer;
}

.im-title {
  margin: 0 2.5rem 0.7rem 0;
  // Headings were gold throughout this panel. The Overpass display face and the
  // size step already say "heading"; a hue on top of that was decoration, and
  // gold-on-deep is the pairing the palette note in sol.less warns about.
  color: var(--sol-text);
  font-family: "Overpass", system-ui, sans-serif;
  font-weight: 600;
  font-size: 1.4rem;
  font-weight: 400;
}

.im-subtitle {
  margin: 1.1rem 0 0.4rem;
  color: var(--sol-text);
  font-size: 0.95rem;
  font-weight: 700;
}

.im-body {
  margin: 0 0 0.7rem;
  font-size: 0.88rem;
  line-height: 1.45;
}

.im-list {
  margin: 0;
  padding-left: 1.1rem;
  font-size: 0.85rem;
  line-height: 1.5;

  li {
    margin-bottom: 0.3rem;
  }

  strong {
    color: var(--sol-text);
  }
}

.im-credits {
  color: var(--sol-text-dim);
}

.im-fine {
  margin: 1rem 0 0;
  color: var(--sol-text-dim);
  font-size: 0.75rem;
  font-style: italic;
}

.im-logos {
  display: flex;
  /* A column now: the institutional lockup on its own line, then one credit
     row per toolkit. Side by side, a 22px mark next to a 160px lockup reads as
     a sizing mistake rather than a hierarchy. */
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  margin-top: 1.1rem;
  padding-top: 0.9rem;
  border-top: 1px solid var(--sol-hairline);
}

.im-logo {
  display: block;
  height: auto;
  opacity: 0.85;
}

.im-logo-link {
  display: block;
  border-radius: 4px;

  &:focus-visible {
    outline: 2px solid var(--sol-select);
    outline-offset: 2px;
  }
}

.im-logo-ip {
  max-width: 10rem;
}

/* The two toolkit credits: a small mark and a caption, on one tappable row.
   The WWT emblem used to sit here alone as a bare 64x64 <img> with no link and
   a `max-width: 6rem` that was NEVER BINDING (96px against a 64px intrinsic),
   so it rendered full size -- a chunky square with more visual weight than the
   institutional lockup above it, and the only mark in the app you could not
   click. Both marks are now height-constrained to the caption's line, which is
   what actually makes them small. */
.im-attr {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  /* 44px keeps each row a real touch target on a phone. */
  min-height: 44px;
  color: var(--sol-text-dim);
  font-size: 0.78rem;
  line-height: 1.3;
  text-decoration: none;
  transition: color 0.16s ease;
}

.im-attr:hover,
.im-attr:focus-visible {
  color: var(--sol-text);
  text-decoration: none;
}

.im-attr-mark {
  flex: 0 0 auto;
  /* Height, not max-width: these marks have different aspect ratios (the WWT
     orb is square, the CosmicDS spiral is not), and matching their HEIGHT is
     what makes them read as one row rather than two sizes. */
  height: 22px;
  width: auto;
  opacity: 0.9;
}
</style>
