"""Daily solar-activity digest (``stats/summary.json``).

Everything here is fetched SERVER-side because the underlying SWPC products are
too big for a phone: the flare list is ~100 KB and the sunspot-cycle file is
~3,300 monthly records.  The app fetches only the small `products/summary/*`
endpoints live and takes the rest from this digest.

Rolling flare history: SWPC publishes a 7-day flare file and nothing longer, so
"biggest flare in 30 days" is accumulated across runs in
``<cache>/flares.json`` (deduped by begin_time+satellite, trimmed to 30 days).
``biggestFlare30d.history_coverage_hours`` reports how much of the window the
cache actually covers, so the app can be honest on a cold cache.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from ..config import (F107_URL, PIPELINE_VERSION, SCHEMA_STATS, SUNSPOTS_URL,
                      WINDOW_HOURS, XRAY_FLARES_URL)
from ..io_utils import (http_get_json, iso_z, parse_iso_z, read_json, unix_s,
                        write_json)

_CLASS_ORDER = {"A": 0, "B": 1, "C": 2, "M": 3, "X": 4}


def flare_magnitude(cls: Optional[str]) -> float:
    """Numeric ordering for GOES classes: 'C2.3' -> 2 + log-decade offset.

    Letters are decades of W/m^2, so a single monotone scalar is
    ``decade * 10 + mantissa``; that sorts X1.0 above M9.9 correctly.
    """
    if not cls or len(cls) < 2:
        return -1.0
    d = _CLASS_ORDER.get(cls[0].upper())
    if d is None:
        return -1.0
    try:
        mant = float(cls[1:])
    except ValueError:
        mant = 1.0
    return d * 10.0 + mant


def _merge_flare_history(cache_dir: Path, fresh: List[Dict],
                         now: datetime) -> List[Dict]:
    """Merge the 7-day file into a rolling 30-day cache; return the union."""
    path = Path(cache_dir) / "flares.json"
    prev = read_json(path) or []
    merged: Dict[str, Dict] = {}
    for rec in list(prev) + list(fresh):
        bt = rec.get("begin_time")
        if not bt:
            continue
        merged["{0}|{1}".format(bt, rec.get("satellite"))] = {
            "begin_time": bt,
            "max_time": rec.get("max_time"),
            "max_class": rec.get("max_class"),
            "satellite": rec.get("satellite"),
        }
    cutoff = now - timedelta(days=30)
    keep = [r for r in merged.values()
            if (parse_iso_z(r["begin_time"]) or now) >= cutoff]
    keep.sort(key=lambda r: r["begin_time"])
    write_json(path, keep)
    return keep


def _biggest(records: List[Dict]) -> Optional[Dict]:
    best, best_m = None, -1.0
    for r in records:
        m = flare_magnitude(r.get("max_class"))
        if m > best_m:
            best, best_m = r, m
    if best is None:
        return None
    return {"class": best.get("max_class"),
            "time_iso": best.get("max_time") or best.get("begin_time")}


def build_stats(now: datetime, cache_dir: Path, active_region_count: int,
                carrington: Dict, verbose: bool = False) -> Dict:
    """Assemble the digest.  Individual sources may fail -> their field is None."""
    ssn: Optional[Dict] = None
    try:
        rows = http_get_json(SUNSPOTS_URL)
        if rows:
            last = rows[-1]
            ssn = {"month": last.get("time-tag"),
                   "value": float(last.get("ssn")),
                   "smoothed": (float(last["smoothed_ssn"])
                                if last.get("smoothed_ssn") is not None
                                else None)}
    except Exception as exc:
        print("  WARN sunspots.json: {0}".format(exc))

    flares_24h: Optional[int] = None
    biggest_30d: Optional[Dict] = None
    latest_flare: Optional[Dict] = None
    flares_window: List[Dict] = []
    coverage_h = 0.0
    try:
        fresh = http_get_json(XRAY_FLARES_URL) or []
        cutoff = now - timedelta(hours=24)
        flares_24h = sum(1 for r in fresh
                         if (parse_iso_z(r.get("begin_time")) or now) >= cutoff)

        # Flares inside the PFSS look-back window, C-class and up, for the
        # app's time-scrubber markers ("scrub to the flare"). A/B events are
        # background noise and would carpet the track.
        cutoff_window = now - timedelta(hours=WINDOW_HOURS)
        for record in fresh:
            begin = parse_iso_z(record.get("begin_time"))
            if begin is None or begin < cutoff_window:
                continue
            cls = record.get("max_class") or ""
            if not cls or cls[0].upper() not in ("C", "M", "X"):
                continue
            peak = parse_iso_z(record.get("max_time")) or begin
            flares_window.append({
                "class": cls,
                "begin_iso": iso_z(begin),
                "peak_iso": iso_z(peak),
                "peak_unix": unix_s(peak),
            })
        flares_window.sort(key=lambda r: r["peak_unix"])
        if fresh:
            latest_flare = {"class": fresh[-1].get("max_class"),
                            "time_iso": fresh[-1].get("max_time")}
        history = _merge_flare_history(cache_dir, fresh, now)
        biggest_30d = _biggest(history)
        if history:
            oldest = parse_iso_z(history[0]["begin_time"])
            if oldest:
                coverage_h = max(0.0, (now - oldest).total_seconds() / 3600.0)
        if biggest_30d is not None:
            biggest_30d["window_days"] = 30
            biggest_30d["history_coverage_hours"] = round(coverage_h, 1)
    except Exception as exc:
        print("  WARN xray-flares-7-day.json: {0}".format(exc))

    f107: Optional[Dict] = None
    try:
        rows = http_get_json(F107_URL)
        rec = rows[0] if isinstance(rows, list) and rows else rows
        if isinstance(rec, dict) and rec.get("flux") is not None:
            f107 = {"value": float(rec["flux"]),
                    "time_iso": rec.get("time_tag")}
    except Exception as exc:
        print("  WARN 10cm-flux.json: {0}".format(exc))

    if verbose:
        print("    ssn {0}  ARs {1}  flares24h {2}  f10.7 {3}".format(
            ssn["value"] if ssn else "-", active_region_count,
            flares_24h if flares_24h is not None else "-",
            f107["value"] if f107 else "-"))

    return {
        "schema": SCHEMA_STATS,
        "pipeline_version": PIPELINE_VERSION,
        "generated_iso": iso_z(now),
        "generated_unix": unix_s(now),
        "sunspotNumber": ssn,
        "activeRegionCount": int(active_region_count),
        "flares24h": flares_24h,
        "latestFlare": latest_flare,
        "biggestFlare30d": biggest_30d,
        "flaresWindow": {"hours": WINDOW_HOURS, "events": flares_window},
        "f107": f107,
        "carrington": carrington,
        "sources": {
            "sunspotNumber": SUNSPOTS_URL,
            "flares": XRAY_FLARES_URL,
            "f107": F107_URL,
            "activeRegionCount": "NOAA SRS (services.swpc.noaa.gov/text/srs.txt)",
        },
    }
