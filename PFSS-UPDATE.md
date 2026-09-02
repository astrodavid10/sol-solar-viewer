# Refreshing and republishing PFSS by hand

**Who this is for.** Any fresh session — including a small model — that finds the live site
reporting `pfss` **stale** and needs to fix it. It is a *runbook*: follow it top to bottom, copy
the commands, check the stated expectation at each step. No step needs you to read the pipeline
source or make a judgement call about the science. The one judgement call is step 4's texture
decision, and it comes with a check and a stated rule.

**Why this exists at all.** GitHub Actions runners cannot reach `gong2.nso.edu` — connect
timeouts on every request, every run, while the identical request from this workstation answers
in under a second (`CLAUDE.md` footgun 33). The scheduled pipeline therefore rebuilds every
*other* product on time and never traces a single field line, so `pfss` went stale roughly once
a day until the GONG relay (`TASKS.md` T2) went live on **2026-09-02**. Republishing from a
machine that *can* reach GONG was the standing workaround — task **T1**, done by hand ten times
— and is now the FALLBACK for when the relay's workstation mirror is down. See the closing
paragraph for how to tell the difference before you start.

**Time:** ~20 minutes if the sphere textures need rebuilding (~12 min of pipeline), ~12 minutes
if they do not (~5 min). Step 4 decides which, and right after a CI run it is usually the
shorter one.
**Where:** this workstation (`C:\Users\adavi\Documents\DataStories\sol`), Git Bash. Any machine
that can reach GONG would do; a GitHub runner cannot.

---

## 0. Preconditions

```bash
cd /c/Users/adavi/Documents/DataStories/sol
git status --porcelain          # expect EMPTY — a hand-publish should not carry local edits
gh auth status                  # must be logged in; step 6 needs `gh auth token`
ls "$USERPROFILE/anaconda3/envs/sdo/python.exe"   # the conda env the pipeline needs
```

Set these once per shell — every later step uses them:

```bash
PY="$USERPROFILE/anaconda3/envs/sdo/python.exe"
SITE=https://astrodavid10.github.io/sol-solar-viewer
REPO=astrodavid10/sol-solar-viewer
LOG=/tmp/pipeline-pfss.log      # any writable path; see trap (c) in step 4
```

---

## 1. Confirm the refresh is actually needed

```bash
curl -s "$SITE/data/index.json" | python -c "
import sys, json, datetime
d = json.load(sys.stdin)
now = datetime.datetime.now(datetime.timezone.utc)
gen = datetime.datetime.fromisoformat(d['generated_iso'].replace('Z', '+00:00'))
print('index generated', d['generated_iso'], '->', round((now - gen).total_seconds() / 3600, 1), 'h ago')
print('last_attempt_status:', d['last_attempt_status'])
for k, v in sorted(d['products'].items()):
    print(' ', k.ljust(15), v['status'].ljust(6), 'age', round(v.get('age_hours', -1), 2), v.get('note', ''))
"
```

**Refresh if** `pfss` says `stale`, usually with the note
`0 freshly traced frame(s) of 19 slot(s)`. That note is the signature of the GONG block: CI
tried, reached nothing, and kept serving the frames a workstation published last time.

Since 2026-09-02 (T20) you will usually learn this from GitHub rather than from this check:
every scheduled `data` run whose `Verdict` step sees `pfss` stale comes out **red** and adds a
comment to the open issue `data pipeline: scheduled run failing`, and `freshness.yml` opens
`live data is stale` once the live field-line data passes 12 h. A red `data` run is therefore
NOT a discarded publish any more — the other five products were published — it is this chore
asking to be done.

Note the *index* age too. If the whole index is hours old, either the last scheduled run failed
**or the cron never fired** — step 2 tells you which, so do not assume a bug. Either way
**every** product is stale, not just PFSS, and step 4 rebuilds all of them.

