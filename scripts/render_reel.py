#!/usr/bin/env python
# =====================================================================
# render_reel.py — a 1080x1920 social reel of the 72 h magnetic field
# =====================================================================
# Renders the published data tree (`public/data`, or any `--root`) to an
# MP4 sized for Reels/Shorts/TikTok: the PFSS field lines animating across
# the whole 72 h window while the sphere beneath cross-fades through all
# five texture channels in `sol.texture/4` order-of-interest —
#
#     Magnetic Map -> Visible Sun -> Chromosphere -> Coronal Loops -> Hot Corona
#
# WHY A SOFTWARE RENDERER AND NOT THE APP.  The obvious route is to drive
# the real app in a browser and screen-record it, and it was rejected for
# four reasons: the app's framing is landscape-first and WWT's FOV is a
# fixed pi/4 VERTICAL (CLAUDE.md footgun 11), so a portrait crop is ~2.2x
# too tight; GL lines are 1 px and aliased, which reads as crawling noise
# at reel bitrates; the browser path is blocked on the Chrome extension
# being connected (TASKS.md T8); and a recorder cannot be asked for exact,
# reproducible frame timings. Rendering offline with numpy gives 2x
# supersampled anti-aliasing, deterministic output, and a framing chosen
# for a phone held upright.
#
# WHAT MAKES IT FAITHFUL ANYWAY.  Every number that decides what the
# picture MEANS is read from the published manifest, never re-invented:
# the dome palette and the opacity model come from `render_hints`, the
# dequantization from `quantization`, the orientation from each frame's
# `quat_carr_to_ecl`, and the surface maps are the pipeline's own
# plate-carree reprojections sampled with the same plate-carree contract
# `texture.json`'s `note` states. The three constants that live in the app
# rather than the data — the far-side dim, its smoothstep band, and the
# glow gradient stops — are copied here with their source file named, and
# `--check-conventions` re-derives the quaternion against the manifest's
# own `mat3_carr_to_ecliptic_j2000` so a convention change fails loudly
# instead of rendering a mirrored Sun (CLAUDE.md footgun 47).
#
# TWO DELIBERATE DEPARTURES FROM THE APP, both noted so they are not read
# as bugs:
#   1. The surface CROSS-FADES between adjacent 4 h slots. The app snaps
#      (`adoptTexture` swaps the map outright). Snapping puts a visible
#      pop every ~1.4 s of reel while the field lines beside it are
#      morphing continuously; a dissolve is the honest analogue of the
#      position lerp the lines already do, and invents no detail that the
#      two bracketing frames do not both contain.
#   2. There is no WWT starfield behind the Sun. Black is unambiguous, and
#      a synthesized starfield would be decoration presented as sky.
#
# COLOR.  three renders linear and encodes sRGB on output; the manifest's
# `render_hints.colors` are already linear (see `Rgb` in src/data/pfss.ts)
# and the JPEG maps are sRGB. So maps are decoded to linear on load, all
# additive accumulation happens in linear, and the frame is encoded back
# to sRGB once, at the end. Getting this wrong is invisible on one layer
# and obvious on three.
#
# Usage:
#   conda run -n sdo python -u scripts/render_reel.py --out reel.mp4
#   ... --frames 1 --at 0.5 --still probe.png      # one frame, to look at
#   ... --check-conventions                        # tripwire only, no render
#
from __future__ import annotations

import argparse
import json
import math
import struct
import subprocess
import sys
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent

# --- Reel geometry ----------------------------------------------------
OUT_W, OUT_H = 1080, 1920
SUPERSAMPLE = 2                     # rendered at 2160x3840, box-filtered down
FPS = 30

# --- Framing ----------------------------------------------------------
# Distance is generous on purpose: at the app's ~2.8 R_sun home framing the
# 2.5 R_sun source surface is almost in the camera's lap, and the open lines
# splay off-frame. 12 R_sun keeps enough perspective to read as 3D while the
# whole field volume stays inside a portrait frame.
CAM_DISTANCE_RSUN = 12.0
HALF_WIDTH_START = 2.50             # horizontal half-span at the Sun, R_sun
HALF_WIDTH_END = 2.20               # a slow push-in over the reel
SUN_CENTER_Y = 0.470                # Sun's screen center, fraction of height
AZIMUTH_SWEEP_DEG = (-15.0, 15.0)   # drift about the SOLAR axis, from sub-Earth
ELEVATION_EXTRA_DEG = 11.0          # above the sub-Earth latitude (B0)

# --- Timing (seconds) -------------------------------------------------
TOTAL_SECONDS = 28.0
PLAYHEAD_SECONDS = 26.0             # 72 h sweep; the tail holds on "now"
FADE_IN_SECONDS = 0.8
CHANNEL_START = 0.5                 # first channel is up before the sweep bites
CHANNEL_END = 26.6
CROSSFADE_SECONDS = 0.9

# The requested order. Channel codes are `sol.texture/4`'s own; the labels
# are read from the manifest so the reel can never disagree with the app.
CHANNEL_ORDER = ["HMIB", "HMIIC", "0304", "0171", "0193"]

# --- Surface far-side treatment (src/three/sunSurface.ts:375-384) ------
OBSERVED_INNER_RAD = math.radians(75.0)
OBSERVED_OUTER_RAD = math.radians(90.0)
FAR_SIDE_DIM = 0.45

# --- Sun glow (src/three/sunGlow.ts drawGradient) ---------------------
# The stops are the app's, verbatim. The RADIUS and GAIN are not, and the
# reason is framing rather than taste: sunGlow's 3 R_sun halo is tuned for a
# view where the Sun fills most of the frame, so its long low tail falls off
# the edges. Here the Sun is ~40% of the frame width, which puts that tail
# across the whole picture — the first render came out as a brown box with a
# Sun in it. Pulling the halo in to 2.2 R_sun and to just over half strength
# keeps the atmosphere it exists for and lets the frame go black again.
GLOW_RADII = 2.2                    # halo radius in R_sun (app: 3.0)
GLOW_GAIN = 0.55                    # (app: 1.0)
GLOW_STOPS = [                      # (t, r, g, b in sRGB 0-255, alpha)
    (0.00, 255, 246, 224, 0.30),
    (0.30, 255, 232, 175, 0.26),
    (0.42, 255, 198, 110, 0.11),
    (0.65, 255, 165, 66, 0.035),
    (1.00, 255, 150, 50, 0.0),
]

