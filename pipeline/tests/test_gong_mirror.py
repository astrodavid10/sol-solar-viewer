"""scripts/gong_mirror.py -- the go-live checks for docs/GONG-RELAY.md Option D.

Five things here can only be verified by test, because each of them is silent
when it breaks:

1. THE SYNTHETIC AUTOINDEX MUST PARSE BACK TO gong2.nso.edu URLS.  The mirror
   manufactures an ``index.html`` (raw.githubusercontent.com serves no
   directory listings), and `_scrape_gong` rebuilds each file's provenance URL
   as ``dir_url + fname`` from the CANONICAL directory it was asked for.  An
   absolute href in that index -- or a filename `_FITS_RE` does not match --
   would either point the traced-frame cache key and the published manifest at
   our own proxy (footgun 37) or drop every file with no error at all.
2. RETENTION MUST COVER THE WHOLE WINDOW THE PIPELINE SCRAPES.  A day
   directory the pipeline asks for and the mirror pruned is a 404, which
   `_scrape_gong` reports as "0 file(s)" -- indistinguishable from GONG being
   down.
3. THE PUSH CREDENTIAL MUST NOT REACH A LOG.  `_push` passes the token as a
   base64 ``http.extraheader`` argv element, and `_git`'s error message is
   built from that argv.
4. A RUN THAT FETCHES NOTHING MUST NOT PUBLISH AN EMPTY TREE.  The push is
   ``--force`` and consults nothing on the remote.
5. A MAGNETOGRAM MUST CROSS BYTE-FOR-BYTE, still gzipped.  The pipeline's own
   `gong_download` gunzips; this mirror must not.

The module is loaded by path (it lives in ``scripts/``, not in a package).
That is safe at import time only because `gong_mirror` imports nothing from
`pipeline` at module level -- it cannot, since `main()` has to clear
``SOL_GONG_PROXY_*`` from the environment BEFORE `pipeline.config` reads it.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ..config import FRAME_SPACING_HOURS, WINDOW_HOURS
from ..pfss import timeline
from ..sources import gong as pgong

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_mirror():
    spec = importlib.util.spec_from_file_location(
        "gong_mirror_under_test", REPO_ROOT / "scripts" / "gong_mirror.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gong_mirror = _load_mirror()

DAY = datetime(2026, 9, 1, tzinfo=timezone.utc)
NAMES = [
    "mrzqs260901t0014c2314_029.fits.gz",
    "mrzqs260901t1214c2314_033.fits.gz",
    "mrzqs260901t2314c2314_037.fits.gz",
]


class _FakeResp:
    """Minimal urlopen() context manager."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _fake_gzip_fits(marker: bytes = b"SIMPLE  =                    T") -> bytes:
    return gzip.compress(marker + b" " * 200)


def _mirrored_day(tmp_path: Path, day: datetime = DAY) -> Path:
    """A day directory holding NAMES, as the mirror would leave it."""
    dest = tmp_path / "oQR" / "zqs" / gong_mirror._rel_day_dir(day)
    dest.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        (dest / name).write_bytes(_fake_gzip_fits())
    return dest


# ── 1. the synthetic autoindex, through the pipeline's real parser ───────────

def _scrape_the_written_index(tmp_path, monkeypatch, dest, dir_url):
    """Serve dest/index.html byte-for-byte and run the real `_scrape_gong`."""
    body = (dest / "index.html").read_bytes()
    asked = []

    def fake_urlopen(req, timeout=None):
        asked.append(req.full_url)
        return _FakeResp(body)

    monkeypatch.setattr(pgong.urllib.request, "urlopen", fake_urlopen)
    pgong.reset_breaker()
    return asked, pgong._scrape_gong(dir_url)


def test_synthetic_index_parses_back_to_canonical_gong_urls(tmp_path,
                                                            monkeypatch):
    dest = _mirrored_day(tmp_path)
    dir_url = pgong._gong_dir_url(DAY)
    assert dir_url == "https://gong2.nso.edu/oQR/zqs/202609/mrzqs260901/"

    assert gong_mirror._write_index(dest, dir_url) == len(NAMES)
    monkeypatch.setattr(pgong, "GONG_PROXY_BASE", "")
    monkeypatch.setattr(pgong, "GONG_PROXY_INDEX", "")
    asked, got = _scrape_the_written_index(tmp_path, monkeypatch, dest, dir_url)

    # No relay configured -> the wire URL is the canonical directory itself.
    assert asked == [dir_url]
    # Every file comes back, in time order, with its CANONICAL provenance URL.
    assert [u for _dt, u in got] == [dir_url + n for n in NAMES]
    assert [dt for dt, _u in got] == [
        datetime(2026, 9, 1, 0, 14, tzinfo=timezone.utc),
        datetime(2026, 9, 1, 12, 14, tzinfo=timezone.utc),
        datetime(2026, 9, 1, 23, 14, tzinfo=timezone.utc),
    ]
    # The cache key / manifest citation must name NSO, never the mirror.
    for _dt, url in got:
        assert url.startswith("https://gong2.nso.edu/"), url
        assert pgong.gong_file_key(url) == url.split("/")[-1][: -len(".fits.gz")]


