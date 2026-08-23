"""GONG synoptic magnetogram discovery + download.

Ported from ``sunspots-Bfield-daily.py`` (L869-994).  GONG publishes
``mrzqsYYMMDDtHHMMcCCCC_NNN.fits.gz`` under a per-day autoindex directory;
there is no query API, so discovery is an HTML scrape of three day
directories (target day +/- 1, because a slot near UTC midnight can be closest
to a file in the neighboring day).

Two additions over the dome version:
  * ``tolerance_hours`` -- the dome pipeline accepted *any* nearest file; a web
    animation must not silently show a 6 h old magnetogram as "now", so a slot
    whose closest file is further away than the tolerance resolves to None and
    the caller falls back to reuse/degraded handling.
  * ``gong_file_key`` -- the filename stem doubles as the traced-frame cache
    key, so consecutive slots landing on one magnetogram share a cache entry.
"""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple
import gzip
import uuid

from ..config import GONG_BASE, GONG_TOLERANCE_HOURS, HEADERS
from ..io_utils import quiet_unlink

_FITS_RE = re.compile(r"mrzqs(\d{6})t(\d{4})c\d+_\d+\.fits\.gz", re.IGNORECASE)


class _HrefParser(HTMLParser):
    """Collect every ``<a href>`` in a directory listing."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: List[str] = []

    def handle_starttag(self, tag, attrs):                  # noqa: D102
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.hrefs.append(v)


def _gong_dir_url(dt: datetime) -> str:
    return "{0}/{1}/mrzqs{2}/".format(
        GONG_BASE, dt.strftime("%Y%m"), dt.strftime("%y%m%d"))


def _scrape_gong(dir_url: str, timeout: float = 20.0
                 ) -> List[Tuple[datetime, str]]:
    """Return [(file_datetime_utc, url)] sorted by time; [] on any failure.

    A FAILURE IS PRINTED, not swallowed.  This used to be a bare
    ``except Exception: return []``, so a runner being blocked, a TLS failure
    and a genuinely empty day directory all reached the log as the same line --
    ``GONG listing 2026-08-23: 0 file(s)``.  On 2026-08-23 that cost a whole
    diagnosis cycle: CI reported 0/19 slots resolved while the identical request
    from a laptop answered 200 in 0.35 s, and the log could not say why.
    Whatever the reason turns out to be, it should be READABLE from one run.
    """
    try:
        req = urllib.request.Request(dir_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        print("  WARN GONG {0}: HTTP {1} {2}".format(
            dir_url, exc.code, exc.reason))
        return []
    except Exception as exc:                                   # noqa: BLE001
        print("  WARN GONG {0}: {1}: {2}".format(
            dir_url, type(exc).__name__, exc))
        return []
    parser = _HrefParser()
    parser.feed(html)
    out: List[Tuple[datetime, str]] = []
    for href in parser.hrefs:
        fname = href.split("/")[-1]
        m = _FITS_RE.match(fname)
        if not m:
            continue
        d, t = m.group(1), m.group(2)
        try:
            file_dt = datetime(2000 + int(d[:2]), int(d[2:4]), int(d[4:6]),
                               int(t[:2]), int(t[2:]), tzinfo=timezone.utc)
        except ValueError:
            continue
        full = href if href.startswith("http") else dir_url + fname
        out.append((file_dt, full))
    out.sort(key=lambda x: x[0])
    if not out:
        # Fetched fine, but nothing matched. Either a genuinely empty day or
        # GONG changed its filename convention -- say which by showing what was
        # actually in the listing.
        print("  WARN GONG {0}: fetched {1} byte(s), {2} link(s), 0 matched "
              "{3}".format(dir_url, len(html), len(parser.hrefs),
                           _FITS_RE.pattern))
    return out


def gong_list(target_dt: datetime) -> List[Tuple[datetime, str]]:
    """All candidates within one day either side of ``target_dt``."""
    cand: List[Tuple[datetime, str]] = []
    for offset in (0, -1, 1):
        cand.extend(_scrape_gong(_gong_dir_url(target_dt
                                               + timedelta(days=offset))))
    # The +/-1 day directories overlap nothing, but dedupe defensively.
    seen = set()
    uniq = []
    for dt, url in sorted(cand, key=lambda x: x[0]):
        if url in seen:
            continue
        seen.add(url)
        uniq.append((dt, url))
    return uniq


def gong_find(target_dt: datetime,
              tolerance_hours: float = GONG_TOLERANCE_HOURS,
              candidates: Optional[List[Tuple[datetime, str]]] = None
              ) -> Optional[Tuple[str, datetime]]:
    """Closest magnetogram to ``target_dt``, or None if none within tolerance.

    ``candidates`` lets a caller reuse one scrape across several nearby slots
    (19 slots over 72 h touch only ~4 day directories).
    """
    cand = candidates if candidates is not None else gong_list(target_dt)
    if not cand:
        return None
    best_dt, best_url = min(cand, key=lambda t: abs(t[0] - target_dt))
    if abs((best_dt - target_dt).total_seconds()) > tolerance_hours * 3600.0:
        return None
    return best_url, best_dt


def gong_file_key(url: str) -> str:
    """Cache key for a magnetogram URL: its filename stem.

    e.g. ``.../mrzqs260822t1914c2314_037.fits.gz`` -> ``mrzqs260822t1914c2314_037``
    """
    fname = url.split("/")[-1]
    for suffix in (".fits.gz", ".fits"):
        if fname.lower().endswith(suffix):
            return fname[: -len(suffix)]
    return fname


def gong_download(url: str, cache_dir: Path) -> Optional[Path]:
    """Download + gunzip a magnetogram into ``cache_dir``; return the .fits path.

    Process-unique temp files + ``os.replace`` so concurrent runs (or a CI
    re-run sharing a restored cache) never write or unlink each other's files.
    The freshest GONG timestamp is often still being published when we fetch it,
    so a truncated/not-yet-gzip body is normal: we return None and the caller
    treats the slot as unresolved rather than crashing.
    """
    cache_dir = Path(cache_dir)
    fname = url.split("/")[-1]
    fits_path = (cache_dir / fname).with_suffix("")     # strip .gz
    if fits_path.exists() and fits_path.stat().st_size > 0:
        return fits_path

    cache_dir.mkdir(parents=True, exist_ok=True)
    uniq = "{0}.{1}".format(os.getpid(), uuid.uuid4().hex)
    tmp_gz = cache_dir / "{0}.{1}.part".format(fname, uniq)
    tmp_fits = cache_dir / "{0}.{1}.part".format(fits_path.name, uniq)
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=60) as resp:
            tmp_gz.write_bytes(resp.read())
    except Exception as exc:
        print("  WARN GONG download {0}: {1}".format(url, exc))
        quiet_unlink(tmp_gz)
        return None
    try:
        with gzip.open(tmp_gz, "rb") as fh:
            data = fh.read()
        tmp_fits.write_bytes(data)
    except Exception as exc:
        print("  WARN GONG gunzip {0}: {1}".format(fname, exc))
        quiet_unlink(tmp_gz, tmp_fits)
        return None
    quiet_unlink(tmp_gz)

    if fits_path.exists() and fits_path.stat().st_size > 0:
        quiet_unlink(tmp_fits)          # another worker won the race
        return fits_path
    try:
        os.replace(tmp_fits, fits_path)
    except OSError:
        quiet_unlink(tmp_fits)
        if fits_path.exists() and fits_path.stat().st_size > 0:
            return fits_path
        return None
    return fits_path
