"""Pass B: adaptive vertex budget, quantization, binary writers, manifest.

Formats (all little-endian).  Both files are read with a couple of typed-array
views and uploaded straight to the GPU, which is why the layouts are flat and
interleaved rather than convenient.

``topology.bin`` -- written once, shared by all frames::

    char[8]            "SOLTOPO1"
    uint32             n_lines
    uint32             n_verts_total
    uint32             n_bg_lines        # first n_bg_lines rows are the grid
    uint32             reserved (0)
    char[8]            seed_set_id (ascii hex)
    uint32[n_lines+1]  line_offset       # cumulative; [n_lines]==n_verts_total
    int16[n_lines]     seed_lat_cdeg     # seed latitude * 100, degrees
    uint16[n_lines]    seed_lon_u16      # seed Carrington lon * 65536/360
    int16[n_lines]     ar_index          # index into manifest.seed_regions,
                                         # -1 = background grid

``fNN.bin`` -- one per frame, NN = 00..12 with the highest index newest::

    char[8]                 "SOLPFRM1"
    uint32                  frame_index
    uint32                  n_lines           # == topology
    uint32                  n_verts_total     # == topology
    uint32                  mag_unix
    uint32                  reserved (0)
    uint32                  reserved (0)
    uint16[n_verts_total*3] xyz, INTERLEAVED x,y,z
    int8[n_lines]           polarity   # 0 closed, +1 open out, -1 open in
    uint8[n_lines]          valid      # 1 real line, 0 dummy

Polarity is per FRAME, not per line: a loop that opens up between two
magnetograms genuinely changes class, and the app recolors accordingly.

``ar_index`` USED to be documented as an index into ``ar/regions.json``, and
that was the bug: it is a POSITION into a table CI regenerates every four
hours, while the seed set that produced it is frozen for the day it was
traced.  NOAA's region list went 6 -> 5 -> 4 over three days, so any published
product older than the next contraction had an ar_index running off the end of
the current list -- a ~2-day fuse that took down the WHOLE publish (footgun
50), because validation was all-or-nothing and ran after the promote.
Schema ``sol.pfss/2`` therefore ships ``seed_regions``: the NOAA region numbers
the seed set was frozen against, aligned with the ar_index positions, so
``ar_index i`` means ``seed_regions[i]``.  The binary format is UNCHANGED --
this is a manifest field, not a format change -- and the bound the validator
enforces becomes self-consistent (``max(ar_index) < len(seed_regions)``) with
the comparison against today's ``regions.json`` demoted to advice, since a
region leaving the SRS is normal (footgun 23).
"""

from __future__ import annotations

import struct
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np

from ..config import (CLOSED_FLOOR, COLORS, LIM_RSUN, MAX_FRAME_BYTES,
                      MAX_TRACE_STEPS, NRHO, PIPELINE_VERSION, RSS,
                      SCHEMA_PFSS, SOLVER_NAME, VERT_BUCKETS)
from ..io_utils import PipelineError
from .seeds import SeedSet
from .solve import TracedFrame, resample_to_n_verts

TOPO_MAGIC = b"SOLTOPO1"
FRAME_MAGIC = b"SOLPFRM1"
Q_SCALE = 2.0 * LIM_RSUN            # 5.2 R_sun full range
Q_MAX = 65535
R_SUN_KM = 695700.0
MAX_DEQUANT_ERR = 1e-4              # R_sun; assert before every write


# ─────────────────────────────────────────────────────────────────────────────
# Adaptive vertex budget
# ─────────────────────────────────────────────────────────────────────────────

def bucket_for(arclen: float) -> int:
    """Vertices for a line of this arc length (R_sun), per VERT_BUCKETS."""
    for limit, nv in VERT_BUCKETS:
        if arclen <= limit:
            return nv
    return VERT_BUCKETS[-1][1]


def plan_verts(arclen_max: np.ndarray) -> np.ndarray:
    """Per-line vertex counts from each line's LONGEST frame.

    Using the max over the window (not the per-frame length) is the morph
    guarantee: the count is identical in every frame, so frame *n* and frame
    *n+1* can be paired vertex-for-vertex.
    """
    return np.array([bucket_for(float(a)) for a in arclen_max], dtype=np.int32)


