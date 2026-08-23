# Getting GONG data into CI

**Status:** the code seam is in and tested; the relay itself needs one deploy
step that only an account holder can do. Until it is deployed, the scheduled
pipeline still cannot build field lines — see `CLAUDE.md` footgun 33.

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

## What NOT to do

- **Do not lower `MIN_FRAMES_TO_PUBLISH`** to make the stage "pass". The soft
  failure policy is correct for a transient outage and actively misleading for a
  permanent block; weakening the threshold would publish a near-empty field-line
  product and call it success.
- **Do not remove footgun 31's `dist-data` seeding** in `data.yml`. It is the
  only thing stopping `rsync --delete` from removing the hand-published frames
  on every GONG outage.
