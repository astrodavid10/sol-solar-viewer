# Sol — work ledger

**What this is.** A task-shaped view of the work, so a fresh session (human or Claude) can
pick up at an exact point. `HANDOFF.md` is the short status doc (session history to 2026-09-30
is in `docs/handoff-archive/`); "what changed and why" goes in commit messages. This file
answers "what is in flight and what is next".

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

**Last updated:** 2026-10-05 (twenty-fourth session — plan phases 1-4 done except T38 (needs a visible tab) and seam 2 (deferred); phases 5.3, 6 and 7 remain)

---

## Status

Rows are listed in **execution order**. IDs are stable names, not positions — T11/T12 sit
where they do because they are live guest-facing defects reported by a real reviewer, which
the plan says outrank documentation work.

**Since 2026-10-04 the execution order is set by [`docs/PLAN-2026-10.md`](docs/PLAN-2026-10.md)**
(the 2026-10-04 audit, 31 findings, seven phases). Rows T24-T46 are its tasks and come first;
older rows it absorbs say which phase owns them. Plan phase → rows: 1 = T24-T31, 2 = T32-T38,
3 = T4, 4 = T6 (vitest) / T39 / T40 / T3 / T12 / T11, 5 = T41-T43, 6 = T6 (Playwright) / T8 / T7,
7 = T44-T46 / T15 / T13 / T14 / T16 / T17 / T9.

