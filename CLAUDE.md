# Sol — the Sun Right Now

Mobile-first solar data explorer for planetarium guests ("Data to Dome, Dome to Phone").
Guests scan a QR code and see current solar conditions: live SDO imagery ("Sun Now" disk view),
the Sun's magnetic field in 3D over the last 72 hours (PFSS field lines from our own pipeline,
same model + colors as the dome show), Parker Solar Probe / Solar Orbiter positions, and live
NOAA space-weather numbers.

**Refreshing the field lines?** `PFSS-UPDATE.md` is the standalone runbook for it — the one
recurring operational chore this project has, and the only one that must be done from a machine
that can reach GONG (footgun 33). Follow it top to bottom; it needs no other context.

**Start here: `TASKS.md`** — the task ledger: what is in flight, what is next, and the
definition of done for each. Then **`HANDOFF.md`**, the living status doc (what is done,
partial, unstarted, and what has never been verified in a browser). Update both at the end of
any session that changes state.
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
conda run -n sdo python -m pytest pipeline/tests -q   # 53 tests, ~1 min; the tz table runs
                                                       # on THIS workstation on purpose (footgun 52)
python scripts/check_pipeline_names.py          # undefined globals; run BEFORE a long build
node scripts/check_label_layout.mjs             # label de-collision invariants
# fallback if conda run misbehaves:
& "$env:USERPROFILE\anaconda3\envs\sdo\python.exe" -m pipeline all --out public\data -v
```

## Architecture

- **Two tracks, one contract.** `src/` is the Vue app; `pipeline/` is the Python data pipeline
  that GitHub Actions runs every 4 h (`.github/workflows/data.yml`), publishing binary PFSS
  frames + JSON products to the `data/` subtree of `gh-pages`. The app fetches them same-origin.
  The contract (binary formats, manifest fields) is specified in the plan file — change it in
  BOTH places or not at all.
- **Validation is per product and happens INSIDE the pipeline, before promote** (since
  2026-09-02, T20). `cmd_all` runs `validate.validate_products()` against a
  staging-over-published overlay, rolls back only a product that fails its own checks (marking
  it `status: degraded` with `last_error`), and exits **0 whenever it promoted a tree**. The CI
  `Validate` step therefore runs AFTER `Publish` as a tripwire, and a `Verdict` step turns a
  degraded publish red without discarding it. Cross-product checks live with the CONSUMER
  (pfss and events check their `ar_index` against regions, not the other way round).
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
26. **WWT's camera lat/lng has its poles at +/-Y, which IS the ecliptic pole** — so `lat` is
    ecliptic latitude and `lng` is ecliptic longitude minus 90. `cameraPosition =
    d*(-cos(lat)sin(lng), sin(lat), cos(lat)cos(lng))`, derived from
    `setupMatricesSolarSystem` + `_rotationX/_rotationY/transform/_multiply` and re-verified
    against the engine on 2026-08-24 (it reproduces to 0.00e+00, as does the `lookUp` e1/e2
    basis). **This entry used to say +/-Y was "an arbitrary pair of points IN the ecliptic
    plane". That was exactly backwards and it is what footgun 47 is about** — the formula was
    always right, the axis labels were not. Consequences: near the poles `lng` does nothing,
    so horizontal drag goes dead there, and the Sun's own axis is only 7.25 deg away, so a
    guest looking over the solar pole lands in that dead zone. `sunStage.orbitByPixels`
    therefore REPLACES the engine's solar-system `move()` and orbits about the SUN's axis
    instead; `clampCameraLat` bounds the angle to that axis. The two drag signs
    (`AZIMUTH_SIGN` +1, `ELEVATION_SIGN` -1) cannot be derived on paper — `rotateAbout` is a
    right-handed Rodrigues rotation applied in a LEFT-handed frame, and the elevation axis
    `cross(solar_axis, u)` flips with which side of the Sun you are on. Both were re-confirmed
    after footgun 47 moved the axis ~90 deg, by replaying `orbitByPixels` in a Node harness
    and projecting a point painted on the Sun through the engine's own matrices: drag right
    150 px moves it +0.112 in NDC x, drag down 110 px moves it -0.092 in NDC y. Both follow
    the finger; both signs stand.
27. **`.solar-view-3d` carries `z-index: 0` for one reason: to create a stacking context.**
    It used to be `position: relative` with `z-index: auto`, which creates NONE — so its
    descendants (scrubber at 5, card slot at 20) competed directly with any SIBLING overlay in
    `sol.vue`, and the branding mark sat invisible at z-index 3 for a whole session. With the
    context in place a sibling only has to clear **0**, which is why `.sol-title` and
    `.sol-brand` work at 6. Do not "tidy up" the line: deleting it silently restores the old
    behavior, and the symptom appears on a different element every time.
    Note the consequence: `.sol-title`/`.sol-brand` at 6 therefore paint OVER `.sv-cover`
    (z-index 20 inside the context), i.e. on top of the black loading cover. That is
    intentional — the title is rendered in `sol.vue` so it paints with the entry chunk, before
    the engine downloads.
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
22. **The 3D sphere texture is MULTI-CHANNEL and is not all AIA.** `sol.texture/3`,
    `TEX_CHANNELS` in `pipeline/config.py` — FIVE products, default first:
    0171 "Coronal Loops", 0304 "Chromosphere", 0193 "Hot Corona", HMIIC "Visible
    Sun", HMIB "Magnetic Map". `run_texture` loops them and writes one
    `sdo{CODE}_carrington_4096x2048.jpg` each (265-800 KB, ~2.4 MB total) plus a
    `layers` array in `texture.json`. Each layer also carries a `frames` array
    of time-aligned history maps at 2048x1024 (footgun 36). The top-level
    fields still describe the FIRST channel's NEWEST frame, so a schema-1
    reader stays correct. A non-default channel that fails is SKIPPED, not
    fatal; the default failing still propagates.
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
    `sol.ar/3` gives each history day its own `regions` array (positions, not
    just counts) so the surface markers can follow the playhead. Those entries
    deliberately carry NO `seed_count`: the frozen seed set describes TODAY's
    trace, and a number there would imply field lines that were never traced.

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

34. **After a forced orphan push, the Pages build can wedge — kick it with an
    explicit `POST /pages/builds`.** Enabling Pages on `gh-pages` produced two
    builds that `errored` with the useless message "Page build failed", then one
    that sat at `building` for over five minutes with the site still 404. The
    branch was fine (`.nojekyll` present, 60 files, 11.8 MB). What cleared it
    was `gh api -X POST repos/<owner>/<repo>/pages/builds`, which built in under
    a minute. The likely cause is our own design: `publish_gh_pages.sh`
    force-pushes a single orphan commit, so the commit Pages was told to build
    stops existing on the next publish. If the site 404s after a publish, ask
    for a build before believing anything is broken.

35. **One pipeline run per `--out` at a time.** `Staging` is `<out>/.staging`, a FIXED path,
    and `Staging.reset()` `rmtree`s it at the start of every run. So a second `python -m
    pipeline <stage>` against the same output root deletes the first one's staged files
    mid-flight — and the first run then promotes whatever survived and writes a manifest
    referencing files that no longer exist. Measured 2026-08-23: a `regions` run wiped 14 of
    18 staged texture files out from under a running `texture` run, which then published a
    `texture.json` naming 15 history frames of which 4 were on disk. Nothing raised; the
    exit code was 0. If you want parallelism, give each run its own `--out`.
36. **History texture frames are keyed on the slot's TARGET TIME, never its index — and the
    PUBLISHED TREE is the only cache.** `sdo0171_carr_2048x1024_20260820T1600Z.jpg`, not
    `_f04.jpg`. Indices shift every run (slot 18 becomes slot 17 four hours later), so an
    index-keyed name would make all 95 files look new every four hours and the stage would
    re-reproject the entire window forever. With a time-keyed name, "already published" is a
    filename existence check, and "orphan" is exactly "outside the current window".
    The reuse depends entirely on footgun 31's seeding: CI reads the previous `texture.json`
    and the existing JPEGs out of `ctx.out`, which is only populated because `data.yml`
    checks out `origin/gh-pages -- data` first. `pipeline/.cache` does NOT survive a runner.
    Measured cost per new frame is ~8 s (fetch + limb fit + 3-plane reproject at 2048x1024),
    so `TEX_HIST_MAX_NEW_PER_RUN` bounds the CI job; net progress is
    `cap - len(TEX_CHANNELS)` per run, because one new slot per channel scrolls into the
    window every 4 h just to stand still. A cap at or below the channel count never
    converges. Locally, `--max-new-textures 200` fills the whole window in one ~13 min pass.
    **A slot DEMOTED from newest to history must be REBUILT, never reused** — the subtlest
    part of this, and it shipped broken once. The newest map's filename is deliberately
    stable and NOT time-keyed (`sdo0171_carrington_4096x2048.jpg`), so when the window
    advances the previous newest slot becomes a history slot whose published url still names
    that stable file — and the file is still on disk, because the same run just overwrote it
    with the NEW newest frame. The reuse check therefore accepted it and published TWO target
    times pointing at ONE file, the older of them showing the newer Sun. `_texture_history`
    now requires `HIST_NAME_RE` to match before reusing anything. Note this is invisible to
    any test that does not cross a 4 h boundary: a same-window re-run reuses everything and
    passes. The validator caught it (`0171 frame 14 is 2048x1024 -- got 4096x2048`), which is
    the argument for asserting a frame's declared size against the file rather than trusting
    the manifest. Steady state is therefore 5 newest maps + 5 demoted-slot rebuilds per run.
37. **The GONG relay rewrites URLs at REQUEST TIME ONLY** (`sources/gong.py:_relay`). Every
    URL stored in a cache key, a manifest, or a log line stays canonical
    (`gong2.nso.edu`) — two reasons, and both matter. `gong_file_key` derives the traced-frame
    cache key from the URL, so rewriting at the source would invalidate every cached frame the
    moment a relay is added, changed or removed; and the published manifest cites that URL as
    provenance, where crediting our own proxy for NSO's data would be simply wrong. Do not
    "simplify" this by setting `GONG_BASE` to the relay. See `docs/GONG-RELAY.md` for why a
    relay is needed at all and what was ruled out by measurement (every host serving the mrzqs
    product — including anonymous FTP and sunpy's VSO client — is the same blocked IP).

38. **The engine's touch AND pointer handlers must be no-opped at IMPORT TIME**, exactly
    like `onGesture*` (footgun 10) — `WWTControl.setup` binds them with
    `ss.bind('onTouchStart', this)`, capturing the method reference, so a patch applied after
    `initControl` is never seen. `src/wwt/gestures.ts` owns touch input instead, and the
    reasons are in its header with engine line numbers: the engine ships TWO independent
    two-finger implementations bound to the same canvas (`touch*` and `pointer*`) and BOTH
    call `zoom()`, so a pinch applied roughly the SQUARE of the intended ratio — and because
    the two have different gates (`_twoTouchEvents > 10` vs. none) the gain also changed
    abruptly mid-gesture. `_rotating` and `_dragging` both latch for the rest of a gesture,
    and two-finger mode is decided from `targetTouches`, which EXCLUDES any finger that
    landed on an overlay element — which is why a pinch starting on a 44 px region chip
    silently became an orbit. Do not try to fix these in place; four faults compound.
    Two consequences worth keeping: our module listens on the **stage root in the capture
    phase** (that is what lets a finger on a chip count toward a pinch), and it claims a
    pointer for the camera only when a SECOND one arrives — claiming the first would break
    every button on the stage. Two-finger twist goes through `sunStage.addUserRoll()`, which
    is separate state, because `orbitByPixels` recomputes `camera.rotation` from scratch every
    drag step to keep solar north up and would otherwise erase a roll on the next pan.
    `TWIST_SIGN` is a named constant and is UNVERIFIED on a touch device, for the same reason
    `AZIMUTH_SIGN`/`ELEVATION_SIGN` are named: the sign cannot be derived reliably through a
    left-handed view matrix and a y-down screen.
39. **`backdrop-filter` over the shared canvas costs a blur EVERY FRAME, moving or not.** A
    backdrop-filter is recomputed whenever its backdrop changes, and the backdrop here is a
    WebGL canvas repainting at the full frame rate — so a static blurred panel is not free,
    and a blurred panel that also MOVES every frame (the label chips did) is the reported
    "framerate feels low on the labels as we drag around the sun". HANDOFF §8.4 already
    specified "NO backdrop-filter — a solid plate doesn't need it" and flagged the risk at
    20 Hz; the shipped code had it at 60. Raise the plate alpha instead. Blur is affordable
    only where it is NOT over the canvas (the kiosk QR modal) — and if you add one, add the
    `-webkit-` prefix too, or older Safari silently skips it and the page looks fine on the
    one device you tested.

40. **The opt-in 4K sphere texture: why it needs an 8192-wide map, and why 0304 does not get
    one.** `--with-hires` publishes a per-layer `high_res` block (`sol.texture/4`) holding a
    single 8192x4096 map of the NEWEST frame only, built from SDO's 4096 px browse still
    instead of the usual 2048.
    **Why 8192 and not 4096:** half of a plate-carree map is the visible hemisphere, so a
    4096-wide map gives only 2048 px across a disk that carries ~3204 px of real detail in a
    4096 source (the disk fills 0.7824 of an AIA frame, footgun 21). The normal map was
    therefore throwing away most of a 4K frame, and 8192 is the width that actually shows it.
    **0304 is EXCLUDED, and this is the guard working, not a bug.** Measured 2026-08-23, the
    limb fit against the synthesized WCS:
      2048 source: r_fit 807.4 vs r_pred 789.4  = +2.28%  (inside TEX_LIMB_RADIUS_TOL's 3%)
      4096 source: r_fit 1644.8 vs r_pred 1578.8 = +4.18%  (REFUSED)
    `r_pred` doubles exactly with the source resolution; `r_fit` does not — it comes out 30 px
    wider than twice the 2048 fit. The fitter finds a systematically larger limb at higher
    sampling, and 0304 is He II 304 A, the AIA channel with the most extended chromospheric
    limb brightening: a diffuse edge, so more ray samples cross it further out. **Do NOT
    "fix" this by raising `TEX_LIMB_RADIUS_TOL`.** That tolerance exists to catch SDO
    re-cropping the browse product, which would silently ship a map misregistered by several
    percent — exactly what footgun 21 is about. A 4% radius error displaces every feature on
    the disk. The failure is SOFT by design: the channel simply has no `high_res` key
    (additive-only contract, footgun 22), the app hides the option for it, and four of five
    channels still get 4K. If it must be fixed properly, fix the FITTER to be
    resolution-independent — and note that doing so risks the already-validated 2048 path.
    **GPU, not bytes, is the binding constraint.** 8192x4096 RGBA is ~134 MB decoded, against
    ~1.1-3.6 MB on the wire. Many mobile GPUs cap `MAX_TEXTURE_SIZE` at 4096, where loading it
    fails outright — so `sunSurface.hasHighRes()` reads
    `gl.getParameter(gl.MAX_TEXTURE_SIZE)` from the REAL renderer and returns false when it
    does not fit. It also returns false when no renderer was passed, which fails closed but
    silently disables the feature: `SolarView3D` must keep passing `rt.stage.renderer`.
    The texture is held in its own slot OUTSIDE `TEXTURE_BUDGET_BYTES`' LRU, because at 3x the
    whole budget it would evict everything else on sight; it is never an eviction candidate and
    must be disposed explicitly.
    **Never enable this in CI.** Each 8192 reprojection is ~3 minutes (4x the pixels of the
    normal map, three colour planes each), so a five-channel run is ~16 min against a ~9 min
    job budget. It is a workstation/dome option, published by hand.
41. **Run background pipeline commands with `python -u`.** Without it, stdout is block-buffered
    and a run that gets killed — a tool timeout, a Ctrl-C — leaves a **zero-byte log** even
    though it did minutes of work and left files in `.staging`. Measured: a `--with-hires` run
    was reported as exit 0 with an empty log and no published output, and the only evidence of
    what happened was the mtimes on the staging files. `-u` costs nothing and is the difference
    between a diagnosis and a re-run. (See also footgun 35: a killed run leaves `.staging`
    behind, and the NEXT run's `Staging.reset()` will delete it, so there is exactly one chance
    to look.)
42. **Sharing over `http://` needs BOTH a fallback and a working selection — and
    `execCommand("copy")` will lie to you.** On the LAN dev origin and on any locally served
    kiosk (`http://192.168.1.121:8080`), `isSecureContext` is false, so `navigator.share` and
    `navigator.clipboard` are **both `undefined`** — the old share button reached through the
    latter, threw `TypeError: Cannot read properties of undefined (reading 'writeText')` into a
    bare `catch`, and did nothing at all, silently, on every phone testing over LAN. The
    surviving route is `document.execCommand("copy")`, which predates the secure-context rules.
    Its trap: it copies a live SELECTION, and a `<textarea>`'s value is **not DOM text** —
    assigning `.value` creates no child node, so `Range.selectNodeContents(area)` selects
    NOTHING while `execCommand` still returns **`true`**. Measured 2026-08-24: the button showed
    its success check and the OS clipboard still held its previous contents. Use the textarea's
    own selection (`focus()` + `setSelectionRange`), never a document Range, and verify a copy
    path against `Get-Clipboard` rather than against the return value. It also needs transient
    user activation, so a `javascript_tool` probe returns false even when the code is correct —
    test it from a real click.