**A 4 h schedule does not mean six runs a day.** GitHub delays cron *and drops slots entirely*.
Measured 2026-08-31: `data` ran at 19:16Z and 22:39Z on the 30th, then 05:20Z and 16:06Z on the
31st — four runs against six slots, every one `success`, leaving a **10.8 h** gap in the index
that looked exactly like a failure and was not one.

---

## 2. Check nothing is in flight on GitHub

A hand-publish is **not** in the `gh-pages-publish` concurrency group that serializes the two
workflows, so it can race a CI publish force-pushing the same orphan branch. Both lists must be
empty:

```bash
gh run list --status in_progress
gh run list --status queued
gh run list --limit 5             # context: did the last scheduled `data` run pass?
grep -n cron .github/workflows/data.yml   # "7 */4 * * *" -> 00:07, 04:07, 08:07 ... UTC
```

**Finding out what a failed run actually failed on:** ask for the *steps*, not the log —

```bash
gh run view <run-id> --json jobs --jq '.jobs[].steps[] | select(.conclusion=="failure") | .name'
```

`gh run view --log-failed` is misleading here: the `Probe upstreams (never fatal)` step exits 1
on every run (GONG times out from a runner, footgun 33) and is `continue-on-error`, so it is what
`--log-failed` prints while the real failure — `Validate`, every time so far — is somewhere in
the full log. Grep the full log for `FAIL` once you know the step.

If something is running, wait for it and re-check. Check `--status queued` **explicitly** — a
run can sit queued for a day and the plain `gh run list` top-5 will not show it. GitHub's cron
also fires late routinely (an hour is normal), so "the schedule says 08:07" is not proof that
nothing is about to start. If the next cron slot is only a few minutes away, either publish now
(the push takes well under a minute) or wait for that run to finish and publish after it.

**If the last `data` run FAILED at `Validate` with
`FAIL ar_index within regions.json bounds -- range [-1,N] vs N regions`,** that is not a separate
bug to chase. The published field lines were seeded on a day when NOAA listed more active regions
than it lists now, so the frozen seed set points past the end of the current `regions.json`.
Rebuilding PFSS re-seeds against today's region list and clears it — a stale-PFSS *symptom*, and
this runbook is the fix.

It has now happened **three times** — 2026-08-28 11:12Z, 2026-08-28 22:12Z and 2026-08-30
05:12Z, all with the identical `range [-1,5] vs 5 regions` — and each time a republish cleared
it. So it is the normal *end state* of stale PFSS (footgun 50), not a novelty: expect it a day
or two after the last republish. **Until 2026-09-02** it also discarded the five products CI
*can* build, because `Validate` ran before `Publish`; since T20 the pipeline validates each
product itself before promoting and rolls back only the failing one, `data.yml` publishes
first and validates after as a tripwire, and the manifest carries `seed_regions` so a shrunken
SRS list is a WARN rather than a FAIL. A `data` run that goes red now still publishes what it
could — read the `Verdict` step's table to see which product degraded.

---

## 3. Seed `public/data` from the published tree — do NOT skip this

`publish_gh_pages.sh` makes `gh-pages:/data` an **exact copy** of `public/data` (rsync
`--delete`). Your local tree is missing every texture frame CI has built since the last hand
publish, so publishing without seeding would *revert CI's work*. This is not precautionary; the
two trees genuinely differ every time (footgun 31). Measured on 2026-08-30: 30 files published
that the local tree lacked, 10 local files that had scrolled out of the window. On 2026-08-31 it
was **40 each way** — and both trees held 142 files, so **equal totals are not evidence the trees
agree**. Count the difference, not the size.

```bash
git fetch origin gh-pages
SEED=$(mktemp -d)
git archive origin/gh-pages data | tar -x -C "$SEED"
echo "published: $(find "$SEED/data" -type f | wc -l)  local: $(find public/data -type f | wc -l)"
( cd "$SEED/data" && find . -type f | sort ) > /tmp/pub.txt
( cd public/data && find . -type f | sort ) > /tmp/loc.txt
echo "published-only: $(comm -23 /tmp/pub.txt /tmp/loc.txt | wc -l)  local-only: $(comm -13 /tmp/pub.txt /tmp/loc.txt | wc -l)"
rm -rf public/data && cp -R "$SEED/data" public/data && rm -rf "$SEED"
find public/data -type f | wc -l        # must equal the "published:" count printed above
git status --porcelain                  # expect EMPTY (public/data is gitignored)
```

