# Getting GONG data into CI

**Status (2026-09-02): Option D is LIVE.** The `gong-cache` branch exists and is
fed hourly by the `SolGongMirror` Scheduled Task on the workstation; the two
repository secrets are set; see "Live configuration" at the end of the Option D
section for exactly what is deployed and how to check it. Option A (the
Cloudflare Worker) remains written and undeployed as the upgrade path that would
take the workstation out of the critical path. Footgun 33 still describes the
underlying block — NSO drops GitHub's runners — it is just routed around now.

## The problem, precisely

`gong2.nso.edu` **times out on every request from a GitHub Actions runner**, and
always has. Measured across four consecutive `data.yml` runs on 2026-08-23: all
12 day-directory scrapes failed with `URLError: <urlopen error timed out>`,
resolving 0 of 19 slots. The identical request from a workstation answers
HTTP 200 in 0.35 s.

It is **not** IPv6 (footgun 24's cause) — `gong2.nso.edu` publishes no AAAA
record at all. It is not a block-with-a-response either: a 403 or a TLS error
would arrive fast, and a silent drop is what times out. Every *other* upstream
works from the same runner in the same run (JPL Horizons, CCMC DONKI, NOAA
SWPC, SDO GSFC), so this is NSO-side and specific to their firewall's view of
Azure/GitHub ranges.

## What was ruled out, by measurement

Investigated 2026-08-23. **There is no free upstream mirror.** Every option was
probed, not assumed:

| Candidate | Verdict |
|---|---|
| `gong.nso.edu`, `nispdata.nso.edu`, `magmap.nso.edu`, `solis.nso.edu` | All CNAME/resolve to **146.5.21.69**, the same address as `gong2` — one host, one firewall. A hostname mirror cannot help. |
| Anonymous **FTP** on `gong2.nso.edu` | Works from a workstation and returns a **byte-identical** file (sha256 confirmed) — but same IP, so same firewall. |
| sunpy **VSO** `GONGClient` | Provably a wrapper around the same blocked host: `sunpy/net/dataretriever/sources/gong.py` returns `https://gong2.nso.edu/oQR/zqs` as its base URL. |
| **JSOC** / Stanford | Reachable, but carries **zero GONG series** — HMI and AIA only. The one "gong" hit is `hmi.fsVbinned_nrt`, HMI data *used for* far-side comparison. |
| **Helioviewer** | Carries only **GONG H-alpha** (6562 Å chromosphere images). That is a different physical observable, not a synoptic magnetogram — ruled out on physics, not on format. |
| **NOAA NCEI** `gong_oQR` archive | Its own landing page says the dataset "is not currently available for public download from NCEI"; access is by email request. Not automatable. |
| `nso.edu` / `www.nso.edu` | On a *different* address (50.6.111.190) and reachable — but serves the general website, no data. |
| **LMSAL** `fieldlines-*.json` | A precomputed field-line product, not the raw magnetogram. Swapping to it changes the model input and breaks parity with the dome show. |
| **fly.io** free tier | Discontinued for new accounts since Oct 2024. |

So the fix has to be a **relay from a network NSO does not block**.

## What is already in the repo

The seam is done and needs no further code:

- `pipeline/config.py` reads `SOL_GONG_PROXY_BASE` and `SOL_GONG_PROXY_TOKEN`
  from the environment. Empty means "no relay", which is today's behavior.
- `pipeline/sources/gong.py` rewrites GONG URLs onto the relay **at request time
  only** (`_relay`). Cache keys, the published manifest and every log line keep
  citing `gong2.nso.edu`, because NSO is the actual source — and because a
  relay swap must not invalidate the traced-frame cache.
- `scripts/gong-proxy-worker.js` + `scripts/wrangler.toml` — a ready-to-deploy
  Cloudflare Worker.
- `pipeline probe-sources` reports whether a relay is configured and whether it
  works, so CI turns "should work" into evidence.

## Option A (recommended): Cloudflare Worker

Lowest effort, fully reversible, adds no always-on host, and does not touch the
repo's CI trust boundary. Cloudflare's edge is a different address space from
the Azure ranges GitHub's hosted runners use, so a block aimed at those ranges
should not apply — *should*, which is why the probe exists.

Free tier is 100,000 requests/day. This pipeline needs roughly 10 per run and
6 runs a day, at ~240 KB per magnetogram. Not close to any limit.

```bash
npm install -g wrangler
wrangler login
cd scripts && wrangler deploy
wrangler secret put RELAY_TOKEN        # paste a long random string
```

Then add two **repository secrets** (Settings → Secrets and variables →
Actions):

| Secret | Value |
|---|---|
| `SOL_GONG_PROXY_BASE` | `https://sol-gong-relay.<your-subdomain>.workers.dev/oQR/zqs` |
| `SOL_GONG_PROXY_TOKEN` | the same random string |

`data.yml` already passes both into every pipeline step. Verify with:

```
gh workflow run data.yml -f dry_run=true
```

and read the `[GONG]` block in the `probe-sources` output. A successful listing
there is the proof; anything else and the relay is being blocked too.

The worker restricts itself deliberately — it requires the shared secret, and it
only forwards the two URL shapes the pipeline actually asks for (a day listing
and one `mrzqs*.fits.gz`). A service that already firewalls a whole cloud
provider does not need an open proxy pointed at it. Responses are edge-cached
(10 min for listings, 1 day for the immutable FITS files), so retries and
re-runs cost NSO nothing.

## Option B (fallback): a self-hosted runner at the planetarium

Highest confidence — it is the same network path that already works from a
workstation — and fully under our control. It also removes the hosted-runner job
time cap. Two real costs:

1. An always-on machine that must be patched and online for every 4 h tick.
2. **The repo is public.** GitHub warns against self-hosted runners on public
   repos, because a workflow triggered from a fork PR can execute arbitrary code
   on the runner. Mitigate deliberately: scope the runner label to the
   `schedule`-triggered `data.yml` only, never to any `pull_request` trigger,
   and keep fork-PR approval required. This has to be configured on purpose,
   not registered and forgotten.

## Option C (parallel, free): ask NSO to allow-list GitHub's ranges

Worth sending regardless — it is the cleanest outcome if honored, and costs
nothing to ask. Caveat: GitHub's published IP ranges rotate, so even a granted
allow-list needs upkeep. Do not wait on it.

## Option D (fallback, no Cloudflare account needed): a static mirror on this repo

Same idea as Option A — relay from a network NSO does not block — but the
relay is a **git branch of this repo**, fed by an hourly Windows Scheduled
Task on a workstation that can already reach `gong2.nso.edu`, and served to
CI over `raw.githubusercontent.com`. Useful when nobody wants to hold a
Cloudflare account, or as a second, independent path if the Worker's account
ever lapses.

**Why a static host qualifies at all.** `_relay()` in
`pipeline/sources/gong.py` rewrites `GONG_BASE/<path>` to
`PROXY_BASE/<path>` — nothing more. It has no opinion about what serves
`PROXY_BASE`; a Cloudflare Worker that fetches NSO live and a static file
tree that already contains the bytes are equally valid, as long as the
path shape lines up. `raw.githubusercontent.com/<org>/<repo>/<branch>/<path>`
preserves the path exactly the way the Worker's route does, so pointing
`SOL_GONG_PROXY_BASE` at
`https://raw.githubusercontent.com/astrodavid10/sol-solar-viewer/gong-cache/oQR/zqs`
is a drop-in swap.

**The directory-404 gap, and the knob it forced.** `raw.githubusercontent.com`
serves files, never directory listings. Measured 2026-08-23:

```
.../gong-cache/oQR/zqs/<...>/ (trailing slash)  -> 404
.../gong-cache/oQR/zqs/<...>  (no trailing slash) -> 404
.../gong-cache/oQR/zqs/<...>/<real file>          -> 200
```

But `_gong_dir_url()` always builds `GONG_BASE/<YYYYMM>/mrzqs<YYMMDD>/` — a
directory, because `_scrape_gong` needs an HTML autoindex to parse, and
`gong2.nso.edu` happily serves one. A static mirror can only answer that by
publishing a real file at a real path: it writes a synthetic `index.html`
into every day directory (naming only the `.fits.gz` files actually
mirrored — never inventing an entry the pipeline could then fail to
download), and `SOL_GONG_PROXY_INDEX` (e.g. `index.html`) tells `_relay()`
to append that filename whenever a relayed URL ends in `/`. Unset (the
Option A / Worker case, since a Worker fetches NSO live and returns whatever
NSO returns), behavior is byte-identical to before this knob existed. The
appended name is a request-time detail only — same rule as the relay
rewrite itself — and never reaches a cache key or the published manifest.

**Repository secrets** (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `SOL_GONG_PROXY_BASE` | `https://raw.githubusercontent.com/astrodavid10/sol-solar-viewer/gong-cache/oQR/zqs` |
| `SOL_GONG_PROXY_INDEX` | `index.html` |
| `SOL_GONG_PROXY_TOKEN` | **leave unset.** `raw.githubusercontent.com` needs no shared secret to read a public branch, so there is nothing to authenticate with the token for — and setting one would be silently ignored (`_relay_headers()` only attaches it, it never gates on it). The consequence is real and deliberate: the `gong-cache` branch is **publicly readable**. That is fine — GONG's data is public and NSO already serves it to anyone — and the bandwidth CI consumes reading it is GitHub's, not NSO's. |

The Scheduled Task itself needs no repository secret at all: it authenticates
its push with `gh auth token` (falling back to whatever the Windows
credential manager already has configured for `git push`), read from the
account that registered the task, never written to a file or the reflog.
**"Never written to a file" was false until `85e626c`:** `_git`'s error
message was built from `" ".join(args)`, and `_push` passes the credential as
an `http.extraheader=` argument, so any failed push wrote a decodable token
straight into the Scheduled Task log. `_redact_args`/`_redact_text` are what
make the sentence true now — do not restore the plain join. The same commit
made the mirror **refuse to push when its state dir holds zero files**: before
it, a fresh or wiped `%LOCALAPPDATA%` would have force-pushed an EMPTY tree over
a good branch and only then printed FAILURE (the mirror-side twin of footgun
31), and the state repo now carries `* -text` in `.gitattributes` because Git
for Windows' SYSTEM config sets `core.autocrlf=true` and the mirror's contract
is byte-verbatim.

**What was measured, 2026-08-23/24, `--retain-days 5` (the default):**

- Cadence: GONG publishes roughly hourly, with real gaps — a `--dry-run`
  against the live site saw 18–24 files per day directory in August and
  23–24 on every complete day measured 2026-09-02 (`GONG_TOLERANCE_HOURS
  = 3.0` in `pipeline/config.py` already assumes gaps this size are normal).
- One magnetogram is ~237 KiB (`242,785`–`243,382` bytes observed).
- A full 5-day retention window (7 day directories: today−5 .. today+1;
  the last one is the FUTURE and 404s outright, which shows up in every run's
  log as `WARN GONG …/mrzqs<tomorrow>/: HTTP 404 Not Found` — normal, not a
  fault) mirrored **135 files, 32,817,395 bytes (31.3 MB)** end to end in
  **61 s** cold, 2 s warm (re-measured 2026-09-02; August's first measurement
  was 109 files / 25.3 MB).
- **Why `--retain-days 5` and not fewer.** It is not a free parameter.
  `WINDOW_HOURS = 72` back from `snap_down(now)` puts the oldest slot target on
  `today−3`, and `gong_list` scrapes each target's day ±1, so the pipeline can
  ask for **`today−4`**. 4 is exact, 5 is one day of margin, and **3 leaves a
  hole that reads in CI as `0 file(s)` — indistinguishable from GONG being
  down.** If `WINDOW_HOURS` ever grows, retain-days must grow with it;
  `pipeline/tests/test_gong_mirror.py::test_default_retention_covers_every_day_the_pipeline_scrapes`
  fails loudly if they drift apart.
- `raw.githubusercontent.com` answers `Cache-Control: max-age=300` on branch
  content (measured against this same repo's `main` branch) — so a file the
  mirror just pushed can be **up to ~5 minutes** invisible to a CI run that
  asks a CDN edge that already cached the previous version.

**Honest weaknesses, not glossed over:**

- This whole option depends on a specific workstation being powered on,
  logged in enough for its credential stores to be reachable (see
  `scripts/gong-mirror-task.ps1`'s header comment on why the Scheduled Task
  needs a stored password rather than the password-less S4U logon type),
  and network-reachable to both NSO and GitHub every hour. Option A's Worker
  has none of those dependencies; treat Option D as the fallback it is.
- The ~5 minute CDN cache above is on top of the mirror's own hourly cadence
  — call it up to ~65 minutes between a fresh GONG file existing and CI
  being able to see it through this path, against Option A's effectively
  live relay.
- The published branch has no history (single amended commit, same
  reasoning as `gh-pages` — see `scripts/publish_gh_pages.sh`), so there is
  no way to recover "what did the mirror look like an hour ago" after the
  fact; `mirror-status.json` at the branch root is the only run-to-run record,
  and it only reflects the most recent push.

**Go live:**

```powershell
# One-time: create the branch with a real push (this repo's maintainer only --
# scripts/gong_mirror.py itself never pushes without being told to).
python scripts/gong_mirror.py --retain-days 5

# Repository secrets (see table above):
gh secret set SOL_GONG_PROXY_BASE  --body "https://raw.githubusercontent.com/astrodavid10/sol-solar-viewer/gong-cache/oQR/zqs"
gh secret set SOL_GONG_PROXY_INDEX --body "index.html"

# Register the hourly Scheduled Task -- see scripts/gong-mirror-task.ps1's
# header comment for the exact command (it prompts for your Windows password).

# Prove it end-to-end:
gh workflow run data.yml -f dry_run=true
# then read the [GONG] block in the probe-sources log: "via relay ... directory
# index: index.html" plus a real file listing is the proof.
```

### Live configuration (deployed 2026-09-02)

| piece | value |
|---|---|
| Branch | `gong-cache`, single amended commit, first pushed 2026-09-02 17:50Z with 136 files (27 stale files from an August test dir pruned on the way) |
| Read path from CI | `https://raw.githubusercontent.com/astrodavid10/sol-solar-viewer/gong-cache/oQR/zqs/<YYYYMM>/mrzqs<YYMMDD>/index.html` → 200, 18 files listed for 2026-09-02 at deploy time; a FITS `HEAD` → 200, `Content-Length: 243016`, `Cache-Control: max-age=300` |
| Repository secrets | `SOL_GONG_PROXY_BASE` = `https://raw.githubusercontent.com/astrodavid10/sol-solar-viewer/gong-cache/oQR/zqs`; `SOL_GONG_PROXY_INDEX` = `index.html`; `SOL_GONG_PROXY_TOKEN` deliberately **unset** |
| Scheduled Task | `SolGongMirror`, hourly (`-Once` + 1 h repetition, indefinite), `-StartWhenAvailable`, `MultipleInstances IgnoreNew`, 30 min execution limit, `RunLevel Limited`. **Registered for the INTERACTIVE logon with no stored password** — it runs while this user is logged on (a locked screen counts), and pauses when logged off. To upgrade to run-when-logged-off, re-register with `-User "$env:USERDOMAIN\$env:USERNAME" -Password '<yours>'` per the ps1 header. Note: `-RepetitionDuration ([TimeSpan]::MaxValue)` is REJECTED on this Windows 11 build; omit it. |
| Interpreter | `C:\Users\adavi\anaconda3\envs\sdo\python.exe` (3.12), chosen by the ps1's `Test-Path`; the PATH fallback (`anaconda3\python.exe`, 3.8) is also verified to work |
| State dir / logs | `%LOCALAPPDATA%\sol-gong-mirror\repo` / `%LOCALAPPDATA%\sol-gong-mirror\logs\` (last 15 runs) |
| Check it | `Get-ScheduledTaskInfo SolGongMirror` (LastTaskResult 0), the newest log's `SUMMARY:` line, `git ls-remote --heads origin gong-cache`, and in a `data.yml` log the `[GONG]` probe block reading `via relay … directory index: index.html` followed by a real listing and `slots: N/19` |

Known, accepted: every run pushes (two timestamps change each run, so "no
change" is effectively dead code — a harmless heartbeat); ~24 unreachable
243 KB blobs a day accumulate in the branch's object store as the single
commit is amended, the same property gh-pages already has; a PARTIALLY wiped
state dir (a few files) still pushes, because the zero-file refusal cannot tell
that from a legitimate cold start without fetching the remote first.

## What NOT to do

- **Do not lower `MIN_FRAMES_TO_PUBLISH`** to make the stage "pass". The soft
  failure policy is correct for a transient outage and actively misleading for a
  permanent block; weakening the threshold would publish a near-empty field-line
  product and call it success.
- **Do not remove footgun 31's `dist-data` seeding** in `data.yml`. It is the
  only thing stopping `rsync --delete` from removing the hand-published frames
  on every GONG outage.
