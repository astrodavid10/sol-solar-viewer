"""Tunable constants for the Sol pipeline.

Numbers here are *measured*, not guessed: NRHO/RSS come from the dome
pipeline (1.8 s/solve; a coarser grid buys nothing visible), the seed grid is
the dome's 40x80 dome grid reduced to a mobile budget, and VERT_BUCKETS was
sized so a 19-frame 72 h window lands near 2.2 MB total on the wire.
"""

from __future__ import annotations

import os
from typing import Dict, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Identity
# ─────────────────────────────────────────────────────────────────────────────

PIPELINE_VERSION = "1.0.0"
# Sent to GONG, NOAA SWPC, SDO and CCMC on every request. Keep the URL
# pointing at the real repo: it is how an upstream operator reaches us if
# this pipeline ever misbehaves against their service.
USER_AGENT = ("sol-pipeline/{0} "
              "(+https://github.com/astrodavid10/sol-solar-viewer)").format(
    PIPELINE_VERSION)
HEADERS = {"User-Agent": USER_AGENT}

# Schema identifiers written into every product (the app pins on these).
SCHEMA_INDEX = "sol.index/1"
SCHEMA_PFSS = "sol.pfss/1"
SCHEMA_EPHEM = "sol.ephem/1"
SCHEMA_AR = "sol.ar/3"        # /2 adds `history`; /3 adds its positions
SCHEMA_STATS = "sol.stats/1"
SCHEMA_TEXTURE = "sol.texture/4"   # /3 adds per-layer `frames`; /4 adds `high_res`
SCHEMA_EVENTS = "sol.events/1"

# ─────────────────────────────────────────────────────────────────────────────
# PFSS model
# ─────────────────────────────────────────────────────────────────────────────

NRHO = 35                 # radial grid points between 1 R_sun and RSS
RSS = 2.5                 # source-surface radius (R_sun)
MAX_TRACE_STEPS = "auto"  # measured: better lines than the dome's 3000 cap
SOLVER_NAME = "sunkit-magex 1.1.0"

# Quantization half-range.  Traced vertices live in [-RSS, RSS]; 2.6 leaves a
# little headroom so a vertex landing exactly on the source surface (or a hair
# outside from the tracer's final step) never clips.
LIM_RSUN = 2.6

# ─────────────────────────────────────────────────────────────────────────────
# Seeds
# ─────────────────────────────────────────────────────────────────────────────

BG_NLAT, BG_NLON = 24, 48        # background grid (dome uses 40x80)
BG_LAT_LIMIT_DEG = 75.0
BG_HEIGHT_RS = 1.01
REGION_MIN_SEEDS, REGION_MAX_SEEDS = 12, 45
REGION_HEIGHTS: Tuple[float, ...] = (1.005, 1.010, 1.020)
SEED_HARD_CAP = 2000
SEED_RNG_SEED = 20260523         # same constant as the dome pipeline

# ─────────────────────────────────────────────────────────────────────────────
# Adaptive vertex counts
# ─────────────────────────────────────────────────────────────────────────────
# (max arc length in R_sun, vertices).  A line's bucket is chosen from its
# LONGEST arc length across the whole window, so its vertex count is identical
# in every frame -- that constancy is what makes GPU morphing legal.
VERT_BUCKETS: Tuple[Tuple[float, int], ...] = (
    (0.25, 6), (0.6, 10), (1.5, 16), (4.0, 28), (1e9, 48),
)

# ─────────────────────────────────────────────────────────────────────────────
# Render hints (shipped in the manifest; the app owns the shader)
# ─────────────────────────────────────────────────────────────────────────────

COLORS: Dict[str, Tuple[float, float, float]] = {
    "closed": (1.0, 0.85, 0.2),
    "open_pos": (0.3, 0.55, 1.0),
    "open_neg": (1.0, 0.4, 0.1),
}
CLOSED_FLOOR = 0.25

# ─────────────────────────────────────────────────────────────────────────────
# Timeline
# ─────────────────────────────────────────────────────────────────────────────