# --- Line rendering ---------------------------------------------------
# The app draws 1 px GL lines. At 2x supersample that would downsample to a
# half-pixel thread that H.264 turns to mush, so the reel draws a slightly
# fatter line: sigma is in SUPERSAMPLED pixels, i.e. ~0.55 px at 1080 wide.
LINE_SIGMA_SS = 1.10
LINE_SAMPLE_STEP_SS = 0.55          # spacing along a segment, supersampled px
# 0.75, not 1.0: the reel's line is ~1.3 px against the app's 1.0 px, so an
# equal per-line alpha piles up ~30% more energy where the low closed arcades
# overlap, and the gold clipped to white exactly where the structure is
# densest — the most interesting part of the picture (sunGlow.ts's own words).
LINE_GAIN = 0.75                    # global multiplier on the manifest opacity

# --- Palette (src/assets/sol.less) ------------------------------------
INK = (245, 244, 240)               # --sol-text
INK_DIM = (166, 174, 196)           # --sol-text-dim
INK_QUIET = (126, 134, 160)         # --sol-text-quiet
ACCENT = (255, 200, 80)             # --sol-accent

FONT_PATH = REPO / "src" / "assets" / "Overpass-SemiBold.ttf"


def instrument_line(layer: dict) -> str:
    """What a channel actually IS, under its guest-facing label.

    Derived from the manifest rather than tabulated here: `wavelength_angstrom`
    is present exactly for the three AIA channels and null for the two HMI
    products (pipeline/config.py TEX_CHANNELS), which is the same distinction
    `far_side` turns on -- a magnetogram's far side is flat because inventing
    magnetic field is not a stylization, it is a fabrication (footgun 22).
    """
    wl = layer.get("wavelength_angstrom")
    if wl:
        return f"SDO / AIA  {wl} Å"
    return {"HMIB": "SDO / HMI  magnetogram",
            "HMIIC": "SDO / HMI  visible light"}.get(layer["channel"], "SDO / HMI")


# =====================================================================
# Small math
# =====================================================================

def srgb_to_linear(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    return np.where(x <= 0.04045, x / 12.92,
                    np.power((x + 0.055) / 1.055, 2.4)).astype(np.float32)


def linear_to_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92,
                    1.055 * np.power(x, 1.0 / 2.4) - 0.055).astype(np.float32)


