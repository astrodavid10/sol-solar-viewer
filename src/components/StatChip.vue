<template>
  <button
    type="button"
    class="stat-chip no-select"
    :class="{ 'is-active': active, 'is-stale': stale }"
    :aria-pressed="active"
    @click="$emit('select')"
  >
    <span class="sc-top">
      <span class="sc-label">{{ label }}</span>
      <!-- Freshness is never hidden: green under 15 min, amber under an hour,
           gray beyond. The title carries the actual time for anyone who cares. -->
      <span class="sc-dot" :class="'is-' + tier" :title="freshnessTitle"></span>
    </span>
    <span class="sc-value">{{ value }}</span>
    <span class="sc-detail">{{ detailText }}</span>
  </button>
</template>

<script lang="ts">
import { defineComponent, PropType } from "vue";

import { agoLabel, clockLabel, freshnessTier } from "../data/swpc";

export default defineComponent({
  name: "StatChip",

  props: {
    label: { type: String, required: true },
    /** Big, plain-language headline: "Quiet", "427 km/s", "Storm — aurora possible!". */
    value: { type: String, required: true },
    /** Small print under it: the actual number or class. */
    detail: { type: String, default: "" },
    /** Observation time, epoch ms. null when we have nothing. */
    observedMs: { type: Number as PropType<number | null>, default: null },
    /** Older than the staleness threshold: dim it and say when. */
    stale: { type: Boolean, default: false },
    /** This chip's explainer is showing. */
    active: { type: Boolean, default: false },
  },

  emits: ["select"],

  computed: {
    tier(): string {
      return freshnessTier(this.observedMs);
    },

    detailText(): string {
      if (this.stale && this.observedMs !== null) {
        return `as of ${clockLabel(this.observedMs)}`;
      }
      return this.detail;
    },

    freshnessTitle(): string {
      if (this.observedMs === null) { return "No measurement yet"; }
      return `Measured ${agoLabel(this.observedMs)} (${clockLabel(this.observedMs)})`;
    },
  },
});
</script>

<style lang="less" scoped>
.stat-chip {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.1rem;
  min-height: 56px;
  padding: 0.4rem 0.6rem;
  // Deliberately identical to `.lp-segment` in LayerPanel.vue: hairline border,
  // the shared control radius, transparent ground. These are the same KIND of
  // thing -- a tappable tile inside a panel -- and they sit one above the other
  // in the desktop rail, so any difference reads as an accident.
  border: 1px solid var(--sol-hairline);
  border-radius: var(--sol-control-radius);
  background: transparent;
  color: var(--sol-text);
  text-align: left;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: border-color 150ms ease, background 160ms ease, opacity 200ms ease;

  &:hover {
    background: var(--sol-hover);
  }

  &:focus-visible {
    outline: 2px solid var(--sol-select);
    outline-offset: -2px;
  }

  // The layer panel's "on" treatment, to the letter: brighter border, faint
  // neutral fill, full-strength text. Three signals, not one hue.
  &.is-active {
    border-color: rgba(var(--sol-select-rgb), 0.75);
    background: rgba(var(--sol-select-rgb), 0.14);
  }

  // Stale values stay visible but stop shouting — they are last-known, not now.
  &.is-stale {
    opacity: 0.6;
  }
}

.sc-top {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  width: 100%;
}

.sc-label {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 0.62rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sol-text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sc-dot {
  flex: 0 0 auto;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #6b6b6b;

  &.is-fresh {
    background: #58d68d;
  }

  &.is-recent {
    background: #f0b429;
  }

  &.is-old {
    background: #6b6b6b;
  }
}

.sc-value {
  font-size: 1.02rem;
  font-weight: 700;
  line-height: 1.15;
  color: var(--sol-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.sc-detail {
  font-size: 0.66rem;
  color: var(--sol-text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
</style>
