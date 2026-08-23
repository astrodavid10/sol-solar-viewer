// =====================================================================
// Kiosk attract loop — what the lobby screen does when nobody is there
// =====================================================================
// A planetarium lobby screen is idle most of the day, and an idle screen has
// exactly one job: look alive enough that a passing guest reaches out and
// touches it. So after `?kioskIdle` seconds (90 s by default) the app takes
// itself for a walk — one continuous 3D scene, camera drifting round the Sun,
// field lines looping the 48 h animation, while the sphere's texture channel
// cycles underneath it all:
//
//   HMIIC → 0171 → 0193 → 0304 → HMIB, 15 s each (~75 s per cycle), forever,
//   re-homing the camera at the top of every cycle.
//
// (There used to be a separate 2D "disk" leg here — SDO stills shown flat,
// cut to from the 3D scene. The disk view is gone: imagery now paints the
// sphere directly, so the attract loop never leaves 3D. It just changes what
// the Sun is wearing.)
//
// Three rules shape the code below:
//
//   1. NO ENGINE IMPORTS. This module lives in the entry chunk, which must
//      stay free of WWT and three.js (CLAUDE.md "Entry chunk must stay
//      engine-free"). The camera drift is therefore a shared boolean —
//      `attractDrift` — that SolarView3D's existing per-frame tick consumes.
//      Everything else the loop does is a write to a state ref.
//   2. ANY TOUCH WINS, INSTANTLY. The idle watcher's activity callback stops
//      the timers and puts back the texture channel the loop found, so a
//      guest never has to undo the screensaver before they can explore.
//   3. NOTHING THE LOOP DOES IS A STATISTIC. The guest's stats session is
//      closed before the first attract move and reopened on the next touch;
//      kioskStats then no-ops on its own for everything in between.

import { ref, watch } from "vue";

import { IdleWatcher, KIOSK_IDLE_MS, createIdleWatcher } from "./kiosk";
import { statsInit, statsSessionEnd, statsSessionStart, statsTrack } from "./kioskStats";
import {
  TextureChannel,
  attractDrift,
  kiosk,
  playing,
  resetView,
  sheet,
  textureChannel,
} from "../state/useAppState";
import { numberParam } from "../urlParams";

/**
 * Dwell time per texture channel. Switching `textureChannel` costs a real
 * download (258-773 KB per CLAUDE.md's measured sizes) plus a GPU decode, so
 * this has to comfortably outlast that or the loop would thrash the network
 * and show a stale/blank sphere more often than a settled one. 15 s clears
 * that with room to spare on kiosk wifi, while still changing often enough
 * that a guest who glances over for a few seconds sees the Sun differently
 * dressed than the guest before them.
 */
const PHASE_CHANNEL_MS = 15_000;

/**
 * The channels shown, in the order shown, and why this order:
 *   HMIIC — colorized continuum: the Sun "as your eye would see it" (with
 *           sunspots). The most legible anchor image, so the loop starts and
 *           ends on it — whoever glances over mid-cycle is more likely to
 *           catch something recognizable.
 *   0171  — quiet corona, calm gold loops: the gentlest step up from visible
 *           light into EUV.
 *   0193  — hotter corona / active regions: livelier structure, still a
 *           gold-green palette that reads easily next to 0171.
 *   0304  — chromosphere & prominences: the most dramatic-looking channel
 *           (bright reds, visible filaments) — placed as the mid-cycle peak
 *           rather than the opener.
 *   HMIB  — the magnetogram: the black/white polarity map that is the actual
 *           source of the field lines that have been arcing overhead the
 *           whole time. Ending here ties the sphere's texture back to the 3D
 *           structure the guest has been watching, right before the loop
 *           re-homes the camera and starts over on HMIIC.
 * Five channels x 15 s = 75 s per full cycle, inside the 60-90 s target in
 * the brief: long enough that a passing guest sees the Sun visibly change,
 * short enough that someone who lingers doesn't wait too long for variety.
 */
const ATTRACT_CHANNELS: TextureChannel[] = ["HMIIC", "0171", "0193", "0304", "HMIB"];

/**
 * Grace period between "idle" and the first attract move. A guest who walked
 * away and turned back gets their screen unchanged, and a hovering hand that
 * trips the watcher's own idle→active→idle path doesn't cause a visible flap.
 */
const SETTLE_MS = 1_500;

/**
 * True while the attract loop is running. Read by sol.vue for the nightly
 * maintenance reload (only safe when no guest is watching) and the
 * "Touch to explore" hint.
 */
export const attractActive = ref(false);

/** What the screen looked like before the loop started; restored on exit. */
interface Snapshot {
  textureChannel: TextureChannel;
}

let watcher: IdleWatcher | null = null;
let statsTeardown: (() => void) | null = null;
let stopTracking: (() => void) | null = null;
let timer = 0;
/** True during the SETTLE_MS window: not attracting yet, but committed to it. */
let pending = false;
let phase = 0;
let saved: Snapshot | null = null;
/** True while the loop itself is writing state — see selfWrite/trackUsage. */
let writing = false;

/**
 * Every state write the loop makes goes through here. `attractActive` alone
 * can't gate the usage watchers: the restore-on-exit writes happen with the
 * flag already down, and would otherwise be counted as the arriving guest's
 * first channel pick. Paired with the sync-flush watcher in trackUsage(),
 * this flag is exact.
 */
