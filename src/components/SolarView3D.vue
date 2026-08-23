<template>
  <div
    ref="root"
    class="solar-view-3d"
    :style="{ '--sv-btn-count': visibleButtonCount }"
  >
    <!-- The engine's own div; the canvas is appended inside it. -->
    <WorldWideTelescope wwt-namespace="wwt-sol" />

    <!-- Everything below floats over the canvas. The layer itself is
         click-through; individual controls opt back in. -->
    <div class="sv-overlay">
      <div class="sv-labels">
        <!-- Drawn BEFORE the chips so a chip always paints over its own
             leader. One per chip that de-collision had to move: the marker's
             true projected point stays honest and only the text steps aside. -->
        <div
          v-for="leader in leaders"
          :key="leader.id"
          class="sv-leader"
          :style="leader.style"
          aria-hidden="true"
        ></div>

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

      <!-- One vertical stack, top right. The app title used to sit in a
           full-width banner above the stage with share and info at its far
           right, which spent a whole row of a phone screen on a wordmark and
           put four controls in two different places. -->
      <div class="sv-buttons">
        <button
          type="button"
          class="sv-icon-btn"
          aria-label="Recenter the Sun"
          title="Recenter the Sun"
          @click="recenter"
        >
          <font-awesome-icon icon="rotate-left" />
        </button>

        <!-- Web Share of the current deep link (the URL already carries the
             surface/channel state). Hidden on the kiosk — guests take THAT home
             via the QR pill, and the exhibit machine shouldn't open share
             sheets. -->
        <button
          v-if="!kiosk"
          type="button"
          class="sv-icon-btn"
          :aria-label="copied ? 'Link copied' : 'Share this view'"
          :title="copied ? 'Link copied!' : 'Share this view'"
          @click="share"
        >
          <font-awesome-icon :icon="copied ? 'check' : 'share-nodes'" />
        </button>

        <!-- Both redundant on desktop: the rail keeps these panels open. -->
        <button
          v-if="!wide"
          type="button"
          class="sv-icon-btn"
          :class="{ 'is-active': sheet === 'info' }"
          aria-label="About this app"
          title="What am I looking at?"
          @click="toggleInfo"
        >
          <font-awesome-icon icon="circle-info" />
        </button>
        <button
          v-if="!wide"
          type="button"
          class="sv-icon-btn"
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
        <p v-if="showUnobserved" class="sv-unobserved">
          <span class="sv-unobserved-text">
            You're looking at the Sun's far side — no telescope sees this half
            from Earth, so it isn't a photograph.
          </span>
          <button
            type="button"
            class="sv-unobserved-close"
            aria-label="Dismiss"
            @click="unobservedDismissed = true"
          >
            <font-awesome-icon icon="times" />
          </button>
        </p>
      </transition>

      <!-- Card and scrubber share one flex column (E1) instead of each
           carrying an independent `bottom` offset. The card used to sit at a
           fixed `bottom: 5.2rem` sized for the scrubber's height WITHOUT its
           `.ts-banner` (TimeScrubber.vue ~3-6, shown while `stale`); the
           banner adds ~18px that a constant can't see coming, so the
           scrubber's top edge rose above the card's bottom edge and (being
           later in the DOM, with nothing here carrying a z-index) painted
           over the card's last line AND stole its taps. Stacking them in
           normal flow means the card's position is always "whatever is
           directly above the scrubber's actual rendered height," computed by
           the browser every frame — no constant to go stale when the banner
           toggles, the label wraps, or a guest's font size changes. -->
      <div class="sv-bottom-stack">
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
import { TextureLoader, Vector3 } from "three";

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
import { deCollideLabels } from "../three/labelLayout";
import { ProjectTarget, Projected, cameraPosition, projectTargets } from "../three/project";
import { SolarWind, createSolarWind } from "../three/solarWind";
import { SpacecraftTrails, TrailInput, createSpacecraftTrails } from "../three/spacecraftTrails";
import { SunGlow, createSunGlow } from "../three/sunGlow";
import { OffLimbLayer, createOffLimb } from "../three/offLimb";
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
import { installSunGestures, type SunGestures } from "../wwt/gestures";
import {
  FieldColorMode,
  SurfaceMode,
  TextureChannel,
  attractDrift,
  fieldColorMode,
  frameT,
  frameTimes,
  getAppHandle,
  kiosk,
  layers,
  playing,
  resetToken,
  sceneUnix as sceneTime,
  sheet,
  surfaceMode,
  textureChannel,
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

/** Chip height is a 44 px tap target; 46 leaves 2 px of air between two. */
const LABEL_STRIDE_PX = 46;

/** Chips further apart than one chip-width never collide, so never move. */
const LABEL_SPREAD_PX = 96;

/** Below this the chip is close enough to its marker to need no leader. */
const LABEL_LEADER_MIN_PX = 6;

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
  /** Optional final line, set apart in warning color. */
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
  offLimb: OffLimbLayer | null;
  /** Off-limb crop URL currently loaded, so a re-check does not reload it. */
  offLimbUrl: string;
  offLimbDir: Vector3;
  offLimbUp: Vector3;
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
  /** Camera state the labels were last projected for — see PROJECT_MS. */
  lastCam: { lat: number; lng: number; zoom: number; rotation: number };
  dragging: boolean;
  destroyed: boolean;
  /** Last playhead value WE wrote to shared state, so the watcher can tell
   *  our own echo from a real outside change. */
  published: number;
  widthCss: number;
  heightCss: number;
  observer: ResizeObserver | null;
  /** Touch/pinch/twist handling; disposed on unmount (see gestures.ts). */
  gestures: SunGestures | null;
  /** Far-side fraction; non-reactive, see `unobservedShown`. */
  unobservedFrac: number;
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
  /** The swhv.oma.be live-position fetch has been issued (at most once). */
  liveRequested: boolean;
}

