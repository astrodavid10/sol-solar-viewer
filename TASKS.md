# Sol — work ledger

**What this is.** A task-shaped view of the work, so a fresh session (human or Claude) can
pick up at an exact point. `HANDOFF.md` is the *session* chronology and stays the place for
"what changed and why"; this file answers "what is in flight and what is next".

**Rules.**

- Tasks are worked **in order**, one at a time.
- Exactly **one** row may be `IN PROGRESS`.
- A row becomes `DONE` only when its *Definition of done* is met **and** verified — not when
  the code is written.
- `BLOCKED` rows must name what unblocks them.
- Every task ends with: change committed → row updated → any new footgun written into
  `CLAUDE.md` (footguns never live here).
- **Record the hash in a FOLLOW-UP commit, never by amending.** Amending changes the hash the
  row just recorded, and you will do it twice before noticing.

**Last updated:** 2026-08-30 (twelfth session)

---

## Status

Rows are listed in **execution order**. IDs are stable names, not positions — T11/T12 sit
where they do because they are live guest-facing defects reported by a real reviewer, which
the plan says outrank documentation work.

| # | Task | Status | Commit | Note |
|---|------|--------|--------|------|
| T0 | Stand up this ledger | DONE | `3108484` | 18 rows incl. Alex's review |
| T1 | Republish PFSS from the workstation | DONE | `4ee53fc`+ | **6th time** 2026-08-30: 18.2 h -> 0; runbook now `PFSS-UPDATE.md` |
| T2 | Land the GONG relay (Option D, workstation mirror) | CODE LANDED | `8650fee`+ | inert until the env vars are set; go-live steps remain |
| T3 | Honest clock when PFSS is stale (one playhead, union of windows) | TODO | — | app half of T1/T2 |
| T11 | Timeline marks: a key, and targets you can hit | TODO | — | **AF** — 8 px targets, no legend |
| T12 | Explainer copy pass | TODO | — | **AF** — aurora copy is wrong, not just unclear |
| T4 | Reconcile CLAUDE.md / HANDOFF.md with the shipped tree | TODO | — | footgun 40 is wrong |
| T5 | Wire existing checks into CI | TODO | — | `build.yml` has never run |
| T6 | First real app tests | TODO | — | tripwire for footguns 19/47 |
| T13 | Tap a live value to open its explainer | TODO | — | **AF** |
| T16 | Earth on the textured side (verify, then frame) | TODO | — | **AF** — data proven correct, app path unverified |
| T15 | Zoom out to Earth's orbit; our own planet orbits, bold + labelled | TODO | — | **AF** + HANDOFF §8.4(f) |
| T14 | Press-and-hold fine scrub on the timeline | TODO | — | **AF** — new gesture |
| T7 | Accessibility pass (`prefers-reduced-motion`, zoom, focus) | TODO | — | |
| T8 | Phone verification | BLOCKED | — | needs the Chrome extension connected + a handset |
| T9 | Decide the eruption layer | TODO | — | `ERUPTIONS_ENABLED = false` on `main` |
| T10 | Dead-code cleanup in `sdoCatalog.ts` | TODO | — | monolith splits deferred, see below |
| T17 | Zoom out to the heliosphere, with the Voyagers | TODO | — | **AF** — largest new feature; needs scoping |
| T18 | A vertical reel of the 72 h field | DONE | — | `scripts/render_reel.py`; asked for outside the plan |
| T19 | Near-side detail maps at full SDO resolution | IN PROGRESS | `8650fee`+ | pipeline DONE; app LOD + cold fill next |

**AF** = from Alex's review, 2026-08-24 (see "Alex's review" at the foot of this file for the
raw items and how each was mapped).

**Deferred, deliberately** — recorded so a later session does not re-find the seams:
splitting `src/components/SolarView3D.vue` (2,764 lines: stage lifecycle · layer construction ·
projection + markers · card content) and `pipeline/cli.py` (1,475 lines: argparse · per-stage
orchestration · failure policy). Behavior-preserving, one seam per commit, browser-verified
between each. Not in this round.

---

## Task detail

### T0 — Stand up this ledger

Create `TASKS.md`, seed it from the approved plan, point `HANDOFF.md` at it.

**Definition of done:** committed, and `HANDOFF.md` links here from the top.

---

### T1 — Republish PFSS from this workstation

**Why.** Live `data/index.json` reports `pfss` stale at 26 h with "0 freshly traced frame(s)
of 19 slot(s)"; `pfss/manifest.json`'s newest frame is `2026-08-24T12:14Z`, ~30 h old. GONG
answers *this* workstation in 0.42 s (probed 2026-08-25) while timing out from every GitHub
runner (footgun 33).

**Follow [`PFSS-UPDATE.md`](PFSS-UPDATE.md), not the recipe below.** That file is the current
runbook — the same procedure, brought up to date (footgun 49's publish-then-wait ordering, the
`--with-texture --with-hires` flags CI actually passes, a fourth process trap), and written to
be followed top to bottom by a fresh session on a small model. What follows here is the
historical recipe plus the record of each run, kept because the *reasoning* behind each step is
in the run notes.

**Recipe** — the order matters:

1. Seed `public/data` from the live `gh-pages` tree **first** (footgun 31). Skipping this lets
   a wholesale republish clobber the fresher non-PFSS products CI built in the meantime.
2. `conda run -n sdo python -u -m pipeline all --out public\data -v` — `-u` so a killed run
   still leaves a log (footgun 41). One run per `--out` at a time (footgun 35).
   **Two process traps, both hit on 2026-08-25 and both producing footgun 41's exact
   zero-byte-log symptom from causes footgun 41 does not name:**
   - **`python -u` does nothing through `conda run`.** conda captures the child's stdout and
     flushes only at exit, so a long run logs *nothing* while plainly working (752 MB RSS,
     0-byte log). For any backgrounded run call the env's interpreter directly —
     `"$USERPROFILE/anaconda3/envs/sdo/python.exe" -u -m pipeline …` — which CLAUDE.md
     already lists as a fallback for unrelated reasons.
   - **Do not `nohup … &` inside a backgrounded shell.** The harness reaps the wrapper's
     process group, so the detached run dies a couple of minutes in with an empty output dir
     and an empty log. Run the pipeline *as* the background command instead.
