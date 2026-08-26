"""Mirror NSO/GONG synoptic magnetograms to a git branch, for CI to read.

WHY THIS EXISTS. `gong2.nso.edu` drops every connection from a GitHub Actions
runner (CLAUDE.md footgun 33, docs/GONG-RELAY.md) but answers fine from this
workstation. Option A (docs/GONG-RELAY.md, the Cloudflare Worker) is the
recommended fix and this script does not replace it -- it is Option D, a
fallback that needs no Cloudflare account: run this hourly on a machine that
CAN reach GONG, and it republishes what it sees to the `gong-cache` branch of
this same repo. CI then reads it over `raw.githubusercontent.com`, which sits
in a different address space than the blocked one.

`raw.githubusercontent.com` serves a FILE at a path, never a directory
listing -- measured 2026-08-23, a directory path 404s with or without a
trailing slash. `pipeline/sources/gong.py`'s `_scrape_gong` needs an HTML
autoindex, so this mirror manufactures one (`index.html`) in every day
directory it publishes, naming only the files that actually made it across.
`pipeline/config.py`'s `SOL_GONG_PROXY_INDEX` is the other half: it tells
`_relay()` to ask for that filename instead of the bare directory.

WHAT THIS DOES NOT DO. It never rewrites a GONG URL, never gunzips a
magnetogram, and never talks to the relay it feeds -- see the env-hygiene
step in `main()`. The published tree is meant to be read-only, unauthenticated
NSO/GONG data one hop closer to CI; it carries no secret.

USAGE
    python scripts/gong_mirror.py --dry-run --retain-days 2 -v
    python scripts/gong_mirror.py                      # real run (real push)
    python scripts/gong_mirror.py --state-dir D:\\gong-mirror-state

See scripts/gong-mirror-task.ps1 for the Windows Scheduled Task wrapper and
docs/GONG-RELAY.md "Option D" for the full write-up, go-live steps and the
weaknesses of this approach (a sleeping workstation, a 5-minute CDN cache).
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_REMOTE = "https://github.com/astrodavid10/sol-solar-viewer.git"
DEFAULT_BRANCH = "gong-cache"

# WINDOW_HOURS is 72 and gong_list scrapes each pipeline slot's target day
# +/- 1, so the oldest day directory the pipeline EVER touches is ~96 h
# (4 days) back from "now". 5 days of retention is one day of margin over
# that, cheap because a day directory is a few hundred KB.
DEFAULT_RETAIN_DAYS = 5

_LOCK_STALE_SECONDS = 30 * 60

# Populated inside main(), AFTER the env-hygiene step below -- see main() for
# why pipeline.config cannot be imported at module load time.
_FITS_RE = None
_gong_dir_url = None
_scrape_gong = None
GONG_BASE = None


# ── args ─────────────────────────────────────────────────────────────────────

def _parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Mirror NSO/GONG synoptic magnetograms to the "
                    "gong-cache branch (docs/GONG-RELAY.md Option D).")
    p.add_argument("--retain-days", type=int, default=DEFAULT_RETAIN_DAYS,
                    help="Day directories from today-N through today+1 are "
                        "kept; older ones are pruned (default {0}).".format(
                            DEFAULT_RETAIN_DAYS))
    p.add_argument("--state-dir", default=None,
                    help="Working directory holding the local git clone + "
                        "downloaded files. Default: "
                        "%%LOCALAPPDATA%%\\sol-gong-mirror\\repo")
    p.add_argument("--remote", default=DEFAULT_REMOTE,
                    help="git remote URL to publish to (default: this repo).")
    p.add_argument("--branch", default=DEFAULT_BRANCH,
                    help="Branch to force-push (default: {0}).".format(
                        DEFAULT_BRANCH))
    p.add_argument("--dry-run", action="store_true",
                    help="Scrape, download, prune and write files/index as "
                        "usual, but do not commit or push. Prints exactly "
                        "what would be committed and pushed.")
    p.add_argument("--verbose", "-v", action="store_true",
                    help="Print one line per file, not just per day.")
    return p.parse_args(argv)


def _default_state_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "sol-gong-mirror" / "repo"
    # Non-Windows fallback; this script targets a Windows Scheduled Task, but
    # nothing about the mirroring logic below is Windows-specific.
    return Path.home() / ".sol-gong-mirror" / "repo"


# ── locking ──────────────────────────────────────────────────────────────────

def _acquire_lock(lock_path: Path) -> bool:
    """Take the exclusive lock, clearing a stale one first. True on success.

    Two overlapping Scheduled Task runs (a slow scrape plus the next hourly
    tick) must not both write the tree and race a `git add -A` / prune /
    commit against each other.
    """
    if lock_path.exists():
        age_s = time.time() - lock_path.stat().st_mtime
        if age_s > _LOCK_STALE_SECONDS:
            print("lock {0} is {1:.0f} min old (> 30) -- treating the "
                  "previous run as dead and taking it".format(
                      lock_path, age_s / 60.0))
            try:
                lock_path.unlink()
            except OSError:
                pass
        else:
            print("another run holds {0} ({1:.0f} min old) -- exiting "
                  "without touching the mirror".format(lock_path, age_s / 60.0))
            return False
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("lost the race for {0} -- exiting without touching the "
              "mirror".format(lock_path))
        return False
    with os.fdopen(fd, "w") as fh:
        fh.write("{0} {1}\n".format(
            os.getpid(), datetime.now(timezone.utc).isoformat()))
    return True


# ── download ─────────────────────────────────────────────────────────────────

def _download_one(url: str, dest: Path, timeout: float = 60.0
                  ) -> Tuple[bool, Optional[str]]:
    """Fetch one magnetogram VERBATIM (still gzipped), after validating it.

    `pipeline/sources/gong.py`'s own `gong_download()` gunzips before
    caching; this mirror must serve the exact bytes GONG serves, so
    validation happens on a throwaway in-memory decompression and only the
    ORIGINAL gzip bytes are written to disk. A freshly published GONG file is
    often still being written when we fetch it, so a truncated/invalid gzip
    body is NORMAL -- reject it loudly and let next hour's run retry rather
    than raising or silently keeping a bad file.
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": "sol-gong-mirror "
                      "(+https://github.com/astrodavid10/sol-solar-viewer)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as exc:                                    # noqa: BLE001
        return False, "{0}: {1}".format(type(exc).__name__, exc)

    try:
        decompressed = gzip.decompress(raw)
    except OSError as exc:
        return False, ("not a valid gzip stream ({0}) -- likely still being "
                       "published upstream".format(exc))
    if decompressed[:6] != b"SIMPLE":
        return False, ("decompressed body does not start with FITS magic "
                       "'SIMPLE' ({0} byte(s) total)".format(len(decompressed)))

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Process-unique temp file + os.replace: never leave a partial file where
    # a reader (or the next run) could see it.
    tmp = dest.parent / "{0}.{1}.part".format(dest.name, uuid.uuid4().hex)
    try:
        tmp.write_bytes(raw)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return True, None