| # | Task | Status | Commit | Note |
|---|------|--------|--------|------|
| T24 | Per-channel texture age ceiling; drop stale layers; per-layer status (plan 1.1) | DONE | `f5a1363`+`38c1d66` | live 2026-10-05 00:50Z: HMIIC/HMIB dropped (latest_* 320 h old), texture `degraded` naming them; validator per-layer age; panel + attract offer only published channels |
| T25 | Save the CI cache on red runs (plan 1.2) | DONE | `0fb390d` | restore/save split; saved on red runs 37247690602, 37248331473, 37248930980 |
| T26 | Validator crash isolation per product (plan 1.3) | DONE | `38c1d66` | test_validator_isolation fails 4/7 without the fix |
| T27 | Region position bounds for srs.txt (plan 1.4) | DONE | `38c1d66` | parse_srs bounds + SrsFormatError; cached srs.txt <= 2 days |
| T28 | Upstream contract errors + DONKI cache age limit (plan 1.5) | DONE | `38c1d66` | UpstreamContractError (`UPSTREAM MOVED:`); DONKI cache <= 24 h; events.json `fetched_iso` |
| T29 | Pipeline loose ends (plan 1.6) | DONE | `7a2bc4e` | no future GONG dirs, cache prune, walker test, runbook pull |
| T30 | Quieter, smarter GitHub signal + mirror heartbeat + freshness backstop dispatch (plan 1.7) | DONE | `0fb390d`+`7a2bc4e` | Verdict reason keys; comment-on-change verified (#2 got one comment per change); mirror heartbeat + backstop dispatch in freshness.yml |
| T31 | Repo-scoped mirror PAT + catch-up dispatch (plan 1.8) | DONE (code) — token pending | `275b2d2` | user to mint a fine-grained PAT (contents+actions write, this repo) into `%LOCALAPPDATA%\sol-gong-mirror\token`; until then `gh auth token` fallback with WARN |
| T32 | `docs/CONTRACT.md` (plan 2.0) | DONE | `c232220`+`965609c` | docs/CONTRACT.md; dead plan refs removed |
| T33 | No silent hang: overall timeout, disk still, Try again (plan 2.1) | DONE | `965609c` | 20 s overall timeout; disk_still (additive); failure cards with today's Sun + Try again; chunk retry once. Browser-verified |
| T34 | Texture loads: latest request wins (plan 2.2) | DONE | `582df6f` | src/three/latestRequest.ts; race itself needs vitest (4.0) or a slow network |
| T35 | Hi-res map only when the disk is big enough (plan 2.3) | DONE | `3987124` | ?hires auto: wide + field lines loaded + disk >= 1600 px (off < 1300). Gate verified 349/1550/1788/1550/544 px. Mipmaps kept (deviation, see commit) |
| T36 | WebGL context-loss cover (plan 2.4) | DONE | `cb9c790` | cover + one auto-reload per minute; solDebug.loseContext(). Browser-verified both paths |
| T37 | Kiosk take-home URL (plan 2.5) | DONE | `0f36049` | kioskHomeUrl set; QR refused for localhost/private hosts |
| T38 | WWT render loop on requestAnimationFrame, measured (plan 2.6) | CLOSED — not needed | — | engine-pinia already renders on requestAnimationFrame (Component.vue: startInternalRenderLoop false + its own rAF loop calling renderOneFrame). Measured 2026-10-05 in a hidden tab: 0 engine setTimeout(10) calls and 0 renders in 4 s, i.e. no timer loop. Audit finding #25 read the engine's own loop, which this app never starts |
| T39 | Split SolarView3D.vue: cards, then time cluster (plan 4.1) | PARTIAL — seam 1 DONE | `17f8c94` | cards/copy -> src/data/cards.ts. Seam 2 deferred: T3 rewrote the time cluster in place and it is now small |
| T40 | Held PFSS frames on the timeline (plan 4.2) | DONE | `cf22fdd` | axis on slot targets; hollow held ticks; 'no new magnetogram since' note. Browser-verified |
| T41 | Hot Corona stops dropping out: fixed-res limb fit + carry-forward (plan 5.1) | DONE | `62a6559`+`112bc43` | carry-forward + limb band centred per channel (user-approved 2026-10-05; tol still 3%). Run 37298265012: 0171/0304/0193 all passed, live has 3 layers; issue #2 not re-commented (reasons unchanged) |
| T42 | Current HMI imagery from JSOC (plan 5.2) | DONE | `f0db3a5` | JSOC dated tree; same product as GSFC's HMI browse (corr 0.999/1.000 at 2026-09-24 11:00:00). Run 37301822199 green, 5 layers live, issue #2 auto-closed; footgun 59 |
| T43 | `_single` as filtered `cmd_all`; `pipeline/index.py` (plan 5.3) | TODO | — |  |
| T44 | Share preview + service worker (plan 7.1) | TODO | — |  |
| T45 | Build stack bumps + Vite spike (plan 7.2) | TODO | — |  |
| T46 | CI supply chain: SHA pins, lockfile (plan 7.3) | TODO | — |  |
| T0 | Stand up this ledger | DONE | `3108484` | 18 rows incl. Alex's review |
| T1 | Republish PFSS from the workstation | DONE, now a FALLBACK | `4ee53fc`+ | 10 hand-publishes 2026-08-25 .. 09-02; **no longer recurring** since T2 went live — `PFSS-UPDATE.md` is the fallback for a mirror outage. **11th on 2026-09-09** (`ac6b53d`, 19/19 slots, all six products `ok`) — needed because the relay's CI *read* path went stale, not the mirror: see **T22**. **12th on 2026-09-15** (`8d7f91d`, 19/19 slots, all six products `ok`) — the mirror itself was down: see note below. **13th on 2026-09-21** (`77f5e24`, 19/19 slots, all six products `ok`) — the mirror was down again, same interactive-logon cause, now footgun 56. **14th on 2026-09-22** (`ef1a1e3`, 19/19 slots, all six products `ok`) — mirror down ~44 h again; 0171 hi-res needed a second texture-only run (footgun 57). **15th on 2026-09-30** (`ef9d547`, 19/19 slots, all six products `ok`) — mirror down ~4.5 days; DONKI's API moved (footgun 58, `1bc2081`) |
| T2 | Land the GONG relay (Option D, workstation mirror) | DONE | `8650fee`+`85e626c` | LIVE 2026-09-02: `gong-cache` fed hourly by `SolGongMirror`; CI traced 19/19 in run 33663715169 (dry) and **published** in 33664961891 (`gh-pages` `ca5426f`, Verdict ok, issue #1 closed). Formal "scheduled" confirmation = the next cron tick |
| T3 | Honest clock when PFSS is stale (one playhead, union of windows) | DONE | `b9f199c` | hold slots to the newest texture slot; 'now' only < 6 h; chips on atNewestSlot; refresh chip after 30 min hidden. Browser-verified vs a 48 h stale manifest |
| T11 | Timeline marks: a key, and targets you can hit | DONE | `0378e07` | 44 px hit areas split at midpoints in clusters; '?' key. Phone feel is T8 |
| T12 | Explainer copy pass | DONE | `a7f6adc` | copy approved by the user 2026-10-05; aurora both hemispheres, flare vs eruption (CME) once, local time everywhere (UTC second on event cards), stale storm banner guard |
| T4 | Reconcile CLAUDE.md / HANDOFF.md with the shipped tree | DONE | `0830ac0` | plan phase 3: CLAUDE.md 71K -> 40K chars, HANDOFF 206K -> 48K, TASKS 104K -> 41K; history archived verbatim under docs/ |
| T6 | First real app tests | PARTIAL — vitest DONE | `9db561b`+`17f8c94` | 33 app tests (winding/frame from the engine's own matrices, labels, manifest, cards, QR guard, latest-request). Playwright + cmd_all contract test are plan 6.1 |
| T13 | Tap a live value to open its explainer | TODO | — | **AF** |
| T16 | Earth on the textured side (verify, then frame) | TODO | — | **AF** — data proven correct, app path unverified |
| T15 | Zoom out to Earth's orbit; our own planet orbits, bold + labelled | PARTIAL — **(c) DONE** | `c7b3438` (c) | **AF** + HANDOFF §8.4(f). Planet **labels** landed and browser-verified 2026-09-03 against WWT's own rings, then sat UNCOMMITTED until 2026-09-11, when they were re-verified and committed. (a) `MAX_ZOOM` and (b) our own orbit lines still TODO |
| T14 | Press-and-hold fine scrub on the timeline | TODO | — | **AF** — new gesture |
| T7 | Accessibility pass (`prefers-reduced-motion`, zoom, focus) | TODO | — | |
| T8 | Phone verification | BLOCKED | — | needs the Chrome extension connected + a handset |
| T9 | Decide the eruption layer | PARTIAL — naming decided | `a7f6adc` | user chose 'Eruption (CME)' as the guest term (2026-10-05). Whether to turn the layer on (ERUPTIONS_ENABLED) is still open |
| T10 | Dead-code cleanup in `sdoCatalog.ts` | TODO | — | monolith splits deferred, see below |
| T17 | Zoom out to the heliosphere, with the Voyagers | TODO | — | **AF** — largest new feature; needs scoping |
| T18 | A vertical reel of the 72 h field | DONE | — | `scripts/render_reel.py`; asked for outside the plan |
| T19 | Near-side detail maps at full SDO resolution | PARKED | `8650fee`+ | pipeline DONE; app LOD + cold fill next; parked while T20 lands |
| T21 | Review fixes, second batch (items 9-13: Vuetify out, texture gate, T5 wiring, token leaks, `max_frames`) | DONE | `30d7ec1`..`5c0d334` | all five landed; `build.yml` green on `main` for the first time (run 33664390163, app + pipeline jobs) after one deflake; T5 closed by it |
| T5 | Wire existing checks into CI | DONE | `095122f` | folded into T21 item 11: `build.yml` runs on push (lint, typecheck, build, label check, names check, pyflakes, pytest); `app-deploy` typechecks + `--immutable` |
| T20 | Review fixes, 2026-09-02 (eight items from the full code review) | DONE | `dc6aa22`..`68bb960` | wind-tz bug, per-product validate, `seed_regions`, notify + freshness, field-line hole, texture GPU leak; republished `85230e5`; dry-run + freshness verified. **Every scheduled `data` run is now RED while pfss is stale** — by design, until T2 |
| T22 | The relay's CI read path serves a FROZEN view of `gong-cache` | TODO | — | mirror + branch are fine; runners get a truncated snapshot. Cause of the 2026-09-09 republish |
| T23 | Desktop seam + info copy (asked for 2026-09-11, outside the plan) | DONE | `e741321` + `bcd35c9` | scrubber on the rail gutter with its bottom on the stats panel's; "What am I looking at?" in plain sentences |

**AF** = from Alex's review, 2026-08-24 (see "Alex's review" at the foot of this file for the
raw items and how each was mapped).

**Deferred, deliberately** — recorded so a later session does not re-find the seams:
splitting `src/components/SolarView3D.vue` (2,764 lines: stage lifecycle · layer construction ·
projection + markers · card content) and `pipeline/cli.py` (1,475 lines: argparse · per-stage
orchestration · failure policy). Behavior-preserving, one seam per commit, browser-verified
between each. Not in this round.

---

## Task detail

Detail for DONE tasks (and T1's run diaries) was moved verbatim to
[`docs/tasks-archive.md`](docs/tasks-archive.md) on 2026-10-05; each moved section leaves a
one-line pointer. Hand-publishes are one line each in
[`docs/republish-log.md`](docs/republish-log.md).

### T0 — Stand up this ledger

Detail moved verbatim to [docs/tasks-archive.md#t0](docs/tasks-archive.md#t0).

---

### T1 — Republish PFSS from this workstation

Detail moved verbatim to [docs/tasks-archive.md#t1](docs/tasks-archive.md#t1).

---

### T2 — Land the GONG relay: Option D, the workstation mirror  *(DONE 2026-09-02)*

Detail moved verbatim to [docs/tasks-archive.md#t2](docs/tasks-archive.md#t2).

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

Detail moved verbatim to [docs/tasks-archive.md#t5](docs/tasks-archive.md#t5).

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

**(c) landed 2026-09-03** — labels only; (a) and (b) are untouched, so this row stays open.

What shipped: `SOLAR_SYSTEM_BODIES` got its first real consumer. Eight chips, gated on
`layers.orbits`, built once in `buildPlanetChips()` and projected by `updatePlanets()` on the
same `moved || PROJECT_MS` cadence as the spacecraft — reusing `SpacecraftLabel.vue` outright
rather than copying its styles, so there is one chip plate to keep legible over the limb
instead of two that drift apart. Positions come from our own Kepler elements, not the engine's
ephemeris, so the anchors sit in the same right-handed ecliptic frame as everything else
(footgun 47). Clicking one opens the shared card slot; `describeOrbitPeriod` writes its compare
line, deliberately NOT `describeDistance`, which from a planet's point of view would tell
Mercury it is "closer to the Sun than Mercury".

Two things worth knowing, both found by building it:

- **Earth was already labelled.** `ephem/spacecraft.json` carries Earth, so with both layers on
  there were two Earth chips on one point. `updatePlanets` suppresses the planet one while the
  spacecraft layer is providing its own, rather than dropping Earth from the planet list, so
  turning the spacecraft layer off still leaves Earth named on its ring. Verified both ways.
- **The `layers.spacecraft` watcher would have closed a planet's card.** It dismissed any
  selection that was not a SURFACE id, which was right while spacecraft were the only bodies
  with chips. A planet is a body and not a surface, so it needed the second test.

On this row's own stride-budget caution: five chips stacked on one point separate to exactly
the 46 px stride, planets interleaving with a spacecraft in one combined pass, `x` untouched
and leaders drawn. Seven chips were on screen at once during verification with no crowding.
That is not a proof that it scales — the worst case is many chips inside one 96 px x-group,
where the spread is `(n-1) * 46` px and would run off a phone — but the geometry works against
it: planets bunch up in x only when the ecliptic is near edge-on, and edge-on is exactly when
they spread out horizontally into SEPARATE groups. Re-check it if (a) raises `MAX_ZOOM`, which
is what would put more planets on screen together.

Verified in a browser at `distanceAu: 1.11` (the current `MAX_ZOOM`): Mercury, Venus and Earth
chips each sit **on** the ring WWT itself draws for them, which per the memory note is the only
check in this scene independent of the app's own frame. Distances cross-check too — the planet
Earth chip reads `217 R☉ · 1.01 AU`, the same as the Horizons-baked ephemeris chip, and an
independent Kepler solve in the page gave 1.0086 AU. From Mars outward a planet is off-frustum
at every zoom a guest can reach, so those chips are built and stay invisible; that is `MAX_ZOOM`
doing what its comment says, i.e. part (a)'s problem, not a label bug.

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

Detail moved verbatim to [docs/tasks-archive.md#t18](docs/tasks-archive.md#t18).

---

### T19 — Near-side detail maps at full SDO resolution  *(IN PROGRESS)*

Asked for directly: the 19 history slots are 2048x1024 while SDO's browse product is 4096x4096,
so the window carries a quarter of the linear detail it could. (The full plan lived outside
the repo and no longer exists; this section is the surviving record of it.)

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

### T20 — Review fixes, 2026-09-02  *(DONE)*

Detail moved verbatim to [docs/tasks-archive.md#t20](docs/tasks-archive.md#t20).

---

### T21 — Review fixes, second batch (items 9-13)  *(DONE)*

Detail moved verbatim to [docs/tasks-archive.md#t21](docs/tasks-archive.md#t21).

---

### T22 — The relay's CI read path serves a FROZEN view of `gong-cache`

**Still open.** On 2026-09-09 CI's GONG listings through the relay were byte-identical across
four runs spanning 17 h (slots decaying 15/19 → 10/19) while the mirror, the `gong-cache` branch
and a workstation scrape were all current. The read path through `raw.githubusercontent.com`
(Fastly, `max-age=300`) is the suspect; the mechanism is not established. Options: cache-bust in
`sources/gong.py:_relay`, read via the GitHub contents API, or deploy the Cloudflare Worker.
**Definition of done:** a *scheduled* `data` run reports `slots: 19/19` and `pfss ok` without a
hand-publish, and the mechanism is written down, measured rather than assumed. Every later
"frozen" signature so far was a mirror outage instead (footgun 56): check the mirror's log
directory first. Full diary, including T1 runs 12-15: [docs/tasks-archive.md#t22](docs/tasks-archive.md#t22).

---

### T23 — Desktop seam + info copy (asked for 2026-09-11)

Detail moved verbatim to [docs/tasks-archive.md#t23](docs/tasks-archive.md#t23).

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