def test_relay_asks_for_the_index_file_but_still_reports_nso_urls(
        tmp_path, monkeypatch):
    """The exact Option D configuration, end to end through the parser."""
    dest = _mirrored_day(tmp_path)
    dir_url = pgong._gong_dir_url(DAY)
    gong_mirror._write_index(dest, dir_url)

    proxy = ("https://raw.githubusercontent.com/astrodavid10/"
             "sol-solar-viewer/gong-cache/oQR/zqs")
    monkeypatch.setattr(pgong, "GONG_PROXY_BASE", proxy)
    monkeypatch.setattr(pgong, "GONG_PROXY_INDEX", "index.html")
    asked, got = _scrape_the_written_index(tmp_path, monkeypatch, dest, dir_url)

    assert asked == [proxy + "/202609/mrzqs260901/index.html"]
    assert [u for _dt, u in got] == [dir_url + n for n in NAMES]
    # And the file fetch relays to a real path under the same tree.
    assert pgong._relay(dir_url + NAMES[0]) == (
        proxy + "/202609/mrzqs260901/" + NAMES[0])


def test_the_index_survives_crlf_line_endings(tmp_path, monkeypatch):
    """`_write_index` writes LF, but a checkout/CDN could hand back CRLF."""
    dest = _mirrored_day(tmp_path)
    dir_url = pgong._gong_dir_url(DAY)
    gong_mirror._write_index(dest, dir_url)
    lf = (dest / "index.html").read_bytes()
    assert b"\r\n" not in lf                      # written as LF on any OS
    (dest / "index.html").write_bytes(lf.replace(b"\n", b"\r\n"))

    monkeypatch.setattr(pgong, "GONG_PROXY_BASE", "")
    monkeypatch.setattr(pgong, "GONG_PROXY_INDEX", "")
    _asked, got = _scrape_the_written_index(tmp_path, monkeypatch, dest,
                                            dir_url)
    assert [u for _dt, u in got] == [dir_url + n for n in NAMES]


def test_index_names_only_files_that_are_really_there(tmp_path):
    dest = _mirrored_day(tmp_path)
    (dest / NAMES[1]).unlink()
    dir_url = pgong._gong_dir_url(DAY)
    assert gong_mirror._write_index(dest, dir_url) == 2
    text = (dest / "index.html").read_text(encoding="utf-8")
    assert NAMES[1] not in text
    # Relative hrefs only: an absolute one would relocate the provenance URL.
    assert "raw.githubusercontent" not in text
    assert 'href="http' not in text
    # An empty / nonexistent directory gets no manufactured index at all.
    assert gong_mirror._write_index(tmp_path / "nope", dir_url) == 0
    assert not (tmp_path / "nope").exists()


# ── 2. retention vs. the window the pipeline actually scrapes ────────────────

def _days_the_pipeline_scrapes(now):
    """Every day directory `resolve_slots` -> `gong_list` would ask for."""
    wanted = set()
    for target in timeline.slot_targets(now, WINDOW_HOURS, FRAME_SPACING_HOURS):
        for offset in (0, -1, 1):        # gong_list's own triple
            wanted.add((target + timedelta(days=offset)).date())
    return wanted


@pytest.mark.parametrize("now", [
    datetime(2026, 9, 2, 0, 0, 0, tzinfo=timezone.utc),      # UTC midnight
    datetime(2026, 9, 2, 0, 0, 1, tzinfo=timezone.utc),
    datetime(2026, 9, 2, 3, 59, 59, tzinfo=timezone.utc),    # pre-snap
    datetime(2026, 9, 2, 18, 30, 0, tzinfo=timezone.utc),
    datetime(2026, 9, 2, 23, 59, 59, tzinfo=timezone.utc),
    datetime(2026, 3, 1, 5, 0, 0, tzinfo=timezone.utc),      # month boundary
    datetime(2027, 1, 2, 5, 0, 0, tzinfo=timezone.utc),      # year boundary
])
def test_default_retention_covers_every_day_the_pipeline_scrapes(now):
    kept = {d.date() for d in
            gong_mirror._day_range(now, gong_mirror.DEFAULT_RETAIN_DAYS)}
    wanted = _days_the_pipeline_scrapes(now)
    assert wanted <= kept, sorted(wanted - kept)
    # 5 days is one day of margin, not an arbitrary number: the pipeline
    # reaches back 72 h and gong_list adds another day, so 4 is exact and 3
    # is short. If this stops failing, WINDOW_HOURS shrank.
    assert not (wanted <= {d.date() for d in gong_mirror._day_range(now, 3)})


