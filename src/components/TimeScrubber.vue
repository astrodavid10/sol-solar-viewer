<template>
  <div class="time-scrubber no-select">
    <div v-if="stale" class="ts-banner">
      <font-awesome-icon icon="circle-info" />
      <span>{{ staleText }}</span>
    </div>

    <div class="ts-row">
      <button
        type="button"
        class="ts-play"
        :class="{ 'is-idle-pulse': idlePulse }"
        :disabled="!canPlay"
        :aria-label="playing ? 'Pause' : playTitle"
        :title="canPlay ? playTitle : 'Still loading'"
        @click="togglePlay"
      >
        <font-awesome-icon :icon="playing ? 'pause' : 'play'" />
      </button>

      <div class="ts-track">
        <!-- Loading progress lives UNDER the slider: frames arrive newest-first,
             so the right-hand (most recent) end fills in first. -->
        <div class="ts-ticks" aria-hidden="true">
          <span
            v-for="tick in ticks"
            :key="tick.index"
            class="ts-tick"
            :class="{ 'is-loaded': tick.loaded, 'is-held': tick.held }"
            :style="{ left: tick.left + '%' }"
          ></span>
        </div>

        <!-- Solar flares and CMEs inside the window: tap one to scrub to it.
             Each button is a transparent hit area up to 44 px wide around an
             8 px painted mark (T11: the marks used to BE the 8 px buttons). In
             a cluster each area stops halfway to its neighbour, so a tap always
             picks the nearest mark and no area steals another's taps. -->
        <div v-if="eventMarks.length" ref="band" class="ts-events">
          <button
            v-for="mark in hitMarks"
            :key="mark.key"
            type="button"
            class="ts-event"
            :style="{ left: mark.hitLeft + 'px', width: mark.hitWidth + 'px' }"
            :title="mark.label"
            :aria-label="'Jump to ' + mark.label"
            @click="onMark(mark)"
          >
            <span class="ts-event-dot" :class="'is-' + mark.severity" :style="{ left: mark.dotLeft + 'px' }"></span>
          </button>
        </div>

        <input
          class="ts-range"
          type="range"
          min="0"
          :max="sliderMax"
          step="0.01"
          :value="frameT"
          :disabled="!available"
          :aria-label="`Time within the last ${windowHours} hours`"
          @input="onInput"
          @pointerdown="onGrab"
          @pointerup="onRelease"
          @pointercancel="onRelease"
        >

        <button
          v-if="eventMarks.length"
          type="button"
          class="ts-key-btn"
          :aria-expanded="keyOpen"
          aria-label="What the marks on the timeline mean"
          @click="keyOpen = !keyOpen"
        >?</button>
        <div v-if="keyOpen" class="ts-key" role="note" data-camera-passthrough="false">
          <p><span class="ts-key-mark ts-event-dot is-m"></span>A flare. This is a flash of light from the Sun. The redder the mark, the stronger the flare.</p>
          <p><span class="ts-key-mark ts-event-dot is-cme"></span>An eruption (CME). This is a cloud of gas leaving the Sun.</p>
          <p><span class="ts-key-mark ts-key-tick"></span>A hollow tick means no new magnetic map came in for that hour.</p>
          <p>Tap a mark to jump to it and read about it.</p>
        </div>

        <p class="ts-label">
          <template v-if="loadingText">{{ loadingText }}</template>
          <template v-else>
            <strong>{{ stampText }}</strong> · {{ ageText }}<template v-if="heldText"> · {{ heldText }}</template><template v-if="gapText"> · {{ gapText }}</template>
          </template>
        </p>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent } from "vue";

import { kiosk, playing } from "../state/useAppState";
import { guestStamp } from "../data/guestTime";

/** How often the "N hours ago" text re-derives from the wall clock. */
const AGE_REFRESH_MS = 60000;


/** The newest slot reads "now" only while it is younger than this (T3). */
const NOW_MAX_AGE_S = 6 * 3600;

interface Tick {
  index: number;
  left: number;
  loaded: boolean;
  held: boolean;
}

/**
 * The 72-hour time control.
 *
 * A native `<input type="range">` on purpose: it is the only slider that gets
 * touch, keyboard and screen-reader behavior right on every phone for free.
 * Everything below is styling and honest labeling.
 *
 * The default resting state is PAUSED at the newest frame, because the app is
 * fundamentally an answer to "what is the Sun doing right now" — the animation
 * is an invitation, not the main event. Kiosk mode is the exception: an unwatched
 * lobby screen should be moving.
 */
