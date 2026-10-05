import { defineConfig } from "vitest/config";

// App unit tests (docs/PLAN-2026-10.md item 4.0). Node environment: the code
// under test is pure arithmetic or uses only URL/three, and the WWT engine's
// UMD bundle loads in plain Node, which is what lets winding.test.ts build its
// matrices with the engine's own functions.
export default defineConfig({
  test: {
    include: ["tests/app/**/*.test.ts"],
    environment: "node",
    // Guest-facing stamps are local time (src/data/guestTime.ts). Pinning the
    // zone keeps their expected strings the same on every machine and runner.
    env: { TZ: "UTC" },
  },
});