3. `python -m pipeline validate --root public\data --strict` → expect 0 failed / 0 warnings.
4. `scripts/publish_gh_pages.sh` (auth via `gh auth token`; it normally runs inside CI with
   `GITHUB_TOKEN`/`GITHUB_SHA` already set).
5. Kick the Pages build: `gh api -X POST repos/astrodavid10/sol-solar-viewer/pages/builds`
   (footgun 34).
6. Re-fetch the live `index.json` and confirm.

**Definition of done:** live `index.json` reports `pfss` ok, age ≈ 0, 19/19 slots.

**DONE 2026-08-25 20:54Z** — published as `gh-pages` commit `cb0ba1a`.

- GONG answered every request from here: **19/19 slots had a magnetogram within 3 h**, so this
  is a fully fresh window, not a partial fill. Live newest frame `2026-08-25T18:44Z`,
  **2.2 h old** (which is simply what a GONG synoptic magnetogram is — the scrubber's copy
  already says so) against **30.1 h** before.
- All six products `ok`, `last_attempt_status: ok`. Both `validate --root public/data --strict`
  and `validate --url …/data/ --strict` report **0 failed / 0 warnings**.
- **Ran `all` WITHOUT `--with-texture`, deliberately.** CI's texture product was 0.2 h old and
  hires-complete; re-running locally would either cost ~15 min for identical pictures or,
  without `--with-hires`, drop the `high_res` blocks the app has used by default since
  `e7095c2`. Verified safe by reading the code first: `_prune_orphan_textures` returns early
  when `results` carries no texture entry (`cli.py:1061-1063`), and `build_index` falls back to
  `_existing_product` (`:949-951`). Published index says texture `ok … not regenerated this
  run`; file count held at 132.
- Seeded `public/data` from `origin/gh-pages` first (footgun 31) — confirmed necessary rather
  than assumed: gh-pages held **132** files against the local tree's **117**, i.e. 15 texture
  frames CI had built since the last local run, which an unseeded `rsync --delete` publish
  would have reverted.
- **A hand-publish is NOT in the `gh-pages-publish` concurrency group** that serializes
  `data.yml` against `app-deploy.yml`. A scheduled `data` run was in flight when this started
  with `Deploy app` queued behind it; publishing into that would have raced two force-pushes
  to the same orphan branch. Wait for both by hand, and check again immediately before
  pushing.

**Note for T2:** the next scheduled CI run will seed from this tree, fail to reach GONG, and
mark `pfss` stale again while preserving these frames. Designed behavior — and exactly the
recurring chore T2 exists to end.

**It recurred, on schedule.** Done again **2026-08-26 07:07Z** (`gh-pages` commit `94fbdfb`),
this time as a full `all` run rather than PFSS alone: live `index.json` had gone back to
`degraded` with `pfss` stale at **8.0 h**, and came out `ok` with all six products `ok` and
19/19 slots freshly traced (newest magnetogram `2026-08-26T04:04Z`, 2.9 h old). Both
`validate --root` and `validate --url` reported 0 failed / 0 warnings. Same two cautions as
above still applied and were followed: seed from `origin/gh-pages` first (the seed differed
from the local tree by 10 files), and check for an in-flight CI run before pushing.

**And again, on schedule.** Done a fourth time **2026-08-27 15:50Z** (`gh-pages` commit
`e6e22d9`): live `index.json` was `degraded` with `pfss` **stale at 18.3 h / "0 freshly traced
frame(s) of 19 slot(s)"**, and came out `ok` with all six products `ok`. GONG answered this
workstation for every request -- 19/19 slots had a magnetogram within 3 h, so a fully fresh
window again; newest frame 3.5 h old, 1362 seed lines, 19 frames / 2.24 MB, 255 s of tracing.
`validate --root` and `validate --url` both reported 0 failed / 0 warnings.

Ran `all` **without** `--with-texture`, the same reasoning as the first publish and re-checked
rather than assumed: CI's texture was 6.3 h old and hires-complete on all five layers, and a
local run without `--with-hires` would have dropped those `high_res` blocks. The published
index says texture `ok ... not regenerated this run`; file count held at 142. Seeding from
`origin/gh-pages` was again *necessary*, not precautionary: the published tree carried 25
texture history frames (5 channels x 5 slots) the local tree lacked, and the local tree held 25
that had scrolled out of the window -- an unseeded `rsync --delete` publish would have reverted
CI's work.

**Two notes for the next time.** (a) Footgun 49 held: the force-push auto-triggered a Pages
build for the right commit, which went `built` in 32 s, so **no explicit `POST /pages/builds`
was made or needed** -- the live tree was serving new data within 15 s of the build starting.
(b) A **`Deploy app` run had been stuck `queued` for 24 h 23 m** (commit `90cd733`, already
superseded by a later deploy that succeeded). It is an *app* publish, which preserves `data/`,
so it could not clobber the data content; the only exposure is an interleaved checkout, and
GitHub drops queued runs at 24 h. Checking `gh run list --status queued` as well as
`--status in_progress` is what surfaced it -- the plain `gh run list` top-5 did not.

**And a fifth time.** Done **2026-08-29 17:39Z** (`gh-pages` commit `4e80021`): live
`index.json` was `degraded` with `pfss` **stale at 46.1 h** and the same
`0 freshly traced frame(s) of 19 slot(s)` note — the longest gap yet, because the recurrence
spans two sessions rather than one. Came out `ok` with all six products `ok`.

