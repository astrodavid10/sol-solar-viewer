"""Active-region table (``ar/regions.json``).

The array order IS the ``ar_index`` space of ``pfss/topology.bin``: entry *k*
here is what ``ar_index == k`` refers to.  ``seed_count`` comes from the frozen
seed set (post-cap), not from a fresh computation, so the two files can never
disagree about how many field lines a region got.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Sequence

from ..config import PIPELINE_VERSION, SCHEMA_AR
from ..io_utils import iso_z, unix_s


def _location_string(lat: int, lon: int) -> str:
    """Rebuild the SRS Stonyhurst location string (e.g. ``N14W37``).

    ``lon`` is W-positive here (the dome pipeline's convention), so W/E is the
    sign and the printed number is the magnitude.
    """
    return "{0}{1:02d}{2}{3:02d}".format(
        "N" if lat >= 0 else "S", abs(int(lat)),
        "W" if lon >= 0 else "E", abs(int(lon)))


def build_regions(regions: Sequence[Dict], seed_counts: Sequence[int],
                  srs_epoch, source: str, now: datetime,
                  status: str = "ok") -> Dict:
    out: List[Dict] = []
    for i, r in enumerate(regions):
        magtype = str(r.get("magtype") or "")
        out.append({
            "number": int(r["rnumber"]),
            "location": _location_string(int(r["lat"]), int(r["lon"])),
            "lat_deg": float(r["lat"]),
            "lon_deg": float(r["lon"]),
            "carr_lon_deg": float(r["cLon"]),
            "area_uh": int(r.get("area") or 0),
            "zurich": str(r.get("zurich") or ""),
            "extent_deg": int(r.get("ext") or 0),
            "n_spots": int(r.get("numSpots") or 0),
            "mag_type": magtype,
            "seed_count": int(seed_counts[i]) if i < len(seed_counts) else 0,
            # A delta configuration means opposite polarities inside one
            # penumbra -- the flare-productive case, worth flagging in the UI.
            "is_complex": "delta" in magtype.lower(),
        })
    return {
        "schema": SCHEMA_AR,
        "pipeline_version": PIPELINE_VERSION,
        "generated_iso": iso_z(now),
        "generated_unix": unix_s(now),
        "status": status,
        "source": source,
        "srs_epoch_date": srs_epoch.isoformat() if srs_epoch else None,
        "count": len(out),
        "regions": out,
        "note": ("Array index is the ar_index space of pfss/topology.bin; "
                 "-1 there means the background seed grid."),
    }
