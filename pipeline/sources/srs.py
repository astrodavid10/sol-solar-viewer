"""NOAA SWPC active-region tables (SRS), HTTPS only.

Ported from ``sunspots-Bfield-daily.py`` (L395-716) minus every FTP path: the
dome pipeline could fall back to ``ftp://ftp.swpc.noaa.gov`` for archive days,
but GitHub Actions runners (and most corporate networks) block outbound FTP, so
those paths would only ever cost a timeout here.  What is left:

  1. ``https://services.swpc.noaa.gov/text/srs.txt``  -- today's report,
     authoritative, with the ``:Issued:`` epoch we key the seed set on.
  2. ``https://services.swpc.noaa.gov/json/solar_regions.json`` -- ~30 days of
     region history, used when srs.txt is unavailable or lags.

Region dicts use the dome pipeline's field names (``rnumber``, ``cLon``,
``numSpots``, ...) so the seed builder is a straight port.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..config import SRS_JSON_URL, SRS_URL
from ..io_utils import http_get_json, http_get_text

Region = Dict[str, object]

_SRS_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}

_REGIONS_JSON_CACHE: Optional[Dict[date, List[Region]]] = None


def fetch_srs(timeout: float = 30.0) -> str:
    """Today's SRS text report."""
    return http_get_text(SRS_URL, timeout)


def srs_epoch_date(text: str) -> Optional[date]:
    """The ``:Issued: YYYY Mon DD`` epoch -- the seed-set cache key."""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(":Issued:"):
            m = re.search(r":Issued:\s+(\d{4})\s+([A-Za-z]{3})\s+(\d{1,2})", s)
            if m:
                mo = _SRS_MONTHS.get(m.group(2).title())
                if mo:
                    try:
                        return date(int(m.group(1)), mo, int(m.group(3)))
                    except ValueError:
                        return None
            break
    return None


def parse_srs(text: str) -> List[Region]:
    """Parse Section I of an SRS report into region dicts.

    Section I columns: Nmbr Location Lo Area Z LL NN Mag Type.  ``Location`` is
    a fixed-width Stonyhurst string (e.g. ``N14W37``); ``Lo`` is Carrington
    longitude.  Longitude sign is flipped to W-positive to match the dome
    pipeline's convention (used for its west-limb tests).
    """
    regions: List[Region] = []
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if not in_section:
            if line.startswith("Nmbr"):
                in_section = True
            continue
        if line.startswith("IA.") or line.startswith("None"):
            break
        fields = line.split()
        if len(fields) < 7:
            continue
        try:
            rnumber = int(fields[0])
            loc = fields[1]
            c_lon = int(fields[2])
            area = int(fields[3])
            zurich = fields[4]
            ext = int(fields[5])
            try:
                num_spots = int(fields[6])
            except ValueError:
                num_spots = 1
            magtype = " ".join(fields[7:]) if len(fields) > 7 else ""
        except (ValueError, IndexError):
            continue
        if len(loc) < 6:
            continue
        lat_sign = -1 if loc[0].upper() == "S" else 1
        lon_sign = -1 if loc[3].upper() == "E" else 1
        try:
            lat = lat_sign * int(loc[1:3])
            lon = lon_sign * int(loc[4:6])
        except ValueError:
            continue
        regions.append({
            "rnumber": rnumber, "numSpots": num_spots, "lat": lat,
            "lon": lon, "cLon": c_lon, "area": area, "ext": ext,
            "zurich": zurich, "magtype": magtype,
        })
    return regions


def _mag_class_to_magtype(mag_class: Optional[str]) -> str:
    """JSON Mt-Wilson abbreviation (A/B/BG/BGD/...) -> SRS-style word string.

    Downstream code (and the app's ``is_complex`` delta flag) matches on the
    words 'beta'/'gamma'/'delta', so both sources must speak the same dialect.
    """
    if not mag_class:
        return ""
    m = mag_class.upper()
    parts = []
    if "B" in m:
        parts.append("Beta")
    if "G" in m:
        parts.append("Gamma")
    if "D" in m:
        parts.append("Delta")
    if not parts and "A" in m:
        parts.append("Alpha")
    return "-".join(parts)


