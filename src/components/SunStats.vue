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

interface Chip {
  key: string;
  label: string;
  value: string;
  detail: string;
  observedMs: number | null;
  stale: boolean;
}

/** One sentence each. No jargon that isn't immediately unpacked. */
const EXPLAINERS: Record<string, string> = {
  flare: "Flares are magnetic explosions on the Sun — NASA labels them A, B, C, M, X, and each letter is ten times stronger than the one before.",
  wind: "The Sun blows a constant stream of charged particles past Earth; at these speeds it makes the trip in about four days.",
  kp: "Kp measures how hard the solar wind is shaking Earth's magnetic field — at 5 and above the northern lights push south.",
  sunspots: "Sunspots are dark, cooler islands of intense magnetism; the more of them there are, the busier the Sun is.",
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
    return { stats };
  },

  data() {
    return {
      openKey: "",
      auroraDismissed: false,
    };
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
      const spotText = sunspotLabel(snapshot.value ? snapshot.value.sunspotNumber : null);

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
          value: spotText.headline,
          // The snapshot comes from the daily pipeline run, which may simply
          // not exist yet — that is a "—", not an error.
          detail: snapshot.value ? spotText.detail : "daily count",
          observedMs: snapshot.observedMs,
          stale: false,
        },
      ];
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

.ss-grid {
  display: grid;
  gap: 0.4rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

// Roomier than a small phone in portrait: one row of four reads better than
// a 2x2 block, and keeps the disk taller.
@media (min-width: 381px) {
  .ss-grid.is-auto {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

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