def test_day_range_is_utc_not_local():
    """The workstation is Central time; the mirror must not be."""
    now = datetime(2026, 9, 2, 2, 30, tzinfo=timezone.utc)   # 21:30 CDT Sep 1
    days = gong_mirror._day_range(now, 5)
    assert all(d.tzinfo == timezone.utc for d in days)
    assert days[-1].date() == datetime(2026, 9, 3).date()
    assert days[0].date() == datetime(2026, 8, 28).date()
    assert [d.hour for d in days] == [0] * len(days)
    assert gong_mirror._rel_day_dir(days[-1]) == "202609/mrzqs260903"


def test_prune_keeps_the_window_and_drops_what_is_outside(tmp_path):
    now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    days = gong_mirror._day_range(now, 5)
    inside = [days[0], days[3], days[-1]]
    outside = [days[0] - timedelta(days=1), days[-1] + timedelta(days=1),
               datetime(2026, 8, 1, tzinfo=timezone.utc),
               datetime(2026, 7, 15, tzinfo=timezone.utc)]
    for day in inside + outside:
        _mirrored_day(tmp_path, day)

    dirs_pruned, files_pruned = gong_mirror._prune(tmp_path, days[0], days[-1])
    assert dirs_pruned == len(outside)
    assert files_pruned == len(outside) * len(NAMES)
    root = tmp_path / "oQR" / "zqs"
    for day in inside:
        assert (root / gong_mirror._rel_day_dir(day)).is_dir()
    for day in outside:
        assert not (root / gong_mirror._rel_day_dir(day)).exists()
    # 202607 held only pruned days, so its month directory goes too --
    # but 202608 must survive, because the window starts on 08-28.
    assert not (root / "202607").exists()
    assert (root / "202608").is_dir()


# ── 3. the push credential never reaches a log ───────────────────────────────

def test_git_failure_redacts_the_push_credential(tmp_path):
    """A failed push used to log a working, base64-only GitHub token."""
    header = "AUTHORIZATION: basic eC1hY2Nlc3MtdG9rZW46U0VDUkVU"
    with pytest.raises(RuntimeError) as excinfo:
        gong_mirror._git(tmp_path, "-c",
                         "http.extraheader={0}".format(header),
                         "--no-such-flag")
    msg = str(excinfo.value)
    assert "<redacted>" in msg
    assert "SECRET" not in msg
    assert "eC1hY2Nlc3MtdG9rZW46" not in msg
    # It must still say WHICH invocation failed.
    assert "http.extraheader=<redacted>" in msg
    assert "--no-such-flag" in msg


def test_redaction_covers_argv_and_captured_output():
    args = ["-c", "http.extraheader=AUTHORIZATION: basic U0VDUkVU", "push"]
    assert gong_mirror._redact_args(args) == [
        "-c", "http.extraheader=<redacted>", "push"]
    # A bare header arg (a future --header-style spelling) is caught too.
    assert gong_mirror._redact_args(
        ["AUTHORIZATION: basic U0VDUkVU"]) == ["<redacted>"]
    # GIT_TRACE=1 prints the whole argv into stderr; scrub that shape as well.
    trace = ("trace: run_command: git -c "
             "'http.extraheader=AUTHORIZATION: basic U0VDUkVU' push --force")
    scrubbed = gong_mirror._redact_text(trace)
    assert "U0VDUkVU" not in scrubbed
    assert "<redacted>" in scrubbed
    # Non-secret output is untouched.
    assert gong_mirror._redact_text(
        "fatal: Authentication failed for "
        "'https://github.com/astrodavid10/sol-solar-viewer.git/'"
    ) == ("fatal: Authentication failed for "
          "'https://github.com/astrodavid10/sol-solar-viewer.git/'")


def test_git_env_disables_the_credential_prompt():
    env = gong_mirror._git_env()
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_COMMITTER_NAME"] == env["GIT_AUTHOR_NAME"]


# ── 4. GONG down: never publish an emptier tree than the last good one ───────

