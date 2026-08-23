<template>
  <div class="view-switcher no-select" role="tablist" aria-label="View">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      type="button"
      class="vs-tab"
      :class="{ 'is-active': view === tab.id }"
      role="tab"
      :aria-selected="view === tab.id"
      @click="view = tab.id"
    >
      {{ tab.label }}
    </button>
  </div>
</template>

<script lang="ts">
import { defineComponent } from "vue";

import { ViewId, view } from "../state/useAppState";

interface Tab {
  id: ViewId;
  label: string;
}

const TABS: Tab[] = [
  { id: "disk", label: "Sun Now" },
  { id: "3d", label: "3D" },
];

export default defineComponent({
  name: "ViewSwitcher",

  setup() {
    return { view };
  },

  computed: {
    tabs(): Tab[] {
      return TABS;
    },
  },
});
</script>

<style lang="less" scoped>
.view-switcher {
  display: flex;
  align-self: center;
  margin: 0.15rem 0 0.3rem;
  padding: 2px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
}

.vs-tab {
  min-height: 36px;
  min-width: 5.5rem;
  padding: 0 1rem;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--sol-text-dim);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: background 150ms ease, color 150ms ease;

  &.is-active {
    background: rgba(255, 200, 80, 0.16);
    color: var(--sol-accent);
  }
}
</style>