43. **Vue scoped `:deep(.x)` compiles to a DESCENDANT selector, so it silently matches nothing
    when `.x` is the SAME element.** The desktop rail binds its classes onto child component
    ROOTS (`.sol-area-stats` IS `.sun-stats`, `.sol-area-layers` IS `.layer-panel`; only
    `.sol-area-info` wraps its panel). A `.sol-area-stats { :deep(.sun-stats) { border… } }`
    block therefore styled no element in the document, and the stats card shipped for a whole
    session with a computed `border: 0px none` and a transparent ground while its comment
    described the framing it was supposed to have. Scoped CSS stamps a child's root with the
    parent's scope id, so put the declarations directly on the item and drop the `:deep()`.
    Same family of bug: the rail's gutter must be a **margin**, not padding — on the two items
    that ARE the panel, padding lands inside the border, so those panels spanned the whole
    column (hard against the window edge, 1251..1920 in a 1920px window) while the wrapped one
    was inset to 1263..1908. And `.sun-stats`' own `width: 100%` then needs `width: auto` in the
    rail, or that 100% resolves against the grid AREA and the margins push it back out.
44. **`grid-template-columns: repeat(auto-fit, minmax(150px, 1fr))` cannot express "2 or 4,
    never 3".** auto-fit does not know the item count, so between ~490px and ~640px of stats
    width it fitted THREE columns and the fourth chip orphaned onto its own row. Four items want
    the count stated: 2 columns, then 4 at the width where all four actually fit (`min-width:
    640px` = 4*150 + gaps + the side padding). Verified across 280-899px: 2 up to 639, 4 from
    640, never 3, never 1.