def bucket_histogram(nv: np.ndarray) -> Dict[str, int]:
    return {str(int(v)): int((nv == v).sum())
            for _, v in VERT_BUCKETS if int((nv == v).sum()) > 0}


# ─────────────────────────────────────────────────────────────────────────────
# Quantization
# ─────────────────────────────────────────────────────────────────────────────

def quantize_xyz(xyz: np.ndarray) -> Tuple[np.ndarray, float]:
    """(V, 3) float R_sun -> (V*3,) uint16 interleaved, plus max round-trip error.

    q = round((v + LIM_RSUN) / (2*LIM_RSUN) * 65535).  One step is
    5.2/65535 = 7.94e-5 R_sun (55 km), so the worst-case error is 28 km -- well
    under a magnetogram pixel and invisible at any zoom the app allows.
    """
    v = np.asarray(xyz, dtype=np.float64)
    q = np.rint((v + LIM_RSUN) / Q_SCALE * Q_MAX)
    if not np.isfinite(q).all():
        raise PipelineError("non-finite vertex in quantization input")
    q = np.clip(q, 0, Q_MAX).astype(np.uint16)
    back = q.astype(np.float64) / Q_MAX * Q_SCALE - LIM_RSUN
    err = float(np.abs(back - v).max()) if v.size else 0.0
    return q.reshape(-1), err


def dequantize(q: np.ndarray) -> np.ndarray:
    return q.astype(np.float64) / Q_MAX * Q_SCALE - LIM_RSUN


# ─────────────────────────────────────────────────────────────────────────────
# Binary writers
# ─────────────────────────────────────────────────────────────────────────────

def pack_topology(ss: SeedSet, nv: np.ndarray) -> bytes:
    """Serialize topology.bin for a seed set + vertex plan."""
    n_lines = int(nv.size)
    line_offset = np.zeros(n_lines + 1, dtype=np.uint32)
    line_offset[1:] = np.cumsum(nv, dtype=np.uint64).astype(np.uint32)
    n_verts_total = int(line_offset[-1])

    lat_cdeg = np.rint(np.asarray(ss.lats) * 100.0).astype(np.int16)
    lon_u16 = np.rint((np.asarray(ss.lons) % 360.0) * 65536.0 / 360.0)
    lon_u16 = np.mod(lon_u16, 65536.0).astype(np.uint16)
    ar_index = np.asarray(ss.ar_index, dtype=np.int16)

    head = TOPO_MAGIC + struct.pack("<IIII", n_lines, n_verts_total,
                                    int(ss.n_bg), 0)
    sid = ss.seed_set_id.encode("ascii")
    if len(sid) != 8:
        raise PipelineError("seed_set_id must be 8 ascii chars, got "
                            "{0!r}".format(ss.seed_set_id))
    return (head + sid + line_offset.astype("<u4").tobytes()
            + lat_cdeg.astype("<i2").tobytes()
            + lon_u16.astype("<u2").tobytes()
            + ar_index.astype("<i2").tobytes())


def pack_frame(frame_index: int, xyz_q: np.ndarray, n_lines: int,
               n_verts_total: int, mag_unix: int, pol: np.ndarray,
               valid: np.ndarray) -> bytes:
    if xyz_q.size != n_verts_total * 3:
        raise PipelineError("frame {0}: {1} quantized components, expected "
                            "{2}".format(frame_index, xyz_q.size,
                                         n_verts_total * 3))
    head = FRAME_MAGIC + struct.pack("<IIIIII", int(frame_index), int(n_lines),
                                     int(n_verts_total), int(mag_unix), 0, 0)
    return (head + xyz_q.astype("<u2").tobytes()
            + np.asarray(pol, dtype=np.int8).tobytes()
            + np.asarray(valid, dtype=np.uint8).tobytes())


