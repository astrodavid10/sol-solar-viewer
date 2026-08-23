<template>
  <header class="sol-topbar sol-chrome no-select">
    <div class="tb-brand">
      <span class="tb-title">Sol</span>
      <span class="tb-subtitle">the Sun right now</span>
    </div>

    <div class="tb-actions">
      <!-- Web Share of the current deep link (the URL already carries
           view/channel state). Hidden on the kiosk — guests take THAT home via
           the QR pill, and the exhibit machine shouldn't open share sheets. -->
      <button
        v-if="!kiosk"
        type="button"
        class="tb-icon-btn"
        aria-label="Share this view"
        :title="copied ? 'Link copied!' : 'Share this view'"
        @click="share"
      >
        <font-awesome-icon :icon="copied ? 'check' : 'share-nodes'" />
      </button>

      <!-- Redundant on desktop: the rail keeps the info panel open. -->
      <button
        v-if="!wide"
        type="button"
        class="tb-icon-btn"
        aria-label="About this app"
        title="What am I looking at?"
        @click="$emit('info')"
      >
        <font-awesome-icon icon="circle-info" />
      </button>
    </div>
  </header>
</template>

<script lang="ts">
import { defineComponent } from "vue";

import { kiosk, wide } from "../state/useAppState";

export default defineComponent({
  name: "TopBar",
  emits: ["info"],

  setup() {
    return { kiosk, wide };
  },

  data() {
    return {
      copied: false,
      copiedTimer: 0,
    };
  },

  beforeUnmount() {
    window.clearTimeout(this.copiedTimer);
  },

  methods: {
    /**
     * Native share sheet where available (every phone), clipboard fallback on
     * desktop. location.href is already the canonical deep link — useDeepLink
     * keeps ?view=&wl=… in step with the app state.
     */
    async share(): Promise<void> {
      const url = window.location.href;
      const nav = navigator as Navigator & { share?: (data: { title: string; url: string }) => Promise<void> };
      if (nav.share) {
        try {
          await nav.share({ title: "Sol — the Sun right now", url });
        } catch {
          // Guest closed the sheet — not an error.
        }
        return;
      }
      try {
        await navigator.clipboard.writeText(url);
        this.copied = true;
        window.clearTimeout(this.copiedTimer);
        this.copiedTimer = window.setTimeout(() => { this.copied = false; }, 2000);
      } catch {
        // Clipboard blocked (http:// LAN testing) — the button just does nothing.
      }
    },
  },
});
</script>

<style lang="less" scoped>
.sol-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  min-height: 44px;
  // Notched phones in portrait: the status bar overlaps the top of the page
  // because index.html asks for viewport-fit=cover.
  padding: env(safe-area-inset-top) 0.75rem 0 0.75rem;
}

.tb-brand {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  min-width: 0;
}

.tb-title {
  font-family: "Overpass", system-ui, sans-serif;
  font-weight: 600;
  font-size: 1.5rem;
  line-height: 1.1;
  color: var(--sol-accent);
}

.tb-subtitle {
  font-size: 0.85rem;
  color: var(--sol-text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tb-actions {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
}

.tb-icon-btn {
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--sol-text);
  font-size: 1.15rem;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;

  &:hover {
    color: var(--sol-accent);
  }
}
</style>