45. **An overflow-scrolling overlay on the stage needs `data-camera-passthrough="false"`.**
    `gestures.ts`' `isControl` exempts `button, a, input, select, textarea, [role=button]` and
    that attribute; anything else a single finger lands on is claimed for the camera. So the
    layer popover's ROWS (buttons) scrolled while its padding, its "Surface" heading and the
    gaps between rows orbited the Sun instead — a panel that scrolls or not depending on which
    3px of it you touch. The attribute is the intended escape hatch and the popover is its first
    user. Verified by synthetic PointerEvents: the drag inside the panel leaves
    `solDebug.camera` untouched, the identical drag on open sky moves lat by 9 degrees.

46. **The CME layer (`src/three/cme.ts`), and four things it cost to learn.** It draws DONKI's
    own cone-model fit — `dir_ecl` + `half_angle_deg` + the two published timestamps — as a
    particle cloud with one smooth shock shell. Read footgun 25 first: the cone group carries
    NO Carrington quaternion, only the flare flash does.
    (a) **A `Mesh` whose geometry has no `position` attribute is silently never rendered** —
    no error, no warning, and `material.program` stays undefined because three never compiles
    it. The flare flash had its corners in a custom `aCorner` attribute plus a valid index and
    a hand-set `boundingSphere`, and drew nothing for an hour of debugging. Put the corners in
    `position`. (Also: `material.program` no longer exists in modern three, so "no program" is
    not a diagnosis.)
    (b) **A point-size formula mixing R_sun and AU reproduces footgun 20's symptom from a new
    cause.** `uSize * uRadius * uPixelScale / abs(mv.z)` with `uRadius` in R_sun and `mv.z` in
    AU computed a want of **986 px against a 64 px ceiling** — all 3,000 particles pinned to
    maximum size at every zoom, 12.3M fragments a frame of pure overdraw, and a cloud that got
    coarser as the guest pulled back. Multiply the size by `rSunAu` where the uniform is set.
    (c) **Smooth envelopes read as glass; only particles read as gas.** Four rounds of tuning a
    shaded cone-and-cap surface (limb brightening, two limb exponents, filament noise, nested
    shells) never stopped it looking like a solid object — a 45 deg half-angle envelope at
    10 R_sun is an enormous smooth sheet, and there is no shading model that saves it. The
    particle version is also CHEAPER (3,000 vertices against ~2,000 triangles).
    (d) **Two additive layers must not share one exposure constant.** A per-PARTICLE alpha
    (0.17, and it took a sweep from 1.0 through 0.06 to find) and a per-SURFACE alpha (0.5) are
    three orders of magnitude apart in what they mean; when the shock read the cloud's number
    it vanished. `brightnessAt()` returns a normalized 0-1 curve and each layer scales it
    itself. Additive blending has no highlight rolloff, so these numbers are the whole
    difference between plasma and poster paint — re-sweep them at the screen if the point count
    or size changes, and do it with the tab FOREGROUND (a hidden tab suspends rAF, so the
    render is frozen and the replay crawls).