WINDOW_HOURS = 72                # user request 2026-08-23 (was 48)
FRAME_SPACING_HOURS = 4          # 72/4 + 1 == 19 frames (~2.2 MB total)
GONG_TOLERANCE_HOURS = 3.0       # real GONG gaps of 5-6 h have been observed
# A directory listing normally answers in ~0.35 s (measured). 20 s was generous
# for a slow day and ruinous for an unreachable host: gong2.nso.edu drops
# connections from GitHub runners entirely (footgun 33), and 12 scrapes x 20 s
# was nearly five minutes of a ~9 minute job spent waiting on nothing. 8 s is
# still 20x the observed latency, and sources/gong.py's circuit breaker stops
# asking after two consecutive timeouts.
GONG_SCRAPE_TIMEOUT = 8.0
STALE_HOURS = 8.0                # index.json "stale" threshold
MIN_FRAMES_TO_PUBLISH = 6        # fewer than this -> don't publish pfss/ at all
MAX_FRAME_BYTES = 200_000        # hard fail; target is 110-160 KB

# ─────────────────────────────────────────────────────────────────────────────
# Sources
# ─────────────────────────────────────────────────────────────────────────────

GONG_BASE = "https://gong2.nso.edu/oQR/zqs"

# ── Optional relay for GONG (footgun 33) ────────────────────────────────────
# gong2.nso.edu drops connections from GitHub Actions runners entirely: connect
# TIMEOUTS on every request, every run, while the identical request from a
# workstation answers in 0.35 s.  Researched 2026-08-23 and there is no free
# upstream alternative -- every hostname that serves the mrzqs product
# (gong.nso.edu, nispdata, magmap, and anonymous FTP) resolves to the SAME
# address, 146.5.21.69, so they share one firewall; sunpy's VSO GONGClient is
# a wrapper around that same host; JSOC carries no GONG series at all;
# Helioviewer has GONG H-alpha, a different physical observable; and NCEI's
# archive is not publicly downloadable.  What is left is relaying the request
# from a network NSO does not block.
#
# This is a REQUEST-TIME rewrite only.  Every URL stored in a cache key, a
# manifest or a log stays canonical (gong2.nso.edu), because NSO is the actual
# source and should be cited as such -- and because a relay swap must not
# invalidate the traced-frame cache.  scripts/gong-proxy-worker.js is a
# ready-to-deploy relay; see docs/GONG-RELAY.md.
GONG_PROXY_BASE = os.environ.get("SOL_GONG_PROXY_BASE", "").strip()
GONG_PROXY_TOKEN = os.environ.get("SOL_GONG_PROXY_TOKEN", "").strip()
GONG_PROXY_HEADER = "X-Sol-Relay-Token"
SRS_URL = "https://services.swpc.noaa.gov/text/srs.txt"
SRS_JSON_URL = "https://services.swpc.noaa.gov/json/solar_regions.json"
SUNSPOTS_URL = "https://services.swpc.noaa.gov/json/solar-cycle/sunspots.json"
XRAY_FLARES_URL = (
    "https://services.swpc.noaa.gov/json/goes/primary/xray-flares-7-day.json")
F107_URL = "https://services.swpc.noaa.gov/products/summary/10cm-flux.json"

# CCMC DONKI -- flare and CME event catalog.  No API key, and it answers with
# Access-Control-Allow-Origin: * (verified 2026-08-23), but we digest it
# server-side anyway: it sends Cache-Control: no-store, so every browser hit
# would go to origin, and CLAUDE.md's rule is "tiny endpoints only in the
# browser".
#
# Do NOT use the api.nasa.gov/DONKI mirror: it needs a key, rate-limits at 10
# requests, and returned 503 when checked on 2026-08-23.
#
# Do NOT probe these with a HEAD request -- DONKI answers HEAD with 403 and GET
# with 200 (measured).  probe-sources therefore does a real GET.
DONKI_BASE = "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/"

# Ask for the display window plus slack, never more.  Measured 2026-08-23: a
# 3-day CME window answers in 0.74 s / 23 KB, a 235-day window takes 32.4 s.
# The slack exists because DONKI back-fills: median CME submission lag is 7.5 h
# and p90 is 103 h, so a record for an event already inside the window can
# appear days later.  Every run re-fetches the whole window and dedupes rather
# than appending, for the same reason.
EVENTS_WINDOW_SLACK_HOURS = 24

