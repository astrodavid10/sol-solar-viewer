<template>
  <div class="disk-viewer no-select">
    <!-- STILL MODE -->
    <div
      v-show="diskMode === 'still'"
      ref="stage"
      class="disk-stage"
      :class="{ 'is-gesturing': gesturing }"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @pointerleave="onPointerUp"
      @wheel.prevent="onWheel"
      @dragstart.prevent
    >
      <!-- Two stacked layers: the settled image and the one loading on top of
           it. The incoming layer fades in only once it has decoded, so a slow
           load never blanks the screen the guest is already looking at. -->
      <!-- Two nested transforms per layer: the OUTER div carries the guest's
           pinch/pan (transitioned, so double-tap zoom eases), the INNER img
           carries the per-channel disk normalization (NOT transitioned — an
           AIA↔HMI switch must be an instant fact about the new image, never
           an animated "bump"). Uniform scales compose commutatively and the
           outer translate stays in un-scaled px, so gesture math is unchanged. -->
      <div v-if="frontSrc" class="disk-layer" :style="userStyle">
        <img
          class="disk-img"
          :src="frontSrc"
          :alt="altText"
          :style="{ transform: `scale(${frontBase})` }"
          decoding="async"
          @load="onFrontLoad"
        >
      </div>
      <div
        v-if="backSrc"
        class="disk-layer disk-layer-incoming"
        :class="{ 'is-ready': backReady }"
        :style="userStyle"
      >
        <img
          class="disk-img"
          :src="backSrc"
          :alt="altText"
          :style="{ transform: `scale(${backBase})` }"
          decoding="async"
          @load="onBackLoad"
          @error="onBackError"
        >
      </div>

      <!-- First-load spinner (no image underneath yet) -->
      <div v-if="!frontSrc && loadState !== 'error'" class="disk-overlay">
        <div class="sol-spinner"></div>
        <p v-if="loadState === 'slow'" class="disk-overlay-text">
          NASA's server is being slow…
        </p>
      </div>

      <!-- Refreshing an image we already have: quiet corner note only -->
      <p v-else-if="loadState === 'slow'" class="disk-slow-note">
        <span class="sol-spinner sol-spinner-sm"></span>
        NASA's server is being slow…
      </p>

      <div v-if="loadState === 'error'" class="disk-error">
        <p class="disk-error-title">We can't reach NASA's image server right now</p>
        <p class="disk-error-body">The numbers below are still live.</p>
        <button type="button" class="disk-error-btn" @click="retryFromScratch">
          Try again
        </button>
      </div>
    </div>

    <!-- MOVIE MODE -->
    <disk-movie
      v-if="diskMode === 'movie'"
      class="disk-movie-slot"
      :product-id="channel"
      @exit="diskMode = 'still'"
    />

    <p class="disk-caption">
      <template v-if="diskMode === 'still'">
        Live from NASA SDO — new image about every 15 minutes<template v-if="loadedAt"> · loaded {{ loadedClock }}</template>
      </template>
      <template v-else>
        Movies are assembled by NASA SDO from thousands of images
      </template>
    </p>
  </div>
</template>

<script lang="ts">
import { defineComponent } from "vue";

import DiskMovie from "./DiskMovie.vue";
import { allowsHeavyLoad, isMetered } from "../data/connection";
import { DiskRes, RES_LADDER, diskScaleFor, product, stillUrl } from "../data/sdoCatalog";
import {
  channel,
  diskMode,
  diskRes,
  diskSettledAt,
  pfssOverlay,
  resetToken,
  view,
} from "../state/useAppState";

type LoadState = "idle" | "loading" | "ready" | "slow" | "error";

/** How long a load may take before we admit the server is slow. */
const SLOW_MS = 4000;
/** Cross-fade duration; must match the CSS transition on .disk-img-incoming. */
const FADE_MS = 320;
/** SDO publishes a new frame about every 15 minutes. */
const REFRESH_MS = 15 * 60 * 1000;
/** On returning to the tab, refresh if what we're showing is older than this. */
const STALE_MS = 10 * 60 * 1000;
/** The image the slow-race falls back to. */
const RACE_RES = 1024;
/** Past this zoom the 4096 still is worth its bytes. */
const UPGRADE_SCALE = 1.5;

