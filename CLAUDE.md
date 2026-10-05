# Sol — the Sun Right Now

Mobile-first solar data explorer for planetarium guests ("Data to Dome, Dome to Phone").
Guests scan a QR code and see current solar conditions in one 3D sphere view: the Sun textured
with recent SDO imagery, its magnetic field over the last 72 hours (PFSS field lines from our
own pipeline, same model + colors as the dome show), Parker Solar Probe / Solar Orbiter
positions, and live NOAA space-weather numbers. (The 2D "Sun Now" disk view was removed in
`a270e5a`.)

**Refreshing the field lines?** Since 2026-09-02 CI does it: the GONG relay (`docs/GONG-RELAY.md`
Option D, an hourly `SolGongMirror` task on the workstation feeding the `gong-cache` branch)
lets the scheduled `data.yml` run trace all 19 frames itself (proved: run 33663715169,
`slots: 19/19`). `PFSS-UPDATE.md` remains the standalone runbook for the day the mirror is
down (the workstation off or logged out); it is no longer a daily chore. If `freshness.yml` or
issue #1 says `pfss` is stale, check the mirror before reaching for the runbook. Check the
**date spread of `%LOCALAPPDATA%\sol-gong-mirror\logs\`**, not just
`Get-ScheduledTaskInfo SolGongMirror`, which reads healthy within an hour of a multi-day outage
(footgun 56). Record each hand-publish as one line in `docs/republish-log.md`.

**Start here: `TASKS.md`**, the task ledger: what is in flight, what is next, and the
definition of done for each. Then **`HANDOFF.md`**, the living status doc (what is done,
partial, unstarted, and what has never been verified in a browser). Update both at the end of
any session that changes state, briefly: detail goes in commit messages.
The binary formats and manifest fields the app and the pipeline must agree on are written
down in **`docs/CONTRACT.md`** and enforced by `pipeline/validate.py`. The current work plan
is `docs/PLAN-2026-10.md`. (Plans kept outside the repo have gone missing before; keep them
in `docs/`.)
Skeleton provenance: adapted from `DataStories\exo-sonification` (that repo is READ-ONLY reference).

## Commands

```bash
yarn install          # yarn 4 (packageManager pin); empty yarn.lock was needed once because
                      # a stray package.json in the user home dir confuses project detection
yarn serve            # dev server (allowedHosts: all — test on a phone via LAN IP)
yarn lint             # eslint, no fix
yarn typecheck        # tsc --noEmit — does NOT check .vue script blocks; only yarn build does
yarn build            # production build to dist/
yarn test:app         # vitest run: tests/app/*.test.ts (~1 s)
yarn check:labels     # vitest run tests/app/labelLayout.test.ts (label de-collision invariants)
yarn check:pipeline   # python scripts/check_pipeline_names.py
yarn test:pipeline    # python -m pytest pipeline/tests -q   (needs the sdo env on PATH)
# build.yml runs ALL of these on every push to main (app job + pipeline job) since 2026-09-02;
# app-deploy.yml installs --immutable and typechecks before it builds.
```

Pipeline (Python, conda env `sdo`):

```powershell
conda run -n sdo python -m pipeline all --out public\data -v    # dev data for yarn serve
conda run -n sdo python -m pipeline pfss --from-cache --out public\data  # fast re-export (~2 s)
conda run -n sdo python -m pipeline validate --root public\data --strict
conda run -n sdo python -m pytest pipeline/tests -q   # ~130 tests, ~1 min; the tz table runs on
                                                       # THIS workstation on purpose (footgun 52);
                                                       # tests that read public/data skip on a runner