---

## 4. Run the pipeline

**First, decide whether the texture stage needs to run.** CI rebuilds all five sphere maps on
every run, so if the copy you just seeded is only a few hours old and complete, rebuilding it is
~10 minutes of pure duplication. Runs 1, 4, 5 and 7 of this chore skipped it for exactly that
reason; run 6 rebuilt it because CI's copy was 13 h old.

```bash
"$PY" -c "
import json, datetime
d = json.load(open('public/data/texture/texture.json'))
gen = datetime.datetime.fromisoformat(d['generated_iso'].replace('Z', '+00:00'))
age = (datetime.datetime.now(datetime.timezone.utc) - gen).total_seconds() / 3600
print('texture', d['generated_iso'], round(age, 1), 'h old')
for l in d['layers']:
    print(' ', l['channel'].ljust(6), 'frames', len(l.get('frames', [])),
          'high_res', (l.get('high_res') or {}).get('width'))
"
```

**Complete** means five layers, 19 frames each, `high_res 8192` on every one. Complete and a few
hours old → omit both texture flags; the seeded files get republished untouched. Older than that,
short of 19 frames, missing a `high_res`, or you are unsure → pass them, which is what CI does.

```bash
mkdir -p "$(dirname "$LOG")"

# PICK ONE. (a) is uncommented because it is the common case; if the check above
# said the texture product is stale or incomplete, comment (a) out and use (b).

# (a) texture fresh and complete — the usual case right after a CI run:
"$PY" -u -m pipeline all --out public/data -v > "$LOG" 2>&1

# (b) texture stale or incomplete — exactly what data.yml passes:
# "$PY" -u -m pipeline all --out public/data -v --with-texture --with-hires > "$LOG" 2>&1
```

Run it **in the background** if your harness has a timeout shorter than ~15 minutes, then watch
it with `grep -v '^INFO:' "$LOG" | tail -20`.

Flags, and why each one is there:

| flag | why |
|---|---|
| `-u` | unbuffered — a killed run still leaves a readable log (footgun 41) |
| `--with-texture` | the sphere maps; **on** in CI, **off** by default locally — see the decision above, and skip it when the seeded copy is fresh and complete |
| `--with-hires` | the 8192x4096 newest-frame maps the app uses by default; CI passes this too. Omitting it **drops** the `high_res` blocks from the manifest and silently downgrades the app |
| `--out public/data` | the dev-server tree, and the thing step 6 publishes |

Do **not** add `--with-near-side` — that is T19's cold fill (~50 min), it has no consumer in the
app yet, and it is not part of this chore.

**Four process traps, all previously hit:**

- **(a) `python -u` does nothing through `conda run`.** conda captures the child's stdout and
  flushes only at exit, so a long run logs *nothing* while plainly working. Call the env's
  interpreter directly, as above — never `conda run` for a backgrounded pipeline.
- **(b) Do not `nohup … &` inside a backgrounded shell.** The harness reaps the wrapper's process
  group and the detached run dies a couple of minutes in, leaving an empty output dir and an
  empty log. Run the pipeline *as* the background command.
- **(c) The log's parent directory must already exist.** If it does not, the redirect fails, the
  pipeline never starts, and the background wrapper still reports a completed task — footgun 41's
  zero-byte-log symptom with no run behind it at all. `mkdir -p` first, and if the log is missing
  or empty a minute in, assume it never started rather than that it is quiet.
- **(d) One run per `--out`, and do not edit `pipeline/` while one is in flight.** A second run
  `rmtree`s the first one's `.staging` mid-flight (footgun 35) and a late lazy import reads your
  new source against an already-loaded old config (footgun 48). Both leave exit code 0.