47. **WWT's solar-system world frame is NOT ecliptic J2000. It is ecliptic J2000 with Y and Z
    SWAPPED, and it is LEFT-HANDED.** `(x, y, z)_wwt = (X, Z, Y)_ecliptic` — the ecliptic
    north pole is **+Y**, the ecliptic plane is **X-Z**, det = -1. This is the single most
    load-bearing fact about the engine and the app asserted its opposite for four sessions:
    a guest reported the Sun tilted ~90 deg out of the planets' orbital plane and possibly
    rotating backwards, and it was both.
    **Why it is a mirror and why that is correct.** The engine renders with `lookAtLH` +
    `perspectiveFovLH` (footgun 19), so its world->clip transform is orientation-reversing.
    A left-handed world frame plus an orientation-reversing projection cancel, and the picture
    comes out physically right. Hand WWT a properly RIGHT-handed copy of the solar system and
    it draws a MIRROR IMAGE of it. So the two "handedness-preserving 90 deg rotations about X"
    that look like the obvious fix, `(x,z,-y)` and `(x,-z,y)`, are both WRONG: measured through
    the engine's own matrices, each fixes the tilt and leaves a fixed solar feature crossing
    the disk right-to-left. Only the odd permutation restores east->west.
    **Where the derivation comes from.** Every planet and orbit the engine draws is built by
    exactly two steps (`Planets.updatePlanetLocations` / `updateOrbits`):
    `Coordinates.raDecTo3dAu(RA, dec, r)` — which writes `(cos.cos, SIN DEC, sin.cos)`, i.e.
    declination into Y — followed by `rotateX(Planets._obliquity)`. Push arbitrary ecliptic
    vectors through those two functions and they come back as `(x, z, y)` to 9e-8, the residual
    being only the engine's truncated `RC = 3.1415927/180`.
    **How the sign was pinned, since neither half can be settled by eye.** (a) POSITION,
    against INCLINED orbits: WWT's own ephemeris vs our Kepler elements gives residuals against
    `(x, z, y)` of 0.002 AU (Earth) to 0.05 AU (Jupiter) — ephemeris-sized — while against
    `(x, -z, y)` the out-of-plane component is wrong by twice the true offset: 0.79 AU on
    Saturn, 0.11 AU on Jupiter. **Earth alone cannot decide this**; it is in the ecliptic, so
    it looks identical under both. (b) HANDEDNESS, against MOTION: finite-difference WWT's own
    planet positions and take `r x v` right-handed. In our ecliptic frame that is +Z for every
    planet (prograde); in WWT's world frame it is **-Y** for every planet while the ecliptic
    pole maps to +Y. `h_world = -M(h_ecliptic)` is the signature of det(M) = -1.
    **The fix, and the two things welded to it.** The swap is folded into the three CAMERA
    (`three-wwt/utils.updateTHREECamera` + `src/three/worldFrame.ts`), NOT into the scene, so
    the whole three.js scene stays in true right-handed ecliptic J2000 and no site that mixes
    camera with data has to know. That requires `camera.matrixWorldAutoUpdate = false`, because
    three's `Camera.updateMatrixWorld` decomposes matrixWorld and rebuilds matrixWorldInverse
    with the scale forced to (1,1,1) "to be glTF conform" — a reflection decomposes to
    (-1,1,1), so it would silently STRIP the transform every frame. And it flips
    `winding.CAMERA_REVERSES_WINDING` to **false**: the projection's reversal and the frame's
    mirror now cancel, so `SOLID_SIDE` is FrontSide. `assertWinding()` re-derives that from
    the live camera and is the tripwire if any of it is ever undone.
    **Why nothing caught it.** Every existing cross-check — the pipeline's
    `_assert_conventions`, the `?debug=1` axis triad and sub-Earth check, `assertWinding`,
    `b0DegApprox` — is INTERNAL to the app's own convention. The Sun mesh, field lines,
    spacecraft trails, CME cone and the camera framing all used "+Z is the pole" consistently,
    so they agreed with each other perfectly while all being 90 deg wrong together. **The only
    independent reference in the scene is WWT's own `solarSystemOrbits` / `solarSystemPlanets`
    rendering.** Turn the "Planet orbits" layer on and draw our own planet orbits over it: they
    must coincide. `solDebug.setCamera({distanceAu, latDeg, lngDeg})` exists to make that check
    one call — it writes BOTH cameras, so a single frame is enough and it works in a background
    tab where the engine's easing does not. The pipeline was NOT implicated: it uses astropy's
    `HeliocentricMeanEcliptic` and was always right.

