<template>
  <v-app id="app">
    <div id="main-content">
      <div class="sol-root" :class="{ 'is-wide': wide, 'is-kiosk': kioskMode }">
        <top-bar class="sol-area-top" @info="sheet = 'info'" />

        <main class="sol-area-stage">
          <!-- The whole app. Async because the WWT engine + three.js live only
               in this chunk, and its module scope installs wwtPinia on the app
               instance stashed by setAppHandle() below — main.ts must never
               import the engine (CLAUDE.md "Entry chunk must stay
               engine-free"). Mounted immediately now that there is nothing
               else to look at; never unmounted, because tearing down
               <WorldWideTelescope> leaves the engine's global texture caches
               pointing at a destroyed GL context and the Sun comes back black
               (footgun 17). -->
          <solar-view-3d />

          <brand-mark class="sol-brand" />
        </main>

        <!-- Desktop rail. On a phone these are overlays the guest opens from
             a button (see SolarView3D / TopBar); here there is room to leave
             them open, so the buttons that would duplicate them are hidden. -->
        <info-modal v-if="wide" inline class="sol-area-info" />
        <layer-panel v-if="wide" class="sol-area-layers" />

        <sun-stats class="sol-area-stats" :layout="wide ? 'two' : 'auto'" />
      </div>

      <info-modal v-if="!wide && sheet === 'info'" @close="sheet = null" />

      <!-- Kiosk only. Bottom right, inside the strip `.sol-root.is-kiosk`
           reserves, so the pill can never cover the stats bar (portrait) or
           the right-hand rail and the 3D scrubber (landscape). -->
      <button
        v-if="kioskMode"
        type="button"
        class="sol-take-home"
        @click="showTakeHomeQr"
      >
        <font-awesome-icon icon="qrcode" />
        <span>Take it with you</span>
      </button>

      <p v-if="attractActive" class="sol-attract-hint" aria-hidden="true">
        Touch to explore
      </p>

      <!-- Async so qrcode.vue stays out of the entry chunk: only a kiosk guest
           tapping the pill (or an intercepted credit link) ever needs it. -->
      <kiosk-qr-modal v-if="qrUrl" :url="qrUrl" :title="qrTitle" @close="closeQr" />
    </div>
  </v-app>
</template>

<script lang="ts">
import { defineAsyncComponent, defineComponent, getCurrentInstance, h } from "vue";

import BrandMark from "./components/BrandMark.vue";
import InfoModal from "./components/InfoModal.vue";
import LayerPanel from "./components/LayerPanel.vue";
import SunStats from "./components/SunStats.vue";
import TopBar from "./components/TopBar.vue";
import { attractActive, initAttract, stopAttract } from "./kiosk/attract";
import { KIOSK_RELOAD_HOUR, installKioskGuards, scheduleDailyReload } from "./kiosk/kiosk";
import { statsTrack } from "./kiosk/kioskStats";
import { takeHomeUrl } from "./kiosk/takeHome";
import { kiosk, setAppHandle, sheet, textureChannel, wide } from "./state/useAppState";
import { initDeepLink } from "./state/useDeepLink";

/** Above this width the stage moves left and the controls become a right rail. */
const WIDE_QUERY = "(min-width: 900px)";

/** Give up on the 3D chunk after this long (a dead network, not a slow one). */
const CHUNK_TIMEOUT_MS = 30000;

// Placeholders for the async 3D chunk. Render functions rather than SFCs so
// they add nothing to the entry bundle; the classes live in assets/sol.less
// (global) because a render function gets no scoped-style attribute.
const chunkLoading = defineComponent({
  name: "SolarView3DLoading",
  render() {
    return h("div", { class: "sol-3d-placeholder no-select" }, [
      h("div", { class: "sol-spinner" }),
      h("p", { class: "sol-3d-text" }, "3D view coming online…"),
    ]);
  },
});

const chunkFailed = defineComponent({
  name: "SolarView3DFailed",
  render() {
    return h("div", { class: "sol-3d-placeholder no-select" }, [
      h("p", { class: "sol-3d-text" },
        "The 3D view couldn't load. Sun Now and the live numbers still work."),
    ]);
  },
});

/**
 * The WWT engine (~330 KB gz) and three.js live ONLY in this chunk, and the
 * chunk's module scope installs wwtPinia on the app instance stashed by
 * setAppHandle() below. Keeping main.ts engine-free is the whole reason the
 * disk view paints in well under a second on a phone.
 */
const solarView3d = defineAsyncComponent({
  loader: () => import(/* webpackChunkName: "solar3d" */ "./components/SolarView3D.vue"),
  loadingComponent: chunkLoading,
  errorComponent: chunkFailed,
  timeout: CHUNK_TIMEOUT_MS,
  delay: 0,
});

/**
 * The QR modal pulls in qrcode.vue, which only a lobby touchscreen ever shows
 * — so it gets its own chunk rather than a place in the entry bundle every
 * phone guest downloads. Local fetch on a kiosk: no placeholder needed.
 */
const kioskQrModal = defineAsyncComponent(
  () => import(/* webpackChunkName: "kioskqr" */ "./components/KioskQrModal.vue"),
);

/**
 * Root hub. Deliberately thin: every panel owns its own data and reads shared
 * knobs straight from src/state/useAppState.ts, so this file stays a layout.
 */
export default defineComponent({
  name: "SolApp",

  components: {
    "brand-mark": BrandMark,
    "info-modal": InfoModal,
    "kiosk-qr-modal": kioskQrModal,
    "layer-panel": LayerPanel,
    "solar-view-3d": solarView3d,
    "sun-stats": SunStats,
    "top-bar": TopBar,
  },

  props: {
    kioskMode: {
      type: Boolean,
      default: false,
    },
    kioskHomeUrl: {
      type: String,
      default: "",
    },
  },

  setup() {
    // Read the incoming QR/deep link before the first render, then keep the
    // URL in step with the state (replaceState, debounced).
    initDeepLink();
    return { attractActive, sheet, wide };
  },

  data() {
    return {
      mediaQuery: null as MediaQueryList | null,



      // Kiosk: the QR modal is open exactly while qrUrl is non-empty.
      qrUrl: "",
      qrTitle: "",
      kioskCleanups: [] as (() => void)[],
    };
  },

  watch: {
    // The attract loop starting means nobody is standing here — so a QR left
    // open by the last guest shouldn't sit over the top of it.
    attractActive(active: boolean) {
      if (active) { this.closeQr(); }
    },

  },

  mounted() {
    // Stash the app instance for the 3D milestone's async loader (it needs
    // app.use(wwtPinia) / app.component(...) after mount, because main.ts must
    // not pull the WWT engine into the entry chunk).
    const instance = getCurrentInstance();
    if (instance) { setAppHandle(instance.appContext.app); }

    // main.ts derives the prop from ?kiosk=1; keep the shared flag in step so
    // components that only see the state module (e.g. DiskMovie's autoplay)
    // agree with the prop.
    if (this.kioskMode) {
      kiosk.value = true;
      this.installKiosk();
    }

    this.mediaQuery = window.matchMedia(WIDE_QUERY);
    wide.value = this.mediaQuery.matches;
    this.mediaQuery.addEventListener("change", this.onWideChange);
  },

  beforeUnmount() {
    if (this.mediaQuery) {
      this.mediaQuery.removeEventListener("change", this.onWideChange);
    }
    this.kioskCleanups.forEach((off) => off());
    this.kioskCleanups = [];
  },

  methods: {
    onWideChange(event: MediaQueryListEvent): void {
      wide.value = event.matches;
    },

    // --- kiosk (lobby touchscreen) ----------------------------------------

    /**
     * Everything ?kiosk=1 turns on. Installed synchronously at mount so the
     * exhibit is locked down before the first image has even loaded; every
     * piece hands back a teardown, because dev HMR remounts this component and
     * stacked listeners/intervals were the M-W7 bug waiting to happen.
     */
    installKiosk(): void {
      // No navigation, ever: an external link (the credits in InfoModal)
      // becomes a QR the guest scans instead. Also kills the context menu,
      // page pinch-zoom and pull-to-refresh.
      this.kioskCleanups.push(installKioskGuards({
        onExternalLink: (url, title) => this.showQr(url, title, url),
      }));

      // 3 am maintenance reload — but only while the attract loop is running,
      // so no guest ever watches the exhibit blink. Sheds WWT's tile cache
      // over a multi-day run.
      this.kioskCleanups.push(scheduleDailyReload(
        KIOSK_RELOAD_HOUR,
        () => this.attractActive,
      ));

      // Idle → attract loop, plus the anonymous local usage stats.
      initAttract();
      this.kioskCleanups.push(stopAttract);

      window.addEventListener("keydown", this.onKioskKeydown);
      this.kioskCleanups.push(() => window.removeEventListener("keydown", this.onKioskKeydown));
    },

    /** `detail` is what the stats rollup counts this QR under. */
    showQr(url: string, title: string, detail: string): void {
      this.qrUrl = url;
      this.qrTitle = title || "Scan to visit";
      this.sheet = null;
      statsTrack("qr", detail);
    },

    closeQr(): void {
      this.qrUrl = "";
    },

    /**
     * The take-home pill: a QR of exactly what's on the screen right now, so
     * the guest's phone opens the Sun painted the way the lobby screen had it
     * (M-W7 / "Dome to Phone"). Counted by channel, which is the interesting
     * question.
     */
    showTakeHomeQr(): void {
      const url = takeHomeUrl(this.kioskHomeUrl, textureChannel.value);
      this.showQr(url, "Take it with you", textureChannel.value);
      statsTrack("takeHome");
    },

    /** Escape closes the QR modal — the only global key this app binds. */
    onKioskKeydown(event: KeyboardEvent): void {
      if (event.key === "Escape" && this.qrUrl) { this.closeQr(); }
    },
  },
});
</script>

<style lang="less" scoped>
.sol-root {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--sol-bg);
  color: var(--sol-text);
  -webkit-tap-highlight-color: transparent;
  user-select: none;
  padding-bottom: env(safe-area-inset-bottom);
}

