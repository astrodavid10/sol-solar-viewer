# Sol — project handoff & status

**Living document.** Update it at the end of any session that changes project state. It exists
so a fresh session (human or Claude) can pick the work up without re-deriving context.

- **Last updated:** 2026-08-23 (third session that day)
- **LIVE AT https://astrodavid10.github.io/sol-solar-viewer/** — the repo is PUBLIC, Pages is
  enabled on `gh-pages` / root, and the deployed data tree passes
  `validate --url … --strict` at 0 failed / 0 warnings.
- **Repo:** `github.com/astrodavid10/sol-solar-viewer`. Actions ENABLED, `gh-pages` carries
  the app at the root and all six data products under `data/`.
- **Branch:** `main`. The old note here said work was on `feature/unified-sphere-view` and
  that main was stale; that branch was **merged in `eeccf06`** and `main` has been ahead ever
  since. Work on `main`.
- **Status summary:** feature-complete against the v1 plan, building clean. The remaining
  headline risk is unchanged and is the reason nothing else should be built on top:
  **almost none of the 3D work has been seen in a browser** — see §4.
- **Current plan:** a six-workstream plan was approved in the third session — the pipeline
  half of time-aligned imagery (**DONE**, §3z), the design system (**partly done**, §3z),
  responsive overlays, label/render performance, gestures (pinch + twist), and the app half of
  time-aligned imagery. The plan file lives outside the repo at
  `~/.claude/plans/review-the-claude-md-and-hidden-rabin.md`.

### Read these first, in this order

1. `CLAUDE.md` — architecture + **30 numbered footguns**. Dense and authoritative. The
   footguns are hard-won; several document bugs that took hours to find. Do not "fix" them.
2. This file — what is done, what is not, what is unverified.
3. The original implementation plan — a local Claude Code planning document, not in this
   repo. Milestone IDs (M-W*, M-P*) below come from it. Its load-bearing half, the data
   contract, is restated in `CLAUDE.md` and enforced by `pipeline/validate.py`.

---

## 1. State at a glance

| | |
|---|---|
| App (`src/`) | Vue 3 + TS; one unified sphere view (no disk view since `a270e5a`) |
| Pipeline (`pipeline/`) | 26 files, ~5,900 lines — Python, conda env `sdo` |
| `yarn lint` / `yarn typecheck` / `yarn build` | all **PASS** |
| `pipeline validate --root public/data --strict` | **0 failed, 0 warnings** |
| Data products building | 6 of 6 (pfss, ar, ephem, stats, texture, events) |
| PFSS window | 72 h, 4 h spacing, **19 frames** (`config.WINDOW_HOURS`) |
| Sphere textures | **5 channels** at 4096x2048, one frame each (per-frame is workstream 1) |
| Git commits | 22 on `feature/unified-sphere-view` |
| Automated tests | none (the pipeline validator is the de-facto test suite; the app has none) |
| CI workflows | `data.yml` and `app-deploy.yml` both green end-to-end; `build.yml` and `keepalive.yml` still unexercised |

### Top risks, highest first

1. **The 3D view has never been confirmed working in a browser.** Large amounts of geometry
   were derived from engine source and verified numerically, not visually. See §4.
2. **GitHub Pages is not enabled**, so nothing is served yet. On a private repo it needs
   GitHub Pro; **making the repo public is the agreed route** (it is also what removes the
   Actions-minutes quota). `gh-pages` already exists and carries both the app and `data/`, at
   exactly one commit. Remaining steps: merge this branch to `main`, flip visibility, then
   `gh api -X POST repos/astrodavid10/sol-solar-viewer/pages -f source[branch]=gh-pages -f source[path]=/`.
   The `data.yml` (4-hourly) and `keepalive.yml` (monthly) schedules are armed.
   **One open question blocks the flip** — see §3, Highway Gothic Narrow.
3. **No app-side tests.** Regressions in the app are caught only by eye.
4. **Field lines are hand-fed.** GONG is unreachable from CI (see below), so the published
   frames come from a workstation run. They age out of the 8 h staleness threshold and the
   app will start showing its "data is stale" banner until someone republishes or the CI
   blockage is solved.

---

## 2. Milestone status

Legend: **VERIFIED** = seen working in a browser · **DONE** = implemented, builds, passes its
own checks, not seen running · **PARTIAL** · **NOT STARTED**

### Web track

| ID | Scope | Status |
|---|---|---|
| M-W0 | Bootstrap from exo-sonification skeleton | **DONE** |
| M-W1 | Shell + "Sun Now" disk viewer | **REMOVED** — the disk view was deleted in `a270e5a`; one unified sphere view now |
| M-W2 | Live SWPC stats | **VERIFIED** |
| M-W3 | WWT 3D boots (`wwt/sunStage.ts`) | **VERIFIED** (2026-08-23) |
| M-W4 | three.js stage on WWT's canvas (vendored `three-wwt`) | **VERIFIED** — no winding warning, no console errors |
| M-W5 | PFSS field lines + 72 h scrubber | **VERIFIED** — renders and morphs; scrub interaction not stress-tested |
| M-W6 | Spacecraft trails + labels | **DONE** — layer now defaults OFF, so it renders only when switched on; not exercised |
| M-W7 | Kiosk mode + polish | **DONE** — never run with `?kiosk=1` |
| M-W8 | App consumes `events.json` (flare/CME marks, event card) | **VERIFIED** — marks render on the scrubber track |
| M-W10 | Mobile layout pass (title pill, button stack, stat grid, label de-collision) | **VERIFIED** (2026-08-23) |

### Pipeline track

| ID | Scope | Status |
|---|---|---|
| M-P1 | Scaffold + GONG/SRS sources | **DONE** |
| M-P2 | Timeline + frozen seed set | **DONE** |
| M-P3 | PFSS solve / trace / resample | **DONE** |
| M-P4 | Binary export + validator | **DONE** |
| M-P5 | Ephemeris + regions + stats | **DONE** |
| M-P6 | Outage drills (GONG, SRS, DONKI) | **DONE** |
| M-P7 | CI end-to-end | **PARTIAL — and the partial half is the important half.** The publish path is now exercised and green, and the deployed tree validates. But **GONG is unreachable from GitHub runners**, so the scheduled pipeline has never once built field lines (§3a). Everything except `pfss` builds in CI. |
| M-P8 | DONKI source + events product | **DONE** (2026-08-23) |
| M-P9 | Events validator + outage drill | **DONE** (2026-08-23) |
| M-P10 | Per-UT-day sunspot history in `ar/regions.json` (`sol.ar/2`) | **VERIFIED** (2026-08-23) — live and feeding the chip |
| M-P11 | Time-aligned per-slot sphere textures (`sol.texture/3`) | **DONE** (2026-08-23) — 80 of 95 frames built and validating; the other 15 are a real SDO archive gap (§3z) |
| M-P12 | Per-UT-day region POSITIONS in `ar/regions.json` (`sol.ar/3`) | **DONE** (2026-08-23) — validates; app half is WS5 |
| M-P13 | GONG relay seam + Cloudflare Worker + docs | **PARTIAL** — code and worker are in and tested; the deploy needs an account holder (§3z) |

### Phase 2

| ID | Scope | Status |
|---|---|---|
| P2.1 | Live AIA texture on the 3D sphere | **VERIFIED**, extended to **5 channels** at 4096x2048 |
| P2.2 | PUNCH + Proba-3 markers | **PARTIAL** — `ephem/spacecraft.json` ships the `at_earth` metadata; the app does not render them |
| P2.3 | LMSAL PFSS fallback (`?pfss=lmsal`) | **NOT STARTED** — worth reconsidering now that GONG is unreachable from CI |
| P2.4a | Flare markers on the disk view | **OBSOLETE** — no disk view |
| P2.4b | Web Share API | **VERIFIED** — in the top-right button stack |
| P2.4c | "What changed since the show" card | **NOT STARTED** |
| P2.4d | `prefers-reduced-motion` | **PARTIAL** — one file only, not applied systematically |
| P2.4e | Audio narration | **NOT STARTED** |
| — | Per-frame sphere textures | **PIPELINE DONE, APP NOT STARTED** — the data is published and validating; `sunSurface.ts` still loads one texture per channel (§3z) |
| — | Flare/CME 3D eruption (see §6) | **NOT STARTED** — feasibility study done |

### Integration (M-INT)

| Scope | Status |
|---|---|
| Deployed-site load | **DONE** — live, validates 0/0 |
| Real-phone QR test | **NOT STARTED** — the main remaining verification gap (§4) |
| Lighthouse mobile | **NOT STARTED** |
| Field-line orientation cross-check vs GSFC's own PFSS overlay | **NOT STARTED** |
| Overnight kiosk soak | **NOT STARTED** |

---

## 3z. What changed on 2026-08-23 (THIRD session — most recent)

A six-workstream plan was approved covering everything the user named: the off-brand palette,
overlays that clip each other, the credit lockup, unreliable pinch zoom plus twist-to-rotate,
time-aligned SDO imagery, and low label framerate while dragging. **The pipeline half of the
headline item is done and published; the design system is partly done.** Everything below
builds clean and `validate --root public/data --strict` reports **0 failed, 0 warnings** over
1,796 checks.

### The headline item is unblocked: SDO serves a date-addressed archive

Probed live rather than assumed. `https://sdo.gsfc.nasa.gov/assets/img/browse/YYYY/MM/DD/`
holds **11,026 files per UT day** — every channel at 256/512/1024/2048/3072/4096, AIA at
288 frames/day (5 min) and HMI at up to 96 (15 min), going back **at least a year**. The
filenames carry irregular seconds, so URLs cannot be constructed; the day listing has to be
scraped and nearest-matched. Listing is 1.64 MB in 0.93 s.

Crucially these are the **same renderings** as the `latest_*` stills the pipeline already used,
so per-slot textures keep color-table parity with the dome show for free. And the pipeline was
most of the way there already: `browse_candidates` already iterated day directories and parsed
obstime per filename, and everything geometric already derived from `src.obstime` rather than
`now` — so a per-timestamp fetch needed **zero maths changes downstream**. No JSOC/Fido path
was needed.

**What shipped (`sol.texture/3`):**

- `fetch_source_at(target, ...)` picks the frame nearest a slot's target time, walking outward
  past unusable frames. It never falls back to `latest_*.jpg` — substituting today's Sun for a
  three-day-old one is the exact dishonesty this feature exists to remove.
- Frames are keyed on the PFSS timeline's own `slot_targets`, at 2048x1024, named for the
  **target time** (`sdo0171_carr_2048x1024_20260820T1600Z.jpg`) rather than a frame index.
  → **footgun 36**: indices shift every run, so an index-keyed name would make all 95 files
  look new every four hours and re-reproject the whole window forever.
- The newest slot stays the 4096x2048 map and deliberately carries the **freshest available**
  image rather than one snapped to the grid — that slot is what "the Sun right now" means.