def _rel_day_dir(day: datetime) -> str:
    return "{0}/mrzqs{1}".format(day.strftime("%Y%m"), day.strftime("%y%m%d"))


def _process_one_day(day: datetime, state_dir: Path, verbose: bool) -> dict:
    """Scrape one day directory, download anything new, refresh its index."""
    dir_url = _gong_dir_url(day)
    listing = _scrape_gong(dir_url)   # [] on ANY failure; _scrape_gong prints why
    dest_dir = state_dir / "oQR" / "zqs" / _rel_day_dir(day)

    added = 0
    rejected = 0
    for _dt, url in listing:
        fname = url.split("/")[-1]
        dest = dest_dir / fname
        if dest.exists() and dest.stat().st_size > 0:
            if verbose:
                print("    have   {0}".format(fname))
            continue
        ok, err = _download_one(url, dest)
        if ok:
            added += 1
            if verbose:
                print("    added  {0}".format(fname))
        else:
            rejected += 1
            print("    REJECT {0}: {1}".format(fname, err))

    n_present = _write_index(dest_dir, dir_url)
    print("  {0}  {1:2d} listed  {2:2d} present  {3:2d} new  {4:2d} rejected  "
          "{5}".format(day.strftime("%Y-%m-%d"), len(listing), n_present,
                       added, rejected, dir_url))
    return {"day": day.strftime("%Y-%m-%d"), "listed": len(listing),
            "present": n_present, "added": added, "rejected": rejected}


# ── synthetic autoindex ──────────────────────────────────────────────────────

