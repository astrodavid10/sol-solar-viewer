<template>
  <section class="sun-stats no-select" aria-label="Live space weather">
    <!-- Storm callout: only when NOAA says geomagnetic storm conditions are in
         effect. For a planetarium crowd this is THE actionable space-weather
         news, so it earns a banner rather than a chip. -->
    <transition-expand>
      <div
        v-if="auroraAlert && !auroraDismissed"
        class="ss-aurora"
        role="status"
        @click="auroraDismissed = true"
      >
        <span class="ss-aurora-glow" aria-hidden="true"></span>
        <span class="ss-aurora-text">{{ auroraAlert }}</span>
        <span class="ss-aurora-hint">tap to dismiss</span>
      </div>
    </transition-expand>

    <div class="ss-grid" :class="'is-' + layout">
      <stat-chip
        v-for="chip in chips"
        :key="chip.key"
        :label="chip.label"
        :value="chip.value"
        :detail="chip.detail"
        :observed-ms="chip.observedMs"
        :stale="chip.stale"
        :active="openKey === chip.key"
        @select="toggle(chip.key)"
      />
    </div>

    <!-- One line, plain language, only when asked for. -->
    <transition-expand>
      <p v-if="explainer" class="ss-explainer">{{ explainer }}</p>
    </transition-expand>
  </section>
</template>

<script lang="ts">
import { defineComponent, PropType } from "vue";

import StatChip from "./StatChip.vue";
import { STALE_MS, useSolarStats } from "../data/useSolarStats";
import { flareLabel, kpLabel, sunspotLabel, windLabel } from "../data/swpc";
import { dataBaseUrl } from "../data/pfss";
import { RegionDay, loadRegionHistory, regionDayAt, utDate } from "../data/regions";
import { sceneUnix } from "../state/useAppState";