const MIN_SCALE = 1;
const MAX_SCALE = 4;
const DOUBLE_TAP_SCALE = 2.5;
const DOUBLE_TAP_MS = 320;
const TAP_SLOP_PX = 20;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * The "Sun Now" full-disk viewer.
 *
 * Hard constraints from the host (CLAUDE.md footguns 6-7): sdo.gsfc.nasa.gov
 * sends no CORS headers, so this component may only ever touch those URLs
 * through <img>/<video> src — no fetch, no canvas, and NEVER a `crossorigin`
 * attribute (setting it makes every load fail). It also means there is no
 * Last-Modified to read, which is why the caption promises a cadence rather
 * than claiming a frame time.
 */
export default defineComponent({
  name: "DiskViewer",

  components: { "disk-movie": DiskMovie },

  setup() {
    return { channel, diskMode, diskRes, pfssOverlay, resetToken, view };
  },

  data() {
    return {
      // --- image layers ---
      frontSrc: "",
      backSrc: "",
      backReady: false,
      loadState: "idle" as LoadState,
      /** Resolution of the image currently on screen. */
      activeRes: 0,
      /** Resolution of the load in flight. */
      pendingRes: 0,
      /** The one cache-busted retry has been spent for this attempt. */
      retriedWithBust: false,
      /** The 4096 upgrade has been offered for this channel/overlay. */
      upgraded: false,
      /** Mid-promote: the URL the front layer is taking over from the back. */
      promotingSrc: "",
      loadedAt: 0,

      // --- timers / probes ---
      slowTimer: 0,
      refreshTimer: 0,
      promoteTimer: 0,

      // --- pinch / pan ---
      scale: 1,
      tx: 0,
      ty: 0,
      /**
       * Per-layer channel normalization (Product.diskScale) so AIA and HMI
       * disks render at the SAME on-screen diameter. Each stacked layer keeps
       * the base scale of the channel its image came from — during an
       * AIA→HMI cross-fade the outgoing and incoming disks already match.
       */
      frontBase: 1,
      backBase: 1,
      pointers: new Map<number, { x: number; y: number }>(),
      pinchStartDist: 0,
      pinchStartScale: 1,
      gestureTravel: 0,
      gestureStartedAt: 0,
      lastTapAt: 0,
      lastTapX: 0,
      lastTapY: 0,
    };
  },

  computed: {
    altText(): string {
      return product(this.channel).blurb;
    },

    /** The guest's pinch/pan only — channel normalization lives on the inner img. */
    userStyle(): Record<string, string> {
      return {
        transform: `translate(${this.tx}px, ${this.ty}px) scale(${this.scale})`,
      };
    },

    /** Live gesture: transform transitions off so pinching tracks the fingers. */
    gesturing(): boolean {
      return this.pointers.size > 0;
    },

    loadedClock(): string {
      if (!this.loadedAt) { return ""; }
      return new Date(this.loadedAt).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    },
  },

  watch: {
    channel() {
      this.upgraded = false;
      this.startLoad(this.preferredRes(), { fresh: true });
    },
    pfssOverlay() {
      this.upgraded = false;
      this.startLoad(this.activeRes || this.preferredRes(), { fresh: true });
    },
    diskRes(res: DiskRes) {
      this.upgraded = false;
      this.startLoad(res, { fresh: true });
    },
    diskMode(mode: string) {
      // Coming back from a movie: make sure the still is current.
      if (mode === "still" && Date.now() - this.loadedAt > STALE_MS) {
        this.startLoad(this.activeRes || this.preferredRes(), { bust: Date.now() });
      }
    },
    resetToken() {
      this.resetTransform();
    },
    scale() {
      this.maybeUpgrade();
    },
  },

  mounted() {
    this.startLoad(this.preferredRes(), { fresh: true });
    this.refreshTimer = window.setInterval(this.autoRefresh, REFRESH_MS);
    document.addEventListener("visibilitychange", this.onVisibilityChange);
  },

  beforeUnmount() {
    window.clearInterval(this.refreshTimer);
    window.clearTimeout(this.slowTimer);
    window.clearTimeout(this.promoteTimer);
    document.removeEventListener("visibilitychange", this.onVisibilityChange);
  },

  methods: {
    // --- loading ---------------------------------------------------------

    /** Resolution to ask for: the guest's choice, trimmed on a metered link. */
    preferredRes(): number {
      return isMetered() ? RACE_RES : this.diskRes;
    },

    /**
     * Begin loading a still into the incoming layer.
     * `fresh` resets the error/retry ladder (a new user intent, not a retry).
     */
    startLoad(res: number, opts: { bust?: number; fresh?: boolean; upgrade?: boolean } = {}): void {
      if (opts.fresh) {
        this.retriedWithBust = false;
        this.loadState = "idle";
      }

      const url = stillUrl(this.channel, res, this.pfssOverlay, opts.bust);
      if (url === this.frontSrc && !opts.upgrade) { return; }

      window.clearTimeout(this.slowTimer);
      window.clearTimeout(this.promoteTimer);

      // Abandon any promote in flight: the front layer already holds the
      // previous URL, and backReady=false makes the incoming layer transparent
      // again, so the handover is complete as far as the guest can tell.
      this.promotingSrc = "";
      this.pendingRes = res;
      this.backReady = false;
      this.backBase = diskScaleFor(this.channel, res, this.pfssOverlay);
      this.backSrc = url;
      this.loadState = "loading";

      // 4 s without a decoded image: say so, and race a smaller one. Whichever
      // arrives first wins — the browser aborts the loser when src changes.
      this.slowTimer = window.setTimeout(() => this.onSlow(res, opts.bust), SLOW_MS);
    },

    onSlow(res: number, bust?: number): void {
      if (this.backSrc === "" || this.backReady) { return; }
      this.loadState = "slow";
      if (res <= RACE_RES) { return; }

      const raceUrl = stillUrl(this.channel, RACE_RES, this.pfssOverlay, bust);
      const probe = new Image();
      probe.decoding = "async";
      probe.onload = () => {
        // Only switch if the full-size image still hasn't landed. The probe has
        // already warmed the cache, so assigning backSrc resolves immediately.
        if (this.backSrc !== "" && !this.backReady) {
          this.pendingRes = RACE_RES;
          // The overlay variant does not exist at every resolution, so dropping
          // to RACE_RES can change WHICH image this layer is showing — and with
          // it the scale that image needs (diskScaleFor mirrors stillUrl).
          this.backBase = diskScaleFor(this.channel, RACE_RES, this.pfssOverlay);
          this.backSrc = raceUrl;
        }
      };
      probe.src = raceUrl;
    },

    onBackLoad(event: Event): void {
      const img = event.target as HTMLImageElement;
      // Stale event from a src we've already moved past.
      if (img.getAttribute("src") !== this.backSrc) { return; }

      window.clearTimeout(this.slowTimer);
      this.backReady = true;
      this.loadState = "ready";
      this.loadedAt = Date.now();
      this.retriedWithBust = false;
      diskSettledAt.value = this.loadedAt;

      // Promote once the cross-fade has finished. Handing the new URL to the
      // front layer while the (now opaque) incoming layer still covers it means
      // the guest never sees the front <img> blank out mid-swap; the incoming
      // layer is torn down only when the front reports it has the image
      // (onFrontLoad), with a timer as a belt-and-braces fallback.
      this.promoteTimer = window.setTimeout(() => {
        if (!this.backReady) { return; }
        this.promotingSrc = this.backSrc;
        this.frontSrc = this.backSrc;
        this.frontBase = this.backBase;
        this.activeRes = this.pendingRes;
        this.promoteTimer = window.setTimeout(this.finishPromote, FADE_MS);
      }, FADE_MS);
    },

    onFrontLoad(event: Event): void {
      const img = event.target as HTMLImageElement;
      if (this.promotingSrc && img.getAttribute("src") === this.promotingSrc) {
        this.finishPromote();
      }
    },

    /** Drop the incoming layer now that the front layer is showing its image. */
    finishPromote(): void {
      if (!this.promotingSrc) { return; }
      window.clearTimeout(this.promoteTimer);
      this.promotingSrc = "";
      this.backSrc = "";
      this.backReady = false;
    },

    onBackError(event: Event): void {
      const img = event.target as HTMLImageElement;
      if (img.getAttribute("src") !== this.backSrc) { return; }

      window.clearTimeout(this.slowTimer);
      this.backSrc = "";

      // 1. One cache-busted retry — most failures here are a truncated or
      //    half-written file on a GSFC edge node.
      if (!this.retriedWithBust) {
        this.retriedWithBust = true;
        this.startLoad(this.pendingRes, { bust: Date.now() });
        return;
      }

      // 2. Step down the resolution ladder (4096 → 2048 → 1024 → 512).
      const smaller = RES_LADDER.find((r) => r < this.pendingRes);
      if (smaller !== undefined) {
        this.retriedWithBust = false;
        this.startLoad(smaller);
        return;
      }

      // 3. Out of options: say so plainly, and keep the stats honest.
      this.loadState = "error";
    },

    retryFromScratch(): void {
      this.startLoad(this.preferredRes(), { bust: Date.now(), fresh: true });
    },

    autoRefresh(): void {
      if (document.visibilityState !== "visible") { return; }
      if (this.view !== "disk" || this.diskMode !== "still") { return; }
      if (this.loadState === "loading" || this.loadState === "slow") { return; }
      this.startLoad(this.activeRes || this.preferredRes(), { bust: Date.now(), fresh: true });
    },

    onVisibilityChange(): void {
      if (document.visibilityState !== "visible") { return; }
      if (Date.now() - this.loadedAt > STALE_MS) { this.autoRefresh(); }
    },

    /**
     * Deep zoom on a good connection: quietly stack-load the 4096 and fade it
     * in. Once per channel/overlay — a guest pinching in and out shouldn't
     * trigger repeat 4 MB downloads.
     */
    maybeUpgrade(): void {
      if (this.upgraded || this.scale <= UPGRADE_SCALE) { return; }
      if (this.loadState !== "ready" || this.diskMode !== "still") { return; }
      if (this.activeRes >= 4096 || this.diskRes >= 4096) { return; }
      if (!allowsHeavyLoad()) { return; }
      this.upgraded = true;
      this.startLoad(4096, { upgrade: true });
    },

    // --- gestures --------------------------------------------------------

    stageRect(): DOMRect | null {
      const stage = this.$refs.stage as HTMLElement | undefined;
      return stage ? stage.getBoundingClientRect() : null;
    },

    pointerList(): { x: number; y: number }[] {
      return Array.from(this.pointers.values());
    },

    /** Keep the disk inside the stage: |t| ≤ half the overflow at this scale. */
    clampTranslate(): void {
      const rect = this.stageRect();
      if (!rect) { return; }
      // Overflow depends on the EFFECTIVE scale (user pinch × channel disk
      // normalization) — an HMI image at user scale 1.1 may not overflow at all.
      // frontBase, not a fresh lookup: it is the scale of the image actually on
      // screen, which the pfss overlay and the resolution race can both change.
      const eff = this.scale * this.frontBase;
      const maxX = (rect.width * Math.max(0, eff - 1)) / 2;
      const maxY = (rect.height * Math.max(0, eff - 1)) / 2;
      this.tx = clamp(this.tx, -maxX, maxX);
      this.ty = clamp(this.ty, -maxY, maxY);
    },

    /** Scale about a screen point, keeping whatever is under it in place. */
    zoomAbout(nextScale: number, clientX: number, clientY: number): void {
      const rect = this.stageRect();
      if (!rect) { return; }
      const target = clamp(nextScale, MIN_SCALE, MAX_SCALE);
      const px = clientX - (rect.left + rect.width / 2);
      const py = clientY - (rect.top + rect.height / 2);
      const ratio = target / this.scale;
      this.tx = px - (px - this.tx) * ratio;
      this.ty = py - (py - this.ty) * ratio;
      this.scale = target;
      if (target === MIN_SCALE) {
        this.tx = 0;
        this.ty = 0;
      }
      this.clampTranslate();
    },

    resetTransform(): void {
      this.scale = MIN_SCALE;
      this.tx = 0;
      this.ty = 0;
    },

    onPointerDown(event: PointerEvent): void {
      const stage = this.$refs.stage as HTMLElement | undefined;
      if (stage && stage.setPointerCapture) {
        try {
          stage.setPointerCapture(event.pointerId);
        } catch {
          // Some browsers refuse capture for already-released pointers.
        }
      }
      this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (this.pointers.size === 1) {
        this.gestureTravel = 0;
        this.gestureStartedAt = Date.now();
      }
      if (this.pointers.size === 2) {
        const pts = this.pointerList();
        this.pinchStartDist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
        this.pinchStartScale = this.scale;
      }
    },

    onPointerMove(event: PointerEvent): void {
      const previous = this.pointers.get(event.pointerId);
      if (!previous) { return; }
      const dx = event.clientX - previous.x;
      const dy = event.clientY - previous.y;
      this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      this.gestureTravel += Math.hypot(dx, dy);

      if (this.pointers.size >= 2) {
        const pts = this.pointerList();
        const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
        if (this.pinchStartDist > 0) {
          const midX = (pts[0].x + pts[1].x) / 2;
          const midY = (pts[0].y + pts[1].y) / 2;
          this.zoomAbout((this.pinchStartScale * dist) / this.pinchStartDist, midX, midY);
        }
        return;
      }

      // Single-finger drag pans, but only when there is something to pan.
      if (this.scale > MIN_SCALE) {
        this.tx += dx;
        this.ty += dy;
        this.clampTranslate();
      }
    },

    onPointerUp(event: PointerEvent): void {
      if (!this.pointers.has(event.pointerId)) { return; }
      this.pointers.delete(event.pointerId);

      if (this.pointers.size === 1) {
        // Second finger lifted mid-pinch: re-baseline so the next move doesn't jump.
        this.pinchStartDist = 0;
      }
      if (this.pointers.size > 0) { return; }

      const wasTap =
        this.gestureTravel < TAP_SLOP_PX && Date.now() - this.gestureStartedAt < 400;
      if (!wasTap) { return; }

      const now = Date.now();
      const near =
        Math.hypot(event.clientX - this.lastTapX, event.clientY - this.lastTapY) < 40;
      if (now - this.lastTapAt < DOUBLE_TAP_MS && near) {
        // Double tap toggles between fit and a close look. No momentum: the
        // disk should feel like a print on a table, not a flicked map.
        const target = this.scale > 1.05 ? MIN_SCALE : DOUBLE_TAP_SCALE;
        this.zoomAbout(target, event.clientX, event.clientY);
        this.lastTapAt = 0;
        return;
      }
      this.lastTapAt = now;
      this.lastTapX = event.clientX;
      this.lastTapY = event.clientY;
    },

    onWheel(event: WheelEvent): void {
      // Desktop courtesy; phones never get here (touch-action: none).
      const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15;
      this.zoomAbout(this.scale * factor, event.clientX, event.clientY);
    },
  },
});
</script>