GONG answered this workstation on every request (0.61 s to the listing root): **19/19 slots had
a magnetogram within 3 h**, a fully fresh window, `reused: 0`. Newest frame
`2026-08-29T16:14Z` — **1.3 h old** against 46.1. Seed set `590cb2a7`, 1351 lines
(1152 background + 199 region), 1324-1332 of them valid per frame; 19 frames / 2.25 MB;
**39.0 s** of solve+trace (1.70-2.70 s per frame). Both `validate --root` and `validate --url`
reported 0 failed / 0 warnings.

Same two cautions, both followed. Seeding was again *necessary*: the local tree held **65**
files the published one lacked (texture frames scrolled out of the window) and the published
tree held **45** the local lacked (CI's newer frames), so an unseeded `rsync --delete` publish
would have reverted CI's work in both directions. Nothing was in flight or queued at publish
time (`--status in_progress` and `--status queued` both empty, re-checked immediately before
the push). Texture again NOT regenerated — CI's copy was 3.7 h old and hires-complete on all
five layers, including 0304; published index says texture `ok`, file count held at **122**.

Footgun 49 held for the second time running: the force-push auto-triggered a Pages build
against the correct commit (`4e80021`), `built` in ~25 s, **no explicit `POST /pages/builds`
made or needed**.

**One new observation.** The window's low edge is now the binding constraint on how long a gap
can be tolerated, not the staleness threshold: at 46.1 h the served frames still spanned a
valid 72 h window, so the app had a complete scrubber showing a two-day-old Sun. That is the
failure mode T2 is really about — not an outage the guest can see, but a plausible one they
cannot.

**That is five hand-publishes in five sessions**, which is the argument for T2 rather than a
note about it. The cost is ~20 minutes of a session each time, and the failure mode when a
session *doesn't* do it is silent: the site keeps serving correct-looking field lines that are
a day old.

**A sixth time — and the recurrence finally cost CI a run.** Done **2026-08-30 11:59Z**
(`gh-pages` commit `98536eb`). Two things were stale at once, which is new:

- `pfss` had not been rebuilt since the fifth republish, so the served manifest was
  **18.2 h** old with the usual `0 freshly traced frame(s) of 19 slot(s)`.
- **The whole index was 13.2 h old**, because the 05:12Z scheduled `data` run *failed* — the
  first CI failure of the project. It died at `Validate` on
  `FAIL ar_index within regions.json bounds -- range [-1,5] vs 5 regions`, and that is a
  **stale-PFSS symptom, not an independent bug**: the frozen seed set was built on a day when
  NOAA's SRS listed six regions, CI kept regenerating `regions.json` down to five, and the
  topology's `ar_index` then pointed one past the end. Since `Validate` runs *before* `Publish`,
  every product CI built that morning was discarded — so a stale PFSS product had started
  blocking the five products CI *can* build. It cleared exactly as expected once the seed set
  was rebuilt against today's five regions (`id=7f48181f`, 1329 lines = 1152 background + 177
  region). **This is a new coupling worth remembering: PFSS staleness is not indefinitely
  survivable — it eventually takes the rest of the tree down with it.**

GONG answered this workstation on every request: **19/19 slots had a magnetogram within 3 h**,
`reused: 0` on all 19, so a fully fresh window. 19 frames / 1329 lines / 19,090 verts /
2.14 MB, 258.1 s of solve+trace, dequant error 3.97e-05 R_sun. Newest frame's magnetogram
`2026-08-30T08:14Z` — 3.6 h old at run time, which is the **4 h slot grid plus GONG's own
latency**, not staleness (the 08:00Z slot is the newest one at or before an 11:47Z run).

**Texture WAS regenerated this time**, unlike runs 1, 4 and 5 — CI's copy was 13.2 h old rather
than a few hours, so the reasoning that protected it before did not apply. Ran with
`--with-texture --with-hires`, matching what `data.yml` actually passes: all five layers rebuilt
with `high_res`, 95 history slots (75 reused, 15 built, 0 unavailable, 0 deferred by the cap),
27.35 MB, 424.4 s. 0304 again produced no hi-res map — footgun 40's guard working, not a
failure. 15 orphan frames pruned; published file count held at **142**.

Seeding was again *necessary*: the published tree held **30** files the local one lacked and the
local held **10** that had scrolled out of the window. Nothing was in flight or queued
(`--status in_progress` and `--status queued` both empty, re-checked immediately before the
push), and the push went out at 11:59:51Z, eight minutes ahead of the 12:07Z cron slot. Footgun
49 held for the third time running: the force-push auto-triggered a Pages build against the
correct commit, `built` in 22 s, **no explicit `POST /pages/builds` made or needed**. Both
`validate --root` and `validate --url` reported 0 failed / 0 warnings.

**The chore is now written down.** Six hand-publishes in six sessions was enough of an argument:
the whole procedure — preconditions, the seed, the flags and why each one is there, the four
process traps, the publish, the Pages wait, and what to record — is now
**[`PFSS-UPDATE.md`](PFSS-UPDATE.md)**, written so a fresh session on a small model can run it
top to bottom without reading the pipeline source. It documents one trap this session hit that
footgun 41 does not name: **if the log file's parent directory does not exist, the redirect
fails, the pipeline never starts, and the background wrapper still reports a completed task** —
footgun 41's zero-byte-log symptom with no run behind it at all. That does not make T2 less
necessary; it makes the interim cheaper.

---

### T2 — Land the GONG relay: Option D, the workstation mirror

**Decided** this session, over Option A (Cloudflare Worker) and over shelving it.

**What is already written and uncommitted** (154 insertions, sitting in the tree since
session five, additive and inert with the env vars unset):

- `scripts/gong_mirror.py` (599 lines) — scrapes GONG from a machine that can reach it and
  republishes to a `gong-cache` branch, manufacturing an `index.html` per day directory
  because `raw.githubusercontent.com` serves files, never directory listings.
