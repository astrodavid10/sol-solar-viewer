"""Flare and CME event list (``events/events.json``).

JSON, not a binary frame format, and that is deliberate.  ``SOLPFRM1`` exists
because 19 frames x 19,328 vertices is 2.2 MB; here a 72 h window is 5-40
events of ~40 numbers each, measured at a few KB.  A binary format would add a
decoder, a validator and a footgun to save nothing.  What IS mirrored from the
PFSS product is the contract discipline: a pinned schema, an honest status, a
validator that re-derives the geometry, and a failure policy.

Two conversions happen here rather than in the app, because both need
ephemeris the browser does not have:

  1. **Cone axis -> ecliptic J2000.**  DONKI reports a CME's direction as
     Stonyhurst heliographic lat/lon, which IS HEEQ, so the unit vector is
     (cos b cos l, cos b sin l, sin b) and ``mat3_heeq_to_ecliptic_j2000``
     (already computed per frame by frames_orient) rotates it into the world
     frame the app draws in.  Shipping ``dir_ecl`` means the app applies NO
     transform at all -- which matters, because a CME must NOT carry the
     Carrington quaternion the field lines use (see ``dir_ecl`` below).

  2. **Stonyhurst -> Carrington longitude** for a flare's source, so a flare
     can be pinned to the rotating surface next to its own active region.

The AR join has a trap in it: DONKI numbers active regions 14513 where NOAA's
SRS calls the same region 4513.  Verified 2026-08-23 against both feeds
simultaneously.  The join is therefore ``donki.activeRegionNum - 10000``.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from .. import frames_orient
from ..config import (CME_MIN_SPEED_KMS, DONKI_DISCLAIMER, PIPELINE_VERSION,
                      SCHEMA_EVENTS, WINDOW_HOURS)
from ..io_utils import iso_z, parse_iso_z, unix_s
from ..sources import donki

# DONKI numbers regions 10000 higher than NOAA SRS does (see the module
# docstring).  A join without this silently matches nothing.
DONKI_AR_OFFSET = 10000

# A CME this fast counts as "fast" in the summary counts.
FAST_CME_KMS = 800.0

_LOCATION_RE = re.compile(r"^\s*([NS])(\d{1,2})([EW])(\d{1,3})\s*$")


def parse_source_location(text: object) -> Optional[Tuple[float, float]]:
    """``"N05E80"`` -> (lat_deg, stonyhurst_lon_deg), W positive.

    DONKI also emits empty strings and the odd malformed value; those mean a
    source we do not know, which is normal for a backside event, not an error.
    """
    if not isinstance(text, str):
        return None
    m = _LOCATION_RE.match(text)
    if not m:
        return None
    lat = float(m.group(2)) * (1.0 if m.group(1).upper() == "N" else -1.0)
    lon = float(m.group(4)) * (1.0 if m.group(3).upper() == "W" else -1.0)
    if abs(lat) > 90.0 or abs(lon) > 180.0:
        return None
    return lat, lon


def donki_time(text: object) -> Optional[datetime]:
    """DONKI stamps are ``2026-08-23T00:12Z`` -- minute resolution, no seconds,
    so ``parse_iso_z`` (which wants a full timestamp) needs the seconds put
    back before it will accept them."""
    if not isinstance(text, str) or not text:
        return None
    s = text.strip()
    if s.endswith("Z") and len(s) == 17:            # YYYY-MM-DDTHH:MMZ
        s = s[:-1] + ":00Z"
    return parse_iso_z(s)


def heeq_to_ecliptic(lat_deg: float, lon_deg: float,
                     when: datetime) -> List[float]:
    """Stonyhurst (== HEEQ) lat/lon -> unit vector in ecliptic J2000.

    The matrix is ROW-MAJOR and right-multiplies a column vector
    (frames_orient.constants_block spells this out), i.e. v_ecl = M . v_heeq.
    """
    b = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    v = (math.cos(b) * math.cos(lon), math.cos(b) * math.sin(lon), math.sin(b))
    m = frames_orient.orient_for(when)["mat3_heeq_to_ecliptic_j2000"]
    out = [
        m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
        m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
        m[6] * v[0] + m[7] * v[1] + m[8] * v[2],
    ]
    n = math.sqrt(sum(c * c for c in out)) or 1.0
    return [c / n for c in out]


def carrington_lon(stonyhurst_lon_deg: float, when: datetime) -> float:
    """Stonyhurst longitude -> Carrington longitude at ``when``.

    L0 is the Carrington longitude of the sub-Earth point and Stonyhurst
    longitude is measured from that same meridian, so the two simply add.
    """
    l0 = float(frames_orient.orient_for(when)["l0_deg"])
    return (stonyhurst_lon_deg + l0) % 360.0


def _ar_lookup(regions: Sequence[Dict]) -> Dict[int, int]:
    """SRS region number -> index in ``ar/regions.json``.

    That index IS the ``ar_index`` space of ``pfss/topology.bin``
    (regions/export.py says so), so an eruption can light up its own field
    lines without any further join.
    """
    out: Dict[int, int] = {}
    for i, r in enumerate(regions):
        try:
            out[int(r["number"])] = i
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _resolve_ar(raw_number: object,
                lookup: Dict[int, int]) -> Tuple[Optional[int], int]:
    """(SRS number, ar_index).

    ``ar_index`` is -1 when the region is not in the current table, which is
    normal rather than exceptional: DONKI keeps reporting a region for days
    after it has rotated off the visible disk and left the SRS.
    """
    try:
        donki_number = int(raw_number)
    except (TypeError, ValueError):
        return None, -1
    if donki_number <= 0:
        return None, -1
    srs_number = donki_number - DONKI_AR_OFFSET
    if srs_number <= 0:                     # already an SRS-style number
        srs_number = donki_number
    return srs_number, lookup.get(srs_number, -1)


def _flare(rec: Dict, lookup: Dict[int, int], oldest: datetime,
           newest: datetime) -> Optional[Dict]:
    peak = donki_time(rec.get("peakTime")) or donki_time(rec.get("beginTime"))
    if peak is None or not (oldest <= peak <= newest):
        return None
    begin = donki_time(rec.get("beginTime"))
    end = donki_time(rec.get("endTime"))
    srs_number, ar_index = _resolve_ar(rec.get("activeRegionNum"), lookup)

    linked = [str(e.get("activityID"))
              for e in (rec.get("linkedEvents") or [])
              if isinstance(e, dict) and e.get("activityID")]

    out: Dict[str, object] = {
        "id": str(rec.get("flrID") or ""),
        "kind": "flare",
        "class": str(rec.get("classType") or ""),
        "peak_unix": unix_s(peak),
        "peak_iso": iso_z(peak),
        "begin_unix": unix_s(begin) if begin else None,
        "end_unix": unix_s(end) if end else None,
        "ar_number": srs_number,
        "ar_index": ar_index,
        # DONKI's own flare <-> CME association, free and better than anything
        # we could infer from timing.
        "linked": linked,
        "donki_link": str(rec.get("link") or ""),
    }
    where = parse_source_location(rec.get("sourceLocation"))
    if where is not None:
        lat, lon = where
        out["source_location"] = str(rec.get("sourceLocation")).strip()
        out["source_lat_deg"] = lat
        out["source_stonyhurst_lon_deg"] = lon
        out["source_carr_lon_deg"] = carrington_lon(lon, peak)
    return out


def _impacts(rec: Dict) -> List[Dict]:
    out: List[Dict] = []
    for sim in (rec.get("enlilList") or []):
        if not isinstance(sim, dict):
            continue
        for hit in (sim.get("impactList") or []):
            if not isinstance(hit, dict):
                continue
            arrival = donki_time(hit.get("arrivalTime"))
            out.append({
                "location": str(hit.get("location") or ""),
                "arrival_unix": unix_s(arrival) if arrival else None,
                "is_glancing_blow": bool(hit.get("isGlancingBlow")),
            })
    return out


def _cme(rec: Dict, lookup: Dict[int, int], oldest: datetime,
         newest: datetime) -> Optional[Dict]:
    start = donki_time(rec.get("startTime"))
    if start is None or not (oldest <= start <= newest):
        return None
    analysis = donki.most_accurate_analysis(rec)
    if analysis is None:
        return None

    try:
        speed = float(analysis.get("speed"))
        half_angle = float(analysis.get("halfAngle"))
        lat = float(analysis.get("latitude"))
        lon = float(analysis.get("longitude"))
    except (TypeError, ValueError):
        return None
    # No fitted kinematics means nothing we can draw, and a very slow "CME" is
    # mostly not a real ejection.
    if not (speed >= CME_MIN_SPEED_KMS) or not (0.0 < half_angle < 90.0):
        return None
    if abs(lat) > 90.0 or abs(lon) > 180.0:
        return None

    srs_number, ar_index = _resolve_ar(rec.get("activeRegionNum"), lookup)
    t21 = donki_time(analysis.get("time21_5"))
    impacts = _impacts(rec)

    out: Dict[str, object] = {
        "id": str(rec.get("activityID") or ""),
        "kind": "cme",
        "start_unix": unix_s(start),
        "start_iso": iso_z(start),
        "time21_5_unix": unix_s(t21) if t21 else None,
        "speed_kms": speed,
        "half_angle_deg": half_angle,
        "lat_deg": lat,
        "lon_deg": lon,
        # Unit vector in ECLIPTIC J2000 -- the app's world frame. Shipped
        # precomputed so the app applies NO rotation: a CME travels along a
        # fixed INERTIAL direction, and attaching it to the Carrington
        # quaternion the field lines carry would swing it 14.18 deg/day, i.e.
        # 42.5 deg across the 72 h window.
        "dir_ecl": heeq_to_ecliptic(lat, lon, start),
        "type": str(analysis.get("type") or ""),
        "is_earth_directed": any(
            str(h.get("location", "")).lower().startswith("earth")
            for h in impacts),
        "impacts": impacts,
        "ar_number": srs_number,
        "ar_index": ar_index,
        "donki_link": str(rec.get("link") or ""),
    }
    where = parse_source_location(rec.get("sourceLocation"))
    if where is not None:
        out["source_location"] = str(rec.get("sourceLocation")).strip()
        out["source_lat_deg"] = where[0]
        out["source_stonyhurst_lon_deg"] = where[1]
    return out


def build_events(now: datetime, flares: Sequence[Dict], cmes: Sequence[Dict],
                 regions: Sequence[Dict], source: str,
                 window_hours: int = WINDOW_HOURS,
                 status: str = "ok") -> Dict:
    """Assemble ``events/events.json`` from raw DONKI records."""
    now = now.astimezone(timezone.utc)
    oldest = now - timedelta(hours=window_hours)
    # An hour of slack forward: DONKI stamps are minute-resolution and a clock
    # skew must not silently drop the newest event.
    newest = now + timedelta(hours=1)
    lookup = _ar_lookup(regions)

    out: List[Dict] = []
    for rec in flares:
        if isinstance(rec, dict):
            built = _flare(rec, lookup, oldest, newest)
            if built and built["id"]:
                out.append(built)
    for rec in cmes:
        if isinstance(rec, dict):
            built = _cme(rec, lookup, oldest, newest)
            if built and built["id"]:
                out.append(built)

    out.sort(key=lambda e: int(e.get("peak_unix") or e.get("start_unix") or 0))

    n_flares = sum(1 for e in out if e["kind"] == "flare")
    n_cmes = len(out) - n_flares
    x_class = sum(1 for e in out if e["kind"] == "flare"
                  and str(e.get("class", "")).upper().startswith("X"))
    fast = sum(1 for e in out if e["kind"] == "cme"
               and float(e.get("speed_kms") or 0.0) >= FAST_CME_KMS)

    return {
        "schema": SCHEMA_EVENTS,
        "pipeline_version": PIPELINE_VERSION,
        "generated_iso": iso_z(now),
        "generated_unix": unix_s(now),
        "status": status,
        "source": source,
        # MUST equal config.WINDOW_HOURS: the app places these on the same
        # track as the field-line frames, so a mismatch puts marks off the end.
        "window_hours": window_hours,
        "counts": {
            "flares": n_flares,
            "cmes": n_cmes,
            "x_class": x_class,
            "fast_cmes": fast,
        },
        "events": out,
        "disclaimer": DONKI_DISCLAIMER,
        "note": ("dir_ecl is a UNIT vector in ecliptic J2000 (the app's world "
                 "frame) and must be used WITHOUT the Carrington quaternion "
                 "the field lines carry. ar_index indexes ar/regions.json, the "
                 "same space as pfss/topology.bin; -1 means no matching "
                 "region. ar_number is the NOAA SRS number (DONKI's own is "
                 "10000 higher). An empty events array is DATA, not failure."),
    }


__all__ = ["build_events", "parse_source_location", "heeq_to_ecliptic",
           "carrington_lon", "donki_time", "DONKI_AR_OFFSET", "FAST_CME_KMS"]
