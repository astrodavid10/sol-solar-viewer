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
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple
import gzip
import uuid

from ..config import (GONG_BASE, GONG_PROXY_BASE, GONG_PROXY_HEADER,
                      GONG_PROXY_INDEX, GONG_PROXY_TOKEN,
                      GONG_SCRAPE_TIMEOUT, GONG_TOLERANCE_HOURS, HEADERS)
from ..io_utils import quiet_unlink

_FITS_RE = re.compile(r"mrzqs(\d{6})t(\d{4})c\d+_\d+\.fits\.gz", re.IGNORECASE)

# ── Circuit breaker ──────────────────────────────────────────────────────────
# gong2.nso.edu is unreachable from GitHub Actions runners (footgun 33): every
# request is a silent drop that costs the full timeout. A 19-slot window touches
# ~4 day directories and gong_list scrapes 3 each, so without a breaker one run
# spends 12 x GONG_SCRAPE_TIMEOUT waiting on a host that is not going to answer
# -- measured at nearly five minutes of a ~9 minute job.
#
# After this many consecutive TIMEOUTS the rest of the run skips GONG entirely.
# Reset between processes, never within one: a host that dropped two connections
# thirty seconds ago is not going to answer the third.
_TIMEOUT_BREAKER = 2
_consecutive_timeouts = 0
_breaker_announced = False


def _breaker_open() -> bool:
    """True once GONG has timed out enough times to stop asking."""
    global _breaker_announced
    if _consecutive_timeouts < _TIMEOUT_BREAKER:
        return False
    if not _breaker_announced:
        _breaker_announced = True
        print("  GONG unreachable ({0} consecutive timeouts); skipping the "
              "remaining listings this run".format(_consecutive_timeouts))
    return True


def reset_breaker() -> None:
    """Test hook: forget that GONG was unreachable."""
    global _consecutive_timeouts, _breaker_announced
    _consecutive_timeouts = 0
    _breaker_announced = False


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


def relay_enabled() -> bool:
    return bool(GONG_PROXY_BASE)


def _relay(url: str) -> str:
    """Rewrite a canonical GONG URL onto the relay, at request time only.

    Deliberately NOT applied where URLs are stored.  ``gong_file_key`` derives
    the traced-frame cache key from the URL, and the manifest cites it as
    provenance -- so rewriting at the source would both invalidate every cached
    frame the moment a relay is added or changed, and credit our proxy for
    NSO's data.  Canonical in the data model, relayed on the wire.
    """
    if not GONG_PROXY_BASE or not url.startswith(GONG_BASE):
        return url
    relayed = GONG_PROXY_BASE.rstrip("/") + url[len(GONG_BASE):]
    # A static path-preserving mirror (docs/GONG-RELAY.md Option D) cannot
    # answer a directory request the way the Cloudflare Worker does -- the
    # Worker fetches gong2.nso.edu live and hands back its real autoindex, but
    # raw.githubusercontent.com 404s on any directory path (measured
    # 2026-08-23, with and without a trailing slash). `_gong_dir_url()` always
    # asks for exactly that shape, so a static mirror has to publish a real
    # file (a synthetic index) at the directory's name and be asked for it by
    # name. GONG_PROXY_INDEX is that filename; empty (the default, and the
    # Worker's case) leaves this a no-op, byte-identical to before this knob
    # existed. Appended here, not stored anywhere -- same reasoning as the
    # rewrite above, and it must never reach `gong_file_key` or a manifest.
    if GONG_PROXY_INDEX and relayed.endswith("/"):
        relayed += GONG_PROXY_INDEX
    return relayed


def _relay_headers() -> dict:
    """Request headers, plus the shared secret when a relay is configured.

    The token keeps the relay from being an open proxy that anyone can point at
    NSO -- which would be a poor way to repay a service that is already
    rate-limited enough to firewall a cloud provider.
    """
    h = dict(HEADERS)
    if GONG_PROXY_BASE and GONG_PROXY_TOKEN:
        h[GONG_PROXY_HEADER] = GONG_PROXY_TOKEN
    return h


def _gong_dir_url(dt: datetime) -> str:
    return "{0}/{1}/mrzqs{2}/".format(
        GONG_BASE, dt.strftime("%Y%m"), dt.strftime("%y%m%d"))


def _scrape_gong(dir_url: str, timeout: float = GONG_SCRAPE_TIMEOUT
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
    global _consecutive_timeouts
    if _breaker_open():
        return []
    try:
        req = urllib.request.Request(_relay(dir_url),
                                    headers=_relay_headers())
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        _consecutive_timeouts = 0
    except urllib.error.HTTPError as exc:
        # An answer, even a rude one, means the host is reachable -- that is a
        # different failure from a drop and must not trip the breaker.
        _consecutive_timeouts = 0
        print("  WARN GONG {0}: HTTP {1} {2}".format(
            dir_url, exc.code, exc.reason))
        return []
    except Exception as exc:                                   # noqa: BLE001
        if isinstance(exc, socket.timeout) or "timed out" in str(exc):
            _consecutive_timeouts += 1
        else:
            _consecutive_timeouts = 0
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
        req = urllib.request.Request(_relay(url),
                                    headers=_relay_headers())
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