- `scripts/gong-mirror-task.ps1` (114 lines) — the Windows Scheduled Task wrapper.
- `SOL_GONG_PROXY_INDEX` seam in `pipeline/config.py`, `pipeline/sources/gong.py` (`_relay`),
  `pipeline/cli.py` (`probe-sources` output) and `.github/workflows/data.yml`.

**The code is now COMMITTED, and not on purpose.** A `git add -A pipeline` in the ninth session
swept the relay seam into `8650fee` (whose message does not mention it), and an earlier
`git add .github/workflows/data.yml` took the workflow half into `90cd733`. Rather than unpick
it, the rest was committed alongside and this row updated: the code is landed and **inert** --
`GONG_PROXY_BASE` and `GONG_PROXY_INDEX` read from env vars that are unset everywhere, so every
URL stays canonical and nothing behaves differently. Treat the diff as unreviewed.

**Go-live steps that REMAIN:** review the landed diff → `--dry-run` the mirror → create the
`gong-cache` branch → install the Scheduled Task → set `SOL_GONG_PROXY_BASE` and
`SOL_GONG_PROXY_INDEX` as repository secrets → confirm from a real scheduled run.

**Do not** set `GONG_BASE` to the relay — the rewrite is request-time only, because
`gong_file_key` derives the traced-frame cache key from the URL and because the manifest
cites that URL as provenance (footgun 37).

**Definition of done:** a scheduled `data.yml` run traces ≥ `MIN_FRAMES_TO_PUBLISH` frames
with no human in the loop, and `docs/GONG-RELAY.md` records the live configuration.

**Known weakness, to be written down rather than discovered:** a sleeping or offline
workstation stops the mirror. The pipeline then degrades exactly as it does today — stale,
not deleted (footgun 31).

---

### T3 — Make the app honest when PFSS is stale: one playhead, union of windows

**Decided** this session: keep exactly one shared playhead, widen its range.

**The defect.** `sceneUnix` (`src/state/useAppState.ts:196`) interpolates **only**
`frameTimes`, which `SolarView3D` fills from `pfss/manifest.json`'s `mag_unix` column. Every
time-aligned layer follows it. With PFSS ending ~30 h in the past:

- `sunSurface.setFrameTime()` can never reach the surface's newest slot, so the **freshest
  published sphere texture (2 h old) is unreachable**.
- `updateOffLimb()` (`src/components/SolarView3D.vue:1566`) gates on
  `surface.atNewestFrame()`, so the **off-limb corona billboard never draws at all**.
- AR markers and the sunspot chip show the stale day.
- `TimeScrubber.vue:290` prints **"now"** at the right-hand end while `:299` prints
  **"Magnetic field data from 30 hours ago"** ~18 px above it.

**(a) Copy.** The newest frame must stop reading "now" when the product under it is stale.

**(b) Range.** Derive the playhead's range from the newest frame across **all** published
products, not from PFSS alone. Field lines hold their last traced frame past their own window
end, and say so.

**Consequence to handle deliberately:** `frameT` is a *fractional index* into `frameTimes`, so
extending the range changes what an index means. Check `useDeepLink` and `parkAtNewest()`, and
make sure a QR printed before this change still lands somewhere sensible.

**Definition of done:** against a deliberately stale `pfss/manifest.json`, the scrubber's copy
is self-consistent, the newest sphere texture is reachable, and `surface.atNewestFrame()` can
become true again.

---

### T4 — Reconcile the docs with the shipped tree

Three footgun-level statements are now false, which is the one failure mode that makes the
whole footgun list less trustworthy:

- **Footgun 40: "0304 is EXCLUDED" and "Never enable this in CI"** — both false. Live
  `texture.json` carries `high_res` for all five channels including 0304 (2.12 MB,
  8192x4096), and `.github/workflows/data.yml:148` passes `--with-hires` every scheduled run
  (~12 min of a 45 min budget). Commits `01889e6` and `5b7c09f` did this.
- **HANDOFF §3z: "The UI toggle is NOT built yet"** — `e7095c2` removed the toggle and made
  4K the *default* (`?hires=0` opts out), `src/state/useAppState.ts:118`.
- **HANDOFF §1: "Sphere textures — one frame each"** — live manifest is 19 frames/channel.
- **HANDOFF §1 "22 commits on `feature/unified-sphere-view`"** and **risk #2 "GitHub Pages is
  not enabled"** — both stale, and both contradict HANDOFF's own header.
- **Footgun 36's "5 newest + 5 demoted rebuilds" steady state** — predates the window being
  full; re-measure from a current CI log.
- **`CLAUDE.md`'s own opening paragraph** still describes `live SDO imagery ("Sun Now" disk
  view)` — the disk view was deleted in `a270e5a`; there is one unified sphere view.

**Definition of done:** no statement in `CLAUDE.md`, or in `HANDOFF.md` §1-§2, contradicts the
shipped tree.

---

### T5 — Wire the checks that already exist into CI

`scripts/check_label_layout.mjs` and `scripts/check_pipeline_names.py` are the only automated
checks in the project and **no workflow and no `package.json` script invokes either**.

`.github/workflows/build.yml` has never run, for two independent reasons: all work lands
directly on `main` so no PR opens it, and its trigger is malformed —

```yaml
on:
  pull_request:
    branches:
      main        # a scalar, not a YAML sequence; GitHub expects a list
