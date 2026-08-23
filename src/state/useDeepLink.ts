// =====================================================================
// Deep links — one-way read at boot, debounced write-back thereafter
// =====================================================================
// A guest arrives here from a QR code printed weeks earlier, or from a link a
// friend texted them. Two rules follow from that:
//
//   1. INVALID VALUES FALL BACK SILENTLY. A mistyped or stale parameter must
//      never produce an error, an empty screen, or a 404 image request. Worst
//      case the guest gets the default view, which is a perfectly good app.
//   2. Never pushState. The back button belongs to the browser, not to us —
//      a guest who taps five channels should leave in one Back press.
//
// Writes are debounced (300 ms) so dragging the resolution chip or flipping
// channels quickly doesn't hammer the history API, and only non-default values
// are written so the URL a guest might share stays short and legible.

import { watch } from "vue";

import { DEFAULT_CHANNEL, hasAnyMovie, isDiskRes, isProductId, product } from "../data/sdoCatalog";
import { queryParams } from "../urlParams";
import {
  DEFAULT_DISK_MODE,
  DEFAULT_DISK_RES,
  DEFAULT_PFSS,
  DEFAULT_FIELD_COLOR,
  DEFAULT_SURFACE,
  DEFAULT_TEXTURE_CHANNEL,
  DEFAULT_VIEW,
  channel,
  diskMode,
  diskRes,
  pfssOverlay,
  fieldColorMode,
  surfaceMode,
  textureChannel,
  view,
} from "./useAppState";

const DEBOUNCE_MS = 300;

/** Params this module owns. Everything else in the query string is preserved. */
const OWNED_PARAMS = ["view", "wl", "pfss", "movie", "res", "surface", "fieldcolor",
  "texch"];

let started = false;
let writeTimer = 0;

/** "1"/"true"/"" (bare presence) is on; "0"/"false" is off; absent is null. */
function readFlag(params: URLSearchParams, name: string): boolean | null {
  const raw = params.get(name);
  if (raw === null) { return null; }
  return raw !== "0" && raw !== "false";
}

function readOnce(): void {
  const params = queryParams();

  const rawView = params.get("view");
  if (rawView === "3d" || rawView === "disk") {
    view.value = rawView;
  }

  const rawChannel = params.get("wl");
  if (isProductId(rawChannel)) {
    channel.value = rawChannel;
  }

  // pfss is meaningless on a channel with no published overlay — drop it
  // rather than firing a request we know 404s.
  const rawPfss = readFlag(params, "pfss");
  if (rawPfss !== null) {
    pfssOverlay.value = rawPfss && product(channel.value).hasPfss;
  }

  const rawMovie = readFlag(params, "movie");
  if (rawMovie !== null) {
    diskMode.value = rawMovie && hasAnyMovie(channel.value) ? "movie" : "still";
  }

  const rawRes = Number(params.get("res"));
  if (Number.isFinite(rawRes) && isDiskRes(rawRes)) {
    diskRes.value = rawRes;
  }

  const rawSurface = params.get("surface");
  if (rawSurface === "sdo" || rawSurface === "synthetic" || rawSurface === "wwt") {
    surfaceMode.value = rawSurface;
  }

  const rawTexChannel = params.get("texch");
  if (rawTexChannel === "0171" || rawTexChannel === "0304"
      || rawTexChannel === "0193" || rawTexChannel === "HMIIC"
      || rawTexChannel === "HMIB") {
    textureChannel.value = rawTexChannel;
  }

  const rawFieldColor = params.get("fieldcolor");
  if (rawFieldColor === "polarity" || rawFieldColor === "blue") {
    fieldColorMode.value = rawFieldColor;
  }
}

/** Build the query string: unrelated params first, then our non-defaults. */
function currentQuery(): string {
  const params = queryParams();
  OWNED_PARAMS.forEach((name) => params.delete(name));

  if (view.value !== DEFAULT_VIEW) { params.set("view", view.value); }
  if (channel.value !== DEFAULT_CHANNEL) { params.set("wl", channel.value); }
  if (pfssOverlay.value !== DEFAULT_PFSS) { params.set("pfss", pfssOverlay.value ? "1" : "0"); }
  if (diskMode.value !== DEFAULT_DISK_MODE) { params.set("movie", diskMode.value === "movie" ? "1" : "0"); }
  if (diskRes.value !== DEFAULT_DISK_RES) { params.set("res", String(diskRes.value)); }
  if (surfaceMode.value !== DEFAULT_SURFACE) { params.set("surface", surfaceMode.value); }
  if (fieldColorMode.value !== DEFAULT_FIELD_COLOR) {
    params.set("fieldcolor", fieldColorMode.value);
  }
  if (textureChannel.value !== DEFAULT_TEXTURE_CHANNEL) {
    params.set("texch", textureChannel.value);
  }

  return params.toString();
}

function writeNow(): void {
  const qs = currentQuery();
  const url = window.location.pathname + (qs ? `?${qs}` : "") + window.location.hash;
  // replaceState, never pushState: see rule 2 above.
  window.history.replaceState(window.history.state, "", url);
}

function scheduleWrite(): void {
  window.clearTimeout(writeTimer);
  writeTimer = window.setTimeout(writeNow, DEBOUNCE_MS);
}

/**
 * Read the incoming deep link once, then keep the URL in sync with the state.
 * Safe to call more than once (later calls are no-ops).
 */
export function initDeepLink(): void {
  if (started) { return; }
  started = true;

  readOnce();
  watch(
    [view, channel, pfssOverlay, diskMode, diskRes, surfaceMode, fieldColorMode,
      textureChannel],
    scheduleWrite);
}
