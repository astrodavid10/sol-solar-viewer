<template>
  <div ref="root" class="solar-view-3d">
    <!-- The engine's own div; the canvas is appended inside it. -->
    <WorldWideTelescope wwt-namespace="wwt-sol" />

    <!-- Everything below floats over the canvas. The layer itself is
         click-through; individual controls opt back in. -->
    <div class="sv-overlay">
      <div class="sv-labels">
        <spacecraft-label
          v-for="chip in chips"
          v-show="chip.visible && layers.spacecraft"
          :key="chip.id"
          :name="chip.name"
          :detail="chip.detail"
          :color="chip.color"
          :x="chip.x"
          :y="chip.y"
          :selected="selectedId === chip.id"
          @select="select(chip.id)"
        />

        <!-- Places ON the Sun. Deliberately NOT gated on layers.fieldLines:
             the regions belong to the surface, and they are the anchors the
             whole 3D story hangs on. -->
        <region-label
          v-for="chip in regionChips"
          v-show="chip.visible"
          :key="chip.id"
          :label="chip.label"
          :description="chip.description"
          :x="chip.x"
          :y="chip.y"
          :selected="selectedId === chip.id"
          @select="select(chip.id)"
        />

        <region-label
          v-show="earthChip.visible"
          variant="earth"
          glyph="⊕"
          :label="earthChip.label"
          :description="earthChip.description"
          :x="earthChip.x"
          :y="earthChip.y"
          :selected="selectedId === earthChip.id"
          @select="select(earthChip.id)"
        />
      </div>

      <div class="sv-buttons">
        <button
          type="button"
          class="sv-icon-btn"
          aria-label="Recentre the Sun"
          title="Recentre the Sun"
          @click="recentre"
        >
          <font-awesome-icon icon="rotate-left" />
        </button>
        <button
          type="button"
          class="sv-icon-btn"
          v-if="!wide"
          :class="{ 'is-active': sheet === 'layers' }"
          aria-label="Layers"
          title="Layers"
          @click="toggleLayers"
        >
          <font-awesome-icon icon="layer-group" />
        </button>
      </div>

      <transition name="fade">
        <div v-if="!wide && sheet === 'layers'" class="sv-layer-popover">
          <layer-panel />
        </div>
      </transition>

      <!-- The far side is never observed from Earth. The sphere dims it, and
           this says why once the guest has actually turned it into view --
           without it the dimming reads as a rendering fault. -->
      <transition name="fade">
        <p v-if="unobserved > 0.55" class="sv-unobserved">
          You're looking at the Sun's far side — no telescope sees this half
          from Earth, so it isn't a photograph.
        </p>
      </transition>

      <!-- One card slot, three kinds of subject: a spacecraft, an active
           region, or the sub-Earth marker. `selectedId` says which. -->
      <transition name="fade">
        <div v-if="selectedCard" class="sv-card">
          <button
            type="button"
            class="sv-card-close"
            aria-label="Close"
            @click="selectedId = ''"
          >
            <font-awesome-icon icon="times" />
          </button>
          <h3 class="sv-card-title">{{ selectedCard.name }}</h3>
          <p v-if="selectedCard.detail" class="sv-card-dist">{{ selectedCard.detail }}</p>
          <p v-if="selectedCard.compare" class="sv-card-compare">{{ selectedCard.compare }}</p>
          <p v-if="selectedCard.blurb" class="sv-card-blurb">{{ selectedCard.blurb }}</p>
          <p v-if="selectedCard.warn" class="sv-card-warn">{{ selectedCard.warn }}</p>
        </div>
      </transition>

      <div class="sv-bottom">
        <p v-if="fieldLinesAbsent" class="sv-note">
          Field lines aren't available right now — the rest of the view still works.
        </p>
        <time-scrubber
          v-else-if="frameCount > 0"
          :frame-count="frameCount"
          :loaded-from="loadedFrom"
          :loaded-count="loadedCount"
          :times="frameTimes"
          :frame-t="frameT"
          :stale="dataStale"
          :stale-hours="dataStaleHours"
          :events="flareMarks"
          @scrub="onScrub"
          @grab="onGrab"
          @release="onRelease"
          @pick-event="pickEvent"
        />
      </div>
    </div>

    <div v-if="!ready && !failed" class="sv-cover no-select">
      <div class="sol-spinner"></div>
      <p class="sv-cover-text">Bringing the Sun into three dimensions…</p>
    </div>

    <div v-if="failed" class="sv-cover no-select">
      <div class="sv-error">
        <h3 class="sv-error-title">The 3D view isn't available right now</h3>
        <p class="sv-error-body">
          It needs a live connection to the WorldWide Telescope service and a
          WebGL-capable browser. <strong>Sun Now</strong> and the live space-weather
          numbers still work.
        </p>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
// wwt-hacks FIRST, for its import-time side effects: the engine binds its touch
// handlers with ss.bind() at initControl and captures the method references
// then, so the onGesture* no-ops must already be on the prototype before
// <WorldWideTelescope> mounts (CLAUDE.md footgun 10).
import "../wwt/wwt-hacks";

import { EngineSetting, WWTControl } from "@wwtelescope/engine";
import { WWTAwareComponent, WWTComponent, wwtPinia } from "@wwtelescope/engine-pinia";
import { defineComponent, markRaw } from "vue";
import { Vector3 } from "three";

import LayerPanel from "./LayerPanel.vue";
import RegionLabel from "./RegionLabel.vue";
import SpacecraftLabel from "./SpacecraftLabel.vue";
import TimeScrubber from "./TimeScrubber.vue";
import {
  PfssManifest,
  PfssTopology,
  dataBaseUrl,
  loadPfss,
} from "../data/pfss";
import {
  SolarRegion,
  describeRegionArea,
  describeRegionMagnetism,
  loadRegions,
  regionVector,
} from "../data/regions";
import {
  SolarEvent,
  SolarEvents,
  describeCmeAim,
  describeCmeSpeed,
  describeFlareClass,
  earthArrivalUnix,
  eventTitle,
  loadEvents,
  thinEvents,
} from "../data/events";
import { AU_KM, R_SUN_AU, R_SUN_KM, Vec3, b0DegApprox, julianDate } from "../data/solarFrames";
import {
  LivePosition,
  SpacecraftEphemeris,
  bodyBlurb,
  describeDistance,
  fetchLivePosition,
  loadSpacecraft,
  positionAt,
  rSunAt,
} from "../data/spacecraft";
import { useSolarStats, thinFlareEvents } from "../data/useSolarStats";
import { DebugHelpers, createDebugHelpers } from "../three/debug";
import { FieldLines, createFieldLines } from "../three/fieldLines";
import { ProjectTarget, Projected, cameraPosition, projectTargets } from "../three/project";
import { SolarWind, createSolarWind } from "../three/solarWind";
import { SpacecraftTrails, TrailInput, createSpacecraftTrails } from "../three/spacecraftTrails";
import { SunGlow, createSunGlow } from "../three/sunGlow";
import { SunSurface, createSunSurface } from "../three/sunSurface";
import { ThreeStage, createThreeStage } from "../three/stage";
import { installHiDpiCanvas } from "../wwt/wwt-hacks";
import {
  SunStageHost,
  cameraInfo,
  clampCameraLat,
  currentDistanceAu,
  homeCamera,
  initSunStage,
  refitFraming,
  solarSystemModeActive,
} from "../wwt/sunStage";
import {
  FieldColorMode,
  SurfaceMode,
  TextureChannel,
  attractDrift,
  fieldColorMode,
  frameT,
  getAppHandle,
  layers,
  playing,
  resetToken,
  sheet,
  surfaceMode,
  textureChannel,
  view,
  wide,
} from "../state/useAppState";
import { boolParam, stringParam } from "../urlParams";