# Below this a CME is not worth drawing (and mostly is not real).
CME_MIN_SPEED_KMS = 250.0

# Hard fail, in the spirit of MAX_FRAME_BYTES.  A 72 h window measured ~5 KB;
# this only trips if DONKI starts returning something structurally different.
EVENTS_MAX_BYTES = 60_000

# DONKI's own words, carried through to the guest-facing copy.  This app does
# not present research-grade data as an official forecast.
DONKI_DISCLAIMER = (
    "Space weather information in DONKI should be considered prototyping "
    "quality and used in a research context. For official forecasts see "
    "NOAA SWPC.")

# ─────────────────────────────────────────────────────────────────────────────
# SDO AIA texture (see pipeline/texture/export.py for the derivations)
# ─────────────────────────────────────────────────────────────────────────────

TEX_WAVELENGTH = 171                      # the app's default channel

# Every channel published as a 3D sphere texture, DEFAULT FIRST.
#
# A channel is not just a wavelength: the two HMI products differ from AIA in
# ways that would silently produce dishonest maps if they shared AIA's settings.
#
#   scale     arcsec/px of the 4096 browse still. AIA is ~0.6009, HMI ~0.5044 --
#             measured 2026-08, the solar disk fills 0.7824 of an AIA frame and
#             0.9184 of an HMI one, a ratio of 1.174. Getting this wrong by more
#             than TEX_LIMB_RADIUS_TOL aborts the run rather than shipping a
#             misregistered map, which is the behavior we want.
#   farside   how the hemisphere Earth cannot see is filled. "quiet" adds the
#             band-limited mottling + polar darkening of farside_modulation,
#             which is a defensible stylization for EUV. "flat" is a plain
#             quiet-Sun fill with NO invented structure -- mandatory for HMIB,
#             where mottling would be fabricated magnetic field, and right for
#             HMIIC, where the polar ramp (tuned to coronal holes) is wrong.
#   ar_check  run the active-region registration check. It scores by locating
#             BRIGHT pixels near each cataloged region, which only means
#             anything in EUV: sunspots are DARK in HMIIC, and bright in HMIB
#             just means positive polarity.
TEX_CHANNELS = (
    {"code": "0171",  "label": "Coronal Loops", "wavelength": 171,
     "scale": 0.6009, "farside": "quiet", "ar_check": True},
    {"code": "0304",  "label": "Chromosphere",  "wavelength": 304,
     "scale": 0.6009, "farside": "quiet", "ar_check": True},
    {"code": "0193",  "label": "Hot Corona",    "wavelength": 193,
     "scale": 0.6009, "farside": "quiet", "ar_check": True},
    {"code": "HMIIC", "label": "Visible Sun",   "wavelength": None,
     "scale": 0.5044, "farside": "flat",  "ar_check": False},
    {"code": "HMIB",  "label": "Magnetic Map",  "wavelength": None,
     "scale": 0.5044, "farside": "flat",  "ar_check": False},
)
# Plate carree, 0.0879 deg/px. Raised from 2048x1024 when the app became a
# single sphere view: the Earth-facing hemisphere is half the width, so this is
# what the guest actually sees across the disk -- 2048 px here against the 3205
# px of a 4096 disk still. Still coarser, but the still is no longer downloaded
# at all (0171 at 4096 is 2.6 MB against ~600 KB here), so the consolidation
# pays for the resolution and then some.
#
# Do not raise further without measuring phone GPU memory: 4096x2048 RGBA is
# 32 MB resident per texture before mipmaps, and sunSurface keeps exactly one.
TEX_OUT_W, TEX_OUT_H = 4096, 2048
TEX_JPEG_QUALITY = 82
TEX_MAX_BYTES = 1_600_000                 # validator ceiling; ~600 KB at 4096x2048

