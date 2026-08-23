// =====================================================================
// App state — module-level refs, deliberately not pinia
// =====================================================================
// The whole app is one screen with a handful of knobs, and every knob is
// either in the URL (see useDeepLink.ts) or a transient UI flag. A pinia store
// would buy nothing here, and pinia's only other consumer in this project is
// the WWT engine — which must stay out of the entry chunk (CLAUDE.md
// "Entry chunk must stay engine-free"). So: plain refs, imported directly by
// the components that need them.

import { App, reactive, ref } from "vue";

import { DEFAULT_CHANNEL, DiskRes, ProductId } from "../data/sdoCatalog";
import { boolParam } from "../urlParams";

export type ViewId = "disk" | "3d";
export type DiskMode = "still" | "movie";
export type SheetId = "info" | "layers";

// --- defaults (also the "omit from the URL" values in useDeepLink) ---------
export const DEFAULT_VIEW: ViewId = "disk";
export const DEFAULT_PFSS = false;
export const DEFAULT_DISK_MODE: DiskMode = "still";
export const DEFAULT_DISK_RES: DiskRes = 2048;

/** Which top-level view is showing: the flat "Sun Now" disk or the 3D scene. */
export const view = ref<ViewId>(DEFAULT_VIEW);

/** Selected SDO channel. */
export const channel = ref<ProductId>(DEFAULT_CHANNEL);

/** Bake GSFC's PFSS field-line overlay into the still (stills only). */
export const pfssOverlay = ref(DEFAULT_PFSS);

/** Still image or movie playback in the disk view. */
export const diskMode = ref<DiskMode>(DEFAULT_DISK_MODE);

/** Requested still resolution. The viewer may serve something smaller on a
 *  metered/slow connection, or larger when the guest zooms in. */
export const diskRes = ref<DiskRes>(DEFAULT_DISK_RES);

export interface LayerFlags {
  fieldLines: boolean;
  wind: boolean;
  spacecraft: boolean;
  orbits: boolean;
  glow: boolean;
}

/** 3D-view layer toggles (M-W5/M-W6 consume these). */
export const layers = reactive<LayerFlags>({
  fieldLines: true,
  wind: true,
  spacecraft: true,
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
 * Which AIA channel the 3D sphere is painted with, in angstrom. Must be one the
 * pipeline publishes (config.TEX_WAVELENGTHS); sunSurface falls back to the
 * manifest's default layer if this run did not publish it.
 */
export type TextureChannel = 171 | 304 | 193;

export const DEFAULT_TEXTURE_CHANNEL: TextureChannel = 171;

export const textureChannel = ref<TextureChannel>(DEFAULT_TEXTURE_CHANNEL);

/**
 * How the field lines are coloured. "polarity" is the dome show's own palette
 * (gold closed arcades, blue outbound open field, orange inbound) and carries
 * real information; "blue" paints every line one electric blue, which reads as
 * a single structure and photographs better on a dome.
 */
export type FieldColorMode = "polarity" | "blue";

export const DEFAULT_FIELD_COLOR: FieldColorMode = "polarity";

export const fieldColorMode = ref<FieldColorMode>(DEFAULT_FIELD_COLOR);

/**
 * Playhead of the 48-hour field-line animation, in FRACTIONAL FRAME INDICES
 * (0 = oldest published frame, frameCount-1 = newest ≈ "now"). SolarView3D owns
 * it: the renderer writes the current value back ~10x/s so TimeScrubber can
 * follow, and an outside write (deep link, reset) is applied to the renderer.
 * Note that resetView() parks it at 0, and SolarView3D deliberately overrides
 * that with the NEWEST frame — the resting state of this app is "now".
 */
export const frameT = ref(0);

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
 * Bumped by resetView(). Viewers watch it to re-centre: the disk viewer drops
 * its pinch-zoom transform, the 3D view will re-frame the camera.
 */
export const resetToken = ref(0);

/**
 * Timestamp of the last successful disk-image load. ChannelPicker watches it
 * to start prefetching neighbouring channels only once the image the guest
 * actually asked for has settled.
 */
export const diskSettledAt = ref(0);

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