.sol-area-top,
.sol-area-stats {
  flex: 0 0 auto;
}

// The Sun gets every pixel the chrome doesn't need.
.sol-area-stage {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
}

// TOP-left of the stage. It started bottom-left and was invisible: the 3D
// view is `position: relative` with `z-index: auto`, so it creates NO stacking
// context and its descendants compete directly with this sibling — the time
// scrubber (z-index 5) and its play button simply painted over the top of a
// z-index 3 mark sitting in the same corner.
//
// Top-left is genuinely free (the reset button owns top-right, the scrubber the
// whole bottom edge), and the z-index clears everything the 3D view uses except
// the card slot at 20, which is a deliberate modal-ish overlay.
.sol-brand {
  top: 0.75rem;
  left: 0.75rem;
  z-index: 6;
}

.sol-area-stage > * {
  flex: 1 1 auto;
  min-height: 0;
}

// --- kiosk (lobby touchscreen) -------------------------------------------
// Reserve a strip along the bottom of the app for the take-home pill. Cheaper
// and far more robust than trying to dodge whatever is currently down there:
// the strip shortens the layout box itself, so in BOTH layouts (portrait flex
// column, landscape grid) the stats bar and the 3D scrubber end above it.
.sol-root.is-kiosk {
  padding-bottom: calc(env(safe-area-inset-bottom) + 3.2rem);
}

