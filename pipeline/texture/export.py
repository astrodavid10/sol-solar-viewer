"""The latest AIA 171 disk, reprojected onto a Carrington equirectangular map.

Why this product exists
----------------------
The app drapes this JPEG on a three.js sphere.  Because the texture and the
PFSS field lines are BOTH expressed in HeliographicCarrington, the app orients
both with the same per-frame ``quat_carr_to_ecl`` and they register by
construction -- no independent alignment to get wrong.

Output contract (``sol.texture/1``)
----------------------------------
2048x1024 plate carree (CAR).  Column 0's pixel CENTRE is Carrington longitude
0.0879 deg -- i.e. the left EDGE of column 0 is longitude 0 -- and longitude
increases left to right to 360 at the right edge.  Row 0 is the TOP of the
picture and is +90 deg latitude (north up).  Formulae::

    lon_deg = (x + 0.5) * 360/2048           x = 0..2047, left to right
    lat_deg = 90 - (y + 0.5) * 180/1024      y = 0..1023, top to bottom

Source image: (b) from the plan
-------------------------------
The GSFC browse JPGs, not FITS via Fido.  Reasons: no VSO/JSOC dependency in
CI (Fido is the flakiest thing in the whole pipeline), 700 KB and ~1 s to
fetch, and a synthesized WCS is honest to well under one output pixel
(0.176 deg = 2200 km at disk centre) which is all a 2048x1024 texture can
resolve.  Real FITS via ``Fido.search(a.Instrument.aia,
a.Wavelength(171*u.AA))`` remains the documented alternative if
sub-arcsecond WCS ever matters.

Three properties of the browse JPGs, all VERIFIED EMPIRICALLY (2026-08-23):

1. *Solar north is already up* -- the P angle is applied.  Tested by predicting
   the pixel position of the four catalogued active regions under six
   hypotheses (P applied / +P / -P, crossed with row order) and scoring each by
   the image brightness there (ARs are bright in 171).  North-up + row 0 = top
   scored 140.2; the next best hypothesis scored 110.3.  With P = 18.62 deg
   that day the test had plenty of leverage.  Consequently ``rotation_angle=0``
   and the PIL array (row 0 = top) is flipped into FITS bottom-up order.
2. *Fixed plate scale, disk centred.*  A limb-ring fit gave radius 788.9 px and
   a centre 6.6 px from the image centre, against 790.5 px predicted from
   sunpy's ``angular_radius`` at 1.2"/px -- 0.2% agreement.  So the nominal
   scale is used (a self-calibrated scale would be biased ~1% high by the 171
   limb-brightening shell at ~1.008 R_sun, and would jitter run to run); the
   fit is kept as a per-run SANITY CHECK that fails loudly if GSFC ever
   re-crops the browse product.
3. *The far side is genuinely absent.*  ``reproject_interp``'s default
   ``roundtrip_coords=True`` is what keeps the far side out: the forward
   transform alone would alias far-side longitudes onto their near-side
   mirrors, because the 2D Helioprojective WCS drops the distance coordinate.
   Measured finite fraction 0.4973 -- 1.0 would have meant aliasing, and that
   number is asserted every run.

Far side
--------
v1 fills it with a quiet-sun base sampled from the real image (so the seam
tracks the current brightness) and cross-fades the near side into it over the
last 15 deg.  ``far_side: "quiet"``, ``far_side_max_age_hours: null`` -- the
app must not claim the far side is observed.

FUTURE (P2.x): a rolling far-side mosaic.  Keep the last ~13 days of near-side
reprojections, composite them cos-weighted by |lon - L0_then| into the far
side, and report the real ``far_side_max_age_hours``.  Deliberately NOT built
here: it needs a cache of full reprojections and a decision about how to
handle a 13-day-old active region that has since decayed.
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional, Tuple

import numpy as np

from ..config import (PIPELINE_VERSION, SCHEMA_TEXTURE, SDO_BROWSE_BASE,
                      SDO_LATEST_BASE, TEX_AR_MAX_SUBEARTH_DEG,
                      TEX_AR_OFFSET_WARN_DEG, TEX_FARSIDE_NOISE_AMP,
                      TEX_FARSIDE_NOISE_TERMS, TEX_FARSIDE_SEED,
                      TEX_FEATHER_DEG, TEX_JPEG_QUALITY, TEX_LAT_FADE_DEG,
                      TEX_LIMB_CENTRE_TOL_PX, TEX_LIMB_RADIUS_TOL,
                      TEX_MAX_BYTES, TEX_MAX_OBS_AGE_HOURS,
                      TEX_MAX_SOURCE_TRIES, TEX_MIN_DISK_MEAN, TEX_OUT_H,
                      TEX_OUT_W, TEX_POLE_FADE_DEG, TEX_POLE_FLOOR,
                      TEX_QUIET_ANNULUS_DEG, TEX_QUIET_PERCENTILE,
                      TEX_CHANNELS, TEX_OFFLIMB_INNER, TEX_OFFLIMB_QUALITY,
                      TEX_OFFLIMB_SIZE, TEX_SRC_RES, tex_src_scale)
from ..io_utils import (PipelineError, age_hours, http_get_full, human_bytes,
                        iso_z, unix_s)

def jpeg_name(code: str) -> str:
    """File name for one channel's Carrington map.

    Keyed on the SDO product CODE rather than a wavelength, because HMIB and
    HMIIC have no wavelength -- they are a magnetogram and a colourised
    continuum image.
    """
    return "sdo{0}_carrington_{1}x{2}.jpg".format(code, TEX_OUT_W, TEX_OUT_H)


def channel_for(code: str) -> dict:
    """The TEX_CHANNELS entry for a product code."""
    for ch in TEX_CHANNELS:
        if ch["code"] == code:
            return ch
    raise PipelineError("unknown texture channel {0!r}".format(code))


DEFAULT_CODE = TEX_CHANNELS[0]["code"]
JPEG_NAME = jpeg_name(DEFAULT_CODE)
PRODUCT_CODE = DEFAULT_CODE
_BROWSE_RE_TMPL = r'href="(\d{{8}}_\d{{6}}_{res}_{prod}\.jpg)"'


# ─────────────────────────────────────────────────────────────────────────────
# Source selection
# ─────────────────────────────────────────────────────────────────────────────

class SourceImage(object):
    """One fetched full-disk browse JPG plus its provenance."""

    def __init__(self, rgb: np.ndarray, obstime: datetime, url: str,
                 kind: str, nbytes: int) -> None:
        # (ny, nx, 3) float32, row 0 = the TOP of the picture
        self.rgb = rgb
        self.obstime = obstime
        self.url = url
        self.kind = kind                # "browse" | "latest"
        self.nbytes = nbytes


def _browse_dir(day: datetime) -> str:
    return "{0}/{1:04d}/{2:02d}/{3:02d}/".format(
        SDO_BROWSE_BASE, day.year, day.month, day.day)


def browse_candidates(now: datetime, days: int = 2,
                      code: str = None
                      ) -> List[Tuple[datetime, str]]:
    """(obstime, url) for every browse frame in the last ``days`` day dirs.

    Sorted oldest first.  Frames dated in the future are dropped: the day
    directory for "today" is written in UT and a clock skew would otherwise let
    us pick an image that does not exist yet.
    """
    pat = re.compile(_BROWSE_RE_TMPL.format(res=TEX_SRC_RES,
                                           prod=code or DEFAULT_CODE))
    out: List[Tuple[datetime, str]] = []
    for d in range(days):
        base = _browse_dir(now - timedelta(days=d))
        try:
            body, _ = http_get_full(base, timeout=30.0)
        except Exception:
            continue
        for name in pat.findall(body.decode("utf-8", "replace")):
            try:
                t = datetime.strptime(name[:15], "%Y%m%d_%H%M%S").replace(
                    tzinfo=timezone.utc)
            except ValueError:
                continue
            if t <= now + timedelta(minutes=5):
                out.append((t, base + name))
    out.sort(key=lambda kv: kv[0])
    return out


def _decode(raw: bytes) -> np.ndarray:
    from PIL import Image
    img = Image.open(io.BytesIO(raw))
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    if arr.shape[0] != TEX_SRC_RES or arr.shape[1] != TEX_SRC_RES:
        raise PipelineError(
            "source image is {0}x{1}, expected {2}x{2}".format(
                arr.shape[1], arr.shape[0], TEX_SRC_RES))
    return arr


def disk_mean(rgb: np.ndarray) -> float:
    """Mean brightness of the central half, which is always inside the disk.

    The cheap eclipse test: SDO passes through Earth's shadow twice a year for
    up to ~72 min a day and the browse JPGs published during those windows are
    essentially black.  Reprojecting one would ship a black Sun that every
    other check would happily pass.
    """
    n = rgb.shape[0]
    return float(rgb[n // 4:3 * n // 4, n // 4:3 * n // 4].mean())


def fetch_source(now: datetime, verbose: bool = False,
                 code: str = None) -> SourceImage:
    """Newest usable browse frame, else the ``latest_*.jpg`` fallback.

    The browse frame is strongly preferred because its FILENAME carries the
    observation time to the second; ``latest_*.jpg`` only has Last-Modified,
    which is when the JPG was written rather than when the photons arrived
    (a few minutes later, and unbounded if the pipeline behind it stalls).

    Frames that fail to download, fail to decode, or are too dark to be a real
    exposure are skipped and the next older one tried.
    """
    skipped: List[str] = []
    code = code or DEFAULT_CODE
    candidates = browse_candidates(now, code=code)
    for t, url in candidates[::-1][:TEX_MAX_SOURCE_TRIES]:
        name = url.rsplit("/", 1)[-1]
        try:
            raw, _ = http_get_full(url, timeout=60.0)
            rgb = _decode(raw)
        except Exception as exc:
            skipped.append("{0}: {1}".format(name, exc))
            continue
        mean = disk_mean(rgb)
        if mean < TEX_MIN_DISK_MEAN:
            skipped.append("{0}: disk mean {1:.1f} (eclipse?)".format(name,
                                                                      mean))
            continue
        if skipped:
            print("  skipped {0} unusable browse frame(s): {1}".format(
                len(skipped), "; ".join(skipped if verbose else skipped[:2])))
        return SourceImage(rgb, t, url, "browse", len(raw))

    url = "{0}/latest_{1}_{2}.jpg".format(SDO_LATEST_BASE, TEX_SRC_RES, code)
    print("  no usable browse frame ({0}); trying latest_*.jpg".format(
        "; ".join(skipped[:3]) or "empty listing"))
    raw, headers = http_get_full(url, timeout=60.0)
    rgb = _decode(raw)
    mean = disk_mean(rgb)
    if mean < TEX_MIN_DISK_MEAN:
        raise PipelineError(
            "every candidate frame is too dark to use (latest_*.jpg disk mean "
            "{0:.1f} < {1}); SDO is probably in eclipse -- keeping the "
            "previously published texture".format(mean, TEX_MIN_DISK_MEAN))
    obstime = now
    lm = headers.get("last-modified")
    if lm:
        try:
            obstime = parsedate_to_datetime(lm).astimezone(timezone.utc)
        except (TypeError, ValueError):
            pass
    return SourceImage(rgb, obstime, url, "latest", len(raw))


# ─────────────────────────────────────────────────────────────────────────────
# Geometry
# ─────────────────────────────────────────────────────────────────────────────

def measure_limb(lum: np.ndarray, r_pred: float
                 ) -> Tuple[float, float, float, float, int]:
    """Fit the limb ring: (cx, cy, radius, per-ray scatter, n rays used).

    Each of 720 rays from the current centre estimate is walked outward and the
    steepest intensity FALL is taken as that ray's limb; a least-squares circle
    through those points is iterated a few times.  Bright off-limb loops are
    rejected by distance from the median radius.  0-based pixel coordinates in
    the PICTURE array (row 0 = top); orientation is irrelevant to a circle.
    """
    from scipy.ndimage import map_coordinates
    ny, nx = lum.shape
    cx, cy = (nx - 1) / 2.0, (ny - 1) / 2.0
    th = np.linspace(0.0, 2.0 * np.pi, 720, endpoint=False)
    rs = np.arange(0.94 * r_pred, 1.09 * r_pred, 0.5)
    ct, st = np.cos(th), np.sin(th)
    r, resid, n_used = r_pred, float("nan"), 0
    for _ in range(4):
        px = cx + ct[:, None] * rs[None, :]
        py = cy + st[:, None] * rs[None, :]
        prof = map_coordinates(lum, [py.ravel(), px.ravel()], order=1,
                               mode="constant", cval=0.0).reshape(px.shape)
        r_edge = rs[np.argmin(np.gradient(prof, axis=1), axis=1)]
        good = np.abs(r_edge - np.median(r_edge)) < 0.02 * r_pred
        if good.sum() < 60:
            break
        a = np.stack([np.ones(int(good.sum())), ct[good], st[good]], axis=1)
        sol, *_ = np.linalg.lstsq(a, r_edge[good], rcond=None)
        r, cx, cy = float(sol[0]), cx + float(sol[1]), cy + float(sol[2])
        resid = float(np.std(r_edge[good] - a @ sol))
        n_used = int(good.sum())
    return cx, cy, r, resid, n_used


def input_header(src: SourceImage, obstime, observer,
                 channel: dict = None):
    """Synthesized level-1.5-style WCS for a browse JPG.

    Disk centre at the array centre, ``TEX_SRC_SCALE_ARCSEC``/px, and identity
    PC (== solar north up, solar west to increasing column) because the browse
    product already has the P rotation applied.
    """
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from sunpy.coordinates import Helioprojective
    from sunpy.map.header_helper import make_fitswcs_header

    channel = channel_for(DEFAULT_CODE) if channel is None else channel
    scale = tex_src_scale(channel["scale"])
    # HMI and AIA are different telescopes at different plate scales; saying
    # "AIA" for a magnetogram would put a false instrument in the WCS that the
    # reprojection then trusts.
    detector = "HMI" if channel["code"].startswith("HMI") else "AIA"

    centre = SkyCoord(0.0 * u.arcsec, 0.0 * u.arcsec, obstime=obstime,
                      observer=observer, frame=Helioprojective)
    header = make_fitswcs_header(
        (src.rgb.shape[0], src.rgb.shape[1]), centre,
        scale=u.Quantity([scale, scale], u.arcsec / u.pix),
        rotation_angle=0.0 * u.deg,
        instrument=detector, telescope="SDO", observatory="SDO",
        detector=detector,
        **({"wavelength": channel["wavelength"] * u.angstrom}
           if channel["wavelength"] else {}))
    return header


def output_header(obstime, observer):
    """Carrington CAR header with longitude 0 at the LEFT EDGE.

    ``make_heliographic_header`` centres the map on ``map_center_longitude``,
    so 180 deg puts 0 at the edges.  Verified: crpix1 1024.5, cdelt1 +0.17578,
    crval1 180 => column 0 centre = 0.0879 deg and column 2047 = 359.912 deg,
    increasing left to right.  cdelt2 is also POSITIVE, so FITS row 0 is
    latitude -89.91: the array is flipped once on the way to the JPEG.
    """
    import astropy.units as u
    from sunpy.map.header_helper import make_heliographic_header
    return make_heliographic_header(
        obstime, observer, (TEX_OUT_H, TEX_OUT_W), frame="carrington",
        projection_code="CAR", map_center_longitude=180.0 * u.deg)


def grid(header) -> Tuple[np.ndarray, np.ndarray]:
    """(lon, lat) in degrees for the OUTPUT array's columns and FITS rows."""
    lon = (header["crval1"]
           + (np.arange(TEX_OUT_W) + 1.0 - header["crpix1"]) * header["cdelt1"])
    lat = (header["crval2"]
           + (np.arange(TEX_OUT_H) + 1.0 - header["crpix2"]) * header["cdelt2"])
    return lon, lat