def _run_main_with_gong_down(tmp_path, monkeypatch, extra=()):
    """main() with every listing empty and the push intercepted."""
    monkeypatch.setattr(pgong, "_scrape_gong",
                        lambda dir_url, timeout=None: [])
    pushed = []
    monkeypatch.setattr(gong_mirror, "_push",
                        lambda state_dir, branch: pushed.append(branch))
    rc = gong_mirror.main(["--state-dir", str(tmp_path),
                           "--retain-days", "5"] + list(extra))
    return rc, pushed


def test_a_cold_state_dir_during_an_outage_does_not_push_an_empty_tree(
        tmp_path, monkeypatch):
    rc, pushed = _run_main_with_gong_down(tmp_path, monkeypatch)
    assert rc == 1
    assert pushed == []
    # And it did not even initialize a repo, so there is nothing to push later.
    assert not (tmp_path / ".git").exists()


def test_an_outage_keeps_the_files_already_mirrored_and_still_reports_failure(
        tmp_path, monkeypatch, capsys):
    today = datetime.now(timezone.utc)
    dest = tmp_path / "oQR" / "zqs" / gong_mirror._rel_day_dir(today)
    dest.mkdir(parents=True)
    name = "mrzqs{0}t1200c2314_029.fits.gz".format(today.strftime("%y%m%d"))
    dest.joinpath(name).write_bytes(_fake_gzip_fits())

    rc, pushed = _run_main_with_gong_down(tmp_path, monkeypatch)
    out = capsys.readouterr().out
    assert rc == 1, out
    # The good tree IS still published -- only an EMPTY one is withheld.
    assert pushed == ["gong-cache"], out
    assert dest.joinpath(name).exists()
    assert "SUMMARY: FAILURE" in out
    assert "unreachable" in out
    assert "still holds 1 file(s)" in out


def test_dry_run_never_pushes_and_leaves_a_clean_index(tmp_path, monkeypatch):
    today = datetime.now(timezone.utc)
    dest = tmp_path / "oQR" / "zqs" / gong_mirror._rel_day_dir(today)
    dest.mkdir(parents=True)
    name = "mrzqs{0}t1200c2314_029.fits.gz".format(today.strftime("%y%m%d"))
    dest.joinpath(name).write_bytes(_fake_gzip_fits())

    rc, pushed = _run_main_with_gong_down(tmp_path, monkeypatch,
                                          extra=["--dry-run"])
    assert rc == 1                      # the outage, not the dry run
    assert pushed == []
    # A dry run may create the local repo, but must leave no commit and no
    # staged index behind for a later run to inherit.
    assert gong_mirror._git(tmp_path, "rev-parse", "-q", "--verify", "HEAD",
                            check=False).returncode != 0
    assert gong_mirror._git(tmp_path, "diff", "--cached", "--name-only"
                            ).stdout.strip() == ""
    # .gitignore keeps run state out of the mirror.
    assert (tmp_path / ".gitignore").read_text().splitlines() == [
        ".mirror.lock", "*.part"]
    assert not (tmp_path / ".mirror.lock").exists()


# ── 5. bytes cross verbatim: still gzipped, never re-compressed ──────────────

def test_download_stores_the_gzip_bytes_verbatim(tmp_path, monkeypatch):
    raw = _fake_gzip_fits()
    monkeypatch.setattr(gong_mirror.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResp(raw))
    dest = tmp_path / NAMES[0]
    ok, err = gong_mirror._download_one("https://gong2.nso.edu/x", dest)
    assert ok and err is None
    assert dest.read_bytes() == raw
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == \
        hashlib.sha256(raw).hexdigest()
    assert dest.read_bytes()[:2] == b"\x1f\x8b"          # still gzipped
    assert gzip.decompress(dest.read_bytes()).startswith(b"SIMPLE")
    assert list(tmp_path.glob("*.part")) == []


@pytest.mark.parametrize("body,fragment", [
    (b"<html>404</html>", "not a valid gzip stream"),
    (gzip.compress(b"NOT-A-FITS-FILE" + b" " * 100), "FITS magic"),
])
def test_download_rejects_a_body_that_is_not_a_gzipped_fits(
        tmp_path, monkeypatch, body, fragment):
    monkeypatch.setattr(gong_mirror.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResp(body))
    dest = tmp_path / NAMES[0]
    ok, err = gong_mirror._download_one("https://gong2.nso.edu/x", dest)
    assert not ok
    assert fragment in err
    assert not dest.exists()
    assert list(tmp_path.glob("*.part")) == []
