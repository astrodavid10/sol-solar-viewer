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
// Writes are debounced (300 ms) so flipping channels quickly doesn't hammer the
// history API, and only non-default values are written so the URL a guest might
// share stays short and legible.
//
// LEGACY PARAMS. The disk view this file used to carry state for (`view`, `wl`,
// `pfss`, `movie`, `res`) was deleted in the single-sphere consolidation. They
// are still DELETED from the query string on write — a QR printed before that
// change can carry them, and leaving them in a URL the guest then shares would
// propagate settings for a screen that no longer exists. They are simply not
// read back.

import { watch } from "vue";

import { queryParams } from "../urlParams";
import {
  DEFAULT_FIELD_COLOR,
  DEFAULT_SURFACE,
  DEFAULT_TEXTURE_CHANNEL,
  fieldColorMode,
  surfaceMode,
  textureChannel,
} from "./useAppState";

const DEBOUNCE_MS = 300;

/** Params this module owns. Everything else in the query string is preserved. */
const OWNED_PARAMS = ["surface", "fieldcolor", "texch"];

/** Params from the deleted disk view: stripped on write, never read. */
const LEGACY_PARAMS = ["view", "wl", "pfss", "movie", "res"];

let started = false;
let writeTimer = 0;

function readOnce(): void {
  const params = queryParams();

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
  LEGACY_PARAMS.forEach((name) => params.delete(name));

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
  watch([surfaceMode, fieldColorMode, textureChannel], scheduleWrite);
}