/** One mark on the track. `id` is empty for NOAA flare history, which has no
 *  stable identifier — only DONKI events can be selected. */
interface EventMark {
  key: string;
  id: string;
  left: number;
  frame: number;
  label: string;
  severity: string;
}

interface HitMark extends EventMark {
  /** px from the band's left edge: the hit area's left edge and width. */
  hitLeft: number;
  hitWidth: number;
  /** px from the hit area's left edge to the painted mark's center. */
  dotLeft: number;
}

/** Widest hit area per mark (a 44 px minimum touch target), T11. */
const HIT_MAX_PX = 44;

export default defineComponent({
  name: "TimeScrubber",

  props: {
    /** Frames the manifest promises (19 over 72 h; config.WINDOW_HOURS). */
    frameCount: {
      type: Number,
      default: 0,
    },
    /** Oldest index of the contiguous loaded run; frameCount when empty. */
    loadedFrom: {
      type: Number,
      default: 0,
    },
    /**
     * Newest index of that run — the right-hand end of the track, and NOT
     * always `frameCount - 1`: if the newest frame 404s during a publish the
     * animation ends four hours short of "now". -1 while nothing has loaded.
     */
    loadedTo: {
      type: Number,
      default: -1,
    },
    loadedCount: {
      type: Number,
      default: 0,
    },
    /** True once the loader has stopped trying, so any frame still missing is
     *  missing for good and the label must give up saying "Loading…". */
    loadDone: {
      type: Boolean,
      default: false,
    },
    /**
     * Slot TARGET time per frame index, unix seconds: an even 4 h grid. It used
     * to be each frame's magnetogram time, so a frame that reused an older
     * magnetogram (a GONG mirror gap) collapsed onto its neighbour: the window
     * read "last 20 hours" against a 72 h manifest and the end of the track went
     * dead (T40).
     */
    times: {
      type: Array as () => number[],
      default: () => [],
    },
    /** Per frame: true when the slot had no new magnetogram and repeats an older one. */
    held: {
      type: Array as () => boolean[],
      default: () => [],
    },
    /** Per frame: the magnetogram's own time, unix seconds (for the held note). */
    magTimes: {
      type: Array as () => number[],
      default: () => [],
    },
    /** Current playhead in fractional frame indices (owned by the renderer). */
    frameT: {
      type: Number,
      default: 0,
    },
    stale: {
      type: Boolean,
      default: false,
    },
    staleHours: {
      type: Number,
      default: 0,
    },
    /**
     * Moments to mark on the track: {unix, label, cls, kind?}.
     *
     * `cls` is the GOES class string ("M1.2") and drives severity styling for
     * flares. `kind` tells a CME from a flare so the two get different marks —
     * a guest has to be able to tell "the Sun flashed" from "the Sun threw
     * something at us" at a glance, and they are genuinely different events
     * even when DONKI links them to each other. Omitted `kind` means "flare",
     * so the NOAA flare history keeps working untouched.
     */
    events: {
      type: Array as () => {
        unix: number; label: string; cls: string; kind?: string; id?: string;
      }[],
      default: () => [],
    },
  },

  emits: ["scrub", "grab", "release", "pick-event"],

  setup() {
    return { kiosk, playing };
  },

  data() {
    return {
      nowUnix: Date.now() / 1000,
      /** Width of the mark band in px, measured; 0 until mounted. */
      bandWidth: 0,
      bandObserver: null as ResizeObserver | null,
      keyOpen: false,
      ageTimer: 0,
      resumeAfterDrag: false,
    };
  },

  computed: {
    available(): boolean {
      return this.loadedCount >= 1;
    },

    /**
     * Look-back window in hours, derived from the manifest's actual frame
     * times so the pipeline can change its window (48 h → 72 h → …) without
     * touching the app. Falls back to 48 until times arrive.
     */
    windowHours(): number {
      const times = this.times;
      if (times.length < 2) { return 48; }
      return Math.round((times[times.length - 1] - times[0]) / 3600);
    },

    playTitle(): string {
      return `Play the last ${this.windowHours} hours`;
    },

    /** Two frames make a cross-fade; three make something worth watching —
     *  counted along the run the renderer can actually animate, not the total
     *  decoded. Three frames with a hole between them play nothing. */
    canPlay(): boolean {
      return this.loadedTo - this.loadedFrom >= 2;
    },

    /**
     * The newest frame the guest can reach.
     *
     * Not `frameCount - 1`: the renderer clamps the playhead to the loaded run,
     * and a range input whose bound value does not change is NOT re-patched by
     * Vue — so a thumb dragged into a missing frame stayed there, pointing at a
     * time the view was not showing. Ending the axis at the last loaded frame
     * is the only clamp the guest's finger can feel.
     *
     * The tick and event marks keep the full-window axis below, so in the
     * missing-newest case the two axes differ by one frame in nineteen (5.6% of
     * the track). That is the trade: a mark a few pixels off in a rare failure,
     * against a thumb that lies about what is on screen every time.
     *
     * `min` deliberately does NOT get the same treatment. This end only moves
     * when the newest frame is missing, which is permanent; `loadedFrom` walks
     * 18 → 0 through every normal load (newest-first), so pinning min to it
     * would rescale the whole track under the guest several times a second.
     */
    sliderMax(): number {
      return Math.max(this.loadedTo, 0.01);
    },

    atNewest(): boolean {
      return this.frameT >= this.frameCount - 1.001;
    },

    idlePulse(): boolean {
      return this.canPlay && !this.playing && this.atNewest;
    },

    /** `loadDone` is what ends this. Counting to `frameCount` alone pinned the
     *  label on "Loading… 18 of 19" forever when one frame was never coming,
     *  and the UT stamp — the thing a guest actually reads — never appeared. */
    loadingText(): string {
      if (this.loadedCount >= this.frameCount || this.frameCount === 0) { return ""; }
      if (this.loadDone) { return ""; }
      return `Loading the last ${this.windowHours} hours… ${this.loadedCount} of ${this.frameCount}`;
    },

    /** Said only once the load has finished with a hole in it, and said in one
     *  clause after the stamp rather than instead of it: the ticks already show
     *  WHERE the gap is, so this only has to explain why the track is short. */
    /** "no new magnetogram since 14:14 UTC" while the playhead sits on a held slot. */
    heldText(): string {
      const i = Math.round(this.frameT);
      if (!this.held[i]) { return ""; }
      const mag = this.magTimes[i];
      if (!Number.isFinite(mag)) { return "no new magnetogram for this hour"; }
      return `no new magnetic map since ${guestStamp(mag)}`;
    },

    gapText(): string {
      if (!this.loadDone || this.frameCount === 0) { return ""; }
      const missing = this.frameCount - this.loadedCount;
      if (missing < 1) { return ""; }
      return `${missing} frame${missing === 1 ? "" : "s"} missing`;
    },

    ticks(): Tick[] {
      const span = Math.max(this.frameCount - 1, 1);
      const out: Tick[] = [];
      for (let i = 0; i < this.frameCount; i++) {
        // Lit = reachable: the run the playhead can actually visit. Frames on
        // the far side of an interior hole are decoded but unreachable, and
        // frames past `loadedTo` never arrived — both read as unlit.
        out.push({
          index: i,
          left: (i / span) * 100,
          loaded: i >= this.loadedFrom && i <= this.loadedTo,
          held: !!this.held[i],
        });
      }
      return out;
    },

    /**
     * Flares mapped onto the track. The frame axis is only piecewise-linear in
     * time (GONG gaps), so each event is converted unix→fractional frame by
     * locating its bracketing frames, then to a track percent on the frame
     * axis — the same axis the range input uses, so a tap really lands there.
     */
    eventMarks(): EventMark[] {
      const times = this.times;
      if (times.length < 2 || !this.events.length) { return []; }
      const last = times.length - 1;
      const out: EventMark[] = [];
      for (const event of this.events) {
        if (event.unix < times[0] || event.unix > times[last]) { continue; }
        let indexA = 0;
        while (indexA < last - 1 && times[indexA + 1] <= event.unix) { indexA++; }
        const span = times[indexA + 1] - times[indexA];
        const frame = indexA + (span > 0 ? (event.unix - times[indexA]) / span : 0);
        const letter = (event.cls || "C").charAt(0).toUpperCase();
        const severity = event.kind === "cme"
          ? "cme"
          : letter === "X" ? "x" : letter === "M" ? "m" : "c";
        out.push({
          key: event.id || `${event.unix}-${event.cls}`,
          id: event.id || "",
          left: (frame / Math.max(this.frameCount - 1, 1)) * 100,
          frame,
          label: event.label,
          severity,
        });
      }
      return out;
    },

    /**
     * The marks with non-overlapping hit areas: each reaches at most 22 px
     * either side of its mark, and never past the midpoint to a neighbour.
     */
    hitMarks(): HitMark[] {
      const width = this.bandWidth;
      const half = HIT_MAX_PX / 2;
      const marks = [...this.eventMarks].sort((a, b) => a.left - b.left);
      const centers = marks.map((m) => (m.left / 100) * width);
      return marks.map((mark, i) => {
        const c = centers[i];
        const lo = i > 0 ? Math.max(c - half, (centers[i - 1] + c) / 2) : c - half;
        const hi = i < marks.length - 1 ? Math.min(c + half, (c + centers[i + 1]) / 2) : c + half;
        return { ...mark, hitLeft: lo, hitWidth: Math.max(hi - lo, 1), dotLeft: c - lo };
      });
    },

    /** Magnetogram time at the playhead, interpolated between frames. */
    playheadUnix(): number {
      const times = this.times;
      if (!times.length) { return this.nowUnix; }
      const last = times.length - 1;
      const t = Math.min(Math.max(this.frameT, 0), last);
      const indexA = Math.min(Math.floor(t), last);
      const indexB = Math.min(indexA + 1, last);
      const fraction = t - indexA;
      return times[indexA] + (times[indexB] - times[indexA]) * fraction;
    },

    /** Local date, time and zone (T12): the one clock a guest reads. */
    stampText(): string {
      return guestStamp(this.playheadUnix);
    },

    /**
     * The newest frame reads "now". It is really ~1-2 h old (that is what a
     * GONG synoptic magnetogram is), and the stale banner says so when the lag
     * grows — but at the right-hand end of a 72-hour scrubber, "now" is the
     * honest answer to what the guest is asking.
     */
    ageText(): string {
      // "now" only while the newest slot really is recent. When every product
      // is stale (a pipeline outage), the newest slot is hours or days old and
      // saying "now" would contradict the banner a few pixels above (T3).
      if (this.atNewest && this.nowUnix - this.playheadUnix < NOW_MAX_AGE_S) { return "now"; }
      const hours = (this.nowUnix - this.playheadUnix) / 3600;
      if (hours < 1.5) { return "just now"; }
      return `${Math.round(hours)} hours ago`;
    },

    staleText(): string {
      const hours = Math.round(this.staleHours);
      if (!(hours > 0)) { return "Magnetic field data may be out of date"; }
      return `Magnetic field data from ${hours} hour${hours === 1 ? "" : "s"} ago`;
    },
  },

  watch: {
    canPlay(value: boolean) {
      // Lobby screens should never sit still; guests' phones always should.
      if (value && this.kiosk) { this.playing = true; }
    },
  },

  mounted() {
    this.ageTimer = window.setInterval(() => {
      this.nowUnix = Date.now() / 1000;
    }, AGE_REFRESH_MS);
    if (this.canPlay && this.kiosk) { this.playing = true; }
    this.bandObserver = new ResizeObserver(() => this.measureBand());
    this.bandObserver.observe(this.$el as Element);
    this.measureBand();
  },

  updated() {
    // The band only exists while there are marks; measure it once it appears.
    if (!this.bandWidth) { this.measureBand(); }
  },

  beforeUnmount() {
    window.clearInterval(this.ageTimer);
    this.bandObserver?.disconnect();
  },

  methods: {
    measureBand(): void {
      const band = this.$refs.band as HTMLElement | undefined;
      const w = band ? band.clientWidth : 0;
      if (w && Math.abs(w - this.bandWidth) > 0.5) { this.bandWidth = w; }
    },

    /** Tapping a mark always scrubs there; if it is a DONKI event it also asks
     *  the parent to open its card. Scrub first so the view is already at the
     *  right moment by the time the card appears. */
    onMark(mark: EventMark): void {
      this.$emit("scrub", mark.frame);
      if (mark.id) { this.$emit("pick-event", mark.id); }
    },

    togglePlay(): void {
      if (!this.canPlay) { return; }
      this.playing = !this.playing;
    },

    onInput(event: Event): void {
      const value = Number((event.target as HTMLInputElement).value);
      if (Number.isFinite(value)) { this.$emit("scrub", value); }
    },

    /** Dragging pauses; releasing resumes only if it was playing. */
    onGrab(): void {
      this.resumeAfterDrag = this.playing;
      this.playing = false;
      this.$emit("grab");
    },

    onRelease(): void {
      if (this.resumeAfterDrag && this.canPlay) { this.playing = true; }
      this.resumeAfterDrag = false;
      this.$emit("release");
    },
  },
});
</script>

