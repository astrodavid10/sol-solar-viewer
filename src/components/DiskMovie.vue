<template>
  <div class="disk-movie no-select">
    <!-- NOTHING has downloaded at this point: preload="none" plus no src at
         all until the guest picks an option, with the size in the button. A
         33 MB surprise on a phone plan is not a feature. -->
    <div v-if="!src" class="dm-choices" :style="posterStyle">
      <p class="dm-prompt">Watch the Sun move</p>

      <button
        v-for="option in options"
        :key="option.key"
        type="button"
        class="dm-btn"
        @click="choose(option.key)"
      >
        <font-awesome-icon icon="play" class="dm-btn-icon" />
        <span class="dm-btn-label">{{ option.label }}</span>
        <span class="dm-btn-size">~{{ option.sizeMb }} MB</span>
      </button>

      <p v-if="options.length === 0" class="dm-note">
        No movie is published for this channel.
      </p>
      <p v-else-if="metered" class="dm-note">
        Looks like you're on a slower connection — the shorter movie is first.
      </p>

      <button type="button" class="dm-link" @click="$emit('exit')">Back to the live image</button>
    </div>

    <div v-else class="dm-player">
      <video
        ref="video"
        class="dm-video"
        :src="src"
        :poster="poster"
        :autoplay="autoplay"
        playsinline
        muted
        loop
        controls
        preload="none"
        @progress="onProgress"
        @loadedmetadata="onProgress"
        @error="onError"
      ></video>

      <div class="dm-bar">
        <span class="dm-bar-label">{{ statusLabel }}</span>
        <!-- Download progress, straight from the element's buffered ranges. -->
        <span v-if="bufferedPct < 100" class="dm-progress">
          <span class="dm-progress-fill" :style="{ width: bufferedPct + '%' }"></span>
        </span>
        <button type="button" class="dm-stop" @click="stop">
          <font-awesome-icon icon="stop" />
          <span>Stop</span>
        </button>
      </div>

      <p v-if="failed" class="dm-note dm-note-error">
        That movie isn't on NASA's server yet. Try the other option, or come back later.
      </p>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, PropType } from "vue";

import { isMetered } from "../data/connection";
import {
  DAILY_MOVIE_MB,
  ProductId,
  dailyMovieUrl,
  latestMovieUrl,
  posterUrl,
  product,
  utcDaysAgo,
} from "../data/sdoCatalog";
import { kiosk } from "../state/useAppState";

type MovieKey = "latest" | "daily";

interface MovieOption {
  key: MovieKey;
  label: string;
  sizeMb: number;
}

/** Daily movies appear a few hours after the UTC day closes, so start at -1. */
const FIRST_DAILY_OFFSET = 1;
/** How far back to walk before giving up on the daily movie. */
const MAX_DAILY_OFFSET = 3;