<style lang="less" scoped>
.disk-viewer {
  display: flex;
  flex-direction: column;
  min-height: 0;
  width: 100%;
  height: 100%;
  -webkit-tap-highlight-color: transparent;
}

.disk-stage {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
  overflow: hidden;
  // The app owns every gesture in here — no browser pan/zoom/scroll.
  touch-action: none;
  background: radial-gradient(circle at 50% 50%, #14100a 0%, #000 70%);
}

.disk-layer {
  position: absolute;
  inset: 0;
  transform-origin: 50% 50%;
  will-change: transform;
  transition: transform 320ms ease-out;
}

.disk-layer-incoming {
  opacity: 0;
  transition: transform 320ms ease-out, opacity 320ms ease-in;

  &.is-ready {
    opacity: 1;
  }
}

.disk-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  transform-origin: 50% 50%;
  -webkit-user-drag: none;
  // Deliberately NO transition: this transform is the per-channel disk
  // normalization, which must never animate (the AIA↔HMI "bump").
}

// During a pinch the transform must track the fingers exactly; the cross-fade
// keeps its own timing.
.disk-stage.is-gesturing .disk-layer {
  transition: none;
}
.disk-stage.is-gesturing .disk-layer-incoming {
  transition: opacity 320ms ease-in;
}