48. **Never edit `pipeline/` source while a pipeline run is in flight** — a lazily-imported
    stage will read your NEW file against an ALREADY-LOADED old one. `run_texture` does
    `from .texture import export as texture_export` at call time, several minutes into a run,
    while `pipeline.config` has been in `sys.modules` since startup. Edit both and the late
    import reads the new `export.py`, asks the *old* config module for a constant that only
    exists in the new file, and dies: `ImportError: cannot import name 'TEX_NEAR_FULL_W' from
    'pipeline.config'` — pointing at a name that is plainly right there on disk, which is what
    makes it confusing. Measured 2026-08-26. **The exit code was 0**, because the texture
    stage's failure is soft by design: five of six products rebuilt, texture rolled back to the
    published copy, `last_attempt_status` came out `partial:texture`, and the whole thing looked
    like an upstream hiccup rather than a self-inflicted one. Related to footgun 35 (one run per
    `--out`) but a different mechanism: that one is about two runs racing on `.staging`, this one
    is about one run racing your editor. If a run is going, edit `src/` or the docs instead.

49. **Do NOT `POST /pages/builds` immediately after `publish_gh_pages.sh` — the push already
    triggers a build, and racing them fails BOTH.** Measured 2026-08-26: the force-push at
    15:15:58 auto-triggered a build at 15:16:04, the explicit POST triggered a second at
    15:16:06, and they came back `failure` and `startup_failure` respectively while the API's
    "latest build" sat at `building` and the site kept serving the previous tree. A single POST
    once nothing else was in flight built cleanly in ~40 s and the new files appeared.
    This REFINES footgun 34 rather than replacing it: an explicit build request is still the fix
    when a publish leaves the site stale, because a forced orphan push can leave Pages pointing
    at a commit that no longer exists. The order matters — **publish, wait, check, and only then
    POST if the live tree is still old.** Note the two views disagree while this is happening:
    `gh api .../pages/builds/latest` reported `building` for a run that
    `gh run list` already showed as `startup_failure`, so check both before concluding anything.

