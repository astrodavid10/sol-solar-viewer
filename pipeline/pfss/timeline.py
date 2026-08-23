"""Resolve the 48 h window into 13 magnetogram slots.

The slot grid is snapped DOWN to the frame spacing (4 h), so every run of the
day asks for the same target times.  That is what makes the traced-frame cache
useful: a run at 12:07 and a run at 16:07 share 12 of their 13 targets.

Consecutive slots frequently resolve to the SAME GONG file (GONG publishes
roughly hourly but with gaps, and the tolerance is +/-3 h).  Those slots are
kept -- the app wants 13 evenly spaced frames -- but flagged ``shared`` so the
tracer solves the magnetogram once and the export reuses the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..config import FRAME_SPACING_HOURS, GONG_TOLERANCE_HOURS, WINDOW_HOURS
from ..sources.gong import gong_file_key, gong_find, gong_list


@dataclass
class Slot:
    """One animation frame's target time and the magnetogram behind it."""

    index: int                          # 0 == oldest
    target: datetime
    url: Optional[str] = None
    mag_dt: Optional[datetime] = None
    gong_key: Optional[str] = None
    age_hours: Optional[float] = None   # |mag_dt - target|
    shared_with: Optional[int] = None   # index of the first slot using this file
    note: str = ""

    @property
    def resolved(self) -> bool:
        return self.url is not None

    @property
    def is_shared(self) -> bool:
        return self.shared_with is not None


def snap_down(dt: datetime, spacing_hours: int = FRAME_SPACING_HOURS
              ) -> datetime:
    """Floor ``dt`` onto the UTC frame grid (00, 04, 08, ... by default)."""
    dt = dt.astimezone(timezone.utc)
    hour = (dt.hour // spacing_hours) * spacing_hours
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0)


def slot_targets(now_utc: datetime, window_hours: int = WINDOW_HOURS,
                 spacing_hours: int = FRAME_SPACING_HOURS) -> List[datetime]:
    """Oldest-first target times; the last one is the snapped 'now'."""
    newest = snap_down(now_utc, spacing_hours)
    n = window_hours // spacing_hours + 1
    return [newest - timedelta(hours=spacing_hours * (n - 1 - i))
            for i in range(n)]


def resolve_slots(now_utc: datetime, window_hours: int = WINDOW_HOURS,
                  spacing_hours: int = FRAME_SPACING_HOURS,
                  tolerance_hours: float = GONG_TOLERANCE_HOURS,
                  simulate_gong_outage: int = 0,
                  verbose: bool = False) -> List[Slot]:
    """Build the slot table, scraping GONG's directory listing once per day.

    ``simulate_gong_outage`` pretends the N NEWEST slots have no magnetogram --
    the realistic failure (GONG publishing lags), and the one that forces the
    reuse-previous-frame path.
    """
    targets = slot_targets(now_utc, window_hours, spacing_hours)
    # One scrape covers a whole day-directory triple; the window spans 3 days
    # at most, so cache listings by the date key we would have scraped.
    listings: dict = {}

    def candidates(t: datetime):
        key = t.date()
        if key not in listings:
            listings[key] = gong_list(t)
            if verbose:
                print("  GONG listing {0}: {1} file(s)".format(
                    key, len(listings[key])))
        return listings[key]

    slots: List[Slot] = []
    n = len(targets)
    for i, t in enumerate(targets):
        slot = Slot(index=i, target=t)
        outage = simulate_gong_outage > 0 and i >= n - simulate_gong_outage
        if outage:
            slot.note = "simulated GONG outage"
        else:
            found = gong_find(t, tolerance_hours, candidates(t))
            if found is None:
                slot.note = "no GONG within {0:.1f} h".format(tolerance_hours)
            else:
                url, mag_dt = found
                slot.url = url
                slot.mag_dt = mag_dt
                slot.gong_key = gong_file_key(url)
                slot.age_hours = abs((mag_dt - t).total_seconds()) / 3600.0
        slots.append(slot)

    # Flag duplicates (later slots pointing at a file an earlier slot already
    # claimed) so the tracer solves each magnetogram exactly once.
    first_for_key: dict = {}
    for slot in slots:
        if slot.gong_key is None:
            continue
        if slot.gong_key in first_for_key:
            slot.shared_with = first_for_key[slot.gong_key]
        else:
            first_for_key[slot.gong_key] = slot.index
    return slots


def unique_keys(slots: List[Slot]) -> List[str]:
    """Distinct magnetogram keys in slot order."""
    out: List[str] = []
    for s in slots:
        if s.gong_key and s.gong_key not in out:
            out.append(s.gong_key)
    return out


def plan_table(slots: List[Slot]) -> str:
    """Human-readable slot table for ``pipeline plan``."""
    lines = ["idx  target (UTC)          magnetogram (UTC)     dt(h)  key"]
    for s in slots:
        mag = s.mag_dt.strftime("%Y-%m-%d %H:%M") if s.mag_dt else "-"
        dt = "{0:5.2f}".format(s.age_hours) if s.age_hours is not None else "  - "
        key = s.gong_key or s.note or "-"
        if s.is_shared:
            key += "  (shared with f{0:02d})".format(s.shared_with)
        lines.append("f{0:02d}  {1}  {2}  {3}  {4}".format(
            s.index, s.target.strftime("%Y-%m-%d %H:%M"), mag, dt, key))
    return "\n".join(lines)


def slots_to_json(slots: List[Slot]) -> List[dict]:
    return [{
        "index": s.index,
        "target_iso": s.target.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mag_iso": (s.mag_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if s.mag_dt
                    else None),
        "gong_key": s.gong_key,
        "url": s.url,
        "age_hours": s.age_hours,
        "shared_with": s.shared_with,
        "note": s.note,
    } for s in slots]


def slots_from_json(data: List[dict]) -> List[Slot]:
    out = []
    for d in data:
        mag = d.get("mag_iso")
        out.append(Slot(
            index=int(d["index"]),
            target=datetime.fromisoformat(d["target_iso"].replace("Z", "+00:00")),
            url=d.get("url"),
            mag_dt=(datetime.fromisoformat(mag.replace("Z", "+00:00"))
                    if mag else None),
            gong_key=d.get("gong_key"),
            age_hours=d.get("age_hours"),
            shared_with=d.get("shared_with"),
            note=d.get("note", ""),
        ))
    return out