def fetch_regions_json(timeout: float = 30.0) -> Dict[date, List[Region]]:
    """``{date -> [region]}`` from solar_regions.json (cached per process).

    NOTE the JSON's Stonyhurst ``longitude`` is E-positive, the OPPOSITE of
    ``parse_srs``, so it is negated here.  An empty dict is cached on failure so
    a dead endpoint costs one timeout per run, not one per lookup.
    """
    global _REGIONS_JSON_CACHE
    if _REGIONS_JSON_CACHE is not None:
        return _REGIONS_JSON_CACHE
    out: Dict[date, List[Region]] = {}
    try:
        data = http_get_json(SRS_JSON_URL, timeout)
    except Exception as exc:
        print("  WARN solar_regions.json unavailable: {0}".format(exc))
        _REGIONS_JSON_CACHE = {}
        return _REGIONS_JSON_CACHE
    for rec in data:
        od = rec.get("observed_date")
        if not od:
            continue
        try:
            d = datetime.strptime(od[:10], "%Y-%m-%d").date()
            rnumber = int(rec.get("region"))
        except (TypeError, ValueError):
            continue
        lat, clon = rec.get("latitude"), rec.get("carrington_longitude")
        if lat is None or clon is None:
            continue
        out.setdefault(d, []).append({
            "rnumber": rnumber,
            "numSpots": int(rec.get("number_spots") or 1),
            "lat": int(lat),
            "lon": -int(rec.get("longitude") or 0),      # E+/W- -> W+
            "cLon": int(clon),
            "area": int(rec.get("area") or 0),
            "ext": int(rec.get("extent") or 0),
            "zurich": rec.get("spot_class") or "",
            "magtype": _mag_class_to_magtype(rec.get("mag_class")),
        })
    _REGIONS_JSON_CACHE = out
    return out


def regions_for_date(d: date, timeout: float = 30.0
                     ) -> Tuple[List[Region], str]:
    """Regions observed on ``d`` from the HTTPS history product."""
    jr = fetch_regions_json(timeout)
    if d in jr:
        return jr[d], "solar_regions.json"
    return [], "none"


def newest_regions(cache_dir: Path, simulate_outage: bool = False,
                   timeout: float = 30.0
                   ) -> Tuple[List[Region], Optional[date], str]:
    """The freshest available region list: (regions, srs_epoch_date, source).

    Order: live srs.txt -> cached srs.txt (any previous run) -> newest day in
    solar_regions.json.  Returns ``([], None, "outage")`` when nothing works;
    the caller then falls back to the persisted seed arrays.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if simulate_outage:
        # The drill must exercise the *seed npz* fallback, so a cached srs.txt
        # (which would rebuild an identical seed set) is skipped too.
        print("  SRS: simulated outage (no srs.txt, no JSON, no cached text)")
        return [], None, "outage"

    try:
        text = fetch_srs(timeout)
        epoch = srs_epoch_date(text)
        regions = parse_srs(text)
        if epoch is not None:
            (cache_dir / "{0}SRS.txt".format(epoch.strftime("%Y%m%d"))
             ).write_text(text, encoding="utf-8")
            # A genuinely spotless Sun is legal, so an empty list with a good
            # epoch is still a successful fetch.
            return regions, epoch, "srs.txt"
    except Exception as exc:
        print("  WARN srs.txt: {0}".format(exc))

    cached = sorted(cache_dir.glob("*SRS.txt"))
    if cached:
        text = cached[-1].read_text(encoding="utf-8", errors="replace")
        epoch = srs_epoch_date(text)
        regions = parse_srs(text)
        if epoch is not None:
            return regions, epoch, "cached {0}".format(cached[-1].name)

    jr = fetch_regions_json(timeout)
    if jr:
        d = max(jr)
        return jr[d], d, "solar_regions.json"

    return [], None, "outage"