def sub_earth_distance(lon: np.ndarray, lat: np.ndarray, l0: float, b0: float
                       ) -> np.ndarray:
    """Great-circle distance (deg) from the sub-observer point, per pixel."""
    lo, la = np.meshgrid(np.radians(lon), np.radians(lat))
    cosd = (np.sin(la) * np.sin(np.radians(b0))
            + np.cos(la) * np.cos(np.radians(b0)) * np.cos(lo - np.radians(l0)))
    return np.degrees(np.arccos(np.clip(cosd, -1.0, 1.0)))


def reproject_rgb(src: SourceImage, in_header, out_header) -> np.ndarray:
    """(TEX_OUT_H, TEX_OUT_W, 3) float32, NaN off the visible hemisphere.

    One reprojection per colour channel.  The AIA 171 colour table is a
    monotone function of intensity, so per-channel interpolation cannot
    introduce false colour.  ~1.8 s per channel.
    """
    import sunpy.map
    planes = []
    for k in range(3):
        # PIL gives row 0 = top of the picture; FITS wants row 0 = bottom.
        plane = np.flipud(src.rgb[..., k]).copy()
        m = sunpy.map.Map(plane, in_header)
        planes.append(np.asarray(m.reproject_to(out_header).data,
                                 dtype=np.float32))
    return np.stack(planes, axis=-1)


