// =====================================================================
// Kiosk attract loop — what the lobby screen does when nobody is there
// =====================================================================
// A planetarium lobby screen is idle most of the day, and an idle screen has
// exactly one job: look alive enough that a passing guest reaches out and
// touches it. So after `?kioskIdle` seconds (90 s by default) the app takes
// itself for a walk:
//
//   3D for 45 s   — field-line animation looping, camera drifting slowly
//                   round the Sun (2°/s), re-homed at the start of every leg
//   disk for ~21 s — 0304 → 0171 → 0193, 7 s each: the three most photogenic
//                   channels, as big bright stills
//   …and repeat.
//
// Three rules shape the code below:
//
//   1. NO ENGINE IMPORTS. This module lives in the entry chunk, which must
//      stay free of WWT and three.js (CLAUDE.md "Entry chunk must stay
//      engine-free"). The camera drift is therefore a shared boolean —
//      `attractDrift` — that SolarView3D's existing per-frame tick consumes.
//      Everything else the loop does is a write to a state ref.
//   2. ANY TOUCH WINS, INSTANTLY. The idle watcher's activity callback stops
//      the timers and puts back the view/channel the loop found, so a guest
//      never has to undo the screensaver before they can explore.
//   3. NOTHING THE LOOP DOES IS A STATISTIC. The guest's stats session is
//      closed before the first attract move and reopened on the next touch;
//      kioskStats then no-ops on its own for everything in between.

import { ref, watch } from "vue";

import { IdleWatcher, KIOSK_IDLE_MS, createIdleWatcher } from "./kiosk";
import { statsInit, statsSessionEnd, statsSessionStart, statsTrack } from "./kioskStats";
import { ProductId } from "../data/sdoCatalog";
import {
  DiskMode,
  ViewId,
  attractDrift,
  channel,
  diskMode,
  kiosk,
  playing,
  resetView,
  sheet,
  view,
} from "../state/useAppState";
import { numberParam } from "../urlParams";

/** The 3D leg: long enough for the 48 h field-line loop to read as motion. */
const PHASE_3D_MS = 45_000;

/** Each channel in the disk interlude (3 x 7 s ≈ the 20 s the interlude wants). */
const PHASE_DISK_MS = 7_000;

/** The disk interlude's channels, in the order shown: hot loops → corona. */
const ATTRACT_CHANNELS: ProductId[] = ["0304", "0171", "0193"];

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
  view: ViewId;
  channel: ProductId;
  diskMode: DiskMode;
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
 * first channel pick. Paired with the sync-flush watchers in trackUsage(),
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

/** The 3D leg: re-home, loop the field lines, start the slow orbit drift. */
function begin3dPhase(): void {
  selfWrite(() => {
    // resetView() re-homes the camera (via resetToken) and parks the playhead —
    // and clears `playing` on the way, so the play flag has to come after it.
    resetView();
    view.value = "3d";
    playing.value = true;
    attractDrift.value = true;
  });
}

/** The disk leg: one big, bright still. */
function beginDiskPhase(id: ProductId): void {
  selfWrite(() => {
    attractDrift.value = false;
    playing.value = false;
    view.value = "disk";
    // Never the movie: the 48 h files run to 50 MB (footgun 7) and DiskMovie
    // autoplays in kiosk mode, so an unattended loop would download all day.
    diskMode.value = "still";
    channel.value = id;
  });
}

/** One step of the loop: the 3D leg, then one channel per disk leg, forever. */
function nextPhase(): void {
  if (!attractActive.value) { return; }
  const step = phase % (ATTRACT_CHANNELS.length + 1);
  phase += 1;
  if (step === 0) {
    begin3dPhase();
    timer = window.setTimeout(nextPhase, PHASE_3D_MS);
  } else {
    beginDiskPhase(ATTRACT_CHANNELS[step - 1]);
    timer = window.setTimeout(nextPhase, PHASE_DISK_MS);
  }
}

function enterAttract(): void {
  // The watcher's throttled pointermove handler clears its own idle flag
  // without calling onActive, so a hovering hand can fire onIdle a second time
  // mid-loop; `pending` covers the settle window the same way.
  if (!kiosk.value || attractActive.value || pending) { return; }

  // Close the guest's session first: everything after this line is the app
  // talking to itself, and none of it is usage data.
  statsSessionEnd(watcher?.lastActivityTs() ?? Date.now());

  saved = { view: view.value, channel: channel.value, diskMode: diskMode.value };

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
      view.value = saved.view;
      channel.value = saved.channel;
      diskMode.value = saved.diskMode;
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
 * The two things worth counting beyond taps: switching into 3D, and picking a
 * channel. `flush: "sync"` is load-bearing — the callback has to run inside
 * the write so `writing` still reads true for the loop's own writes; a queued
 * (default pre-flush) callback would see it back down and count them.
 * statsTrack's own "no open session" rule is the second line of defence.
 *
 * Note the rollup field names are exo-era (`mode3d`, `planets`): kioskStats.ts
 * is shared verbatim across data stories, so a channel id lands in `planets`.
 */
function trackUsage(): () => void {
  const stopView = watch(view, (now, before) => {
    if (writing || attractActive.value) { return; }
    if (now === "3d" && before !== "3d") { statsTrack("mode3d"); }
  }, { flush: "sync" });
  const stopChannel = watch(channel, (id) => {
    if (writing || attractActive.value) { return; }
    statsTrack("select", id);
  }, { flush: "sync" });
  return () => { stopView(); stopChannel(); };
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
