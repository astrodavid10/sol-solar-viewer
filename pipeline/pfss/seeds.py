"""The frozen seed set: background grid + per-active-region clusters.

Ported from ``sunspots-Bfield-daily.py`` (L1014-1072) with the mobile-sized
constants from ``config``.

Two properties matter more than anything else here:

1. **Frozen for the whole window.**  Every one of the 19 frames is traced from
   the SAME seed positions, so row *i* of frame *n* and row *i* of frame *n+1*
   are the same field line at two times -- which is what makes a GPU lerp
   between them physically meaningful instead of a random cross-fade.

2. **Keyed on the SRS *date*, not on run time.**  All six daily runs share one
   ``seed_set_id``, which (a) makes 18 of 19 traced-frame caches hit on the
   second run of a day and (b) stops the line set from jumping mid-day, which
   would look like the corona teleporting.

The dome pipeline's hard cap used ``rng.choice`` without sorting, which
shuffles rows.  Here the kept indices are SORTED, because the binary topology
format promises "the first ``n_bg_lines`` rows are the background grid" and the
per-region ``ar_index`` mapping has to survive the cap.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..config import (BG_HEIGHT_RS, BG_LAT_LIMIT_DEG, BG_NLAT, BG_NLON,
                      PIPELINE_VERSION, REGION_HEIGHTS, REGION_MAX_SEEDS,
                      REGION_MIN_SEEDS, SEED_HARD_CAP, SEED_RNG_SEED)


def _region_seed_count(area: float, num_spots: int) -> int:
    n = int(area / 20.0 + 10 * max(1, num_spots))
    return max(REGION_MIN_SEEDS, min(REGION_MAX_SEEDS, n))


def _region_radius_deg(area: float, ext: float) -> float:
    geom_deg = math.sqrt(max(1, area)) / 4.0
    ext_deg = ext / 2.0
    return max(1.5, min(12.0, max(geom_deg, ext_deg)))


def _seeds_for_region(rng: np.random.Generator, region: Dict
                      ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Uniform-in-area disc of seeds around a region, at 3 discrete heights.

    ``dlon`` is divided by cos(lat) so the cluster stays circular on the sphere
    rather than being squeezed toward the poles.
    """
    n = _region_seed_count(region["area"], region["numSpots"])
    rad_deg = _region_radius_deg(region["area"], region["ext"])
    rho = rad_deg * np.sqrt(rng.random(n))
    phi = 2.0 * math.pi * rng.random(n)
    dlat = rho * np.cos(phi)
    dlon = rho * np.sin(phi) / max(1e-3, math.cos(math.radians(region["lat"])))
    lats = np.clip(region["lat"] + dlat, -85.0, 85.0)
    lons = (region["cLon"] + dlon) % 360.0
    heights = np.array(REGION_HEIGHTS)
    r = heights[rng.integers(0, len(heights), size=n)]
    return lats, lons, r


@dataclass
class SeedSet:
    """The frozen seed arrays plus everything needed to describe them."""

    lats: np.ndarray            # (n,) deg, heliographic latitude
    lons: np.ndarray            # (n,) deg, Carrington longitude
    rs: np.ndarray              # (n,) R_sun
    ar_index: np.ndarray        # (n,) int16; -1 == background grid
    n_bg: int                   # background rows, always the first n_bg
    region_seed_counts: List[int]
    regions: List[Dict]
    srs_epoch: Optional[date]
    seed_set_id: str
    source: str = "srs"

    @property
    def n_lines(self) -> int:
        return int(self.lats.size)


def compute_seed_set_id(srs_epoch: Optional[date],
                        regions: Sequence[Dict]) -> str:
    """Stable 8-hex-char id for a (SRS date, region list, grid config) triple.

    Includes PIPELINE_VERSION so a change to the grid or the bucket table
    invalidates old frame caches instead of silently mixing topologies.
    """
    tuples = sorted(
        (int(r["rnumber"]), int(r["lat"]), int(r["cLon"]), int(r["area"]),
         int(r["ext"]), int(r["numSpots"])) for r in regions)
    payload = "|".join([
        srs_epoch.isoformat() if srs_epoch else "no-srs",
        ";".join(",".join(str(v) for v in t) for t in tuples),
        "grid={0}x{1}@{2}/{3}".format(BG_NLAT, BG_NLON, BG_LAT_LIMIT_DEG,
                                      BG_HEIGHT_RS),
        "reg={0}-{1}:{2}".format(REGION_MIN_SEEDS, REGION_MAX_SEEDS,
                                 ",".join(str(h) for h in REGION_HEIGHTS)),
        "cap={0};rng={1}".format(SEED_HARD_CAP, SEED_RNG_SEED),
        "v={0}".format(PIPELINE_VERSION),
    ])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def build_seed_arrays(regions: Sequence[Dict], rng_seed: int = SEED_RNG_SEED
                      ) -> Tuple[np.ndarray, np.ndarray, np.ndarray,
                                 np.ndarray, int, List[int]]:
    """Build (lats, lons, rs, ar_index, n_bg, region_seed_counts).

    Deterministic given ``regions`` and ``rng_seed``; no SkyCoord wrapping (the
    caller adds each frame's obstime/observer).
    """
    rng = np.random.default_rng(seed=rng_seed)
    lat_bg = np.linspace(-BG_LAT_LIMIT_DEG, BG_LAT_LIMIT_DEG, BG_NLAT)
    lon_bg = np.linspace(0.0, 360.0, BG_NLON, endpoint=False)
    lon_grid, lat_grid = np.meshgrid(lon_bg, lat_bg)

    lats: List[np.ndarray] = [lat_grid.ravel()]
    lons: List[np.ndarray] = [lon_grid.ravel()]
    rs: List[np.ndarray] = [np.full(lat_grid.size, BG_HEIGHT_RS)]
    ars: List[np.ndarray] = [np.full(lat_grid.size, -1, dtype=np.int32)]
    n_bg = int(lat_grid.size)

    # Region order is the caller's order; export.py writes regions.json in the
    # same order so ar_index lines up with regions[].
    for ri, reg in enumerate(regions):
        rl, rlon, rr = _seeds_for_region(rng, reg)
        lats.append(rl)
        lons.append(rlon)
        rs.append(rr)
        ars.append(np.full(rl.size, ri, dtype=np.int32))

    lats_all = np.concatenate(lats)
    lons_all = np.concatenate(lons)
    rs_all = np.concatenate(rs)
    ar_all = np.concatenate(ars)

    if lats_all.size > SEED_HARD_CAP:
        keep = np.sort(rng.choice(lats_all.size, SEED_HARD_CAP, replace=False))
        lats_all, lons_all = lats_all[keep], lons_all[keep]
        rs_all, ar_all = rs_all[keep], ar_all[keep]
        n_bg = int((ar_all < 0).sum())

    counts = [int((ar_all == ri).sum()) for ri in range(len(regions))]
    return (lats_all, lons_all, rs_all, ar_all.astype(np.int16), n_bg, counts)