export default defineComponent({
  name: "DiskMovie",

  props: {
    productId: {
      type: String as PropType<ProductId>,
      required: true,
    },
  },

  emits: ["exit"],

  setup() {
    return { kiosk };
  },

  data() {
    return {
      src: "",
      choice: null as MovieKey | null,
      dailyOffset: FIRST_DAILY_OFFSET,
      bufferedPct: 0,
      failed: false,
      autoplay: false,
    };
  },

  computed: {
    metered(): boolean {
      return isMetered();
    },

    poster(): string {
      return posterUrl(this.productId);
    },

    posterStyle(): Record<string, string> {
      return { backgroundImage: `url("${this.poster}")` };
    },

    /**
     * The daily 24 h file goes first on a metered connection, and it is the
     * only option at all for the HMI channels (no 48 h movie is published for
     * them). Otherwise the rolling 48 h movie leads — it's the better story.
     */
    options(): MovieOption[] {
      const info = product(this.productId);
      const list: MovieOption[] = [];
      if (info.hasLatestMovie) {
        list.push({
          key: "latest",
          label: "Last 48 hours",
          sizeMb: info.approxMovieMb ?? 35,
        });
      }
      if (info.hasDailyMovie) {
        list.push({
          key: "daily",
          label: "Yesterday, 24h",
          sizeMb: info.approxDailyMovieMb ?? DAILY_MOVIE_MB,
        });
      }
      // Metered: cheapest first. (Not a blind reverse — for 0094 the daily file
      // is 41 MB against 100 MB, so the order genuinely depends on the numbers.)
      if (this.metered) { list.sort((a, b) => a.sizeMb - b.sizeMb); }
      return list;
    },

    statusLabel(): string {
      if (this.choice === "daily") {
        const date = utcDaysAgo(this.dailyOffset);
        const label = date.toLocaleDateString([], { month: "short", day: "numeric" });
        return `24 hours of ${label} (UTC)`;
      }
      return "The last 48 hours";
    },
  },

  watch: {
    productId() {
      // A different channel is a different movie — unload before anything else.
      this.abort();
    },
  },

  mounted() {
    // Kiosks have no data plan and no one to tap play.
    if (this.kiosk && this.options.length > 0) {
      this.autoplay = true;
      this.choose(this.options[0].key);
    }
  },

  beforeUnmount() {
    this.abort();
  },

  methods: {
    choose(key: MovieKey): void {
      this.failed = false;
      this.choice = key;
      this.bufferedPct = 0;
      this.dailyOffset = FIRST_DAILY_OFFSET;
      this.src = key === "latest"
        ? latestMovieUrl(this.productId)
        : dailyMovieUrl(this.productId, utcDaysAgo(this.dailyOffset));
      // The click IS the user gesture, so an explicit play() is allowed here
      // (and muted autoplay would be allowed anyway).
      void this.$nextTick(() => {
        const video = this.$refs.video as HTMLVideoElement | undefined;
        if (video) { void video.play().catch(() => { /* controls remain */ }); }
      });
    },

    onProgress(): void {
      const video = this.$refs.video as HTMLVideoElement | undefined;
      if (!video || !Number.isFinite(video.duration) || video.duration <= 0) { return; }
      const ranges = video.buffered;
      if (ranges.length === 0) { return; }
      const end = ranges.end(ranges.length - 1);
      this.bufferedPct = Math.min(100, Math.round((end / video.duration) * 100));
    },

    onError(): void {
      // Yesterday's daily movie may not be published yet — walk back a day.
      if (this.choice === "daily" && this.dailyOffset < MAX_DAILY_OFFSET) {
        this.dailyOffset += 1;
        this.src = dailyMovieUrl(this.productId, utcDaysAgo(this.dailyOffset));
        return;
      }
      this.failed = true;
    },

    /**
     * Detach the source so the browser ABORTS the download in progress —
     * "Stop" on a 33 MB file has to actually stop the bytes, not just the
     * pixels. Clearing the attribute (rather than setting src="") avoids
     * browsers re-resolving "" against the page URL.
     */
    abort(): void {
      const video = this.$refs.video as HTMLVideoElement | undefined;
      if (video) {
        video.pause();
        video.removeAttribute("src");
        video.load();
      }
      this.src = "";
      this.choice = null;
      this.bufferedPct = 0;
      this.autoplay = false;
    },

    stop(): void {
      this.abort();
      this.$emit("exit");
    },
  },
});
</script>

<style lang="less" scoped>
.disk-movie {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  width: 100%;
}

.dm-choices {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.7rem;
  padding: 1rem;
  min-height: 0;
  // The 512 still doubles as the poster behind the play buttons: it is almost
  // certainly already in cache from the chip prefetch, so this costs nothing.
  background-position: center;
  background-size: contain;
  background-repeat: no-repeat;
  background-color: #000;
}

.dm-prompt {
  margin: 0;
  padding: 0.2rem 0.7rem;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.55);
  color: var(--sol-text);
  font-size: 1rem;
  font-weight: 600;
}

.dm-btn {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  min-height: 44px;
  min-width: min(88%, 18rem);
  padding: 0 1rem;
  border: 1px solid var(--sol-accent);
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.72);
  color: var(--sol-accent);
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
}

.dm-btn-icon {
  flex: 0 0 auto;
}

.dm-btn-label {
  flex: 1 1 auto;
  text-align: left;
}

.dm-btn-size {
  flex: 0 0 auto;
  color: var(--sol-text-dim);
  font-size: 0.8rem;
  font-weight: 400;
}

.dm-note {
  margin: 0;
  max-width: 20rem;
  padding: 0.3rem 0.6rem;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.55);
  color: var(--sol-text-dim);
  font-size: 0.75rem;
  text-align: center;
}

.dm-note-error {
  color: var(--sol-accent);
}

.dm-link {
  padding: 0.4rem 0.6rem;
  border: none;
  background: none;
  color: var(--sol-text-dim);
  font-size: 0.8rem;
  text-decoration: underline;
  cursor: pointer;
}

.dm-player {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.dm-video {
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
  background: #000;
  object-fit: contain;
}

.dm-bar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.35rem 0.6rem;
}

.dm-bar-label {
  color: var(--sol-text-dim);
  font-size: 0.78rem;
}

.dm-progress {
  flex: 1 1 auto;
  height: 3px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.15);
  overflow: hidden;
}

.dm-progress-fill {
  display: block;
  height: 100%;
  background: var(--sol-accent);
  transition: width 200ms linear;
}

.dm-stop {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  min-height: 36px;
  padding: 0 0.7rem;
  margin-left: auto;
  border: 1px solid var(--sol-text-dim);
  border-radius: 8px;
  background: transparent;
  color: var(--sol-text);
  font-size: 0.8rem;
  cursor: pointer;
}
</style>