```

**Definition of done:** a push to `main` runs lint + typecheck + build + both checks, green,
and each check is one `yarn` command locally.

---

### T6 — First real app tests

Zero coverage today. The pure, high-consequence modules, in priority order:

- `src/three/worldFrame.ts` — assert `det(ECLIPTIC_TO_WWT) = -1` and the `(x,z,y)` mapping.
  This is the **tripwire for footgun 47 being undone**, which cost four sessions.
- `src/three/winding.ts` — `CAMERA_REVERSES_WINDING` false / `SOLID_SIDE` FrontSide
  (footgun 19).
- `src/three/project.ts`, `src/data/solarFrames.ts`.
- `src/data/swpc.ts`'s `pickNumber` — it shipped a permanently-blank stat chip once.
- `src/data/pfss.ts` / `src/data/events.ts` manifest parsing, against real published JSON.

**Definition of done:** the suite runs in T5's workflow and fails if footgun 19's or
footgun 47's convention is reverted.

---

### T7 — Accessibility pass

- **`prefers-reduced-motion` is one media query**, `src/sol.vue:484`. Not honored by field-line
  playback, the kiosk attract drift, the CME replay, the loading spinner, any `.fade-*`
  transition, or `TransitionExpand`. One guard, not per-component queries.
- **`user-scalable=no, maximum-scale=1`** (`public/index.html:7`) blocks browser text zoom
  (WCAG 1.4.4). Deliberate — the app owns pinch (footgun 38) — but unrecorded, and there is
  no in-app text-size path. Decide and write it down.
- Audit `:focus-visible` coverage on the stage controls.

**Definition of done:** with reduced motion on, nothing animates unbidden and the app is still
fully usable.

---

### T8 — Phone verification  *(BLOCKED)*

**Blocked on:** the Chrome extension being connected (it was not, this session) and a real
handset. This is the project's largest standing verification gap.

- DPR > 1 — footgun 16's regression signature (overlay offset into the bottom-left quadrant)
  appears *only* there.
- **The 8192x4096 sphere map is now the DEFAULT and has never been on a phone.** ~134 MB
  decoded. `hasHighRes()` gates on `MAX_TEXTURE_SIZE >= 8192`, which many phones *report*
  while still struggling to allocate it. `?hires=0` is the immediate mitigation; flipping the
  default is the fix. **The single riskiest untested default in the app.**
- Pinch + twist, and `TWIST_SIGN` (explicitly unverified on a touch device, footgun 38).
- A first finger on a label chip still taps it; layer-popover flick scrolling (footgun 45).
- Kiosk `?kiosk=1` + attract loop + QR flow — never run.
- Lighthouse mobile.

**Definition of done:** each line moves from HANDOFF §4's "not seen running" half to the
"proven" half, or becomes a filed defect row here.

---

### T9 — Decide the eruption layer

`ERUPTIONS_ENABLED = false` (`src/state/useAppState.ts:53`); the wired version is preserved on
`feature/cme-3d`, one line different. It is tuned for the replay framing (~21.5 R_sun) and
overexposes at the 2.8 R_sun home framing.

Re-sweep the alpha and point-size constants **at the screen, tab foregrounded** (footgun
46(d)), then pick one: re-enable, restrict to the replay only, or drop it and delete the
branch.

**Definition of done:** the flag carries a decision on `main`, not a deferral.

---

### T10 — Dead-code cleanup in `sdoCatalog.ts`

`src/data/sdoCatalog.ts` is 347 lines with exactly **one** live consumer: `product()`,
imported by `src/components/LayerPanel.vue:72`. `stillUrl`, `posterUrl`, `latestMovieUrl`,
`dailyMovieUrl`, `diskScaleFor`, `usesPfssVariant`, `RES_LADDER`, `PFSS_RESOLUTIONS`,
`DAILY_MOVIE_MB`, `hasAnyMovie`, `resLabel`, `isDiskRes`, `utcDaysAgo` and the movie-size
tables are all left over from the disk view deleted in `a270e5a`.

**This is a move, not a delete.** Those comments are where footgun 7's measured movie sizes
and footgun 21's limb fractions live. Migrate the measurements into `CLAUDE.md` **first**,
then trim the file.

Also still true and worth a line: `orbitSampleVerticesAU()` (`src/data/planets.ts:72`) has
zero callers — HANDOFF §8.4(f)'s own planet orbits remain undone.

**Definition of done:** `yarn build` clean, a grep proves nothing else resolves into the
removed exports, and no measurement was lost.

---

### T11 — Timeline marks: a key, and targets you can actually hit

> *Alex:* "We need a key explaining what the symbols mean in the timeline, also it's hard to
> select the symbols on the timeline. Idk if they are even clickable."

Both halves confirmed in the code, and the second one is a genuine defect:

- **Hit target is 8x8 px.** `.ts-event` in `src/components/TimeScrubber.vue:458-465` — 8x8 for
  C-class, 10x10 for X, 9x9 for CME, inside a `.ts-events` band 12 px tall. Against a 44 px
  minimum touch target that is roughly a fifth of the area a thumb needs. **The rest of this
  app already knows this** — the play button next to it is 44x44 (`:396`) and the layer-panel
  segments are 44 px by explicit decision (HANDOFF §8.4).
- **They ARE clickable** — real `<button>`s with `@click="onMark(mark)"` (`:37-46`) emitting
  `pick-event`. Nothing on screen says so. The only affordance is `cursor: pointer` (invisible
  on touch) and a `title` attribute — and HANDOFF §8.2 already flagged `title`-only meaning as
  "inaccessible on touch" for the stat-chip freshness dot. Same mistake, second site.
- **There is no key anywhere.** Shape carries the type (diamond = flare, circle = CME) and
  color carries severity (amber C / orange M / red X). HANDOFF §8.2 rightly praises that as
  meaning-not-by-color-alone — but the guest is never told what either axis means.

Fix directions: separate the *visual* mark from its *hit area* (a transparent >= 44 px wide
button centered on an 8 px painted mark — the standard split, and it costs no layout); give
the marks a resting affordance; and add a compact key. The key wants to be discoverable
without spending permanent vertical space on a phone — a tap on the mark row, or a line in the
info panel, rather than a legend strip.

**Watch for:** overlapping hit areas when marks cluster. `thinEvents`/`thinFlareEvents`
(`SolarView3D.vue:779,791`) already thin the marks, but 44 px targets overlap far sooner than
8 px ones do — decide what a tap between two close marks selects before shipping it.

**Definition of done:** every mark is tappable first time at 390 px width with a real finger,
the key is reachable, and no two hit areas silently steal each other's taps.

---

### T12 — Explainer copy pass

Four items, one pass over the explainer/info copy. The aurora one is a **factual** fix, not a
clarity one.

> *Alex:* "the Aurora text box should say something like 'the Aurora (northern and southern
> lights) heads towards the equator', not 'the northern lights heads south'."

Correct, and worth stating plainly: a geomagnetic storm pushes the auroral **oval** equatorward
in *both* hemispheres. The current copy describes the northern half only and says "south",
which is actively wrong for a southern-hemisphere reader and imprecise for everyone.

> *Alex:* "'NOAA publishes one count per day… scrub rather than sliding' in the sunspots info
> box is a confusing sentence, and may not be necessary."

He is right, and it is worth understanding *why* it reads badly: the sentence explains an
implementation consequence (the number steps at UT midnight because the SRS is a daily
product — footgun 30) to a guest who never asked. The guest-facing fact is just "NOAA counts
these once a day". Keep the cadence honest, drop the mechanism.

> *Alex:* "Maybe explains the difference between a flare and a CME in the flare text box."
> *Alex:* "Need to explain the eruptions vs CME."

One flare/CME explanation, written once and reachable from both the flare chip and a CME
event card. The distinction the code already makes is nearly the copy already —
`TimeScrubber.vue:493`: "A flare is a flash on the Sun; a CME is something leaving it."

**Open question for the user:** "eruptions vs CME" is ambiguous, because `ERUPTIONS_ENABLED`
is `false` on `main` and the "Eruptions" layer row is filtered out of the live build (verified
on the live site, HANDOFF §3zzzz). So either Alex saw an older deploy, or he means the
vocabulary generally. **Ask before writing copy for a control that does not exist** — and note
this feeds T9's naming decision: if the layer comes back, "Eruptions" vs "CMEs" is a naming
choice, not just an explanation.

**Definition of done:** no explainer sentence describes an implementation detail; the aurora
copy is hemisphere-correct; flare vs CME is explained once and linked from both places.

---

### T13 — Tap a live value to open its explainer

> *Alex:* "For 'a C' what if you had a link that then opened up the explanation tab/bubble
> explaining what that is."

The flare chip's headline is the class (`C1.4` / `M2.3` / `X5.0` — session four made the class
the headline precisely because "small flare" could not distinguish C1.0 from C9.9). The class
is the most jargon-dense string in the app and currently explains itself nowhere a guest will
look.

Generalize rather than special-case it: any live value that is a term of art (flare class, Kp,
km/s, sunspot number) gets a consistent, visible affordance that opens the existing explainer.
Depends on T12 having written the content.

**Definition of done:** tapping the flare class opens its explanation on phone and desktop,
the affordance is visible without hover, and the same pattern is reused by at least one other
chip rather than hand-built.

---

### T14 — Press-and-hold fine scrub on the timeline

> *Alex:* "it'd be a cool feature if I tapped and held the timeline for about 1.5 seconds it
> then rescales the timeline to about a tenth the scale then I could fine adjust the timeline
> scale and more easily [get] to the event I want to go to."

A magnifier mode: long-press, the track re-scales to ~1/10 of the window around the playhead,
drag to fine-adjust, release to return. Real value on a 72 h window compressed into ~300 px,
where one pixel is ~15 minutes.

**Read `src/wwt/gestures.ts` first.** That module took touch input away from the WWT engine for
four compounding reasons (footgun 38) and it listens on the **stage root in the capture phase**.
A long-press on the scrubber must not be stolen by it and must not start a camera orbit —
`isControl` exempts `button/a/input/select/textarea/[role=button]` and
`data-camera-passthrough="false"` (footgun 45). The track is an `<input type="range">`, so it is
already exempt; the surrounding chrome is not.

**Also:** decide the interaction on *desktop* (there is no long-press there), and make sure the
1.5 s hold does not fight the existing `@pointerdown="onGrab"` / `onRelease` drag path
(`TimeScrubber.vue:59-61`), which the field-line renderer uses to suspend playback.

**Definition of done:** long-press magnifies, drag fine-adjusts, release restores, the camera
never moves during it, and a normal drag is unchanged.

---

### T15 — Zoom out to Earth's orbit; our own planet orbits, bold and labelled

> *Alex:* "I'd still like to be able to zoom out up until the orbit of earth to get a sense of
> scale for the orbiter's location… if you have the planet orbits in a different bold with
> labels, then I don't think people will get lost."
> *Alex:* "Add labels for the planets."

Three things, one workstream, and **HANDOFF §8.4(f) already specified two of them**.

**(a) The zoom range.** `MAX_ZOOM = 2.5` (`src/wwt/sunStage.ts:87`), and footgun 14 gives
`distance_AU = 4*zoom/9`, so the camera currently stops at **1.111 AU**. Earth's orbit is
1 AU — so you can *reach* it but not *see* it: at 1.11 AU with WWT's fixed pi/4 vertical FOV
the view spans only ~0.92 AU, less than half the orbit's diameter. Framing the whole orbit
needs ~2.5-3 AU, i.e. `MAX_ZOOM` around 5.6-6.75. Raising it also means checking
`setSolarSystemMinZoom/MaxZoom` (`:753-754`) and the pinch clamp (`:725`).

**(b) Our own planet orbits.** WWT's orbits are `Colors.get_white()` in engine-internal
per-`Orbit` state and are **not reachable through the Settings API** — HANDOFF §8.2 proved
this. The only route is `solarSystemOrbits = false` plus drawing our own.
`orbitSampleVerticesAU()` (`src/data/planets.ts:72`) returns exactly the vertex list
`LineGeometry.setPositions()` wants and **still has zero callers**. §8.4(f) has the settled
numbers (casing 3.0 px `#05010F` @ 0.45 + core 1.4 px violet `#7B7EE0` @ 0.42) and the caution
that violet must stay clear of STEREO-A's `#c77dff`.

