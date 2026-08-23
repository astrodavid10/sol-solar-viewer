# Sol — project handoff & status

**Living document.** Update it at the end of any session that changes project state. It exists
so a fresh session (human or Claude) can pick the work up without re-deriving context.

- **Last updated:** 2026-08-23
- **Repo:** `github.com/astrodavid10/sol-solar-viewer` (**private**; GitHub Actions currently
  **disabled at the repo level** — see §5 step 4)
- **Status summary:** feature-complete against the v1 plan, building clean, and now pushed to
  GitHub. The remaining headline risk is that **almost none of the 3D work has been seen in a
  browser** — see §4.

### Read these first, in this order

1. `CLAUDE.md` — architecture + **25 numbered footguns**. Dense and authoritative. The
   footguns are hard-won; several document bugs that took hours to find. Do not "fix" them.
2. This file — what is done, what is not, what is unverified.
3. `the implementation plan (local, not in this repo)` — the original
   implementation plan and the **data contract**. Milestone IDs (M-W*, M-P*) below come from it.

---

## 1. State at a glance

| | |
|---|---|
| App (`src/`) | 51 files, ~13,000 lines — Vue 3 + TS |
| Pipeline (`pipeline/`) | 26 files, ~5,700 lines — Python, conda env `sdo` |
| `yarn lint` / `yarn typecheck` / `yarn build` | all **PASS** |
| `pipeline validate --root public/data --strict` | **0 failed, 0 warnings** |
| Data products building | 6 of 6 (pfss, ar, ephem, stats, texture, events) |
| Git commits | 2, pushed to `origin/main` |
| Automated tests | none (the pipeline validator is the de-facto test suite; the app has none) |
| CI workflows | 4 written, **0 ever run** |

### Top risks, highest first

1. **The 3D view has never been confirmed working in a browser.** Large amounts of geometry
   were derived from engine source and verified numerically, not visually. See §4.
2. **The publish path has never run.** `data.yml`'s build+validate half is proven on a clean
   runner; `app-deploy.yml`, `keepalive.yml` and the gh-pages publish are still unexercised,
   and there is no gh-pages branch. **GitHub Pages is blocked**: a private repo needs GitHub
   Pro, and the API refuses with "Your current plan does not support GitHub Pages for this
   repository." Unblock by making the repo public or upgrading — deferred by choice.
   Actions are ENABLED, so the `data.yml` (4-hourly) and `keepalive.yml` (monthly) schedules
   are armed and will consume private-repo CI minutes publishing to a branch nobody serves.
3. **No app-side tests.** Regressions in the app are caught only by eye.

---

## 2. Milestone status

Legend: **DONE** = implemented, builds, passes its own checks · **UNVERIFIED** = same, but
never seen running · **PARTIAL** · **NOT STARTED**

### Web track

| ID | Scope | Status |
|---|---|---|
| M-W0 | Bootstrap from exo-sonification skeleton | **DONE** |
| M-W1 | Shell + "Sun Now" disk viewer | **DONE** |
| M-W2 | Live SWPC stats | **DONE** |
| M-W3 | WWT 3D boots (`wwt/sunStage.ts`) | **UNVERIFIED** |
| M-W4 | three.js stage on WWT's canvas (vendored `three-wwt`) | **UNVERIFIED** |
| M-W5 | PFSS field lines + 72 h scrubber | **UNVERIFIED** |
| M-W6 | Spacecraft (PSP, SolO, STEREO-A) trails + labels | **UNVERIFIED** |
| M-W7 | Kiosk mode + polish | **UNVERIFIED** |
| M-W8 | App consumes `events.json` (flare/CME marks, event card) | **UNVERIFIED** (2026-08-23) |

M-W1/M-W2 are marked DONE rather than UNVERIFIED because the disk view and stats work with
no WWT at all and the user has been exercising them.

### Pipeline track

| ID | Scope | Status |
|---|---|---|
| M-P1 | Scaffold + GONG/SRS sources | **DONE** |
| M-P2 | Timeline + frozen seed set | **DONE** |
| M-P3 | PFSS solve / trace / resample | **DONE** |
| M-P4 | Binary export + validator | **DONE** |
| M-P5 | Ephemeris + regions + stats | **DONE** |
| M-P6 | Outage drills (GONG, SRS, DONKI) | **DONE** |
| M-P7 | CI end-to-end | **PARTIAL** — `data.yml -f dry_run=true` passed first try on 2026-08-23 (build + validate + artifact green, publish correctly skipped). Publish path still unexercised. |
| M-P8 | DONKI source + events product | **DONE** (2026-08-23) |
| M-P9 | Events validator + outage drill | **DONE** (2026-08-23) |