def frame_bytes_expected(n_lines: int, n_verts_total: int) -> int:
    return 32 + 6 * n_verts_total + 2 * n_lines


# ─────────────────────────────────────────────────────────────────────────────
# Pass B driver
# ─────────────────────────────────────────────────────────────────────────────

def resample_frame(tf: TracedFrame, nv: np.ndarray) -> np.ndarray:
    """Resample every line of a traced frame to its planned vertex count.

    Returns (n_verts_total, 3) float64 in R_sun, lines laid out consecutively
    in seed order so the topology's ``line_offset`` addresses it directly.
    """
    offs = tf.offsets()
    out = np.empty((int(nv.sum()), 3), dtype=np.float64)
    w = 0
    for i in range(tf.n_lines):
        line = tf.xyz_flat[offs[i]:offs[i + 1]].T.astype(np.float64)  # (3, n)
        k = int(nv[i])
        res = line if line.shape[1] == k else resample_to_n_verts(line, k)
        out[w:w + k] = res.T
        w += k
    if w != out.shape[0]:
        raise PipelineError("resample wrote {0} of {1} vertices".format(
            w, out.shape[0]))
    return out


def build_frame_payload(frame_index: int, tf: TracedFrame, nv: np.ndarray,
                        mag_unix: int) -> Tuple[bytes, dict]:
    """Quantize + pack one frame; asserts the round-trip error before writing."""
    xyz = resample_frame(tf, nv)
    q, err = quantize_xyz(xyz)
    if err >= MAX_DEQUANT_ERR:
        raise PipelineError(
            "frame {0}: dequant round-trip error {1:.3e} R_sun >= {2:.0e}"
            .format(frame_index, err, MAX_DEQUANT_ERR))
    n_lines = tf.n_lines
    n_verts_total = int(nv.sum())
    blob = pack_frame(frame_index, q, n_lines, n_verts_total, mag_unix,
                      tf.pol, tf.valid)
    exp = frame_bytes_expected(n_lines, n_verts_total)
    if len(blob) != exp:
        raise PipelineError("frame {0}: packed {1} bytes, expected {2}".format(
            frame_index, len(blob), exp))
    if len(blob) > MAX_FRAME_BYTES:
        raise PipelineError(
            "frame {0} is {1} bytes, over the {2}-byte budget; reduce "
            "VERT_BUCKETS or the seed count".format(frame_index, len(blob),
                                                    MAX_FRAME_BYTES))
    stats = {
        "bytes": len(blob),
        "max_error_rsun": err,
        "n_valid": int(tf.valid.sum()),
        "n_closed": int(((tf.pol == 0) & (tf.valid == 1)).sum()),
        "n_open_pos": int(((tf.pol > 0) & (tf.valid == 1)).sum()),
        "n_open_neg": int(((tf.pol < 0) & (tf.valid == 1)).sum()),
    }
    return blob, stats


# ─────────────────────────────────────────────────────────────────────────────
# Manifest
# ─────────────────────────────────────────────────────────────────────────────

def render_hints() -> dict:
    """Dome palette + the opacity model the app implements in-shader."""
    return {
        "colors": {k: list(v) for k, v in COLORS.items()},
        "opacity_model": {
            "formula": ("t=(r-1)/(rss-1); closed: max(closed_floor, "
                        "1-(1-closed_floor)*t); open: clamp(1-t,0,1); "
                        "invalid: 0"),
            "rss": RSS,
            "closed_floor": CLOSED_FLOOR,
            "note": ("Per-vertex opacity is NOT shipped: it is a two-"
                     "instruction function of the dequantized radius, and "
                     "shipping it would add 2 bytes per vertex."),
        },
        "load_order": "newest_first",
    }


def quantization_block(max_error_rsun: float) -> dict:
    return {
        "xyz": {
            "dtype": "uint16",
            "layout": "interleaved_xyz",
            "normalized": True,
            "limit_rsun": LIM_RSUN,
            "scale": Q_SCALE,
            "offset": -LIM_RSUN,
            "decode": "world_rsun = q / 65535 * 5.2 - 2.6",
            "max_error_rsun": max_error_rsun,
            "max_error_km": max_error_rsun * R_SUN_KM,
        }
    }