Two warnings that already cost this project a session each: `LineMaterial` needs
`side: FLAT_SIDE` or WWT's winding culls every quad (footgun 19), and `resolution` must come
from `stage.bufferSize()`, never `gl.canvas.width` (footgun 16). The fat-line work for
spacecraft trails already solved both — copy that, do not re-derive it.

**(c) Planet labels.** The label machinery exists and is good: `src/three/project.ts` +
`src/three/labelLayout.ts` de-collide chips and draw leader lines, and `SpacecraftLabel.vue` is
the chip. Planets are more label sources into the same pipeline — but note the de-collision was
fuzz-tested against ~6 chips, and a wide zoom could put 5 planets plus 3 craft plus AR markers
on screen at once. Check the stride budget before assuming it scales.

**Definition of done:** at max zoom-out Earth's whole orbit is on screen and legible, the orbits
are ours and readably thick on a DPR-3 phone, planets are labelled, and the labels still
de-collide with everything else at that zoom.

---

### T16 — Earth on the textured side (verify first, then frame)

> *Alex:* "I would like to see earth on the same side that the texture side is at."

**The published data is already correct — verified numerically this session.** Cross-checked
`texture.json`'s per-frame `sub_earth_carr_lon_deg` against `ephem/spacecraft.json`'s Earth
`carr_lon_deg` at the same instants: they agree to **0.03 deg** over the window. (The newest
slot differs by 0.5 deg because it deliberately carries the freshest available image rather
than one snapped to the grid — expected, §3z.) So Earth's position and the textured hemisphere
describe the same side of the Sun.

