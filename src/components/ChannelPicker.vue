<template>
  <div class="channel-picker no-select">
    <div ref="row" class="cp-row">
      <button
        v-for="item in shownProducts"
        :key="item.id"
        :ref="(el) => registerChip(item.id, el)"
        type="button"
        class="cp-chip"
        :class="{ 'is-active': item.id === channel }"
        :aria-pressed="item.id === channel"
        @click="select(item.id)"
        @pointerenter="warm(item.id)"
        @touchstart.passive="warm(item.id)"
      >
        <span class="cp-label">{{ item.label }}</span>
        <!-- Always rendered (min-height in CSS) so chips with and without a
             temperature line up on the same baseline. -->
        <span class="cp-temp">{{ item.tempLabel || '' }}</span>
      </button>

      <button
        v-if="!showExtras"
        type="button"
        class="cp-chip cp-more"
        @click="revealExtras"
      >
        <span class="cp-label">More</span>
        <span class="cp-temp">2 more</span>
      </button>
    </div>
  </div>
</template>

<script lang="ts">
import { ComponentPublicInstance, defineComponent } from "vue";

import {
  EXTRA_PRODUCTS,
  PRIMARY_PRODUCTS,
  Product,
  ProductId,
  hasAnyMovie,
  stillUrl,
} from "../data/sdoCatalog";
import { channel, diskMode, diskSettledAt, pfssOverlay } from "../state/useAppState";

/** Resolution used for every speculative load. Never 2048/4096 — see prefetch(). */
const PREFETCH_RES = 1024;

export default defineComponent({
  name: "ChannelPicker",

  setup() {
    return { channel, diskMode, diskSettledAt, pfssOverlay };
  },

  data() {
    return {
      showExtras: false,
      /** URLs already warmed this session, so we never re-request one. */
      warmed: new Set<string>(),
      chips: {} as Record<string, HTMLElement>,
    };
  },

  computed: {
    shownProducts(): readonly Product[] {
      return this.showExtras
        ? [...PRIMARY_PRODUCTS, ...EXTRA_PRODUCTS]
        : PRIMARY_PRODUCTS;
    },
  },

  watch: {
    channel(id: ProductId) {
      // Deep links and the kiosk attract loop change the channel from outside;
      // make sure the active chip is actually on screen.
      if (EXTRA_PRODUCTS.some((p) => p.id === id)) { this.showExtras = true; }
      void this.$nextTick(() => this.scrollActiveIntoView());
    },

    /**
     * Prefetch the neighbours ONLY once the image the guest asked for has
     * settled — a speculative 1024 must never compete for bandwidth with the
     * 2048 on screen.
     */
    diskSettledAt() {
      this.prefetchNeighbours();
    },
  },

  mounted() {
    this.scrollActiveIntoView();
  },

  methods: {
    registerChip(id: string, el: Element | ComponentPublicInstance | null): void {
      if (el instanceof HTMLElement) {
        this.chips[id] = el;
      } else {
        delete this.chips[id];
      }
    },

    select(id: ProductId): void {
      this.channel = id;
      // Movie mode can't survive a channel with no movie published.
      if (this.diskMode === "movie" && !hasAnyMovie(id)) { this.diskMode = "still"; }
    },

    revealExtras(): void {
      this.showExtras = true;
    },

    /**
     * Warm a channel on hover/touch-start — the 1024 arrives while the finger
     * is still on the glass, so the tap feels instant. 1024 only: a warm-up
     * that costs 700 KB is not a warm-up.
     */
    warm(id: ProductId): void {
      const url = stillUrl(id, PREFETCH_RES, this.pfssOverlay);
      if (this.warmed.has(url)) { return; }
      this.warmed.add(url);
      const img = new Image();
      img.decoding = "async";
      img.src = url;
    },

    prefetchNeighbours(): void {
      const list = this.shownProducts;
      const index = list.findIndex((p) => p.id === this.channel);
      if (index < 0) { return; }
      [index - 1, index + 1].forEach((i) => {
        if (i >= 0 && i < list.length) { this.warm(list[i].id); }
      });
    },

    scrollActiveIntoView(): void {
      const chip = this.chips[this.channel];
      const row = this.$refs.row as HTMLElement | undefined;
      if (!chip || !row) { return; }
      // Manual scrollLeft rather than scrollIntoView: the latter also scrolls
      // ancestors, which on a phone drags the whole layout around.
      const target = chip.offsetLeft - (row.clientWidth - chip.clientWidth) / 2;
      row.scrollTo({ left: Math.max(0, target), behavior: "smooth" });
    },
  },
});
</script>

<style lang="less" scoped>
.channel-picker {
  width: 100%;
}

.cp-row {
  display: flex;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
  overflow-x: auto;
  overflow-y: hidden;
  // One row that scrolls sideways, snapping chip to chip. pan-x (not none):
  // the row must scroll horizontally while vertical drags still belong to the
  // page/stage.
  touch-action: pan-x;
  scroll-snap-type: x proximity;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;

  &::-webkit-scrollbar {
    display: none;
  }
}

.cp-chip {
  flex: 0 0 auto;
  scroll-snap-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.05rem;
  min-height: 44px;
  padding: 0.3rem 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--sol-text);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: border-color 150ms ease, color 150ms ease, background 150ms ease;

  &.is-active {
    border-color: var(--sol-accent);
    background: rgba(255, 200, 80, 0.12);
    color: var(--sol-accent);
  }
}

.cp-label {
  font-size: 0.85rem;
  font-weight: 600;
  white-space: nowrap;
}

.cp-temp {
  min-height: 0.85rem;
  font-size: 0.65rem;
  color: var(--sol-text-dim);
  white-space: nowrap;
}

.cp-chip.is-active .cp-temp {
  color: rgba(255, 200, 80, 0.75);
}

.cp-more {
  border-style: dashed;
}
</style>
