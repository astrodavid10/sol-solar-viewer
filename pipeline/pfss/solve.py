"""PFSS solve + ordered field-line tracing (pass A of the two-pass export).

Pass A traces every magnetogram at FULL tracer resolution and caches the
result as a ragged polyline set.  Pass B (``export.py``) then picks each line's
vertex count from its LONGEST arc length across the window and resamples every
frame to those counts.  Doing it in that order is what buys adaptive detail
*and* a constant per-line vertex count -- the two things a morphing renderer
needs simultaneously.

Critical detail ported from the dome pipeline: use the ORDERED trace.  The
convenience wrapper there filters out short lines, which silently destroys the
seed-index <-> row correspondence; for an animation that is fatal, because row
*i* would be a different field line in every frame.  Here every seed is walked
in order and degenerate traces become dummies.
"""

from __future__ import annotations

import os
import time
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from ..config import MAX_TRACE_STEPS, NRHO, RSS
from .seeds import SeedSet, seed_xyz_solrad

# Heavy imports are deferred: `pipeline plan` / `probe-sources` should not pay
# the ~5 s cost of importing sunpy + the solver.
_np = None
_u = None
_SkyCoord = None
_sunpy_map = None
_HGC = None
_pfsspy = None
_tracing = None


def ensure_heavy_imports() -> None:
    """Import the scientific stack into module globals (idempotent)."""
    global _np, _u, _SkyCoord, _sunpy_map, _HGC, _pfsspy, _tracing
    if _np is not None:
        return
    import numpy as np_
    import astropy.units as u_
    from astropy.coordinates import SkyCoord as SkyCoord_
    import sunpy.map as sunpy_map_          # noqa: F401
    import sunpy.coordinates                # noqa: F401  (registers frames)
    from sunpy.coordinates import HeliographicCarrington as HGC_
    from sunkit_magex import pfss as pfsspy_
    from sunkit_magex.pfss import tracing as tracing_
    _np, _u, _SkyCoord = np_, u_, SkyCoord_
    _sunpy_map, _HGC = sunpy_map_, HGC_
    _pfsspy, _tracing = pfsspy_, tracing_


def tracer_name() -> str:
    ensure_heavy_imports()
    cls = getattr(_tracing, "PerformanceTracer", None) or _tracing.FortranTracer
    return cls.__name__


def pfss_compute(fits_path: Path, nrho: int = NRHO, rss: float = RSS):
    """Solve the potential field for one GONG synoptic map (or None on error)."""
    ensure_heavy_imports()
    try:
        gong_map = _sunpy_map.Map(str(fits_path))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return _pfsspy.pfss(_pfsspy.Input(gong_map, nrho, rss))
    except Exception as exc:
        print("  WARN PFSS {0}: {1}".format(Path(fits_path).name, exc))
        return None


def resample_to_n_verts(xyz: np.ndarray, n_target: int) -> np.ndarray:
    """Resample a (3, n) polyline to exactly ``n_target`` vertices by arc length.

    Ported from the dome pipeline (L1407).  Endpoints are preserved exactly,
    which keeps footpoints on the photosphere after resampling.
    """
    n = xyz.shape[1]
    n_target = max(2, int(n_target))
    if n == n_target:
        return xyz
    if n < 2:
        return np.tile(xyz[:, :1], (1, n_target))
    segs = np.linalg.norm(np.diff(xyz, axis=1), axis=0)
    cumlen = np.concatenate([[0.0], np.cumsum(segs)])
    total = float(cumlen[-1])
    if total <= 0.0:
        return np.tile(xyz[:, :1], (1, n_target))
    sample_s = np.linspace(0.0, total, n_target)
    idx = np.clip(np.searchsorted(cumlen, sample_s, side="right") - 1,
                  0, n - 2)
    seg_len = segs[idx].copy()
    seg_len[seg_len == 0.0] = 1.0
    t = (sample_s - cumlen[idx]) / seg_len
    return xyz[:, idx] + (xyz[:, idx + 1] - xyz[:, idx]) * t[None, :]


def intensity_from_r(r_arr: np.ndarray, polarity: int) -> np.ndarray:
    """Reference implementation of the shipped opacity model (NOT exported).

    The app computes this in the vertex shader from the dequantized radius --
    shipping a per-vertex float would nearly double the frame size for
    something a shader derives in two instructions.  Kept here so
    ``validate`` can prove the manifest formula matches the dome pipeline.
    """
    from ..config import CLOSED_FLOOR
    t = (r_arr - 1.0) / (RSS - 1.0)
    if polarity == 0:
        return np.maximum(CLOSED_FLOOR, 1.0 - (1.0 - CLOSED_FLOOR) * t)
    return np.clip(1.0 - t, 0.0, 1.0)


@dataclass
class TracedFrame:
    """One magnetogram traced at full resolution, in ragged form.

    ``xyz_flat`` is (V_total, 3) float32 in R_sun, HeliographicCarrington at
    ``mag_iso``; ``counts`` says how many rows belong to each line, in seed
    order.  Ragged rather than padded because full-resolution lines differ in
    length by 100x and a padded array would be mostly zeros.
    """

    xyz_flat: np.ndarray        # (V_total, 3) float32
    counts: np.ndarray          # (n_lines,) int32
    pol: np.ndarray             # (n_lines,) int8   0 closed, +-1 open
    valid: np.ndarray           # (n_lines,) uint8
    arclen: np.ndarray          # (n_lines,) float32, R_sun
    mag_iso: str
    seed_set_id: str

    @property
    def n_lines(self) -> int:
        return int(self.counts.size)

    def offsets(self) -> np.ndarray:
        return np.concatenate([[0], np.cumsum(self.counts)]).astype(np.int64)

    def line(self, i: int) -> np.ndarray:
        """Line ``i`` as (3, n) -- the orientation resample_to_n_verts wants."""
        off = self.offsets()
        return self.xyz_flat[off[i]:off[i + 1]].T.astype(float)