**What a good run looks like** (`grep -v '^INFO:' "$LOG"`):

```
  seeds: 1329 line(s) (1152 background + 177 region) from srs.txt [2026-08-30] id=7f48181f
  slots: 19/19 have a magnetogram within 3 h        <- the line that matters
  tracing 19 distinct magnetogram(s) for 19 slot(s)
    pfss 1.76s trace 0.33s valid 1314/1329 ...      <- x19
  19 frame(s), 1329 lines, 19090 verts, ... (2.14 MB total), 258.1s
  ...
  history: 19 slot(s) x 5 channel(s) = 95; 75 reused, 15 built, 0 unavailable, 0 deferred
  [publish] 67 file(s) into public\data
    pfss ok / active_regions ok / ephemeris ok / events ok / stats ok / texture ok
```

- `19/19 … within 3 h` means a fully fresh window. Fewer is still publishable — the stage refuses
  only below `MIN_FRAMES_TO_PUBLISH = 6` — it just means part of the scrubber is older.
- A `WARN GONG …/mrzqs2608**31**/: HTTP 404` for *tomorrow's* directory is normal; the scraper
  probes a day ahead.
- The newest frame's magnetogram is normally **1–4 h old**, and that is correct, not stale: slot
  targets sit on a 4 h grid at or before "now", and a GONG synoptic magnetogram is a few hours old
  by construction. The app's scrubber copy already says so. (Measured 2026-08-31: a 16:00Z slot
  filled by a 15:14Z magnetogram, **0.77 h** — the low end of the band, not an anomaly.)
- `regions` printing `today's srs.txt lists 5 region(s), the history product 6` is expected and is
  explained in footgun 30 — different epochs, and `parse_srs` reads Section I only.
- With `--with-texture --with-hires`, the texture stage prints a `limb fit` per channel and a
  `hi-res 8192x4096 …` line per channel — **expect all five, 0304 included.** `TEX_LIMB_FIT_RES
  = 2048` now performs the limb fit at a fixed resolution whatever the source, so the guard keeps
  its calibration instead of rejecting the one channel with a diffuse limb; the live product
  carried `high_res 8192` on 5/5 layers when checked 2026-08-31. **`CLAUDE.md` footgun 40 still
  says 0304 is excluded and is out of date** (`TASKS.md` T4 owns that fix) — a *missing* 0304
  hi-res line is now a regression, not the guard working.
- The `history:`, `texture ok` and `hi-res` lines appear **only** with `--with-texture`. Under
  option (a) the publish line carries fewer files — **26 rather than 67**, measured 2026-08-31 —
  there is no `texture` line in the per-product summary, and `index.json` reports the texture
  product's real age with the note `not regenerated this run` instead of 0.0 h. All three are
  correct, not a partial run.
- Expect exit code **0** — but texture failures are *soft* and never change the exit code, so read
  the log rather than trusting the code alone.

---

## 5. Validate

```bash
"$PY" -m pipeline validate --root public/data --strict
```

**Expect `OK: 0 check(s) failed, 0 warning(s)`.** Do not publish otherwise. The most likely
failure is step 2's `ar_index` one, which a fresh PFSS run should have just fixed.

---

## 6. Publish

Re-check step 2's two lists **immediately** before pushing, not five minutes earlier.

```bash
GITHUB_TOKEN="$(gh auth token)" \
GITHUB_REPOSITORY="$REPO" \
GITHUB_SHA="$(git rev-parse HEAD)" \
bash scripts/publish_gh_pages.sh public/data data
```

The script force-pushes a single orphan commit to `gh-pages` carrying the app (materialised from
the existing branch) plus your `data/`. It leaves your working repo clean and a gitignored `.ghp/`
scratch dir behind, which is normal. Confirm what landed:

```bash
git fetch origin gh-pages && git log -1 --format='%H %ci %s' origin/gh-pages
git ls-tree -r --name-only origin/gh-pages -- data | wc -l
```