.sol-take-home {
  position: absolute;
  right: 0.75rem;
  bottom: calc(env(safe-area-inset-bottom) + 0.45rem);
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 0.55rem;
  // Thumb-sized: this is the one control every guest is invited to press.
  min-height: 48px;
  padding: 0.5rem 1.15rem;
  border: 1px solid rgba(255, 200, 80, 0.55);
  border-radius: 999px;
  background: var(--sol-surface);
  color: var(--sol-accent);
  font-size: 1rem;
  font-weight: 700;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

// "Still here?" prompt while the attract loop runs. Shares the reserved strip
// with the pill, so it needs the room a lobby screen has — hidden on a narrow
// one, where the two would touch.
.sol-attract-hint {
  display: none;
}

@media (min-width: 600px) {
  .sol-attract-hint {
    display: block;
    position: absolute;
    left: 0.75rem;
    bottom: calc(env(safe-area-inset-bottom) + 0.45rem);
    z-index: 30;
    margin: 0;
    padding: 0.7rem 1.2rem;
    border: 1px solid rgba(255, 200, 80, 0.35);
    border-radius: 999px;
    background: var(--sol-surface);
    color: var(--sol-text);
    font-size: 1rem;
    font-weight: 600;
    pointer-events: none;
  }
}

@media (min-width: 600px) and (prefers-reduced-motion: no-preference) {
  .sol-attract-hint {
    animation: sol-attract-pulse 2.4s ease-in-out infinite;
  }
}

@keyframes sol-attract-pulse {
  0%, 100% { opacity: 0.65; }
  50% { opacity: 1; }
}

// --- landscape / desktop -------------------------------------------------
// Stage on the left at ~65%, everything else in a rail on the right. Same
// components, same state — only the boxes move.
// Each rail occupant gets its own grid row so nothing can overlap; the stage
// spans all three of them.
.sol-root.is-wide {
  display: grid;
  grid-template-columns: 65fr 35fr;
  // Two rows, matching grid-template-areas below. These MUST stay the same
  // length: leaving four row sizes here against a two-row area map put the
  // stage in an `auto` row, and the 3D canvas has no intrinsic height, so it
  // collapsed to nothing.
  // info takes the slack and scrolls; layers and stats keep their height.
  grid-template-rows: auto 1fr auto auto;
  // One view now, so the right-hand rail carries only the stats. The Sun
  // spans the full height beside them rather than sharing the column with a
  // view switcher and disk controls that no longer exist.
  grid-template-areas:
    "top    top"
    "stage  info"
    "stage  layers"
    "stage  stats";
  column-gap: 0.5rem;
  // Spacing between the rail's panels comes from the grid, so all three gaps
  // are the same by construction rather than by three components agreeing.
  row-gap: var(--sol-rail-gutter);

  .sol-area-top {
    grid-area: top;
  }

  .sol-area-stage {
    grid-area: stage;
    min-width: 0;
  }

  // One gutter, one width, one rhythm. Each of these components can also
  // appear as a phone overlay, where they size themselves — so the rail sets
  // the geometry here rather than any of them assuming it.
  .sol-area-info,
  .sol-area-layers,
  .sol-area-stats {
    padding-right: var(--sol-rail-gutter);
    padding-left: var(--sol-rail-gutter);
  }

  .sol-area-info {
    grid-area: info;
    // Load-bearing: without it the info panel's content sets a floor on this
    // grid item's height and the 1fr row stops constraining anything.
    min-height: 0;
  }

  .sol-area-layers {
    grid-area: layers;
    align-self: start;
  }

  .sol-area-stats {
    grid-area: stats;
    align-self: end;
    padding-bottom: var(--sol-rail-gutter);

    // SunStats carries its own gutter for the phone layout; the rail owns it
    // here, so the two must not add up to a wider inset than its neighbours.
    :deep(.sun-stats) {
      padding-right: 0;
      padding-left: 0;
    }
  }
}
</style>