def build_manifest(*, generated: datetime, run_id: str, status: str,
                   ss: SeedSet, nv: np.ndarray, topology_bytes: int,
                   frames: List[dict], tracer: str,
                   newest_mag_iso: str, newest_mag_age_hours: float,
                   newest_mag_unix: int,
                   window_hours: int, frame_spacing_hours: int,
                   constants: dict, max_error_rsun: float) -> dict:
    """Assemble pfss/manifest.json."""
    from ..io_utils import iso_z, unix_s
    n_verts_total = int(nv.sum())
    return {
        "schema": SCHEMA_PFSS,
        "pipeline_version": PIPELINE_VERSION,
        "generated_iso": iso_z(generated),
        "generated_unix": unix_s(generated),
        "run_id": run_id,
        "status": status,
        "newest_mag_iso": newest_mag_iso,
        # The same instant as newest_mag_iso, as an integer.  Additive, and it
        # exists because the STALE path reads this manifest back to report how
        # old the field data it is still serving is: a reader that has to
        # re-parse an ISO string to answer that will eventually get it wrong,
        # and this pipeline has already paid for one timezone bug (footgun on
        # parse_iso_z).  Asserted == max(frames[*].mag_unix) by the validator.
        "newest_mag_unix": int(newest_mag_unix),
        "newest_mag_age_hours": newest_mag_age_hours,
        "window_hours": window_hours,
        "frame_spacing_hours": frame_spacing_hours,
        "model": {
            "source": "GONG mrzqs synoptic magnetogram (gong2.nso.edu)",
            "method": "PFSS",
            "solver": SOLVER_NAME,
            "nrho": NRHO,
            "rss": RSS,
            "tracer": tracer,
            "max_steps": MAX_TRACE_STEPS,
        },
        "quantization": quantization_block(max_error_rsun),
        "geometry": {
            "frame": "HeliographicCarrington",
            "units": "R_sun",
            "n_lines": int(nv.size),
            "n_verts_total": n_verts_total,
            "n_bg_lines": int(ss.n_bg),
            "seed_set_id": ss.seed_set_id,
            "topology_url": "topology.bin",
            "topology_bytes": int(topology_bytes),
            "verts_per_line": {
                "min": int(nv.min()),
                "max": int(nv.max()),
                "mean": float(nv.mean()),
                "buckets": bucket_histogram(nv),
            },
        },
        "constants": constants,
        "render_hints": dict(render_hints(),
                             recommended_first_frame=len(frames) - 1),
        "frames": frames,
        # What ar_index actually addresses: the NOAA region numbers this seed
        # set was FROZEN against, in ar_index order.  See the module docstring
        # for why a bare position into ar/regions.json was a ~2-day fuse.
        # Empty only when the seed set came from an npz predating the field and
        # its cached region list was gone too, in which case the validator
        # falls back to the old bound.
        "seed_regions": list(ss.region_numbers),
        "active_regions_url": "../ar/regions.json",
        "seed_regions_note": (
            "ar_index i in topology.bin refers to seed_regions[i], the NOAA "
            "AR number this seed set was frozen against; -1 is the background "
            "grid. A number missing from ar/regions.json means the region "
            "rotated off or was dropped since the trace, which is normal."),
    }


def frame_entry(*, index: int, target_iso: str, orient: dict, mag_file: str,
                mag_age_hours: float, stats: dict, reused: bool) -> dict:
    """One manifest ``frames[]`` record (oldest-first ordering)."""
    return {
        "index": index,
        "url": "f{0:02d}.bin".format(index),
        "bytes": int(stats["bytes"]),
        "target_iso": target_iso,
        "mag_iso": orient["iso"],
        "mag_unix": orient["unix"],
        "mag_file": mag_file,
        "mag_age_hours": mag_age_hours,
        "carrington_rotation": orient["carrington_rotation"],
        "l0_deg": orient["l0_deg"],
        "b0_deg": orient["b0_deg"],
        "p_deg": orient["p_deg"],
        "hci_rot_deg": orient["hci_rot_deg"],
        "quat_carr_to_ecl": orient["quat_carr_to_ecl"],
        "mat3_carr_to_ecliptic_j2000": orient["mat3_carr_to_ecliptic_j2000"],
        "mat3_heeq_to_ecliptic_j2000": orient["mat3_heeq_to_ecliptic_j2000"],
        "n_valid": int(stats["n_valid"]),
        "n_closed": int(stats["n_closed"]),
        "n_open_pos": int(stats["n_open_pos"]),
        "n_open_neg": int(stats["n_open_neg"]),
        "reused": bool(reused),
    }