// --- engine installation ----------------------------------------------------
// main.ts must stay engine-free (the whole point of the async chunk), so the
// pinia instance and the WWT component are installed on the running app the
// first time this module is evaluated — i.e. before this component's own
// instance is created, so `provide()` from pinia is visible to it.
let engineInstalled = false;

function installEngine(): void {
  if (engineInstalled) { return; }
  const app = getAppHandle();
  if (!app) {
    console.error("[SolarView3D] no app handle; sol.vue must call setAppHandle() at mount.");
    return;
  }
  app.use(wwtPinia);
  app.component("WorldWideTelescope", WWTComponent);
  engineInstalled = true;
}

installEngine();

/** Solar-system mode has this long to engage before we show the error card. */
const MODE_TIMEOUT_MS = 10000;

/** How often the playhead is written back to shared state (scrubber follow).
 *  ~30 Hz: at 10 Hz the native range thumb visibly steps across a 0.8 s/frame
 *  animation (user-reported); a 30 Hz single-input re-render is negligible. */
const PUBLISH_MS = 33;

/**
 * DOM label refresh while the camera is STILL. 20 Hz is plenty for labels that
 * are only tracking the Sun's own rotation and the spacecraft crawling along
 * their orbits.
 *
 * While the camera is MOVING it is not plenty: the scene renders at 60 fps and
 * the labels stepped at 20, so they visibly lagged and stuttered behind the
 * features they name (user-reported). Motion is the case where the eye is most
 * sensitive to it, so the tick below projects every frame whenever the camera
 * has actually changed and falls back to this rate the moment it settles.
 * Projecting a handful of points and writing their transforms is cheap; it is
 * doing it 60 times a second for nothing that is worth avoiding.
 */
const PROJECT_MS = 50;

/** Kiosk attract loop: prograde camera drift, in degrees per second. */
const ATTRACT_DRIFT_DEG_S = 2;

/** Chip names: the full mission name doesn't fit on a phone. */
const SHORT_NAMES: Record<string, string> = {
  psp: "Parker",
  solo: "Solar Orbiter",
  stereoa: "STEREO-A",
  earth: "Earth",
};

/**
 * Surface markers sit 3% above the photosphere. The surface sphere itself is at
 * 1.001 R (sunSurface.ts), so this is far enough out that a chip's ring never
 * z-fights with the granulation under it, and near enough that it still reads as
 * a place ON the Sun rather than a thing floating over it.
 */
const MARKER_RADIUS = R_SUN_AU * 1.03;

/**
 * Facing test for surface markers: show one while the cosine between its own
 * surface normal and the direction to the camera exceeds this. 0.1 is ~84° from
 * the sub-camera point — just inside the limb, where a chip's text would
 * otherwise run off the disc and its projected position is least stable.
 */
const FACING_MIN_DOT = 0.1;

/** Most flare diamonds a phone-width scrubber track can carry (see thinning). */
const MAX_FLARE_MARKS = 10;

/** The sub-Earth marker's id in the shared selection slot. */
const SUB_EARTH_ID = "sub-earth";

/** Active-region ids carry this so they can't collide with an ephemeris body. */
const AR_PREFIX = "ar:";

/** Card-slot prefix for a DONKI flare or CME. */
const EVENT_PREFIX = "evt:";

/** Marks a 72 h window can hold before the track reads as texture, not data. */
const MAX_EVENT_MARKS = 12;

/**
 * Shown on every event card. CCMC's own words for DONKI are "prototyping
 * quality and in research context", and this app's habit is to say what the
 * data actually is rather than let a confident-looking card imply more (the
 * disk view refuses to fake a frame timestamp for the same reason).
 */