python scripts/check_pipeline_names.py          # undefined globals; run BEFORE a long build
# fallback if conda run misbehaves (and for any backgrounded run: conda run buffers stdout):
& "$env:USERPROFILE\anaconda3\envs\sdo\python.exe" -u -m pipeline all --out public\data -v
```

## Architecture

- **Two tracks, one contract.** `src/` is the Vue app; `pipeline/` is the Python data pipeline
  that GitHub Actions runs every 4 h (`.github/workflows/data.yml`), publishing binary PFSS
  frames + JSON products to the `data/` subtree of `gh-pages`. The app fetches them same-origin.
  The contract (binary formats, manifest fields) is `docs/CONTRACT.md`. Change it in the
  pipeline, the app and that file in one commit, or not at all.
- **Validation is per product and happens INSIDE the pipeline, before promote** (since
  2026-09-02, T20). `cmd_all` runs `validate.validate_products()` against a
  staging-over-published overlay, rolls back only a product that fails its own checks (marking
  it `status: degraded` with `last_error`), and exits **0 whenever it promoted a tree**. The CI
  `Validate` step therefore runs AFTER `Publish` as a tripwire, and a `Verdict` step turns a
  degraded publish red without discarding it. Cross-product checks live with the CONSUMER
  (pfss and events check their `ar_index` against regions, not the other way round).
- **Entry chunk must stay engine-free.** `src/main.ts` must NOT import `@wwtelescope/engine-pinia`
  (or `three`); `SolarView3D.vue` is an async component whose loader installs `wwtPinia`
  post-mount. The title, stats and failure cards paint with no WWT at all.
- **gh-pages is a single forced orphan commit** (see `scripts/publish_gh_pages.sh`), shared by
  `app-deploy.yml` (excludes `data/`) and `data.yml` (writes only `data/`), serialized by the
  `gh-pages-publish` concurrency group. A hand-publish is NOT in that group: check for an
  in-flight run before pushing. No history there by design; workflow artifacts are the
  audit trail. `keepalive.yml` commits monthly to main. It is REQUIRED, or the cron schedule
  auto-disables after 60 days without default-branch commits.

## Footguns (hard-won; do not "fix" these)

Each entry is the rule. The measurements and the story behind it are in
`docs/footguns-archive.md` under the same number. **Numbers never change**: code comments
cite "footgun N". A new footgun takes the next number, a compact rule here and its full text
in the archive.

**Footgun index by area**

- WWT engine / camera / 3D frame: 1, 2, 3, 5, 10, 11, 14, 17, 26, 38, 47
- three.js rendering on the shared canvas: 4, 9, 12, 15, 16, 18, 19, 20, 25, 29, 46
- SDO imagery and sphere textures: 6, 7, 21, 22, 36, 40, 57, 59
- Pipeline and upstream data: 13, 23, 24, 30, 32, 35, 41, 48, 51, 52, 58
- GONG relay and field-line freshness: 33, 37, 50, 54, 55, 56
- CI and publishing: 31, 34, 49
- UI / CSS / browser: 8, 27, 28, 39, 42, 43, 44, 45, 53

1. **Never `setTrackedObject(sun)`** in solar-system mode. The engine adds a lat/lng-dependent
   surface offset that slides the world origin ~1 R_sun as the user orbits, detaching the
   three.js overlay. Always `camera.target = 20` (custom) + `viewTarget = (0,0,0)`.
   Detail: docs/footguns-archive.md#fg1
2. **`R_SUN_AU = 0.004645784`** (the engine's adjusted Sun radius), NOT the physical 695,700 km,
   and `solarSystemScale` must stay 1. Else field-line footpoints float off the sphere by 0.15%+.
   Detail: docs/footguns-archive.md#fg2
3. **Engine must be ≥ 7.36** for `WWTControl.addFrameCallback` (three-wwt hook). If it's
   undefined, the yarn `resolutions` block didn't take: `yarn why @wwtelescope/engine`.
   Detail: docs/footguns-archive.md#fg3
4. Shared-canvas three rendering (`target:"wwt"`) gives correct depth occlusion (Sun hides
   far-side lines). If WWT artifacts appear, `?three=overlay` is the escape hatch (loses
   occlusion). Detail: docs/footguns-archive.md#fg4
5. **3D mode needs worldwidetelescope.org up** (imageset catalog fetched at init). Never set
   freestanding mode. The title, stats and failure cards must stay fully independent of WWT.
   Detail: docs/footguns-archive.md#fg5
6. **No CORS on sdo.gsfc.nasa.gov**: `<img>`/`<video>` only. No `fetch()`, no canvas readback,
   no WebGL textures, and NEVER set `crossorigin` on those tags (it breaks loading). This also
   means no `Last-Modified`, so a hotlinked SDO image cannot carry a frame timestamp. Don't
   "fix" it with a fetch; it will CORS-fail. (The sphere textures avoid this by going through
   the pipeline.) Detail: docs/footguns-archive.md#fg6
7. **SDO URL quirks:** PFSS overlay stills have NO underscore (`latest_2048_0171pfss.jpg`);
   pfss variants exist at 512/1024/2048/4096 only, and not for HMIIC/HMII/HMID/4500. 48 h movies
   exist only at 1024 and only for AIA channels + 4500 (0171 is ~32 MB: never preload, always
   show the size). Daily movies (incl. HMI) live under `dailymov/YYYY/MM/DD/`.
   **Movie sizes vary wildly by channel**, measured 2026-08 with HEAD requests, 48 h / 24 h:
   0193 16/6, 0211 17/7, 0171 32/13, 0304 52/21, **0094 100/41**, HMIB —/18, HMIIC —/8 MB.
   They live in `src/data/sdoCatalog.ts` (`approxMovieMb`, `approxDailyMovieMb`); any UI that
   plays a movie must show the size before a byte loads. Do not replace them with one average.
   (No UI plays movies since the disk view went, T10; GSFC's HMI output stopped 2026-09-24,
   footgun 59.) Detail: docs/footguns-archive.md#fg7
8. **`.gitignore` uses `/public/data/`**. A bare `data/` would also swallow `src/data/`.
   Detail: docs/footguns-archive.md#fg8
9. **PFSS dead-seed padding repeats the last valid vertex** (opacity 0 via valid=0).
   Zero-padding instead draws rays to the Sun's center. Detail: docs/footguns-archive.md#fg9
10. **`onGesture*` engine patches must run at import time** (`src/wwt/wwt-hacks.ts`; the engine
    binds handlers at initControl and captures the method reference). `move` can be patched
    anytime. These patches replace exo's `modify_index.py` node_modules hack.
    Detail: docs/footguns-archive.md#fg10
11. **WWT's FOV is fixed π/4 VERTICAL.** Portrait framing needs `aspectPad()` in
    `src/wwt/sunStage.ts` (≈ innerHeight/innerWidth, exo's `tfAspectPad()`) or every view is
    ~2.2x too tight on a phone. Detail: docs/footguns-archive.md#fg11
12. Keep `src/three/fieldLines.ts`, `spacecraftTrails.ts`, `sunGlow.ts`, `project.ts`,
    `winding.ts` free of WWT imports. They take scene/camera from `stage.ts`, so a pure-three.js
    stage could replace WWT if 3D proves too heavy on phones. Detail: docs/footguns-archive.md#fg12
13. **Quantized coords don't gzip** (measured 1.13x), so the raw `.bin` sizes are the real
    budget. Ship raw binaries; GitHub Pages gzips transparently (and pre-gzipped `.gz` files
    would NOT get Content-Encoding on Pages; they'd arrive as garbage).
    Detail: docs/footguns-archive.md#fg13
14. Camera zoom semantics in solar-system mode: `distance_AU = 4·zoom/9 + 1e-6`. The engine
    eases `viewCamera` toward `targetCamera` every frame. Write `targetCamera` for smooth
    motion; no slew machinery needed. Detail: docs/footguns-archive.md#fg14
15. The vendored `src/three/three-wwt/` is patched (drawing-buffer-driven sizing, webgl1
    fallback, direct addFrameCallback, the footgun 47 camera mirror). Do NOT replace it with the
    `@cosmicds/three-wwt` npm package: 0.0.3 bundles a duplicate WWT engine (1.7 MB) and has a
    broken CJS entry. Detail: docs/footguns-archive.md#fg15
16. **three's `resetState()` clobbers the GL viewport from the shimmed `gl.canvas.width`**
    (CSS px on DPR>1 screens) and leaves its own viewport cache stale, so `setViewport()`
    afterwards no-ops. The vendored setupThreeWWT restores the viewport with a RAW
    `gl.viewport(0,0,drawingBufferWidth,drawingBufferHeight)` call before every shared-canvas
    render. Symptom when regressed: overlay renders offset into the bottom-left quadrant on
    every phone, correct on desktop. Detail: docs/footguns-archive.md#fg16
17. **Never unmount `<WorldWideTelescope>`** once created. The engine's global texture/tile
    caches hold handles into the destroyed GL context and a remounted Sun renders black.
    `sol.vue` mounts `SolarView3D` once and never `v-if`s it. (`stage.setEnabled()` still
    exists to pause three work; since the disk view went it has no caller.)
    Detail: docs/footguns-archive.md#fg17
18. **WWT's depth buffer is not trustworthy for overlay depth-testing.** Its TileShader never
    sets depthMask and its planet passes write engine-internal values, so depth-testing our sun
    sphere against them let WWT's own Sun texture occlude the sphere completely. The
    shared-canvas pass therefore CLEARS the depth buffer at the start of every three render
    (`setupThreeWWT.ts`) and the sun-surface mesh is the authoritative occluder; in "Plain"
    surface mode it renders depth-only (colorWrite=false). Do not remove the clear or the
    depth-only mode: far-side field-line occlusion depends on both. (Browser-verified
    2026-08-23, HANDOFF §4.) Detail: docs/footguns-archive.md#fg18
19. **WWT's projection REVERSES triangle winding.** `Matrix3d.lookAtLH` +
    `perspectiveFovLH` (D3D: left-handed, clip w = +z_view, depth [0,1]) pass through
    `wwtMatrixToTHREE` verbatim (`det(P_wwt) = +1.166e-3` vs `det(P_three) = -2.332e-3`), and
    three picks winding from the OBJECT's `matrixWorld` only, never the camera.
    `src/three/winding.ts` owns it: `SOLID_SIDE = CAMERA_REVERSES_WINDING ? BackSide :
    FrontSide`, `FLAT_SIDE` (DoubleSide) for sprites. Since footgun 47's camera mirror cancels
    the reversal, `CAMERA_REVERSES_WINDING` is **false** and `SOLID_SIDE` is FrontSide.
    `assertWinding()` re-derives the sign each session. Wrong side looks like: texture seen
    through the sphere, surface at ~21% brightness, glow and spacecraft dots gone.
    Detail: docs/footguns-archive.md#fg19
20. **View-space z is POSITIVE in front of the camera** (same lookAtLH cause as 19). Anything
    ported from a three.js example that says `-mvPosition.z` is wrong here and will silently
    take the other branch of a `max()`. This pinned every solar-wind particle to the 6 px
    `gl_PointSize` ceiling at every zoom (the "wind is a white blob" report). Use `abs(mv.z)`.
    `src/three/project.ts` also assumes GL's [-1,1] NDC depth (`z > -1`); under D3D's [0,1]
    that bound is merely loose, not wrong (behind-camera still rejects via `z < 1`).
    Detail: docs/footguns-archive.md#fg20
21. **SDO browse stills: `latest_*_HMIBpfss.jpg` is framed differently from `latest_*_HMIB.jpg`.**
    GSFC renders the PFSS overlay onto a COMMON frame, so the pfss magnetogram is already at
    AIA's plate scale while the plain one is at HMI's. Measured limb diameter as a fraction of
    frame (identical across 1024/2048/4096): HMIB 0.9184, HMIBpfss 0.7676, 0171 0.7824,
    0171pfss 0.7893. `diskScaleFor(id, res, pfss)` in `sdoCatalog.ts` (no caller today) mirrors `stillUrl`'s
    variant choice exactly; change them together. The plain-HMI 0.8395 is measurement-backed
    (AIA 4500 0.7711 vs HMI 0.9168 = 0.8411, within 0.2% of the 0.5044/0.6009 plate-scale
    ratio). The EUV channels' limb really is ~1.5% larger (emission above the photosphere, not
    a framing error). Do not "correct" it away. (Footgun 59 measures the JSOC HMI disk at
    0.9265; the 0.8395 ratio was not re-derived.) Detail: docs/footguns-archive.md#fg21
22. **The sphere texture is MULTI-CHANNEL and not all AIA.** `TEX_CHANNELS` in
    `pipeline/config.py`, default first: 0171, 0304, 0193, HMIIC, HMIB. A channel that is not
    the default and fails is SKIPPED (additive contract); top-level `texture.json` fields
    describe the first channel's newest frame. Per-channel `scale` (AIA 0.6009"/px, HMI
    0.5044"), `farside` ("quiet" mottling for EUV only; HMI is "flat") and `ar_check` (EUV only)
    must be right or the map is dishonest. The app holds ONE 4096x2048 channel texture resident
    (≈ 32 MB GPU); do not raise `TEX_OUT_W/H` without measuring phone GPU memory.
    Detail: docs/footguns-archive.md#fg22
23. **DONKI numbers active regions 10000 higher than NOAA SRS does** (`14513` vs `4513`).
    `events/export.py` joins with `activeRegionNum - 10000`; a naive join matches ZERO regions.
    `run_events` prints the match rate every run. An `ar_index` of -1 is NORMAL: DONKI keeps
    reporting a region for days after it has left the SRS. Detail: docs/footguns-archive.md#fg23
24. **DONKI's old host `kauai.ccmc.gsfc.nasa.gov` had a black-holed AAAA record, and urllib
    has no Happy Eyeballs.** v6 comes FIRST and times out after 21.06 s before v4 answers in
    0.03 s; curl races the families and never notices. `io_utils._ipv4_only()` is a scoped
    `getaddrinfo` filter entered by `http_get_full(..., prefer_ipv4=True)` (events 47.3 s →
    5.4 s). Subclassing HTTPSConnection does NOT work (urllib never calls the override); don't
    "clean it up" that way. OPT-IN on purpose: SWPC and SDO resolve v6-first and are fine. It
    stays on for the new DONKI host (footgun 58), unmeasured. Detail: docs/footguns-archive.md#fg24
25. **A CME must NOT carry the Carrington quaternion the field lines use.** Field lines, solar
    wind and the surface rotate with Carrington (14.18 deg/day, 42.5 deg over 72 h); a CME
    travels along a fixed INERTIAL direction. `events.json` ships `dir_ecl` already in ecliptic
    J2000 and the app applies NO rotation to it. Surface-anchored parts (flash, arcade) DO stay
    Carrington-local, like `solarWind.ts`. Detail: docs/footguns-archive.md#fg25
26. **WWT's camera lat/lng has its poles at +/-Y, which IS the ecliptic pole**, so `lat` is
    ecliptic latitude and `lng` is ecliptic longitude minus 90. `cameraPosition =
    d*(-cos(lat)sin(lng), sin(lat), cos(lat)cos(lng))` (from `setupMatricesSolarSystem`,
    reproduced against the engine to 0.00e+00). Near the poles `lng` does nothing and the Sun's
    axis is only 7.25 deg away, so `sunStage.orbitByPixels` REPLACES the engine's solar-system
    `move()` and orbits about the SUN's axis; `clampCameraLat` bounds the angle to that axis.
    The drag signs (`AZIMUTH_SIGN` +1, `ELEVATION_SIGN` -1) cannot be derived on paper (a
    right-handed Rodrigues rotation in a LEFT-handed frame); both were confirmed through the
    engine's matrices after footgun 47 (drag right 150 px → +0.112 NDC x, drag down 110 px →
    -0.092 NDC y). Both signs stand. Detail: docs/footguns-archive.md#fg26
27. **`.solar-view-3d` carries `z-index: 0` for one reason: to create a stacking context.**
    With `z-index: auto` there is none, so its descendants (scrubber at 5, card slot at 20)
    compete directly with any SIBLING overlay in `sol.vue`; the branding mark once sat invisible
    at z-index 3 for a whole session. With the context in place a sibling only has to clear
    **0**, which is why `.sol-title` and `.sol-brand` work at 6. Do not "tidy up" the line;
    the symptom appears on a different element every time. Consequence, intentional:
    `.sol-title`/`.sol-brand` paint OVER `.sv-cover` (the black loading cover), because the
    title is rendered in `sol.vue` so it paints with the entry chunk.
    Detail: docs/footguns-archive.md#fg27
28. **An internally-scrolling flex panel needs `min-height: 0` on the container, the panel AND
    the grid item.** Miss any one and the content sets a floor on the item's height, the `1fr`
    row stops constraining anything, and the panel silently clips with no scrollbar. Also:
    `grid-template-rows` and `grid-template-areas` must declare the SAME number of rows, or the
    stage lands in an `auto` row and the WebGL canvas (no intrinsic height) collapses to
    nothing. Detail: docs/footguns-archive.md#fg28
29. **Off-limb structure cannot go on the sphere.** A disk image has no depth, so
    `texture/*_offlimb_*.jpg` is a camera-facing additive billboard (`src/three/offLimb.ts`)
    that FADES OUT with angle from the sub-Earth direction (past ~25-55 deg). Crop on the
    FITTED disk center, not the array center (12-14 px offsets on AIA). Black, not alpha (PNG
    costs several times the bytes). `half_width_rsun` is DATA (AIA 1.28, HMI 1.09). The
    validator asserts the disk center is black; keep that check.
    Detail: docs/footguns-archive.md#fg29
30. **NOAA's two SRS products disagree; never line them up by date.** `srs.txt`'s `:Issued:`
    date describes the PREVIOUS UT day, and `parse_srs` (Section I only) misses the spotless
    plage regions that `json/solar_regions.json` lists. `sources.srs.daily_history` uses the
    JSON for EVERY day. `fetch_regions_json` floors `numSpots` at 1, so sum spot COUNTS from
    `nSpotsRaw` (validator: `spot_count >= spotted_region_count`). History-day `regions`
    entries (`sol.ar/3`) carry NO `seed_count`. Detail: docs/footguns-archive.md#fg30
31. **CI must seed `dist-data` from the published tree, or `rsync --delete` eats the live
    product.** The whole failure policy (reuse a previous frame, roll back to the served copy,
    `MIN_FRAMES_TO_PUBLISH`) is written against `ctx.out` = what is published. `data.yml` checks
    out `origin/gh-pages -- data` into `dist-data` before the build, then runs `git reset`
    (that checkout also stages into the repo index). Measured 2026-08-23: without it one GONG
    outage deleted `data/pfss/` from gh-pages. Detail: docs/footguns-archive.md#fg31
32. **Never swallow an exception into an empty result.** `_scrape_gong` used to `return []` on
    everything, so a blocked runner looked like an empty day. It now prints the exception (or
    byte count, link count and regex when nothing matches). Keep every new
    swallow-and-continue path equally loud: degrade quietly for the guest, never quietly for
    the operator. Detail: docs/footguns-archive.md#fg32
33. **Current state: routed around since 2026-09-02; the block itself is unchanged.**
    `gong2.nso.edu` (A 146.5.21.69, no AAAA) silently drops every request from GitHub runners,
    so CI reaches GONG only through the relay (workstation mirror → `gong-cache` →
    `SOL_GONG_PROXY_*` secrets; first traced run 33663715169, `slots: 19/19`). If the mirror
    stops, CI stops tracing and frames age. Do NOT "fix" stale field lines by lowering
    `MIN_FRAMES_TO_PUBLISH` (6): check the mirror (footgun 56), then `PFSS-UPDATE.md`. Footgun
    55 is the mirror's own trap. Detail: docs/footguns-archive.md#fg33
34. **After a forced orphan push, the Pages build can wedge.** The commit Pages was told to
    build stops existing on the next publish. If the site stays stale or 404s after a publish,
    `gh api -X POST repos/<owner>/<repo>/pages/builds` (built in under a minute), but only per
    footgun 49's ordering. Detail: docs/footguns-archive.md#fg34
35. **One pipeline run per `--out` at a time.** `Staging` is the FIXED path `<out>/.staging`
    and `Staging.reset()` `rmtree`s it at the start of every run, so a second run deletes the
    first one's staged files and the first then publishes a manifest naming missing files, exit
    0. For parallelism give each run its own `--out`. Detail: docs/footguns-archive.md#fg35
36. **History texture frames are keyed on the slot's TARGET TIME, never its index**
    (`sdo0171_carr_2048x1024_20260820T1600Z.jpg`), and the PUBLISHED TREE is the only cache
    (footgun 31; `pipeline/.cache` does not survive a runner). Reuse requires `HIST_NAME_RE`: a
    slot DEMOTED from newest still names the stable newest file, which the same run just
    overwrote, so it must be REBUILT, never reused. `TEX_HIST_MAX_NEW_PER_RUN` (15, ~8 s per
    frame) bounds a run; a cap at or below the channel count never converges. Steady state per
    run, derived from the code: 5 newest + 5 hi-res (footgun 40) + 5 demoted rebuilds. Last
    measured (run 37301822199, mid-backfill after the JSOC switch): 54 reused, 15 built, 21
    deferred. Detail: docs/footguns-archive.md#fg36
37. **The GONG relay rewrites URLs at REQUEST TIME ONLY** (`sources/gong.py:_relay`). Every URL
    stored in a cache key, a manifest, or a log line stays canonical (`gong2.nso.edu`):
    `gong_file_key` derives the traced-frame cache key from the URL, so rewriting at the source
    would invalidate every cached frame whenever a relay changes; and the manifest cites that
    URL as provenance, where crediting our proxy for NSO's data would be wrong. Do not
    "simplify" this by setting `GONG_BASE` to the relay. `docs/GONG-RELAY.md` records what was
    ruled out (every host serving mrzqs, including anonymous FTP and sunpy's VSO client, is the
    same blocked IP). Detail: docs/footguns-archive.md#fg37
38. **The engine's touch AND pointer handlers must be no-opped at IMPORT TIME**, like
    `onGesture*` (footgun 10): `WWTControl.setup` binds them with `ss.bind('onTouchStart',
    this)`. `src/wwt/gestures.ts` owns touch input instead (reasons in its header): two engine
    two-finger paths BOTH call `zoom()` (a pinch applied ~the SQUARE of the ratio),
    `_rotating`/`_dragging` latch, and `targetTouches` EXCLUDES fingers on overlay elements. Do
    not try to fix these in place; four faults compound. Keep: listen on the **stage root in
    the capture phase**, and claim a pointer for the camera only when a SECOND one arrives
    (claiming the first breaks every button). Twist goes through `sunStage.addUserRoll()`
    (separate state; `orbitByPixels` recomputes `camera.rotation` every step). `TWIST_SIGN`
    (-1) is UNVERIFIED on a touch device. Detail: docs/footguns-archive.md#fg38
39. **No `backdrop-filter` over the shared canvas.** It is recomputed every frame the WebGL
    canvas repaints, static or not, and moving blurred label chips made dragging feel slow.
    Raise the plate alpha instead. Blur only off-canvas (the kiosk QR modal), and always add the
    `-webkit-` prefix. Detail: docs/footguns-archive.md#fg39
40. **8192 sphere maps and the limb guard.** `--with-hires` (on in every CI run, ~35-60 s per
    channel) adds a per-layer `high_res` 8192x4096 map of the newest frame (`sol.texture/4`);
    8192 because a 4096 map gives only 2048 px across a disk carrying ~3204 px of detail.
    `fit_limb` is the only check that catches SDO re-cropping. It fits at a FIXED
    `TEX_LIMB_FIT_RES = 2048` (the fitter creeps outward with sampling: 0304 +2.0% at 2048,
    +4.2% at 4096), with a +/-3% band (`TEX_LIMB_RADIUS_TOL`) centred on each channel's
    measured `limb_excess` (0171 -0.87%, 0304 +2.22%, 0193 +3.49%, HMI 0.0; 2026-10-04).
    `test_limb_band.py` asserts a 3.5% shift is still caught.
    **Never raise `TEX_LIMB_RADIUS_TOL`.** If a channel drifts, re-measure (~12 frames over two
    days) before changing its `limb_excess`, and record it. A failing channel carries its last
    good layer forward (T41). GPU is the constraint (~134 MB decoded): `sunSurface.hasHighRes()`
    reads `MAX_TEXTURE_SIZE` from the REAL renderer (`SolarView3D` must pass
    `rt.stage.renderer`), and the texture lives OUTSIDE `TEXTURE_BUDGET_BYTES`' LRU and is
    disposed explicitly. `?hires` defaults to auto (T35): wide screen, field lines loaded,
    disk ≥ 1600 buffer px (`HIRES_ON_PX`, off below 1300); `?hires=1` forces, `?hires=0`
    disables. Verify the gate in a VISIBLE tab. Detail: docs/footguns-archive.md#fg40
41. **Run background pipeline commands with `python -u`**, and call the env's `python.exe`
    directly (`conda run` buffers the child's stdout regardless). Without it a killed run leaves
    a zero-byte log. A killed run's `.staging` is wiped by the NEXT run's `Staging.reset()`, so
    look before re-running. Detail: docs/footguns-archive.md#fg41
42. **Sharing over `http://` needs a fallback AND a real selection.** On a LAN dev origin or a
    kiosk served from a LAN address, `isSecureContext` is false and `navigator.share` /
    `navigator.clipboard` are `undefined`. The fallback is `document.execCommand("copy")`,
    which needs the textarea's OWN selection (`focus()` + `setSelectionRange`), never a document
    Range: a Range over a textarea selects nothing while `execCommand` still returns `true`.
    Verify against `Get-Clipboard` from a real click, not the return value.
    Detail: docs/footguns-archive.md#fg42
43. **Vue scoped `:deep(.x)` compiles to a DESCENDANT selector, so it silently matches nothing
    when `.x` is the SAME element.** The desktop rail binds its classes onto child component
    ROOTS (`.sol-area-stats` IS `.sun-stats`, `.sol-area-layers` IS `.layer-panel`; only
    `.sol-area-info` wraps its panel). Scoped CSS stamps a child's root with the parent's scope
    id, so put the declarations directly on the item and drop the `:deep()`. Same family: the
    rail's gutter must be a **margin**, not padding (padding lands inside the border of the
    items that ARE the panel), and `.sun-stats`' `width: 100%` needs `width: auto` in the rail.
    Detail: docs/footguns-archive.md#fg43
44. **`grid-template-columns: repeat(auto-fit, minmax(150px, 1fr))` cannot express "2 or 4,
    never 3".** auto-fit does not know the item count, so between ~490px and ~640px it fitted
    THREE columns and the fourth chip orphaned. State the count: 2 columns, then 4 at
    `min-width: 640px` (4*150 + gaps + side padding). Verified across 280-899px: never 3, never
    1. Detail: docs/footguns-archive.md#fg44
45. **An overflow-scrolling overlay on the stage needs `data-camera-passthrough="false"`.**
    `gestures.ts`' `isControl` exempts `button, a, input, select, textarea, [role=button]` and
    that attribute; anything else a single finger lands on is claimed for the camera, so a panel
    scrolls or orbits depending on which 3px you touch. The layer popover is its first user.
    Detail: docs/footguns-archive.md#fg45
46. **CME layer (`src/three/cme.ts`).** Footgun 25 first: only the flare flash carries the
    Carrington quaternion. (a) A `Mesh` with no `position` attribute never renders, silently.
    (b) Never mix R_sun and AU in a point-size formula; multiply by `rSunAu` where the uniform
    is set. (c) Draw it as particles; smooth envelopes read as glass. (d) Never share one
    exposure constant across additive layers (particle 0.17, shock 0.5); re-sweep with the tab
    FOREGROUND. Detail: docs/footguns-archive.md#fg46
47. **WWT's solar-system world frame is ecliptic J2000 with Y and Z SWAPPED, and it is
    LEFT-HANDED.** `(x, y, z)_wwt = (X, Z, Y)_ecliptic`: ecliptic north is **+Y**, the ecliptic
    plane is **X-Z**, det = -1. With the reversing projection (footgun 19) the picture comes out
    physically right. The swap lives in the three CAMERA (`three-wwt/utils.updateTHREECamera` +
    `src/three/worldFrame.ts`), NOT the scene, which stays true right-handed ecliptic J2000.
    **Never "fix" it with a rotation**: `(x,z,-y)` and `(x,-z,y)` fix the tilt and leave the
    Sun spinning backwards. Keep `camera.matrixWorldAutoUpdate = false` (three would strip the
    reflection every frame), and `CAMERA_REVERSES_WINDING` stays false. The only independent
    check is WWT's own planet orbits: ours must coincide (`solDebug.setCamera(...)`).
    Detail (derivation and sign proofs): docs/footguns-archive.md#fg47
48. **Never edit `pipeline/` source while a pipeline run is in flight.** A lazily-imported stage
    reads your NEW file against an ALREADY-LOADED old one (`run_texture` imports
    `.texture.export` minutes in; `pipeline.config` loaded at startup), and dies with an
    `ImportError` for a name plainly on disk (`TEX_NEAR_FULL_W`). **The exit code was 0**
    (texture fails soft: `partial:texture`), so it looks like an upstream hiccup. Different from
    footgun 35: this is one run racing your editor. If a run is going, edit `src/` or the docs
    instead. Detail: docs/footguns-archive.md#fg48
49. **Do NOT `POST /pages/builds` immediately after `publish_gh_pages.sh`.** The push already
    triggers a build, and racing them fails BOTH (measured 2026-08-26: `failure` +
    `startup_failure`, site kept serving the previous tree). **Publish, wait, check, and only
    then POST if the live tree is still old** (a lone POST built in ~40 s). While it is
    happening `gh api .../pages/builds/latest` and `gh run list` disagree; check both.
    Detail: docs/footguns-archive.md#fg49
50. **Current state: mitigated since 2026-09-02 (T20 per-product validation), and the coupling
    is still real.** The PFSS seed set is frozen per traced run and its `ar_index` points into
    `regions.json` by position, which CI regenerates every 4 h. When frames go stale and the SRS
    lists fewer regions than at seeding, `ar_index` runs off the end (`range [-1,5] vs 5
    regions`). Today that degrades `pfss` alone; before T20 it discarded all six products. The
    fix is a retrace (relay or `PFSS-UPDATE.md`), which re-seeds. Do NOT loosen the validator
    bound, and do not put `Validate` back in front of `Publish` in `data.yml`.
    Detail: docs/footguns-archive.md#fg50
51. **NOAA publishes impossible region coordinates** (AR4521 at `latitude: 98`, a keying error
    for 9, 2026-09-01). `fetch_regions_json`, the only parser of that JSON, DROPS such a record
    with a `WARN … impossible record … dropped` line; its bounds mirror `validate.py`'s
    (`|lat| <= 60`). Never repair it from `srs.txt` (the products differ legitimately, footgun
    30) and never widen the validator bound. Since T20 one bad record degrades one product, not
    the publish (footgun 50). Detail: docs/footguns-archive.md#fg51
52. **A timestamp parsed from any upstream feed must be tz-aware before it reaches `unix_s`,
    `age_hours`, or a comparison.** SWPC's `rtsw_wind_1m.json` tags carry no zone and are UTC;
    `parse_iso_z` stamps UTC on a naive parse. A naive value shifts silently via
    `.astimezone()` (+5 h on this workstation, a no-op in CI) or raises `TypeError` inside
    `_existing_product`, leaving NO `index.json`. Test parsers on the workstation, not only in
    CI. Detail: docs/footguns-archive.md#fg52
53. **A CSS framework's RESET is part of what you remove.** Vuetify also shipped ress.css and
    an `html` rule, and five rules held the layout up: `box-sizing: border-box`,
    `* { margin: 0; padding: 0 }`, `button { font: inherit; background: transparent; border:
    none }` (21 buttons), `line-height: 1.5`, and `:root { color-scheme: dark }`; `#app`'s text
    colour came from `.v-application`. All are now explicit at the top of `common.less`. Before
    removing a framework, read its rules out of the BUILT vendor CSS; a diff of your own
    stylesheets shows nothing. And run `yarn build`, not just `yarn typecheck`: a `.vue`
    script-block type error passed typecheck and failed the build.
    Detail: docs/footguns-archive.md#fg53
54. **Any file whose bytes must survive git on this workstation needs `-text`.** A fresh
    `git init` inherits `core.autocrlf=true` from Git for Windows' SYSTEM config.
    `gong_mirror._ensure_local_repo` writes `* -text` into the state repo's `.gitattributes`,
    and files written for a parser need explicit LF bytes (not `Path.write_text` on Windows).
    Detail: docs/footguns-archive.md#fg54
55. **A relay that force-pushes must refuse to push nothing.** `gong_mirror.py` force-pushes one
    amended commit and never fetches `origin/gong-cache` first, so it publishes whatever its
    state dir holds. The zero-files check runs before the local repo is touched (`85e626c`).
    Accepted residual: a PARTIALLY wiped state dir still pushes. Know what is live before you
    replace it. Detail: docs/footguns-archive.md#fg55
56. **The GONG mirror stops silently and `Get-ScheduledTaskInfo` hides it afterwards.**
    `SolGongMirror` runs only at an INTERACTIVE logon with no stored password (not while off or
    logged out; locked is fine) and has `DisallowStartIfOnBatteries: True`. After it resumes,
    `LastRunTime`, `LastTaskResult 0` and `NumberOfMissedRuns 0` read healthy. **Diagnose by
    the date spread of `%LOCALAPPDATA%\sol-gong-mirror\logs\`** (last 15 runs, all within
    15 h if hourly). Do that before concluding anything about T22, which looks identical in a
    `data` log. Fix: re-register with a stored password and `-AllowStartIfOnBatteries`
    (`scripts/gong-mirror-task.ps1`, `docs/GONG-RELAY.md`); only the user can.
    Detail: docs/footguns-archive.md#fg56
57. **A hi-res `MemoryError` can drop the DEFAULT channel's 8192 map with nothing turning red.**
    0171 runs first, right after PFSS, and once failed to allocate 768 MiB. Before publishing a
    `--with-hires` run from the workstation, check that `grep 'hi-res 8192'` shows five lines.
    If one says `hi-res skipped`, re-run `pipeline texture --out public/data -v --with-hires`
    alone (~5 min, history reused). Detail: docs/footguns-archive.md#fg57
58. **CCMC moved the DONKI API on 2026-09-30; the old base 301s to an HTML news page.**
    `config.DONKI_BASE` is `https://ccmc.gsfc.nasa.gov/DONKI-API/get/` (no `/WS/`; that 404s).
    A JSON decode error at char 0 means a moved service: `curl -sI` the URL before assuming an
    outage. Since T28 `http_get_full(expect=...)` raises `UpstreamContractError` (`UPSTREAM
    MOVED: ...`) on an off-host redirect or HTML body, DONKI never serves its cache on one, and
    the cache is refused past 24 h. Detail: docs/footguns-archive.md#fg58
59. **HMI comes from JSOC.** GSFC stopped HMI browse frames 2026-09-24 without notice (every
    `latest_*.jpg` froze 2026-09-21). HMIIC/HMIB use `jsoc1.stanford.edu/data/hmi/images/`
    `YYYY/MM/DD/YYYYMMDD_HHMMSS_{Ic,M}_4k.jpg` (`source: "jsoc"`). **Do not "correct" its
    geometry**: it matches GSFC's own frames (radius 1897 px, correlation 0.999/1.000, limb
    +0.09%, disk fill 0.9265). It serves 4096 ONLY (`_load_rgb` asserts it) and has no `latest`
    fallback: nothing within 2 days fails the channel and T41 carries the last good layer.
    Probe: `.../hmi/images/image_times.json`. Detail: docs/footguns-archive.md#fg59

## Data sources (verified live 2026-08)

- SDO GSFC stills/movies: hotlinked, no CORS (see footguns 6-7). AIA browse frames only:
  GSFC's HMI browse frames stopped 2026-09-24 and every `latest_*.jpg` froze 2026-09-21.
- JSOC (Stanford) HMI images: the pipeline's source for HMIIC/HMIB since 2026-10-05,
  `jsoc1.stanford.edu/data/hmi/images/YYYY/MM/DD/`, 15 min cadence, 4096 only (footgun 59).
- NOAA SWPC (CORS *): tiny endpoints only in the browser (`xray-flares-latest`,
  `products/summary/*`, `noaa-planetary-k-index`, `noaa-scales`); the BIG files
  (`xrays-1-day.json` 654 KB, `rtsw_wind_1m.json` 2.9 MB, `solar-cycle/sunspots.json`) are
  digested server-side into `data/stats/summary.json`.
- Spacecraft: baked `data/ephem/spacecraft.json` (Horizons: PSP=-96, SolO=-144, Earth='399');
  live now-dot from `swhv.oma.be/position` (CORS *, ONE utc per call, no ranges).
- PFSS: our pipeline (GONG mrzqs + sunkit-magex, nrho=35, rss=2.5). Fallback (phase 2):
  LMSAL `fieldlines-YYYYMMDD-000400.json` (CORS *, single daily frame).
- PUNCH & Proba-3 have NO Horizons ids. Both orbit Earth; heliocentrically they ARE Earth.
- **CCMC DONKI** (`ccmc.gsfc.nasa.gov/DONKI-API/get/` since 2026-09-30; the old
  `kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/` base now 301s to a news page, footgun 58): flare +
  CME catalog, no API key. The old base sent `ACAO: *`; the new one sent no ACAO header when
  checked 2026-10-01, which does not matter while it is digested server-side. The ONLY source
  that gives a flare/CME a place and a direction: NOAA's `xray-flares-latest.json` has class
  and timing but no source location at all. Digested server-side into
  `data/events/events.json` (~4 KB). Ask for SHORT windows: 3 days is 0.74 s / 23 KB, a year
  is 32 s. It 403s on HEAD and 200s on GET, so probe with a GET. Not real-time: measured lag
  to publication is a median 1.9 h for flares, 7.5 h for CMEs (p90 16 h / 103 h), and records
  are back-filled and revised via `versionId`, so every run re-fetches the whole window and
  dedupes rather than appending. Do NOT use the `api.nasa.gov/DONKI` mirror (needs a key,
  rate-limits at 10, returned 503 when checked). DONKI's own terms call it "prototyping
  quality... research context"; that disclaimer ships in the product and must reach the
  guest-facing copy.
- **Coronagraphs WITH CORS** (unlike SDO, footgun 6): NOAA SWPC re-serves LASCO C2/C3 and
  CCOR-1/CCOR-2 at `services.swpc.noaa.gov/images/animations/<inst>/latest.jpg`, `ACAO: *`
  and a real `Last-Modified`. These CAN be fetched, canvas-read and used as WebGL textures.
  SWPC also publishes its operational WSA-ENLIL run as CORS-clean JPEGs: real MHD of the
  real CME, ~93 KB/frame, for free. (Not yet used by the app.)
