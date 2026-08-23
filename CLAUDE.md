# Sol — the Sun Right Now

Mobile-first solar data explorer for planetarium guests ("Data to Dome, Dome to Phone").
Guests scan a QR code and see current solar conditions: live SDO imagery ("Sun Now" disk view),
the Sun's magnetic field in 3D over the last 72 hours (PFSS field lines from our own pipeline,
same model + colors as the dome show), Parker Solar Probe / Solar Orbiter positions, and live
NOAA space-weather numbers.

**Start here: `HANDOFF.md`** — living status doc (what is done, partial, unstarted, and what
has never been verified in a browser). Update it at the end of any session that changes state.
The original implementation plan lives outside this repo as a local Claude Code planning
document; the parts that matter (the binary formats and manifest fields that the app and the
pipeline must agree on) are restated here and in `pipeline/validate.py`, which enforces them.
Skeleton provenance: adapted from `DataStories\exo-sonification` (that repo is READ-ONLY reference).

## Commands

```bash
yarn install          # yarn 4 (packageManager pin); empty yarn.lock was needed once because
                      # a stray package.json in the user home dir confuses project detection
yarn serve            # dev server (allowedHosts: all — test on a phone via LAN IP)
yarn lint             # eslint, no fix
yarn typecheck        # tsc --noEmit — does NOT check .vue script blocks; only yarn build does
yarn build            # production build to dist/
```

Pipeline (Python, conda env `sdo`):

```powershell
conda run -n sdo python -m pipeline all --out public\data -v    # dev data for yarn serve
conda run -n sdo python -m pipeline pfss --from-cache --out public\data  # fast re-export (~2 s)
conda run -n sdo python -m pipeline validate --root public\data --strict
# fallback if conda run misbehaves:
& "$env:USERPROFILE\anaconda3\envs\sdo\python.exe" -m pipeline all --out public\data -v
```

## Architecture

- **Two tracks, one contract.** `src/` is the Vue app; `pipeline/` is the Python data pipeline
  that GitHub Actions runs every 4 h (`.github/workflows/data.yml`), publishing binary PFSS
  frames + JSON products to the `data/` subtree of `gh-pages`. The app fetches them same-origin.
  The contract (binary formats, manifest fields) is specified in the plan file — change it in
  BOTH places or not at all.
- **Entry chunk must stay engine-free.** `src/main.ts` must NOT import `@wwtelescope/engine-pinia`
  (or `three`); `SolarView3D.vue` is an async component whose loader installs `wwtPinia`
  post-mount. The disk view + stats work with no WWT at all.
- **gh-pages is a single forced orphan commit** (see `scripts/publish_gh_pages.sh`), shared by
  `app-deploy.yml` (excludes `data/`) and `data.yml` (writes only `data/`), serialized by the
  `gh-pages-publish` concurrency group. No history there by design; workflow artifacts are the
  audit trail. `keepalive.yml` commits monthly to main — REQUIRED, or the cron schedule
  auto-disables after 60 days without default-branch commits.

## Footguns (hard-won; do not "fix" these)

1. **Never `setTrackedObject(sun)`** in solar-system mode — the engine adds a lat/lng-dependent
   surface offset that slides the world origin ~1 R_sun as the user orbits, detaching the
   three.js overlay. Always `camera.target = 20` (custom) + `viewTarget = (0,0,0)`.