**What is NOT verified** is the app's placement of that data into the scene — and there is a
real geometric reason Earth may look wrong that is *not* a bug:

`earthFacingCamera()` puts the camera **on the Sun-Earth line**. So Earth is either directly
behind the camera (near framings) or, once you zoom past 1.01 AU, directly *in front* of it,
projected onto the middle of the Sun. There is no home framing in which Earth appears usefully
"off to the side on the textured hemisphere". Getting the picture Alex describes needs the
wide-zoom framing to orbit off the Sun-Earth line — not a sign fix.

So: **verify before changing anything.** Check against WWT's own `solarSystemPlanets`
rendering, the only independent reference in the scene (footgun 47) — never against our own
layers, which is exactly how the 90-degree bug survived four sessions.
`solDebug.setCamera({distanceAu, latDeg, lngDeg})` makes that a one-call check.

**Definition of done:** either (a) Earth is confirmed coincident with WWT's own Earth and the
remaining work is a *framing* change filed under T15, or (b) a placement bug is found, in which
case it is promoted immediately and gets a footgun.

---

### T17 — Zoom out to the heliosphere, with the Voyagers

> *Alex:* "Maybe we can have the ability to zoom all the way out to see the
> heliopause/heliosphere bringing up the voyager orbits in the process."

The largest new feature on the list, and **it needs scoping before it needs building.** Open
questions, all of which change the cost by an order of magnitude:

- **Range.** The heliopause is ~120 AU. T15 needs ~3 AU. That is a 40x further step, i.e. a
  ~1000x span from the 2.8 R_sun home framing — almost certainly a *staged* zoom with different
  content at each decade, not one continuous range.
- **Whose rendering?** WWT already knows the outer solar system. Drawing our own out there
  duplicates it; letting WWT do it means accepting its unstyleable white (see T15(b)).
- **Voyager ephemerides.** Both have Horizons ids (Voyager 1 = -31, Voyager 2 = -32), so the
  existing `pipeline/ephem/export.py` path likely extends — but a +/-30 day window at 6 h is
  meaningless for a probe 40 years out. The sampling and the window are a different design.
- **Is the heliopause data or decoration?** There is no live observation of its shape. A drawn
  boundary is a model, and this project's whole discipline is that a stylization must be
  labelled as one (footgun 22's `farside`, footgun 29's off-limb billboard, the CCMC
  "prototyping quality" disclaimer). Decide what it *claims* before drawing it.

**Definition of done:** a written scope with those four answered, then a build decision — not an
implementation started from this paragraph.

---

### T18 — A vertical reel of the 72 h field  *(DONE 2026-08-26)*

Asked for directly, outside the plan: a reel-sized animation of the full 72 h magnetic field
with the surface switching Magnetic Map → Visible Sun → Chromosphere → Coronal Loops → Hot
Corona while it plays. `scripts/render_reel.py` renders the published tree to 1080x1920 MP4;
HANDOFF §3zzzzz has the reasoning and the three deliberate departures from the app.

**Why it is not a screen recording**, since that is the obvious question a later session will
ask: WWT's FOV is a fixed π/4 *vertical* (footgun 11), so a portrait crop is ~2.2x too tight;
GL lines are 1 px and aliased; the browser path is blocked on T8; and a recorder cannot be
asked for reproducible frame timings.

**The part worth reusing:** `--check-conventions` re-derives each frame's rotation from
`quat_carr_to_ecl` and checks it against the pipeline's own `mat3_carr_to_ecliptic_j2000`
(8.2e-16). That is the shape of check **T6** wants — external, not internal. Footgun 47 got
four sessions because every internal cross-check agreed with every other one.

**Not committed:** the MP4. `gh-pages` is a forced orphan commit precisely to keep regenerable
binaries out of history; a ~20 MB video on `main` would undo that. Re-run the script.

