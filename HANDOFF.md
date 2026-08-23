# Sol — project handoff & status

**Living document.** Update it at the end of any session that changes project state. It exists
so a fresh session (human or Claude) can pick the work up without re-deriving context.

- **Last updated:** 2026-08-23
- **Repo:** `github.com/astrodavid10/sol-solar-viewer`. Actions are ENABLED and the
  `gh-pages` branch is live (app + data). GitHub Pages is not yet turned on.
- **Status summary:** feature-complete against the v1 plan, building clean, and now pushed to
  GitHub. The remaining headline risk is that **almost none of the 3D work has been seen in a
  browser** — see §4.

### Read these first, in this order

1. `CLAUDE.md` — architecture + **25 numbered footguns**. Dense and authoritative. The
   footguns are hard-won; several document bugs that took hours to find. Do not "fix" them.
2. This file — what is done, what is not, what is unverified.
3. The original implementation plan — a local Claude Code planning document, not in this
   repo. Milestone IDs (M-W*, M-P*) below come from it. Its load-bearing half, the data
   contract, is restated in `CLAUDE.md` and enforced by `pipeline/validate.py`.

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
| CI workflows | `data.yml` and `app-deploy.yml` both green end-to-end; `build.yml` and `keepalive.yml` still unexercised |

### Top risks, highest first

1. **The 3D view has never been confirmed working in a browser.** Large amounts of geometry
   were derived from engine source and verified numerically, not visually. See §4.
2. **GitHub Pages is not enabled**, so nothing is served yet. On a private repo it needs
   GitHub Pro ("Your current plan does not support GitHub Pages for this repository");
   making the repo public is the other route. `gh-pages` already exists and carries both the
   app and `data/`, at exactly one commit, so enabling Pages is the only remaining step.
   The `data.yml` (4-hourly) and `keepalive.yml` (monthly) schedules are armed.
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

---

## 8. Design audit — in progress

**Status: PROPOSAL ONLY. No application source file was modified, and none should be.**
A visual-design audit + revision proposal was started 2026-08-23 and cut off before the
deliverable (a design canvas) was built. Everything below is written from the working context so
a fresh session does not have to re-derive it. The expensive part is §8.1 — recovering it means
re-reading an 18 MB PDF.

### 8.1 Brand kit facts — `C:\Users\adavi\Downloads\Planetarium_Brand_Kit_V7.pdf`

4 pages, 792×612 pt (landscape Letter), 18 MB. Page 1 is the **master INTUITIVE Planetarium
brand**; pages 2–4 are show sub-brands (Our Place in Space, JWST, Black Holes).

