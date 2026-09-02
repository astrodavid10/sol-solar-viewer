import { createApp } from "vue";

import KioskStatsPanel from "./components/KioskStatsPanel.vue";
import TransitionExpand from "./components/TransitionExpand.vue";
import sol from "./sol.vue";
import { boolParam } from "./urlParams";
import "./assets/common.less";
import "./assets/sol.less";

// NOTE: Vuetify was removed on 2026-09-02. It was loaded for exactly one
// `<v-app>` wrapper in sol.vue and cost 587 KB / 85 KB-gzip of
// render-blocking CSS plus 3.6 MB of Material Design Icons webfonts for
// glyphs this app never draws (every icon here is a FontAwesome SVG). The
// parts of its reset the layout actually depended on now live explicitly at
// the top of assets/common.less. Do not reintroduce it for a component or
// two — reach for a plain element first.

import { FontAwesomeIcon } from "@fortawesome/vue-fontawesome";
import { library } from "@fortawesome/fontawesome-svg-core";
import {
  faCheck,
  faCircleInfo,
  faLayerGroup,
  faPause,
  faPlay,
  faQrcode,
  faRotateLeft,
  faShareNodes,
  faStop,
  faTimes,
} from "@fortawesome/free-solid-svg-icons";
library.add(faCheck);
library.add(faCircleInfo);
library.add(faLayerGroup);
library.add(faPause);
library.add(faPlay);
library.add(faQrcode);
library.add(faRotateLeft);
library.add(faShareNodes);
library.add(faStop);
library.add(faTimes);

// iOS Safari: prevent page-level pinch zoom (the app handles its own pinch
// gestures on the disk image and the 3D canvas).
document.addEventListener("gesturestart", (e) => e.preventDefault(), { passive: false });

// ?kioskStats=1 → mount the standalone usage-stats panel instead of the app
// (no engine boot needed). See kiosk/kioskStats.ts.
if (boolParam("kioskStats")) {
  createApp(KioskStatsPanel).mount("#app");
} else {
  // NOTE: @wwtelescope/engine-pinia is deliberately NOT imported here — the
  // WWT engine (~330 KB gz) loads only when the guest opens the 3D view.
  // SolarView3D's async loader installs wwtPinia on this app post-mount.
  createApp(sol, {
    // Kiosk mode (lobby touchscreen): turned on by ?kiosk=1.
    kioskMode: boolParam("kiosk"),
    // Canonical public URL for the take-home QR code shown in kiosk mode.
    // Must be absolute: an empty value falls back to deriving it from the
    // current URL, which on an exhibit machine is a localhost/LAN address the
    // guest's phone cannot reach. Set this when the production URL is known.
    kioskHomeUrl: "",
  })
    .component("font-awesome-icon", FontAwesomeIcon)
    .component("transition-expand", TransitionExpand)
    .mount("#app");
}
