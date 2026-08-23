<template>
  <div class="disk-controls no-select">
    <!-- PFSS overlay. Disabled (with a reason) rather than hidden: a control
         that vanishes as you switch channels is disorienting. -->
    <button
      type="button"
      class="dc-btn"
      :class="{ 'is-active': pfssActive }"
      :disabled="!info.hasPfss"
      :title="pfssTitle"
      :aria-pressed="pfssActive"
      @click="togglePfss"
    >
      <font-awesome-icon icon="layer-group" />
      <span>Magnetic overlay</span>
    </button>

    <button
      v-if="movieAvailable"
      type="button"
      class="dc-btn"
      :class="{ 'is-active': diskMode === 'movie' }"
      :aria-pressed="diskMode === 'movie'"
      @click="toggleMovie"
    >
      <font-awesome-icon :icon="diskMode === 'movie' ? 'pause' : 'play'" />
      <span>{{ movieLabel }}</span>
    </button>

    <button
      type="button"
      class="dc-btn dc-res"
      :disabled="diskMode === 'movie'"
      :title="resTitle"
      @click="cycleRes"
    >
      <span class="dc-res-value">{{ resText }}</span>
      <span class="dc-res-label">detail</span>
    </button>
  </div>
</template>

<script lang="ts">
import { defineComponent } from "vue";

import {
  DISK_RESOLUTIONS,
  DiskRes,
  Product,
  hasAnyMovie,
  product,
  resLabel,
} from "../data/sdoCatalog";
import { channel, diskMode, diskRes, pfssOverlay } from "../state/useAppState";

export default defineComponent({
  name: "DiskControls",

  setup() {
    return { channel, diskMode, diskRes, pfssOverlay };
  },

  computed: {
    info(): Product {
      return product(this.channel);
    },

    /**
     * The preference survives a hop to a channel with no overlay (so coming
     * back restores it) but the button reads honestly as off while it can't
     * apply. stillUrl() enforces the same rule on the URL side.
     */
    pfssActive(): boolean {
      return this.pfssOverlay && this.info.hasPfss;
    },

    pfssTitle(): string {
      if (!this.info.hasPfss) { return "Not published for this channel"; }
      return "Magnetic field lines, computed by NASA and drawn on the still image";
    },

    movieAvailable(): boolean {
      return hasAnyMovie(this.channel);
    },

    /** HMI channels have no rolling 48 h file — only the daily one. */
    movieLabel(): string {
      return this.info.hasLatestMovie ? "48h movie" : "24h movie";
    },

    resText(): string {
      return resLabel(this.diskRes);
    },

    resTitle(): string {
      if (this.diskMode === "movie") { return "Movies are 1024 px only"; }
      return `Still image detail — now ${this.diskRes} px across. Tap to change.`;
    },
  },

  methods: {
    togglePfss(): void {
      if (!this.info.hasPfss) { return; }
      this.pfssOverlay = !this.pfssOverlay;
    },

    toggleMovie(): void {
      this.diskMode = this.diskMode === "movie" ? "still" : "movie";
    },

    cycleRes(): void {
      const index = DISK_RESOLUTIONS.indexOf(this.diskRes);
      const next = DISK_RESOLUTIONS[(index + 1) % DISK_RESOLUTIONS.length];
      this.diskRes = next as DiskRes;
    },
  },
});
</script>

<style lang="less" scoped>
.disk-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 0.5rem;
  padding: 0.15rem 0.75rem 0.4rem;
}

// 44 px minimum on every target: this is a phone, held one-handed, possibly
// in the dark at the back of a planetarium.
.dc-btn {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  min-height: 44px;
  padding: 0 0.8rem;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--sol-text);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: border-color 150ms ease, color 150ms ease, background 150ms ease;

  &.is-active {
    border-color: var(--sol-accent);
    background: rgba(255, 200, 80, 0.12);
    color: var(--sol-accent);
  }

  &:disabled {
    opacity: 0.4;
    cursor: default;
  }
}

.dc-res {
  flex-direction: column;
  gap: 0;
  justify-content: center;
  min-width: 3.6rem;
}

.dc-res-value {
  font-size: 0.9rem;
  color: var(--sol-accent);
}

.dc-res-label {
  font-size: 0.6rem;
  font-weight: 400;
  color: var(--sol-text-dim);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
</style>