**Colours (page 1, verbatim including the kit's own casing):**

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

- Exists in two colours: **White** and **Spaceberry**. *"Except for B&W printing, spaceberry is
  an appropriate choice anywhere black could be chosen, and should be regarded as the default."*
- *"Outer Glow may be applied to the white version of the wordmark, though legibility is key and
  the effect should be slight."*
- *"The Intuitive Planetarium wordmark cannot exist where the USSRC logo does not."*
- *"The wordmark's primary rule is that it must always be legible."* On print items where the
  logo acts alone it must not be modified from the showcased versions; **recolouring or
  modifying it to integrate with a graphic or artwork by the planetarium team for marketing
  purposes IS appropriate** (see: Spectra Billboard).
- **Icon & Complete Logo:** the complete Logo = Icon + Wordmark. The Icon may appear in
  spaceberry, white, or coloured. *"The icon can appear as one with the title, approximately
  where the ends of the two shooting stars are placed evenly following the line of the Intuitive
  'I', or to the left of the wordmark."*
- Wordmark forms shown: stacked two-line `INTUITIVE / PLANETARIUM` and single-line
  `INTUITIVE PLANETARIUM`; boxed versions on Spaceberry and on Spacebubble grounds. "INTUITIVE"
  is bold italic; "PLANETARIUM" is lighter with wider tracking.

**Design Elements (page 1, right column) — the brand's visual motifs:**

1. Four-point **sparkle stars**, white, varied sizes, scattered with small circles on a
   Spaceship-Gray/blue-grey rounded panel.
2. A **maroon gradient panel** (Cosmaroon → Midnight Cherry) with a *stepped/notched* rounded
   corner and pink pixel/square speckle.
3. A **hexagon tessellation** strip, gradient from near-black through Spaceberry to Spacebubble
   navy.

**Layout / grid convention of the kit itself** (worth copying — it is how the brand presents
information): section headers set in **letterspaced caps at roughly 0.2em+ tracking**
(`W o r d m a r k s`, `T y p o g r a p h y`, `C o l o r s`), each followed by a **thin
horizontal rule spanning the column**. Page ground is a light grey (~`#E3E5E9`) carrying faint
sparkle stars. IP wordmark top-left, USSRC lock-up top-right.

**Show sub-brands (pages 2–4) — not the master brand, but recorded so the PDF need not be
reopened:**

- *Our Place in Space* — design-element hexes `#dbd4db #abb0d4 #8d9cc9 #6e87bf` /
  `#335494 #243870 #1c264d #141436`. Type: **Gotham** (Book/Bold + italics); Gotham Bold full
  caps is the full title in the inline logo and the word "Space" in the standard logo.
  **Nimbus Sans Light at tracking value 350** for the "you are here" portion. Two logo
  variations × four colour options (Full colour with gradients whose epicentres sit at each
  planet, Earth's Moon and the Sun, plus a gradient overlay on the text; Partial colour with
  planet gradients and white text; White; Black). The inline logo is the only use case for the
  complete inner-solar-system icon; default to the multi-line wordmark when possible.
- *JWST: The Story Unfolds* — design-element hexes `#f3ecae #e8ce73 #bf7f2e` /
  `#3262af #023789 #000e33`. Type: **Casanova Scotia** (must be hosted locally, no other
  variations) for "James Webb Space Telescope"; **Good Times Book** for "The story unfolds".
  Logo may appear white or Spaceberry; the white version may drop a black shadow. The Northrop
  Grumman Foundation logo must appear wherever this logo does.
- *Black Holes: Cosmic Abyss* — wordmark in White, Black, and a main coloured version with a
  peach-to-white gradient; in every variation except Black the black-hole icon serving as the
  "o" is filled black. Every colourway except black also has a glowing option (the main coloured
  wordmark has two glow colours); on dark backgrounds use the coloured-aura variant
  `Black_Hole_Logo_[format]_Full_Color.png`. Prioritise the two-line standard version. Type:
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
   #b8b0a0` warm grey. Nothing can pop against neighbours of its own temperature. *This is the
   real answer to "the yellow on grey is just OK"* — the fix is to cool the neutrals, not to
   find a better yellow.
2. **The chrome wears the data's colour.** `--sol-panel-border: 1px solid rgba(255,200,80,0.3)`
   is gold, so every rail panel is painted in the same hue as closed field loops. The chrome
   competes with the Sun instead of framing it.
3. **Nothing in the app uses the brand palette at all.** No Spaceberry, no Spacebubble, no
   Cosmaroon anywhere. The app is currently off-brand.

**In-scene colours inventoried (dome-shared — do NOT recolour):** `pfss.ts` manifest fallbacks
`closed [1,0.85,0.2]` ≈ `#FFD933`, `open_pos [0.3,0.55,1]` ≈ `#4C8CFF`, `open_neg [1,0.4,0.1]`
≈ `#FF6619` (render hints in the manifest can override these); `fieldLines.ts` `MONO_COLOR
[0.373,0.722,1.0]` = `#5FB8FF`; `solarWind.ts` `COLOR [0.70,0.83,1.0]` ≈ `#B3D4FF`;
`sunGlow.ts` radial stops `rgba(255,246,224,.30) → (255,232,175,.26) → (255,198,110,.11) →
(255,165,66,.035) → (255,150,50,0)`.

**Spacecraft colours** (`public/data/ephem/spacecraft.json`): psp `#ff8a3d`, solo `#5fb8ff`,
stereoa `#c77dff`, earth `#7de08a`. Note solo's colour is *exactly* `--sol-accent2`, and
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
  value])` (`SolarView3D.vue` ~line 720). The engine's orbit colour is
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
  `Vector3(0,0,0)` once per frame gives the Sun's screen centre for leader-line angles.
- **BrandMark collision (new in 49e06cd).** `.sol-brand` is now `top: 0.75rem; left: 0.75rem;
  z-index: 6` on the stage — directly under `TopBar`'s own left-aligned "Sol / the Sun right
  now". Two brand marks stacked on the same left edge ~50 px apart. Also, the stage BrandMark
  appears *alone*, which the kit's "cannot exist where the USSRC logo does not" rule forbids.
- **`backdrop-filter` over the WebGL canvas is already proven here** — `SpacecraftLabel` uses
  `blur(4px)`, `TimeScrubber` `blur(6px)`.
- `StatChip`'s freshness dot (`#58d68d` / `#f0b429` / `#6b6b6b`) puts the actual time only in a
  `title` attribute — inaccessible on touch, and colour is the sole carrier.