- Each layer gained a `frames[]` array; the top-level fields still describe the first channel's
  newest frame, so a schema-2 reader stays correct (footgun 22's discipline).
- A day-listing cache means all five channels and all 19 slots come out of the same document:
  4 HTTP GETs per run instead of 20.
- `TEX_HIST_TOLERANCE_HOURS` is **half the slot spacing**, derived not typed. Inside it the
  chosen frame is unambiguously closest to that slot; outside it some other slot is closer, so
  filling it would show a guest the same picture at two playhead positions.
- `TEX_HIST_MAX_NEW_PER_RUN = 15` bounds the CI job at ~8 s per new frame; `--max-new-textures`
  overrides it so a workstation can fill the window in one pass (measured 623 s).
- Orphan pruning for texture files, which only existed for `pfss/f*.bin` before — visible
  beforehand as 443 KB of unreferenced schema-1 maps.

**Measured result:** 16 frames per channel, 10.85 MB of history, `public/data` 5.3 MB → **16.79
MB**, `texture.json` 4.9 KB → 37 KB. Zero extra bytes for a guest who never scrubs.

**The reuse path is PROVEN, not assumed** — the mechanism the CI budget depends on.
A second run against the same tree reported `75 reused, 0 built, 15 unavailable
upstream, 0 deferred by the cap`: only the five full-resolution newest maps were
rebuilt. Cold build was 623 s for 80 frames (~8 s each); warm is the five newest
maps alone.

**A real upstream gap, correctly handled.** The SDO browse archive for **2026-08-21 stops at
12:42 UT in every channel at every resolution** — verified directly against the listings, not
inferred. Three slots x five channels are therefore unobtainable for this window, and they are
**omitted from the manifest** with a per-slot log line rather than filled with the wrong hour.
The app must fall back to the nearest frame it has. The run log now separates "unavailable
upstream" from "deferred by the cap": the first will not fix itself and the second will, and
reporting them as one number tells an operator to wait for something that is not coming.

### Regions can follow the playhead too (`sol.ar/3`)

`ar/regions.json` carried per-day COUNTS but today-only positions, so surface markers pinned
today's spots onto three-day-old imagery. The upstream data was **already being downloaded**:
`sources/srs.py:fetch_regions_json` has parsed per-day `latitude` and `carrington_longitude`
all along (228 records over 31 days, memoized) and `daily_history` simply discarded them.

Each history day now carries its own `regions` array, normalized by one shared
`_region_entry()` so the top-level list and the per-day lists can never drift apart. History
entries deliberately carry **no `seed_count`** — the frozen seed set describes today's trace,
and a number there would imply field lines that were never traced. 1.6 KB → 7 KB.

Physically convenient: in the Carrington frame a region barely moves (measured, `carr_lon` for
AR 4514 goes 172 → 173 → 174 over three days), which is the point of a co-rotating frame. What
actually changes across the window is **which** regions exist and how many spots each has.

### GONG: no upstream mirror exists, so the fix is a relay

Researched exhaustively, and the conclusion is that footgun 33 was right rather than incomplete.
**Every host that serves the mrzqs product resolves to the same blocked address, 146.5.21.69** —
`gong.nso.edu`, `nispdata`, `magmap`, `solis`, and anonymous FTP (which returns a
sha256-identical file). sunpy's VSO `GONGClient` is provably a wrapper around that same host.
JSOC carries **zero** GONG series. Helioviewer has GONG H-alpha, a different physical
observable. NOAA NCEI's archive is not publicly downloadable. fly.io's free tier is gone.

So the seam is built and tested, and only the deploy is outstanding:

- `SOL_GONG_PROXY_BASE` / `SOL_GONG_PROXY_TOKEN` env vars, wired into `data.yml`'s probe and
  build steps as repository secrets. Unset, behavior is exactly as today.
- `sources/gong.py:_relay()` rewrites URLs **at request time only** → **footgun 37**. Cache
  keys, manifests and logs stay canonical, because `gong_file_key` derives the traced-frame
  cache key from the URL (a relay change would otherwise invalidate every cached frame) and
  because crediting our own proxy for NSO's data would be wrong.
- `scripts/gong-proxy-worker.js` + `wrangler.toml` — a Cloudflare Worker that requires the
  shared secret and forwards **only** the two URL shapes the pipeline asks for, so it cannot be
  used to mirror the rest of NSO. Path guards unit-tested against the real URLs and three
  hostile ones. Edge-cached: 10 min for listings, 1 day for the immutable FITS.
- `probe-sources` now prints whether a relay is configured and whether the token is set, so a
  green probe says WHICH path worked.
- `docs/GONG-RELAY.md` — the deploy steps, and the full ruled-out table so nobody re-derives it.

**Remaining human step:** `wrangler deploy` + two repository secrets. Nothing else blocks it.

### Design system, partly landed

- **`--sol-accent-rgb`.** The gold triplet was retyped as a literal at 19 sites across 7 files,
  and `common.less` held a **dead copy** that poisoned exactly that find/replace. One token now;
  all 19 sites route through it, and the dead block is gone.
- **The chrome is cool.** `--sol-panel-border` was gold, painting every rail panel in the same
  hue as closed field loops — the chrome competing with the Sun instead of framing it. Now a
  cool neutral at 22%, which takes gold off every panel with one line. Spaceberry surfaces,
  Light Speed White text, Spaceship Gray dim text, plus `--sol-ember` and `--sol-violet` as
  lifted Cosmaroon/Spacebubble (both are too dark at their kit values to work on a dark ground).
  Four hardcoded `rgba(8, 6, 2, a)` olive-brown plates cooled to the same hue as the tokens.
  **In-scene physics colors are untouched** — closed loops, open field, wind and glow are the
  dome show's legend, and a guest may see the dome an hour before the phone.
- **The credit lockup**, as asked. The WWT emblem was a bare unlinked 64x64 `<img>` whose
  `max-width: 6rem` was **never binding** (96 px against a 64 px intrinsic), so it rendered
  full size — which is what made it look big. It and a vendored CosmicDS mark are now two
  22 px `.im-attr` rows ("Interactive developed using the CosmicDS toolkit" / "Powered by
  WorldWide Telescope"), both linked, below the IP+USSRC lockup — which stays a single paired
  image because the brand kit requires it. The duplicate text credit was removed.
  `src/assets/logo_cosmicds.png` is the spiral device only: the wordmark half is dark navy and
  would be illegible on these panels, and the caption names CosmicDS anyway. Recorded in
  `THIRD-PARTY.md`.
- **`.fade-*` transitions were broken app-wide.** `common.less` used `.fade-enter`, which is
  **Vue 2** naming; Vue 3 wants `.fade-enter-from`. Every `<transition name="fade">` faded out
  correctly and snapped in with no transition at all. Four sites.
- **`KioskStatsPanel.vue`** read *"Exoplanet Sonification Kiosk — Usage Stats"* with the donor
  project's entire blue palette and zero `--sol-*` usage, on a public site at `?kioskStats=1`.
  Retitled and rethemed.
- Dead donor CSS swept (`#modal-loading` — an un-tokenized duplicate of `.sol-spinner` and the
  second home of the gold literal — `.bottom-sheet`, `.pointer`, `.control-icon`, `.scrollable`,
  `.pointer-events`, `--default-font-size`/`-line-height`, and the off-palette link color
  `#aec2fd`, which was the only link color in the app). Added `.sol-num` (tabular figures, so
  live numbers stop jittering as they refresh) and `.sol-section-head` (the kit's own
  letterspaced-caps-over-a-rule convention). Favicon moved onto a Spaceberry ground — the disk
  keeps its solar gold, because that is the Sun.

### One process footgun learned the hard way

**footgun 35: one pipeline run per `--out` at a time.** `Staging` is a FIXED `<out>/.staging`
path and `reset()` `rmtree`s it. A `regions` run wiped 14 of 18 staged texture files out from
under a running `texture` run, which then promoted the survivors and wrote a `texture.json`
naming 15 history frames of which 4 existed. Nothing raised; exit code 0.

### Overlays, gestures, performance — the rest of the session

**All seven measured overlay defects fixed at the cause.** The arithmetic for each
is in the code comments; the headline ones: the scrubber painted over the card
whenever the stale banner showed (a fixed `bottom` cannot see +18 px of banner
coming — both now live in one flex column); the layer popover hung off a
hardcoded button count of `4` despite a comment claiming it was derived, and had
no `max-height`, so on a landscape phone it clipped mid-content with no
scrollbar (footgun 28's exact failure mode); the far-side note overlapped the
button stack below ~416 px AND was covered entirely by the title pill on any
notched phone, because it had no `env(safe-area-inset-top)` while the title
does. **E7 is the one worth remembering:** in overlay mode the three.js canvas
sits at `z-index: 10` inside `.solar-view-3d` and outranked the whole UI at 5 —
and that is not just `?three=overlay`, because `stage.ts` falls back to overlay
mode **automatically on WebGL1-only devices**, i.e. exactly the cheap phone a
guest is likely to have. Field lines painted over the scrubber, the card and the
labels on those devices.

**Gestures: the app now owns touch input.** The engine's two-finger handling was
not fixable in place — four independent faults, each sufficient on its own,
every one read out of the engine source and recorded in `src/wwt/gestures.ts`:
two competing implementations (`touch*` AND `pointer*` bound to the same canvas,
both calling `zoom()`, so the applied ratio was roughly SQUARED — and with
different gates, so the gain changed abruptly mid-gesture); `_rotating` latching
and blocking zoom for the rest of a gesture; `_dragging` latching because
`onTouchEnd` returns early without clearing it; and two-finger mode being decided
from `targetTouches`, which excludes any finger that landed on an overlay
element. That last one is the user's actual complaint, and it is why the new
module listens on the **stage root in the capture phase** — a second finger
landing on a label chip is seen before the chip sees it.

Twist needed new state: `orbitByPixels` recomputes `camera.rotation` from
scratch every drag step to keep solar north up, so a roll written into the camera
survived only until the next pan. `sunStage` now owns `userRollRad` that the
framing is ADDED to; recenter is the only thing that clears it.
→ **footgun 38** (these patches must be installed at import time, like
`onGesture*`) and **footgun 39** (`backdrop-filter` over the shared canvas costs
a blur every frame whether the element moves or not).

**`TWIST_SIGN` is UNVERIFIED.** It is a named constant for the same reason
`AZIMUTH_SIGN`/`ELEVATION_SIGN` are: the sign cannot be derived reliably through
a left-handed view matrix and a y-down screen. If twist rotates the wrong way,
flip one character in `gestures.ts`.

**Label framerate — the reported symptom, root-caused.** The GPU is not the
problem: the scene is ~15 draw calls and ~23k vertices. Three CPU/compositor
costs that all scale with camera motion:

- **`backdrop-filter` on the four chips that move every frame**, over a canvas
  that repaints every frame. A backdrop-filter is recomputed whenever its
  backdrop changes, so they were re-blurring at 60 Hz. HANDOFF §8.4 had already
  specified "NO backdrop-filter — blur is the most expensive thing in the
  overlay" and estimated the risk at 20 Hz; the shipped code had it at 60.
  Removed from the chips and from the far-side note; a higher plate alpha does
  the legibility job for nothing.
- **`solarWind.tick()` ran a 3,000-particle loop and re-uploaded 48 KB of
  attributes every frame, outside every throttle in the app** (it is reached
  from `updateSun`, not from the projection block). Now a fixed 30 Hz cadence
  with time ACCUMULATED rather than dropped, so the wind still travels at the
  speed the solar-wind reading implies.
- **Per-frame allocation.** `project.ts` claimed "nothing is allocated per
  call" — true of its vectors, false of its output (one object literal per
  target per call, ~1,080/s during a drag). `deCollideLabels` allocated ~5 arrays
  and 2 closures per invocation. Both zero now. The solar axis was also being
  re-derived from the Julian date on every pointer event and twice per frame in
  `clampCameraLat`, for a value that moves 1e-5 deg/minute — cached.

Drag input is also coalesced now: deltas accumulate and apply once per animation
frame, because a museum touchscreen fires several `pointermove` events per
rendered frame (`kiosk.ts:67` already said so) and `orbitByPixels` does real
trigonometry.

### A real bug found by measurement: label de-collision was wrong in the common case

The old algorithm closed a "run" whenever a chip cleared the **previous** one in
y, so chip A and chip C could land in different runs because B separated them —
and then still overlap each other. Fuzzed over 20,000 layouts, that left an
overlap in **3.67% of realistic phone layouts and 33.95% when the chips cluster
near disk centre**. Clustering near disk centre is not the unusual case: active
regions live in the activity belts, which is exactly where they bunch up. §8.0
had already flagged "two active regions near disk centre" as the case §8.4 did
not anticipate — this is that case, quantified.

Now every chip clears the stride against every already-placed chip it overlaps
horizontally, and independent groups (union-find over the x-overlap graph) are
shifted rigidly back onto their own mean — safe precisely because chips in
different groups provably do not overlap in x. **0.00% overlaps** at every
viewport tested.

**`scripts/check_label_layout.mjs` is the app's first test.** It asserts what has
to hold rather than what the code does: no overlapping pair inside the stride, `x`
never mutated, and the caller's array order preserved (that order IS the chip
identity — the template renders `chips[i]`, so a reorder would relabel every
marker). It earned its keep immediately: my first version of the grouping cached
a group id that a merge could invalidate, leaving 38 bad pairs in 20,000 — rare
enough to look like it worked, and only the fuzz found it.

### App half of time-aligned imagery

`sunSurface.ts` reads `sol.texture/3`'s per-slot frames and `setFrameTime(unix)`
snaps to the nearest 4 h slot, driven from the playhead on the chip cadence.
Snapping rather than cross-fading follows the **solar wind's** precedent (rebuild
on integer frame change) rather than the field lines' GPU `uMix` blend: a
cross-fade needs a second sampler and twice the resident memory to smooth
something the 4 h data cadence does not support.