def _write_index(dest_dir: Path, canonical_dir_url: str) -> int:
    """(Re)write a synthetic autoindex naming only files actually mirrored.

    Bare relative filenames only -- NEVER an absolute URL. `_scrape_gong`
    builds `full = href if href.startswith("http") else dir_url + fname`
    from the CANONICAL `dir_url` it was passed (verified by reading
    pipeline/sources/gong.py). An absolute href here would make that
    provenance URL -- which becomes the cache key AND the manifest citation
    -- point at raw.githubusercontent.com instead of gong2.nso.edu.

    Also: list only what actually landed. A listing naming a file that isn't
    really here makes the pipeline pick a "nearest" magnetogram it then can't
    download, resolving a slot to nothing instead of falling back cleanly.
    """
    if not dest_dir.exists():
        # Nothing has ever been mirrored for this day -- do not manufacture
        # an empty directory just to hold an empty index.
        return 0
    names = sorted(p.name for p in dest_dir.glob("*.fits.gz"))
    if not names:
        return 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "<!-- Mirror of NSO/GONG synoptic magnetograms (gong2.nso.edu). -->",
        "<!-- Source directory: {0} -->".format(canonical_dir_url),
        "<!-- Mirrored (UTC): {0} -->".format(now),
        "<!-- Generated by scripts/gong_mirror.py -- do not edit by hand. -->",
        "<html><body>",
    ]
    lines.extend('<a href="{0}">{0}</a>'.format(name) for name in names)
    lines.append("</body></html>")
    tmp = dest_dir / ".index.html.{0}.part".format(uuid.uuid4().hex)
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, dest_dir / "index.html")
    return len(names)


# ── prune ────────────────────────────────────────────────────────────────────

_DAY_DIRNAME_RE = re.compile(r"^mrzqs(\d{6})$")


def _prune(state_dir: Path, window_start: datetime, window_end: datetime
          ) -> Tuple[int, int]:
    """Delete day directories (and their files) outside the retention window.

    Returns (day_dirs_pruned, files_pruned).
    """
    root = state_dir / "oQR" / "zqs"
    if not root.exists():
        return 0, 0
    start_date = window_start.date()
    end_date = window_end.date()
    dirs_pruned = 0
    files_pruned = 0
    for month_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for day_dir in sorted(p for p in month_dir.iterdir() if p.is_dir()):
            m = _DAY_DIRNAME_RE.match(day_dir.name)
            if not m:
                continue     # not ours (e.g. a stray index/status file); leave it
            yymmdd = m.group(1)
            try:
                d = datetime(2000 + int(yymmdd[:2]), int(yymmdd[2:4]),
                            int(yymmdd[4:6]), tzinfo=timezone.utc).date()
            except ValueError:
                continue
            if d < start_date or d > end_date:
                n = sum(1 for _ in day_dir.glob("*.fits.gz"))
                shutil.rmtree(day_dir)
                dirs_pruned += 1
                files_pruned += n
                print("  pruned {0} ({1} file(s), outside the {2}..{3} "
                      "retention window)".format(day_dir, n, start_date, end_date))
        if month_dir.exists() and not any(month_dir.iterdir()):
            month_dir.rmdir()
    return dirs_pruned, files_pruned


# ── heartbeat ────────────────────────────────────────────────────────────────

def _write_status(state_dir: Path, retain_days: int, added: int, pruned: int,
                  rejected: int, now: datetime) -> dict:
    """Write mirror-status.json at the BRANCH ROOT -- never inside oQR/, so it
    can never collide with a real GONG path."""
    root = state_dir / "oQR" / "zqs"
    total_files = 0
    total_bytes = 0
    newest_dt: Optional[datetime] = None
    days: Dict[str, int] = {}
    if root.exists():
        for day_dir in root.glob("*/mrzqs*"):
            n = sum(1 for _ in day_dir.glob("*.fits.gz"))
            if n:
                days[day_dir.name] = n
        for f in root.rglob("*.fits.gz"):
            total_files += 1
            total_bytes += f.stat().st_size
            m = _FITS_RE.match(f.name)
            if not m:
                continue
            d, t = m.group(1), m.group(2)
            try:
                file_dt = datetime(2000 + int(d[:2]), int(d[2:4]), int(d[4:6]),
                                   int(t[:2]), int(t[2:]), tzinfo=timezone.utc)
            except ValueError:
                continue
            if newest_dt is None or file_dt > newest_dt:
                newest_dt = file_dt

    status = {
        "generated_iso": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "retain_days": retain_days,
        "days": days,
        "total_files": total_files,
        "total_bytes": total_bytes,
        "newest_file_iso": (newest_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                           if newest_dt else None),
        "added_this_run": added,
        "pruned_this_run": pruned,
        "rejected_this_run": rejected,
        "source": "NSO/GONG synoptic magnetograms, gong2.nso.edu/oQR/zqs -- "
                  "see docs/GONG-RELAY.md Option D. Generated by "
                  "scripts/gong_mirror.py; do not edit by hand.",
    }
    tmp = state_dir / ".mirror-status.json.{0}.part".format(uuid.uuid4().hex)
    tmp.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, state_dir / "mirror-status.json")
    return status


# ── git ──────────────────────────────────────────────────────────────────────