# ─────────────────────────────────────────────────────────────────────────────
# Far side + compositing
# ─────────────────────────────────────────────────────────────────────────────

def quiet_sun_rgb(near: np.ndarray, valid: np.ndarray, dist: np.ndarray
                  ) -> np.ndarray:
    """Median RGB of the quiet near side -- the far side's base colour."""
    lo, hi = TEX_QUIET_ANNULUS_DEG
    ann = valid & (dist > lo) & (dist < hi)
    if ann.sum() < 1000:
        raise PipelineError(
            "only {0} near-side pixels between {1} and {2} deg; the "
            "reprojection is probably empty".format(int(ann.sum()), lo, hi))
    lum = near.mean(axis=-1)
    keep = ann & (lum <= np.percentile(lum[ann], TEX_QUIET_PERCENTILE))
    return np.array([float(np.median(near[..., k][keep])) for k in range(3)])


def _smoothstep(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def farside_modulation(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Smooth multiplicative field: band-limited noise x polar darkening.

    Built from cosine terms rather than smoothed random pixels so it is exactly
    periodic in longitude (no seam at 0/360) and identical on every platform
    for a given seed.  Two octaves: a coarse one that gives the hemisphere
    large-scale shape and a finer one at 45% amplitude, because a single
    octave reads as an out-of-focus blur rather than solar mottling.  The polar
    ramp is there because polar coronal holes really are dark in 171, so a flat
    far side would look wrong at the caps.
    """
    lo, la = np.meshgrid(np.radians(lon), np.radians(lat))
    rng = np.random.default_rng(TEX_FARSIDE_SEED)
    field = np.zeros_like(lo)
    for lo_m, hi_m, lo_n, hi_n, amp in ((1, 5, 1, 4, 1.0), (5, 13, 3, 8, 0.45)):
        for _ in range(TEX_FARSIDE_NOISE_TERMS):
            m, n = int(rng.integers(lo_m, hi_m)), int(rng.integers(lo_n, hi_n))
            p1, p2 = rng.uniform(0.0, 2.0 * np.pi, 2)
            field += amp * rng.normal() * np.cos(m * lo + p1) * np.cos(
                n * la + p2)
    std = float(field.std())
    mod = 1.0 + TEX_FARSIDE_NOISE_AMP * (field / std if std > 0 else field)

    p0, p1 = TEX_POLE_FADE_DEG
    return mod * (1.0 - (1.0 - TEX_POLE_FLOOR) * _smoothstep(
        (np.abs(np.degrees(la)) - p0) / (p1 - p0)))


def feather_weight(dist: np.ndarray, valid: np.ndarray, lat: np.ndarray
                   ) -> np.ndarray:
    """Near-side weight: raised cosine in sub-earth distance x polar taper."""
    d0, d1 = TEX_FEATHER_DEG
    w = 0.5 * (1.0 + np.cos(np.pi * np.clip((dist - d0) / (d1 - d0), 0.0, 1.0)))
    p0, p1 = TEX_LAT_FADE_DEG
    w = w * (1.0 - _smoothstep((np.abs(lat) - p0) / (p1 - p0)))[:, None]
    return np.where(valid, w, 0.0)


def compose(near: np.ndarray, valid: np.ndarray, dist: np.ndarray,
            lon: np.ndarray, lat: np.ndarray, farside: str = "quiet"
            ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Blend near side over the quiet base and flip to picture row order.

    ``farside`` selects what fills the hemisphere Earth cannot see:

      "quiet"  the measured quiet-Sun colour times farside_modulation's
               band-limited mottling and polar darkening. A stylisation, and a
               defensible one for EUV -- a flat EUV hemisphere looks wrong.
      "flat"   the measured quiet-Sun colour and nothing else.

    "flat" exists because the mottling is INVENTED. On a magnetogram it would
    be fabricated magnetic field on the half of the Sun nobody can see, drawn
    convincingly enough to be believed, and the polar ramp encodes coronal
    holes that a continuum image does not show either.

    Returns (uint8 image with row 0 = +90 lat, feather weights, base RGB).
    """
    base = quiet_sun_rgb(near, valid, dist)
    if farside == "flat":
        quiet = np.broadcast_to(base[None, None, :], near.shape)
    else:
        quiet = base[None, None, :] * farside_modulation(lon, lat)[..., None]
    w = feather_weight(dist, valid, lat)[..., None]
    blend = w * np.nan_to_num(near, nan=0.0, posinf=0.0, neginf=0.0) \
        + (1.0 - w) * quiet
    img = np.flipud(np.clip(blend, 0.0, 255.0)).astype(np.uint8)
    return img, w[..., 0], base


def encode_jpeg(img: np.ndarray, quality: int = TEX_JPEG_QUALITY) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(img, "RGB").save(buf, "JPEG", quality=int(quality),
                                     optimize=True)
    blob = buf.getvalue()
    if len(blob) > TEX_MAX_BYTES:
        raise PipelineError(
            "texture JPEG is {0} bytes, over the {1}-byte budget; lower "
            "TEX_JPEG_QUALITY".format(len(blob), TEX_MAX_BYTES))
    return blob


# ─────────────────────────────────────────────────────────────────────────────
# AR registration guard
# ─────────────────────────────────────────────────────────────────────────────

def ar_offsets(near: np.ndarray, valid: np.ndarray, lon: np.ndarray,
               lat: np.ndarray, regions: List[dict], l0: float, b0: float
               ) -> List[dict]:
    """Where the bright 171 pixels sit relative to each catalogued AR.

    This is the check that catches a P-angle, mirror or centre-longitude error:
    all of those look plausible and only show up as a systematic displacement
    of real features.  Per region, take a +/-10 deg window, drop pixels that
    are nearer some OTHER region (a 10 uH alpha spot next to a 200 uH
    beta-gamma-delta would otherwise just measure its neighbour's loops), and
    take the brightness-weighted centroid of the top 8%.

    Residual offsets of a couple of degrees are EXPECTED and not a bug: SRS
    rounds positions to 1 deg, quotes them for 00:00 UT (up to ~36 h before the
    image), and coronal loop systems are both extended and offset from the
    photospheric spot group they arch over.
    """
    from scipy.ndimage import uniform_filter
    half = 10.0
    lum = uniform_filter(np.where(valid, near.mean(axis=-1), 0.0), size=7)
    shape = lum.shape
    out: List[dict] = []
    for reg in regions:
        try:
            clon = float(reg["carr_lon_deg"])
            clat = float(reg["lat_deg"])
        except (KeyError, TypeError, ValueError):
            continue
        dlon = (lon - clon + 180.0) % 360.0 - 180.0
        dlat = lat - clat
        win = valid & (np.abs(dlon)[None, :] < half) & (np.abs(dlat)[:, None]
                                                        < half)
        mine = np.hypot(np.broadcast_to(dlon[None, :], shape),
                        np.broadcast_to(dlat[:, None], shape))
        for other in regions:
            if other is reg:
                continue
            try:
                oc = float(other["carr_lon_deg"])
                odl = (lon - oc + 180.0) % 360.0 - 180.0
                odla = lat - float(other["lat_deg"])
            except (KeyError, TypeError, ValueError):
                continue
            win &= mine <= np.hypot(np.broadcast_to(odl[None, :], shape),
                                    np.broadcast_to(odla[:, None], shape))
        d_sub = float(sub_earth_distance(np.array([clon]), np.array([clat]),
                                         l0, b0)[0, 0])
        rec = {"number": reg.get("number"), "carr_lon_deg": clon,
               "lat_deg": clat, "sub_earth_deg": round(d_sub, 2),
               "pixels": int(win.sum())}
        if win.sum() >= 200:
            sel = win & (lum >= np.percentile(lum[win], 92.0))
            wt = lum[sel] - float(np.percentile(lum[win], 92.0))
            tot = float(wt.sum())
            if tot > 0:
                olon = float((np.broadcast_to(dlon[None, :], shape)[sel] * wt
                              ).sum() / tot)
                olat = float((np.broadcast_to(dlat[:, None], shape)[sel] * wt
                              ).sum() / tot)
                rec["d_lon_deg"] = round(olon, 2)
                rec["d_lat_deg"] = round(olat, 2)
                rec["offset_deg"] = round(float(np.degrees(np.arccos(np.clip(
                    np.cos(np.radians(olat)) * np.cos(np.radians(olon)),
                    -1.0, 1.0)))), 2)
        out.append(rec)
    return out


def ar_summary(offsets: List[dict]) -> Tuple[Optional[float], int]:
    """(median offset of well-placed regions, how many were usable)."""
    good = [r["offset_deg"] for r in offsets
            if "offset_deg" in r
            and r["sub_earth_deg"] <= TEX_AR_MAX_SUBEARTH_DEG]
    if not good:
        return None, 0
    return float(np.median(good)), len(good)


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────

def offlimb_name(code: str) -> str:
    """File name for one channel's off-limb crop."""
    return "sdo{0}_offlimb_{1}.jpg".format(code, TEX_OFFLIMB_SIZE)


def build_offlimb(src: SourceImage, cx: float, cy: float, r_fit: float
                  ) -> Tuple[bytes, float]:
    """Square crop around the disk with the disk blacked out.

    Returns (jpeg, half_width_rsun) where half_width_rsun is how far from Sun
    centre the crop's edge reaches -- the app needs it to size the billboard,
    and it is NOT a constant: it falls out of the fitted limb radius, which
    differs between AIA (~1.28 R_sun) and HMI (~1.09).

    The disk is removed rather than kept because the sphere already draws it,
    at a resolution this crop cannot match. Feathered across TEX_OFFLIMB_INNER
    so the billboard does not meet the sphere on a hard ring.
    """
    import numpy as np
    from PIL import Image

    h, w = src.rgb.shape[:2]
    # Square, centred on the FITTED disk centre rather than the array centre:
    # measure_limb reports offsets of 12-14 px on AIA browse frames, and a
    # billboard built around the wrong centre would sit visibly off the sphere.
    half = int(min(cx, cy, w - 1 - cx, h - 1 - cy))
    if half < 32:
        raise PipelineError(
            "disk centre ({0:.1f}, {1:.1f}) leaves only {2} px of square crop"
            .format(cx, cy, half))
    x0, y0 = int(round(cx)) - half, int(round(cy)) - half
    crop = src.rgb[y0:y0 + 2 * half, x0:x0 + 2 * half].astype(np.float32)

    # Radius of every pixel, in units of the solar radius.
    n = crop.shape[0]
    yy, xx = np.mgrid[0:n, 0:n]
    centre = (n - 1) / 2.0
    r = np.hypot(yy - centre, xx - centre) / r_fit

    lo, hi = TEX_OFFLIMB_INNER
    t = np.clip((r - lo) / (hi - lo), 0.0, 1.0)
    keep = (t * t * (3.0 - 2.0 * t))[..., None]        # smoothstep
    out = np.clip(crop * keep, 0.0, 255.0).astype(np.uint8)

    img = Image.fromarray(out).resize(
        (TEX_OFFLIMB_SIZE, TEX_OFFLIMB_SIZE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=TEX_OFFLIMB_QUALITY, optimize=True)
    return buf.getvalue(), half / r_fit


def build_texture(now: datetime, regions: Optional[List[dict]] = None,
                  verbose: bool = False, code: str = None
                  ) -> Tuple[bytes, dict, dict, bytes]:
    """Fetch, reproject, composite, encode.  Returns (jpeg, doc, info)."""
    import astropy.units as u
    from astropy.time import Time
    from sunpy.coordinates import get_earth, sun

    channel = channel_for(code or DEFAULT_CODE)
    src = fetch_source(now, verbose=verbose, code=channel["code"])
    obs_age = age_hours(src.obstime, now)
    print("  source: {0} ({1}, {2}, obs {3}, age {4:.2f} h)".format(
        src.url.rsplit("/", 1)[-1], src.kind, human_bytes(src.nbytes),
        iso_z(src.obstime), obs_age))
    if obs_age < -0.1:
        raise PipelineError("source image is {0:.2f} h in the future".format(
            -obs_age))

    obstime = Time(iso_z(src.obstime).replace("Z", ""), scale="utc")
    observer = get_earth(obstime)
    l0 = float(sun.L0(obstime).to_value(u.deg)) % 360.0
    b0 = float(sun.B0(obstime).to_value(u.deg))
    p_deg = float(sun.P(obstime).to_value(u.deg))

    # Sanity check the assumed geometry against the image's own limb.
    r_pred = float(sun.angular_radius(obstime).to_value(u.arcsec)
                   ) / tex_src_scale(channel["scale"])
    cx, cy, r_fit, resid, n_rays = measure_limb(src.rgb.mean(axis=-1), r_pred)
    c_off = float(np.hypot(cx - (TEX_SRC_RES - 1) / 2.0,
                           cy - (TEX_SRC_RES - 1) / 2.0))
    r_err = abs(r_fit / r_pred - 1.0)
    print("  limb fit: r {0:.1f} px vs {1:.1f} predicted ({2:+.2%}), centre "
          "{3:.1f} px off, scatter {4:.1f} px ({5} rays)".format(
              r_fit, r_pred, r_fit / r_pred - 1.0, c_off, resid, n_rays))
    if r_err > TEX_LIMB_RADIUS_TOL or c_off > TEX_LIMB_CENTRE_TOL_PX:
        raise PipelineError(
            "browse JPG geometry has changed: limb radius {0:.1f} px vs "
            "{1:.1f} predicted ({2:+.1%}, tol {3:.0%}), disk centre {4:.1f} "
            "px from the array centre (tol {5:.0f}); the synthesized WCS is "
            "no longer valid".format(r_fit, r_pred, r_fit / r_pred - 1.0,
                           TEX_LIMB_RADIUS_TOL, c_off, TEX_LIMB_CENTRE_TOL_PX))

    in_hdr = input_header(src, obstime, observer, channel=channel)
    out_hdr = output_header(obstime, observer)
    near = reproject_rgb(src, in_hdr, out_hdr)
    lon, lat = grid(out_hdr)
    dist = sub_earth_distance(lon, lat, l0, b0)
    valid = np.isfinite(near).all(axis=-1)

    # Half of a plate-carree map is the visible hemisphere, exactly, whatever
    # B0 is.  A fraction near 1 would mean the far side had been aliased onto
    # the near side (see the module docstring); near 0 means an empty frame.
    frac = float(valid.mean())
    if not 0.40 <= frac <= 0.60:
        raise PipelineError(
            "reprojection covers {0:.1%} of the map, expected ~50%; the far "
            "side is being aliased or the source is blank".format(frac))
    n_cap = float(valid[lat > 86.0].mean())
    s_cap = float(valid[lat < -86.0].mean())
    lit, dark = ((n_cap, s_cap) if b0 >= 0 else (s_cap, n_cap))
    if lit < 0.5 or dark > 0.5:
        raise PipelineError(
            "polar caps disagree with B0 = {0:+.2f} deg (north cap {1:.0%} "
            "visible, south {2:.0%}); the output latitude axis is flipped"
            .format(b0, n_cap, s_cap))

    # Off-limb crop, from the SAME fitted limb the reprojection trusts, so the
    # billboard and the sphere cannot disagree about where the edge is.
    offlimb, offlimb_half_rsun = build_offlimb(src, cx, cy, r_fit)

    img, w, base = compose(near, valid, dist, lon, lat, channel["farside"])
    blob = encode_jpeg(img)

    # Only meaningful in EUV: the check scores by finding BRIGHT pixels near
    # each region, and sunspots are dark in HMIIC while bright in HMIB just
    # means positive polarity (see TEX_CHANNELS.ar_check).
    offsets = (ar_offsets(near, valid, lon, lat, regions or [], l0, b0)
               if channel["ar_check"] else [])
    med, n_good = ar_summary(offsets)

    doc = {
        "schema": SCHEMA_TEXTURE,
        "pipeline_version": PIPELINE_VERSION,
        "generated_iso": iso_z(now),
        "generated_unix": unix_s(now),
        "url": jpeg_name(channel["code"]),
        "width": TEX_OUT_W,
        "height": TEX_OUT_H,
        "bytes": len(blob),
        "projection": "plate carree (CAR), HeliographicCarrington",
        "lon_at_u0_deg": 0.0,
        "north_up": True,
        "channel": channel["code"],
        "label": channel["label"],
        "wavelength_angstrom": channel["wavelength"],
        "obs_iso": iso_z(src.obstime),
        "sub_earth_carr_lon_deg": l0,
        "sub_earth_lat_deg": b0,
        "near_side_half_angle_deg": 90.0,
        # "quiet" adds farside_modulation's invented mottling; "flat" is a
        # plain fill with no fabricated structure. HMIB must never be "quiet" --
        # see TEX_CHANNELS.
        # The off-limb band, drawn as a camera-facing billboard. half_width_rsun
        # is how far the crop reaches from Sun centre; it is NOT constant
        # across channels (AIA ~1.28 R_sun, HMI ~1.09) because it falls out of
        # each instrument's plate scale.
        "off_limb": {
            "url": offlimb_name(channel["code"]),
            "bytes": len(offlimb),
            "size": TEX_OFFLIMB_SIZE,
            "half_width_rsun": round(offlimb_half_rsun, 5),
            "note": ("Square crop centred on the fitted disk centre with the "
                     "disk blacked out. Additively blended, so black is "
                     "transparent. Only valid from the sub-earth viewpoint: it "
                     "is a 2D projection of structure whose depth is unknown."),
        },
        "far_side": channel["farside"],
        "far_side_max_age_hours": None,
        "source": ("SDO/{0} {1} JPEG from sdo.gsfc.nasa.gov ({2} px, "
                   "solar-north-up), synthesized WCS at {3:.4f}\"/px, "
                   "reprojected with sunpy + reproject").format(
                       channel["code"], src.kind, TEX_SRC_RES,
                       tex_src_scale(channel["scale"])),
        "source_url": src.url,
        "note": ("lon_deg = (x + 0.5) * 360/{0}, x = 0..{1} left to right; "
                 "lat_deg = 90 - (y + 0.5) * 180/{2}, y = 0..{3} top to "
                 "bottom. Longitude increases toward solar west (the same "
                 "sense as HeliographicCarrington), so no mirroring is needed "
                 "to match pfss/manifest.json's quat_carr_to_ecl. Observed "
                 "pixels are cross-faded into the quiet base over {4:.0f}-"
                 "{5:.0f} deg from the sub-earth point and above {6:.0f} deg "
                 "latitude, so the honestly-observed band is narrower than "
                 "near_side_half_angle_deg."
                 ).format(TEX_OUT_W, TEX_OUT_W - 1, TEX_OUT_H, TEX_OUT_H - 1,
                          TEX_FEATHER_DEG[0], TEX_FEATHER_DEG[1],
                          TEX_LAT_FADE_DEG[0]),
    }
    info = {
        "obs_age_hours": obs_age,
        "src_bytes": src.nbytes,
        "src_kind": src.kind,
        "p_deg": p_deg,
        "limb_radius_px": r_fit,
        "limb_radius_pred_px": r_pred,
        "limb_centre_offset_px": c_off,
        "valid_fraction": frac,
        "near_fraction": float((w >= 1.0).mean()),
        "feather_fraction": float(((w > 0.0) & (w < 1.0)).mean()),
        "quiet_rgb": [round(float(v), 2) for v in base],
        "ar_offsets": offsets,
        "ar_offset_median_deg": med,
        "ar_offset_n": n_good,
        "brightness": {
            "mean": round(float(img.mean()), 2),
            "p50": round(float(np.percentile(img, 50)), 2),
            "p99": round(float(np.percentile(img, 99)), 2),
            "max": int(img.max()),
        },
    }
    return blob, doc, info, offlimb


def log_texture(info: dict, blob_len: int, verbose: bool = False) -> None:
    """Human-readable summary + the AR registration verdict."""
    print("  {0}x{1} plate carree, {2} JPEG q{3} (near side {4:.0%}, feather "
          "{5:.0%}, quiet fill {6:.0%})".format(
              TEX_OUT_W, TEX_OUT_H, human_bytes(blob_len), TEX_JPEG_QUALITY,
              info["near_fraction"], info["feather_fraction"],
              1.0 - info["near_fraction"] - info["feather_fraction"]))
    print("  quiet-sun base RGB {0}, image mean {1}, p99 {2}".format(
        info["quiet_rgb"], info["brightness"]["mean"],
        info["brightness"]["p99"]))
    med, n = info["ar_offset_median_deg"], info["ar_offset_n"]
    if med is None:
        print("  AR registration: no region within {0:.0f} deg of disk centre "
              "to check against".format(TEX_AR_MAX_SUBEARTH_DEG))
    else:
        print("  AR registration: median offset {0:.2f} deg over {1} "
              "well-placed region(s){2}".format(
                  med, n, "" if med <= TEX_AR_OFFSET_WARN_DEG
                  else "  <-- WARN, expected <= {0:.0f} deg; check the P "
                       "angle, the row order and map_center_longitude"
                       .format(TEX_AR_OFFSET_WARN_DEG)))
    if verbose:
        for r in info["ar_offsets"]:
            if "offset_deg" in r:
                print("    AR{0} carr {1:6.1f} lat {2:+5.1f}  d_sub {3:5.1f}  "
                      "dlon {4:+6.2f} dlat {5:+6.2f}  offset {6:5.2f} deg{7}"
                      .format(r["number"], r["carr_lon_deg"], r["lat_deg"],
                              r["sub_earth_deg"], r["d_lon_deg"],
                              r["d_lat_deg"], r["offset_deg"],
                              "  [limb, feathered]"
                              if r["sub_earth_deg"] > TEX_AR_MAX_SUBEARTH_DEG
                              else ""))
            else:
                print("    AR{0} carr {1:6.1f} lat {2:+5.1f}  d_sub {3:5.1f}  "
                      "not measurable ({4} usable pixel(s))".format(
                          r["number"], r["carr_lon_deg"], r["lat_deg"],
                          r["sub_earth_deg"], r["pixels"]))


def texture_status(obs_age: float) -> str:
    return "ok" if obs_age < TEX_MAX_OBS_AGE_HOURS else "degraded"


__all__ = [
    "JPEG_NAME", "SourceImage", "browse_candidates", "disk_mean",
    "jpeg_name", "channel_for", "DEFAULT_CODE",
    "fetch_source",
    "measure_limb", "input_header", "output_header", "grid",
    "sub_earth_distance", "reproject_rgb", "quiet_sun_rgb",
    "farside_modulation", "feather_weight", "compose", "encode_jpeg",
    "ar_offsets", "ar_summary", "build_texture", "log_texture",
    "texture_status",
]
