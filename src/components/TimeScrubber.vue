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
            :class="{ 'is-loaded': tick.loaded }"
            :style="{ left: tick.left + '%' }"
          ></span>
        </div>

        <!-- Solar flares inside the window: tap one to scrub to it. -->
        <div v-if="eventMarks.length" class="ts-events">
          <button
            v-for="mark in eventMarks"
            :key="mark.key"
            type="button"
            class="ts-event"
            :class="'is-' + mark.severity"
            :style="{ left: mark.left + '%' }"
            :title="mark.label"
            :aria-label="'Jump to ' + mark.label"
            @click="onMark(mark)"
          ></button>
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

        <p class="ts-label">
          <template v-if="loadingText">{{ loadingText }}</template>
          <template v-else><strong>{{ stampText }}</strong> · {{ ageText }}</template>
        </p>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent } from "vue";

import { kiosk, playing } from "../state/useAppState";

/** How often the "N hours ago" text re-derives from the wall clock. */
const AGE_REFRESH_MS = 60000;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

interface Tick {
  index: number;
  left: number;
  loaded: boolean;
}

/**
 * The 48-hour time control.
 *
 * A native `<input type="range">` on purpose: it is the only slider that gets
 * touch, keyboard and screen-reader behaviour right on every phone for free.
 * Everything below is styling and honest labelling.
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

export default defineComponent({
  name: "TimeScrubber",

  props: {
    /** Frames the manifest promises (13 over 48 h). */
    frameCount: {
      type: Number,
      default: 0,
    },
    /** Oldest index of the contiguous loaded run; frameCount when empty. */
    loadedFrom: {
      type: Number,
      default: 0,
    },
    loadedCount: {
      type: Number,
      default: 0,
    },
    /** Magnetogram time per frame index, unix seconds. */
    times: {
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

    /** Two frames make a cross-fade; three make something worth watching. */
    canPlay(): boolean {
      return this.loadedCount >= 3;
    },

    sliderMax(): number {
      return Math.max(this.frameCount - 1, 0.01);
    },

    atNewest(): boolean {
      return this.frameT >= this.frameCount - 1.001;
    },

    idlePulse(): boolean {
      return this.canPlay && !this.playing && this.atNewest;
    },

    loadingText(): string {
      if (this.loadedCount >= this.frameCount || this.frameCount === 0) { return ""; }
      return `Loading the last ${this.windowHours} hours… ${this.loadedCount} of ${this.frameCount}`;
    },

    ticks(): Tick[] {
      const span = Math.max(this.frameCount - 1, 1);
      const out: Tick[] = [];
      for (let i = 0; i < this.frameCount; i++) {
        out.push({ index: i, left: (i / span) * 100, loaded: i >= this.loadedFrom });
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

    stampText(): string {
      const d = new Date(this.playheadUnix * 1000);
      const hh = String(d.getUTCHours()).padStart(2, "0");
      const mm = String(d.getUTCMinutes()).padStart(2, "0");
      return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${hh}:${mm} UTC`;
    },

    /**
     * The newest frame reads "now". It is really ~1-2 h old (that is what a
     * GONG synoptic magnetogram is), and the stale banner says so when the lag
     * grows — but at the right-hand end of a 48-hour scrubber, "now" is the
     * honest answer to what the guest is asking.
     */
    ageText(): string {
      if (this.atNewest) { return "now"; }
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
  },

  beforeUnmount() {
    window.clearInterval(this.ageTimer);
  },

  methods: {
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
  padding: 0.4rem 0.6rem 0.5rem;
  border-radius: 12px;
  background: rgba(8, 6, 2, 0.72);
  backdrop-filter: blur(6px);
}

.ts-banner {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--sol-accent);
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
  border: 1px solid rgba(255, 200, 80, 0.5);
  border-radius: 50%;
  background: rgba(255, 200, 80, 0.12);
  color: var(--sol-accent);
  font-size: 0.95rem;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;

  &:disabled {
    opacity: 0.35;
    cursor: default;
    border-color: rgba(255, 255, 255, 0.2);
    color: var(--sol-text-dim);
    background: transparent;
  }

  // A resting app should still say "there is more here" — once.
  &.is-idle-pulse {
    animation: ts-pulse 2.6s ease-in-out infinite;
  }
}

@keyframes ts-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255, 200, 80, 0.35); }
  50% { box-shadow: 0 0 0 8px rgba(255, 200, 80, 0); }
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

.ts-event {
  position: absolute;
  top: 2px;
  width: 8px;
  height: 8px;
  margin-left: -4px;
  padding: 0;
  border: none;
  border-radius: 1px;
  transform: rotate(45deg);
  cursor: pointer;
  pointer-events: auto;
  -webkit-tap-highlight-color: transparent;

  // C flares: quiet amber diamonds.
  background: rgba(255, 200, 80, 0.55);

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
    top: 0;
  }

  // CMEs: a circle in the open-field blue, deliberately NOT a diamond and
  // deliberately not on the flare colour ramp. A flare is a flash on the Sun;
  // a CME is something leaving it, and the two must not read as degrees of the
  // same thing even when DONKI links them.
  &.is-cme {
    width: 9px;
    height: 9px;
    margin-left: -4.5px;
    top: 1px;
    border-radius: 50%;
    transform: none;
    background: transparent;
    border: 2px solid var(--sol-accent2, #5fb8ff);
    box-shadow: 0 0 6px rgba(95, 184, 255, 0.55);
  }
}

.ts-tick {
  position: absolute;
  top: 0;
  width: 2px;
  height: 4px;
  margin-left: -1px;
  border-radius: 1px;
  background: rgba(255, 255, 255, 0.16);
  transition: background 200ms ease;

  &.is-loaded {
    background: rgba(255, 200, 80, 0.75);
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
    background: rgba(255, 255, 255, 0.14);
  }

  &::-moz-range-track {
    height: 4px;
    border-radius: 2px;
    background: rgba(255, 255, 255, 0.14);
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
    background: var(--sol-accent);
  }

  &::-moz-range-thumb {
    width: 20px;
    height: 20px;
    border: 2px solid rgba(0, 0, 0, 0.6);
    border-radius: 50%;
    background: var(--sol-accent);
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
