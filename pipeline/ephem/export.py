"""Bake spacecraft trajectories from JPL Horizons into a single JSON.

Why bake instead of fetching live from the browser?  Horizons sends no CORS
header, and the CORS-clean alternative (swhv.oma.be/position) accepts exactly
ONE epoch per request -- fine for a "now" dot, useless for a trail.  So the
trails are baked here (+/-30 d at 6 h = 241 samples per body, one HTTP call
each) and the app may optionally refresh only the now-dot live.

Earth is requested as ``'399'``: the string ``'Earth'`` is ambiguous in
Horizons (it matches several records and the query fails).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np

from ..config import (EPHEM_AT_EARTH, EPHEM_BODIES, EPHEM_SPAN_DAYS,
                      EPHEM_STEPS, PIPELINE_VERSION, SCHEMA_EPHEM)
from ..io_utils import iso_z, unix_s

_R_SUN_AU = 0.00465047  # 695700 km / 149597870.7 km


def _imports():
    import astropy.units as u
    from astropy.time import Time
    from astropy.coordinates import HeliocentricMeanEcliptic
    import sunpy.coordinates                            # noqa: F401
    from sunpy.coordinates import (HeliocentricInertial,
                                   HeliographicCarrington, get_earth,
                                   get_horizons_coord)
    return (u, Time, HeliocentricMeanEcliptic, HeliocentricInertial,
            HeliographicCarrington, get_earth, get_horizons_coord)


def _fetch_body(target: str, start, stop, steps: int, retries: int = 3):
    """One Horizons call with exponential backoff (3 attempts: 2 s, 4 s, 8 s)."""
    (_u, _Time, _HME, _HCI, _HGC, _get_earth, get_horizons_coord) = _imports()
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return get_horizons_coord(
                target, {"start": start, "stop": stop, "step": str(steps)})
        except Exception as exc:                        # network / Horizons 5xx
            last = exc
            wait = 2.0 * (2 ** attempt)
            print("  WARN Horizons {0} attempt {1}/{2}: {3} "
                  "(retry in {4:.0f}s)".format(target, attempt + 1, retries,
                                               exc, wait))
            if attempt < retries - 1:
                time.sleep(wait)
    raise RuntimeError("Horizons failed for {0}: {1}".format(target, last))


def build_spacecraft(now: datetime, verbose: bool = False) -> Dict:
    """Fetch every body and assemble ``ephem/spacecraft.json``.

    Raises on total failure so the caller can keep the previous file and mark
    the product stale rather than publishing an empty ephemeris.
    """
    (u, Time, HME, HCI, HGC, get_earth, _ghc) = _imports()

    start = Time(now - timedelta(days=EPHEM_SPAN_DAYS))
    stop = Time(now + timedelta(days=EPHEM_SPAN_DAYS))
    step_hours = 2.0 * EPHEM_SPAN_DAYS * 24.0 / EPHEM_STEPS

    bodies: List[Dict] = []
    epochs_unix: Optional[List[int]] = None
    now_index = 0

    for target, bid, name, hid, color in EPHEM_BODIES:
        t0 = time.perf_counter()
        coord = _fetch_body(target, start, stop, EPHEM_STEPS)
        obstime = coord.obstime

        ecl = coord.transform_to(HME(obstime=obstime, equinox="J2000"))
        xyz_au = np.asarray(ecl.cartesian.xyz.to_value(u.AU), dtype=float)

        r_au = np.linalg.norm(xyz_au, axis=0)
        r_rsun = r_au / _R_SUN_AU

        hci = coord.transform_to(HCI(obstime=obstime))
        carr = coord.transform_to(
            HGC(obstime=obstime, observer=get_earth(obstime)))

        if epochs_unix is None:
            epochs_unix = [int(round(v)) for v in obstime.unix]
            now_unix = unix_s(now)
            now_index = int(np.argmin(np.abs(np.asarray(epochs_unix)
                                             - now_unix)))
        bodies.append({
            "id": bid,
            "name": name,
            "horizons_id": hid,
            "color": color,
            # One [x, y, z] triple per epoch (not 3 parallel arrays): the app
            # flattens this straight into a Float32Array for the trail.
            "xyz_au": [[float(x), float(y), float(z)]
                       for x, y, z in zip(*xyz_au)],
            "r_rsun": [float(v) for v in r_rsun],
            "hci_lon_deg": [float(v) for v in hci.lon.to_value(u.deg)],
            "hci_lat_deg": [float(v) for v in hci.lat.to_value(u.deg)],
            "carr_lon_deg": [float(v) for v in carr.lon.to_value(u.deg)],
            "r_rsun_min": float(r_rsun.min()),
            "r_rsun_now": float(r_rsun[now_index]),
        })
        if verbose:
            print("    {0:22s} {1} samples, r_now {2:7.1f} R_sun, "
                  "r_min {3:6.1f} R_sun  ({4:.2f}s)".format(
                      name, len(r_rsun), r_rsun[now_index], r_rsun.min(),
                      time.perf_counter() - t0))

    return {
        "schema": SCHEMA_EPHEM,
        "pipeline_version": PIPELINE_VERSION,
        "generated_iso": iso_z(now),
        "generated_unix": unix_s(now),
        "source": "JPL Horizons via sunpy.coordinates.get_horizons_coord",
        "frame": "HeliocentricMeanEcliptic (equinox J2000), Sun-centered",
        "units": {"xyz_au": "AU ([x,y,z] per epoch)", "r_rsun": "R_sun",
                  "angles": "deg"},
        "epochs_unix": epochs_unix or [],
        "now_index": now_index,
        "now_iso": iso_z(now),
        "step_hours": step_hours,
        "span_days": [-EPHEM_SPAN_DAYS, EPHEM_SPAN_DAYS],
        "bodies": bodies,
        "at_earth": [dict(m) for m in EPHEM_AT_EARTH],
    }