50. **A stale PFSS product does not stay contained — it eventually fails the validator and
    blocks the WHOLE publish.** The seed set is frozen per traced run and its `ar_index` column
    points into `regions.json` by position. CI regenerates `regions.json` every 4 h but (footgun
    33) cannot retrace the field, so on the day NOAA's SRS lists fewer regions than it did when
    the seeds were frozen, the topology's max `ar_index` runs off the end of the current list.
    Measured 2026-08-30: seeds frozen against six regions, SRS down to five, and the run died at
    `FAIL ar_index within regions.json bounds -- range [-1,5] vs 5 regions`. `Validate` ran
    BEFORE `Publish` in `data.yml` (until 2026-09-02, T20), so **the five products CI *can*
    build were discarded too** —
    the site fell 13 h behind on everything, not just on field lines. For eleven sessions the
    working assumption had been that stale PFSS degrades exactly one product; it does not, it
    just takes a day or two to bite. The fix is a rebuild from a GONG-reachable machine
    (`PFSS-UPDATE.md`), which re-seeds against today's regions. Do NOT "fix" it by loosening the
    validator: the bound is what stops a frame's `ar_index` from anchoring a field line to a
    region that is not there, and the coupling it exposes is real. The permanent fix is the
    relay (TASKS.md T2).