def _git(state_dir: Path, *args: str, env: Optional[dict] = None,
        check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["git", "-C", str(state_dir)] + list(args)
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError("git {0} failed (exit {1}): {2}".format(
            " ".join(args), result.returncode,
            (result.stderr or result.stdout).strip()))
    return result


def _git_env() -> dict:
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "sol-bot")
    env.setdefault("GIT_AUTHOR_EMAIL", "sol-bot@users.noreply.github.com")
    env["GIT_COMMITTER_NAME"] = env["GIT_AUTHOR_NAME"]
    env["GIT_COMMITTER_EMAIL"] = env["GIT_AUTHOR_EMAIL"]
    return env


def _ensure_local_repo(state_dir: Path, remote_url: str) -> None:
    """git init + remote add, nothing more. No `git clone` of `main` --
    the mirror only ever needs an empty tree plus the files it downloads
    itself; cloning the app's history would be pure waste."""
    if not (state_dir / ".git").exists():
        _git(state_dir, "init", "-q")
        print("initialized local git repo at {0}".format(state_dir))
    gitignore = state_dir / ".gitignore"
    if not gitignore.exists():
        # The lock file and any interrupted temp write are LOCAL run state,
        # not mirror content -- `git add -A` would otherwise happily commit
        # `.mirror.lock` (caught by inspecting a real dry-run diff) and any
        # `*.part` left behind by a killed run.
        gitignore.write_text(".mirror.lock\n*.part\n", encoding="utf-8")
    existing = _git(state_dir, "remote", "get-url", "origin", check=False)
    if existing.returncode != 0:
        _git(state_dir, "remote", "add", "origin", remote_url)
    elif existing.stdout.strip() != remote_url:
        _git(state_dir, "remote", "set-url", "origin", remote_url)


def _stage_and_commit(state_dir: Path, message: str, dry_run: bool) -> bool:
    """git add -A, then commit. Returns whether there was anything to commit.

    The commit AMENDS the one existing commit (when there is one) instead of
    adding a new one on top, so the local repo -- like the remote branch --
    never grows history: `docs/GONG-RELAY.md`'s Option D and
    `scripts/publish_gh_pages.sh` both keep exactly one commit, by design.
    """
    _git(state_dir, "add", "-A")
    diff = _git(state_dir, "diff", "--cached", "--quiet", check=False)
    has_changes = diff.returncode != 0
    if not has_changes:
        return False

    if dry_run:
        stat = _git(state_dir, "diff", "--cached", "--stat").stdout
        print("would commit ({0}):".format(message))
        print(stat.rstrip("\n"))
        # Leave no trace across repeated dry runs. Works whether or not a
        # commit exists yet (an unborn branch has nothing for `git reset` to
        # restore to); either way the next real run re-stages from the
        # working tree regardless, so failure here is harmless.
        _git(state_dir, "reset", check=False)
        return True

    env = _git_env()
    head = _git(state_dir, "rev-parse", "-q", "--verify", "HEAD", check=False)
    if head.returncode == 0:
        _git(state_dir, "commit", "--amend", "-q", "-m", message, env=env)
    else:
        _git(state_dir, "commit", "-q", "-m", message, env=env)
    return True