def read_frame_header(blob: bytes) -> dict:
    """Parse an fNN.bin header (used by validate and by frame reuse)."""
    if len(blob) < 32 or blob[:8] != FRAME_MAGIC:
        raise PipelineError("not a SOLPFRM1 frame")
    (idx, n_lines, n_verts, mag_unix, r1, r2) = struct.unpack(
        "<IIIIII", blob[8:32])
    return {"frame_index": idx, "n_lines": n_lines, "n_verts_total": n_verts,
            "mag_unix": mag_unix, "reserved": (r1, r2)}


def read_topology_header(blob: bytes) -> dict:
    if len(blob) < 32 or blob[:8] != TOPO_MAGIC:
        raise PipelineError("not a SOLTOPO1 topology")
    n_lines, n_verts, n_bg, reserved = struct.unpack("<IIII", blob[8:24])
    seed_set_id = blob[24:32].decode("ascii", errors="replace")
    return {"n_lines": n_lines, "n_verts_total": n_verts, "n_bg_lines": n_bg,
            "reserved": reserved, "seed_set_id": seed_set_id}


def unpack_frame(blob: bytes) -> dict:
    """Full parse of a frame file: header + arrays (validate/debug use)."""
    h = read_frame_header(blob)
    n_lines, n_verts = h["n_lines"], h["n_verts_total"]
    exp = frame_bytes_expected(n_lines, n_verts)
    if len(blob) != exp:
        raise PipelineError("frame length {0}, expected {1}".format(
            len(blob), exp))
    o = 32
    xyz = np.frombuffer(blob, dtype="<u2", count=n_verts * 3, offset=o)
    o += 6 * n_verts
    pol = np.frombuffer(blob, dtype=np.int8, count=n_lines, offset=o)
    o += n_lines
    valid = np.frombuffer(blob, dtype=np.uint8, count=n_lines, offset=o)
    return dict(h, xyz=xyz, pol=pol, valid=valid)


def unpack_topology(blob: bytes) -> dict:
    h = read_topology_header(blob)
    n = h["n_lines"]
    exp = 36 + 10 * n
    if len(blob) != exp:
        raise PipelineError("topology length {0}, expected {1}".format(
            len(blob), exp))
    o = 32
    line_offset = np.frombuffer(blob, dtype="<u4", count=n + 1, offset=o)
    o += 4 * (n + 1)
    lat = np.frombuffer(blob, dtype="<i2", count=n, offset=o)
    o += 2 * n
    lon = np.frombuffer(blob, dtype="<u2", count=n, offset=o)
    o += 2 * n
    ar = np.frombuffer(blob, dtype="<i2", count=n, offset=o)
    return dict(h, line_offset=line_offset, seed_lat_cdeg=lat,
                seed_lon_u16=lon, ar_index=ar)


def topology_bytes_expected(n_lines: int) -> int:
    return 36 + 10 * n_lines


__all__ = [
    "TOPO_MAGIC", "FRAME_MAGIC", "bucket_for", "plan_verts",
    "bucket_histogram", "quantize_xyz", "dequantize", "pack_topology",
    "pack_frame", "resample_frame", "build_frame_payload", "build_manifest",
    "frame_entry", "render_hints", "quantization_block", "read_frame_header",
    "read_topology_header", "unpack_frame", "unpack_topology",
    "frame_bytes_expected", "topology_bytes_expected",
]