<style lang="less" scoped>
.time-scrubber {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.5rem 0.6rem;
  // The same panel treatment as the layer panel and the info panel, from the
  // same tokens. It had its own radius (12 vs 14), its own translucent ground
  // and its own blur -- three private decisions that made the one control every
  // guest touches look unrelated to the rest of the app.
  //
  // The blur is gone for the reason in footgun 39: this panel is full-width and
  // sits directly over the WebGL canvas, so a backdrop-filter here was the most
  // expensive single thing in the overlay, re-blurring every frame whether
  // anything moved or not.
  border: var(--sol-panel-border);
  border-radius: var(--sol-panel-radius);
  background: var(--sol-surface);
  box-shadow: var(--sol-panel-shadow);
}

.ts-banner {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  // A staleness warning: amber is the right signal, but through the semantic
  // token, so it is not the same string as "closed magnetic field".
  color: var(--sol-warn);
  font-size: 0.7rem;
  line-height: 1.2;
}

.ts-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.ts-play {
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  // Was a 50% circle with its own border and fill alpha. It is a control in a
  // panel, exactly like a layer segment, so it uses the segment's treatment and
  // the shared control radius -- a lone circle among rounded rectangles was the
  // most visible mismatch in the app.
  border: 1px solid rgba(var(--sol-select-rgb), 0.75);
  border-radius: var(--sol-control-radius);
  background: rgba(var(--sol-select-rgb), 0.14);
  color: var(--sol-text);
  font-size: 0.95rem;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;

  &:disabled {
    opacity: 0.35;
    cursor: default;
    border-color: var(--sol-hairline);
    color: var(--sol-text-dim);
    background: transparent;
  }

  // A resting app should still say "there is more here" — once.
  &.is-idle-pulse {
    animation: ts-pulse 2.6s ease-in-out infinite;
  }
}

