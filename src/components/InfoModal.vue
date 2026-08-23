<template>
  <!-- Hand-rolled rather than v-dialog: this sheet has to sit under the same
       CSS-variable scope as the rest of the app (a teleported Vuetify overlay
       loses --sol-* tokens), and it needs to scroll on a short phone. -->
  <div class="modal im-backdrop" @click.self="$emit('close')">
    <div class="im-panel" role="dialog" aria-modal="true" aria-label="About Sol">
      <button
        type="button"
        class="im-close close-icon"
        aria-label="Close"
        @click="$emit('close')"
      >
        <font-awesome-icon icon="times" />
      </button>

      <h2 class="im-title">What am I looking at?</h2>

      <p class="im-body">
        This is the Sun as it is right now — the newest pictures NASA's Solar
        Dynamics Observatory has sent down, usually only a few minutes old. The
        spacecraft watches the Sun around the clock from orbit and takes a new
        image about every 15 seconds.
      </p>

      <p class="im-body">
        Each channel below the picture is a different colour of light, and each
        colour comes from gas at a different temperature — so switching channels
        is really switching altitude, from the visible surface all the way out
        into the million-degree corona.
      </p>

      <h3 class="im-subtitle">How to use it</h3>
      <ul class="im-list">
        <li><strong>Tap a channel</strong> to change what you're seeing (and how hot it is).</li>
        <li><strong>Pinch or double-tap</strong> the picture to zoom in on a sunspot or a loop.</li>
        <li><strong>Magnetic overlay</strong> draws NASA's computed field lines on top of the still.</li>
        <li><strong>48h movie</strong> plays the last two days — it's a big download, so the size is on the button.</li>
        <li>
          <strong>3D</strong> lifts the Sun off the page: its magnetic field in three dimensions.
          The half of the Sun facing away from Earth can't be photographed — in the 3D view
          it's an artist's fill.
        </li>
        <li>The <strong>numbers at the bottom</strong> are live space weather from NOAA. Tap one for a plain-English explanation.</li>
      </ul>

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
          <a href="https://www.swpc.noaa.gov/" target="_blank" rel="noopener"><strong>NOAA Space Weather Prediction Center</strong></a>
          — flares, solar wind, aurora forecast.
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

      <div class="im-logos">
        <img
          class="im-logo im-logo-ip"
          src="../assets/ip-ussrc.png"
          alt="INTUITIVE Planetarium at the U.S. Space &amp; Rocket Center"
        >
        <img
          class="im-logo im-logo-wwt"
          src="../assets/logo_wwt.png"
          alt="WorldWide Telescope"
        >
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent } from "vue";

export default defineComponent({
  name: "InfoModal",
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

.im-panel {
  position: relative;
  width: min(100%, 32rem);
  margin: auto;
  padding: 1.4rem 1.2rem 1.2rem;
  border: 1px solid rgba(255, 200, 80, 0.35);
  border-radius: 14px;
  background: var(--sol-surface);
  color: var(--sol-text);
  box-shadow: 0 0 30px rgba(0, 0, 0, 0.7);
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

.im-logo-ip {
  max-width: 10rem;
}

.im-logo-wwt {
  max-width: 6rem;
}
</style>
