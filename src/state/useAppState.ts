// =====================================================================
// App state — module-level refs, deliberately not pinia
// =====================================================================
// The whole app is one screen with a handful of knobs, and every knob is
// either in the URL (see useDeepLink.ts) or a transient UI flag. A pinia store
// would buy nothing here, and pinia's only other consumer in this project is
// the WWT engine — which must stay out of the entry chunk (CLAUDE.md
// "Entry chunk must stay engine-free"). So: plain refs, imported directly by
// the components that need them.

import { App, computed, reactive, ref } from "vue";

import { boolParam } from "../urlParams";

export type SheetId = "info" | "layers";

export interface LayerFlags {
  fieldLines: boolean;
  wind: boolean;
  spacecraft: boolean;
  orbits: boolean;
  glow: boolean;
}

/**
 * 3D-view layer toggles (M-W5/M-W6 consume these).
 *
 * `spacecraft` starts OFF deliberately. The Sun and its field are the story;
 * three mission markers and their trails are a second, unrelated one, and on a
 * phone they land on top of the disk before the guest has looked at it. The
 * layer panel is the way in, and SolarView3D defers the two live-position
 * requests until it is switched on, so a guest who never opens it pays nothing.
 */
export const layers = reactive<LayerFlags>({
  fieldLines: true,
  wind: true,
  spacecraft: false,
  orbits: false,
  glow: true,
});

/** How the Sun's own surface is painted in the 3D view:
 *  "sdo" the pipeline's AIA Carrington map, "synthetic" animated granulation
 *  plus the real sunspots, "wwt" the engine's own flat texture. "sdo" falls
 *  back to "synthetic" on its own while no texture has loaded. */
export type SurfaceMode = "sdo" | "synthetic" | "wwt";

export const DEFAULT_SURFACE: SurfaceMode = "sdo";

export const surfaceMode = ref<SurfaceMode>(DEFAULT_SURFACE);

/**
 * Which SDO product the 3D sphere is painted with, as the product CODE — the
 * same identifiers `sdoCatalog` uses, so one table names them for both the
 * chips and the sphere. Not a wavelength: HMIB is a magnetogram and HMIIC a
 * colorized continuum image, and neither has one.
 *
 * Must be a channel the pipeline publishes (config.TEX_CHANNELS); sunSurface
 * falls back to the manifest's default layer if this run did not publish it.
 */
export type TextureChannel = "0171" | "0304" | "0193" | "HMIIC" | "HMIB";

export const DEFAULT_TEXTURE_CHANNEL: TextureChannel = "0171";

export const textureChannel = ref<TextureChannel>(DEFAULT_TEXTURE_CHANNEL);

/**
 * True on a screen wide enough for the desktop rail (>= 900 px).
 *
 * Shared rather than local to sol.vue because it changes WHERE panels live,
 * not just how they look: on a phone the info sheet and the layer popover are
 * overlays opened from a button, and on a desktop they are permanent columns
 * in the right-hand rail. Both the owner of the rail (sol.vue) and the owner
 * of the buttons (SolarView3D, TopBar) have to agree on which world they are
 * in, or the guest gets two copies of the same panel.
 */
export const wide = ref(false);

/**
 * How the field lines are colored. "polarity" is the dome show's own palette
 * (gold closed arcades, blue outbound open field, orange inbound) and carries
 * real information; "blue" paints every line one electric blue, which reads as
 * a single structure and photographs better on a dome.
 */
export type FieldColorMode = "polarity" | "blue";

/**
 * Blue, not polarity, is the resting state. Polarity encodes real information
 * but it is a three-color legend a guest has not been given yet; one electric
 * blue reads immediately as a single structure wrapped around the Sun, and the
 * legend is one tap away in the layer panel. `?fieldcolor=polarity` is now the
 * non-default value useDeepLink writes.
 */
export const DEFAULT_FIELD_COLOR: FieldColorMode = "blue";

export const fieldColorMode = ref<FieldColorMode>(DEFAULT_FIELD_COLOR);

/**
 * Playhead of the 72-hour field-line animation, in FRACTIONAL FRAME INDICES
 * (0 = oldest published frame, frameCount-1 = newest ≈ "now"). SolarView3D owns
 * it: the renderer writes the current value back ~10x/s so TimeScrubber can
 * follow, and an outside write (deep link, reset) is applied to the renderer.
 * Note that resetView() parks it at 0, and SolarView3D deliberately overrides
 * that with the NEWEST frame — the resting state of this app is "now".
 */
export const frameT = ref(0);

/**
 * Magnetogram time of each published frame, unix seconds, oldest first — the
 * `mag_unix` column of `pfss/manifest.json`.
 *
 * Shared rather than private to SolarView3D because `frameT` alone is a
 * fractional INDEX and cannot be turned into a wall-clock time without it.
 * Anything outside the 3D view that has to answer "when is the guest looking
 * at?" — today the sunspot chip — needs both. SolarView3D is still the only
 * writer, exactly as it is for `frameT`.
 */
export const frameTimes = ref<number[]>([]);

/**
 * The moment under the playhead, unix seconds — `frameTimes` interpolated at
 * `frameT`. Falls back to now while no manifest has loaded, which is also the
 * right answer for a build with no PFSS product at all.
 *
 * Kept here rather than duplicated per consumer so there is exactly one
 * definition of "scene time"; SolarView3D's own `sceneUnix()` reads it.
 */
export const sceneUnix = computed<number>(() => {
  const times = frameTimes.value;
  if (!times.length) { return Date.now() / 1000; }
  const last = times.length - 1;
  const t = Math.min(Math.max(frameT.value, 0), last);
  const indexA = Math.min(Math.floor(t), last);
  const indexB = Math.min(indexA + 1, last);
  return times[indexA] + (times[indexB] - times[indexA]) * (t - indexA);
});

/** Field-line animation playback (M-W5). */
export const playing = ref(false);

/** Which overlay sheet is open, if any. */
export const sheet = ref<SheetId | null>(null);

/** Kiosk mode (lobby touchscreen), from `?kiosk=1`. Activated in M-W7. */
export const kiosk = ref(boolParam("kiosk"));

/**
 * Kiosk attract loop: drift the 3D camera slowly round the Sun. Set by
 * kiosk/attract.ts, consumed by SolarView3D's per-frame tick — the attract
 * module lives in the entry chunk and so must not import the WWT engine
 * (CLAUDE.md "Entry chunk must stay engine-free"), which makes a shared
 * boolean the whole interface between the two.
 */
export const attractDrift = ref(false);

/**
 * Bumped by resetView(). Viewers watch it to re-center: the disk viewer drops
 * its pinch-zoom transform, the 3D view will re-frame the camera.
 */
export const resetToken = ref(0);

/** Reset the viewer to its resting state: no zoom, animation parked at "now". */
export function resetView(): void {
  frameT.value = 0;
  playing.value = false;
  resetToken.value += 1;
}

// --- Vue app handle -------------------------------------------------------
// The 3D milestone's async loader needs the app instance to install wwtPinia
// and register the WWT component AFTER mount (main.ts must not import the
// engine). sol.vue stashes the instance here at mount time so the loader can
// pick it up without prop-drilling or a second createApp.

let handle: App | null = null;

export function setAppHandle(app: App): void {
  handle = app;
}

export function getAppHandle(): App | null {
  return handle;
}