Residency became a **byte budget (40 MB), not "exactly one texture"**. The newest
map is 4096x2048 (32 MB as RGBA) and history frames are 2048x1024 (8 MB), so a
frame COUNT would either allow four newest maps or discard three history frames
per newest one. A plain LRU means scrubbing back naturally evicts the big one and
buys four history frames instead; the frame on screen is never evicted; both
neighbours are prefetched, because a dragging playhead reverses constantly.
**Not yet measured on a phone** — that number is the one to lower if a mid-range
device runs out of texture memory.

The terminator came free exactly as the old comment promised: `adoptTexture`
rewrites the info's sub-Earth fields, so `subEarthFrame()` and
`unobservedFraction()` follow the pixels without knowing frames exist.

**The off-limb billboard is hidden while scrubbed.** It is a photograph of the
corona as seen from Earth RIGHT NOW and the pipeline publishes exactly one, so
wrapping it around a three-day-old photosphere would pair today's prominences
with an older Sun. The sphere is time-aligned; this one layer is honest about
only having "now".

### The far-side tip closes now

Dismissal is sticky for the session — it is the same sentence every time. Two
things fixed with it: hysteresis (show above 0.58, hide below 0.50), because a
single threshold meant a drag hovering near it mounted and unmounted a
transition-wrapped element several times a second; and its fraction is no longer
reactive state, because it was a reactive write per frame dirtying the whole
overlay's render effect to move a hint that only appears or disappears.

### Design tiers 2-3: the two items §8.0 called highest-value are done

**`RegionLabel`'s gold text is gone** — it measured **1.54:1 on the photosphere**,
the worst contrast anywhere in the app, sitting by definition exactly where it
was worst. The chip had no background at all, so the text sat naked on the
brightest thing on screen; nothing survives there (app text 1.10:1, gold 1.54:1,
dim text 2.22:1), which is the whole argument of §8.3's last table. The chip now
carries a solid plate (14.6:1) and gold lives in the ring only. Colour also stops
being the sole carrier: the ring means "active region", the ⊕ glyph means
"sub-Earth".

**Fat orbit lines shipped.** §8.2 named 1-device-pixel trails as the root cause
of "the planet orbits don't pop very well", and it was never a colour problem:
`LineBasicMaterial` renders exactly one DEVICE pixel on WebGL whatever
`linewidth` says, so on a DPR-3 phone each orbit was **0.33 CSS px**. The
opacities had already been lifted once without helping, which is the tell. Now
`Line2`/`LineGeometry`/`LineMaterial` (already in three 0.185; nothing in `src/`
had imported them) with a two-pass road casing. Both of §8.4(e)'s warnings
observed and commented: `side: FLAT_SIDE`, or WWT's reversed winding culls every
quad (footgun 19); and `resolution` from `stage.bufferSize()`, never
`gl.canvas.width` (footgun 16) — plus a CSS-to-device scale, without which a
"2 px" line draws 0.67 CSS px on DPR 3 and the original bug returns in disguise.
Cost +29.5 KiB raw / +9.3 KiB gzipped, in the async 3D chunk, so first paint is
unaffected.

Planet orbits (§8.4f, `solarSystemOrbits = false` plus our own from
`orbitSampleVerticesAU()`) are still NOT done — those are WWT's and remain
unstyleable.

### Verified end to end over HTTP

Through the dev server, so the data contract is proven rather than assumed:
`sol.texture/3` serves 5 layers x 16 frames (oldest 2048x1024, newest
4096x2048), an individual history frame returns as a 150 KB JPEG, and `sol.ar/3`
serves 4 history days each carrying its regions' positions.

### The palette read as LSU. That was measurable, and it is fixed.

Reported as "a little too much LSU colors", which was exactly right, and not a
matter of taste:

| | hue |
|---|---|
| LSU purple `#461D7C` | 265.9 deg |
| the surface I shipped `#0E0526` | **256.4 deg** — 9.5 deg away |
| LSU gold `#FDD023` | 47.6 deg |
| the accent I kept `#FFC850` | **41.1 deg** — 6.5 deg away |

Two colours that close to a famous pair, used in the same relationship (dark
ground, bright accent), read as that pair. The error was twofold: taking
Spaceberry literally for the surfaces AND keeping gold as the UI's "on" state —
which also quietly defeated the original brief, "away from the yellow on brown
grey", because it preserved the yellow-on-dark relationship the brief was asking
to leave.

Two fixes, each independently defensible:

1. **Surfaces move to hue ~230** — navy, 36 deg clear of LSU purple and much
   closer to Spacebubble (238) than Spaceberry (263). "Deep space" was always
   the brief; navy says it and grape does not. Contrast IMPROVES: body text over
   a bright disk goes 14.05 → 14.73:1.
2. **Gold leaves the chrome entirely.** It now appears only where it carries
   data meaning: closed field lines, a C-class flare diamond, the ring that
   means "active region". Selection is a brand neutral (`--sol-select`, Nova
   White) at 16.37:1 against gold's 12.66:1, and unconfusable with any physics
   colour — which gold genuinely was, a gold-bordered switch sitting inches from
   gold closed-field lines meaning something else entirely.

That swept **28 gold sites**, including the app's own title, every `InfoModal`
heading and every `is-active` state. Warnings keep amber through a new semantic
`--sol-warn`, because "caution" is what amber means almost universally and
warnings are rare, brief and never adjacent to a field line — but as a separate
token, so "warning" and "closed magnetic field" stop being the same string. The
kiosk take-home pill goes ember, one of exactly three places the ember guard-rail
permits it. Roughly 20 ad-hoc `rgba(255,255,255,x)` greys were unified onto
`--sol-hairline` / `--sol-hover`.

### The layer panel was misaligned by 43.6 px, measured

A row's label starts after the 34 px switch and its 0.6rem gap
(0.5rem + 34 + 0.6rem = 51.6 px); the "Surface" group label started at the bare
0.5rem = 8 px — with `font-size: 0.85rem; font-weight: 600`, **byte for byte
identical to the row labels**. Identical styling at a different indent is the
worst of both readings: it looks like a peer of the rows and lines up with
nothing. It is now a real section header using the global `.sol-section-head`
class, which carries the kit's own convention (letterspaced caps over a thin
rule) and matches every other heading in the app instead of being this
component's private invention. Vertical padding was three numbers for one rhythm
(0.3 / 0.35 / 0.4rem); it is one now.

**Measuring the switch caught a bug in my own first values.** At 0.42 alpha the
on/off change was 2.88:1, under the 3.0 a state change needs to be
unmistakable, and the off track sat at 1.24:1 against the panel — a switch you
cannot see until you turn it on. Now 0.55 on / 0.28 off: 3.45:1 between states,
1.56:1 for the off track, and the knob keeps 3.29:1 against the lit track plus a
dark ring at 5.59:1, because the knob's POSITION is the only thing that says
which way the switch is thrown. Keyboard focus was also invisible on every row
and segment (`border: none`, no outline rule).

### Opt-in 4K sphere texture (`--with-hires`, `sol.texture/4`)

A per-layer `high_res` block holding one 8192x4096 map of the NEWEST frame,
built from SDO's 4096 px browse still. Off by default in the pipeline AND in the
app. → **footgun 40**, which has the whole rationale; the essentials:

- **8192, not 4096, is the point.** Half a plate-carree map is the visible
  hemisphere, so a 4096-wide map gives 2048 px across a disk carrying ~3204 px of
  real detail in a 4096 source. The normal map was discarding most of a 4K frame.
- **0304 is excluded and that is the guard working.** Its limb fits +2.28% at a
  2048 source (inside tolerance) but **+4.4% at 4096** — `r_pred` doubles
  exactly with resolution, `r_fit` comes out 30 px wider than twice the 2048 fit,
  because 0304 is He II 304 A with the most extended chromospheric limb of the
  AIA channels and more ray samples cross a diffuse edge further out. Do NOT
  raise `TEX_LIMB_RADIUS_TOL`: it exists to catch SDO re-cropping the browse
  product, and a 4% radius error displaces every feature on the disk. Four of
  five channels get 4K; the failure is soft and the app hides the option per
  channel.
- **GPU is the binding constraint, not bytes.** ~1.1-3.5 MB on the wire against
  ~134 MB decoded. `hasHighRes()` reads `gl.MAX_TEXTURE_SIZE` from the real
  renderer and returns false when it does not fit (many phones cap at 4096) —
  and false when no renderer was passed, which fails closed but silently
  disables the feature, so `SolarView3D` must keep passing `rt.stage.renderer`.
  The texture lives in its own slot OUTSIDE the LRU, because at 3x the whole
  budget it would evict everything on sight.
- **Never in CI:** ~100-230 s per 8192 reprojection, ~11 min for four channels.
  Workstation/dome only, published by hand.

Measured: 0171 1.32 MB / 232 s · 0193 1.06 MB / 218 s · HMIIC 1.10 MB / 126 s ·
HMIB 3.46 MB / 99 s · 0304 skipped. ~7 MB added.

**The UI toggle is NOT built yet** — `sunSurface` exposes `hasHighRes()`,
`setHighRes()`, `highResActive()`, `maxTextureSize()` and nothing calls them.

### A NameError hid in a rarely-taken branch for several runs

`TEX_HIST_TOLERANCE_HOURS` was used in a `cli.py` log message but never added to
that module's `from .config import (...)`. It sits on the branch that only runs
when a timeline slot has no usable source image, so it never fired on the happy
path — and when it did, it killed the texture stage **after four minutes of
reprojection**, rolled the product back and published nothing.

Two things worth keeping from it. First, **the failure policy worked**:
`index.json` correctly reported texture as `ok`, "not regenerated this run", not
stale, and the previously-published product was left serving. Nothing was
damaged. Second, **it was read past once.** A grep for
`history:|capped|omitted|layer(s)` partially matched, the reuse conclusion drawn
from it was correct, and the crash below it went unnoticed. Check exit codes, not
greps.

`scripts/check_pipeline_names.py` now catches the whole class. `pipeline/` had no
Python linting of any kind — no pyflakes, flake8 or ruff, no config — and its
only real test is the validator, which needs a complete run to say anything. The
script uses Python's own `symtable` (no dependencies) to find every name a
function expects in module globals and check the module has it. **Negative-tested**
against a throwaway module reproducing the exact bug shape plus a plain typo: it
flagged both, and returns clean when removed. 26 modules, 0 problems.
→ **footgun 41** also records why background pipeline runs need `python -u`: a
killed run without it leaves a ZERO-BYTE log, and the only evidence of what
happened is the mtimes on `.staging`.

### ⚠ NOT VERIFIED IN A BROWSER