51. **NOAA publishes impossible region coordinates, and one of them blocks the WHOLE publish.**
    Measured 2026-09-01: `json/solar_regions.json` carried AR4521 at `"latitude": 98` on
    09-01 having carried the same region at `9` on 08-31, with `srs.txt` independently
    reporting `N09E67` for it — a keying error at NOAA (98 for 9), not a parse error here.
    `validate` range-checks every history region (`|lat| <= 60`; anything beyond the activity
    belts is a parse error, not a sunspot), so the `data` run at 13:26Z died on
    `FAIL history 2026-09-01 AR4521: lat_deg within +/-60 -- got 98.0`. **This is footgun 50's
    coupling from a completely different cause:** `Validate` ran before `Publish`, so one bad
    record 30 days deep in someone else's feed discarded the five products CI had just built
    correctly and left the site 11.5 h stale on everything. Expect this class of thing again —
    the SRS is hand-keyed.
    **The coupling itself was removed on 2026-09-02 (T20):** the pipeline now validates each
    product against a staging-over-published overlay BEFORE promoting and rolls back only the
    product that fails (`cli.py` `cmd_all`, `validate.validate_products`), `pipeline all` exits 0
    whenever it promoted a tree, and `data.yml` publishes first and validates after as a
    tripwire, with a `Verdict` step that turns a degraded publish red instead of discarding it.
    Footguns 50 and 51 remain the record of WHY that structure exists; do not put the validate
    step back in front of publish.
    **The fix is at the source, and it DROPS the record rather than repairing it.**
    `fetch_regions_json` is the only place that JSON is parsed, so it is the only place that
    has to reject it; the bounds there deliberately mirror `validate.py`'s region checks, so
    whatever the source keeps the validator must accept. Repairing the latitude from `srs.txt`
    was the tempting alternative and is wrong: the two products legitimately disagree by epoch
    and by region set (footgun 30), so a source that patched one from the other would invent
    positions on the days they differ for a real reason. One region missing from one day's
    sunspot chip is a rounding error to a guest; a marker drawn at a latitude nobody measured
    is a lie printed over imagery that shows the truth. The drop prints a `WARN … impossible
    record … dropped` line naming the region and every value, per footgun 32 — degrade quietly
    for the guest, never quietly for the operator.
    Do NOT instead widen the validator's bound. It is the only thing standing between a
    hand-keyed feed and a sunspot marker at latitude 98.

