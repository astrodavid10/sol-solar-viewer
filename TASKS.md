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

**Last updated:** 2026-08-25 (seventh session)

---

## Status

Rows are listed in **execution order**. IDs are stable names, not positions — T11/T12 sit
where they do because they are live guest-facing defects reported by a real reviewer, which
the plan says outrank documentation work.

| # | Task | Status | Commit | Note |
|---|------|--------|--------|------|
| T0 | Stand up this ledger | DONE | `3108484` | 18 rows incl. Alex's review |
| T1 | Republish PFSS from the workstation | TODO | — | live PFSS is ~30 h stale |
| T2 | Land the GONG relay (Option D, workstation mirror) | TODO | — | code uncommitted since session 5 |
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

**Go-live steps:** review + commit → `--dry-run` the mirror → create the `gong-cache` branch →
install the Scheduled Task → set `SOL_GONG_PROXY_BASE` and `SOL_GONG_PROXY_INDEX` as
repository secrets → confirm from a real scheduled run.

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