def _seed_cache_path(cache_root: Path, seed_set_id: str) -> Path:
    return Path(cache_root) / "seeds" / "{0}.npz".format(seed_set_id)


def save_seed_set(cache_root: Path, ss: SeedSet) -> Path:
    """Persist the frozen arrays so an SRS outage can reuse them verbatim."""
    import json
    path = _seed_cache_path(cache_root, ss.seed_set_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".partial.npz")
    np.savez_compressed(
        str(tmp), lats=ss.lats, lons=ss.lons, rs=ss.rs,
        ar_index=ss.ar_index, n_bg=np.int32(ss.n_bg),
        region_seed_counts=np.asarray(ss.region_seed_counts, dtype=np.int32),
        regions_json=np.array(json.dumps(ss.regions)),
        srs_epoch=np.array(ss.srs_epoch.isoformat() if ss.srs_epoch else ""),
        seed_set_id=np.array(ss.seed_set_id),
    )
    import os
    os.replace(str(tmp), str(path))
    return path


def load_newest_seed_set(cache_root: Path) -> Optional[SeedSet]:
    """Most recently written cached seed set, or None."""
    import json
    from datetime import date as _date
    seeds_dir = Path(cache_root) / "seeds"
    if not seeds_dir.is_dir():
        return None
    files = sorted(seeds_dir.glob("*.npz"), key=lambda p: p.stat().st_mtime,
                   reverse=True)
    for path in files:
        try:
            with np.load(str(path), allow_pickle=False) as z:
                epoch_s = str(z["srs_epoch"])
                return SeedSet(
                    lats=z["lats"], lons=z["lons"], rs=z["rs"],
                    ar_index=z["ar_index"].astype(np.int16),
                    n_bg=int(z["n_bg"]),
                    region_seed_counts=[int(v) for v in
                                        z["region_seed_counts"]],
                    regions=json.loads(str(z["regions_json"])),
                    srs_epoch=(_date.fromisoformat(epoch_s) if epoch_s
                               else None),
                    seed_set_id=str(z["seed_set_id"]),
                    source="cached seeds {0}".format(path.name),
                )
        except Exception as exc:
            print("  WARN seed cache {0}: {1}".format(path.name, exc))
    return None


def freeze_seed_set(regions: Sequence[Dict], srs_epoch: Optional[date],
                    cache_root: Path, source: str = "srs") -> SeedSet:
    """Build + persist the seed set for a region list."""
    lats, lons, rs, ar_index, n_bg, counts = build_seed_arrays(regions)
    ss = SeedSet(lats=lats, lons=lons, rs=rs, ar_index=ar_index, n_bg=n_bg,
                 region_seed_counts=counts, regions=list(regions),
                 srs_epoch=srs_epoch,
                 seed_set_id=compute_seed_set_id(srs_epoch, regions),
                 source=source)
    save_seed_set(cache_root, ss)
    return ss


def seed_xyz_solrad(lats_deg: np.ndarray, lons_deg: np.ndarray,
                    rs: np.ndarray) -> np.ndarray:
    """Cartesian (3, N) of heliographic (lat, lon, r) seeds in R_sun.

    Used for DUMMY lines: a seed that traced nothing in some frame is stored as
    N copies of its own seed point (never zeros -- zeros would draw rays into
    the Sun's center the moment a shader bug let them through) with valid=0.
    """
    lat = np.radians(np.asarray(lats_deg, dtype=float))
    lon = np.radians(np.asarray(lons_deg, dtype=float))
    r = np.asarray(rs, dtype=float)
    cl = np.cos(lat)
    return np.stack([r * cl * np.cos(lon), r * cl * np.sin(lon),
                     r * np.sin(lat)], axis=0)