### Phase 2

| ID | Scope | Status |
|---|---|---|
| P2.1 | Live AIA texture on the 3D sphere | **DONE**, extended to 3 channels |
| P2.2 | PUNCH + Proba-3 markers | **PARTIAL** — `ephem/spacecraft.json` ships the `at_earth` metadata; the app does not render them |
| P2.3 | LMSAL PFSS fallback (`?pfss=lmsal`) | **NOT STARTED** |
| P2.4a | Flare markers on the disk view | **NOT STARTED** |
| P2.4b | Web Share API | **NOT STARTED** |
| P2.4c | "What changed since the show" card | **NOT STARTED** |
| P2.4d | `prefers-reduced-motion` | **PARTIAL** — referenced in one file, not applied systematically |
| P2.4e | Audio narration | **NOT STARTED** |
| — | Flare/CME 3D eruption (see §6) | **NOT STARTED** — feasibility study done |

### Integration (M-INT) — all NOT STARTED

Deployed-site load, real-phone QR test, Lighthouse mobile, field-line orientation
cross-check against GSFC's own PFSS overlay, overnight kiosk soak.

---

## 3. What changed on 2026-08-23 (most recent session)

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

**Field-line colour toggle** — Polarity vs Electric blue, as a shader uniform. `?fieldcolor=blue`.

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

---

## 4. Verification ledger

Being explicit about this, because "it builds" has been doing a lot of work.

### Proven by measurement

- SDO browse-image framing across all channels and resolutions (sub-pixel limb fits);
  `HMIBpfss` vs `HMIB` confirmed by red/green composite where GSFC's own AR number labels
  coincide at scale 1.0.
- The winding determinants (computed from the engine's own `perspectiveFovLH` formula).
- `earthFacingCamera()` — camera lands on the Sun→Earth line to 0.000° across a full
  simulated year; solar north screen-up to 0.0000°.
- Events `dir_ecl` — negative-tested (a 10° rotation makes the validator fail).
- HEEQ→ecliptic conversion cross-checked against an independent solar-longitude route.
- DONKI IPv6 timeout (21.06 s) vs IPv4 (0.03 s), measured directly.
- All pipeline outage drills.

### Asserted but NOT seen running

Everything visual. In particular:

- The winding fix itself. `assertWinding()` will `console.warn` if the constant is wrong —
  **check the browser console first thing.** If it warns, the Sun renders inside-out.
- The Earth-facing home camera.
- The depth-buffer clear (footgun 18) that makes far-side field lines hide behind the Sun.
- Multi-channel texture switching, the field-colour toggle, the reworked solar wind.
- Kiosk mode, the attract loop, the QR flow.
- Anything on a real phone.

**Dev server:** `yarn serve` → `localhost:8080`, or the LAN IP for a phone (`allowedHosts: all`).

---

## 5. Suggested next steps

Ordered by value, with the blocker first.

1. **Browser-verify the 3D view.** One session with the dev server open, working through §4's
   unverified list. Everything else is built on the assumption this works.
2. **M-W9 — the 3D eruption layer.** M-W8 shipped the marks and cards; the remaining piece
   is drawing the CME itself (`src/three/cme.ts`). `events.json` already carries `dir_ecl`
   ready to use. See §6, and **read footgun 25 first** — the CME group must carry no
   quaternion at all.
3. **Re-enable Actions, then M-P7 — run CI once.** Actions are off at the repo level; turn
   them back on under Settings → Actions → General, or:

   ```
   gh api -X PUT repos/astrodavid10/sol-solar-viewer/actions/permissions -F enabled=true
   ```

   Then exercise the pipeline without publishing:

   ```
   gh workflow run data.yml -f dry_run=true
   ```

   Be aware that enabling Actions also arms `app-deploy.yml` (push to `main`) and the
   `data.yml` / `keepalive.yml` schedules.
4. **M-INT** — deploy, then the real-phone and Lighthouse passes.

---

## 6. Flare / CME 3D eruption — decision already made

A feasibility study was run (2026-08-23). Summary so it does not get re-litigated:

- **Real per-event BATSRUS/MHD is not viable.** One *scalar field*, one snapshot, medium
  resolution = **11.1 MB** (measured against PSI's public MAS archive); a usable CME state is
  ~89 MB/snapshot and a 6-hour eruption ~6 GB, against a 1.55 MB total PFSS product. There is
  no run API (CCMC Runs-on-Request is a human-mediated order form), it is retrospective
  (recent solar runs simulate 2011–2013 events), and CCMC's publication policy asks for
  developer contact and co-authorship consideration rather than granting redistribution.
- **Recommended instead:** a stylised parametric eruption driven by real DONKI numbers
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