2. **`R_SUN_AU = 0.004645784`** (the engine's adjusted Sun radius), NOT the physical 695,700 km,
   and `solarSystemScale` must stay 1 — else field-line footpoints float off the sphere by 0.15%+.
3. **Engine must be ≥ 7.36** for `WWTControl.addFrameCallback` (three-wwt hook). If it's
   undefined, the yarn `resolutions` block didn't take: `yarn why @wwtelescope/engine`.
4. Shared-canvas three rendering (`target:"wwt"`) gives correct depth occlusion (Sun hides
   far-side lines). If WWT artifacts appear, `?three=overlay` is the escape hatch (loses occlusion).
5. **3D mode needs worldwidetelescope.org up** (imageset catalog fetched at init). Never set
   freestanding mode. Disk view + stats must stay fully independent of WWT.
6. **No CORS on sdo.gsfc.nasa.gov**: `<img>`/`<video>` only. No `fetch()`, no canvas readback,
   no WebGL textures, and NEVER set `crossorigin` on those tags (it breaks loading). This also
   means no `Last-Modified` — the disk view intentionally shows "new image about every 15 min"
   instead of a frame timestamp. Don't "fix" it with a fetch; it will CORS-fail.
7. **SDO URL quirks:** PFSS overlay stills have NO underscore (`latest_2048_0171pfss.jpg`);
   pfss variants exist at 512/1024/2048/4096 only, and not for HMIIC/HMII/HMID/4500. 48 h movies
   exist only at 1024 and only for AIA channels + 4500 (0171 is ~32 MB — never preload, always
   show the size). Daily movies (incl. HMI) live under `dailymov/YYYY/MM/DD/`.
   **Movie sizes vary wildly by channel** — measured 2026-08 with HEAD requests, 48 h / 24 h:
   0193 16/6, 0211 17/7, 0171 32/13, 0304 52/21, **0094 100/41**, HMIB —/18, HMIIC —/8 MB.
   They live in `src/data/sdoCatalog.ts` (`approxMovieMb`, `approxDailyMovieMb`) and are shown
   on the play button before a single byte loads. Do not replace them with one average.
8. **`.gitignore` uses `/public/data/`** — a bare `data/` would also swallow `src/data/`.
9. **PFSS dead-seed padding repeats the last valid vertex** (opacity 0 via valid=0). Zero-padding
   instead draws rays to the Sun's center.
10. **`onGesture*` engine patches must run at import time** (`src/wwt/wwt-hacks.ts` — the engine
    binds handlers at initControl and captures the method reference). `move` can be patched
    anytime. These patches replace exo's `modify_index.py` node_modules hack.
11. **WWT's FOV is fixed π/4 VERTICAL.** Portrait framing needs `tfAspectPad()`
    (≈ innerHeight/innerWidth) or every view is ~2.2x too tight on a phone.
12. Keep `src/three/fieldLines.ts`, `spacecraftTrails.ts`, `sunGlow.ts`, `project.ts` free of
    WWT imports — they take scene/camera from `stage.ts`, so a pure-three.js stage could replace
    WWT if 3D proves too heavy on phones.
13. **Quantized coords don't gzip** (measured 1.13x) — the raw `.bin` sizes are the real budget.
    Ship raw binaries; GitHub Pages gzips transparently (and pre-gzipped `.gz` files would NOT
    get Content-Encoding on Pages — they'd arrive as garbage).
14. Camera zoom semantics in solar-system mode: `distance_AU = 4·zoom/9 + 1e-6`. The engine
    eases `viewCamera` toward `targetCamera` every frame — write `targetCamera` for smooth
    motion; no slew machinery needed.
15. The vendored `src/three/three-wwt/` is patched (drawing-buffer-driven sizing, webgl1
    fallback, direct addFrameCallback). Do NOT replace it with the `@cosmicds/three-wwt` npm
    package — 0.0.3 bundles a duplicate WWT engine (1.7 MB) and has a broken CJS entry.
16. **three's `resetState()` clobbers the GL viewport from the shimmed `gl.canvas.width`**
    (CSS px on DPR>1 screens) and leaves its own viewport cache stale, so `setViewport()`
    afterwards no-ops. The vendored setupThreeWWT restores the viewport with a RAW
    `gl.viewport(0,0,drawingBufferWidth,drawingBufferHeight)` call before every shared-canvas
    render. Symptom when regressed: overlay renders offset into the bottom-left quadrant on
    every phone, correct on desktop.
17. **Never unmount `<WorldWideTelescope>`** once created — the engine's global texture/tile
    caches hold handles into the destroyed GL context and a remounted Sun renders black.
    sol.vue mounts SolarView3D once and hides it with v-show; SolarView3D pauses its three
    work via `stage.setEnabled(view === "3d")`.
18. **WWT's depth buffer is not trustworthy for overlay depth-testing.** Its TileShader never
    sets depthMask (inherits whatever the last GL user left) and its planet passes write
    engine-internal values — depth-testing our sun sphere against them let WWT's own Sun
    texture occlude the sphere completely. The shared-canvas pass therefore CLEARS the depth
    buffer at the start of every three render (setupThreeWWT.ts) and the sun-surface mesh is
    the authoritative occluder; in "Plain" surface mode it renders depth-only
    (colorWrite=false). Do not remove the clear or the depth-only mode: far-side field-line
    occlusion depends on both. (Fix applied but NOT yet human-verified in a browser.)
19. **WWT's camera REVERSES triangle winding — every solid material needs `side` flipped.**
    The engine builds its matrices with `Matrix3d.lookAtLH` + `Matrix3d.perspectiveFovLH`
    (D3D, left-handed, clip w = +z_view, depth [0,1]); three assumes GL's right-handed
    convention. `wwtMatrixToTHREE` passes them through verbatim (that is what keeps our
    geometry registered with WWT), so the world→clip transform three draws with is
    orientation-REVERSING: `det(P_wwt) = +1.166e-3` vs `det(P_three) = -2.332e-3` at
    fov π/4 / aspect 0.5 / zn 1e-4 (det(V) = +1 in both). three cannot compensate — it picks
    winding from `object.matrixWorld.determinantAffine() < 0`, the OBJECT only, never the
    camera. So with three's defaults every solid mesh has its FRONT faces culled.
    Symptoms, all one cause: the Sun's SDO/artist texture visible "through" the sphere (you
    were seeing the inside of the far hemisphere); that surface ~21% brightness (sunSurface's
    `mu = max(dot(normalize(vWorld), view), 0.08)` is negative on a back face → clamps to
    0.08 → `pow(0.08,0.6)`); and the sun glow + spacecraft marker dots GONE, because three's
    Sprite quad is wound CCW and SpriteMaterial defaults to FrontSide. `src/three/winding.ts`
    owns this: `SOLID_SIDE` (BackSide) for meshes, `FLAT_SIDE` (DoubleSide) for sprites, and
    `assertWinding()` re-derives the sign from the live camera each session so a convention
    change in the engine warns instead of silently rendering inside-out.
20. **View-space z is POSITIVE in front of the camera** (same lookAtLH cause as 19). Anything
    ported from a three.js example that says `-mvPosition.z` is wrong here and will silently
    take the other branch of a `max()`. This pinned every solar-wind particle to the 6 px
    `gl_PointSize` ceiling at every zoom — 3000 max-size additive dots in the Sun's few
    hundred pixels, i.e. the "wind is a white blob" report. Use `abs(mv.z)`.
    `src/three/project.ts` also assumes GL's [-1,1] NDC depth (`z > -1`); under D3D's [0,1]
    that bound is merely loose, not wrong (behind-camera still rejects via `z < 1`).
21. **SDO browse stills: `latest_*_HMIBpfss.jpg` is framed differently from `latest_*_HMIB.jpg`.**
    GSFC renders the PFSS overlay onto a COMMON frame, so the pfss magnetogram is already at
    AIA's plate scale while the plain one is at HMI's. Measured limb diameter as a fraction of
    frame (identical across 1024/2048/4096): HMIB 0.9184, HMIBpfss 0.7676, 0171 0.7824,
    0171pfss 0.7893. Applying `diskScale` to the overlay rendered the Magnetic Map ~18% small.
    `diskScaleFor(id, res, pfss)` mirrors `stillUrl`'s variant choice exactly — change them
    together. The plain-HMI 0.8395 is CORRECT and measurement-backed: AIA 4500 (white light,
    same photospheric limb HMI sees) is 0.7711 vs HMI 0.9168 = 0.8411, within 0.2% of the
    0.5044/0.6009 plate-scale ratio. The EUV channels' limb really is ~1.5% larger — emission
    above the photosphere, not a framing error. Do not "correct" it away.
26. **WWT's camera lat/lng has its poles at +/-Y — an arbitrary pair of points IN the
    ecliptic plane** (ecliptic longitude 90 and 270), NOT at the ecliptic or solar poles.
    `cameraPosition = d*(-cos(lat)sin(lng), sin(lat), cos(lat)cos(lng))`, derived from
    `setupMatricesSolarSystem` + `_rotationX/_rotationY/transform/_multiply`. Near those
    points `lng` does nothing, so horizontal drag goes dead, and clamping `lat` to guard the
    degeneracy reads as an invisible wall in a direction unrelated to anything on screen.
    `sunStage.orbitByPixels` therefore REPLACES the engine's solar-system `move()` and orbits
    about the SUN's axis instead; `clampCameraLat` now bounds the angle to that axis.
    The two drag signs (`AZIMUTH_SIGN` +1, `ELEVATION_SIGN` -1) were settled at the screen and
    cannot be derived from the engine's own `lng -= x` / `lat += y` — different axis, and the
    elevation axis `cross(solar_axis, u)` flips with which side of the Sun you are on.
27. **`.solar-view-3d` is `position: relative` with `z-index: auto`, so it creates NO stacking
    context** — its descendants (scrubber at z-index 5, card slot at 20) compete directly with
    any SIBLING overlay in `sol.vue`. The branding mark sat invisible at z-index 3 for a whole
    session because of this. Anything placed over the 3D view from outside it must clear the
    z-indices used INSIDE it, or the 3D view needs its own stacking context.
28. **An internally-scrolling flex panel needs `min-height: 0` on the container, the panel AND
    the grid item.** Miss any one and the content sets a floor on the item's height, the `1fr`
    row stops constraining anything, and the panel silently clips mid-content with no
    scrollbar while its neighbor draws over the top. Also: `grid-template-rows` and
    `grid-template-areas` must declare the SAME number of rows — four sizes against a two-row
    map put the stage in an `auto` row and the WebGL canvas, which has no intrinsic height,
    collapsed to nothing.
29. **Off-limb structure cannot go on the sphere.** A disk image records the corona's
    PROJECTION from Earth and carries no depth, so `texture/*_offlimb_*.jpg` is drawn as a
    camera-facing billboard (`src/three/offLimb.ts`) and FADES OUT with the angle from the
    sub-Earth direction — past ~25-55 deg it would be a flat photograph pasted across a Sun
    seen from the side. The crop is centered on the FITTED disk center, not the array center
    (`measure_limb` reports 12-14 px offsets on AIA frames). Black, not alpha: the billboard
    is additive, so black already contributes nothing and a PNG would cost several times the
    bytes. `half_width_rsun` is DATA (AIA 1.28, HMI 1.09) because it falls out of plate scale.
    The validator asserts the disk center is black — additive blending would otherwise paint a
    second Sun over the sphere and nothing else would catch it.
22. **The 3D sphere texture is MULTI-CHANNEL and is not all AIA.** `sol.texture/2`,
    `TEX_CHANNELS` in `pipeline/config.py` — FIVE products, default first:
    0171 "Coronal Loops", 0304 "Chromosphere", 0193 "Hot Corona", HMIIC "Visible
    Sun", HMIB "Magnetic Map". `run_texture` loops them and writes one
    `sdo{CODE}_carrington_4096x2048.jpg` each (265-800 KB, ~2.4 MB total) plus a
    `layers` array in `texture.json`. The top-level fields still describe the
    FIRST channel, so a schema-1 reader stays correct. A non-default channel
    that fails is SKIPPED, not fatal; the default failing still propagates.
    A channel is NOT just a wavelength, and three per-channel fields exist
    because getting them wrong ships a dishonest map rather than an error:
    `scale` (AIA 0.6009"/px vs HMI 0.5044" — the disk fills 0.7824 of an AIA
    frame and 0.9184 of an HMI one, footgun 21), `farside` ("quiet" adds
    invented mottling, which is a defensible stylization for EUV and fabricated
    magnetic field on a magnetogram — HMIB and HMIIC are "flat"), and `ar_check`
    (the registration guard scores by finding BRIGHT pixels near a region, which
    only means anything in EUV: spots are DARK in HMIIC and bright in HMIB just
    means positive polarity).
    The app holds ONE channel texture resident (4096x2048 RGBA ≈ 32 MB of GPU
    memory) and re-decodes from the HTTP cache on switch. Do not raise
    `TEX_OUT_W/H` further without measuring phone GPU memory.
23. **DONKI numbers active regions 10000 higher than NOAA SRS does.** DONKI says `14513`,
    `srs.txt` and `ar/regions.json` say `4513` (verified against both feeds simultaneously
    2026-08-23). `events/export.py` joins with `activeRegionNum - 10000`; a naive join
    silently matches ZERO regions and anchors every eruption nowhere. `run_events` prints
    the match rate every run so a regression is visible in the log, and the validator
    range-checks `ar_index` against `ar/regions.json`. An `ar_index` of -1 is NORMAL, not a
    failure: DONKI keeps reporting a region for days after it has left the SRS.
24. **`kauai.ccmc.gsfc.nasa.gov` (DONKI) has a black-holed AAAA record, and urllib has no
    Happy Eyeballs.** getaddrinfo returns the v6 address FIRST; connecting to it times out
    after 21.06 s, then urllib falls back to v4 (0.03 s). curl races the families (RFC 8305)
    and never notices — which is why a curl probe says 0.87 s and the pipeline said 21.8 s
    for the identical URL. Two fetches per run was 42 s of a ~4 min CI budget. Fixed with
    `io_utils._ipv4_only()`, a scoped `getaddrinfo` filter that `http_get_full(...,
    prefer_ipv4=True)` enters; the events stage went 47.3 s → 5.4 s. Subclassing
    HTTPSConnection to force the family does NOT work (urllib builds the handler and then
    never calls the override) — don't "clean it up" that way. It is OPT-IN on purpose:
    services.swpc.noaa.gov and sdo.gsfc.nasa.gov also resolve v6-first and are fine
    (0.1-0.4 s), so nothing else should pay for CCMC's DNS.
25. **A CME must NOT carry the Carrington quaternion the field lines use.** Field lines,
    solar wind and the sun surface all live in the rotating Carrington frame; a CME
    propagates along a fixed INERTIAL direction. Carrington rotation is 14.18 deg/day, so
    over the 72 h window a Carrington-parented CME would swing 42.5 deg — looks fine on one
    frame, wildly wrong at the other end of the scrubber. `events.json` therefore ships
    `dir_ecl`, a unit vector already in ecliptic J2000 (the app's world frame), and the app
    must apply NO rotation to it. Surface-anchored parts of an eruption (flash, arcade) DO
    stay Carrington-local and should mirror the quaternion the way `solarWind.ts` does.

30. **NOAA's two SRS products disagree, and lining them up by date fabricates a
    cliff.** `srs.txt` and `json/solar_regions.json` are NOT the same series.
    (a) *Different epochs* — the JSON keys on `observed_date`; srs.txt carries
    an `:Issued:` date describing the PREVIOUS UT day, so matching them by date
    shifts one by 24 h. (b) *Different region sets* — `parse_srs` reads
    Section I only (it breaks at the `IA.` marker) and so never sees the
    spotless plage regions; measured 2026-08-22, srs.txt listed 4 regions where
    the JSON listed 7, and the srs.txt set was a strict subset. Preferring
    srs.txt for "today" and the JSON for older days turned a flat Sun into
    34 → 19 spots overnight. `sources.srs.daily_history` therefore uses the JSON
    for EVERY day; `run_regions` prints a note when the two disagree so the gap
    stays visible rather than looking like a bug. Also: `fetch_regions_json`
    floors `numSpots` at 1 (a region that exists deserves a seed even with no
    spots), so a spot COUNT must be summed from `nSpotsRaw`, not `numSpots` —
    the validator asserts `spot_count >= spotted_region_count` to catch it.

31. **CI must seed `dist-data` from the published tree, or `rsync --delete`
    eats the live product.** Every clause of the pipeline's failure policy is
    written against `ctx.out` = "what is currently published": reuse a previous
    frame for an unresolved slot, roll a failed stage back to the served copy,
    and — the big one — `run_pfss` refusing to publish when fewer than
    `MIN_FRAMES_TO_PUBLISH` frames traced, on the stated grounds that "previous
    frames keep being served". On a runner, `--out dist-data` starts EMPTY, so
    none of that could fire; and `publish_gh_pages.sh` rsyncs **with
    `--delete`**, so a run that produced no `pfss/` did not leave the published
    frames alone — it deleted them. Measured 2026-08-23: one GONG outage
    (0/19 slots) removed `data/pfss/` from gh-pages entirely, leaving the app's
    headline product 404 while every check reported success. `data.yml` now
    checks out `origin/gh-pages -- data` into `dist-data` before the build, so
    CI matches local dev (where `--out public/data` accumulates) and the policy
    is real. Note `git --work-tree=X checkout ref -- path` also stages into the
    CURRENT repo's index; the step runs `git reset` afterwards.
32. **`_scrape_gong` used to swallow every exception into `return []`**, so a
    blocked runner, a TLS failure and a genuinely empty day directory all
    reached the log as `GONG listing <date>: 0 file(s)`. It now prints the
    exception (and, when a fetch succeeds but nothing matches, the byte count,
    the link count and the regex) — because the alternative is diagnosing an
    upstream outage that is actually a client-side block. Keep any new
    swallow-and-continue path equally loud: this pipeline's whole design is
    "degrade quietly for the guest, never quietly for the operator".

33. **`gong2.nso.edu` is UNREACHABLE from GitHub Actions runners** — connect
    timeouts, every request, every run. Measured 2026-08-23 across four
    consecutive CI runs: `URLError: <urlopen error timed out>` on all 12 day-
    directory scrapes, while the identical request from a laptop answers
    HTTP 200 in 0.35 s. Not IPv6 (footgun 24's cause): `gong2.nso.edu` publishes
    **no AAAA record at all**, only A 146.5.21.69. Not a block-with-a-response
    either — a 403 or a TLS error would arrive fast; a silent drop is what
    times out. Every OTHER upstream works fine from the same runner in the same
    run (JPL Horizons, CCMC DONKI, NOAA SWPC, SDO GSFC), so it is NSO-side and
    specific to their firewall's view of Azure/GitHub ranges.
    **Consequence: the scheduled pipeline cannot build field lines at all.** It
    reported success anyway for four runs, because the PFSS stage's failure
    policy is a soft one — which is right for a transient outage and actively
    misleading for a permanent block. The frames currently served were built on
    a workstation and published by hand; footgun 31's seeding is what keeps CI
    from deleting them on the next run. Until this is resolved (an NSO
    allow-list request, a mirror, or a self-hosted runner), treat `pfss` in
    `index.json` as expected-stale and do NOT "fix" it by lowering
    `MIN_FRAMES_TO_PUBLISH`.

## Data sources (verified live 2026-08)

- SDO GSFC stills/movies: hotlinked, no CORS (see footguns 6-7).
- NOAA SWPC (CORS *): tiny endpoints only in the browser (`xray-flares-latest`,
  `products/summary/*`, `noaa-planetary-k-index`, `noaa-scales`); the BIG files
  (`xrays-1-day.json` 654 KB, `rtsw_wind_1m.json` 2.9 MB, `solar-cycle/sunspots.json`) are
  digested server-side into `data/stats/summary.json`.
- Spacecraft: baked `data/ephem/spacecraft.json` (Horizons: PSP=-96, SolO=-144, Earth='399');
  live now-dot from `swhv.oma.be/position` (CORS *, ONE utc per call — no ranges).
- PFSS: our pipeline (GONG mrzqs + sunkit-magex, nrho=35, rss=2.5). Fallback (phase 2):
  LMSAL `fieldlines-YYYYMMDD-000400.json` (CORS *, single daily frame).
- PUNCH & Proba-3 have NO Horizons ids — both orbit Earth; heliocentrically they ARE Earth.
- **CCMC DONKI** (`kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/`): flare + CME catalog, no API
  key, `ACAO: *`. The ONLY source that gives a flare/CME a place and a direction — NOAA's
  `xray-flares-latest.json` has class and timing but no source location at all. Digested
  server-side into `data/events/events.json` (~4 KB). Ask for SHORT windows: 3 days is
  0.74 s / 23 KB, a year is 32 s. It 403s on HEAD and 200s on GET, so probe with a GET.
  Not real-time — measured lag to publication is a median 1.9 h for flares, 7.5 h for CMEs
  (p90 16 h / 103 h) — and records are back-filled and revised via `versionId`, so every
  run re-fetches the whole window and dedupes rather than appending. Do NOT use the
  `api.nasa.gov/DONKI` mirror (needs a key, rate-limits at 10, returned 503 when checked).
  DONKI's own terms call it "prototyping quality... research context"; that disclaimer
  ships in the product and must reach the guest-facing copy.
- **Coronagraphs WITH CORS** (unlike SDO, footgun 6): NOAA SWPC re-serves LASCO C2/C3 and
  CCOR-1/CCOR-2 at `services.swpc.noaa.gov/images/animations/<inst>/latest.jpg`, `ACAO: *`
  and a real `Last-Modified`. These CAN be fetched, canvas-read and used as WebGL textures.
  SWPC also publishes its operational WSA-ENLIL run as CORS-clean JPEGs — real MHD of the
  real CME, ~93 KB/frame, for free. (Not yet used by the app.)