# ── Time-aligned history frames ─────────────────────────────────────────────
# The sphere used to carry ONE Carrington map -- always the newest -- while the
# field lines morphed through 19 frames over 72 h.  Scrubbing back three days
# therefore showed three-day-old magnetic field over TODAY's photosphere, with
# the terminator parked at today's sub-earth longitude.  Every slot in the PFSS
# timeline now gets its own map, so the imagery, the sunspots and the field all
# describe the same hour.
#
# Half the linear resolution of the newest frame: 2048x1024 RGBA is 8 MB
# resident on the GPU against 32 MB, and the app keeps a small ring of them.
# Measured ~150 KB/frame, so 18 history slots x 5 channels is ~14-18 MB
# published -- and ZERO bytes for a guest who never touches the scrubber.
TEX_HIST_W, TEX_HIST_H = 2048, 1024
TEX_HIST_MAX_BYTES = 500_000

# A slot must be matched by a browse frame this close or it is left UNFILLED
# rather than shown the wrong hour.  HALF THE SLOT SPACING is the only
# defensible value: inside it the chosen frame is unambiguously the closest one
# to this slot, and outside it some OTHER slot is closer, so filling it would
# show a guest the same picture at two different playhead positions.
#
# It has to be this generous because the archive really does have holes.  AIA
# publishes every 5 min and HMI every 15 (measured: 288 and up to 96 frames per
# UT day), but HMIB on 2026-08-21 has 51 frames and stops at 12:30 -- a genuine
# instrument gap, which correctly leaves that day's 16:00 and 20:00 slots empty
# for that channel rather than substituting a four-hour-old photosphere.
TEX_HIST_TOLERANCE_HOURS = FRAME_SPACING_HOURS / 2.0

# Cold-start throttle.  A full 18 x 5 rebuild is several minutes of
# reprojection and the whole CI job has ~9.  Frames already published are
# REUSED rather than rebuilt (CI seeds `out` from gh-pages -- footgun 31), so
# steady state is only the 5 slots that scrolled into the window.  This cap
# bounds the FIRST run; the window then fills over the next few. Newest missing
# slots are built first, because recent time is what guests actually scrub.
TEX_HIST_MAX_NEW_PER_RUN = 15
TEX_MAX_OBS_AGE_HOURS = 24.0              # older than this -> status degraded