.disk-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.9rem;
  pointer-events: none;
}

.disk-overlay-text {
  margin: 0;
  color: var(--sol-text-dim);
  font-size: 0.9rem;
  text-align: center;
}

.disk-slow-note {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  margin: 0;
  color: var(--sol-text-dim);
  font-size: 0.8rem;
  pointer-events: none;
}

.sol-spinner {
  width: 2.6rem;
  height: 2.6rem;
  border-radius: 50%;
  border: 4px solid rgba(255, 200, 80, 0.25);
  border-top-color: var(--sol-accent);
  animation: sol-spin 1s linear infinite;
}

.sol-spinner-sm {
  width: 1rem;
  height: 1rem;
  border-width: 2px;
}

.disk-error {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  max-width: min(92%, 22rem);
  padding: 1rem 1.1rem;
  border: 1px solid rgba(255, 200, 80, 0.4);
  border-radius: 12px;
  background: var(--sol-surface);
  text-align: center;
}

.disk-error-title {
  margin: 0 0 0.35rem;
  color: var(--sol-accent);
  font-size: 1rem;
  font-weight: 700;
}

.disk-error-body {
  margin: 0 0 0.75rem;
  color: var(--sol-text-dim);
  font-size: 0.85rem;
}

.disk-error-btn {
  min-height: 44px;
  padding: 0 1.3rem;
  border: 1px solid var(--sol-accent);
  border-radius: 8px;
  background: transparent;
  color: var(--sol-accent);
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
}

.disk-movie-slot {
  flex: 1 1 auto;
  min-height: 0;
}

.disk-caption {
  flex: 0 0 auto;
  margin: 0;
  padding: 0.35rem 0.75rem 0.2rem;
  color: var(--sol-text-dim);
  font-size: 0.72rem;
  line-height: 1.25;
  text-align: center;
}
</style>