def quat_to_matrix(q) -> np.ndarray:
    """[x, y, z, w] (THREE order) -> 3x3 rotation, v_ecl = M @ v_carr."""
    x, y, z, w = (float(v) for v in q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def slerp(qa, qb, t: float) -> np.ndarray:
    a = np.asarray(qa, dtype=np.float64)
    b = np.asarray(qb, dtype=np.float64)
    dot = float(np.dot(a, b))
    if dot < 0.0:            # shortest arc — the app's Quaternion.slerp does this
        b = -b
        dot = -dot
    if dot > 0.9995:
        out = a + t * (b - a)
        return out / np.linalg.norm(out)
    theta0 = math.acos(max(-1.0, min(1.0, dot)))
    theta = theta0 * t
    perp = b - a * dot
    perp /= np.linalg.norm(perp)
    return a * math.cos(theta) + perp * math.sin(theta)


def carr_unit(lon_deg: float, lat_deg: float) -> np.ndarray:
    """HeliographicCarrington cartesian (src/three/sunSurface.ts:20-24)."""
    lon = math.radians(lon_deg)
    lat = math.radians(lat_deg)
    return np.array([math.cos(lat) * math.cos(lon),
                     math.cos(lat) * math.sin(lon),
                     math.sin(lat)], dtype=np.float64)


def smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def ease(t: float) -> float:
    """Smootherstep, for camera drift that starts and ends at rest."""
    t = min(1.0, max(0.0, t))
    return t * t * t * (t * (t * 6 - 15) + 10)


# =====================================================================
# PFSS wire formats (specified in src/data/pfss.ts's header)
# =====================================================================

TOPOLOGY_MAGIC = b"SOLTOPO1"
FRAME_MAGIC = b"SOLPFRM1"
HEADER_BYTES = 32


class Topology:
    def __init__(self, path: Path):
        buf = path.read_bytes()
        if buf[:8] != TOPOLOGY_MAGIC:
            raise SystemExit(f"{path}: bad magic {buf[:8]!r}")
        n_lines, n_verts, n_bg, _res = struct.unpack_from("<4I", buf, 8)
        at = HEADER_BYTES
        self.n_lines = n_lines
        self.n_verts = n_verts
        self.n_bg = n_bg
        self.line_offset = np.frombuffer(buf, "<u4", n_lines + 1, at).astype(np.int64)
        at += 4 * (n_lines + 1)
        at += 2 * n_lines          # seed_lat_cdeg — unused here
        at += 2 * n_lines          # seed_lon_u16  — unused here
        at += 2 * n_lines          # ar_index      — unused here
        if len(buf) != at:
            raise SystemExit(f"{path}: length {len(buf)} B, expected {at} B")
        if self.line_offset[-1] != n_verts:
            raise SystemExit(f"{path}: lineOffset tail != nVertsTotal")

        # Fixed topology means the segment list is built ONCE for all 19
        # frames — the pipeline guarantees seed i is row i in every frame.
        starts = []
        for i in range(n_lines):
            a, b = int(self.line_offset[i]), int(self.line_offset[i + 1])
            if b - a >= 2:
                starts.append(np.arange(a, b - 1, dtype=np.int64))
        self.seg_a = np.concatenate(starts) if starts else np.zeros(0, np.int64)
        self.seg_b = self.seg_a + 1

        # Per-vertex line id, so per-LINE polarity/valid expand with a gather.
        self.vert_line = np.zeros(n_verts, dtype=np.int32)
        for i in range(n_lines):
            self.vert_line[self.line_offset[i]:self.line_offset[i + 1]] = i


class Frame:
    def __init__(self, path: Path, n_lines: int, n_verts: int):
        buf = path.read_bytes()
        if buf[:8] != FRAME_MAGIC:
            raise SystemExit(f"{path}: bad magic {buf[:8]!r}")
        index, f_lines, f_verts, mag_unix = struct.unpack_from("<4I", buf, 8)
        if (f_lines, f_verts) != (n_lines, n_verts):
            raise SystemExit(f"{path}: geometry {f_lines}x{f_verts} != topology")
        at = HEADER_BYTES
        self.index = index
        self.mag_unix = mag_unix
        self.xyz_u16 = np.frombuffer(buf, "<u2", n_verts * 3, at).reshape(n_verts, 3)
        at += n_verts * 3 * 2
        self.polarity = np.frombuffer(buf, "<i1", n_lines, at)
        at += n_lines
        self.valid = np.frombuffer(buf, "<u1", n_lines, at)
        at += n_lines
        if len(buf) != at:
            raise SystemExit(f"{path}: length {len(buf)} B, expected {at} B")


# =====================================================================
# Scene data
# =====================================================================

class Scene:
    def __init__(self, root: Path, verbose: bool = True):
        self.root = root
        self.verbose = verbose

        man_path = root / "pfss" / "manifest.json"
        self.manifest = json.loads(man_path.read_text(encoding="utf-8"))
        hints = self.manifest["render_hints"]
        self.colors = {
            0: np.array(hints["colors"]["closed"], dtype=np.float32),
            1: np.array(hints["colors"]["open_pos"], dtype=np.float32),
            -1: np.array(hints["colors"]["open_neg"], dtype=np.float32),
        }
        self.rss = float(hints["opacity_model"]["rss"])
        self.closed_floor = float(hints["opacity_model"]["closed_floor"])
        quant = self.manifest["quantization"]["xyz"]
        self.q_scale = float(quant["scale"])
        self.q_offset = float(quant["offset"])

        self.topology = Topology(root / "pfss" / "topology.bin")
        self.meta = self.manifest["frames"]
        self.frames = [
            Frame(root / "pfss" / f["url"], self.topology.n_lines, self.topology.n_verts)
            for f in self.meta
        ]
        self.n_frames = len(self.frames)
        self.frame_unix = np.array(
            [iso_to_unix(f["target_iso"]) for f in self.meta], dtype=np.float64)
        self.quats = [np.array(f["quat_carr_to_ecl"], dtype=np.float64) for f in self.meta]

        # Per-frame, per-VERTEX color + meta alpha, precomputed once. 19 x
        # 18,926 x 4 floats is 5.8 MB and turns the per-render-frame work
        # into two gathers and a lerp.
        self.vcolor = []
        self.valpha = []
        for fr in self.frames:
            pol = fr.polarity[self.topology.vert_line]
            val = fr.valid[self.topology.vert_line]
            rgb = np.empty((self.topology.n_verts, 3), dtype=np.float32)
            rgb[pol == 0] = self.colors[0]
            rgb[pol > 0] = self.colors[1]
            rgb[pol < 0] = self.colors[-1]
            # meta.a: 255 = valid + closed, 128 = valid + open, 0 = dead seed
            # (src/three/fieldLines.ts buildMeta), normalized as the GPU sees it.
            a = np.where(val != 0, np.where(pol == 0, 255.0, 128.0), 0.0) / 255.0
            self.vcolor.append(rgb)
            self.valpha.append(a.astype(np.float32))

        # --- surface maps -------------------------------------------------
        tex = json.loads((root / "texture" / "texture.json").read_text(encoding="utf-8"))
        self.layers = {L["channel"]: L for L in tex["layers"]}
        missing = [c for c in CHANNEL_ORDER if c not in self.layers]
        if missing:
            raise SystemExit(f"texture.json has no layer(s) for {missing}")
        self.layer_unix = {
            c: np.array([iso_to_unix(f["target_iso"]) for f in self.layers[c]["frames"]],
                        dtype=np.float64)
            for c in CHANNEL_ORDER
        }
        self._tex_cache: "OrderedDict[str, np.ndarray]" = OrderedDict()
        self._tex_cache_max = 6

    # -- textures ---------------------------------------------------------
    def texture(self, channel: str, index: int) -> np.ndarray:
        """One surface map as LINEAR float32 (H, W, 3), resized to 2048x1024.

        Everything is normalized to one size on purpose: the newest slot
        ships at 4096x2048 (and the hi-res block at 8192x4096), which is far
        more than a 520 px Sun can show, and mixing sizes would make the
        cross-fade between two slots resample differently on each side.
        """
        key = f"{channel}:{index}"
        hit = self._tex_cache.get(key)
        if hit is not None:
            self._tex_cache.move_to_end(key)
            return hit
        meta = self.layers[channel]["frames"][index]
        path = self.root / "texture" / meta["url"]
        img = Image.open(path).convert("RGB")
        if img.size != (2048, 1024):
            img = img.resize((2048, 1024), Image.LANCZOS)
        arr = srgb_to_linear(np.asarray(img, dtype=np.float32) / 255.0)
        self._tex_cache[key] = arr
        while len(self._tex_cache) > self._tex_cache_max:
            self._tex_cache.popitem(last=False)
        return arr

    def surface_slot(self, channel: str, t_unix: float):
        """Bracketing slots + fraction for a wall-clock time.

        Time-based rather than index-based because the texture window and
        the PFSS window are published by different stages and need not carry
        the same slot count (footgun 36 keys texture frames on target time
        for exactly this reason).
        """
        times = self.layer_unix[channel]
        if t_unix <= times[0]:
            return 0, 0, 0.0
        if t_unix >= times[-1]:
            last = len(times) - 1
            return last, last, 0.0
        j = int(np.searchsorted(times, t_unix))
        i = j - 1
        span = times[j] - times[i]
        f = 0.0 if span <= 0 else float((t_unix - times[i]) / span)
        return i, j, f


def iso_to_unix(iso: str) -> float:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc).timestamp()


# =====================================================================
# Camera
# =====================================================================