@keyframes ts-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(var(--sol-select-rgb), 0.35); }
  50% { box-shadow: 0 0 0 8px rgba(var(--sol-select-rgb), 0); }
}

.ts-track {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
}

.ts-ticks {
  position: absolute;
  top: 6px;
  left: 8px;
  right: 8px;
  height: 4px;
  pointer-events: none;
}

// Flare markers sit just above the track, inside the same 8px inset the ticks
// use so their percent axis lines up with the range input's.
.ts-events {
  position: absolute;
  top: -8px;
  left: 8px;
  right: 8px;
  height: 12px;
  pointer-events: none;
}

// The hit area (T11): transparent, up to 44 px wide, extending upward from
// the band so it never overlaps the range input the guest drags.
.ts-event {
  position: absolute;
  top: -22px;
  height: 32px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  pointer-events: auto;
  -webkit-tap-highlight-color: transparent;

  &:focus-visible {
    outline: 2px solid rgba(var(--sol-select-rgb), 0.8);
    outline-offset: -2px;
    border-radius: 6px;
  }
}

// The painted mark, centered at `left` inside its hit area.
.ts-event-dot {
  position: absolute;
  top: 24px;
  width: 8px;
  height: 8px;
  margin-left: -4px;
  border-radius: 1px;
  transform: rotate(45deg);
  pointer-events: none;

  // C flares: quiet amber diamonds.
  background: rgba(var(--sol-accent-rgb), 0.55);

  &.is-m {
    background: #ffa040;
    box-shadow: 0 0 6px rgba(255, 160, 64, 0.6);
  }

  &.is-x {
    background: #ff5f4d;
    box-shadow: 0 0 8px rgba(255, 95, 77, 0.8);
    width: 10px;
    height: 10px;
    margin-left: -5px;
    top: 22px;
  }

  // CMEs: a circle in the open-field blue, deliberately NOT a diamond and
  // deliberately not on the flare color ramp. A flare is a flash on the Sun;
  // a CME is something leaving it, and the two must not read as degrees of the
  // same thing even when DONKI links them.
  &.is-cme {
    width: 9px;
    height: 9px;
    margin-left: -4.5px;
    top: 23px;
    border-radius: 50%;
    transform: none;
    background: transparent;
    border: 2px solid var(--sol-accent2, #5fb8ff);
    box-shadow: 0 0 6px rgba(var(--sol-accent2-rgb), 0.55);
  }
}

// The key (T11): a small "?" at the right end of the label row, opening a
// note above the track. Not a permanent legend strip: phones have no room.
.ts-key-btn {
  position: absolute;
  right: 0;
  bottom: -6px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid rgba(var(--sol-select-rgb), 0.35);
  background: transparent;
  color: var(--sol-text-dim);
  font-size: 0.8rem;
  font-weight: 700;
  cursor: pointer;
}

.ts-key {
  position: absolute;
  right: 0;
  bottom: calc(100% + 26px);
  z-index: 2;
  width: min(20rem, 100%);
  padding: 0.6rem 0.8rem;
  border-radius: 10px;
  background: var(--sol-surface);
  border: 1px solid rgba(var(--sol-select-rgb), 0.2);
  color: var(--sol-text-dim);
  font-size: 0.78rem;
  line-height: 1.4;

  p { margin: 0 0 0.35rem; }
  p:last-child { margin-bottom: 0; }
}

.ts-key-mark {
  position: relative;
  display: inline-block;
  top: 0;
  margin: 0 0.6rem 0 0.2rem;
  vertical-align: middle;
}

.ts-key-tick {
  width: 4px;
  height: 8px;
  box-shadow: inset 0 0 0 1px rgba(var(--sol-select-rgb), 0.7);
}

.ts-tick {
  position: absolute;
  top: 0;
  width: 2px;
  height: 4px;
  margin-left: -1px;
  border-radius: 1px;
  background: var(--sol-hairline);
  transition: background 200ms ease;

  // A held slot repeats an older magnetogram (T40): drawn hollow, so a guest
  // can see where the field stops changing.
  &.is-held {
    width: 4px;
    margin-left: -2px;
    background: transparent !important;
    box-shadow: inset 0 0 0 1px rgba(var(--sol-select-rgb), 0.6);
  }

  // Which frames have downloaded: UI state, not data. Neutral.
  &.is-loaded {
    background: rgba(var(--sol-select-rgb), 0.75);
  }
}

.ts-range {
  position: relative;
  display: block;
  width: 100%;
  height: 16px;
  margin: 0;
  background: transparent;
  -webkit-appearance: none;
  appearance: none;
  cursor: pointer;
  touch-action: pan-y;

  &:disabled {
    opacity: 0.4;
    cursor: default;
  }

  &::-webkit-slider-runnable-track {
    height: 4px;
    border-radius: 2px;
    background: var(--sol-hairline);
  }

  &::-moz-range-track {
    height: 4px;
    border-radius: 2px;
    background: var(--sol-hairline);
  }

  // 20 px thumb inside a 44 px-tall row: the visual is small, the target isn't.
  &::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 20px;
    height: 20px;
    margin-top: -8px;
    border: 2px solid rgba(0, 0, 0, 0.6);
    border-radius: 50%;
    // The playhead handle: UI, so neutral. It also has to out-contrast the
    // gold C-flare diamonds sitting on the very same track -- when both were
    // gold, the thing you drag and the thing you tap looked identical.
    background: var(--sol-select);
  }

  &::-moz-range-thumb {
    width: 20px;
    height: 20px;
    border: 2px solid rgba(0, 0, 0, 0.6);
    border-radius: 50%;
    // The playhead handle: UI, so neutral. It also has to out-contrast the
    // gold C-flare diamonds sitting on the very same track -- when both were
    // gold, the thing you drag and the thing you tap looked identical.
    background: var(--sol-select);
  }
}

.ts-label {
  margin: 0.1rem 0 0;
  color: var(--sol-text-dim);
  font-size: 0.72rem;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

  strong {
    color: var(--sol-text);
    font-weight: 600;
  }
}
</style>