**This session had no browser automation available.** Everything above passes
`yarn lint`, `yarn typecheck` and `yarn build`, the pipeline validates 0/0, and
the label-layout invariants are proven by test — but **none of the visual or
touch work has been seen running.** Specifically unverified:

- every overlay fix at every viewport (the §4 iframe harness is the tool; add
  **812x375 landscape**, which is the case E4 breaks in, and **320 px**, which is
  E6's);
- the whole gesture module: pinch, twist, `TWIST_SIGN`, one-finger orbit, and
  whether a first finger on a label chip still taps it;
- the texture sequence actually swapping as the scrubber moves, and whether the
  snap reads as a jump;
- the cooled palette, the new credit rows, the region-label plate and the fat
  orbit lines (the last is the one most likely to need tuning by eye — the
  casing/core widths were taken from the design spec, not from a screen);
- GPU memory under a real scrub on a real phone.

`preview.jpg` was NOT regenerated — it needs a screenshot of the running app, so
it is still the pre-redesign image.

### Still not done from the approved plan

**Browser and phone verification of everything this session touched** (see the
warning above — this is now the single biggest gap) · `preview.jpg` ·
deploying the GONG relay (`wrangler deploy` + two repo secrets; the code is
ready) · our own planet orbits (§8.4f) · a texture cross-fade, if the 4 h snap
reads badly · M-W9's CME eruption layer · Lighthouse mobile · kiosk soak.

---

## 3a. What changed on 2026-08-23 (second session)

A four-workstream plan was approved: (1) time-aligned per-frame sphere textures, (2) the §8
design overhaul, (3) commit/merge/publish publicly, (4) a set of small corrections.
**Workstreams 3 and 4 are DONE. Workstream 2 is partly done (tokens/chrome landed as part of
the mobile layout pass; §8.7 has the detail). Workstream 1 has not been started** — it is now
the largest remaining item, see §5.

**THE SITE IS LIVE.** https://astrodavid10.github.io/sol-solar-viewer/ — repo made public,
Pages enabled on `gh-pages` / root. The deployed data tree passes
`validate --url … --strict` at 0 failed / 0 warnings. → **footgun 34** (a forced orphan push
can wedge the Pages build; kick it with `POST /pages/builds`).

**THE 3D VIEW IS CONFIRMED WORKING IN A BROWSER** — the project's headline risk since M-W3,
now closed. No `assertWinding()` warning, `assertTextureFacing` OK at 7.3°, zero console
errors. §4 has exactly what was and was not proven, and the iframe-harness technique, which
is worth reusing.

**Mobile layout pass (M-W10)** — driven by the user reporting alignment problems, then
measured rather than eyeballed:

- **Stat chips clipped their own text at 390 px**, the most common phone width. `.ss-grid`
  jumped to four columns at a `min-width: 381px` breakpoint, giving 87 px tracks that
  truncated four separate strings. Now `repeat(auto-fit, minmax(150px, 1fr))`: content-driven,
  cannot clip, no breakpoint to get wrong.
- **All three surface labels overlapped each other at every viewport tested.** AR 4513,
  AR 4515 and the sub-Earth marker sit ~12 px apart on screen with 44 px-tall chips. New
  `src/three/labelLayout.ts` de-collides them (46 px stride, horizontal independence,
  re-centred on the run's own mean); a moved chip draws a **leader line** back to its true
  projected point, so the marker stays honest and only the text steps aside. Zero overlaps
  after.
- **Title pill + one button stack**, as asked. The banner spent 44 px of a 640 px phone on a
  wordmark and split four controls across two places. `TopBar.vue` is **deleted**; the title
  is an overlay in `sol.vue` (so it paints with the entry chunk, before the engine downloads)
  and recenter/share/info/layers are one vertical stack top-right — four on a phone, two on
  desktop where the rail already carries info and layers. The wide grid drops four rows to
  three, so the Sun runs the full window height.
- **`.solar-view-3d` now has `z-index: 0`.** It had no stacking context, so its descendants
  competed with siblings in `sol.vue` — the bug that hid the brand mark for a whole session,
  and the one the title pill would have hit next. Footgun 27 stays: its reasoning is what
  stops someone deleting the line.

**Defaults changed, per user request.** Field lines start as one electric blue rather than the
polarity palette; spacecraft start OFF, and the two `swhv.oma.be` live-position requests are
deferred until that layer is switched on.

**Sunspot count now follows the scrubber.** The chip was labelled "Sunspots" but showed the
active-region count, always for *today*. It now shows the real spot total for the day under
the playhead, from a new per-UT-day `history` array in `ar/regions.json` (**schema
`sol.ar/2`**) — no new request, no new file. NOAA issues the SRS once a day, so the number
**steps at UT midnight rather than sliding**; the chip names the date so the cadence is
visible, and the freshness dot is suppressed for a scrubbed day.
→ **footgun 30** (NOAA's two SRS products are different series; mixing them fabricated a
34 → 19 overnight collapse).

**`frameTimes` and `sceneUnix` are now shared state** in `useAppState`. `frameT` alone is a
fractional index, so nothing outside the 3D view could turn the playhead into a wall-clock
time — which is why the sunspot chip could not follow it. SolarView3D remains the only writer.

**American English throughout** — 208 replacements across 44 files, plus three identifiers a
`` regex could not reach (`_` and camelCase suppress the boundary). Verified safe first: no
British spelling appears as a key in any published JSON, in any CSS class or `--sol-*` token,
or in any compared/serialized value. `analysis`/`analyst`/`analyses` are identical in both
dialects and were left alone, as was DONKI's `cmeAnalyses`.

**Pre-publication hygiene.** Full-history secret scan clean; no private IPs, paths or emails in
tracked files. Stale "48 h / 13 frames" corrected in fourteen places (SDO's *movies* really
are a rolling 48 h, so those were left — that is why it was done by hand). README described
the deleted disk view. Footgun 22 was two revisions out of date. The favicon hotlinked
`worldwidetelescope.org`. Dead disk-view state (`view`, `channel`, `pfssOverlay`, `diskMode`,
`diskRes`, `diskSettledAt`) removed — `useDeepLink` was still writing
`?view=&wl=&pfss=&movie=&res=` into every shareable URL; those params are still *stripped* on
write, because a QR printed before the consolidation can carry them.

### ⚠ GONG IS UNREACHABLE FROM GITHUB ACTIONS — the scheduled pipeline cannot build field lines

Found while verifying the first real deploy, and it is the most important thing on this page.

`gong2.nso.edu` **times out on every request from a GitHub Actions runner**, and always has:
all four data.yml runs to date (14:45, 14:59, 16:36, 19:41 on 2026-08-23) resolved **0 of 19
slots**. The identical request from a workstation answers HTTP 200 in 0.35 s. Every other
upstream works from the same runner in the same run — JPL Horizons, CCMC DONKI, NOAA SWPC and
SDO GSFC all succeeded. Not IPv6 (footgun 24's cause): `gong2.nso.edu` publishes no AAAA
record at all. A connect *timeout* rather than a 403 or a TLS error is the signature of a
silent firewall drop, so this reads as NSO blocking Azure/GitHub ranges. → **footgun 33**.

**Every one of those runs reported success.** The PFSS stage's failure policy is soft by
design, which is correct for a transient outage and actively misleading for a permanent block.
HANDOFF previously recorded "data.yml passed first try" — true of the exit code, and never
true of the product.

**It was also deleting the live data.** `publish_gh_pages.sh` rsyncs `--delete`, and CI built
into an empty `dist-data`, so "don't publish pfss/, the previous frames keep being served"
actually removed them from gh-pages. → **footgun 31**; `data.yml` now seeds `dist-data` from
`origin/gh-pages -- data` before building, which makes the whole failure policy real.

**Where that leaves things:** the published frames are built on a workstation and pushed by
hand; CI now preserves them and marks `pfss` stale rather than deleting them. Treat a stale
`pfss` entry in `index.json` as expected. Do NOT "fix" it by lowering
`MIN_FRAMES_TO_PUBLISH`.

**Options.** One is already ruled out by measurement: `gong.nso.edu` and `gong2.nso.edu`
resolve to the **same IP** (146.5.21.69), so switching hostname mirrors cannot help — any
allow-listing or blocking applies to both. (`nso.edu` itself is on 50.6.111.190 and is
reachable from CI, but serves no data.) What is left: ask NSO to allow-list GitHub's ranges;
run the data job on a **self-hosted runner** at the planetarium, which is the only option
fully under our control and also removes the 25-minute job cap; substitute a different
synoptic magnetogram source (JSOC's HMI synoptic Carrington maps are the obvious candidate,
but that changes the model input and breaks parity with the dome show, so it is not a casual
swap); or proxy the fetch through a host NSO does not block. Diagnostics are now in place either way — `_scrape_gong`
prints the actual exception (footgun 32), `data.yml` runs `probe-sources` every run, and a
circuit breaker stops asking after two consecutive timeouts (which also gave back ~4 minutes
of every run).

### Font: Highway Gothic Narrow → Overpass (RESOLVED)

`HighwayGothicNarrow.ttf` carried no license record at all (no nameID 13, no nameID 14 — just
`copyright: "2009"` / `trademark: "Ash Pikachu Font"`), and making the repo public would have
redistributed it on unknown terms. Replaced with **Overpass** (Red Hat, SIL OFL 1.1 / LGPL
2.1 dual), which descends from the same US FHWA Standard Alphabets, self-declares its license
in its own name table, and ships its license text alongside at
`src/assets/Overpass-LICENSE.md`. One weight, `font-display: swap`.

The three `Roboto*.ttf` files went too: they had **no `@font-face` rule**, so the browser never
loaded them — naming "Roboto" in a CSS stack only ever resolved to a system copy. 500 KB of
dead weight in every clone.
---

## 3. What changed on 2026-08-23 (FIRST session)

A long session driven by user-reported visual bugs. Root cause of most of them was one thing.

**The big find — WWT's camera reverses triangle winding.** The engine builds matrices with
`lookAtLH` + `perspectiveFovLH` (D3D, left-handed). `wwtMatrixToTHREE` passes them to three
verbatim, so the world→clip transform is orientation-**reversing**: `det(P_wwt) = +1.166e-3`
vs `det(P_three) = -2.332e-3`. three can't detect this — it picks winding from
`object.matrixWorld.determinantAffine()`, never the camera. Every solid mesh had its *front*
faces culled. That one bug produced: the Sun's texture visible "through" the sphere (you were
seeing the inside of the far hemisphere), that surface at ~21% brightness, **and the sun glow
plus every spacecraft marker sprite missing entirely**. Fixed via `src/three/winding.ts`
(`SOLID_SIDE` / `FLAT_SIDE`) with `assertWinding()` re-deriving the sign from the live camera
each session. → footgun 19.

**Same handedness, second victim.** `solarWind.ts` used `max(-mv.z, 1e-9)`, but view-space z
is *positive* toward the viewer here, so it always returned `1e-9` and pinned every particle
to the 6 px size ceiling at every zoom. → footgun 20.

**Solar wind** — reverted an extent/speed change the user disliked; kept the sign fix and
replaced alpha-fading with **population thinning** (`(want/ceiling)²` kept, stable per-particle
`aRank`, 10% floor) so it stays dots rather than haze when zoomed out.

**Magnetic Map disk size** — GSFC ships `HMIBpfss` already reframed to AIA's plate scale
(disk fraction 0.7676) while plain `HMIB` is at HMI's (0.9184). The app applied `diskScale` to
both, so with the PFSS overlay on it rendered ~18% undersized. `diskScaleFor(id, res, pfss)`
now mirrors `stillUrl` exactly. Plain-HMI's 0.8395 was measured to be *correct* and left alone.
→ footgun 21.

**Initial 3D framing** — was `lat=7, lng=0`, which puts the camera almost straight down the
*ecliptic north pole*. Now computes the Earth-facing framing with solar north up
(`earthFacingCamera()` in `wwt/sunStage.ts`).

**Multi-channel sphere textures** — `sol.texture/1` → `/2`. `TEX_WAVELENGTHS = (171, 304, 193)`,
one Carrington map each (432 KB total, 38.5 s), `layers` array in `texture.json`. Surface
control is now Coronal Loops / Chromosphere / Hot Corona / Artist. → footgun 22.

**Field-line color toggle** — Polarity vs Electric blue, as a shader uniform. `?fieldcolor=blue`.

**Events pipeline (M-P8/M-P9)** — `sources/donki.py` + `events/export.py` + validator +
outage drill. Produces `data/events/events.json` (~4 KB). → footgun 23 (DONKI AR numbers are
SRS + 10000) and footgun 25 (a CME must not carry the Carrington quaternion).

**Events in the app (M-W8)** — `src/data/events.ts` reader; `TimeScrubber` now marks CMEs as
blue circles distinct from the flare diamonds and emits `pick-event`; tapping a mark scrubs
there *and* opens a card in the existing single card slot (`evt:` prefix). DONKI events take
precedence over NOAA flare history where both describe the same flare — DONKI knows where it
happened and what CME went with it — but NOAA remains the fallback for the newest events
DONKI has not published yet (median lag 1.9 h for flares, 7.5 h for CMEs). Every card carries
"Research data from NASA CCMC — not an official forecast."

**`scripts/make_event_fixture.py`** — writes a synthetic `events.json` covering an X-class
flare with a linked CME, fast Earth-directed CMEs with arrival times, and an unattributed
flare. Needed because the live window is usually boring (2026-08-23: no X-class, no predicted
impacts, 3 of 5 CMEs from regions already rotated off). Built through the pipeline's own
`heeq_to_ecliptic`, so `validate --strict` passes on it — verified.

**Unrelated perf bug found en route** — `kauai.ccmc.gsfc.nasa.gov` publishes a black-holed
AAAA record and urllib has no Happy Eyeballs: 21.06 s to time out on IPv6, then 0.03 s on
IPv4. curl races the families and never notices, which is why a curl probe said 0.87 s for a
URL the pipeline spent 21.8 s on. Fixed with `io_utils._ipv4_only()`. Events stage 47.3 s →
5.4 s standalone, 1.5 s inside `all`. → footgun 24.

**Sunspots chip was permanently blank** (user-reported) — a pipeline/app contract mismatch,
two independent misses that compounded. `stats/export.py` publishes `sunspotNumber` as an
object (`{month, smoothed, value}`) and `activeRegionCount` in camelCase; `parseSnapshot`'s
`pickNumber` understood numbers, numeric strings and arrays but not the publisher's own
`{value, …}` idiom, and its alias list didn't contain `activeRegionCount`. `parseSnapshot`
returns null only when BOTH fields are missing, so two separate bugs presented as one silent
blank. `pickNumber` now unwraps `value` generally. Verified against the real payload:
null/null before, 78.1 / 4 after. The fix also exposed that the chip was about to present a
*July monthly average* as if it were today's Sun, so `sunspotLabel` now names the month.

Lesson worth keeping: the reader's long list of tolerated alias keys created false confidence
— it looked thoroughly defensive while missing the one name the publisher actually uses.

**First real CI run found a publish bug that had never fired.** `data.yml -f dry_run=true`
passed on the first attempt (build + validate + artifact green). But the *publish* step is
skipped in a dry run, so pushing then exercised `app-deploy.yml` for real — and
`publish_gh_pages.sh` failed with "Author identity unknown". The script did set
`git config user.name/user.email`, but on the OUTER repo; it then runs `git init` in `.ghp`,
creating a throwaway repo that inherits none of it, and Actions runners have no global git
identity. Identity now comes from `GIT_AUTHOR_*` / `GIT_COMMITTER_*` environment variables,
which apply regardless of which repo the commit lands in. This would have failed every
scheduled `data.yml` publish too — same script.

---

## 4. Verification ledger

Being explicit about this, because "it builds" did a lot of work here for a long time.

### Proven in a browser (2026-08-23, second session)

**The 3D view works.** This was the project's headline risk from the start and it is now
closed. Verified against the deployed site and then the dev server, using Chrome automation.

- **Winding (footgun 19) is correct.** `assertWinding()` emitted no warning, and the Sun
  renders textured, lit and right way round. The determinant reasoning holds in practice.
- **Surface UV mapping is correct.** `?debug=1` printed
  `[debug] surface sub-Earth check OK: sub-Earth lon 78.5° is 7.3° from Earth`, inside the
  < 8° the check allows (|B0| ≤ 7.25°). A 90° or mirrored mapping could not produce that.
- **The depth-buffer clear (footgun 18) works** — far-side field lines are hidden by the Sun.
- **Zero console errors** on load, deployed and local.
- The Earth-facing home camera, the field-line morph, the scrubber, the event marks, the
  layer panel, the surface channel switcher and the stats row all render and respond.

### Proven by measurement

- **Layout, at 360x640 / 390x844 / 1100x760** (real viewports via an iframe harness — see
  the note at the end of this section):
  - stat chips: 4 columns at 87 px clipped four separate strings at 390 px; after the
    `auto-fit` fix, zero clipped text at any size.
  - surface labels: all three overlapped each other at all three sizes; after
    `labelLayout.ts`, zero overlaps, spaced at exactly the 46 px stride.
  - the Sun's apparent diameter is 25-31% of canvas width across all three, which is the
    framing fitting the whole PFSS domain (source surface 2.5 R_sun ≈ 77% of width), not a
    bug.
- SDO browse-image framing across all channels and resolutions (sub-pixel limb fits);
  `HMIBpfss` vs `HMIB` confirmed by red/green composite where GSFC's own AR number labels
  coincide at scale 1.0.
- The winding determinants (computed from the engine's own `perspectiveFovLH` formula).
- `earthFacingCamera()` — camera lands on the Sun→Earth line to 0.000° across a full
  simulated year; solar north screen-up to 0.0000°.
- Events `dir_ecl` — negative-tested (a 10° rotation makes the validator fail).
- HEEQ→ecliptic conversion cross-checked against an independent solar-longitude route.
- DONKI IPv6 timeout (21.06 s) vs IPv4 (0.03 s), measured directly.
- **GONG from CI**: connect timeouts on all 12 day-directory scrapes, four runs running,
  against HTTP 200 in 0.35 s from a workstation. `gong.nso.edu` and `gong2.nso.edu` share
  one IP (146.5.21.69), so a hostname mirror cannot help.
- All pipeline outage drills.
- The deployed data tree: `validate --url https://astrodavid10.github.io/sol-solar-viewer/data/
  --strict` → 0 failed, 0 warnings.

### Still NOT seen running

- **A real phone.** Everything above was a desktop browser at phone-sized viewports, which
  tests layout and media queries but NOT: device pixel ratio > 1 (footgun 16's regression
  signature is an overlay offset into the bottom-left quadrant, which only appears on DPR > 1),
  touch gestures, GPU memory limits, or cellular load time.
- **Kiosk mode, the attract loop and the QR flow** (`?kiosk=1`).
- **The reworked solar wind** at various zooms (footgun 20's fix).
- **Multi-channel texture switching** — the control renders, but switching was not exercised.
- Lighthouse mobile.

### How the browser verification was done — reuse this

`resize_window` does not change the viewport of a maximized Chrome window, so it cannot test
breakpoints. What works: navigate to the app's own origin, then replace the document with a
harness of same-origin iframes at fixed widths —

```js
document.documentElement.innerHTML = `<body><div style="display:flex;gap:12px">
  <iframe src="/" width="360" height="640"></iframe>
  <iframe src="/" width="390" height="844"></iframe>
  <iframe src="/" width="1100" height="760"></iframe>
</div></body>`;
```

Each iframe is a real viewport, so media queries respond correctly, and every breakpoint is
visible in ONE screenshot. Because they are same-origin, `f.contentDocument` then allows
measuring overlaps, clipped text (`scrollWidth > clientWidth`) and computed styles
numerically rather than by eye — which is how all four layout defects were pinned down.

**Dev server:** `yarn serve` → `localhost:8080`, or the LAN IP for a phone (`allowedHosts:
all`). Note: backgrounding `yarn serve` through a pipe (`| head`) kills it with SIGPIPE —
redirect to a file instead.

---

## 5. Suggested next steps

Ordered by value. The old blocker ("browser-verify the 3D view") is done; these are what is
left.

1. **Per-frame textures (plan workstream 1) — NOT STARTED, and the largest remaining item.**
   The sphere carries one Carrington texture (always the newest AIA image) while the field
   lines morph through 19 frames over 72 h, so scrubbing back three days shows historical
   field over today's photosphere with the terminator parked at today's sub-Earth longitude.
   The user chose **2048x1024 history frames for all five channels**, newest frame staying
   4096x2048: ~15 MB added to the published tree, 0 bytes for a guest who never scrubs.
   `src/three/sunSurface.ts:726` already anticipates it ("a future per-frame texture sequence
   gets the sweeping terminator for free"). Ship the pipeline half first and let a couple of
   runs warm the frame cache before the app half goes live.
   **Read first:** footgun 22 (channels are not interchangeable), footgun 31 (the CI seeding
   this depends on), and the GPU budget — 2048x1024 RGBA is 8 MB resident per texture.
2. **Unblock GONG.** The scheduled pipeline cannot build field lines at all (§3a). Published
   frames are a workstation build and go stale ~8 h after each hand-publish. A **self-hosted
   runner** at the planetarium is the only option fully under our control; asking NSO to
   allow-list GitHub's ranges is the cheapest if it works. A hostname mirror is already
   disproven.
3. **A real phone.** The one class of defect the iframe harness cannot see (§4). Load the live
   URL over cellular, check for the footgun-16 offset signature, and run Lighthouse.
4. **Design tiers 2-3** (plan workstream 2, partly done — see §8.7). The two highest-value
   pieces left: fat orbit lines (`Line2`, currently 0.33 CSS px on a DPR-3 phone) and taking
   gold out of region-label text (1.54:1 on the photosphere). Also: the desktop info panel is
   a 194 px window onto 1762 px of content at 1100x760 — it scrolls correctly, but the
   proportion is wrong.
5. **M-W9 — the 3D eruption layer.** M-W8 shipped the marks and cards; the remaining piece is
   drawing the CME itself (`src/three/cme.ts`). `events.json` already carries `dir_ecl` ready
   to use. See §6, and **read footgun 25 first** — the CME group must carry no quaternion.

---

## 6. Flare / CME 3D eruption — decision already made

A feasibility study was run (2026-08-23). Summary so it does not get re-litigated:

- **Real per-event BATSRUS/MHD is not viable.** One *scalar field*, one snapshot, medium
  resolution = **11.1 MB** (measured against PSI's public MAS archive); a usable CME state is
  ~89 MB/snapshot and a 6-hour eruption ~6 GB, against a 1.55 MB total PFSS product. There is
  no run API (CCMC Runs-on-Request is a human-mediated order form), it is retrospective
  (recent solar runs simulate 2011–2013 events), and CCMC's publication policy asks for
  developer contact and co-authorship consideration rather than granting redistribution.
- **Recommended instead:** a stylized parametric eruption driven by real DONKI numbers
  (~8 days of work). The events pipeline built today is step one of this.
- **Optional Phase 2:** one *generic* precomputed MHD eruption, traced offline to ~200
  fixed-topology field lines × 24 frames and baked into the existing `SOLPFRM1`-shaped format
  as a ~1.2 MB one-time static fixture — published once, not on the 4 h cadence.
- **Free win available now:** NOAA SWPC re-serves LASCO C2/C3 and CCOR-1/CCOR-2 coronagraph
  imagery **with CORS** (`ACAO: *`, real `Last-Modified`) — unlike SDO (footgun 6), these can
  be fetched, canvas-read and used as WebGL textures. SWPC also publishes its operational
  WSA-ENLIL run of the real CME as CORS-clean JPEGs: real MHD of the real event, ~93 KB/frame,
  zero engineering. See the Data sources section of `CLAUDE.md`.

---

## 7. Keeping this document current

At the end of a session that changed project state, update: the **Last updated** date, the
**status summary**, any milestone rows in §2, a new entry in §3, and — most importantly — move
items between the two halves of §4 as they get verified. If a session discovers a footgun, it
belongs in `CLAUDE.md`, not here; reference it from §3 by number.

---

## 8. Design audit — PARTLY IMPLEMENTED

**Status: §8.1-§8.4 are the audit and remain accurate as a specification. They are no longer
"proposal only" — some of it has shipped.** Read **§8.0 first**: it says what is done, what is
not, and which numbers below have been superseded. Everything else in §8 is preserved because
re-deriving it is expensive (§8.1 means re-reading an 18 MB PDF) and because the contrast
tables in §8.3 are measured, not estimated.

The original audit was written 2026-08-23 (first session) and cut off before its deliverable
(a design canvas) was built. The canvas was never built and, given the work has now started
landing directly in the app and is verifiable in a browser, probably should not be — §8.7.

### 8.0 What has actually SHIPPED — read this before trusting §8.3-§8.5

Second session, 2026-08-23. The user approved implementing **all three tiers**. Tier 0/1 are
partly done; tiers 2 and 3 are not started.

**Done, and verified in a browser:**

- **The layout half of Tier 1.** Title pill top-centre, one four-button stack top-right,
  `TopBar.vue` deleted, the wide grid down to three rows, `.solar-view-3d` given its own
  stacking context. See §3a.
- **The stat grid** is content-driven (`auto-fit / minmax(150px, 1fr)`) instead of
  breakpoint-driven — this fixed real text clipping at 390 px, and supersedes §8.3's
  "StatChip → stat tile" item only in layout, not in styling.
- **Label de-collision + leader lines** — `src/three/labelLayout.ts`. This is §8.4(c)'s leader
  line, arrived at from the opposite direction: §8.4 proposed offsetting chips radially so they
  *prefer the sky*; what shipped nudges them vertically only when they actually collide, and
  draws the leader then. **The collision case §8.4 did not anticipate** is two active regions
  near disk centre, which no radial offset separates — measured overlapping at every viewport.
  If the radial offset is added later, keep the de-collision pass: they solve different halves.
- **Fonts** — Highway Gothic Narrow (no license record) replaced by **Overpass** (SIL OFL 1.1),
  and the three orphaned `Roboto*.ttf` deleted. This supersedes §8.3's typography paragraph:
  the Pirulen / Magistral / Omnes stack is still unlicensed and still aspirational, but the
  *display* slot is now filled by a properly licensed FHWA-derived face rather than an
  unlicensed one. `--sol-font-*` tokens do not exist yet.

**NOT done — still exactly as specified:**

- **Tier 0's token set (§8.3).** `sol.less` still carries the OLD palette: `--sol-accent`
  `#ffc850`, `--sol-surface rgba(20,16,8,.92)`, and `--sol-panel-border` still gold. None of
  Spaceberry / Spacebubble / ember / violet has landed. The app is still off-brand.
- **`--sol-accent-rgb`.** Still absent, and still the single highest-leverage fix: the gold
  triplet `rgba(255, 200, 80, α)` is re-typed at **17 sites across 7 files**
  (`sol.less`, `common.less`, `LayerPanel.vue:215,286`,
  `TimeScrubber.vue:389,391,412,413,457,501`, `SolarView3D.vue`, `sol.vue`), so changing the
  accent today needs a find/replace on the RGB triplet *as well as* the variable — and
  `common.less` holds a dead copy that will poison exactly that search.
- **`common.less` cleanup.** Roughly half is still dead donor-project code
  (`--default-font-size`, `.fade-*`, `#modal-loading` — an un-tokenized duplicate of
  `.sol-spinner` — `.bottom-sheet`, `.pointer`, `.control-icon`, `.scrollable`), plus the
  off-palette periwinkle link color `#aec2fd`.
- **`KioskStatsPanel.vue`** still reads *"Exoplanet Sonification Kiosk — Usage Stats"* and
  carries an entire unrelated blue palette with zero `--sol-*` usage. It is reachable at
  `?kioskStats=1` on a now-PUBLIC site.
- **Tier 2 beyond the leader lines** — the `onDisk` flag from `project.ts` (one gate to drop,
  §8.4), the `.is-sky` / `.is-disk` adaptive plates, the dual-contrast marker dot, and taking
  gold out of `RegionLabel`'s text (**still 1.54:1 on the photosphere — the worst contrast in
  the app**).
- **Tier 3 entirely.** Orbits are still `LineBasicMaterial`, i.e. one DEVICE pixel — 0.33 CSS
  px on a DPR-3 phone. `orbitSampleVerticesAU()` in `planets.ts:71` still has zero callers.
  Read §8.4(e)'s two warnings before starting: `LineMaterial.resolution` must come from
  `drawingBufferWidth`, and `LineMaterial` needs `FLAT_SIDE` or WWT's reversed winding will
  cull it exactly as it culled the sun glow.
- **The design canvas (§8.5).** Not built, and arguably now obsolete: the app is live and
  every proposal in §8.3/§8.4 can be checked in a real browser at real viewports (§4). Build
  it only if you want a shareable artifact for review, not as a prerequisite.

**One new finding from the browser session:** at 1100x760 the desktop info panel is a 194 px
window onto 1762 px of content. It scrolls correctly (footgun 28's `min-height: 0` chain is
intact) — the proportion is simply wrong. The rail's `1fr auto auto` gives the info panel
whatever the layer panel and stats leave, which on a short window is very little.

### 8.1 Brand kit facts — `C:\Users\adavi\Downloads\Planetarium_Brand_Kit_V7.pdf`

4 pages, 792×612 pt (landscape Letter), 18 MB. Page 1 is the **master INTUITIVE Planetarium
brand**; pages 2–4 are show sub-brands (Our Place in Space, JWST, Black Holes).

**Colors (page 1, verbatim including the kit's own casing):**

| Name | Hex | RGB | CMYK |
|---|---|---|---|
| Spaceberry | `#0e0024` | 14 0 36 | 79 100 0 87 |
| Starliner | `#D9DDE2` | 217 221 226 | 4 2 0 11 |
| Spacebubble | `#202267` | 32 34 103 | 69 67 0 60 |
| Nova White | `#EAEBEF` | 234 235 239 | 2 2 0 6 |
| Midnight Cherry | `#64102d` | 100 16 45 | 0 84 55 61 |
| Light Speed White | `#f5f4f0` | 245 244 240 | 3 2 4 0 |
| Cosmaroon | `#821036` | 130 16 54 | 0 88 58 49 |
| Spaceship Gray | `#949baf` | 148 155 175 | 45 34 21 0 |

Stated principle, quoted: *"Spaceberry & Spacebubble are the planetarium's primary colors, with
the maroon shades as accents. The colors are chosen to best work in tandem with wider USSRC
branding, acting as an adapted version of the classic red and blue. Both colors have been
deepened and toned with purple to evoke the 'deep space' atmosphere of the planetarium.
**Spaceberry acts as the default Dark color rather than black.**"*

HSL, computed (useful for deriving tints — `#821036` and `#202267` are far too dark to be
accents on a dark ground, so any UI accent must be a lightness lift at held hue):
Spaceberry `hsl(263.3, 100%, 7.1%)` · Spacebubble `hsl(238.3, 52.6%, 26.5%)` ·
Midnight Cherry `hsl(339.3, 72.4%, 22.7%)` · Cosmaroon `hsl(340.0, 78.1%, 28.6%)` ·
Nova White `hsl(228, 13.5%, 92.7%)` · Light Speed White `hsl(48, 20%, 95.1%)` ·
Starliner `hsl(213.3, 13.4%, 86.9%)` · Spaceship Gray `hsl(224.4, 14.4%, 63.3%)`.

**Typography (page 1).** Three families, each shown Light / Light Italic, Book / Book Italic,
Bold / Bold Italic (Omnes is listed Light / Regular / Bold rather than Book):

- **Pirulen** — *"used in the planetarium wordmark and utilized for other titles and headings."*
  A wide squarish techno face.
- **Magistral** — *"the main typeface for written items from the planetarium, and is also
  utilized in headings, often with increased tracking."*
- **Omnes** — *"used in cases of large blocks of text at small sizes."*

**Wordmark rules (page 1), quoted/paraphrased:**

- Exists in two colors: **White** and **Spaceberry**. *"Except for B&W printing, spaceberry is
  an appropriate choice anywhere black could be chosen, and should be regarded as the default."*
- *"Outer Glow may be applied to the white version of the wordmark, though legibility is key and
  the effect should be slight."*
- *"The Intuitive Planetarium wordmark cannot exist where the USSRC logo does not."*
- *"The wordmark's primary rule is that it must always be legible."* On print items where the
  logo acts alone it must not be modified from the showcased versions; **recoloring or
  modifying it to integrate with a graphic or artwork by the planetarium team for marketing
  purposes IS appropriate** (see: Spectra Billboard).
- **Icon & Complete Logo:** the complete Logo = Icon + Wordmark. The Icon may appear in
  spaceberry, white, or colored. *"The icon can appear as one with the title, approximately
  where the ends of the two shooting stars are placed evenly following the line of the Intuitive
  'I', or to the left of the wordmark."*
- Wordmark forms shown: stacked two-line `INTUITIVE / PLANETARIUM` and single-line
  `INTUITIVE PLANETARIUM`; boxed versions on Spaceberry and on Spacebubble grounds. "INTUITIVE"
  is bold italic; "PLANETARIUM" is lighter with wider tracking.

**Design Elements (page 1, right column) — the brand's visual motifs:**

1. Four-point **sparkle stars**, white, varied sizes, scattered with small circles on a
   Spaceship-Gray/blue-gray rounded panel.
2. A **maroon gradient panel** (Cosmaroon → Midnight Cherry) with a *stepped/notched* rounded
   corner and pink pixel/square speckle.
3. A **hexagon tessellation** strip, gradient from near-black through Spaceberry to Spacebubble
   navy.

**Layout / grid convention of the kit itself** (worth copying — it is how the brand presents
information): section headers set in **letterspaced caps at roughly 0.2em+ tracking**
(`W o r d m a r k s`, `T y p o g r a p h y`, `C o l o r s`), each followed by a **thin
horizontal rule spanning the column**. Page ground is a light gray (~`#E3E5E9`) carrying faint
sparkle stars. IP wordmark top-left, USSRC lock-up top-right.

**Show sub-brands (pages 2–4) — not the master brand, but recorded so the PDF need not be
reopened:**

- *Our Place in Space* — design-element hexes `#dbd4db #abb0d4 #8d9cc9 #6e87bf` /
  `#335494 #243870 #1c264d #141436`. Type: **Gotham** (Book/Bold + italics); Gotham Bold full
  caps is the full title in the inline logo and the word "Space" in the standard logo.
  **Nimbus Sans Light at tracking value 350** for the "you are here" portion. Two logo
  variations × four color options (Full color with gradients whose epicenters sit at each
  planet, Earth's Moon and the Sun, plus a gradient overlay on the text; Partial color with
  planet gradients and white text; White; Black). The inline logo is the only use case for the
  complete inner-solar-system icon; default to the multi-line wordmark when possible.
- *JWST: The Story Unfolds* — design-element hexes `#f3ecae #e8ce73 #bf7f2e` /
  `#3262af #023789 #000e33`. Type: **Casanova Scotia** (must be hosted locally, no other
  variations) for "James Webb Space Telescope"; **Good Times Book** for "The story unfolds".
  Logo may appear white or Spaceberry; the white version may drop a black shadow. The Northrop
  Grumman Foundation logo must appear wherever this logo does.
- *Black Holes: Cosmic Abyss* — wordmark in White, Black, and a main colored version with a
  peach-to-white gradient; in every variation except Black the black-hole icon serving as the
  "o" is filled black. Every colorway except black also has a glowing option (the main colored
  wordmark has two glow colors); on dark backgrounds use the colored-aura variant
  `Black_Hole_Logo_[format]_Full_Color.png`. Prioritize the two-line standard version. Type:
  **Fino Sans** (Regular/Bold + italics); Fino Sans Bold is the title face except the first "O".

**Logo assets** — `C:\Data\IP-Logos\IP_Icon_1\` holds
`Main_Wordmarks_{Dark,White}_{,Centered_,Inline_,Left_Aligned_}Icon_1.{png,svg}` (note the odd
one out: `Main_Wordmarks_White_Left_Aligned_Icon_2-12.svg`). The app currently bundles
`src/assets/ip-wordmark-white.svg` — viewBox `0 0 160 160`, `id="Logos_Icon_1"`, group
`White_Icon_1`, single `.cls-1 { fill:#fff }`. Being square and named Icon_1, it is almost
certainly the **icon**, not the full wordmark, despite the filename. `src/assets/ip-ussrc.png`
is also present and `InfoModal.vue`'s `.im-logos` row already pairs the two.

### 8.2 What was audited, and what it showed

Read: `src/assets/sol.less`, `src/sol.vue`, `LayerPanel.vue`, `StatChip.vue`, `BrandMark.vue`,
`SpacecraftLabel.vue`, `RegionLabel.vue`, `TopBar.vue`, `TimeScrubber.vue`, `SunStats.vue`,
`InfoModal.vue` (styles), `src/three/spacecraftTrails.ts`, `fieldLines.ts`, `solarWind.ts`,
`sunGlow.ts`, `project.ts`, `src/data/pfss.ts`, `src/data/planets.ts`,
`public/data/ephem/spacecraft.json`.

**The current palette's three problems:**

1. **Everything is one temperature — warm.** `--sol-accent #ffc850` gold, `--sol-surface
   rgba(20,16,8,.92)` (a muddy olive-brown), `--sol-text #f5efe2` warm cream, `--sol-text-dim
   #b8b0a0` warm gray. Nothing can pop against neighbors of its own temperature. *This is the
   real answer to "the yellow on gray is just OK"* — the fix is to cool the neutrals, not to
   find a better yellow.
2. **The chrome wears the data's color.** `--sol-panel-border: 1px solid rgba(255,200,80,0.3)`
   is gold, so every rail panel is painted in the same hue as closed field loops. The chrome
   competes with the Sun instead of framing it.
3. **Nothing in the app uses the brand palette at all.** No Spaceberry, no Spacebubble, no
   Cosmaroon anywhere. The app is currently off-brand.

**In-scene colors inventoried (dome-shared — do NOT recolor):** `pfss.ts` manifest fallbacks
`closed [1,0.85,0.2]` ≈ `#FFD933`, `open_pos [0.3,0.55,1]` ≈ `#4C8CFF`, `open_neg [1,0.4,0.1]`
≈ `#FF6619` (render hints in the manifest can override these); `fieldLines.ts` `MONO_COLOR
[0.373,0.722,1.0]` = `#5FB8FF`; `solarWind.ts` `COLOR [0.70,0.83,1.0]` ≈ `#B3D4FF`;
`sunGlow.ts` radial stops `rgba(255,246,224,.30) → (255,232,175,.26) → (255,198,110,.11) →
(255,165,66,.035) → (255,150,50,0)`.

**Spacecraft colors** (`public/data/ephem/spacecraft.json`): psp `#ff8a3d`, solo `#5fb8ff`,
stereoa `#c77dff`, earth `#7de08a`. Note solo's color is *exactly* `--sol-accent2`, and
stereoa's violet collides with any violet chrome accent.

**Surprises — the load-bearing finds:**

- **Orbit lines are one DEVICE pixel.** `spacecraftTrails.ts` uses `LineBasicMaterial` and never
  sets `linewidth`; three.js ignores `linewidth` on WebGL regardless of value. On a DPR-3 phone
  each orbit is **0.33 CSS px**. `PAST_OPACITY 0.55` / `FUTURE_OPACITY 0.30` (already lifted
  once from 0.38/0.22) treat the symptom — no opacity can fix a sub-pixel line. **This is the
  root cause of "the planet orbits don't pop very well."**
- **three 0.185.1 already ships fat lines.** `node_modules/three/examples/jsm/lines/` has
  `Line2.js`, `LineGeometry.js`, `LineMaterial.js`, `LineSegments2.js`,
  `LineSegmentsGeometry.js`. **Nothing in `src/` imports them.** No new dependency needed.
- **Planet orbits are WWT's, not ours.** `layers.orbits` → `host.applySetting(["solarSystemOrbits",
  value])` (`SolarView3D.vue` ~line 720). The engine's orbit color is
  `this._orbitColor = Colors.get_white()` (`@wwtelescope/engine/src/index.js` ~line 37874) —
  internal per-`Orbit` state, **not exposed through the Settings API**. The app therefore cannot
  restyle, thicken or fade planet orbits at all. To make them pop you must set
  `solarSystemOrbits = false` permanently and draw your own.
- **`src/data/planets.ts` already exports `orbitSampleVerticesAU(b, segments = 160)` and nothing
  calls it.** It returns exactly the vertex list `LineGeometry.setPositions()` wants. The tool
  for drawing our own orbits is already written and unused.
- **Region-label text is gold on the photosphere: 1.54:1.** `RegionLabel` sets
  `.is-region .rl-text { color: var(--sol-accent) }` — the worst contrast in the app, and by
  definition it sits exactly where it is worst.
- **`project.ts` already computes everything an adaptive label needs.** It has the camera
  position, `sunAngle = asin(occluderRadius / cameraDistance)`, and the per-target test
  `acos(cosAngle) < sunAngle`, currently gated on `bodyDistance > cameraDistance` to produce
  `occluded`. **Dropping that gate yields an `onDisk` boolean for free.** Projecting
  `Vector3(0,0,0)` once per frame gives the Sun's screen center for leader-line angles.
- **BrandMark collision (new in 49e06cd).** `.sol-brand` is now `top: 0.75rem; left: 0.75rem;
  z-index: 6` on the stage — directly under `TopBar`'s own left-aligned "Sol / the Sun right
  now". Two brand marks stacked on the same left edge ~50 px apart. Also, the stage BrandMark
  appears *alone*, which the kit's "cannot exist where the USSRC logo does not" rule forbids.
- **`backdrop-filter` over the WebGL canvas is already proven here** — `SpacecraftLabel` uses
  `blur(4px)`, `TimeScrubber` `blur(6px)`.
- `StatChip`'s freshness dot (`#58d68d` / `#f0b429` / `#6b6b6b`) puts the actual time only in a
  `title` attribute — inaccessible on touch, and color is the sole carrier.
- `TimeScrubber` event marks already carry meaning by **shape** (diamond = flare, circle = CME)
  independent of color. Keep that; it satisfies the "not color alone" rule for free.

### 8.3 Decisions reached, with settled numbers

Proposed token set (all contrast-verified — see the table below):

```
--sol-bg              #000                                    UNCHANGED
--sol-surface         rgba(16, 6, 42, 0.90)   → #0E0526 over black, #281F3F over a white disk
--sol-surface-raised  rgba(32, 34, 103, 0.34) → #0A0B21       NEW (Spacebubble veil)
--sol-casing          #05010F                                 NEW (dark half of every mark)
--sol-text            #F5F4F0                                 Light Speed White, verbatim
--sol-text-dim        #A6AEC4                                 Spaceship Gray, L 63.3 → ~71%
--sol-text-quiet      #7E86A0                                 NEW
--sol-accent          #FFC850                                 UNCHANGED, usage narrowed
--sol-accent2         #5FB8FF                                 UNCHANGED
--sol-ember           #F34982      NEW  Cosmaroon, hue 340° held, L 28.6 → 62%, S 88%
--sol-violet          #7B7EE0      NEW  Spacebubble, hue 238° held, L 26.5 → 68%, S 62%
--sol-panel-border    1px solid rgba(148, 155, 175, 0.22)     was gold rgba(255,200,80,.3)
--sol-panel-shadow    0 10px 30px rgba(0,0,0,.65), inset 0 1px 0 rgba(245,244,240,.07)
--sol-panel-radius    14px                                    was 12px
--sol-panel-pad       1rem                                    UNCHANGED
--sol-rail-gutter     0.75rem                                 UNCHANGED
--sol-label-bg        rgba(9, 2, 24, 0.86)    → #080215 over black, #241E33 over a white disk
```

`--sol-bg` stays `#000` deliberately: it must match the WebGL sky exactly or a seam appears at
the canvas edge. WWT owns the sky color and the canvas is shared, so changing the three.js
clear color is risky — flagged as **not verified feasible**.

`--sol-panel-border` is the single highest-leverage line in the whole proposal: one token takes
gold off every rail panel at once.

`--sol-panel-shadow`'s `inset` hairline is the "modern/sleek" move — a lit top edge rather than a
drawn box. A comma list still fits in one token, so no component needs editing.

Alternate lifts computed, if the chosen values need tuning (contrast is vs `#0E0526`):
ember L55 `#f1276b` 4.91 · L58 `#f23674` 5.20 · **L62 `#f34982` 5.70** · L66 `#f55c8f` 6.37 ·
L70 `#f66f9c` 7.18. violet L62 `#6265da` 4.11 · **L68 `#7b7ee0` 5.53** · L74 `#9496e6` 7.27.

**Measured contrast (WCAG 2.1 relative luminance), computed not estimated:**

| on | text `#F5F4F0` | dim `#A6AEC4` | quiet `#7E86A0` | gold `#FFC850` | blue `#5FB8FF` | ember `#F34982` | violet `#7B7EE0` |
|---|---|---|---|---|---|---|---|
| `#0E0526` panel over black | 17.86 | 8.87 | 5.43 | 12.76 | 9.16 | 5.70 | 5.53 |
| `#281F3F` panel over white disk | 14.05 | 6.98 | 4.27 | 10.04 | 7.21 | 4.48 | 4.35 |
| `#080215` chip over black | 18.53 | 9.20 | 5.64 | 13.23 | 9.50 | 5.91 | 5.73 |
| `#241E33` chip over white disk | 14.58 | 7.24 | 4.44 | 10.42 | 7.48 | 4.65 | 4.51 |
| `#000` bare sky | 19.08 | 9.47 | 5.80 | 13.63 | 9.79 | 6.09 | 5.90 |
| **`#FFF` bare disk, NO plate** | **1.10** | **2.22** | 3.62 | **1.54** | **2.15** | 3.45 | 3.56 |

The last row is the whole argument: **nothing survives naked on the photosphere.** Legibility
over the Sun must come from a plate or a casing, never from a color choice. `--sol-text-quiet`
is the floor of the system — keep it to 12 px+ short strings, never a sentence.

**Ember guard-rail.** Ember sits at hue 340°; the inbound-field orange is at 20° and the X-flare
marker `#ff5f4d` at 6° — under deuteranopia the three converge. Restrict ember to exactly three
places, never adjacent to data and never a small dot: the 1 px gradient rule under the top bar,
the section-header rules in the rail, and the kiosk "Take it with you" pill. Never a status,
never a severity, never a legend swatch.

**Typography decision.** Pirulen for display (**≥ 20 px only** — a wide techno face muddies
below that), Magistral for all UI including section heads at `0.22em` tracking, Omnes for body
copy at small sizes. **None of the three is on Google Fonts, and licensing is blocking:** Pirulen
(Typodermic) is free for personal use only; Magistral (ParaType) and Omnes (Darden / Adobe
Fonts) need webfont licenses. The app already bundles local TTFs so the mechanism exists — the
rights do not. Ship this stack meanwhile (it is also what the drafted artboards are drawn in):

```
--sol-font-display: "Pirulen", "Chakra Petch", "Highway Gothic Narrow", sans-serif;
--sol-font-ui:      "Magistral", "Barlow", system-ui, sans-serif;
--sol-font-body:    "Omnes", "Nunito Sans", system-ui, sans-serif;
```

Add `font-variant-numeric: tabular-nums` to every live number so stat values stop jittering as
they refresh. Adopt the kit's own section-header convention in the rail — letterspaced caps at
`0.22em` plus a thin rule under them.

**BrandMark recommendation.** Desktop: move it to the **bottom of the rail** as a proper IP +
USSRC credit lockup — off the canvas entirely, so it never fights the Sun, never needs a halo,
and satisfies the kit's pairing rule. Phone: **bottom-left of the stage** (where it was before
49e06cd), since the top-left is where TopBar's wordmark already lives. Keep it over the canvas
with dual-contrast treatment: raise the existing radial halo to
`radial-gradient(circle, rgba(5,1,15,0.55) 0%, rgba(5,1,15,0) 72%)` and add a light rim
`drop-shadow(0 0 1px rgba(245,244,240,0.35))` so the white glyph survives the bright disk. The
kit explicitly permits a slight outer glow on the white wordmark — the light rim is exactly
that, used at legibility strength.

### 8.4 The technique for labels and orbits — "adaptive casing"

One rule, applied everywhere: **every mark carries a dark contour inside a light edge, and DOM
labels additionally switch to a solid plate when `project.ts` reports they are over the disk.**
The dark half wins over the bright photosphere; the light half wins over the black sky; one
treatment therefore works on both backgrounds, which no single color can.

**(a) Dual-contrast marker dot** — replaces `.sl-dot`'s current 8 px + `box-shadow: 0 0 6px
currentColor`, a colored glow that vanishes over the photosphere:

```css
width: 11px; height: 11px; border-radius: 50%; background: <mission color>;
box-shadow:
  0 0 0 2px   rgba(5,1,15,0.92),        /* dark contour — wins on the bright disk */
  0 0 0 3.5px rgba(245,244,240,0.62),   /* light ring   — wins on the black sky   */
  0 0 12px 1px <mission color @ 55%>;  /* glow, cosmetic only */
```

**(b) Adaptive label plate** — `project.ts` returns `onDisk` per target (see §8.2):

```css
.is-sky  { background: rgba(9,2,24,0.72); backdrop-filter: blur(10px) saturate(1.15);
           border: 1px solid rgba(245,244,240,0.28);
           box-shadow: 0 0 0 1px rgba(5,1,15,0.8), 0 6px 18px rgba(0,0,0,0.55); }
.is-disk { background: rgba(9,2,24,0.92); border-color: rgba(245,244,240,0.42);
           box-shadow: 0 0 0 1.5px rgba(5,1,15,0.95), 0 2px 10px rgba(0,0,0,0.7);
           /* NO backdrop-filter — a solid plate doesn't need it, and blur is the most
              expensive thing in the overlay at 20 Hz on a phone */ }
/* both states */
text-shadow: 0 0 3px rgba(5,1,15,0.95), 0 1px 2px rgba(5,1,15,0.9);
```

Name 13 px / 0.8125rem / 700; detail 11 px / 500 / `#A6AEC4`. Selected state:
`border-color: var(--sol-accent)` — gold stays the app's word for "on".

**(c) Leader line, so labels prefer the sky.** Offset the chip radially outward from the
projected Sun center by ~26 px and draw a 1.5 px leader from marker to chip:

```css
.sl-leader { position: absolute; height: 1.5px; transform-origin: 0 50%;
  background: linear-gradient(90deg, rgba(245,244,240,0.7), rgba(245,244,240,0.28));
  filter: drop-shadow(0 0 1.5px rgba(5,1,15,0.95)); }
```

Angle = `Math.atan2(y - sunCy, x - sunCx)`. Two wins at once: chips stop sitting on the disk in
most framings, and the marker stays on the true position while only the text moves off it.

**(d) `RegionLabel` — take the gold out of the text.** Gold text on the photosphere is 1.54:1
today. Text goes `#F5F4F0` (14.58:1 on the on-disk plate); gold stays in the **ring only**:
12 px, `2px solid #FFC850`, `box-shadow: 0 0 0 1.5px rgba(5,1,15,0.9), 0 0 0 3px
rgba(255,200,80,0.22)`. Color is then not the sole carrier — ring = active region, ⊕ glyph =
sub-Earth.

**(e) Orbits — replace `LineBasicMaterial` with `Line2` / `LineGeometry` / `LineMaterial`**
(already in three 0.185.1, no new dependency). Two-pass casing per arc, the cartographic
road-casing trick and the same dual-contrast idea as the labels:

| pass | width (screen px) | color | opacity | notes |
|---|---|---|---|---|
| casing, past | 5.0 | `#05010F` | 0.55 | `renderOrder` 10 |
| core, past | 2.0 | mission color | 0.90 | `renderOrder` 11; vertex-color ramp 0.35 → 1.0 toward "now" |
| casing, future | 4.0 | `#05010F` | 0.40 | |
| core, future | 1.6 | mission color | 0.55 | `dashed: true` |

`depthWrite: false` on all four.

> **CRITICAL — ties to footgun 16.** `LineMaterial.resolution` MUST be set from
> `gl.drawingBufferWidth` / `drawingBufferHeight`, **not** `gl.canvas.width/height`. The vendored
> `three-wwt` shim reports the canvas in CSS px on DPR > 1 screens, so feeding it `canvas.width`
> makes every line width wrong by the device pixel ratio — a 2 px line renders 6 px on a DPR-3
> phone. Set it where the viewport is restored in `setupThreeWWT.ts`, and again on every resize.

Dash caveat: `LineMaterial`'s `dashSize`/`gapSize` are world units scaled by `dashScale`, so the
existing `0.012 / 0.012` must be **retuned, not copied**.

**(f) Planet orbits.** Set `solarSystemOrbits = false` permanently and draw our own from the
already-present `orbitSampleVerticesAU()`: casing 3.0 px `#05010F` @ 0.45 + core 1.4 px
`#7B7EE0` (brand violet) @ 0.42. Cool violet reads as reference furniture, clearly not one of
the four physics colors. **Caution:** `#7B7EE0` vs STEREO-A's `#c77dff` — keep planet orbits
well below spacecraft-trail brightness so the two never read as the same class.

**(g) In-scene physics colors are NOT changed.** Gold (closed loops), blue (outbound open),
orange (inbound open) and pale blue-white (solar wind) are the dome show's legend, and a guest
may see the dome an hour before the phone. The apparent lift comes entirely from taking gold
*out of the chrome*, which raises the field lines' perceived saturation without touching a
single data value.

**Component decisions already made:**

- **LayerPanel** — switch off-track `rgba(148,155,175,0.20)`, on-track `rgba(255,200,80,0.55)`,
  knob `#F5F4F0`. Segments stay 44 px; border `rgba(148,155,175,0.22)`; on-state
  `border-color #FFC850`, `background rgba(255,200,80,0.14)`, `color #F5F4F0`. Add a 14 px
  inline-SVG glyph per layer row (loops / streaming dots / craft / ring / halo) for non-color
  redundancy at 90-second glance. Do **not** add a left-border accent bar — that is an AI-slop
  trope the design skill calls out.
- **StatChip → stat tile** — larger value with `tabular-nums`; label in Magistral small caps at
  `0.08em`; replace the silent `title`-only freshness dot with dot **plus** a visible age string
  ("2 min") in `--sol-text-quiet`, because `title` is inaccessible on touch.
- **TimeScrubber** — track 4 px → 6 px; thumb 20 px → 22 px with a dark casing ring
  (`border: 2px solid rgba(5,1,15,0.85)` + `box-shadow: 0 0 0 1px rgba(245,244,240,0.35)`);
  loaded ticks gold. Keep the existing shape language for event marks.

### 8.5 What remains, in order

1. **Build the design canvas** via the `design` skill. Planned artboards:
   `Main.dc.html` = Desktop 65/35 (1440×900) · `Palette.dc.html` (1100×1430, **already written**
   — see §8.6 for the path) · `Phone.dc.html` (390×844) · `Labels.dc.html` (~1240×1000, the key
   artboard: the same label and orbit rendered over a black strip and a bright-disk strip,
   before/after, with the anatomy spec beside it) · `Components.dc.html` (~980×1200: layer panel,
   stat tile, scrubber) · `Rationale.dc.html` (~980×1200).
   Planned `canvas.json`: row 1 at y=0 — Palette x=0 w=1100 h=1430, Main x=1220 w=1440 h=900;
   row 2 at y≈1560 — Phone x=0, Labels x=550; row 3 — Components + Rationale. Keep ≥80 px
   between frames in a row and ≥120 px between rows. `launch: {"view": "canvas"}`.
2. Seed with `node "<design skill base dir>/seed-canvas.mjs" --template <base>/payload.template.html
   --out sol-visual-revision.html --title "Sol Visual Revision" --artboard … --canvas canvas.json`,
   then `--check`, then publish with the `Artifact` tool at `contract: "0.1.31"`.
3. **Deliberate departures to write up on the Rationale artboard:** (i) `--sol-bg` stays `#000`
   rather than Spaceberry, because it must match the WebGL sky; (ii) gold and the in-scene
   physics colors are kept even though they are not brand colors, because they are dome-show
   semantics; (iii) the aurora callout stays green for the same reason; (iv) ember is a *lifted*
   Cosmaroon, not Cosmaroon itself, because `#821036` at 28.6% lightness cannot function as an
   accent on a dark ground.
4. **Open question, explicitly not verified:** whether `backdrop-filter: blur(10px)` on up to ~6
   labels at 20 Hz is affordable on a mid-range phone. Measure before shipping the `.is-sky`
   variant; the `.is-disk` solid plate is the safe fallback for both states.
5. Nothing in the app has been modified, and nothing should be — this is a proposal.

### 8.6 Environment notes — things that did not work

- **Bash truncates very long commands.** Two attempts to write a ~20 KB artboard via heredoc
  failed with ``unexpected EOF while looking for matching `'`` at a line *inside* the heredoc:
  the command was cut mid-content, leaving an unterminated quote. A short heredoc works fine, so
  it is length, not quoting. **Write artboards with the `Write` tool.**
- **`Read` on the PDF fails** — "pdftoppm is not installed". Use `pdftotext -layout` (present at
  `/mingw64/bin/pdftotext`, v4.00) for text, and **PyMuPDF** via `C:\Users\adavi\anaconda3\python`
  (`import fitz; doc[i].get_pixmap(dpi=90).save(...)`, and `get_pixmap(clip=fitz.Rect(...),
  dpi=200)` for crops) to render pages to PNG for visual reading. `pypdf` / `PyPDF2` are not
  installed.
- **Scratchpad in use** —
  `C:\Users\adavi\AppData\Local\Temp\claude\C--Users-adavi-Documents-DataStories-sol\95b79b8d-e8ae-41f6-8cd0-abcc88fa8ce0\scratchpad\`
  holds `brandkit.txt` (pdftotext output), `bk_00..bk_03.png` (rendered pages),
  `bk0_design.png` / `bk0_wordmarks.png` (crops), `cr.py` (the contrast + HSL calculator that
  produced every number above — reusable), and `sol-design\Palette.dc.html` (the finished
  artboard) plus `sol-design\_helmet.txt` (the shared `<helmet>` block: a Google Fonts link for
  Chakra Petch / Barlow / Nunito Sans and the `.disp` / `.bod` / `.sec` / `.rule` / `.mono`
  utility classes the artboards use). Temp directories are not durable — copy anything worth
  keeping before relying on it.
