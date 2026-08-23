"""Write a SYNTHETIC events.json so the flare/CME UI can be exercised.

Why this exists: the live DONKI window is usually boring. On 2026-08-23 it held
2 flares (no X-class), 5 CMEs, no predicted Earth impacts, and 3 of the 5 CMEs
came from regions that had already rotated off the disk. That is a perfectly
normal Sun, and it means the interesting card paths -- an X-class flare with a
known source, a fast Earth-directed CME with an arrival time, a flare linked to
its own CME -- never render.

So: run this to fill `public/data/events/events.json` with events that exercise
every branch, look at the app, then re-run the real pipeline to put it back:

    python scripts/make_event_fixture.py
    conda run -n sdo python -m pipeline events --out public/data

The output is DELIBERATELY marked in `source` and `note` so it can never be
mistaken for real data in a screenshot or a bug report, and it is written into
gitignored `public/data/`, so it cannot be committed by accident.

It is also a test of the validator: the fixture is built through the pipeline's
OWN `heeq_to_ecliptic`, so `pipeline validate --strict` must pass on it. If it
does not, either the fixture or the validator is wrong -- and both live here.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.config import (DONKI_DISCLAIMER, PIPELINE_VERSION,  # noqa: E402
                             SCHEMA_EVENTS, WINDOW_HOURS)
from pipeline.events.export import carrington_lon, heeq_to_ecliptic  # noqa: E402
from pipeline.io_utils import iso_z, read_json, unix_s, write_json  # noqa: E402

MARKER = ("SYNTHETIC FIXTURE from scripts/make_event_fixture.py -- NOT REAL "
          "DATA. Re-run `python -m pipeline events` to replace it.")


def build(now: datetime, regions) -> dict:
    """Six events spread across the window, covering every card branch."""
    # Anchor to a real region when one is available, so the AR join and the
    # "from sunspot region N" copy are exercised against the live table.
    ar_number = None
    ar_index = -1
    if regions:
        ar_number = int(regions[0].get("number", 0)) or None
        ar_index = 0

    def at(hours_ago: float) -> datetime:
        return now - timedelta(hours=hours_ago)

    def flare(hours_ago, cls, lat, lon, linked=(), with_ar=True):
        t = at(hours_ago)
        out = {
            "id": "{0}-FLR-FIXTURE".format(iso_z(t)),
            "kind": "flare",
            "class": cls,
            "peak_unix": unix_s(t),
            "peak_iso": iso_z(t),
            "begin_unix": unix_s(t - timedelta(minutes=12)),
            "end_unix": unix_s(t + timedelta(minutes=25)),
            "ar_number": ar_number if with_ar else None,
            "ar_index": ar_index if with_ar else -1,
            "linked": list(linked),
            "donki_link": "",
        }
        if lat is not None:
            out["source_location"] = "{0}{1:02d}{2}{3:02d}".format(
                "N" if lat >= 0 else "S", abs(lat),
                "W" if lon >= 0 else "E", abs(lon))
            out["source_lat_deg"] = float(lat)
            out["source_stonyhurst_lon_deg"] = float(lon)
            out["source_carr_lon_deg"] = carrington_lon(float(lon), t)
        return out

    def cme(hours_ago, speed, half, lat, lon, earth_hours=None, with_ar=True):
        t = at(hours_ago)
        impacts = []
        if earth_hours is not None:
            arrival = t + timedelta(hours=earth_hours)
            impacts.append({
                "location": "Earth",
                "arrival_unix": unix_s(arrival),
                "is_glancing_blow": False,
            })
        return {
            "id": "{0}-CME-FIXTURE".format(iso_z(t)),
            "kind": "cme",
            "start_unix": unix_s(t),
            "start_iso": iso_z(t),
            "time21_5_unix": unix_s(t + timedelta(hours=3)),
            "speed_kms": float(speed),
            "half_angle_deg": float(half),
            "lat_deg": float(lat),
            "lon_deg": float(lon),
            "dir_ecl": heeq_to_ecliptic(float(lat), float(lon), t),
            "type": "O" if speed >= 900 else "C",
            "is_earth_directed": earth_hours is not None,
            "impacts": impacts,
            "ar_number": ar_number if with_ar else None,
            "ar_index": ar_index if with_ar else -1,
            "donki_link": "",
        }

    linked_cme = cme(40.0, 1480, 38, 6, 4, earth_hours=52)
    events = [
        flare(62.0, "C4.1", -12, -68, with_ar=False),        # small, off-limb-ish
        flare(41.0, "X2.4", 6, 4, linked=[linked_cme["id"]]),  # the headline event
        linked_cme,                                            # fast + Earth-directed
        cme(30.0, 620, 22, -18, 61),                           # ordinary, aimed away
        flare(14.0, "M1.6", 9, 33),                            # recent, mid-size
        cme(6.0, 980, 15, 2, -47, earth_hours=61),             # fast, Earth-directed
    ]
    events.sort(key=lambda e: e.get("peak_unix") or e["start_unix"])

    n_flares = sum(1 for e in events if e["kind"] == "flare")
    return {
        "schema": SCHEMA_EVENTS,
        "pipeline_version": PIPELINE_VERSION,
        "generated_iso": iso_z(now),
        "generated_unix": unix_s(now),
        "status": "ok",
        "source": MARKER,
        "window_hours": WINDOW_HOURS,
        "counts": {
            "flares": n_flares,
            "cmes": len(events) - n_flares,
            "x_class": sum(1 for e in events
                           if e["kind"] == "flare" and e["class"].startswith("X")),
            "fast_cmes": sum(1 for e in events
                             if e["kind"] == "cme" and e["speed_kms"] >= 800.0),
        },
        "events": events,
        "disclaimer": DONKI_DISCLAIMER,
        "note": MARKER,
    }


def main() -> int:
    now = datetime.now(timezone.utc)
    out = REPO / "public" / "data" / "events" / "events.json"
    regions = (read_json(REPO / "public" / "data" / "ar" / "regions.json")
               or {}).get("regions") or []
    doc = build(now, regions)
    write_json(out, doc)
    c = doc["counts"]
    print("wrote {0}".format(out))
    print("  {0} flare(s) ({1} X), {2} CME(s) ({3} fast), {4} with an Earth arrival".format(
        c["flares"], c["x_class"], c["cmes"], c["fast_cmes"],
        sum(1 for e in doc["events"] if e.get("impacts"))))
    print("  SYNTHETIC -- re-run `python -m pipeline events --out public/data` to restore")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