function makeRuntime(): Runtime {
  return {
    stage: null,
    fieldLines: null,
    surface: null,
    offLimb: null,
    offLimbUrl: "",
    offLimbDir: new Vector3(),
    offLimbUp: new Vector3(),
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
    gestures: null,
    unobservedFrac: 0,
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
    liveRequested: false,
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
      frameT, frameTimes, sceneTime, kiosk, layers, playing, resetToken, sheet,
      surfaceMode, fieldColorMode, textureChannel, wide,
      solarStats: stats,
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
      /** `events/events.json`, or null while it loads / when it is absent. */
      solarEvents: null as SolarEvents | null,
      /** Share button feedback on the clipboard-fallback path. */
      copied: false,
      copiedTimer: 0,
      /** One entry per chip de-collision had to move; see layoutLabels(). */
      leaders: [] as { id: string; style: Record<string, string> }[],

      rt: markRaw(makeRuntime()),
      /**
       * Whether the far-side note is up.
       *
       * A BOOLEAN in reactive state, with the underlying fraction kept on the
       * non-reactive runtime. It used to be the float, written on every
       * projection pass — and since the projection throttle is short-circuited
       * whenever the camera moves, that was a reactive write per frame during a
       * drag, dirtying the whole overlay's render effect to move a hint that
       * only ever appears or disappears.
       */
      unobservedShown: false,
      /**
       * The guest closed the note.
       *
       * Sticky for the session rather than per-turn: someone who has read it
       * once does not want it again every time they spin the Sun round, and it
       * is the same sentence every time.
       */
      unobservedDismissed: false,
    };
  },

  computed: {
    showUnobserved(): boolean {
      return this.unobservedShown && !this.unobservedDismissed;
    },

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

    /**
     * How many 44px buttons `.sv-buttons` is actually rendering right now:
     * recenter (always), share (hidden in kiosk), info + layers (both hidden
     * when `wide` — the desktop rail covers them). Written onto the root
     * element as `--sv-btn-count` (see the template's root `:style`) so the
     * layer popover's `top` offset (below, in `<style>`) can hang itself off
     * the stack's REAL length instead of the literal `4` it used to have —
     * that number was only ever right in narrow+non-kiosk; narrow+kiosk
     * renders 3 (no share button) and floated the popover ~48px too low.
     */
    visibleButtonCount(): number {
      let count = 1; // recenter — unconditional
      if (!this.kiosk) { count += 1; } // share
      if (!this.wide) { count += 2; } // info + layers
      return count;
    },
  },

  watch: {
    resetToken() {
      this.recenter();
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
      // The layer now starts OFF (useAppState), so this is where most guests
      // who ever see a spacecraft first ask for one — and the first place it is
      // worth spending two requests on swhv.oma.be. Once only: the baked
      // ephemeris is accurate to well under a pixel without it.
      if (value && !this.rt.liveRequested) { void this.refreshLivePositions(); }
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
    // worldwidetelescope.org for its imageset catalog. If the mode never
    // engages, say so plainly instead of showing a black rectangle.
    this.rt.modeTimer = window.setTimeout(() => {
      if (!solarSystemModeActive()) {
        console.error("[SolarView3D] solar-system mode did not engage within 10 s.");
        this.failed = true;
      }
    }, MODE_TIMEOUT_MS);

    if (!this.createStage()) { return; }

    // Touch input. Bound to the STAGE ROOT rather than the canvas, and in the
    // capture phase, so a finger that lands on a label chip still counts toward
    // a pinch — see src/wwt/gestures.ts for the four engine faults this
    // replaces. The engine's own touch and pointer handlers are already no-ops
    // (wwt-hacks.ts), so nothing competes with it.
    const stageRoot = this.$refs.root as HTMLElement | undefined;
    if (stageRoot) { this.rt.gestures = installSunGestures(stageRoot); }

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
    window.clearTimeout(this.copiedTimer);
    rt.observer?.disconnect();
    rt.gestures?.dispose();
    rt.abort?.abort();
    playing.value = false;

    rt.fieldLines?.dispose();
    rt.surface?.dispose();
    rt.offLimb?.dispose();
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

      // The part of the image that is NOT on the sphere. Created next to the
      // surface because it is the same picture, and it takes its texture from
      // whatever channel the surface settles on.
      rt.offLimb = markRaw(createOffLimb({ rSunAu: R_SUN_AU }));
      rt.stage.scene.add(rt.offLimb.object3d);

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
        this.layoutLabels();
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
     * where the branch cut is, and it normalizes `viewCamera` itself.
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
            frameTimes.value = manifest.frames.map((f) => f.magUnix);
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
      // The layer can be (re)built long after the guest picked a color — a
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
      // Before the first render: the line widths are meaningless until the
      // shader knows the framebuffer size (footgun 16).
      this.syncLineResolution();
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

      // Deferred until the layer is switched on (see the layers.spacecraft
      // watcher). A deep link that arrives with it already on still gets the
      // live dots, because the watcher has not run for that case.
      if (this.layers.spacecraft) { void this.refreshLivePositions(); }
    },

    /**
     * Optional freshener: swhv.oma.be reports ONE epoch per call, which is why
     * the trails are baked. Failure is silent — the Horizons interpolation is
     * accurate to well under a pixel anyway.
     */
    async refreshLivePositions(): Promise<void> {
      const rt = this.rt;
      rt.liveRequested = true;
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

    /**
     * Scene time: the magnetogram time under the playhead, or now.
     *
     * The arithmetic moved to useAppState's `sceneUnix` computed when the
     * sunspot chip needed the same answer — one definition, two readers. Kept
     * as a method because this file calls it from the render tick, where a
     * plain function read is cheaper to reason about than a computed.
     */
    sceneUnix(): number {
      return this.sceneTime;
    },

    updateSpacecraft(): void {
      const rt = this.rt;
      const { stage, trails, ephemeris } = rt;
      if (!stage || !trails || !ephemeris || !this.chips.length) { return; }

      const unix = this.sceneUnix();
      // The live dot is only honest at the newest frame; anywhere else in the
      // 72-hour window the baked ephemeris is the correct answer.
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

      // The imagery follows the playhead, so the photosphere, the sunspots and
      // the field lines all describe the same hour. Without this the sphere
      // carried the NEWEST map while the field lines morphed through three days
      // -- historical magnetic field over today's Sun, with the terminator
      // parked at today's sub-earth longitude.
      //
      // setFrameTime snaps to the nearest 4 h slot and no-ops when that is
      // already the frame on screen, so calling it on the chip cadence costs a
      // comparison per pass and only does work at a slot boundary.
      this.rt.surface?.setFrameTime(unix);

      // HYSTERESIS, not a single threshold. `unobservedFraction` is a smooth
      // function of camera angle, so one threshold means a drag that hovers near
      // it mounts and unmounts a <transition>-wrapped, backdrop-filtered element
      // several times a second. Show above 0.58, hide below 0.50, and in the
      // band between keep doing whatever it was doing.
      const frac = this.rt.surface?.unobservedFraction() ?? 0;
      this.rt.unobservedFrac = frac;
      const shown = this.unobservedShown ? frac > 0.50 : frac > 0.58;
      // Guarded because this is the only reactive write left in the per-frame
      // path here, and it must stay a no-op unless the note actually changes.
      if (shown !== this.unobservedShown) { this.unobservedShown = shown; }
      this.updateOffLimb();
    },

    /**
     * Aim the off-limb billboard and keep its texture in step with the surface.
     *
     * The crop is pulled from the surface's OWN manifest choice rather than
     * fetched independently: a run may not publish every channel, and the crop
     * has to match the channel the surface actually got, not the one the guest
     * asked for.
     */
    updateOffLimb(): void {
      const rt = this.rt;
      const offLimb = rt.offLimb;
      const surface = rt.surface;
      if (!offLimb || !surface) { return; }

      // The off-limb crop is a photograph of the corona AS SEEN FROM EARTH RIGHT
      // NOW (footgun 29), and the pipeline publishes exactly one of them --
      // per-frame crops would thrash a TextureLoader on every scrub step for a
      // band the guest is barely looking at. So while the playhead is in the
      // past, hide it rather than wrap today's prominences around a three-day-
      // old photosphere. The sphere itself is time-aligned; this one layer is
      // honest about only having "now".
      const atNow = surface.atNewestFrame();
      offLimb.setVisible(atNow);
      if (!atNow) { return; }

      const info = surface.textureInfo();
      if (info && info.offLimbUrl && info.offLimbUrl !== rt.offLimbUrl) {
        const wanted = info.offLimbUrl;
        const halfWidth = info.offLimbHalfWidthRSun;
        rt.offLimbUrl = wanted;
        new TextureLoader().load(wanted, (texture) => {
          if (rt.destroyed || rt.offLimbUrl !== wanted) {
            texture.dispose();
            return;
          }
          offLimb.setTexture(texture, halfWidth);
        }, undefined, () => {
          // Optional product: an absent crop just means no off-limb layer.
          if (rt.offLimbUrl === wanted) { rt.offLimbUrl = ""; }
        });
      }

      if (!surface.subEarthFrame(rt.offLimbDir, rt.offLimbUp)) { return; }
      offLimb.update(rt.cameraWorld, rt.offLimbDir, rt.offLimbUp);
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
     * Flare + CME catalog. Optional product: absent or empty simply means no
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
      // farther from the camera than the Sun's center while still being in front
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
     * Keep the chips off each other.
     *
     * Projection is exact, which is the problem: two active regions 12 deg
     * apart on the Sun land ~12 px apart on a phone, and the chips naming them
     * are 44 px tall. Measured on the live site across three viewports from
     * 360x640 to 820x700, ALL THREE surface chips (AR 4513, AR 4515 and the
     * sub-Earth marker) overlapped each other at every size.
     *
     * Runs on the combined set — a spacecraft chip and a region chip collide
     * exactly as readily as two region chips — and only at the 20 Hz DOM
     * cadence, never per frame.
     */
    layoutLabels(): void {
      const boxes: { chip: Chip | RegionChip; ax: number; ay: number;
        x: number; y: number; visible: boolean }[] = [];
      const collect = (chip: Chip | RegionChip, visible: boolean): void => {
        boxes.push({ chip, ax: chip.x, ay: chip.y, x: chip.x, y: chip.y, visible });
      };
      if (this.layers.spacecraft) {
        this.chips.forEach((chip) => collect(chip, chip.visible));
      }
      this.regionChips.forEach((chip) => collect(chip, chip.visible));
      collect(this.earthChip, this.earthChip.visible);

      deCollideLabels(boxes, { strideY: LABEL_STRIDE_PX, spreadX: LABEL_SPREAD_PX });

      const leaders: { id: string; style: Record<string, string> }[] = [];
      boxes.forEach((box) => {
        box.chip.y = box.y;
        if (!box.visible) { return; }
        const dy = box.y - box.ay;
        if (Math.abs(dy) < LABEL_LEADER_MIN_PX) { return; }
        // A pure vertical nudge, so the leader is a vertical line from the
        // marker's true point to where the chip ended up. Drawn from whichever
        // end is higher so the height is always positive.
        leaders.push({
          id: box.chip.id,
          style: {
            transform: `translate3d(${Math.round(box.ax)}px, `
              + `${Math.round(Math.min(box.ay, box.y))}px, 0)`,
            height: `${Math.round(Math.abs(dy))}px`,
          },
        });
      });
      this.leaders = leaders;
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
     * ("prototyping quality... research context"): the catalog is analyst-
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

    recenter(): void {
      // targetCamera only: the engine eases viewCamera toward it every frame,
      // so this is a smooth flight home for free (footgun 14).
      homeCamera(false);
    },

    toggleLayers(): void {
      this.sheet = this.sheet === "layers" ? null : "layers";
    },

    toggleInfo(): void {
      this.sheet = this.sheet === "info" ? null : "info";
    },

    /**
     * Native share sheet where available (every phone), clipboard fallback on
     * desktop. location.href is already the canonical deep link — useDeepLink
     * keeps ?surface=&fieldcolor=&texch= in step with the app state.
     *
     * Moved here from TopBar when the banner became a title pill: the control
     * belongs with the other three, not on its own in a row of its own.
     */
    async share(): Promise<void> {
      const url = window.location.href;
      const nav = navigator as Navigator & {
        share?: (data: { title: string; url: string }) => Promise<void>;
      };
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

    measure(): void {
      const root = this.$refs.root as HTMLElement | undefined;
      if (!root) { return; }
      this.rt.widthCss = root.clientWidth;
      this.rt.heightCss = root.clientHeight;
      this.syncLineResolution();
    },

    /**
     * Keep the fat orbit lines' screen-space widths correct.
     *
     * Line2 expands its quads in a vertex shader, so it needs the FRAMEBUFFER
     * size — and it must come from `gl.drawingBufferWidth/Height`, never from
     * `gl.canvas.width/height`, because the vendored three-wwt shim reports the
     * canvas in CSS px on DPR > 1 screens (footgun 16). `stage.bufferSize()` is
     * that source. The CSS width goes along so the widths declared in CSS px
     * become the right number of device px.
     *
     * Called from measure(), which is what the ResizeObserver and the
     * resize/orientationchange handlers already go through — so a device
     * rotation or a URL bar sliding away re-syncs it for free.
     */
    syncLineResolution(): void {
      const rt = this.rt;
      if (!rt.stage || !rt.trails) { return; }
      const buffer = rt.stage.bufferSize();
      rt.trails.setResolution(buffer.width, buffer.height, rt.widthCss);
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
// `z-index: 0` is load-bearing, not cosmetic. With `z-index: auto` this
// element creates NO stacking context, so its descendants (the scrubber at 5,
// the card slot at 20) competed directly with SIBLINGS in sol.vue -- which is
// how the brand mark spent a whole session invisible at z-index 3, and what the
// title pill would have walked straight into. Now the whole 3D view is one
// layer and a sibling only has to clear 0. (CLAUDE.md footgun 27.)
.solar-view-3d {
  position: relative;
  z-index: 0;
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

// z-index 11: this only ever had to clear `.solar-view-3d`'s own z-index 0
// (footgun 27) until three.js needed a fallback canvas. `three-wwt/utils.ts`
// (`src/three/`, off limits to this file) creates that overlay canvas with
// `style.zIndex = "10"` and appends it as a SIBLING of the WWT canvas --
// i.e. INSIDE this stacking context, above the z-index 5 this used to be.
// That path isn't only the `?three=overlay` URL flag: `src/three/stage.ts`
// falls back to it automatically on WebGL1-only devices, exactly the cheap
// phone a guest is likely holding. Below 10, field lines / solar wind /
// spacecraft sprites painted OVER the scrubber, the card and the labels
// (E7). Do not lower this back under 10 without also changing that canvas's
// z-index, which lives in a file this component may not edit.
.sv-overlay {
  position: absolute;
  inset: 0;
  z-index: 11;
  pointer-events: none;
}

.sv-labels {
  position: absolute;
  inset: 0;
  // Explicit rather than `auto` (E7): every direct child of `.sv-overlay`
  // gets one of these now, so paint order among them is a choice, not an
  // accident of DOM order -- which is exactly how the scrubber ended up
  // covering the card (E1) with nothing here to say it shouldn't.
  z-index: 1;
}

// From a marker's true projected point to the chip de-collision moved. Dark
// core inside a light edge, the same dual-contrast idea the chips themselves
// need: the dark half wins over the bright photosphere, the light half over the
// black sky, and one treatment therefore works on both.
.sv-leader {
  position: absolute;
  top: 0;
  left: 0;
  width: 1px;
  margin-left: -0.5px;
  background: rgba(245, 244, 240, 0.55);
  box-shadow: 0 0 0 0.5px rgba(5, 1, 15, 0.85);
  pointer-events: none;
}

// The stage now runs to the top of the page (the top bar is gone), so these
// have to clear a notch themselves.
.sv-buttons {
  position: absolute;
  top: calc(env(safe-area-inset-top) + 0.5rem);
  right: 0.5rem;
  z-index: 3; // see the z-index note on `.sv-labels` above (E7)
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
  background: rgba(9, 2, 24, 0.6);
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

// Below the whole stack. `--sv-btn-count` (set on `.solar-view-3d`'s root
// `:style` from the `visibleButtonCount` computed) is the ACTUAL number of
// 44px buttons `.sv-buttons` is rendering right now -- recenter always,
// share unless `kiosk`, info+layers unless `wide`. This used to be a
// literal `4`, and the comment here claimed it was "derived rather than
// typed as a magic number" -- it was not. In narrow+kiosk only 3 buttons
// render (no share button), and the popover floated ~48px below the real
// stack it was meant to hang off (E2).
.sv-layer-popover {
  position: absolute;
  top: calc(
    env(safe-area-inset-top) + 0.5rem
      + (var(--sv-btn-count) * 44px) + ((var(--sv-btn-count) - 1) * 0.4rem)
      + 0.4rem
  );
  right: 0.5rem;
  z-index: 4; // above `.sv-buttons` (E7) -- it's the popover FROM that stack

  // `.layer-panel` alone runs ~400px tall (6 rows * ~48px + the Surface
  // `.lp-group` block's ~78px + 2rem of panel padding) with no cap of its
  // own, and on a landscape phone (e.g. 812x375 -- still `!wide`, since
  // 812 < 900) the stage is only 375px tall with `.solar-view-3d`'s
  // `overflow: hidden` (above) clipping whatever doesn't fit -- silently,
  // with no scrollbar (E4). `max-height` reuses the exact formula `top`
  // uses above: whatever room `top` doesn't take, minus 1rem of breathing
  // room at the bottom of the stage. Unlike footgun 28's `1fr`-row case,
  // this cap is a hard length (not a flexible track share `.layer-panel`'s
  // own content size could inflate), so `max-height` + `overflow-y: auto`
  // alone are enough to turn "clipped with no scrollbar" into "scrollable" --
  // the `min-height: 0` on `.layer-panel` (LayerPanel.vue) is kept anyway,
  // as cheap insurance matching this codebase's usual pattern for a
  // scrollable panel, in case that ever changes to a flexible allocation.
  max-height: calc(
    100% - (
      env(safe-area-inset-top) + 0.5rem
        + (var(--sv-btn-count) * 44px) + ((var(--sv-btn-count) - 1) * 0.4rem)
        + 0.4rem
    ) - 1rem
  );
  overflow-y: auto;
  pointer-events: auto;
}

// No longer independently positioned (E1) -- it is the first flex item in
// `.sv-bottom-stack` below, which is what now supplies the bottom/left/right
// anchoring for the pair. `align-self: center` + `max-width` reproduce the
// old centered-and-capped look; `width: 100%` is what lets it actually
// reach that cap on a narrow phone instead of shrink-wrapping its text.
// `position: relative` stays -- not for this box's own placement (the flex
// column handles that now), but because `.sv-card-close` below anchors
// itself to it with `position: absolute; top; right`, and a `static` box
// is not a containing block for that.
.sv-card {
  position: relative;
  align-self: center;
  width: 100%;
  max-width: 22rem;
  padding: 0.8rem 2.2rem 0.8rem 0.9rem;
  border: 1px solid rgba(var(--sol-accent-rgb), 0.3);
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
  background: rgba(var(--sol-accent-rgb), 0.12);
  color: var(--sol-accent);
  font-size: 0.76rem;
  line-height: 1.35;
}

// Card and scrubber's shared positioning (E1). Was two independent
// `position: absolute` boxes: the card at a fixed `bottom: 5.2rem`, sized
// for `TimeScrubber`'s height WITHOUT its `.ts-banner` (TimeScrubber.vue
// ~3-6, shown while `stale`) -- the banner adds ~18px a constant can't see
// coming, so the scrubber's top edge rose above the card's bottom edge and,
// with nothing here carrying a z-index, painted over the card's last line
// (DOM order = paint order) AND stole its taps. A flex column removes the
// arithmetic: the card sits directly above whatever the scrubber's real
// rendered height is, recomputed by the browser on every layout, so no
// future change to the scrubber's content (banner, a wrapped label, a
// guest's larger font) can reopen this collision.
.sv-bottom-stack {
  position: absolute;
  left: 0.4rem;
  right: 0.4rem;
  bottom: 0.4rem;
  z-index: 5; // topmost of `.sv-overlay`'s children (E7) -- card + controls
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  pointer-events: none; // children opt back in, same contract as .sv-overlay
}

.sv-bottom {
  pointer-events: auto;
}

.sv-note {
  margin: 0;
  padding: 0.5rem 0.6rem;
  border-radius: 10px;
  background: rgba(9, 2, 24, 0.7);
  color: var(--sol-text-dim);
  font-size: 0.75rem;
  text-align: center;
}

// Clear of the button column and the title pill. Deliberately quiet: it
// explains the dimming the guest has just caused, it is not an alert.
//
// Horizontal (E3a): was centered edge-to-edge (`left: 50%` + translateX), so
// at 360px its ~328px width spanned x 16-344 while `.sv-buttons` (right:
// 0.5rem, 44px wide) occupies x 308-352 -- they overlapped on any phone
// narrower than ~416px, and the backdrop-filter blur made the overlap
// visible. Anchoring BOTH edges instead of centering a computed width makes
// the box "whatever room is left after clearing the button column," by
// construction, on every viewport -- the same idea `.sol-title` uses now
// (E5) -- rather than a symmetric inset that only happens to clear an
// asymmetric obstacle. `margin: 0 auto` still recenters the (possibly
// narrower) box once `max-width` caps it clear of both edges on a wide
// screen.
//
// Vertical (E3b): was a flat `3.6rem` with NO safe-area term, tuned to clear
// `.sol-title`'s bottom edge on a device with no notch. `.sol-title` (a
// SIBLING of the entire 3D view, at z-index 6 outside a view that is
// z-index 0 -- footgun 27) DOES add the inset, so on a notched phone
// (safe-area-inset-top ~= 47px) the title moved down while this note held
// still, and the title covered it completely. Adding the same inset term
// keeps the SAME buffer under the title on every device, not only the one
// this constant happened to be tuned for.
.sv-unobserved {
  position: absolute;
  top: calc(env(safe-area-inset-top) + 3.6rem);
  left: 0.5rem;
  right: 3.75rem; // clears .sv-buttons (44px + 0.5rem inset ~= 3.25rem) with margin to spare
  max-width: 24rem;
  margin: 0 auto;
  padding: 0.45rem 0.5rem 0.45rem 0.7rem;
  border-radius: 10px;
  // Was rgba(...,0.78) plus blur(4px). The blur is gone for the same reason it
  // left the label chips: a backdrop-filter is recomputed whenever its BACKDROP
  // changes, and the backdrop here is a canvas repainting at the full frame
  // rate — so this note cost a full-width blur every frame merely by existing.
  // A higher alpha is what actually makes the text readable.
  background: rgba(9, 2, 24, 0.92);
  border: var(--sol-panel-border);
  color: var(--sol-text-dim);
  font-size: 0.74rem;
  line-height: 1.3;
  text-align: left;
  // Was `none`. The note now carries a close button, so it has to take taps —
  // but only the button does anything, and the note sits clear of the button
  // column (see the E3 note above), so this cannot swallow a camera gesture.
  // A two-finger gesture starting here still reaches the camera anyway:
  // gestures.ts listens on the stage root in the capture phase.
  pointer-events: auto;
  display: flex;
  align-items: flex-start;
  gap: 0.35rem;
  z-index: 2; // see the z-index note on `.sv-labels` above (E7)
}

.sv-unobserved-text {
  flex: 1 1 auto;
  min-width: 0;
}

.sv-unobserved-close {
  flex: 0 0 auto;
  // 28px, not the 44px a primary control gets: this is a dismiss affordance on
  // an advisory note, and a 44px square next to two lines of 0.74rem text would
  // outweigh the sentence it is attached to. The whole note is only reachable
  // deliberately, so the smaller target is the right trade.
  width: 28px;
  height: 28px;
  margin: -0.15rem -0.15rem 0 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--sol-text-quiet);
  font-size: 0.8rem;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;

  &:hover,
  &:focus-visible {
    color: var(--sol-text);
    background: var(--sol-surface-raised);
  }
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