**If it is rendered again:** it reads only the published contract, so it works against any
`--root`, including a `--url`-fetched tree if one is ever mirrored locally. The constants most
likely to need a re-sweep are the three in the header (glow gain, line gain, line sigma), and
they must be judged at 1080x1920, not on a scaled-down still.

---

### T19 — Near-side detail maps at full SDO resolution  *(IN PROGRESS)*

Asked for directly: the 19 history slots are 2048x1024 while SDO's browse product is 4096x4096,
so the window carries a quarter of the linear detail it could. Full plan lives outside the repo
at `~/.claude/plans/i-am-confused-when-eager-thompson.md`.

**The shape of the answer, decided with the user:** do NOT publish 8192x4096 full-sphere maps
for all 19 slots. Publish the existing 2048x1024 full-sphere map as a BASE plus a 4096x4096
**near-side window** (the observed hemisphere only, ±90° of longitude about that frame's
`sub_earth_carr_lon_deg`). Same 22.76 px/deg on every observed pixel as a full 8K map, half the
GPU (67 MB vs 134), and — the decisive part — **largest dimension 4096, which most phone GPUs
can actually hold, where 8192 cannot.** The far side is synthesized (footgun 22), so a full 8K
map would spend 4096x4096 pixels on fabricated Sun.

**Two prerequisites found and fixed first, both standing on their own:**

- **`2cbfa32` — one broadcast reprojection instead of three.** `reproject_rgb` rebuilt the
  coordinate transform per colour plane; that transform is 87% of the cost. Measured on the real
  production path: 2.41x at 2048x1024, **2.54x at 4096x2048**, and 8192x4096 went 86-117 s (CI)
  to 56.1 s here. **Byte-identical output** — 0 of 25,165,824 uint8 pixels differ, encoded JPEG
  471,803 B both ways.
- **`0ee3a0e` — the polar-cap guard would have killed the texture stage for 13 days a year.**
  It required the B0-lit cap to be >= 50% visible against a hard 0.5, which the real ~0.35° limb
  ring loss breaks for |B0| < 0.4°: 2026-06-04..06-10 and **2026-12-06..12-11**. Default channel,
  so `run_texture` re-raises and the whole stage dies. Replaced by `check_coverage`, which
  compares the reprojected mask against `dist <= 90` — geometry already computed one line
  earlier, correct for a window as well as a full sphere.
  **Correction to that commit message:** it says to check "last December's CI logs". There are
  none — the repo starts 2026-08-23, so June's crossing predates it and December's has not
  happened. **The bug never fired; it was caught before its first opportunity.**

**The PIPELINE HALF IS DONE** (`8650fee`), behind `--with-near-side`, off everywhere including
CI. Every slot can carry a 4096x4096 near-side window beside its 2048x1024 full-sphere frame;
schema is `sol.texture/5`. Verified: the window is pixel-exact against the matching crop of a
full-sphere reprojection (0 of 3,145,728 uint8 pixels differ), header edges land to 0.00e+00 deg
on four dates including both longitude wrap directions, and all six validator negative controls
catch their failure. Measured 31.8 s per slot per channel -> ~50 min cold fill, ~2.75 min/run
steady state. Off-limb went to a **1024/2048/4096 ladder** rather than a single bump, because
4096 turned out to be native (the crop is 4048-4092 px off the 4096 source), and it is live.

**Still to do, in order:**
1. **App**: second sampler on the SDO material (`uNear`, `uNearLon0`, `uNearSpan`), blending
   detail->base across the SAME 75-90 deg band `applyFarSide` already uses. Two traps recorded
   during design: `vMapUv` is the TRANSFORMED uv, so the window CANNOT be swapped in via
   `texture.offset/repeat` without corrupting the far-side dimming maths, and the window needs
   `ClampToEdgeWrapping` where the base map needs `RepeatWrapping`.
2. **App**: zoom-gated LOD (`stage.bufferSize()` + `cameraDistanceAu()`, with hysteresis),
   tier-aware `TEXTURE_BUDGET_BYTES` (one window is 67 MB against a 40 MB total budget today),
   no +/-1 prefetch on the window tier, and progressive refinement while scrubbing.
3. **Cold fill** by hand on the workstation, then publish.
4. Turn `--with-near-side` on in CI.
5. Retire `TEX_HIRES_*`.

**Not started and NOT verified in a browser:** all of the above, plus the `a9f6acd` wiring fix.

**The dead wiring is fixed but UNVERIFIED in a browser** (uncommitted at time of writing): the
8192x4096 maps CI has built every four hours since `01889e6` have never been fetched by any
browser, because `SolarView3D.vue` asked `hasHighRes()` synchronously before the manifest fetch
could resolve. The preference now goes in as a construction option. Needs T8's browser to
confirm, and the extension is still not connected.

---

## Alex's review — raw items, 2026-08-24

Kept verbatim so nothing is lost in the mapping, and so a later reader can check my reading of
each against the source.

| Alex's item | Filed as |
|---|---|
| Key explaining the timeline symbols; hard to select them; unsure they're clickable | **T11** |
| "NOAA publishes one count per day… scrub rather than sliding" is confusing / unnecessary | **T12** |
| A link on "a C" that opens the explanation | **T13** |
| Tap-and-hold ~1.5 s on the timeline to rescale ~10x for fine adjustment | **T14** |
| Zoom out to Earth's orbit for a sense of the orbiter's scale | **T15(a)** |
| Planet orbits bolder + labelled so people don't get lost | **T15(b)**, **T15(c)** |
| See Earth on the same side the texture is on | **T16** |
| Explain eruptions vs CME | **T12** *(blocked on a question — the Eruptions layer is off on `main`)* |
| Aurora box: "heads towards the equator", not "northern lights heads south" | **T12** |
| Explain flare vs CME in the flare text box | **T12** |
| Add labels for the planets | **T15(c)** |
| Zoom out to the heliopause/heliosphere, bringing up the Voyager orbits | **T17** |