function selfWrite(apply: () => void): void {
  writing = true;
  try {
    apply();
  } finally {
    writing = false;
  }
}

// ── Choreography ────────────────────────────────────────────────────────────

/**
 * One texture-channel dwell. `rehome` is true once per full cycle (the first
 * step) — re-homing every dwell would reset the 48 h field-line playhead to 0
 * every 15 s and the animation would never visibly progress, but never
 * re-homing at all would let the drifting camera wander somewhere useless
 * over an unattended run that can go for hours.
 */
function beginChannelPhase(id: TextureChannel, rehome: boolean): void {
  selfWrite(() => {
    if (rehome) {
      // resetView() re-homes the camera (via resetToken) and parks the
      // playhead — and clears `playing` on the way, so the play flag has to
      // come after it.
      resetView();
      playing.value = true;
      attractDrift.value = true;
    }
    textureChannel.value = id;
  });
}

/** One step of the loop: cycle the sphere's texture channel forever. */
function nextPhase(): void {
  if (!attractActive.value) { return; }
  const step = phase % ATTRACT_CHANNELS.length;
  phase += 1;
  beginChannelPhase(ATTRACT_CHANNELS[step], step === 0);
  timer = window.setTimeout(nextPhase, PHASE_CHANNEL_MS);
}

function enterAttract(): void {
  // The watcher's throttled pointermove handler clears its own idle flag
  // without calling onActive, so a hovering hand can fire onIdle a second time
  // mid-loop; `pending` covers the settle window the same way.
  if (!kiosk.value || attractActive.value || pending) { return; }

  // Close the guest's session first: everything after this line is the app
  // talking to itself, and none of it is usage data.
  statsSessionEnd(watcher?.lastActivityTs() ?? Date.now());

  saved = { textureChannel: textureChannel.value };

  pending = true;
  window.clearTimeout(timer);
  timer = window.setTimeout(() => {
    pending = false;
    attractActive.value = true;
    // Only now: a guest who turns back during the settle window keeps the
    // sheet they had open.
    sheet.value = null;
    phase = 0;
    nextPhase();
  }, SETTLE_MS);
}

/** Leave attract mode and put back what the guest would have seen. */
function exitAttract(): void {
  if (!attractActive.value && !pending) { return; }
  window.clearTimeout(timer);
  timer = 0;
  attractActive.value = false;
  pending = false;
  selfWrite(() => {
    attractDrift.value = false;
    playing.value = false;
    if (saved) {
      textureChannel.value = saved.textureChannel;
      saved = null;
    }
  });
}

/**
 * Any genuine activity. The watcher has already reset its own idle clock by
 * the time this runs, so exiting here is all the "reset the timer" needed.
 */
function onActivity(): void {
  exitAttract();
  // First touch after load, or after an attract reset. Idempotent while a
  // session is already open.
  statsSessionStart();
}

// ── Usage tracking ──────────────────────────────────────────────────────────

/**
 * The one thing worth counting beyond taps: which channel a guest picks to
 * paint the sphere with. (There used to be a second watcher here counting
 * 2D→3D switches; with the disk view gone there's only one view, so
 * "switched into 3D" isn't an event that can happen any more — this is what
 * it was replaced with.) `flush: "sync"` is load-bearing — the callback has
 * to run inside the write so `writing` still reads true for the loop's own
 * writes; a queued (default pre-flush) callback would see it back down and
 * count them. statsTrack's own "no open session" rule is the second line of
 * defense.
 *
 * Note the rollup field name is exo-era (`planets`): kioskStats.ts is shared
 * verbatim across data stories, so a channel id lands in `planets`.
 */
function trackUsage(): () => void {
  const stopChannel = watch(textureChannel, (id) => {
    if (writing || attractActive.value) { return; }
    statsTrack("select", id);
  }, { flush: "sync" });
  return () => { stopChannel(); };
}

// ── Lifecycle ───────────────────────────────────────────────────────────────

/**
 * Start watching for idleness (kiosk mode only; a no-op otherwise, and
 * idempotent). `?kioskIdle=<seconds>` shortens the timeout for testing —
 * `?kiosk=1&kioskIdle=10` is the exhibit rehearsal URL.
 */
export function initAttract(): void {
  if (!kiosk.value || watcher !== null) { return; }

  // Anonymous, local-only usage stats (?kioskStats=1 reads them back).
  statsTeardown = statsInit(true);
  stopTracking = trackUsage();

  const overrideS = numberParam("kioskIdle");
  const idleMs = overrideS !== null && overrideS > 0 ? overrideS * 1000 : KIOSK_IDLE_MS;

  watcher = createIdleWatcher({
    idleMs,
    onIdle: enterAttract,
    onActive: onActivity,
    onTap: () => statsTrack("tap"),
  });
  watcher.start();
}

/**
 * Tear the whole thing down: leave attract mode, stop the idle watcher, the
 * usage watchers and the stats flush timer. A production kiosk never unmounts,
 * but dev HMR does — and without this each reload stacked another watcher.
 */
export function stopAttract(): void {
  exitAttract();
  watcher?.stop();
  watcher = null;
  stopTracking?.();
  stopTracking = null;
  statsTeardown?.();
  statsTeardown = null;
}