52. **Zone-less SWPC time tags are UTC, and `parse_iso_z` used to hand them back NAIVE — which
    is a +5 h shift on this workstation and a no-op in CI.** NOAA's `rtsw_wind_1m.json`
    publishes `"time_tag": "2026-09-02T15:23:00"` (no `Z`, no offset) while the GOES flare
    product carries a `Z`. `datetime.fromisoformat` returns a naive value for the former, and
    `io_utils.unix_s`'s `.astimezone()` on a naive datetime means "assume the SYSTEM zone":
    UTC on a GitHub runner, **Central time here**. So every hand-publish (T1, nine of them)
    shipped a wind series five hours in the future. Measured 2026-09-02 minutes after the ninth:
    live `windWindow.points` ended at **20:00Z with the clock at 15:40Z**, five future points
    and a 5 h hole where CI's UTC points met the workstation's shifted ones.
    `_merge_wind_series` writes into a persistent cache (`pipeline/.cache/wind.json`), so the
    poison survived runs; it self-healed at each successful CI run and recurred at each
    hand-publish, and nothing caught it because the validator checked `stats/summary.json` for
    `schema` and `carrington` only. Fixed at the source — `parse_iso_z` stamps UTC on a naive
    parse — plus validator checks that wind points are strictly increasing and never later
    than `generated_iso`. The general rule: **a timestamp parsed from any upstream feed must be
    tz-aware before it reaches `unix_s`, `age_hours`, or a comparison.** A naive one either
    shifts silently (`astimezone`) or raises `TypeError: can't compare offset-naive and
    offset-aware` — and that `TypeError` inside `_existing_product`, which runs inside the
    failure handler, escapes `cmd_all` and leaves the run with NO `index.json`. Test the parser
    on the workstation, not only in CI: the bug is invisible in every UTC environment, which is
    exactly why four sessions of green CI runs never saw it.

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