- `TimeScrubber` event marks already carry meaning by **shape** (diamond = flare, circle = CME)
  independent of colour. Keep that; it satisfies the "not colour alone" rule for free.

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
the canvas edge. WWT owns the sky colour and the canvas is shared, so changing the three.js
clear colour is risky — flagged as **not verified feasible**.

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
over the Sun must come from a plate or a casing, never from a colour choice. `--sol-text-quiet`
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
Fonts) need webfont licences. The app already bundles local TTFs so the mechanism exists — the
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
treatment therefore works on both backgrounds, which no single colour can.

**(a) Dual-contrast marker dot** — replaces `.sl-dot`'s current 8 px + `box-shadow: 0 0 6px
currentColor`, a coloured glow that vanishes over the photosphere:

```css
width: 11px; height: 11px; border-radius: 50%; background: <mission colour>;
box-shadow:
  0 0 0 2px   rgba(5,1,15,0.92),        /* dark contour — wins on the bright disk */
  0 0 0 3.5px rgba(245,244,240,0.62),   /* light ring   — wins on the black sky   */
  0 0 12px 1px <mission colour @ 55%>;  /* glow, cosmetic only */
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
projected Sun centre by ~26 px and draw a 1.5 px leader from marker to chip:

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
rgba(255,200,80,0.22)`. Colour is then not the sole carrier — ring = active region, ⊕ glyph =
sub-Earth.

**(e) Orbits — replace `LineBasicMaterial` with `Line2` / `LineGeometry` / `LineMaterial`**
(already in three 0.185.1, no new dependency). Two-pass casing per arc, the cartographic
road-casing trick and the same dual-contrast idea as the labels:

| pass | width (screen px) | colour | opacity | notes |
|---|---|---|---|---|
| casing, past | 5.0 | `#05010F` | 0.55 | `renderOrder` 10 |
| core, past | 2.0 | mission colour | 0.90 | `renderOrder` 11; vertex-colour ramp 0.35 → 1.0 toward "now" |
| casing, future | 4.0 | `#05010F` | 0.40 | |
| core, future | 1.6 | mission colour | 0.55 | `dashed: true` |

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
the four physics colours. **Caution:** `#7B7EE0` vs STEREO-A's `#c77dff` — keep planet orbits
well below spacecraft-trail brightness so the two never read as the same class.

**(g) In-scene physics colours are NOT changed.** Gold (closed loops), blue (outbound open),
orange (inbound open) and pale blue-white (solar wind) are the dome show's legend, and a guest
may see the dome an hour before the phone. The apparent lift comes entirely from taking gold
*out of the chrome*, which raises the field lines' perceived saturation without touching a
single data value.

**Component decisions already made:**

- **LayerPanel** — switch off-track `rgba(148,155,175,0.20)`, on-track `rgba(255,200,80,0.55)`,
  knob `#F5F4F0`. Segments stay 44 px; border `rgba(148,155,175,0.22)`; on-state
  `border-color #FFC850`, `background rgba(255,200,80,0.14)`, `color #F5F4F0`. Add a 14 px
  inline-SVG glyph per layer row (loops / streaming dots / craft / ring / halo) for non-colour
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
   physics colours are kept even though they are not brand colours, because they are dome-show
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
