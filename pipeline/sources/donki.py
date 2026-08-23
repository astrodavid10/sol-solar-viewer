"""CCMC DONKI flare and CME catalog.

DONKI is the only source we have found that gives a flare or CME a PLACE and a
DIRECTION.  NOAA's `xray-flares-latest.json` (already used by the app) reports
class and timing but has no source location at all, so it can say "an M8.1 is
happening" and never "from there, heading that way" -- which is the whole
feature.

What DONKI is not:

  * Real-time.  Measured over 2026-05-01..2026-08-23, the lag between an event
    and its DONKI record is a median 1.9 h for flares and 7.5 h for CMEs (p90
    16 h and 103 h).  That is comfortably inside a 72 h window on a 4 h
    pipeline, but the app must never claim more freshness than this.
  * Append-only.  Records are back-filled days later and carry a `versionId`
    that increments as analysts revise them.  So every run re-fetches the WHOLE
    window and dedupes on the event id, keeping the highest versionId.  Never
    append to a stored list.
  * Fast on wide windows.  A 3-day window answers in 0.74 s / 23 KB; a 235-day
    window takes 32.4 s.  Ask for the window and nothing more.

Cache: raw responses are kept under ``<cache>/donki/`` so a DONKI outage reuses
the last good pull, exactly as ``sources/gong.py`` does for magnetograms.  A
stale events file is a much better outcome than a failed run -- field lines are
the headline product and this one must never cost the guest a Sun.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..config import DONKI_BASE
from ..io_utils import PipelineError, atomic_write_bytes, http_get_full

Record = Dict[str, object]


def _window(now: datetime, hours: float) -> Tuple[str, str]:
    """DONKI's inclusive date window.  It takes DATES, not timestamps, so the
    start is floored a day early rather than risk clipping the oldest event."""
    end = now.astimezone(timezone.utc)
    start = end - timedelta(hours=hours + 24.0)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _cache_path(cache: Path, kind: str) -> Path:
    return cache / "donki" / "{0}.json".format(kind)


def _fetch(kind: str, now: datetime, hours: float, cache: Optional[Path],
           timeout: float = 45.0, verbose: bool = False,
           simulate_outage: bool = False) -> Tuple[List[Record], str]:
    """One DONKI endpoint.  Returns (records, source) where source is "live"
    or "cached:<age>"; raises only if there is neither."""
    start, end = _window(now, hours)
    url = "{0}{1}?startDate={2}&endDate={3}".format(DONKI_BASE, kind, start, end)
    try:
        if simulate_outage:
            raise RuntimeError("simulated DONKI outage")
        # prefer_ipv4: CCMC's AAAA record black-holes and urllib has no Happy
        # Eyeballs, so the default path costs 21 s per fetch. See
        # io_utils._ipv4_only for the measurement.
        raw, _ = http_get_full(url, timeout=timeout, prefer_ipv4=True)
        data = json.loads(raw.decode("utf-8", "replace"))
        if not isinstance(data, list):
            raise ValueError("expected a JSON array, got {0}".format(type(data).__name__))
        if cache is not None:
            atomic_write_bytes(_cache_path(cache, kind), raw)
        if verbose:
            print("  donki {0}: {1} record(s), {2} B".format(kind, len(data), len(raw)))
        return data, "live"
    except Exception as exc:                                  # noqa: BLE001
        if cache is not None:
            path = _cache_path(cache, kind)
            try:
                data = json.loads(path.read_bytes().decode("utf-8", "replace"))
                if isinstance(data, list):
                    print("  donki {0}: live fetch failed ({1}); using cache"
                          .format(kind, exc))
                    return data, "cached"
            except Exception:                                 # noqa: BLE001
                pass
        raise PipelineError("DONKI {0} unavailable: {1}".format(kind, exc))


def _dedupe(records: List[Record], id_key: str) -> List[Record]:
    """Keep the highest `versionId` per event id.

    DONKI revises records in place: a flare sampled during this work was on
    versionId 3.  Without this a re-fetch would show the same event several
    times with contradictory numbers.
    """
    best: Dict[str, Record] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        key = rec.get(id_key)
        if not isinstance(key, str) or not key:
            continue
        prior = best.get(key)
        if prior is None:
            best[key] = rec
            continue
        try:
            newer = int(rec.get("versionId") or 0) >= int(prior.get("versionId") or 0)
        except (TypeError, ValueError):
            newer = True
        if newer:
            best[key] = rec
    return list(best.values())


def fetch_flares(now: datetime, hours: float, cache: Optional[Path] = None,
                 verbose: bool = False, simulate_outage: bool = False
                 ) -> Tuple[List[Record], str]:
    records, source = _fetch("FLR", now, hours, cache, verbose=verbose,
                             simulate_outage=simulate_outage)
    return _dedupe(records, "flrID"), source


def fetch_cmes(now: datetime, hours: float, cache: Optional[Path] = None,
               verbose: bool = False, simulate_outage: bool = False
               ) -> Tuple[List[Record], str]:
    records, source = _fetch("CME", now, hours, cache, verbose=verbose,
                             simulate_outage=simulate_outage)
    return _dedupe(records, "activityID"), source


def most_accurate_analysis(cme: Record) -> Optional[Dict]:
    """The CME analysis to believe.

    DONKI attaches several analyses to one CME as different analysts fit it.
    Exactly one is normally flagged `isMostAccurate`; if none is, fall back to
    the last one listed, which is the most recently submitted.
    """
    analyses = cme.get("cmeAnalyses")
    if not isinstance(analyses, list) or not analyses:
        return None
    usable = [a for a in analyses if isinstance(a, dict)]
    if not usable:
        return None
    for a in usable:
        if a.get("isMostAccurate"):
            return a
    return usable[-1]


__all__ = ["fetch_flares", "fetch_cmes", "most_accurate_analysis"]