def frame_cache_dir(cache_root: Path, seed_set_id: str) -> Path:
    return Path(cache_root) / "frames" / seed_set_id


def frame_cache_path(cache_root: Path, seed_set_id: str, gong_key: str) -> Path:
    return frame_cache_dir(cache_root, seed_set_id) / "{0}.npz".format(gong_key)


def save_traced(path: Path, tf: TracedFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".partial.npz")
    np.savez_compressed(
        str(tmp), xyz_flat=tf.xyz_flat, counts=tf.counts, pol=tf.pol,
        valid=tf.valid, arclen=tf.arclen,
        mag_iso=np.array(tf.mag_iso), seed_set_id=np.array(tf.seed_set_id))
    os.replace(str(tmp), str(path))
    return path


def load_traced(path: Path) -> Optional[TracedFrame]:
    try:
        with np.load(str(path), allow_pickle=False) as z:
            return TracedFrame(
                xyz_flat=z["xyz_flat"], counts=z["counts"].astype(np.int32),
                pol=z["pol"].astype(np.int8), valid=z["valid"].astype(np.uint8),
                arclen=z["arclen"].astype(np.float32),
                mag_iso=str(z["mag_iso"]), seed_set_id=str(z["seed_set_id"]))
    except Exception as exc:
        print("  WARN frame cache {0}: {1}".format(Path(path).name, exc))
        return None


def trace_frame(fits_path: Path, ss: SeedSet, verbose: bool = False
                ) -> Optional[Tuple[TracedFrame, dict]]:
    """Solve + trace one magnetogram against the frozen seed set.

    Returns (TracedFrame, timings) or None if the solve failed.  Modelled on
    ``_anim_field_worker_parametric`` (dome L2633) but keeping full-resolution
    geometry, because the vertex budget is decided later.
    """
    ensure_heavy_imports()
    t0 = time.perf_counter()
    pfss_out = pfss_compute(fits_path)
    if pfss_out is None:
        return None
    t_solve = time.perf_counter() - t0

    obstime = pfss_out.input_map.date
    observer = pfss_out.input_map.observer_coordinate
    carr_frame = _HGC(obstime=obstime, observer=observer)
    seeds = _SkyCoord(ss.lons * _u.deg, ss.lats * _u.deg, ss.rs * _u.R_sun,
                      frame=carr_frame)

    t1 = time.perf_counter()
    tracer_cls = (getattr(_tracing, "PerformanceTracer", None)
                  or _tracing.FortranTracer)
    tracer = tracer_cls(max_steps=MAX_TRACE_STEPS)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        flines = tracer.trace(seeds, pfss_out)
    t_trace = time.perf_counter() - t1

    n_seeds = ss.n_lines
    seed_xyz = seed_xyz_solrad(ss.lats, ss.lons, ss.rs)      # (3, N)
    chunks = []
    counts = np.zeros(n_seeds, dtype=np.int32)
    pol = np.zeros(n_seeds, dtype=np.int8)
    valid = np.zeros(n_seeds, dtype=np.uint8)
    arclen = np.zeros(n_seeds, dtype=np.float32)

    n_trace = min(len(flines), n_seeds)
    need_xform = not (n_trace > 0
                      and isinstance(flines[0].coords.frame, type(carr_frame)))
    for i in range(n_seeds):
        # A dummy is TWO copies of the seed point: the minimum a polyline
        # resampler accepts, and it dequantizes to a zero-length segment the
        # shader kills via valid=0.
        if i >= n_trace:
            chunks.append(np.repeat(seed_xyz[:, i][None, :], 2, axis=0))
            counts[i] = 2
            continue
        fl = flines[i]
        if len(fl.coords) < 3:
            chunks.append(np.repeat(seed_xyz[:, i][None, :], 2, axis=0))
            counts[i] = 2
            continue
        coords_c = fl.coords.transform_to(carr_frame) if need_xform else fl.coords
        xyz = coords_c.cartesian.xyz.to_value("solRad")      # (3, n)
        arclen[i] = float(np.linalg.norm(np.diff(xyz, axis=1), axis=0).sum())
        chunks.append(xyz.T.astype(np.float32))
        counts[i] = xyz.shape[1]
        pol[i] = int(fl.polarity)
        valid[i] = 1

    xyz_flat = np.concatenate(chunks, axis=0).astype(np.float32)
    mag_dt = obstime.to_datetime().replace(tzinfo=timezone.utc)
    tf = TracedFrame(xyz_flat=xyz_flat, counts=counts, pol=pol, valid=valid,
                     arclen=arclen,
                     mag_iso=mag_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     seed_set_id=ss.seed_set_id)
    timings = {"solve_s": t_solve, "trace_s": t_trace,
               "n_valid": int(valid.sum()), "n_lines": n_seeds,
               "n_closed": int(((pol == 0) & (valid == 1)).sum()),
               "n_open_pos": int(((pol > 0) & (valid == 1)).sum()),
               "n_open_neg": int(((pol < 0) & (valid == 1)).sum()),
               "verts_full": int(xyz_flat.shape[0])}
    if verbose:
        print("    pfss {0:.2f}s trace {1:.2f}s valid {2}/{3} "
              "closed {4} open+ {5} open- {6} full-verts {7}".format(
                  t_solve, t_trace, timings["n_valid"], n_seeds,
                  timings["n_closed"], timings["n_open_pos"],
                  timings["n_open_neg"], timings["verts_full"]))
    return tf, timings


def mag_datetime(tf: TracedFrame) -> datetime:
    return datetime.strptime(tf.mag_iso, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)