# Source browse JPGs.  2048 px frames are the 4096 native downsampled by 2, so
# the level-1.5 plate scale of 0.6"/px becomes 1.2"/px.  MEASURED against the
# limb (see measure_limb): ring radius 788.9 px vs 790.5 px predicted from
# sunpy's angular_radius, i.e. agreement to 0.2%.
SDO_BROWSE_BASE = "https://sdo.gsfc.nasa.gov/assets/img/browse"
SDO_LATEST_BASE = "https://sdo.gsfc.nasa.gov/assets/img/latest"
TEX_SRC_RES = 2048
def tex_src_scale(channel_scale: float, src_res: int = TEX_SRC_RES) -> float:
    """arcsec/px of the browse still actually downloaded, for one channel.

    ``channel_scale`` (TEX_CHANNELS[...]["scale"]) is the plate scale of
    SDO's NATIVE 4096 px product; a still fetched at a coarser ``src_res``
    has proportionally fewer, proportionally bigger pixels across the same
    disk. Parameterized (rather than hard-coded to the module's TEX_SRC_RES)
    so the SAME function serves the normal 2048 px source and the high-res
    4096 px one below -- at src_res=4096 this returns channel_scale
    unchanged, which is correct: the native still needs no upscaling factor.
    """
    return channel_scale * (4096 // src_res)


TEX_SRC_SCALE_ARCSEC = tex_src_scale(0.6)   # AIA default, kept for callers
TEX_LIMB_RADIUS_TOL = 0.03                # warn if the fitted limb is >3% off

# ── Opt-in high-resolution newest-frame texture (--with-hires) ──────────────
# TEX_OUT_W/H (4096x2048) resamples the 2048 px browse still, and half of a
# plate-carree map is the visible hemisphere -- so the near side the guest
# actually sees only ever gets 2048 px across 180 deg of longitude. SDO's
# browse tree also publishes a 4096 px native still (footgun 7); at that
# resolution the AIA disk (fills 0.7824 of the frame, TEX_LIMB_RADIUS_TOL's
# derivation) is ~3204 px across -- more real detail than the 2048x1024
# near-side output can show at all. TEX_HIRES_W/H is TEX_OUT_W/H exactly
# doubled, so the near side gets 4096 px and the source detail is actually
# used rather than thrown away on the way in.
#
# NEWEST FRAME ONLY (hard constraint from the task that added this: no
# history sequence at this size -- 19 slots x 5 channels x 4x the pixels is
# not a defensible CI cost) and OFF by default at both ends: the pipeline
# needs --with-hires (cli.py), and the app needs a guest opt-in
# (sunSurface.ts's setHighRes()) because the decoded texture is a real GPU
# memory commitment (see TEX_HIRES_W/H's docstring math below) that a phone
# guest must never pay for just because the product exists.
TEX_HIRES_SRC_RES = 4096                  # SDO's native browse resolution
TEX_HIRES_W, TEX_HIRES_H = 8192, 4096
# Measured 2026-08-23, `python -m pipeline texture --with-hires` (5 channels,
# TEX_HIRES_JPEG_QUALITY below): see HANDOFF.md / the session report for the
# per-channel wall-clock and byte counts that justified this number. Sized
# with headroom over the largest observed channel, the same way TEX_MAX_BYTES
# (1.6 MB, ~600 KB typical at 4096x2048) leaves headroom over its typical size
# -- this is a SEPARATE budget rather than a raised TEX_MAX_BYTES because an
# 8192x4096 JPEG at the same quality is measured several times bigger than the
# 4096x2048 one, and a shared ceiling would either fail every normal-res
# build or let a hi-res build through many times bigger than intended.
TEX_HIRES_JPEG_QUALITY = 82                # same as TEX_JPEG_QUALITY; see below
TEX_HIRES_MAX_BYTES = 4_500_000

# ── Off-limb annulus ────────────────────────────────────────────────────────
# The Carrington reprojection maps the SURFACE, so everything outside the limb
# -- prominences, low coronal loops, the inner corona -- is thrown away. It is
# also the only part of a solar image that is genuinely three-dimensional and
# that we have no model for, so it cannot go on the sphere at all.
#
# Instead it ships as a square crop centered on the disk with the disk itself
# blacked out, drawn in the app as a camera-facing billboard around the sphere.
# Black rather than an alpha channel because the billboard is ADDITIVELY
# blended, so black already contributes nothing -- an alpha channel would cost
# a PNG (several times the bytes) to encode information the blend mode already
# carries.
#
# The crop is only honest from Earth's viewpoint: it is a 2D projection of
# structure whose real depth is unknown. The app fades it out as the camera
# leaves the sub-Earth direction rather than pretending otherwise.
TEX_OFFLIMB_SIZE = 1024                   # px, square
TEX_OFFLIMB_QUALITY = 80
TEX_OFFLIMB_MAX_BYTES = 400_000
# Feather the inner edge across this fraction of a solar radius so the billboard
# does not meet the sphere on a hard ring. Starts just inside the limb: the
# sphere's own edge is drawn by the surface texture, and overlapping slightly
# hides any sub-pixel disagreement between the two.
TEX_OFFLIMB_INNER = (0.985, 1.02)
TEX_LIMB_CENTER_TOL_PX = 25.0             # warn if the disk is not centered
# ^ measured/tuned at TEX_SRC_RES (2048 px); fit_limb() scales this by
# src_res / TEX_SRC_RES before comparing, because a pixel offset scales
# linearly with resolution -- without that, the 4096 px hi-res source (same
# real disk-center offset, exactly 2x the pixels) would fail this check for
# being MORE precise, not less.

# SDO has two eclipse seasons a year (mid-Feb to mid-Mar, mid-Aug to mid-Sep)
# with a daily blackout of up to ~72 min, so near-black browse frames are
# NORMAL and must be walked past rather than reprojected into a black Sun.
# A healthy frame's central-half mean is ~70 of 255; an eclipsed one is ~0.
TEX_MIN_DISK_MEAN = 20.0
TEX_MAX_SOURCE_TRIES = 10                 # 10 min cadence -> covers ~100 min

# Near-side -> far-side blend.  Beyond ~75 deg from the sub-earth point the
# reprojection is so foreshortened that one output pixel spans many degrees of
# real Sun (and the 171 limb-brightening ring lives at 88-90 deg), so the last
# 15 deg is cross-faded into the quiet-sun base with a raised cosine.  The same
# distance test handles the stretched polar caps for free: with |B0| ~ 7 deg one
# pole sits at 83 deg and the other is not visible at all.
TEX_FEATHER_DEG = (75.0, 90.0)

# The near side is ALSO tapered in LATITUDE, which the distance test cannot do
# for us: at latitude 85 the closest a pixel ever gets to the sub-earth point
# is 78 deg, so the distance feather leaves those rows at 90% weight.  But the
# polar surface is seen at >70 deg from normal there, so one input pixel smears
# over many degrees of latitude and the 171 limb brightening turns the top and
# bottom rows into a bright horizontal streak.  ARs live inside +/-40 deg, so
# nothing the app cares about is lost.
TEX_LAT_FADE_DEG = (72.0, 88.0)

# Quiet-sun base color: median of the near side between these angular
# distances, below this percentile (excludes limb brightening and AR cores).
TEX_QUIET_ANNULUS_DEG = (20.0, 60.0)
TEX_QUIET_PERCENTILE = 80.0

# Far-side texture: a band-limited analytic field (periodic in longitude, so no
# seam at lon 0) times a polar darkening ramp.  The seed is FIXED so the far
# side does not flicker between runs.
TEX_FARSIDE_SEED = 20260823
TEX_FARSIDE_NOISE_AMP = 0.12
TEX_FARSIDE_NOISE_TERMS = 12
TEX_POLE_FADE_DEG = (55.0, 90.0)
TEX_POLE_FLOOR = 0.55

# AR registration guard: the cataloged regions must show up as bright pixels
# near their Carrington coordinates.  Measured 2026-08-23 with 4 regions:
# 2.7-3.6 deg for the two well-placed ones, which is the floor set by SRS's
# 1 deg rounding + its 00:00 UT epoch + coronal loops being offset from spots.
TEX_AR_MAX_SUBEARTH_DEG = 60.0            # only well-placed regions count
TEX_AR_OFFSET_WARN_DEG = 5.0

# ─────────────────────────────────────────────────────────────────────────────
# Caching / output
# ─────────────────────────────────────────────────────────────────────────────

CACHE_DIR = "pipeline/.cache"    # gong/, frames/<seed_set_id>/, seeds/, srs/
DEFAULT_OUT = "dist-data"
KEEP_FRAME_CACHE_SETS = 2        # prune older seed-set frame caches

# Spacecraft baked from JPL Horizons.  'Earth' is ambiguous in Horizons (it
# matches several records), so the barycenter-free planet id '399' is used.
EPHEM_BODIES = (
    # (horizons target, app id, display name, horizons id (informational), color)
    ("Parker Solar Probe", "psp", "Parker Solar Probe", -96, "#ff8a3d"),
    ("Solar Orbiter", "solo", "Solar Orbiter", -144, "#5fb8ff"),
    ("STEREO-A", "stereoa", "STEREO-A", -234, "#c77dff"),
    ("399", "earth", "Earth", 399, "#7de08a"),
)
EPHEM_SPAN_DAYS = 30             # +/- this many days around now
EPHEM_STEPS = 240                # 240 intervals -> 241 samples -> 6 h cadence

# Missions whose heliocentric position IS Earth's (both are Earth-orbiting, so
# Horizons has no heliocentric record for them).
EPHEM_AT_EARTH = (
    {"id": "punch", "name": "PUNCH",
     "note": "Sun-synchronous LEO (~600 km); heliocentric position is Earth's"},
    {"id": "proba3", "name": "Proba-3/ASPIICS",
     "note": "Earth HEO 600 x 60,500 km; heliocentric position is Earth's"},
)

# Solar rotation axis in ecliptic J2000 (IAU values; shipped as constants so the
# app can sanity-check its own basis maths).
SOLAR_AXIS_TILT_DEG = 7.25173
SOLAR_AXIS_NODE_DEG = 75.76576