interface Chip {
  key: string;
  label: string;
  value: string;
  detail: string;
  observedMs: number | null;
  stale: boolean;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Aug 21" from a `YYYY-MM-DD` UT date, parsed as UTC rather than local. */
function dayLabel(date: string): string {
  const parts = date.split("-");
  const month = Number(parts[1]) - 1;
  if (!(month >= 0 && month < 12)) { return date; }
  return `${MONTHS[month]} ${Number(parts[2])}`;
}

/** One sentence each. No jargon that isn't immediately unpacked. */
const EXPLAINERS: Record<string, string> = {
  flare: "Flares are magnetic explosions on the Sun — NASA labels them A, B, C, M, X, and each letter is ten times stronger than the one before.",
  wind: "The Sun blows a constant stream of charged particles past Earth; at these speeds it makes the trip in about four days.",
  kp: "Kp measures how hard the solar wind is shaking Earth's magnetic field — at 5 and above the northern lights push south.",
  sunspots: "The sunspots NOAA counted that day. Each is an island of magnetism strong enough to cool the surface, and the more there are, the busier the Sun is. NOAA publishes one count per day, so this steps as you scrub rather than sliding.",
};

export default defineComponent({
  name: "SunStats",

  components: { "stat-chip": StatChip },

  props: {
    /**
     * "auto" = 2x2 on a narrow phone, 4x1 above 380 px (media query).
     * "two"  = always 2x2, for the narrow right-hand rail on desktop.
     */
    layout: {
      type: String as PropType<"auto" | "two">,
      default: "auto",
    },
  },

  setup() {
    // Calling the composable is what starts the fetch/poll cycle; the state
    // object it also returns is only needed by the retry affordance, which
    // lives in the disk viewer's error card instead.
    const { stats } = useSolarStats();
    // The moment under the field-line playhead. Reading it here is what makes
    // the sunspot chip follow the scrubber instead of always reporting now.
    return { stats, sceneUnix };
  },

  data() {
    return {
      openKey: "",
      auroraDismissed: false,
      /** `ar/regions.json`'s per-UT-day counts; empty until it loads. */
      history: [] as RegionDay[],
      abort: null as AbortController | null,
    };
  },

  async mounted() {
    // Optional enrichment: an absent or schema-1 product leaves this empty and
    // the chip falls back to the live active-region count.
    this.abort = new AbortController();
    const history = await loadRegionHistory(dataBaseUrl(), this.abort.signal);
    this.history = history;
  },

  beforeUnmount() {
    this.abort?.abort();
  },

  computed: {
    chips(): Chip[] {
      const flare = this.stats.flare;
      const wind = this.stats.wind;
      const kp = this.stats.kp;
      const snapshot = this.stats.snapshot;

      const flareText = flareLabel(flare.value ? flare.value.currentClass : null);
      const windText = windLabel(wind.value);
      const kpText = kpLabel(kp.value);
      const spots = this.spotDay;

      return [
        {
          key: "flare",
          label: "Flare",
          value: flareText.headline,
          detail: flareText.detail,
          observedMs: flare.observedMs,
          stale: this.isStale(flare.fetchedAt),
        },
        {
          key: "wind",
          label: "Solar wind",
          value: windText.headline,
          detail: windText.detail,
          observedMs: wind.observedMs,
          stale: this.isStale(wind.fetchedAt),
        },
        {
          key: "kp",
          label: "Aurora",
          value: kpText.headline,
          detail: kpText.detail,
          observedMs: kp.observedMs,
          stale: this.isStale(kp.fetchedAt),
        },
        {
          key: "sunspots",
          label: "Sunspots",
          value: spots.headline,
          detail: spots.detail,
          // Null on purpose whenever the value belongs to a scrubbed day: the
          // freshness dot answers "how long ago did we MEASURE this", and for a
          // deliberately historical number that question has no useful answer.
          // A green dot beside a three-day-old count would be a lie told in
          // color.
          observedMs: spots.live ? snapshot.observedMs : null,
          stale: false,
        },
      ];
    },

    /**
     * The sunspot chip's value, for the day under the playhead.
     *
     * Three tiers, in order: the published daily history (what this is for),
     * the live active-region count (what the chip showed before the history
     * existed, and the fallback for an old data tree), and "—".
     *
     * `live` says which, so the caller knows whether a freshness dot means
     * anything.
     */
    spotDay(): { headline: string; detail: string; live: boolean } {
      const day = regionDayAt(this.history, this.sceneUnix);
      if (day) {
        const regions = day.spottedRegionCount === 1
          ? "1 spotted region" : `${day.spottedRegionCount} spotted regions`;
        // Name the date always, not just when scrubbed: NOAA issues one report
        // a day, so even "now" is a number with a date on it, and saying so is
        // what stops the chip implying a live count it never had.
        const today = utDate(Date.now() / 1000);
        const when = day.date === today ? "today" : dayLabel(day.date);
        return {
          headline: String(day.spotCount),
          detail: `${regions} · ${when}`,
          live: day.date === today,
        };
      }
      const snapshot = this.stats.snapshot;
      const text = sunspotLabel(snapshot.value ? snapshot.value.activeRegions : null);
      return {
        headline: text.headline,
        detail: snapshot.value ? text.detail : "daily count",
        live: true,
      };
    },

    explainer(): string {
      return this.openKey ? EXPLAINERS[this.openKey] ?? "" : "";
    },

    /**
     * Non-empty exactly when a geomagnetic storm is observed or in effect:
     * measured Kp >= 5, or NOAA's G scale >= 1 for today. Copy scales with
     * severity — a G3+ night deserves stronger wording than a G1 blip.
     */
    auroraAlert(): string {
      const kp = this.stats.kp.value;
      const g = this.stats.scales.value ? this.stats.scales.value.gScale : null;
      const gLevel = g ?? 0;
      const storming = (kp !== null && kp >= 5) || gLevel >= 1;
      if (!storming) { return ""; }
      if (gLevel >= 3 || (kp !== null && kp >= 7)) {
        return "Strong geomagnetic storm — aurora may be visible unusually far south tonight!";
      }
      return "Geomagnetic storm conditions — aurora may be visible tonight at high latitudes!";
    },
  },

  methods: {
    /**
     * Staleness is measured from OUR last successful fetch, not from the
     * observation time. Kp is only published every three hours, so a two-hour-old
     * Kp is the newest number that exists — dimming it would be a lie. What
     * deserves dimming is a value we haven't been able to refresh: the
     * localStorage cache a returning guest sees before the network answers.
     * The freshness dot still reports the observation age honestly.
     */
    isStale(fetchedAt: number): boolean {
      if (!fetchedAt) { return false; }
      return Date.now() - fetchedAt > STALE_MS;
    },

    toggle(key: string): void {
      this.openKey = this.openKey === key ? "" : key;
    },
  },
});
</script>

<style lang="less" scoped>
.sun-stats {
  width: 100%;
  padding: 0.2rem 0.75rem 0.4rem;
}

// Content-driven, not breakpoint-driven. This was `repeat(2, 1fr)` with a
// `@media (min-width: 381px)` override to `repeat(4, 1fr)`, which meant a
// 390 px phone -- the single most common size there is -- got four 87 px
// columns and clipped every chip: "Small flare", "Solar wind", "392 km/s" and
// "5 spotted regions · today" all ran past their boxes (measured in a browser
// at 390x844, 2026-08-23).
//
// 150px is the measured floor: the widest chip content is "876,904 mph" and
// "5 spotted regions · today", and both fit above it. auto-fit then chooses
// 2 columns on a phone and 4 as soon as there is room, with no breakpoint to
// get wrong -- and it cannot clip, because the track can never be narrower
// than the content needs.
.ss-grid {
  display: grid;
  gap: 0.4rem;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
}

// Two 150px columns cost 150*2 + the 0.4rem gap + `.sun-stats`'s own
// 0.75rem*2 side padding = 330.4px of viewport (E6). Below that -- an
// iPhone SE 1st gen (320px) or a Galaxy Fold's cover screen (~280px) --
// there is nowhere left for a second column to shrink to: 150px is already
// the measured floor for THIS content (comment above -- "876,904 mph" and
// "5 spotted regions · today" both need it), so lowering the floor would
// bring back the exact clipping bug that comment describes. `.sol-root`'s
// `overflow: hidden` (sol.vue) then clips the row instead of scrolling it,
// silently. A single column below the breakeven point costs vertical
// space, never truncated text -- the floor stays exactly where the comment
// above says it has to.
@media (max-width: 340px) {
  .ss-grid {
    grid-template-columns: 1fr;
  }
}

// The desktop rail is a fixed narrow column, so it always wants 2x2 -- there
// auto-fit would give 2 anyway, but saying so keeps the rail stable while the
// window is dragged rather than flipping to 4 at some incidental width.
.ss-grid.is-two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

// Roomier than a small phone in portrait: one row of four reads better than
// a 2x2 block, and keeps the disk taller.
.ss-explainer {
  margin: 0.4rem 0 0;
  color: var(--sol-text-dim);
  font-size: 0.75rem;
  line-height: 1.35;
}

// Aurora storm callout — the one loud element in the app, on purpose.
.ss-aurora {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 0.45rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid rgba(90, 235, 170, 0.5);
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  background: linear-gradient(100deg, rgba(20, 60, 45, 0.9), rgba(25, 45, 70, 0.9));
}

.ss-aurora-glow {
  position: absolute;
  inset: 0;
  background: linear-gradient(100deg, transparent 20%, rgba(90, 235, 170, 0.22) 50%, transparent 80%);
  background-size: 220% 100%;
  animation: ss-aurora-sweep 3.6s ease-in-out infinite;
  pointer-events: none;
}

@keyframes ss-aurora-sweep {
  0% { background-position: 120% 0; }
  100% { background-position: -120% 0; }
}

.ss-aurora-text {
  position: relative;
  color: #b8ffd9;
  font-size: 0.82rem;
  font-weight: 600;
  line-height: 1.3;
}

.ss-aurora-hint {
  position: relative;
  margin-left: auto;
  color: var(--sol-text-dim);
  font-size: 0.65rem;
  white-space: nowrap;
}
</style>