Record that commit hash — it goes in the `TASKS.md` note in step 8.

---

## 7. Verify the live site — and only then consider kicking Pages

The force-push **auto-triggers** a Pages build. Wait for it. Do **not** immediately
`POST /pages/builds`: racing the automatic build fails both of them (footgun 49).

```bash
sleep 45
gh api "repos/$REPO/pages/builds/latest" \
  --jq '{status, commit, created: .created_at, duration, error: .error.message}'
```

Expect `status: built`, `commit` equal to the hash from step 6, in ~25–40 s. Then:

```bash
curl -s "$SITE/data/index.json" | python -c "
import sys, json
d = json.load(sys.stdin)
print(d['generated_iso'], d['last_attempt_status'])
for k, v in sorted(d['products'].items()):
    print(' ', k.ljust(15), v['status'], round(v.get('age_hours', -1), 2), 'h')
"
"$PY" -m pipeline validate --url "$SITE/data/" --strict
```

**Definition of done:** live `index.json` reports `last_attempt_status: ok`, all six products
`ok`, `pfss` age ≈ 0, and `validate --url` at 0 failed / 0 warnings.

**Only if** the live tree is still the old one several minutes after the build finished:

```bash
gh api -X POST "repos/$REPO/pages/builds"
```

That is footgun 34 — a forced orphan push can leave Pages pointing at a commit that no longer
exists — but it is a *recovery* step, not a routine one. Note the two views disagree while a
build is wedged: `pages/builds/latest` can say `building` for a run `gh run list` already shows
as failed, so check both before concluding anything.

---

## 8. Record it

```bash
git add TASKS.md HANDOFF.md
git commit -m "Republish the data products: pfss was stale at N h, live is ok again"
git push
```

- **`TASKS.md` T1** — append what this run measured: how stale it was, slots fresh / 19, the
  newest magnetogram's age, the `gh-pages` commit, and that validate was clean both ways.
- **`HANDOFF.md`** — a short session entry saying the same thing.
- A genuinely *new* failure mode goes in **`CLAUDE.md`** as a numbered footgun, never in
  `TASKS.md`.

Optionally watch the next scheduled `data` run confirm the fix held: it will seed from your tree,
fail to reach GONG (expected), keep your frames, and pass `Validate` again.

---

## Quick reference

| symptom | meaning | do |
|---|---|---|
| `pfss stale`, `0 freshly traced frame(s) of 19 slot(s)` | GONG blocked from CI — the normal case | this runbook |
| index hours old but the last `data` run says `success` | GitHub skipped a cron slot — ~4 runs/day, not 6 | nothing; not a failure |
| CI `data` run red with `pfss` `degraded` in the `Verdict` table (or, before 2026-09-02, failed at `Validate` on `ar_index … bounds`) | region list shrank under a frozen seed set; the other five products still published | this runbook |
| pipeline log empty or missing a minute in | the run never started — trap (c), or (a)/(b) | fix the invocation, re-run |
| `0/19 slots have a magnetogram` **from this workstation** | a real GONG outage, not the CI block | wait; published frames keep serving |
| live tree still old > 5 min after a `built` Pages build | Pages wedged on a vanished commit | `gh api -X POST "repos/$REPO/pages/builds"` |
| newest frame 2–4 h old after a successful run | normal — 4 h slot grid + GONG's own latency | nothing |

**The permanent fix, `TASKS.md` T2, went live on 2026-09-02** — the GONG relay
(`docs/GONG-RELAY.md` Option D). CI now traces all 19 frames itself, so this runbook is for
the day the relay is down, not a daily chore. Before running it, check the mirror:
`Get-ScheduledTaskInfo SolGongMirror` (LastTaskResult 0, LastRunTime within the hour) and the
newest log's `SUMMARY:` line in `%LOCALAPPDATA%\sol-gong-mirror\logs\`. If the mirror is fine and
`pfss` is still stale, read the latest `data` run's `[GONG]` probe block — the failure is
between the branch and the runner, and this runbook will only paper over it for a day.
