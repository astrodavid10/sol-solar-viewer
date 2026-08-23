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

      <p class="im-body">
        This is the Sun as it is right now: real pictures from NASA's Solar
        Dynamics Observatory, wrapped around a 3D globe you can spin with a
        finger. SDO watches the Sun around the clock from orbit, so the picture
        on the globe is usually only a few minutes old.
      </p>

      <p class="im-body">
        Each surface below is a different colour of light, and each colour
        comes from gas at a different temperature — so switching surfaces is
        really switching altitude, from the visible photosphere all the way
        out into the million-degree corona.
      </p>

      <h3 class="im-subtitle">Six ways to see the Sun</h3>
      <ul class="im-list">
        <li><strong>Visible Sun</strong> — what your eyes would see (never look directly!). The dark freckles are sunspots.</li>
        <li><strong>Chromosphere</strong> — the thin layer just above the surface. Watch the edge for prominences, arcs of glowing gas bigger than Earth.</li>
        <li><strong>Coronal Loops</strong> — ultraviolet light tracing the Sun's own magnetic field.</li>
        <li><strong>Hot Corona</strong> — the outer atmosphere, millions of degrees, with dark coronal holes where the solar wind escapes.</li>
        <li><strong>Magnetic Map</strong> — light and dark show which way the magnetic field points. These are the roots of the field lines you can turn on below.</li>
        <li><strong>Artist</strong> — a stylised, illustrated Sun. Not a photograph of anything — just a clean way to see the model's shape.</li>
      </ul>

      <!-- Say this plainly rather than let a photorealistic globe imply more
           than it should: this app's culture is to state data-provenance
           caveats in guest copy rather than let a confident-looking picture
           speak for itself. -->
      <p class="im-body">
        SDO only ever sees the side of the Sun facing Earth. Spin the globe
        around and the far side is never a photograph: for Chromosphere,
        Coronal Loops and Hot Corona it's a stylised, quiet-looking fill; for
        Visible Sun and Magnetic Map it's just flat grey, with nothing invented.
      </p>

      <h3 class="im-subtitle">How to use it</h3>
      <ul class="im-list">
        <li><strong>Drag</strong> to spin the Sun, <strong>pinch</strong> to zoom in on a sunspot or a loop.</li>
        <li><strong>Surface</strong> switches which picture is painted on the globe — the six above.</li>
        <li>
          <strong>Magnetic field</strong> draws our own model of the Sun's field lines (a "PFSS" model,
          rebuilt from the last 72 hours of magnetic maps). <strong>Polarity</strong> colours them by
          which way the field points; switched off, they're all one electric blue.
        </li>
        <li>The <strong>timeline</strong> scrubs back through those same 72 hours. The marks on it are flares and CMEs — tap one to jump straight to it.</li>
        <li>The <strong>numbers at the bottom</strong> are live space weather from NOAA. Tap one for a plain-English explanation.</li>
      </ul>

      <p class="im-fine">
        The flare and CME marks come from NASA's DONKI catalogue — solid research
        data, but not an official forecast. NOAA's Space Weather Prediction
        Center (below) is the official source.
      </p>

      <!-- Real links: on a phone they go to the source, and on the lobby
           touchscreen installKioskGuards() intercepts every one of them and
           shows a QR code instead of navigating the exhibit away. -->
      <h3 class="im-subtitle">Where the data comes from</h3>
      <ul class="im-list im-credits">
        <li>
          <a href="https://sdo.gsfc.nasa.gov/" target="_blank" rel="noopener"><strong>NASA SDO</strong></a>
          — AIA (ultraviolet) and HMI (visible light and magnetism) imagery.
        </li>
        <li>
          <a href="https://ccmc.gsfc.nasa.gov/tools/DONKI/" target="_blank" rel="noopener"><strong>NASA CCMC DONKI</strong></a>
          — the flare and CME catalogue behind the timeline marks.
        </li>
        <li>
          <a href="https://www.swpc.noaa.gov/" target="_blank" rel="noopener"><strong>NOAA Space Weather Prediction Center</strong></a>
          — the official space-weather forecast, and the live numbers at the bottom of the screen.
        </li>
        <li>
          <a href="https://gong.nso.edu/" target="_blank" rel="noopener"><strong>GONG / NSO</strong></a>
          — the surface magnetic maps behind our field-line model.
        </li>
        <li>
          <a href="https://worldwidetelescope.org/" target="_blank" rel="noopener"><strong>WorldWide Telescope</strong></a>
          and
          <a href="https://www.cosmicds.cfa.harvard.edu/" target="_blank" rel="noopener"><strong>CosmicDS</strong></a>
          — the 3D engine and the data-story framework.
        </li>
      </ul>

      <p class="im-fine">
        Never look at the Sun directly, with or without a telescope.
      </p>

      <p class="im-fine">Created by A. David Weigel.</p>

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
        <img
          class="im-logo im-logo-wwt"
          src="../assets/logo_wwt.png"
          alt="WorldWide Telescope"
        >
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
.im-inline {
  display: flex;
  min-height: 0;
  overflow: hidden;

  .im-panel {
    // Fill the rail column: `width: min(100%, 32rem)` is a modal constraint,
    // and in a 35% column it made this panel narrower than its neighbours.
    width: 100%;
    max-width: none;
    max-height: 100%;
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
  color: var(--sol-accent);
  font-family: "Highway Gothic Narrow", "Roboto", sans-serif;
  font-size: 1.4rem;
  font-weight: 400;
}

.im-subtitle {
  margin: 1.1rem 0 0.4rem;
  color: var(--sol-accent);
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
  align-items: center;
  justify-content: center;
  gap: 1.2rem;
  margin-top: 1.1rem;
  padding-top: 0.9rem;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
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
    outline: 2px solid var(--sol-accent);
    outline-offset: 2px;
  }
}

.im-logo-ip {
  max-width: 10rem;
}

.im-logo-wwt {
  max-width: 6rem;
}
</style>