const EVENT_DISCLAIMER = "Research data from NASA CCMC — not an official forecast.";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Aug 22, 20:09 UTC" — flares are quoted in UTC everywhere in this app. */
function flareStamp(unix: number): string {
  const d = new Date(unix * 1000);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${hh}:${mm} UTC`;
}

interface Chip {
  id: string;
  name: string;
  detail: string;
  color: string;
  x: number;
  y: number;
  visible: boolean;
}

/** A chip pinned to a point on the Sun: an active region, or the sub-Earth ⊕. */
interface RegionChip {
  id: string;
  label: string;
  description: string;
  x: number;
  y: number;
  visible: boolean;
}

interface CardInfo {
  name: string;
  detail: string;
  compare: string;
  blurb: string;
  /** Optional final line, set apart in warning colour. */
  warn?: string;
}

/**
 * The slice of WWTAwareComponent this file calls. Reached through one cast
 * rather than relying on `extends:` to flow through the type system — the
 * runtime merge is what matters, and one narrow interface is easier to audit
 * than a component-instance type that spans 400 declarations.
 */
interface WwtHost extends SunStageHost {
  waitForReady: () => Promise<void>;
}

/** Everything the render loop touches, kept OUT of Vue's reactivity. */
interface Runtime {
  stage: ThreeStage | null;
  fieldLines: FieldLines | null;
  surface: SunSurface | null;
  wind: SolarWind | null;
  glow: SunGlow | null;
  trails: SpacecraftTrails | null;
  debug: DebugHelpers | null;
  manifest: PfssManifest | null;
  topology: PfssTopology | null;
  ephemeris: SpacecraftEphemeris | null;
  live: Record<string, LivePosition>;
  abort: AbortController | null;
  modeTimer: number;
  lastTickMs: number;
  lastPublishMs: number;
  lastProjectMs: number;
  dragging: boolean;
  destroyed: boolean;
  /** Last playhead value WE wrote to shared state, so the watcher can tell
   *  our own echo from a real outside change. */
  published: number;
  widthCss: number;
  heightCss: number;
  observer: ResizeObserver | null;
  positions: Map<string, Vector3>;
  targets: ProjectTarget[];
  projected: Projected[];
  /** Active regions from `ar/regions.json`; empty when the product is absent. */
  regions: SolarRegion[];
  /** Each region's marker point in the CARRINGTON LOCAL frame, parallel to
   *  `regions` — rotated into world coordinates every projection pass. */
  regionLocal: Vector3[];
  /** Surface markers: the sub-Earth point FIRST, then one per region, so the
   *  index of a projected point identifies its chip without a lookup. */
  markerTargets: ProjectTarget[];
  markerProjected: Projected[];
  scratch: [number, number, number];
  /** Camera world position, refreshed per frame for the surface shader. */
  cameraWorld: Vector3;
  /** Integer frame the wind paths were built from; -1 forces a rebuild. */
  windFrame: number;
  /** ?debug=1 sub-Earth assertion has already run (it only needs to once). */
  textureChecked: boolean;
}

function makeRuntime(): Runtime {
  return {
    stage: null,
    fieldLines: null,
    surface: null,
    wind: null,
    glow: null,
    trails: null,
    debug: null,
    manifest: null,
    topology: null,
    ephemeris: null,
    live: {},
    abort: null,
    modeTimer: 0,
    lastTickMs: 0,
    lastPublishMs: 0,
    lastProjectMs: 0,
    /** Last camera state the labels were projected for — see PROJECT_MS. */
    lastCam: { lat: NaN, lng: NaN, zoom: NaN, rotation: NaN },
    dragging: false,
    destroyed: false,
    published: -1,
    widthCss: 0,
    heightCss: 0,
    observer: null,
    positions: new Map(),
    targets: [],
    projected: [],
    regions: [],
    regionLocal: [],
    markerTargets: [{ id: SUB_EARTH_ID, position: new Vector3() }],
    markerProjected: [],
    scratch: [0, 0, 0],
    cameraWorld: new Vector3(),
    windFrame: -1,
    textureChecked: false,
  };
}

/**
 * The 3D view: WWT in solar-system mode with a three.js overlay carrying the
 * PFSS field lines, the sun glow and the spacecraft.
 *
 * Extends WWTAwareComponent directly rather than vue-toolkit's MiniDSBase:
 * vue-toolkit ships as a single CJS bundle, so importing it would drag leaflet
 * and friends into this chunk for the sake of five methods we already have here
 * (waitForReady, applySetting, setBackground/ForegroundImageByName, setClockSync,
 * setTime).
 */
export default defineComponent({
  name: "SolarView3D",

  extends: WWTAwareComponent,

  components: {
    "layer-panel": LayerPanel,
    "region-label": RegionLabel,
    "spacecraft-label": SpacecraftLabel,
    "time-scrubber": TimeScrubber,
  },

  // Belt and braces. The module-scope call above normally wins the race (a
  // dynamic import cannot resolve before sol.vue's synchronous mount flush has
  // called setAppHandle), but if it ever didn't, this runs before our render
  // function resolves <WorldWideTelescope> and before any pinia-backed getter.
  beforeCreate() {
    installEngine();
  },

  setup() {
    // Module singleton: the stats row already drives the polling, and the wind
    // layer only reads the current speed (416 km/s today) to scale itself.
    const { stats } = useSolarStats();
    return {
      frameT, layers, playing, resetToken, sheet, surfaceMode, fieldColorMode,
      textureChannel, view, wide, solarStats: stats,
    };
  },

  data() {
    return {
      ready: false,
      failed: false,
      fieldLinesAbsent: false,

      frameCount: 0,
      loadedFrom: 0,
      loadedCount: 0,
      frameTimes: [] as number[],
      dataStale: false,
      dataStaleHours: 0,

      chips: [] as Chip[],
      regionChips: [] as RegionChip[],
      earthChip: {
        id: SUB_EARTH_ID,
        label: "Facing Earth",
        description: "The point on the Sun that faces Earth right now",
        x: 0,
        y: 0,
        visible: false,
      } as RegionChip,
      selectedId: "",
      /** 0..1 — how much of the hemisphere in view was never observed. */
      unobserved: 0,
      /** `events/events.json`, or null while it loads / when it is absent. */
      solarEvents: null as SolarEvents | null,

      rt: markRaw(makeRuntime()),
    };
  },

  computed: {
    selectedBody(): CardInfo | null {
      if (!this.selectedId) { return null; }
      const eph = this.rt.ephemeris;
      const body = eph?.bodies.find((b) => b.id === this.selectedId);
      if (!eph || !body) { return null; }
      const rSun = rSunAt(body, eph.epochs, this.sceneUnix());
      return {
        name: body.name,
        detail: this.formatDistance(rSun),
        compare: describeDistance(rSun),
        blurb: bodyBlurb(body.id),
      };
    },

    /**
     * What the one card slot is showing. Three subjects share it, told apart by
     * the id: the sub-Earth marker, an active region ("ar:4513"), or an
     * ephemeris body (a bare id, so nothing changed for the spacecraft).
     */
    selectedCard(): CardInfo | null {
      const id = this.selectedId;
      if (!id) { return null; }
      if (id === SUB_EARTH_ID) {
        return {
          name: "Facing Earth",
          detail: "",
          compare: "",
          blurb: "This side of the Sun is facing Earth right now — "
            + "it's the view in Sun Now.",
        };
      }
      if (id.indexOf(AR_PREFIX) === 0) { return this.regionCard(id.slice(AR_PREFIX.length)); }
      if (id.indexOf(EVENT_PREFIX) === 0) { return this.eventCard(); }
      return this.selectedBody;
    },

    /**
     * Flare diamonds for the scrubber track.
     *
     * TimeScrubber drops anything outside the frame window itself, so all this
     * has to do is thin the noise (29 events today, 25 of them C-class) and
     * write the label a guest reads on tap.
     */
    flareMarks(): { unix: number; label: string; cls: string; kind?: string; id?: string }[] {
      const donki = this.solarEvents?.events ?? [];

      // DONKI wins where both feeds have the same flare. It is the richer
      // record — it knows WHERE the flare was and what CME went with it — and
      // a mark that opens a card beats one that only scrubs. NOAA's history is
      // still the fallback: it is near-real-time (median DONKI lag is 1.9 h
      // for flares, 7.5 h for CMEs), so it covers the newest events DONKI has
      // not published yet.
      const claimed = new Set<number>();
      for (const event of donki) {
        if (event.kind === "flare") { claimed.add(Math.round(event.unix / 60)); }
      }

      const marks: { unix: number; label: string; cls: string; kind?: string; id?: string }[] = [];
      for (const event of thinEvents(donki, MAX_EVENT_MARKS)) {
        marks.push({
          unix: event.unix,
          label: `${eventTitle(event)} · ${flareStamp(event.unix)}`,
          cls: event.cls ?? "",
          kind: event.kind,
          id: `${EVENT_PREFIX}${event.id}`,
        });
      }

      const history = this.solarStats.flareHistory.value?.events;
      if (history && history.length) {
        for (const event of thinFlareEvents(history, MAX_FLARE_MARKS)) {
          if (claimed.has(Math.round(event.peakUnix / 60))) { continue; }
          marks.push({
            unix: event.peakUnix,
            label: `${event.cls ? `${event.cls} flare` : "Flare"} · ${flareStamp(event.peakUnix)}`,
            cls: event.cls,
          });
        }
      }
      return marks.sort((a, b) => a.unix - b.unix);
    },

    /** The DONKI event the card slot is showing, if that is what it holds. */
    selectedEvent(): SolarEvent | null {
      const id = this.selectedId;
      if (id.indexOf(EVENT_PREFIX) !== 0) { return null; }
      const wanted = id.slice(EVENT_PREFIX.length);
      return this.solarEvents?.events.find((e) => e.id === wanted) ?? null;
    },
  },

  watch: {
    // The component stays mounted for the life of the page (sol.vue hides it
    // with v-show — remounting WWT leaves its texture caches on a dead GL
    // context and the Sun comes back black). Pause three's per-frame work
    // while the guest is in Sun Now; WWT's own loop keeps its state warm.
    view(value: string) {
      this.rt.stage?.setEnabled(value === "3d");
    },

    resetToken() {
      this.recentre();
      // resetView() parks frameT at 0, which for a frame-index playhead is the
      // OLDEST frame. Resting state is "now", so override it here — this
      // watcher runs before the frameT one, so that write is what survives.
      this.parkAtNewest();
    },

    frameT(value: number) {
      // Ignore our own write-back from tick(): comparing against the value we
      // last published (not against lines.time(), which has moved on since)
      // means playback never gets rewound by its own echo.
      const rt = this.rt;
      if (!rt.fieldLines || Math.abs(value - rt.published) < 1e-4) { return; }
      rt.fieldLines.setTime(value);
      rt.published = rt.fieldLines.time();
    },

    "layers.fieldLines"(value: boolean) {
      this.rt.fieldLines?.setVisible(value);
    },

    "layers.wind"(value: boolean) {
      this.rt.wind?.setVisible(value);
      // Paths are only rebuilt on an integer-frame change, and that change may
      // have happened while the layer was off — force one on the way back in.
      if (value) { this.rt.windFrame = -1; }
    },

    surfaceMode(value: SurfaceMode) {
      this.rt.surface?.setMode(value);
    },

    fieldColorMode(value: FieldColorMode) {
      this.rt.fieldLines?.setMonochrome(value === "blue");
    },

    textureChannel(value: TextureChannel) {
      this.rt.surface?.setChannel(value);
    },

    "layers.spacecraft"(value: boolean) {
      this.rt.trails?.setVisible(value);
      // Only a SPACECRAFT card is dismissed with the spacecraft layer — the
      // surface markers share this slot and are not part of that layer.
      if (!value && this.selectedId && !this.isSurfaceId(this.selectedId)) {
        this.selectedId = "";
      }
    },

    "layers.orbits"(value: boolean) {
      this.host().applySetting(["solarSystemOrbits", value] as EngineSetting);
    },

    "layers.glow"(value: boolean) {
      this.rt.glow?.setVisible(value);
    },
  },

  async mounted() {
    const host = this.host();
    try {
      await host.waitForReady();
    } catch (err) {
      console.error("[SolarView3D] WWT never became ready:", err);
      this.failed = true;
      return;
    }
    if (this.rt.destroyed) { return; }

    // Order matters: the DPR shim rewrites canvas sizing behind the engine's
    // back, so it has to land before the first frame is drawn.
    installHiDpiCanvas(2);
    initSunStage(host);
    host.applySetting(["solarSystemOrbits", this.layers.orbits] as EngineSetting);

    // Non-freestanding requirement (CLAUDE.md footgun 5): 3D mode needs
    // worldwidetelescope.org for its imageset catalogue. If the mode never
    // engages, say so plainly instead of showing a black rectangle.
    this.rt.modeTimer = window.setTimeout(() => {
      if (!solarSystemModeActive()) {
        console.error("[SolarView3D] solar-system mode did not engage within 10 s.");
        this.failed = true;
      }
    }, MODE_TIMEOUT_MS);

    if (!this.createStage()) { return; }
    this.measure();
    this.observeSize();
    window.addEventListener("resize", this.onResize);
    window.addEventListener("orientationchange", this.onResize);
    this.ready = true;

    void this.loadFieldLines();
    void this.loadSpacecraftLayer();
    void this.loadRegionLayer();
    void this.loadEventLayer();
  },

  beforeUnmount() {
    const rt = this.rt;
    rt.destroyed = true;
    window.clearTimeout(rt.modeTimer);
    window.removeEventListener("resize", this.onResize);
    window.removeEventListener("orientationchange", this.onResize);
    rt.observer?.disconnect();
    rt.abort?.abort();
    playing.value = false;

    rt.fieldLines?.dispose();
    rt.surface?.dispose();
    rt.wind?.dispose();
    rt.glow?.dispose();
    rt.trails?.dispose();
    rt.debug?.dispose();
    // Last: disconnecting the stage removes the frame callback, so nothing can
    // touch a disposed layer afterwards.
    rt.stage?.dispose();

    delete (window as unknown as { solDebug?: unknown }).solDebug;
  },

  methods: {
    /** The WWTAwareComponent methods we use, typed narrowly (see WwtHost). */
    host(): WwtHost {
      return this as unknown as WwtHost;
    },

    // --- stage ------------------------------------------------------------

    createStage(): boolean {
      const rt = this.rt;
      try {
        rt.stage = markRaw(createThreeStage({
          target: stringParam("three") === "overlay" ? "overlay" : "wwt",
          onBeforeRender: this.tick,
          onContextRestored: this.onContextRestored,
        }));
      } catch (err) {
        console.error("[SolarView3D] three.js stage failed:", err);
        this.failed = true;
        return false;
      }

      rt.glow = markRaw(createSunGlow(R_SUN_AU));
      rt.glow.setVisible(this.layers.glow);
      rt.stage.scene.add(rt.glow.sprite);

      // Our own Sun sphere, 0.1% above WWT's. It loads its own products
      // (texture/texture.json, ar/regions.json) and falls back to the
      // synthetic surface when either is absent.
      rt.surface = markRaw(createSunSurface({
        rSunAu: R_SUN_AU,
        dataBaseUrl: dataBaseUrl(),
        mode: this.surfaceMode,
        channel: this.textureChannel,
        debug: boolParam("debug"),
      }));
      rt.stage.scene.add(rt.surface.object3d);

      // Wind paths arrive with the first frame (see tick()); the layer is
      // created here so its buffers exist before anything can ask for them.
      rt.wind = markRaw(createSolarWind({ rSunAu: R_SUN_AU }));
      rt.wind.setVisible(this.layers.wind);
      rt.stage.scene.add(rt.wind.object3d);

      if (boolParam("debug")) {
        rt.debug = markRaw(createDebugHelpers(R_SUN_AU));
        rt.stage.scene.add(rt.debug.group);
        this.installDebugHandle();
      }
      return true;
    },

    /** Rebuild GPU buffers from the retained ArrayBuffers after context loss. */
    onContextRestored(): void {
      this.rt.fieldLines?.rebuild();
    },

    // --- per-frame --------------------------------------------------------

    /**
     * Runs inside three-wwt's onBeforeRender, i.e. after WWT has restored the
     * frame's matrices — so the camera we read is the one about to be drawn.
     */
    tick(): void {
      const rt = this.rt;
      if (rt.destroyed) { return; }

      // Enforced here rather than by patching the engine's input handlers: WWT
      // accumulates latitude in several places and one clamp per frame catches
      // all of them.
      clampCameraLat();

      const now = performance.now();
      const dt = rt.lastTickMs > 0 ? Math.min((now - rt.lastTickMs) / 1000, 0.25) : 0;
      rt.lastTickMs = now;

      // Kiosk attract loop. The ref is read (not a prop/computed) so the
      // attract module needs no engine import of its own.
      if (attractDrift.value) { this.driftCamera(dt); }

      const lines = rt.fieldLines;
      if (lines) {
        if (this.playing && !rt.dragging) { lines.advance(dt); }
        if (now - rt.lastPublishMs > PUBLISH_MS) {
          rt.lastPublishMs = now;
          const t = lines.time();
          if (Math.abs(t - rt.published) > 1e-4) {
            rt.published = t;
            this.frameT = t;
          }
        }
      }

      this.updateSun(dt);

      // Camera motion, cheaply: lat/lng/zoom/rotation is the whole of WWT's
      // camera state, and the engine eases viewCamera toward targetCamera for
      // a while after a drag ends, so this keeps up through the settle too.
      const cam = cameraInfo();
      const moved = Math.abs(cam.latDeg - rt.lastCam.lat) > 1e-4
        || Math.abs(cam.lngDeg - rt.lastCam.lng) > 1e-4
        || Math.abs(cam.zoom - rt.lastCam.zoom) > 1e-9
        || Math.abs(cam.rotation - rt.lastCam.rotation) > 1e-5;
      if (moved) {
        rt.lastCam.lat = cam.latDeg;
        rt.lastCam.lng = cam.lngDeg;
        rt.lastCam.zoom = cam.zoom;
        rt.lastCam.rotation = cam.rotation;
      }

      if (moved || now - rt.lastProjectMs > PROJECT_MS) {
        rt.lastProjectMs = now;
        this.updateSpacecraft();
        this.updateSurfaceMarkers();
        this.tuneWind();
        if (rt.debug) { this.assertTextureFacing(); }
      }
    },

    /**
     * Surface + wind, both riding the field lines' orientation.
     *
     * The quaternion is READ FROM the field-line group rather than recomputed:
     * that group already carries the slerped `quat_carr_to_ecl` for the exact
     * sub-frame position of the playhead, and sharing the one value is what
     * makes a texture feature (or a sunspot) sit under its own field lines. A
     * second copy of the slerp would be a second thing to get wrong.
     */
    updateSun(dt: number): void {
      const rt = this.rt;
      const { stage, surface, wind, fieldLines } = rt;
      if (!stage) { return; }
      const orientation = fieldLines?.group.quaternion;

      if (surface) {
        if (orientation) { surface.setQuaternion(orientation); }
        surface.setCameraPosition(cameraPosition(stage.camera, rt.cameraWorld));
        surface.tick(dt);
      }

      if (wind) {
        if (orientation) { wind.setQuaternion(orientation); }
        if (fieldLines && this.layers.wind) {
          const index = fieldLines.frameIndex();
          if (index >= 0 && index !== rt.windFrame) {
            rt.windFrame = index;
            wind.setFrameData(fieldLines.openLinePaths());
          }
        }
        wind.tick(dt);
      }
    },

    /**
     * Wind speed and point size, at the 20 Hz throttle: both are cheap reads
     * that only need to track the live SWPC number and the drawing-buffer size,
     * neither of which changes per frame.
     */
    tuneWind(): void {
      const rt = this.rt;
      const wind = rt.wind;
      if (!wind || !rt.stage) { return; }
      const speed = this.solarStats.wind.value;
      if (typeof speed === "number") { wind.setSpeedKms(speed); }
      wind.setPixelScale(rt.stage.bufferSize().height * 0.5);
    },

    /**
     * A slow prograde orbit for the attract loop. Written to `targetCamera`
     * only, so the engine's own per-frame easing smooths it for free (footgun
     * 14), and wrapped into [0, 360) exactly as the engine's drag handler does:
     * the easing takes the short way round only while both cameras agree on
     * where the branch cut is, and it normalises `viewCamera` itself.
     */
    driftCamera(dt: number): void {
      const camera = WWTControl.singleton?.renderContext?.targetCamera;
      if (!camera) { return; }
      camera.lng = (camera.lng + ATTRACT_DRIFT_DEG_S * dt + 720) % 360;
    },

    // --- field lines ------------------------------------------------------

    async loadFieldLines(): Promise<void> {
      const rt = this.rt;
      rt.abort = new AbortController();
      let result;
      try {
        result = await loadPfss(dataBaseUrl(), {
          onManifest: (manifest) => {
            rt.manifest = markRaw(manifest);
            this.frameCount = manifest.frames.length;
            this.loadedFrom = manifest.frames.length;
            this.frameTimes = manifest.frames.map((f) => f.magUnix);
            // Surfaced now so the banner (if it appears) already has the right
            // number in it; `dataStale` itself waits for index.json's verdict.
            this.dataStaleHours = manifest.newestMagAgeHours;
            if (boolParam("debug")) { this.assertOrientation(manifest); }
          },
          onTopology: (topology) => {
            rt.topology = markRaw(topology);
            this.buildFieldLines();
          },
          onFrame: (frame) => {
            rt.fieldLines?.addFrame(frame);
            this.syncFrameCounts();
          },
          signal: rt.abort.signal,
        });
      } catch (err) {
        if (!rt.destroyed) { console.warn("[SolarView3D] field lines aborted:", err); }
        return;
      }
      if (rt.destroyed) { return; }

      this.dataStale = result.stale;
      this.dataStaleHours = result.staleHours ?? this.dataStaleHours;
      if (result.status === "absent" || result.framesLoaded === 0) {
        this.fieldLinesAbsent = true;
        if (result.reason) { console.warn("[SolarView3D]", result.reason); }
      }
    },

    buildFieldLines(): void {
      const rt = this.rt;
      const { manifest, topology, stage } = rt;
      if (!manifest || !topology || !stage || rt.fieldLines) { return; }

      rt.fieldLines = markRaw(createFieldLines({
        rSunAu: R_SUN_AU,
        frameCount: manifest.frames.length,
        nLines: topology.nLines,
        nVertsTotal: topology.nVertsTotal,
        lineOffset: topology.lineOffset,
        colors: manifest.hints,
        quantScale: manifest.quantScale,
        quantOffset: manifest.quantOffset,
        rss: manifest.hints.rss,
        closedFloor: manifest.hints.closedFloor,
      }));
      rt.fieldLines.setVisible(this.layers.fieldLines);
      // The layer can be (re)built long after the guest picked a colour — a
      // deep link sets it before any frame data has arrived.
      rt.fieldLines.setMonochrome(this.fieldColorMode === "blue");
      stage.scene.add(rt.fieldLines.group);
      if (boolParam("debug")) { this.installDebugHandle(); }
    },

    syncFrameCounts(): void {
      const lines = this.rt.fieldLines;
      if (!lines) { return; }
      this.loadedCount = lines.loadedCount();
      this.loadedFrom = lines.loadedFrom();
      this.rt.published = lines.time();
      this.frameT = this.rt.published;
    },

    onScrub(value: number): void {
      const lines = this.rt.fieldLines;
      if (!lines) { return; }
      lines.setTime(value);
      // Clamped to the loaded range, so the thumb snaps back if the guest drags
      // into frames that haven't arrived yet — the tick bar shows which those are.
      this.rt.published = lines.time();
      this.frameT = this.rt.published;
    },

    parkAtNewest(): void {
      const lines = this.rt.fieldLines;
      if (!lines) { return; }
      lines.setTime(this.frameCount - 1);
      this.rt.published = lines.time();
      this.frameT = this.rt.published;
    },

    onGrab(): void {
      this.rt.dragging = true;
    },

    onRelease(): void {
      this.rt.dragging = false;
    },

    // --- spacecraft -------------------------------------------------------

    async loadSpacecraftLayer(): Promise<void> {
      const rt = this.rt;
      let ephemeris: SpacecraftEphemeris | null = null;
      try {
        ephemeris = await loadSpacecraft(dataBaseUrl(), rt.abort?.signal);
      } catch {
        return; // aborted by unmount
      }
      if (!ephemeris || rt.destroyed || !rt.stage) { return; }
      rt.ephemeris = markRaw(ephemeris);

      const inputs: TrailInput[] = ephemeris.bodies.map((body) => ({
        id: body.id,
        color: body.color,
        positions: body.positions,
        nowIndex: ephemeris.nowIndex,
        // Earth's orbit is already available from WWT (layers.orbits) and a
        // second 1 AU ring just adds clutter.
        drawTrail: body.id !== "earth",
      }));
      rt.trails = markRaw(createSpacecraftTrails(inputs));
      rt.trails.setVisible(this.layers.spacecraft);
      rt.stage.scene.add(rt.trails.group);

      rt.targets = [];
      this.chips = ephemeris.bodies.map((body) => {
        const position = new Vector3();
        rt.positions.set(body.id, position);
        rt.targets.push({ id: body.id, position });
        return {
          id: body.id,
          name: SHORT_NAMES[body.id] ?? body.name,
          detail: this.formatDistance(body.rRsunNow),
          color: body.color,
          x: 0,
          y: 0,
          visible: false,
        };
      });

      void this.refreshLivePositions();
    },

    /**
     * Optional freshener: swhv.oma.be reports ONE epoch per call, which is why
     * the trails are baked. Failure is silent — the Horizons interpolation is
     * accurate to well under a pixel anyway.
     */
    async refreshLivePositions(): Promise<void> {
      const rt = this.rt;
      const when = new Date();
      const results = await Promise.all([
        fetchLivePosition("psp", when),
        fetchLivePosition("solo", when),
      ]);
      if (rt.destroyed) { return; }
      results.forEach((live) => {
        if (live) { rt.live[live.id] = live; }
      });
    },

    /** Scene time: the magnetogram time under the playhead, or now. */
    sceneUnix(): number {
      const times = this.frameTimes;
      if (!times.length) { return Date.now() / 1000; }
      const last = times.length - 1;
      const t = Math.min(Math.max(this.frameT, 0), last);
      const indexA = Math.min(Math.floor(t), last);
      const indexB = Math.min(indexA + 1, last);
      return times[indexA] + (times[indexB] - times[indexA]) * (t - indexA);
    },

    updateSpacecraft(): void {
      const rt = this.rt;
      const { stage, trails, ephemeris } = rt;
      if (!stage || !trails || !ephemeris || !this.chips.length) { return; }

      const unix = this.sceneUnix();
      // The live dot is only honest at the newest frame; anywhere else in the
      // 48-hour window the baked ephemeris is the correct answer.
      const atNewest = this.frameT >= this.frameCount - 1.001;

      ephemeris.bodies.forEach((body) => {
        const position = rt.positions.get(body.id);
        if (!position) { return; }
        const live = atNewest ? rt.live[body.id] : undefined;
        if (live) {
          position.set(live.world[0], live.world[1], live.world[2]);
        } else {
          positionAt(body, ephemeris.epochs, unix, rt.scratch);
          position.set(rt.scratch[0], rt.scratch[1], rt.scratch[2]);
        }
        trails.setMarker(body.id, position.x, position.y, position.z);
      });

      trails.updateMarkerScale(currentDistanceAu());

      projectTargets(
        stage.camera,
        rt.widthCss,
        rt.heightCss,
        rt.targets,
        R_SUN_AU,
        rt.projected,
      );

      // Mutate in place: the chip list is stable, so Vue patches text and
      // transforms instead of tearing down three components 20 times a second.
      rt.projected.forEach((point, i) => {
        const chip = this.chips[i];
        const body = ephemeris.bodies[i];
        if (!chip || !body) { return; }
        chip.x = point.xCss;
        chip.y = point.yCss;
        chip.visible = point.visible;
        chip.detail = this.formatDistance(rSunAt(body, ephemeris.epochs, unix));
      });

      // Same cadence as the chips rather than per frame: this drives a piece of
      // DOM, and 20 Hz is already far more than a fading hint needs.
      this.unobserved = this.rt.surface?.unobservedFraction() ?? 0;
    },

    /** "97 R☉ · 0.45 AU" — solar radii first, because that's the story. */
    formatDistance(rSun: number): string {
      const au = (rSun * R_SUN_KM) / AU_KM;
      return `${Math.round(rSun)} R☉ · ${au.toFixed(2)} AU`;
    },

    select(id: string): void {
      this.selectedId = this.selectedId === id ? "" : id;
    },

    // --- surface markers (active regions + sub-Earth) ----------------------

    /** True for the ids that belong to the Sun's surface, not to a body. */
    isSurfaceId(id: string): boolean {
      return id === SUB_EARTH_ID || id.indexOf(AR_PREFIX) === 0
        || id.indexOf(EVENT_PREFIX) === 0;
    },

    /**
     * Active regions. Optional in exactly the way the other data products are:
     * no file, or a spotless Sun, simply means no chips and no error UI.
     *
     * three/sunSurface.ts fetches the same JSON for its sunspot shader, which
     * makes two requests for one 1 KB file that the HTTP cache collapses anyway.
     * That module is off limits for restructuring, and threading its parsed
     * regions out would mean giving it a callback and a lifecycle it doesn't
     * otherwise need — a second typed reader in src/data/ is the cheaper seam,
     * and it is the one that carries the fields a guest-facing card talks about
     * (number, mag class, spot count, seed count) which the shader never needed.
     */
    /**
     * Flare + CME catalogue. Optional product: absent or empty simply means no
     * marks, which on a quiet Sun is the honest answer rather than an error.
     */
    async loadEventLayer(): Promise<void> {
      const rt = this.rt;
      const loaded = await loadEvents(dataBaseUrl(), rt.abort?.signal);
      if (rt.destroyed || !loaded) { return; }
      this.solarEvents = markRaw(loaded);
    },

    async loadRegionLayer(): Promise<void> {
      const rt = this.rt;
      const regions = await loadRegions(dataBaseUrl(), rt.abort?.signal);
      if (rt.destroyed || !regions.length) { return; }
      rt.regions = markRaw(regions);

      const local: Vec3 = [0, 0, 0];
      rt.regionLocal = regions.map((region) => {
        regionVector(region, MARKER_RADIUS, local);
        return new Vector3(local[0], local[1], local[2]);
      });
      // Index 0 stays the sub-Earth point; the regions follow it in order.
      rt.markerTargets.length = 1;
      regions.forEach((region) => {
        rt.markerTargets.push({
          id: `${AR_PREFIX}${region.number}`,
          position: new Vector3(),
        });
      });

      this.regionChips = regions.map((region) => ({
        id: `${AR_PREFIX}${region.number}`,
        label: `AR ${region.number}`,
        description: `Active Region ${region.number}, ${describeRegionMagnetism(region.magType)}`,
        x: 0,
        y: 0,
        visible: false,
      }));
    },

    /**
     * Active-region and sub-Earth chips, at the same 20 Hz DOM cadence as the
     * spacecraft labels.
     *
     * The regions arrive in the Carrington LOCAL frame, so each is turned by the
     * SAME slerped quaternion the surface and the field lines use — read off the
     * field-line group exactly as updateSun() does, because a second slerp would
     * be a second thing to get wrong and a region would drift out from under its
     * own field-line bundle. The sub-Earth point needs no rotation at all: it is
     * defined in WORLD coordinates as the direction Sun→Earth.
     */
    updateSurfaceMarkers(): void {
      const rt = this.rt;
      const stage = rt.stage;
      if (!stage) { return; }

      const orientation = rt.fieldLines?.group.quaternion;
      rt.regionLocal.forEach((point, i) => {
        const target = rt.markerTargets[i + 1];
        if (!target) { return; }
        target.position.copy(point);
        if (orientation) { target.position.applyQuaternion(orientation); }
      });

      // Earth under the PLAYHEAD (updateSpacecraft wrote it moments ago in this
      // same pass), projected onto the marker sphere. Earth moves ~1.5°/day, so
      // scrubbing 72 h back barely moves this point — but taking it from the
      // playhead keeps it consistent with the surface rotating underneath it.
      const earth = rt.positions.get("earth");
      const haveEarth = !!earth && earth.lengthSq() > 0;
      if (earth && haveEarth) {
        rt.markerTargets[0].position.copy(earth).setLength(MARKER_RADIUS);
      }

      // Occluder radius 0 on purpose. projectTargets' sphere test is built for
      // bodies out in SPACE — for a point sitting ON the sphere it misfires,
      // hiding near-limb chips at the closest zoom (a marker at 1.03 R can be
      // farther from the camera than the Sun's centre while still being in front
      // of the surface). The facing dot below is the exact test for a point on a
      // sphere, so this call is used purely for the world→CSS projection.
      cameraPosition(stage.camera, rt.cameraWorld);
      projectTargets(
        stage.camera,
        rt.widthCss,
        rt.heightCss,
        rt.markerTargets,
        0,
        rt.markerProjected,
      );

      // A marker's own position IS its surface normal, and both vectors have a
      // known length here, so the facing test is one dot product and one divide.
      const cameraLength = rt.cameraWorld.length();
      const scale = cameraLength > 0 ? 1 / (MARKER_RADIUS * cameraLength) : 0;
      rt.markerProjected.forEach((point, i) => {
        const facing = rt.markerTargets[i].position.dot(rt.cameraWorld) * scale > FACING_MIN_DOT;
        const visible = point.visible && facing;
        if (i === 0) {
          this.earthChip.x = point.xCss;
          this.earthChip.y = point.yCss;
          this.earthChip.visible = visible && haveEarth;
          return;
        }
        const chip = this.regionChips[i - 1];
        if (!chip) { return; }
        chip.x = point.xCss;
        chip.y = point.yCss;
        chip.visible = visible;
      });
    },

    /**
     * The card for one active region, in the language a guest can act on: how
     * big it is against the only silhouette they know, whether its field is
     * tangled, and how much of the 3D view they're looking at belongs to it.
     */
    /**
     * The card for a flare or CME.
     *
     * Every number shown is the measured one — this app does not round a real
     * measurement into a vibe. The `warn` line carries DONKI's own framing
     * ("prototyping quality... research context"): the catalogue is analyst-
     * submitted research data, not a NOAA forecast, and a planetarium should
     * not imply otherwise.
     */
    eventCard(): CardInfo | null {
      const event = this.selectedEvent;
      if (!event) { return null; }

      const when = flareStamp(event.unix);
      const region = event.arNumber ? `sunspot region ${event.arNumber}` : "";

      if (event.kind === "flare") {
        const where = region
          ? `From ${region}${event.sourceLocation ? ` (${event.sourceLocation})` : ""}.`
          : "";
        const linked = event.linked.length
          ? " It also threw off a cloud of gas — the blue circle on the timeline."
          : "";
        return {
          name: eventTitle(event),
          detail: when,
          compare: where,
          blurb: `${describeFlareClass(event.cls ?? "")}${linked}`.trim(),
          warn: EVENT_DISCLAIMER,
        };
      }

      const arrival = earthArrivalUnix(event);
      const parts = [describeCmeAim(event)];
      if (arrival) { parts.push(`Expected at Earth ${flareStamp(arrival)}.`); }
      if (region) { parts.push(`It came from ${region}.`); }
      return {
        name: eventTitle(event),
        detail: describeCmeSpeed(event.speedKms ?? 0),
        compare: when,
        blurb: parts.join(" "),
        warn: EVENT_DISCLAIMER,
      };
    },

    /** A timeline mark was tapped. TimeScrubber has already scrubbed there. */
    pickEvent(id: string): void {
      this.selectedId = id;
    },

    regionCard(numberText: string): CardInfo | null {
      const region = this.rt.regions.find((r) => String(r.number) === numberText);
      if (!region) { return null; }
      const spots = region.nSpots === 1 ? "1 sunspot" : `${region.nSpots} sunspots`;
      const seeds = region.seedCount === 1
        ? "One of the field lines in this view is rooted here."
        : `${region.seedCount} of the field lines in this view are rooted here.`;
      return {
        name: `Active Region ${region.number}`,
        detail: `${describeRegionArea(region.areaUh)} · ${spots}`,
        compare: `This is ${describeRegionMagnetism(region.magType)}.`,
        blurb: region.seedCount > 0 ? seeds : "",
        warn: region.isComplex
          ? "⚠ Watch this one — regions like this produce most big flares."
          : "",
      };
    },

    // --- chrome -----------------------------------------------------------

    recentre(): void {
      // targetCamera only: the engine eases viewCamera toward it every frame,
      // so this is a smooth flight home for free (footgun 14).
      homeCamera(false);
    },

    toggleLayers(): void {
      this.sheet = this.sheet === "layers" ? null : "layers";
    },

    measure(): void {
      const root = this.$refs.root as HTMLElement | undefined;
      if (!root) { return; }
      this.rt.widthCss = root.clientWidth;
      this.rt.heightCss = root.clientHeight;
    },

    observeSize(): void {
      const root = this.$refs.root as HTMLElement | undefined;
      if (!root || typeof ResizeObserver === "undefined") { return; }
      const observer = new ResizeObserver(() => this.measure());
      observer.observe(root);
      this.rt.observer = observer;
    },

    onResize(): void {
      // Portrait↔landscape changes the required framing distance by ~2x
      // (footgun 11), so the zoom is rescaled rather than left alone.
      refitFraming();
      this.measure();
    },

    // --- ?debug=1 ---------------------------------------------------------

    /**
     * Independent check on the frame conventions: the manifest's B0 comes from
     * sunpy in the pipeline, `b0DegApprox` from a low-precision series here. A
     * sign error in either shows up as a degrees-scale disagreement now, instead
     * of as "everything is subtly rotated" three milestones later.
     */
    assertOrientation(manifest: PfssManifest): void {
      manifest.frames.forEach((frame) => {
        const local = b0DegApprox(julianDate(new Date(frame.magUnix * 1000)));
        const delta = Math.abs(frame.b0Deg - local);
        if (delta > 0.05) {
          console.warn(
            `[debug] frame ${frame.index} b0 mismatch: manifest ${frame.b0Deg.toFixed(4)}° `
            + `vs local ${local.toFixed(4)}° (Δ ${delta.toFixed(4)}°)`);
        }
      });
    },

    /**
     * The one check that can catch a 90/180° error in the surface UV mapping
     * WITHOUT a human looking at the screen.
     *
     * The texture ships the Carrington longitude of its own sub-Earth point.
     * Rotate that meridian (on the equator) by the same quaternion the field
     * lines use and it must end up pointing at Earth's world position — off
     * only by the heliographic latitude of the sub-Earth point, B0, which is
     * never more than 7.25°. A mirrored or quarter-turned mapping puts it 90°
     * or 180° away, which no tolerance can hide.
     *
     * Runs once, only at the newest frame: the group quaternion belongs to the
     * PLAYHEAD, and scrubbing back 72 h turns it by another 42°.
     */
    assertTextureFacing(): void {
      const rt = this.rt;
      const { surface, fieldLines } = rt;
      if (rt.textureChecked || !surface || !fieldLines) { return; }
      const info = surface.textureInfo();
      const earth = rt.positions.get("earth");
      if (!info || !earth || !Number.isFinite(info.subEarthCarrLonDeg)) { return; }
      if (earth.lengthSq() === 0) { return; }
      if (this.frameCount > 0 && this.frameT < this.frameCount - 1.001) { return; }
      rt.textureChecked = true;

      const lon = (info.subEarthCarrLonDeg * Math.PI) / 180;
      const probe = new Vector3(Math.cos(lon), Math.sin(lon), 0)
        .applyQuaternion(fieldLines.group.quaternion);
      const toEarth = earth.clone().normalize();
      const cos = Math.max(-1, Math.min(1, probe.dot(toEarth)));
      const deg = (Math.acos(cos) * 180) / Math.PI;
      const detail = `sub-Earth lon ${info.subEarthCarrLonDeg.toFixed(1)}° `
        + `is ${deg.toFixed(1)}° from Earth (obs ${info.obsIso || "?"})`;
      if (deg > 15) {
        console.warn(`[debug] SURFACE MAPPING SUSPECT: ${detail}; expected < 8° (|B0| ≤ 7.25°).`);
      } else {
        console.warn(`[debug] surface sub-Earth check OK: ${detail}.`);
      }
    },

    installDebugHandle(): void {
      const rt = this.rt;
      (window as unknown as { solDebug?: unknown }).solDebug = {
        stage: rt.stage,
        fieldLines: rt.fieldLines,
        surface: rt.surface,
        wind: rt.wind,
        manifest: rt.manifest,
        get camera() {
          return {
            ...cameraInfo(),
            distanceAu: currentDistanceAu(),
            distanceRSun: currentDistanceAu() / R_SUN_AU,
            solarSystemMode: solarSystemModeActive(),
          };
        },
      };
    },
  },
});
</script>

<style lang="less" scoped>
.solar-view-3d {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #000;
}

// Scoped to the engine's own div, NOT the root: `touch-action: none` on the
// root would also cover the time scrubber, and the browser's own handling of a
// range input is what makes dragging it feel right on a phone.
:deep(.wwtelescope-component) {
  touch-action: none;
}

.sv-overlay {
  position: absolute;
  inset: 0;
  z-index: 5;
  pointer-events: none;
}

.sv-labels {
  position: absolute;
  inset: 0;
}

.sv-buttons {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.sv-icon-btn {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 11px;
  background: rgba(8, 6, 2, 0.6);
  backdrop-filter: blur(6px);
  color: var(--sol-text);
  font-size: 0.95rem;
  cursor: pointer;
  pointer-events: auto;
  -webkit-tap-highlight-color: transparent;

  &.is-active {
    border-color: var(--sol-accent);
    color: var(--sol-accent);
  }
}

// Below both icon buttons (2 x 44 px + a 0.4rem gap under a 0.5rem inset).
.sv-layer-popover {
  position: absolute;
  top: 7.1rem;
  right: 0.5rem;
  pointer-events: auto;
}

.sv-card {
  position: absolute;
  left: 0.5rem;
  right: 0.5rem;
  bottom: 5.2rem;
  max-width: 22rem;
  margin: 0 auto;
  padding: 0.8rem 2.2rem 0.8rem 0.9rem;
  border: 1px solid rgba(255, 200, 80, 0.3);
  border-radius: 12px;
  background: var(--sol-surface);
  box-shadow: 0 8px 26px rgba(0, 0, 0, 0.6);
  pointer-events: auto;
}

.sv-card-close {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--sol-text-dim);
  cursor: pointer;
}

.sv-card-title {
  margin: 0 0 0.25rem;
  color: var(--sol-accent);
  font-size: 1rem;
  font-weight: 700;
}

.sv-card-dist {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
}

.sv-card-compare {
  margin: 0.1rem 0 0;
  color: var(--sol-accent2);
  font-size: 0.78rem;
}

.sv-card-blurb {
  margin: 0.45rem 0 0;
  color: var(--sol-text-dim);
  font-size: 0.78rem;
  line-height: 1.4;
}

// Reserved for the one line that is a genuine heads-up (a delta-class region),
// so it can't become the house style for every card.
.sv-card-warn {
  margin: 0.45rem 0 0;
  padding: 0.35rem 0.45rem;
  border-radius: 8px;
  background: rgba(255, 160, 64, 0.14);
  color: #ffc98a;
  font-size: 0.76rem;
  line-height: 1.35;
}

.sv-bottom {
  position: absolute;
  left: 0.4rem;
  right: 0.4rem;
  bottom: 0.4rem;
  pointer-events: auto;
}

.sv-note {
  margin: 0;
  padding: 0.5rem 0.6rem;
  border-radius: 10px;
  background: rgba(8, 6, 2, 0.7);
  color: var(--sol-text-dim);
  font-size: 0.75rem;
  text-align: center;
}

// Centred near the top, clear of the card slot and the scrubber. Deliberately
// quiet: it explains the dimming the guest has just caused, it is not an alert.
.sv-unobserved {
  position: absolute;
  top: 3.6rem;
  left: 50%;
  transform: translateX(-50%);
  max-width: min(24rem, calc(100% - 2rem));
  margin: 0;
  padding: 0.45rem 0.7rem;
  border-radius: 10px;
  background: rgba(8, 6, 2, 0.78);
  backdrop-filter: blur(4px);
  color: var(--sol-text-dim);
  font-size: 0.74rem;
  line-height: 1.3;
  text-align: center;
  pointer-events: none;
}

.sv-cover {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 1.2rem;
  background: #000;
}

.sv-cover-text {
  margin: 0;
  color: var(--sol-text-dim);
  font-size: 0.95rem;
  text-align: center;
}

.sv-error {
  max-width: 24rem;
  text-align: center;
}

.sv-error-title {
  margin: 0 0 0.5rem;
  color: var(--sol-accent);
  font-size: 1.05rem;
  font-weight: 700;
}

.sv-error-body {
  margin: 0;
  color: var(--sol-text-dim);
  font-size: 0.85rem;
  line-height: 1.45;

  strong {
    color: var(--sol-text);
  }
}
</style>