class Camera:
    """Perspective camera looking at the Sun's center with solar north up.

    Solar north rather than the ecliptic pole because that is what the app's
    `sunStage.orbitByPixels` maintains (footgun 26) — the Sun's rotation axis
    should sit vertical in the frame, not tilt with the ecliptic.
    """

    def __init__(self, pos, up, half_width_rsun: float, width: int, height: int,
                 center_y: float):
        self.pos = np.asarray(pos, dtype=np.float64)
        dist = float(np.linalg.norm(self.pos))
        self.forward = -self.pos / dist
        right = np.cross(self.forward, np.asarray(up, dtype=np.float64))
        self.right = right / np.linalg.norm(right)
        self.up = np.cross(self.right, self.forward)
        self.width = width
        self.height = height
        self.tan_h = half_width_rsun / dist
        self.tan_v = self.tan_h * height / width
        self.cx = width * 0.5
        # The Sun sits above centre so the channel label and clock have room.
        self.cy = height * center_y
        self.px_per_rsun = (width * 0.5) / half_width_rsun

    def project(self, pts: np.ndarray):
        """(N,3) world R_sun -> (px, py, depth). depth <= 0 is behind."""
        v = pts - self.pos
        z = v @ self.forward
        x = v @ self.right
        y = v @ self.up
        safe = np.where(np.abs(z) < 1e-9, 1e-9, z)
        # NDC is [-1,1] on each axis independently, so x scales by half the
        # WIDTH and y by half the HEIGHT. Using the width for both squashes
        # the Sun into an ellipse of exactly aspect ratio W/H — which is what
        # it did on the first render, and it looks like a camera bug rather
        # than a projection one.
        px = self.cx + (x / safe) / self.tan_h * (self.width * 0.5)
        py = self.cy - (y / safe) / self.tan_v * (self.height * 0.5)
        return px, py, z

    def ray_dirs(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """Unit ray directions for pixel centres (xs, ys)."""
        ndx = (xs + 0.5 - self.cx) / (self.width * 0.5) * self.tan_h
        ndy = -(ys + 0.5 - self.cy) / (self.height * 0.5) * self.tan_v
        d = (self.forward[None, :]
             + ndx[:, None] * self.right[None, :]
             + ndy[:, None] * self.up[None, :])
        return d / np.linalg.norm(d, axis=1, keepdims=True)


def build_camera(scene: Scene, playhead: float, progress: float,
                 width: int, height: int) -> Camera:
    """Place the camera relative to the SUB-EARTH point of this instant.

    Anchoring to sub-Earth (not to a fixed ecliptic direction) keeps the
    hemisphere SDO actually observed facing the viewer for the whole 72 h,
    so the far-side fill stays behind the limb where it belongs and the
    reel never shows invented surface as though it were data.
    """
    ia = min(int(math.floor(playhead)), scene.n_frames - 1)
    ib = min(ia + 1, scene.n_frames - 1)
    f = playhead - ia
    rot = quat_to_matrix(slerp(scene.quats[ia], scene.quats[ib], f))

    l0 = (1 - f) * scene.meta[ia]["l0_deg"] + f * scene.meta[ib]["l0_deg"]
    b0 = (1 - f) * scene.meta[ia]["b0_deg"] + f * scene.meta[ib]["b0_deg"]

    north = rot @ np.array([0.0, 0.0, 1.0])
    north /= np.linalg.norm(north)
    sub_earth = rot @ carr_unit(l0, b0)

    east = np.cross(north, sub_earth)
    east /= np.linalg.norm(east)
    ref = np.cross(east, north)                 # sub-Earth, de-tilted to the equator
    ref /= np.linalg.norm(ref)

    e = ease(progress)
    az = math.radians(AZIMUTH_SWEEP_DEG[0] + e * (AZIMUTH_SWEEP_DEG[1] - AZIMUTH_SWEEP_DEG[0]))
    el = math.radians(b0 + ELEVATION_EXTRA_DEG)
    direction = (math.cos(el) * (math.cos(az) * ref + math.sin(az) * east)
                 + math.sin(el) * north)

    half_width = HALF_WIDTH_START + e * (HALF_WIDTH_END - HALF_WIDTH_START)
    return Camera(direction * CAM_DISTANCE_RSUN, north, half_width,
                  width, height, SUN_CENTER_Y)


# =====================================================================
# Layers
# =====================================================================

def glow_layer(cam: Camera, width: int, height: int) -> np.ndarray:
    """The app's additive halo, evaluated in screen space.

    `src/three/sunGlow.ts` is a camera-facing Sprite of 2*GLOW_RADII R_sun
    centred on the Sun, so its projection is exactly a radial ramp of
    GLOW_RADII R_sun in pixels. Contribution is colour * alpha: the material
    is AdditiveBlending with premultipliedAlpha left false, i.e. (SRC_ALPHA, ONE).
    """
    ys, xs = np.mgrid[0:height, 0:width]
    r = np.hypot(xs + 0.5 - cam.cx, ys + 0.5 - cam.cy) / (GLOW_RADII * cam.px_per_rsun)
    r = np.clip(r, 0.0, 1.0).astype(np.float32)

    stops = np.array([s[0] for s in GLOW_STOPS], dtype=np.float32)
    rgba = np.array([[s[1] / 255.0, s[2] / 255.0, s[3] / 255.0, s[4]] for s in GLOW_STOPS],
                    dtype=np.float32)
    out = np.empty((height, width, 3), dtype=np.float32)
    a = np.interp(r, stops, rgba[:, 3]).astype(np.float32)
    for c in range(3):
        srgb = np.interp(r, stops, rgba[:, c]).astype(np.float32)
        out[:, :, c] = srgb_to_linear(srgb) * a * GLOW_GAIN
    return out


def surface_layer(scene: Scene, cam: Camera, rot: np.ndarray, t_unix: float,
                  weights: dict, width: int, height: int):
    """Ray-trace the unit sphere and paint the blended surface maps.

    Returns (rgb, coverage, depth) where coverage is 1 inside the disk and
    depth is the distance from the camera to the near hit (used as the
    occluder for the field lines, exactly as the app's opaque sphere is).
    """
    rgb = np.zeros((height, width, 3), dtype=np.float32)
    cover = np.zeros((height, width), dtype=np.float32)
    depth = np.full((height, width), np.inf, dtype=np.float32)

    # Only the sphere's screen bounding box can hit — ~1/12 of the frame.
    dist = float(np.linalg.norm(cam.pos))
    ang = math.asin(min(1.0, 1.0 / dist))
    rad_px = math.tan(ang) / cam.tan_h * (width * 0.5) * 1.04 + 3.0
    x0 = max(0, int(cam.cx - rad_px)); x1 = min(width, int(cam.cx + rad_px) + 1)
    y0 = max(0, int(cam.cy - rad_px)); y1 = min(height, int(cam.cy + rad_px) + 1)
    if x1 <= x0 or y1 <= y0:
        return rgb, cover, depth

    ys, xs = np.mgrid[y0:y1, x0:x1]
    shape = xs.shape
    dirs = cam.ray_dirs(xs.ravel().astype(np.float64), ys.ravel().astype(np.float64))

    oc = cam.pos
    b = 2.0 * (dirs @ oc)
    c = float(oc @ oc) - 1.0
    disc = b * b - 4.0 * c                      # a == 1, dirs are unit
    hit = disc > 0.0
    if not np.any(hit):
        return rgb, cover, depth

    sq = np.zeros_like(disc)
    sq[hit] = np.sqrt(disc[hit])
    t_hit = (-b - sq) * 0.5
    hit &= t_hit > 0.0

    p = oc[None, :] + t_hit[:, None] * dirs     # world (ecliptic) hit points
    p_carr = p @ rot                            # rot is orthonormal: inverse == transpose

    lon = np.arctan2(p_carr[:, 1], p_carr[:, 0])
    lat = np.arcsin(np.clip(p_carr[:, 2], -1.0, 1.0))

    # texture.json's own contract: lon_deg = (x+0.5)*360/W increasing toward
    # solar west, lat_deg = 90 - (y+0.5)*180/H.
    u = (lon / (2.0 * math.pi)) % 1.0
    v = 0.5 - lat / math.pi

    # Blend the channels the reel is cross-fading between, and within each
    # channel the two bracketing 4 h slots.
    acc = np.zeros((u.size, 3), dtype=np.float32)
    for channel, w in weights.items():
        if w <= 1e-4:
            continue
        i, j, f = scene.surface_slot(channel, t_unix)
        sample = sample_equirect(scene.texture(channel, i), u, v)
        if j != i and f > 1e-4:
            sample = sample * (1.0 - f) + sample_equirect(scene.texture(channel, j), u, v) * f
        meta_i = scene.layers[channel]["frames"][i]
        meta_j = scene.layers[channel]["frames"][j]
        se_lon = (1 - f) * meta_i["sub_earth_carr_lon_deg"] + f * meta_j["sub_earth_carr_lon_deg"]
        se_lat = (1 - f) * meta_i["sub_earth_lat_deg"] + f * meta_j["sub_earth_lat_deg"]
        acc += w * (sample * far_side_dim(lon, lat, se_lon, se_lat)[:, None])

    total = sum(weights.values())
    if total > 1e-4:
        acc /= total

    band_rgb = np.zeros((u.size, 3), dtype=np.float32)
    band_rgb[hit] = acc[hit]
    rgb[y0:y1, x0:x1] = band_rgb.reshape(shape + (3,))
    cover[y0:y1, x0:x1] = hit.reshape(shape).astype(np.float32)
    band_d = np.where(hit, t_hit, np.inf).astype(np.float32)
    depth[y0:y1, x0:x1] = band_d.reshape(shape)
    return rgb, cover, depth


def far_side_dim(lon: np.ndarray, lat: np.ndarray,
                 se_lon_deg: float, se_lat_deg: float) -> np.ndarray:
    """src/three/sunSurface.ts's onBeforeCompile chunk, verbatim in numpy.

    Says "we did not observe this half" in the one language a picture has.
    """
    se_lon = math.radians(se_lon_deg)
    se_lat = math.radians(se_lat_deg)
    cosd = np.sin(lat) * math.sin(se_lat) + np.cos(lat) * math.cos(se_lat) * np.cos(lon - se_lon)
    ang = np.arccos(np.clip(cosd, -1.0, 1.0))
    far = smoothstep(OBSERVED_INNER_RAD, OBSERVED_OUTER_RAD, ang)
    return (1.0 + (FAR_SIDE_DIM - 1.0) * far).astype(np.float32)


def sample_equirect(tex: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinear, wrapping in u (the map is seamless in longitude), clamped in v."""
    h, w, _ = tex.shape
    fx = u * w - 0.5
    fy = np.clip(v * h - 0.5, 0.0, h - 1.0)
    x0 = np.floor(fx).astype(np.int64)
    y0 = np.floor(fy).astype(np.int64)
    tx = (fx - x0).astype(np.float32)[:, None]
    ty = (fy - y0).astype(np.float32)[:, None]
    x0m = x0 % w
    x1m = (x0 + 1) % w
    y0c = np.clip(y0, 0, h - 1)
    y1c = np.clip(y0 + 1, 0, h - 1)
    a = tex[y0c, x0m]
    b = tex[y0c, x1m]
    c = tex[y1c, x0m]
    d = tex[y1c, x1m]
    return (a * (1 - tx) * (1 - ty) + b * tx * (1 - ty)
            + c * (1 - tx) * ty + d * tx * ty)


def field_line_layer(scene: Scene, cam: Camera, playhead: float,
                     sphere_depth: np.ndarray, width: int, height: int,
                     opacity: float) -> np.ndarray:
    """The PFSS lines, morphed and additively accumulated in linear light.

    Mirrors src/three/fieldLines.ts's vertex shader step for step: lerp the
    two frames' quantized positions, derive the opacity from the dequantized
    radius via the manifest's model, and separate the validity ramp (which
    SHOULD cross-fade) from the class flag (which must not).
    """
    from scipy.ndimage import gaussian_filter

    topo = scene.topology
    last = scene.n_frames - 1
    ia = min(int(math.floor(playhead)), last)
    ib = min(ia + 1, last)
    u = 0.0 if ib == ia else playhead - ia

    pa = scene.frames[ia].xyz_u16.astype(np.float32) / 65535.0
    pb = scene.frames[ib].xyz_u16.astype(np.float32) / 65535.0
    p = (pa * (1.0 - u) + pb * u) * scene.q_scale + scene.q_offset
    r = np.linalg.norm(p, axis=1)

    t = np.clip((r - 1.0) / max(scene.rss - 1.0, 1e-3), 0.0, 1.0)
    a_closed = np.maximum(scene.closed_floor, 1.0 - (1.0 - scene.closed_floor) * t)
    a_open = np.clip(1.0 - t, 0.0, 1.0)

    ma = scene.valpha[ia]
    mb = scene.valpha[ib]
    vis_a = (ma > 0.01).astype(np.float32)
    vis_b = (mb > 0.01).astype(np.float32)
    vis = vis_a * (1.0 - u) + vis_b * u
    meta_a = ma * (1.0 - u) + mb * u
    closed = (meta_a / np.maximum(vis, 1e-3) >= 0.7).astype(np.float32)

    alpha = vis * (a_open * (1.0 - closed) + a_closed * closed) * opacity * LINE_GAIN
    color = scene.vcolor[ia] * (1.0 - u) + scene.vcolor[ib] * u

    rot = quat_to_matrix(slerp(scene.quats[ia], scene.quats[ib], u))
    world = p.astype(np.float64) @ rot.T

    px, py, depth = cam.project(world)

    acc = np.zeros((height * width, 3), dtype=np.float32)

    sa, sb = topo.seg_a, topo.seg_b
    live = (alpha[sa] > 0.004) | (alpha[sb] > 0.004)
    live &= (depth[sa] > 0) & (depth[sb] > 0)
    sa, sb = sa[live], sb[live]
    if sa.size == 0:
        return acc.reshape(height, width, 3)

    x0, y0 = px[sa], py[sa]
    x1, y1 = px[sb], py[sb]
    seg_len = np.hypot(x1 - x0, y1 - y0)
    nsamp = np.maximum(2, np.ceil(seg_len / LINE_SAMPLE_STEP_SS).astype(np.int64) + 1)
    # A segment that lands on a single pixel still gets one sample; a wild
    # one (a vertex projected near the camera plane) is capped so a single
    # degenerate line cannot cost the whole frame.
    nsamp = np.minimum(nsamp, 4096)

    total = int(nsamp.sum())
    seg_id = np.repeat(np.arange(sa.size, dtype=np.int64), nsamp)
    within = np.arange(total, dtype=np.int64) - np.repeat(
        np.concatenate(([0], np.cumsum(nsamp)[:-1])), nsamp)
    frac = (within / np.maximum(nsamp[seg_id] - 1, 1)).astype(np.float32)

    sx = x0[seg_id] * (1 - frac) + x1[seg_id] * frac
    sy = y0[seg_id] * (1 - frac) + y1[seg_id] * frac
    sa_alpha = alpha[sa][seg_id] * (1 - frac) + alpha[sb][seg_id] * frac
    scol = color[sa][seg_id] * (1 - frac)[:, None] + color[sb][seg_id] * frac[:, None]

    # Occlusion by the Sun, evaluated per SAMPLE against the sphere's depth
    # buffer — the same job the app hands to depthTest against its opaque
    # sphere (footgun 18: the sphere is the authoritative occluder).
    ix = np.floor(sx).astype(np.int64)
    iy = np.floor(sy).astype(np.int64)
    inside = (ix >= 0) & (ix < width - 1) & (iy >= 0) & (iy < height - 1)
    if not np.any(inside):
        return acc.reshape(height, width, 3)

    # Sample depth along the segment the same way the position is sampled.
    sdepth = depth[sa][seg_id] * (1 - frac) + depth[sb][seg_id] * frac
    keep = inside.copy()
    flat = np.where(inside, iy * width + ix, 0)
    occl = sphere_depth.reshape(-1)[flat]
    keep &= ~(sdepth > occl + 1e-4)

    if not np.any(keep):
        return acc.reshape(height, width, 3)

    # Constant PEAK brightness regardless of sample spacing: for a Gaussian
    # of sigma s laid down every `step` px, peak = (E/step)/(s*sqrt(2pi)),
    # so E = alpha * step * s * sqrt(2pi). Splat with bilinear taps and let
    # one separable blur below do the widening — 4 scatter adds per sample
    # instead of ~80.
    energy = (sa_alpha * LINE_SAMPLE_STEP_SS * LINE_SIGMA_SS * math.sqrt(2.0 * math.pi))
    sx, sy, scol, energy = sx[keep], sy[keep], scol[keep], energy[keep]
    ix, iy = np.floor(sx).astype(np.int64), np.floor(sy).astype(np.int64)
    tx = (sx - ix).astype(np.float32)
    ty = (sy - iy).astype(np.float32)

    base = iy * width + ix
    idx = np.concatenate([base, base + 1, base + width, base + width + 1])
    wts = np.concatenate([(1 - tx) * (1 - ty), tx * (1 - ty),
                          (1 - tx) * ty, tx * ty]) * np.tile(energy, 4)
    cols = np.tile(scol, (4, 1))
    n = height * width
    for ch in range(3):
        acc[:, ch] = np.bincount(idx, weights=wts * cols[:, ch], minlength=n)

    out = acc.reshape(height, width, 3)
    return gaussian_filter(out, sigma=(LINE_SIGMA_SS, LINE_SIGMA_SS, 0), mode="nearest")


# =====================================================================
# Timeline
# =====================================================================

def channel_weights(t: float) -> dict:
    """Cross-fade weights across CHANNEL_ORDER at reel time `t` seconds."""
    n = len(CHANNEL_ORDER)
    span = (CHANNEL_END - CHANNEL_START) / n
    weights = {}
    for i, ch in enumerate(CHANNEL_ORDER):
        start = CHANNEL_START + i * span
        end = start + span
        rise = 1.0 if i == 0 else smoothstep(start - CROSSFADE_SECONDS * 0.5,
                                             start + CROSSFADE_SECONDS * 0.5,
                                             np.array(t)).item()
        fall = 1.0 if i == n - 1 else 1.0 - smoothstep(end - CROSSFADE_SECONDS * 0.5,
                                                       end + CROSSFADE_SECONDS * 0.5,
                                                       np.array(t)).item()
        w = rise * fall
        if w > 1e-4:
            weights[ch] = w
    if not weights:
        weights = {CHANNEL_ORDER[0]: 1.0}
    return weights


def playhead_at(t: float, n_frames: int) -> float:
    """72 h swept linearly, then held on the newest frame for the tail beat."""
    if t >= PLAYHEAD_SECONDS:
        return float(n_frames - 1)
    return (t / PLAYHEAD_SECONDS) * (n_frames - 1)


# =====================================================================
# Overlay
# =====================================================================

def load_fonts():
    def f(size):
        try:
            return ImageFont.truetype(str(FONT_PATH), size)
        except OSError:
            return ImageFont.truetype("segoeuib.ttf", size)
    return {
        "title": f(58),
        "sub": f(30),
        "channel": f(64),
        "clock": f(38),
        "small": f(25),
        "tiny": f(22),
    }


def draw_overlay(img: Image.Image, fonts, scene: Scene, t: float,
                 weights: dict, t_unix: float, playhead: float) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    W, H = img.size

    # A global fade so the reel opens and closes on black rather than cutting.
    fade = min(1.0, t / FADE_IN_SECONDS) if t < FADE_IN_SECONDS else 1.0
    tail = TOTAL_SECONDS - t
    if tail < 0.6:
        fade = min(fade, max(0.0, tail / 0.6))

    def a(x: float) -> int:
        return int(round(max(0.0, min(1.0, x * fade)) * 255))

    def centered(text, font, y, fill, alpha, spacing=0):
        if spacing == 0:
            w = d.textlength(text, font=font)
            d.text(((W - w) / 2, y), text, font=font, fill=fill + (a(alpha),))
            return
        widths = [d.textlength(c, font=font) for c in text]
        total = sum(widths) + spacing * (len(text) - 1)
        x = (W - total) / 2
        for c, cw in zip(text, widths):
            d.text((x, y), c, font=font, fill=fill + (a(alpha),))
            x += cw + spacing

    # --- title ---------------------------------------------------------
    centered("THE SUN'S MAGNETIC FIELD", fonts["title"], 138, INK, 1.0, spacing=2)
    centered("the last 72 hours", fonts["sub"], 212, INK_DIM, 1.0)

    # --- field-line key -------------------------------------------------
    key = [("closed loops", (255, 200, 80)),
           ("open, outward", (110, 150, 255)),
           ("open, inward", (255, 120, 60))]
    dot, gap, pad = 13, 26, 13
    widths = [d.textlength(t2, font=fonts["small"]) for t2, _ in key]
    total = sum(widths) + len(key) * (dot + pad) + gap * (len(key) - 1)
    x = (W - total) / 2
    ky = 276
    for (label, col), tw in zip(key, widths):
        d.ellipse([x, ky + 7, x + dot, ky + 7 + dot], fill=col + (a(0.92),))
        x += dot + pad
        d.text((x, ky), label, font=fonts["small"], fill=INK_DIM + (a(0.92),))
        x += tw + gap

    # --- channel label, cross-fading with the surface it names ----------
    # ONE label, dipping through zero at the crossover — never two.
    # Cross-fading the two names in place the way the surface cross-fades
    # looked obvious and was unreadable: both are centred, so mid-transition
    # they render as "MVAIGSNIEBTLIEC SMUANP" at half opacity each. The
    # surface can dissolve because the two images are the same subject; two
    # words are not. Blanking for ~0.35 s reads as a deliberate swap instead.
    y_channel = 1462
    top_ch = max(weights, key=weights.get)
    top_w = weights[top_ch]
    label_a = smoothstep(0.5, 0.9, np.array(top_w)).item()
    if label_a > 0.01:
        layer = scene.layers[top_ch]
        centered(layer["label"].upper(), fonts["channel"], y_channel, INK,
                 label_a, spacing=3)
        centered(instrument_line(layer), fonts["small"], y_channel + 82, INK_QUIET,
                 label_a * 0.85)

    # --- clock + progress ----------------------------------------------
    stamp = datetime.fromtimestamp(t_unix, tz=timezone.utc)
    centered(stamp.strftime("%Y-%m-%d  %H:%M UTC"), fonts["clock"], 1586, ACCENT, 1.0)

    bar_w, bar_h, by = 640, 5, 1662
    bx = (W - bar_w) / 2
    d.rounded_rectangle([bx, by, bx + bar_w, by + bar_h], radius=3,
                        fill=(255, 255, 255, a(0.16)))
    frac = playhead / max(scene.n_frames - 1, 1)
    d.rounded_rectangle([bx, by, bx + max(bar_h, bar_w * frac), by + bar_h], radius=3,
                        fill=ACCENT + (a(0.9),))
    d.text((bx, by + 16), "72 h ago", font=fonts["tiny"], fill=INK_QUIET + (a(0.9),))
    nw = d.textlength("now", font=fonts["tiny"])
    d.text((bx + bar_w - nw, by + 16), "now", font=fonts["tiny"], fill=INK_QUIET + (a(0.9),))

    # --- provenance -----------------------------------------------------
    centered("PFSS model from GONG / NSO magnetograms  ·  surface imagery NASA SDO",
             fonts["tiny"], 1746, INK_QUIET, 0.95)
    centered("astrodavid10.github.io/sol-solar-viewer", fonts["tiny"], 1780,
             INK_QUIET, 0.8)

    if fade < 1.0:
        d.rectangle([0, 0, W, H], fill=(0, 0, 0, int(round((1.0 - fade) * 255))))


# =====================================================================
# Render
# =====================================================================

def render_one(scene: Scene, fonts, t: float, width: int, height: int) -> Image.Image:
    playhead = playhead_at(t, scene.n_frames)
    progress = min(1.0, t / max(PLAYHEAD_SECONDS, 1e-6))
    weights = channel_weights(t)

    ia = min(int(math.floor(playhead)), scene.n_frames - 1)
    ib = min(ia + 1, scene.n_frames - 1)
    f = playhead - ia
    t_unix = float(scene.frame_unix[ia] * (1 - f) + scene.frame_unix[ib] * f)
    rot = quat_to_matrix(slerp(scene.quats[ia], scene.quats[ib], f))

    cam = build_camera(scene, playhead, progress, width, height)

    img = glow_layer(cam, width, height)
    surf, cover, depth = surface_layer(scene, cam, rot, t_unix, weights, width, height)

    # The sphere is OPAQUE (MeshBasicMaterial, renderOrder 0) and the glow is
    # drawn under it (renderOrder -1, depthTest false), so inside the disk the
    # surface replaces the halo rather than adding to it.
    m = cover[:, :, None]
    img = img * (1.0 - m) + surf * m

    img += field_line_layer(scene, cam, playhead, depth, width, height, opacity=1.0)

    np.clip(img, 0.0, 1.0, out=img)
    out = (linear_to_srgb(img) * 255.0 + 0.5).astype(np.uint8)

    if width != OUT_W:
        s = width // OUT_W
        out = out.reshape(OUT_H, s, OUT_W, s, 3).mean(axis=(1, 3))
        out = (out + 0.5).astype(np.uint8)

    pil = Image.fromarray(out, "RGB")
    draw_overlay(pil, fonts, scene, t, weights, t_unix, playhead)
    return pil


def check_conventions(scene: Scene) -> None:
    """Re-derive the quaternion against the manifest's own matrix.

    Footgun 47 cost four sessions because every internal cross-check agreed
    with every other internal cross-check. This one is against the PIPELINE's
    independently written mat3, so a sign flip on either side fails here.
    """
    worst = 0.0
    for i, meta in enumerate(scene.meta):
        m_json = np.array(meta["mat3_carr_to_ecliptic_j2000"], dtype=np.float64).reshape(3, 3)
        m_quat = quat_to_matrix(meta["quat_carr_to_ecl"])
        worst = max(worst, float(np.abs(m_json - m_quat).max()))
        det = float(np.linalg.det(m_quat))
        if abs(det - 1.0) > 1e-6:
            raise SystemExit(f"frame {i}: quat matrix det {det:+.9f}, expected +1")
    print(f"  quat_carr_to_ecl vs mat3_carr_to_ecliptic_j2000: max |delta| {worst:.3e}")
    if worst > 1e-9:
        raise SystemExit("quaternion and matrix disagree — refusing to render")

    # Every valid line must have ONE end on the photosphere: a closed line has
    # two footpoints, an open one has a footpoint and a source-surface end.
    # This is the check that catches a dequantization slip, whose symptom is
    # footgun 9's — lines drawn as rays toward the Sun's centre.
    # Note the raw order is NOT footpoint-first: `openLinePaths` in
    # src/three/fieldLines.ts flips any line whose first vertex is the outer
    # one, so the invariant is on min(r_first, r_last), not on r_first.
    fr = scene.frames[-1]
    p = fr.xyz_u16.astype(np.float64) / 65535.0 * scene.q_scale + scene.q_offset
    r = np.linalg.norm(p, axis=1)
    live = fr.valid != 0
    r_first = r[scene.topology.line_offset[:-1][live]]
    r_last = r[scene.topology.line_offset[1:][live] - 1]
    foot = np.minimum(r_first, r_last)
    outer = np.maximum(r_first, r_last)
    print(f"  valid footpoint radius: min {foot.min():.5f}  max {foot.max():.5f} R_sun")
    print(f"  far end radius:         min {outer.min():.5f}  max {outer.max():.5f} R_sun")
    print(f"  vertex radius range:    min {r.min():.5f}  max {r.max():.5f} R_sun")
    # The bound is 1.03, not 1.001: the exporter decimates vertices, so the
    # retained near-end vertex is the closest one KEPT, not the traced
    # footpoint itself (measured 2026-08-26: median 1.005, worst 1.020).
    # Tight enough that a dequantization slip — which would scatter the ends
    # anywhere in +/-2.6 R_sun — still fails here.
    if not (0.99 < foot.min() and foot.max() < 1.03):
        raise SystemExit("no line end sits on the photosphere")
    if r.max() > scene.rss + 0.01:
        raise SystemExit(f"a vertex is outside the source surface ({r.max():.4f} R_sun)")
    print("  conventions OK")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(REPO / "public" / "data"),
                    help="published data tree (default: public/data)")
    ap.add_argument("--out", default=str(REPO / "media" / "sol-reel.mp4"))
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--seconds", type=float, default=TOTAL_SECONDS)
    ap.add_argument("--supersample", type=int, default=SUPERSAMPLE)
    ap.add_argument("--still", help="render ONE frame to this PNG and stop")
    ap.add_argument("--at", type=float, default=13.0,
                    help="reel time in seconds for --still")
    ap.add_argument("--check-conventions", action="store_true",
                    help="run the geometry tripwires and exit")
    args = ap.parse_args()

    root = Path(args.root)
    print(f"sol reel - data {root}")
    scene = Scene(root)
    man = scene.manifest
    print(f"  pfss   {scene.n_frames} frames "
          f"{scene.meta[0]['target_iso']} -> {scene.meta[-1]['target_iso']}"
          f"  ({man['window_hours']} h, newest mag {man['newest_mag_age_hours']:.1f} h old)")
    print(f"  lines  {scene.topology.n_lines}  verts {scene.topology.n_verts}"
          f"  segments {scene.topology.seg_a.size}")
    for ch in CHANNEL_ORDER:
        L = scene.layers[ch]
        print(f"  tex    {ch:6s} {L['label']:16s} {len(L['frames'])} frames  far_side={L['far_side']}")

    check_conventions(scene)
    if args.check_conventions:
        return 0

    width = OUT_W * args.supersample
    height = OUT_H * args.supersample
    fonts = load_fonts()

    if args.still:
        t0 = time.time()
        img = render_one(scene, fonts, args.at, width, height)
        Path(args.still).parent.mkdir(parents=True, exist_ok=True)
        img.save(args.still)
        print(f"  still t={args.at:.2f}s -> {args.still} ({time.time() - t0:.1f}s)")
        return 0

    n = int(round(args.seconds * args.fps))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{OUT_W}x{OUT_H}", "-r", str(args.fps), "-i", "-",
        "-an",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
        "-movflags", "+faststart",
        str(out_path),
    ]
    print(f"  render {n} frames at {width}x{height} -> {OUT_W}x{OUT_H} -> {out_path}")
    started = time.time()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(n):
            t = i / args.fps
            img = render_one(scene, fonts, t, width, height)
            proc.stdin.write(img.tobytes())
            if i % 30 == 0 or i == n - 1:
                el = time.time() - started
                rate = (i + 1) / max(el, 1e-6)
                eta = (n - i - 1) / max(rate, 1e-6)
                print(f"    {i + 1:4d}/{n}  t={t:5.2f}s  {rate:4.2f} fps  eta {eta / 60:4.1f} min",
                      flush=True)
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        return proc.returncode
    size = out_path.stat().st_size / 1e6
    print(f"  done in {(time.time() - started) / 60:.1f} min — {out_path} ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