def _get_gh_token() -> Optional[str]:
    try:
        result = subprocess.run(["gh", "auth", "token"],
                                capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    token = result.stdout.strip()
    return token or None


def _push(state_dir: Path, branch: str) -> None:
    """Force-push HEAD to `branch`. Never prints the token."""
    token = _get_gh_token()
    if token:
        basic = base64.b64encode(
            "x-access-token:{0}".format(token).encode("ascii")).decode("ascii")
        header = "AUTHORIZATION: basic {0}".format(basic)
        # -c http.extraheader is scoped to THIS invocation only, never written
        # to .git/config or the reflog -- the same approach GitHub Actions'
        # own checkout uses.
        _git(state_dir, "-c", "http.extraheader={0}".format(header),
            "push", "-q", "--force", "origin", "HEAD:{0}".format(branch))
        print("pushed to origin/{0} (authenticated via `gh auth token`)".format(
            branch))
    else:
        print("`gh auth token` unavailable -- falling back to a plain "
              "`git push` (Windows Credential Manager / "
              "credential.helper=manager will be asked to authenticate)")
        _git(state_dir, "push", "-q", "--force", "origin", "HEAD:{0}".format(branch))
        print("pushed to origin/{0}".format(branch))


# ── main ─────────────────────────────────────────────────────────────────────

def _day_range(now: datetime, retain_days: int) -> List[datetime]:
    """UTC dates from today-retain_days through today+1, inclusive."""
    start = (now - timedelta(days=retain_days)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    end = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def main(argv: Optional[List[str]] = None) -> int:
    # Env hygiene, BEFORE any import of pipeline.config: this mirror is the
    # thing SOL_GONG_PROXY_BASE would eventually point AT once deployed. If
    # it inherited that variable from the environment (e.g. a workstation
    # that also has the pipeline's env vars set for local testing), it would
    # relay its own GONG fetches through itself -- pipeline.config reads
    # these once, at import time, so clearing must happen first.
    for var in ("SOL_GONG_PROXY_BASE", "SOL_GONG_PROXY_TOKEN",
               "SOL_GONG_PROXY_INDEX"):
        os.environ.pop(var, None)

    global _FITS_RE, _gong_dir_url, _scrape_gong, GONG_BASE
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    # Reuse, don't reinvent: `_FITS_RE`/`_gong_dir_url`/`_scrape_gong` are the
    # pipeline's own filename convention and scrape implementation, so there
    # is exactly ONE of each in the repo. They are `_`-prefixed (private to
    # pipeline/sources/gong.py) -- imported anyway; duplicating a regex that
    # encodes GONG's filename convention is the worse of the two options.
    from pipeline.config import GONG_BASE as _gb
    from pipeline.sources.gong import (_FITS_RE as _fr, _gong_dir_url as _gdu,
                                       _scrape_gong as _sg)
    _FITS_RE, _gong_dir_url, _scrape_gong, GONG_BASE = _fr, _gdu, _sg, _gb

    args = _parse_args(argv)
    state_dir = Path(args.state_dir) if args.state_dir else _default_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    lock_path = state_dir / ".mirror.lock"
    if not _acquire_lock(lock_path):
        print("SUMMARY: skipped -- another run holds the lock")
        return 0

    try:
        now = datetime.now(timezone.utc)
        days = _day_range(now, args.retain_days)
        print("gong_mirror: window {0}..{1} ({2} day dir(s)), state={3}".format(
            days[0].strftime("%Y-%m-%d"), days[-1].strftime("%Y-%m-%d"),
            len(days), state_dir))
        if args.dry_run:
            print("(--dry-run: will scrape/download/prune for real, but "
                  "will not commit or push)")

        day_results = [_process_one_day(day, state_dir, args.verbose)
                      for day in days]
        total_added = sum(r["added"] for r in day_results)
        total_rejected = sum(r["rejected"] for r in day_results)

        dirs_pruned, files_pruned = _prune(state_dir, days[0], days[-1])

        status = _write_status(state_dir, args.retain_days, total_added,
                               files_pruned, total_rejected, now)

        _ensure_local_repo(state_dir, args.remote)
        message = "gong-cache mirror @ {0} -- {1} file(s) across {2} day(s)".format(
            status["generated_iso"], status["total_files"], len(status["days"]))
        has_changes = _stage_and_commit(state_dir, message, args.dry_run)

        if not has_changes:
            print("no change, not pushing")
        elif args.dry_run:
            print("dry-run: would force-push HEAD to {0} ({1}:{2})".format(
                args.remote, "HEAD", args.branch))
        else:
            _push(state_dir, args.branch)

        # Reachability: today's and yesterday's directories almost always
        # carry at least one file when GONG is up (GONG publishes several
        # times a day); today+1 being empty is NORMAL (it hasn't happened
        # yet) and must not count against reachability.
        today_str = now.strftime("%Y-%m-%d")
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        recent = [r for r in day_results if r["day"] in (today_str, yesterday_str)]
        reachable = (not recent) or any(r["listed"] > 0 for r in recent)

        newest_age_h = None
        if status["newest_file_iso"]:
            newest_dt = datetime.strptime(
                status["newest_file_iso"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            newest_age_h = (now - newest_dt).total_seconds() / 3600.0

        if not reachable:
            print("SUMMARY: FAILURE -- GONG appears unreachable from this "
                  "machine (0 files listed for today/yesterday); mirror "
                  "still holds {0} file(s) from earlier runs, newest "
                  "{1}".format(
                      status["total_files"],
                      "{0:.1f} h old".format(newest_age_h)
                      if newest_age_h is not None else "unknown"))
            return 1
        if status["total_files"] == 0:
            print("SUMMARY: FAILURE -- mirror holds zero files after this run")
            return 1

        print("SUMMARY: OK -- {0} file(s) present, newest {1:.1f} h old, "
              "+{2}/-{3} added/pruned this run ({4} rejected)".format(
                  status["total_files"], newest_age_h, total_added,
                  files_pruned, total_rejected))
        return 0
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:                                       # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
