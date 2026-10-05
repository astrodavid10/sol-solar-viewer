# Tasks archive

---

Task detail sections moved VERBATIM out of `TASKS.md` on 2026-10-05 (T4, the docs diet):
DONE tasks, T1's per-run republish diaries, and the long diary of T22 (still open; `TASKS.md`
keeps its summary and definition of done). The status-table rows stay in `TASKS.md`.
Hand-publishes are summarized one line each in `docs/republish-log.md`. Where these notes
disagree with `CLAUDE.md` or the code, the newer source wins.

---

<a id="t0"></a>

### T0 — Stand up this ledger

Create `TASKS.md`, seed it from the approved plan, point `HANDOFF.md` at it.

**Definition of done:** committed, and `HANDOFF.md` links here from the top.

---

<a id="t1"></a>

### T1 — Republish PFSS from this workstation

**Why.** Live `data/index.json` reports `pfss` stale at 26 h with "0 freshly traced frame(s)
of 19 slot(s)"; `pfss/manifest.json`'s newest frame is `2026-08-24T12:14Z`, ~30 h old. GONG
answers *this* workstation in 0.42 s (probed 2026-08-25) while timing out from every GitHub
runner (footgun 33).

**Follow [`PFSS-UPDATE.md`](PFSS-UPDATE.md), not the recipe below.** That file is the current
runbook — the same procedure, brought up to date (footgun 49's publish-then-wait ordering, the
`--with-texture --with-hires` flags CI actually passes, a fourth process trap), and written to
be followed top to bottom by a fresh session on a small model. What follows here is the
historical recipe plus the record of each run, kept because the *reasoning* behind each step is
in the run notes.

**Recipe** — the order matters:

1. Seed `public/data` from the live `gh-pages` tree **first** (footgun 31). Skipping this lets
   a wholesale republish clobber the fresher non-PFSS products CI built in the meantime.
2. `conda run -n sdo python -u -m pipeline all --out public\data -v` — `-u` so a killed run
   still leaves a log (footgun 41). One run per `--out` at a time (footgun 35).
   **Two process traps, both hit on 2026-08-25 and both producing footgun 41's exact
   zero-byte-log symptom from causes footgun 41 does not name:**
   - **`python -u` does nothing through `conda run`.** conda captures the child's stdout and
     flushes only at exit, so a long run logs *nothing* while plainly working (752 MB RSS,
     0-byte log). For any backgrounded run call the env's interpreter directly —
     `"$USERPROFILE/anaconda3/envs/sdo/python.exe" -u -m pipeline …` — which CLAUDE.md
     already lists as a fallback for unrelated reasons.
   - **Do not `nohup … &` inside a backgrounded shell.** The harness reaps the wrapper's
     process group, so the detached run dies a couple of minutes in with an empty output dir
     and an empty log. Run the pipeline *as* the background command instead.
3. `python -m pipeline validate --root public\data --strict` → expect 0 failed / 0 warnings.
4. `scripts/publish_gh_pages.sh` (auth via `gh auth token`; it normally runs inside CI with
   `GITHUB_TOKEN`/`GITHUB_SHA` already set).
5. Kick the Pages build: `gh api -X POST repos/astrodavid10/sol-solar-viewer/pages/builds`
   (footgun 34).
6. Re-fetch the live `index.json` and confirm.

**Definition of done:** live `index.json` reports `pfss` ok, age ≈ 0, 19/19 slots.

**DONE 2026-08-25 20:54Z** — published as `gh-pages` commit `cb0ba1a`.

- GONG answered every request from here: **19/19 slots had a magnetogram within 3 h**, so this
  is a fully fresh window, not a partial fill. Live newest frame `2026-08-25T18:44Z`,
  **2.2 h old** (which is simply what a GONG synoptic magnetogram is — the scrubber's copy
  already says so) against **30.1 h** before.
- All six products `ok`, `last_attempt_status: ok`. Both `validate --root public/data --strict`
  and `validate --url …/data/ --strict` report **0 failed / 0 warnings**.
- **Ran `all` WITHOUT `--with-texture`, deliberately.** CI's texture product was 0.2 h old and
  hires-complete; re-running locally would either cost ~15 min for identical pictures or,
  without `--with-hires`, drop the `high_res` blocks the app has used by default since
  `e7095c2`. Verified safe by reading the code first: `_prune_orphan_textures` returns early
  when `results` carries no texture entry (`cli.py:1061-1063`), and `build_index` falls back to
  `_existing_product` (`:949-951`). Published index says texture `ok … not regenerated this
  run`; file count held at 132.
- Seeded `public/data` from `origin/gh-pages` first (footgun 31) — confirmed necessary rather
  than assumed: gh-pages held **132** files against the local tree's **117**, i.e. 15 texture
  frames CI had built since the last local run, which an unseeded `rsync --delete` publish
  would have reverted.
- **A hand-publish is NOT in the `gh-pages-publish` concurrency group** that serializes
  `data.yml` against `app-deploy.yml`. A scheduled `data` run was in flight when this started
  with `Deploy app` queued behind it; publishing into that would have raced two force-pushes
  to the same orphan branch. Wait for both by hand, and check again immediately before
  pushing.

**Note for T2:** the next scheduled CI run will seed from this tree, fail to reach GONG, and
mark `pfss` stale again while preserving these frames. Designed behavior — and exactly the
recurring chore T2 exists to end.

**It recurred, on schedule.** Done again **2026-08-26 07:07Z** (`gh-pages` commit `94fbdfb`),
this time as a full `all` run rather than PFSS alone: live `index.json` had gone back to
`degraded` with `pfss` stale at **8.0 h**, and came out `ok` with all six products `ok` and
19/19 slots freshly traced (newest magnetogram `2026-08-26T04:04Z`, 2.9 h old). Both
`validate --root` and `validate --url` reported 0 failed / 0 warnings. Same two cautions as
above still applied and were followed: seed from `origin/gh-pages` first (the seed differed
from the local tree by 10 files), and check for an in-flight CI run before pushing.

**And again, on schedule.** Done a fourth time **2026-08-27 15:50Z** (`gh-pages` commit
`e6e22d9`): live `index.json` was `degraded` with `pfss` **stale at 18.3 h / "0 freshly traced
frame(s) of 19 slot(s)"**, and came out `ok` with all six products `ok`. GONG answered this
workstation for every request -- 19/19 slots had a magnetogram within 3 h, so a fully fresh
window again; newest frame 3.5 h old, 1362 seed lines, 19 frames / 2.24 MB, 255 s of tracing.
`validate --root` and `validate --url` both reported 0 failed / 0 warnings.

Ran `all` **without** `--with-texture`, the same reasoning as the first publish and re-checked
rather than assumed: CI's texture was 6.3 h old and hires-complete on all five layers, and a
local run without `--with-hires` would have dropped those `high_res` blocks. The published
index says texture `ok ... not regenerated this run`; file count held at 142. Seeding from
`origin/gh-pages` was again *necessary*, not precautionary: the published tree carried 25
texture history frames (5 channels x 5 slots) the local tree lacked, and the local tree held 25
that had scrolled out of the window -- an unseeded `rsync --delete` publish would have reverted
CI's work.

**Two notes for the next time.** (a) Footgun 49 held: the force-push auto-triggered a Pages
build for the right commit, which went `built` in 32 s, so **no explicit `POST /pages/builds`
was made or needed** -- the live tree was serving new data within 15 s of the build starting.
(b) A **`Deploy app` run had been stuck `queued` for 24 h 23 m** (commit `90cd733`, already
superseded by a later deploy that succeeded). It is an *app* publish, which preserves `data/`,
so it could not clobber the data content; the only exposure is an interleaved checkout, and
GitHub drops queued runs at 24 h. Checking `gh run list --status queued` as well as
`--status in_progress` is what surfaced it -- the plain `gh run list` top-5 did not.

**And a fifth time.** Done **2026-08-29 17:39Z** (`gh-pages` commit `4e80021`): live
`index.json` was `degraded` with `pfss` **stale at 46.1 h** and the same
`0 freshly traced frame(s) of 19 slot(s)` note — the longest gap yet, because the recurrence
spans two sessions rather than one. Came out `ok` with all six products `ok`.

GONG answered this workstation on every request (0.61 s to the listing root): **19/19 slots had
a magnetogram within 3 h**, a fully fresh window, `reused: 0`. Newest frame
`2026-08-29T16:14Z` — **1.3 h old** against 46.1. Seed set `590cb2a7`, 1351 lines
(1152 background + 199 region), 1324-1332 of them valid per frame; 19 frames / 2.25 MB;
**39.0 s** of solve+trace (1.70-2.70 s per frame). Both `validate --root` and `validate --url`
reported 0 failed / 0 warnings.

Same two cautions, both followed. Seeding was again *necessary*: the local tree held **65**
files the published one lacked (texture frames scrolled out of the window) and the published
tree held **45** the local lacked (CI's newer frames), so an unseeded `rsync --delete` publish
would have reverted CI's work in both directions. Nothing was in flight or queued at publish
time (`--status in_progress` and `--status queued` both empty, re-checked immediately before
the push). Texture again NOT regenerated — CI's copy was 3.7 h old and hires-complete on all
five layers, including 0304; published index says texture `ok`, file count held at **122**.

Footgun 49 held for the second time running: the force-push auto-triggered a Pages build
against the correct commit (`4e80021`), `built` in ~25 s, **no explicit `POST /pages/builds`
made or needed**.

**One new observation.** The window's low edge is now the binding constraint on how long a gap
can be tolerated, not the staleness threshold: at 46.1 h the served frames still spanned a
valid 72 h window, so the app had a complete scrubber showing a two-day-old Sun. That is the
failure mode T2 is really about — not an outage the guest can see, but a plausible one they
cannot.

**That is five hand-publishes in five sessions**, which is the argument for T2 rather than a
note about it. The cost is ~20 minutes of a session each time, and the failure mode when a
session *doesn't* do it is silent: the site keeps serving correct-looking field lines that are
a day old.

**A sixth time — and the recurrence finally cost CI a run.** Done **2026-08-30 11:59Z**
(`gh-pages` commit `98536eb`). Two things were stale at once, which is new:

- `pfss` had not been rebuilt since the fifth republish, so the served manifest was
  **18.2 h** old with the usual `0 freshly traced frame(s) of 19 slot(s)`.
- **The whole index was 13.2 h old**, because the 05:12Z scheduled `data` run *failed* — the
  first CI failure of the project. It died at `Validate` on
  `FAIL ar_index within regions.json bounds -- range [-1,5] vs 5 regions`, and that is a
  **stale-PFSS symptom, not an independent bug**: the frozen seed set was built on a day when
  NOAA's SRS listed six regions, CI kept regenerating `regions.json` down to five, and the
  topology's `ar_index` then pointed one past the end. Since `Validate` runs *before* `Publish`,
  every product CI built that morning was discarded — so a stale PFSS product had started
  blocking the five products CI *can* build. It cleared exactly as expected once the seed set
  was rebuilt against today's five regions (`id=7f48181f`, 1329 lines = 1152 background + 177
  region). **This is a new coupling worth remembering: PFSS staleness is not indefinitely
  survivable — it eventually takes the rest of the tree down with it.**

GONG answered this workstation on every request: **19/19 slots had a magnetogram within 3 h**,
`reused: 0` on all 19, so a fully fresh window. 19 frames / 1329 lines / 19,090 verts /
2.14 MB, 258.1 s of solve+trace, dequant error 3.97e-05 R_sun. Newest frame's magnetogram
`2026-08-30T08:14Z` — 3.6 h old at run time, which is the **4 h slot grid plus GONG's own
latency**, not staleness (the 08:00Z slot is the newest one at or before an 11:47Z run).

**Texture WAS regenerated this time**, unlike runs 1, 4 and 5 — CI's copy was 13.2 h old rather
than a few hours, so the reasoning that protected it before did not apply. Ran with
`--with-texture --with-hires`, matching what `data.yml` actually passes: all five layers rebuilt
with `high_res`, 95 history slots (75 reused, 15 built, 0 unavailable, 0 deferred by the cap),
27.35 MB, 424.4 s. 0304 again produced no hi-res map — footgun 40's guard working, not a
failure. 15 orphan frames pruned; published file count held at **142**.

Seeding was again *necessary*: the published tree held **30** files the local one lacked and the
local held **10** that had scrolled out of the window. Nothing was in flight or queued
(`--status in_progress` and `--status queued` both empty, re-checked immediately before the
push), and the push went out at 11:59:51Z, eight minutes ahead of the 12:07Z cron slot. Footgun
49 held for the third time running: the force-push auto-triggered a Pages build against the
correct commit, `built` in 22 s, **no explicit `POST /pages/builds` made or needed**. Both
`validate --root` and `validate --url` reported 0 failed / 0 warnings.

**The chore is now written down.** Six hand-publishes in six sessions was enough of an argument:
the whole procedure — preconditions, the seed, the flags and why each one is there, the four
process traps, the publish, the Pages wait, and what to record — is now
**[`PFSS-UPDATE.md`](PFSS-UPDATE.md)**, written so a fresh session on a small model can run it
top to bottom without reading the pipeline source. It documents one trap this session hit that
footgun 41 does not name: **if the log file's parent directory does not exist, the redirect
fails, the pipeline never starts, and the background wrapper still reports a completed task** —
footgun 41's zero-byte-log symptom with no run behind it at all. That does not make T2 less
necessary; it makes the interim cheaper.

**A seventh time — and the runbook earned its keep, then needed fixing.** Done **2026-08-31
16:22Z** (`gh-pages` commit `c0d0f1f`), following `PFSS-UPDATE.md` top to bottom.

- Live `pfss` was **stale at 17.6 h** with the usual `0 freshly traced frame(s) of 19 slot(s)`,
  `last_attempt_status: degraded`.
- **The index was 10.8 h old and nothing had failed.** The 05:20Z run succeeded; GitHub simply
  never fired the 08:07Z or 12:07Z slots. Over the two preceding days `data` ran four times a
  day against six scheduled slots (19:16Z, 22:39Z, 05:20Z, 16:06Z), every run `success`. The
  runbook told a session to read a stale index as "the last scheduled run failed" — corrected.
- **A scheduled run was in flight when the check ran** (16:06:40Z, 7m16s, `success`), so this
  waited for it and for its Pages build before seeding — the case step 2 exists for. Seeding
  was again necessary: **40 files each way**, and both trees held 142, so equal totals prove
  nothing.
- Ran `all --out public/data -v` with **no texture flags**, deliberately: CI's texture product
  was 8 minutes old and complete (five layers, 19 frames each, `high_res 8192` on every one).
  That saved ~10 minutes of pure duplication and is the same judgement runs 1, 4 and 5 made.
  The published `index.json` reports it honestly — `texture ok 0.14 h, not regenerated this run`.
- GONG answered every request: **19/19 slots within 3 h**. 19 frames, 1340 lines
  (1152 background + 188 region, `id=1ef475a7`), 18,890 verts, 2.12 MB, dequant err
  3.97e-05 R_sun, 277.6 s. Newest slot 16:00Z filled by a **15:14Z** magnetogram — 0.77 h old,
  the freshest of the seven runs. Window `2026-08-28T16:00Z .. 2026-08-31T16:00Z`, a full 72 h.
- `events` printed `AR join: 0/4` and that is correct, not a regression: DONKI cites AR **4521**
  while today's SRS lists 4513/4515/4517/4518/4520, so `ar_index -1` is the honest answer
  (footgun 23). Checked rather than assumed.
- Both `validate --root` and `validate --url` reported **0 failed / 0 warnings**; live
  `index.json` is `ok` on all six products with `pfss` at 0.0 h. Footgun 49 held for the
  **fourth** time running: the force-push auto-triggered a Pages build against the correct
  commit, `built` in 27.7 s, no explicit `POST /pages/builds` made or needed.

**Correction to the sixth run's record above: the 2026-08-30 05:12Z `Validate` failure was not
"the first CI failure of the project".** The identical `FAIL ar_index within regions.json bounds
-- range [-1,5] vs 5 regions` had already failed two runs on **2026-08-28** (11:12Z and 22:12Z),
which the eleventh session's republish cleared without noticing. Three occurrences, one cause —
so footgun 50's coupling is the *normal end state* of stale PFSS on a roughly two-day fuse, not a
one-off. `PFSS-UPDATE.md` step 2 now says so, and also warns that `gh run view --log-failed`
points at the wrong step: the never-fatal `Probe upstreams` step exits 1 on every run, so it is
what `--log-failed` prints while `Validate` is the actual failure.

**The runbook was reviewed against this run and corrected in eight places** — the two above plus:
the seed step now counts the *difference* between the trees rather than comparing totals; step 4
opens with an explicit texture-rebuild decision (a check and a rule, instead of an unconditional
`--with-texture`); the "expect no 0304 hi-res line" bullet was **backwards** and would have hidden
a real regression (`TEX_LIMB_FIT_RES = 2048` made the limb fit resolution-independent, so all five
channels earn a hi-res map — `CLAUDE.md` footgun 40 is stale, which T4 already owns); the newest-
magnetogram band widened to 1–4 h; a quick-reference row for "index old but the last run passed";
and the time estimate split by whether textures rebuild (~12 min vs ~20).

**DONE 2026-09-01 16:40Z — eighth run.** Published as `gh-pages` commit **`5f915030`** at
**16:40:27Z**. 132 data files, **down from 142**: 25 texture orphans scrolled out of the window
and 10 new history frames were deferred by the per-run cap (see below). A file count that *falls*
is normal here and is not evidence of a clobbered tree — count the difference, not the total.

**The blocking problem this time was NOT staleness. It was one bad record in NOAA's feed.**
Live `pfss` was stale at 12.66 h inside an `index.json` that was itself **11.5 h** old, with
`last_attempt_status: partial:texture` — so every product was behind, not just field lines. Step 2
found the 13:26Z scheduled `data` run had failed at `Validate`, but **not** on the familiar
`ar_index` bound:

```
FAIL  history 2026-09-01 AR4521: lat_deg within +/-60  -- got 98.0
```

`json/solar_regions.json` was publishing AR4521 at `"latitude": 98` on 09-01 having published the
same region at `9` on 08-31, and `srs.txt` independently reported `N09E67` for it — a keying error
at NOAA (98 for 9). Because `Validate` runs before `Publish`, that one record discarded the five
products CI *had* built correctly, which is why the whole index was 11.5 h old. **Footgun 50's
coupling, from a completely new cause** — and worth noting that eight runs of this chore had
trained the expectation that a `Validate` failure means `ar_index`. It did not. Read the FAIL line.

Fixed at the source, in `pipeline/sources/srs.py` — `fetch_regions_json` now drops physically
impossible records with a loud `WARN` naming every value, with bounds that deliberately mirror
`validate.py`'s region checks. Recorded as **footgun 51**. Two decisions worth keeping:

- **Dropped, not repaired.** `srs.txt` happened to carry the right latitude, but patching one feed
  from the other would invent positions on the days they legitimately disagree — and they do, by
  epoch and by region set (footgun 30). One region missing from one day's chip is a rounding error
  to a guest; a marker at a latitude nobody measured is a lie over imagery showing the truth.
- **The validator's bound was NOT loosened.** It is the only thing between a hand-keyed feed and a
  sunspot at latitude 98.

Verified on the live feed before running: the guard fires exactly once, drops only AR4521 on
09-01, and keeps that same region's good 08-31 entry.

**The run itself:**

- **19/19 slots had a magnetogram within 3 h** — a fully fresh window. 19 frames, 1307 lines
  (1152 background + 155 region, seed `id=c609eea3`), 18,386 verts, 2.06 MB, dequant err
  3.97e-05 R_sun, **269.2 s**. Window `2026-08-29T16:00Z .. 2026-09-01T16:00Z`, a full 72 h.
- Newest slot 16:00Z filled by a **15:14Z** magnetogram — **1.47 h** old, mid-band.
- **Textures WERE rebuilt** (`--with-texture --with-hires`): the seeded copy was complete but
  **19.0 h** old, which is past step 4's "a few hours" rule. All five channels produced a
  `high_res 8192` map (0171 1.26 MB/62.6 s, 0304 1.99 MB/58.1 s, 0193 1.06 MB/63.2 s, HMIIC
  1.07 MB/42.4 s, HMIB 3.28 MB/36.5 s) — **including 0304**, again confirming `CLAUDE.md`
  footgun 40 is stale (T4 owns it). Hi-res cost ~40-63 s per channel, well under footgun 40's
  ~3 min estimate.
- Limb fits all inside `TEX_LIMB_RADIUS_TOL`: 0171 -0.00%, 0304 **+2.37%**, 0193 +1.67%, HMIIC
  +0.10%, HMIB +0.12%. The EUV channels sit high and the HMI ones are near-perfect (0.3-0.5 px
  scatter), exactly the diffuse-vs-sharp limb split footgun 40 describes.
- **10 of 95 history frames were deferred by the cap** — `65 reused, 15 built, 0 unavailable, 10
  deferred`, leaving every channel at **17 of 19** frames. Published anyway, deliberately: the
  validator has no minimum frame count, the app falls back to the nearest frame it has, and **CI
  can build textures** (only GONG is blocked), so it converges at +10/run on the next scheduled
  run. Refilling here would have cost ~8 min, and a bare `texture` re-run would also have had to
  redo `--with-hires` or silently drop the `high_res` blocks.
- `events` printed **`AR join: 4/4`** — a full match, in contrast to the seventh run's 0/4 (which
  was also correct at the time). Footgun 23's join is working.
- Both `validate --root` and `validate --url` reported **0 failed / 0 warnings**; live
  `index.json` is `last_attempt_status: ok` with all six products `ok` at 0.0 h.
- Footgun 49 held a **fifth** time: the force-push auto-triggered a Pages build against the right
  commit, `built` in **31.4 s**, no explicit `POST /pages/builds` made or needed.
- Nothing was in flight or queued on GitHub at 16:40Z; the next cron slot was 20:07Z. The 16:07Z
  slot appears to have been dropped outright — the runbook's "~4 runs against 6 slots" again.

**One process note:** `scripts/publish_gh_pages.sh` produced **no stdout at all** through
`2>&1 | tail -20`, which looked like a failed push. It had in fact succeeded. Verify a publish by
fetching `origin/gh-pages` and reading the commit, never by the script's console output.

**DONE 2026-09-02 15:36Z — ninth run.** Published as `gh-pages` commit **`726f69a`** at
**15:35:55Z**, following `PFSS-UPDATE.md` top to bottom. **137** data files, down from 142: 20
texture orphans scrolled out of the window against 15 newly built history frames. A falling
count is normal here — count the difference, not the total.

- Live `pfss` was **stale at 22.92 h** (`generated_iso 2026-09-01T16:27:02Z`) with the usual
  `0 freshly traced frame(s) of 19 slot(s)`, inside an `index.json` that was itself **16.8 h**
  old, `last_attempt_status: degraded`.
- **Both scheduled `data` runs since had failed at `Validate`, and this time it *was* the
  `ar_index` one.** 04:17Z and 12:43Z, identically:
  `FAIL ar_index within regions.json bounds -- range [-1,5] vs 4 regions`. So the 16.8 h index
  age was footgun 50's coupling and not a dropped cron slot — the seed set frozen on 09-01 was
  built when NOAA listed six regions, today's SRS lists four, and the five products CI *can*
  build were discarded twice. Footgun 50's normal end state on its usual two-day fuse; the
  eighth run's warning to *read the actual FAIL line* still stands, it just came out the other
  way this time.
- Seeding was again *necessary*: the published tree held **15** files the local one lacked and
  the local held **5** that had scrolled out of the window.
- GONG answered this workstation on every request (day listings 71/72/63/39 files):
  **19/19 slots had a magnetogram within 3 h**, `reused: 0` on all 19 — a fully fresh window.
  19 frames, **1251 lines** (1152 background + 99 region, seed `id=fd2edf25`), 18,706 verts,
  2.09 MB, dequant err 3.97e-05 R_sun, **238.4 s**. Window
  `2026-08-30T12:00Z .. 2026-09-02T12:00Z`, a full 72 h. The log also reported `pruned stale
  frame cache 1ef475a7` — the seventh run's seed set aging out, which is why nothing was reused.
- Newest slot 12:00Z filled by a **12:04Z** magnetogram: `mag_age_hours` **0.07 h** off-slot,
  the closest fill of the nine runs, and **3.33 h** old at run time — inside the runbook's 1-4 h
  band, which is the 4 h slot grid plus GONG's own latency.
- **Textures WERE rebuilt** (`--with-texture --with-hires`). The seeded copy was *complete*
  (five layers, 19 frames each, `high_res 8192` on every one) but **16.8 h** old, which is past
  step 4's "a few hours" rule — the same call the sixth and eighth runs made. All five channels
  earned a `high_res 8192x4096` map, **0304 included**: 0171 1.26 MB/61.1 s, 0304 1.98 MB/59.5 s,
  0193 1.05 MB/57.9 s, HMIIC 1.07 MB/37.4 s, HMIB 3.28 MB/38.3 s. 5 layers, 26.28 MB, **422.3 s**.
  Third run running that contradicts `CLAUDE.md` footgun 40 (T4 owns it).
- Limb fits all inside `TEX_LIMB_RADIUS_TOL`: 0171 **-0.62%**, 0304 +2.03%, 0193 +1.78%,
  HMIIC +0.09%, HMIB +0.11%. 0171 is the first *negative* fit recorded here, and the
  sharp-limbed HMI channels again scatter 0.6-1.9 px against the EUV channels' 17-18 px.
- **5 of 95 history frames deferred by the cap** — `70 reused, 15 built, 0 unavailable, 5
  deferred` — leaving every channel at **18 of 19**. Published deliberately, the eighth run's
  reasoning: no validator minimum, the app falls back to the nearest frame it has, and CI *can*
  build textures, so it converges on the next scheduled run. The log says so itself: "net
  +10/run, so ~1 more run(s) to fill".
- `events` printed **`AR join: 3/3`** — a full match (footgun 23's `- 10000` join working).
- Total pipeline wall time **668.6 s** (11 min 9 s), exit code 0. Both `validate --root` and
  `validate --url` reported **0 failed / 0 warnings**; live `index.json` is
  `last_attempt_status: ok` with all six products `ok` at 0.0 h.
- Footgun 49 held a **sixth** time: the force-push auto-triggered a Pages build against the
  right commit, `built` in **27.5 s**, no explicit `POST /pages/builds` made or needed. And the
  eighth run's process note held too — `publish_gh_pages.sh` printed **nothing at all** on a
  successful push, so it was verified by fetching `origin/gh-pages` and reading the commit.
- Nothing was in flight or queued at 15:35Z (re-checked immediately before the push), 31 minutes
  ahead of the 16:07Z cron slot.

**Nothing in the runbook needed correcting this time** — it was followed literally end to end and
every stated expectation held, including the 404 for tomorrow's GONG directory, the `regions`
epoch note, and the `--log-failed` warning in step 2. Two small things a future run may want
stated: the newest-frame band is quoted against *run time* while `manifest.json`'s
`mag_age_hours` measures the offset from the **slot target** (0.07 h here, 3.33 h against the
clock), and step 4's "what a good run looks like" sample shows `0 deferred`, which the last two
runs have not matched.

---

<a id="t2"></a>

### T2 — Land the GONG relay: Option D, the workstation mirror  *(DONE 2026-09-02)*

**Decided** this session, over Option A (Cloudflare Worker) and over shelving it.

**What is already written and uncommitted** (154 insertions, sitting in the tree since
session five, additive and inert with the env vars unset):

- `scripts/gong_mirror.py` (599 lines) — scrapes GONG from a machine that can reach it and
  republishes to a `gong-cache` branch, manufacturing an `index.html` per day directory
  because `raw.githubusercontent.com` serves files, never directory listings.
- `scripts/gong-mirror-task.ps1` (114 lines) — the Windows Scheduled Task wrapper.
- `SOL_GONG_PROXY_INDEX` seam in `pipeline/config.py`, `pipeline/sources/gong.py` (`_relay`),
  `pipeline/cli.py` (`probe-sources` output) and `.github/workflows/data.yml`.

**The code is now COMMITTED, and not on purpose.** A `git add -A pipeline` in the ninth session
swept the relay seam into `8650fee` (whose message does not mention it), and an earlier
`git add .github/workflows/data.yml` took the workflow half into `90cd733`. Rather than unpick
it, the rest was committed alongside and this row updated: the code is landed and **inert** --
`GONG_PROXY_BASE` and `GONG_PROXY_INDEX` read from env vars that are unset everywhere, so every
URL stays canonical and nothing behaves differently. Treat the diff as unreviewed.

**Go-live steps that REMAIN:** review the landed diff → `--dry-run` the mirror → create the
`gong-cache` branch → install the Scheduled Task → set `SOL_GONG_PROXY_BASE` and
`SOL_GONG_PROXY_INDEX` as repository secrets → confirm from a real scheduled run.

**Do not** set `GONG_BASE` to the relay — the rewrite is request-time only, because
`gong_file_key` derives the traced-frame cache key from the URL and because the manifest
cites that URL as provenance (footgun 37).

**Definition of done:** a scheduled `data.yml` run traces ≥ `MIN_FRAMES_TO_PUBLISH` frames
with no human in the loop, and `docs/GONG-RELAY.md` records the live configuration.

**Known weakness, to be written down rather than discovered:** a sleeping or offline
workstation stops the mirror. The pipeline then degrades exactly as it does today — stale,
not deleted (footgun 31). **The mirror itself did NOT have that property until `85e626c`:** an
empty state dir force-pushed an empty tree over the good branch (deleted, not stale). It
refuses now; footgun 55.

**GO-LIVE, 2026-09-02 (sixteenth session), in the order the list above gives:**

1. Reviewed the landed diff — the full item-by-item review is in T21's progress notes; five
   defects fixed in `85e626c`, 12 tests added, `docs/GONG-RELAY.md` corrected (stale byte
   counts, the future-day 404, why `--retain-days 5`, the token sentence).
2. `--dry-run --retain-days 5 -v`: 7 day dirs, 135 files / 31.3 MB, 61 s, exit 0.
3. Real run, default state dir `%LOCALAPPDATA%\sol-gong-mirror\repo`: pruned 27 files from an
   August test (`mrzqs260823/24`), mirrored **136 files**, newest 0.6 h old, **pushed
   `origin/gong-cache`** (`0f75a8e`). Verified over `raw.githubusercontent.com`: today's
   `index.html` → 200 listing 18 files; a FITS `HEAD` → 200, 243,016 bytes, `max-age=300`.
4. Secrets: `SOL_GONG_PROXY_BASE` = the raw URL of `gong-cache/oQR/zqs`;
   `SOL_GONG_PROXY_INDEX` = `index.html`; token left unset.
5. `SolGongMirror` registered: hourly, `-StartWhenAvailable`, `IgnoreNew`, 30 min limit,
   `RunLevel Limited`, **interactive logon, no stored password** — runs while this user is
   logged on (locked is fine), pauses when logged off. Re-register with a stored password per
   the ps1 header if run-when-logged-off is wanted. `-RepetitionDuration ([TimeSpan]::MaxValue)`
   from the header's original snippet is REJECTED on this Windows 11 build (`Duration:
   P99999999DT23H59M59S` out of range); the snippet now omits it.
6. `gh workflow run data.yml -f dry_run=true` (run 33663715169) — **the relay works from a
   runner.** `[GONG] via relay … directory index: index.html`; listings 71 / 72 / 66 / 42 files
   for 08-30 .. 09-02; **`slots: 19/19 have a magnetogram within 3 h`**; `tracing 19 distinct
   magnetogram(s)` → 19 frames, 1251 lines, 2.10 MB, **243.3 s** on the runner (against 11.8 s
   cache-warm locally; the runner's `actions/cache` had never held a frame before — footgun 33
   — so this fills it); pre-promote `[validate]` OK for all SIX staged products; publish
   skipped (dry run); tripwire 0/0; **`last_attempt_status ok`, Verdict green, Notify
   skipped.** Whole job well inside the 45 min budget. The first `data` run since 2026-08-23
   to build field lines without a workstation.
7. A real (publishing) dispatch followed immediately: **run 33664961891 — `slots: 19/19`, 19
   frames in 30.0 s** (the dry run had just filled the runner's traced-frame cache, footgun 33's
   `actions/cache` comment is finally true), `[publish] 62 file(s)`, `VERDICT: ok -- all 6
   products ok`, published as `gh-pages` **`ca5426f`** at 18:13Z. Live `index.json` 18:05Z `ok`,
   pfss `data_age_hours 1.85`, manifest `sol.pfss/2`. **The first field lines ever published by
   CI.** Issue #1 commented and closed. The formal DoD wording ("a *scheduled* run") is met by
   the next cron tick; `freshness.yml` and a reopened issue #1 are what would say otherwise.

**Definition of done:** a scheduled `data.yml` run traces ≥ `MIN_FRAMES_TO_PUBLISH` frames
with no human in the loop, and `docs/GONG-RELAY.md` records the live configuration (done).

---

<a id="t5"></a>

### T5 — Wire the checks that already exist into CI

`scripts/check_label_layout.mjs` and `scripts/check_pipeline_names.py` are the only automated
checks in the project and **no workflow and no `package.json` script invokes either**.

`.github/workflows/build.yml` has never run, for two independent reasons: all work lands
directly on `main` so no PR opens it, and its trigger is malformed —

```yaml
on:
  pull_request:
    branches:
      main        # a scalar, not a YAML sequence; GitHub expects a list
```

**Definition of done:** a push to `main` runs lint + typecheck + build + both checks, green,
and each check is one `yarn` command locally.

---

<a id="t18"></a>

### T18 — A vertical reel of the 72 h field  *(DONE 2026-08-26)*

Asked for directly, outside the plan: a reel-sized animation of the full 72 h magnetic field
with the surface switching Magnetic Map → Visible Sun → Chromosphere → Coronal Loops → Hot
Corona while it plays. `scripts/render_reel.py` renders the published tree to 1080x1920 MP4;
HANDOFF §3zzzzz has the reasoning and the three deliberate departures from the app.

**Why it is not a screen recording**, since that is the obvious question a later session will
ask: WWT's FOV is a fixed π/4 *vertical* (footgun 11), so a portrait crop is ~2.2x too tight;
GL lines are 1 px and aliased; the browser path is blocked on T8; and a recorder cannot be
asked for reproducible frame timings.

**The part worth reusing:** `--check-conventions` re-derives each frame's rotation from
`quat_carr_to_ecl` and checks it against the pipeline's own `mat3_carr_to_ecliptic_j2000`
(8.2e-16). That is the shape of check **T6** wants — external, not internal. Footgun 47 got
four sessions because every internal cross-check agreed with every other one.

**Not committed:** the MP4. `gh-pages` is a forced orphan commit precisely to keep regenerable
binaries out of history; a ~20 MB video on `main` would undo that. Re-run the script.

**If it is rendered again:** it reads only the published contract, so it works against any
`--root`, including a `--url`-fetched tree if one is ever mirrored locally. The constants most
likely to need a re-sweep are the three in the header (glow gain, line gain, line sigma), and
they must be judged at 1080x1920, not on a scaled-down still.

---

<a id="t20"></a>

### T20 — Review fixes, 2026-09-02  *(DONE)*

**Why.** A full read-only review on 2026-09-02 (four passes: the publish run, the app, the
pipeline, CI/ops; report at
<https://claude.ai/code/artifact/2d47d6e5-c7e8-4efc-8bb4-795f91f32908>) ranked thirteen fixes
by guest-and-operator pain over effort. The first eight are this task. They outrank the rest of
the ledger because two are live data-correctness defects and two are why the site went 16.8 h
stale on every product this morning.

**The eight items, in the order they are being worked** (pipeline items are sequential in one
stream because they all touch `validate.py` and `cli.py`; app and workflow items run beside them
on disjoint files):

| item | what | where |
|---|---|---|
| 1 | Zone-less SWPC time tags parsed as LOCAL time — every hand-publish from this Central-time workstation shipped the wind series +5 h (live today: five points in the future, a 5 h hole) | `pipeline/io_utils.py` `parse_iso_z`, validator stats checks, `stats/export.py` f107 |
| 8 | `index.json` reports a stage that FAILED this run as `ok` (only `last_attempt_status` knew); the stale pfss path had no `data_age_hours` at all | `cli.py` `_existing_product` / `failed()`, `pfss/export.py` `newest_mag_unix` |
| 7 | The validator decodes 60 of 115 referenced texture files and cannot see a manifest naming a missing one (footgun 35's production failure, still uncaught); the orphan pruner's keep-set is hand-maintained | new `pipeline/manifest_urls.py`, `validate.py`, `cli.py` |
| 2 | Validate-before-Publish discards all six products on one failed check (6 of 44 runs; footguns 50/51) — validation moves INTO the pipeline, per product, before promote, with per-product rollback; exit code 0 = "a tree was promoted" | `validate.py` `validate_products`, `cli.py` `cmd_all` |
| 3 | `ar_index` is a POSITION into a `regions.json` CI regenerates every 4 h (5 of the 6 failures) — the manifest now carries `seed_regions` (NOAA numbers); an unlisted region is a WARN | `pfss/seeds.py`, `pfss/export.py`, `validate.py` |
| 4 | Nothing notified anyone and nothing checked the live site — failure → one deduped issue; a 2-hourly `freshness.yml` watches the live index; `data.yml` reordered Build → Publish → Validate (tripwire) → Verdict | `.github/workflows/data.yml`, `freshness.yml`, README badge |
| 5 | One dropped PFSS frame blanked the whole field-line layer and pinned "Loading… 18 of 19" forever (`recomputeLoadedFrom` anchored on the newest INDEX, not the newest LOADED frame) | `src/three/fieldLines.ts`, `TimeScrubber.vue` |
| 6 | Duplicate sphere-texture loads leaked ~8 MB of GPU memory per slot crossing (no `pending` guard on `loadTexture`; displaced textures never disposed) and the LRU could evict the map on the sphere | `src/three/sunSurface.ts` |

**Not in this task (items 9-13 of the review):** dropping Vuetify from the entry chunk, moving
`setFrameTime` off the ephemeris gate, T5's CI wiring, the two token leaks (must land before
T2's Option D goes live), the destructive `max_frames` input.

**Definition of done:** each item committed with its own regression test where one is
practical (pipeline: pytest under `pipeline/tests/`), `yarn lint` / `typecheck` / `build`
green, `validate --root public/data --strict` still 0/0 on the published tree, a `dry_run`
`data.yml` dispatch passing under the new step order, and `CLAUDE.md` carrying the zone bug as
a footgun.

**Progress** — filled in as items land:

- **Item 1 DONE** `dc6aa22` — `parse_iso_z` stamps UTC on a naive parse; validator requires
  `windWindow.points` strictly increasing and never later than `generated_iso`; `f107.time_iso`
  normalized; the poisoned local `pipeline/.cache/wind.json` deleted; `pipeline/tests/` created
  with the tz table test. **Footgun 52.** The live wind series stays shifted until the next
  scheduled run rebuilds `stats/summary.json` on a UTC runner (or a hand-republish from this
  tree, which now produces correct times).
- **Item 8 DONE** `e92eaeb` — a stage that raised is published `status: degraded` with the
  exception text in `note` and a new `last_error`; a deliberately skipped stage stays `ok` /
  "not regenerated this run"; the stale pfss path carries `data_age_hours`; the pfss manifest
  gains `newest_mag_unix` (additive).
- **Items 5 + 6 DONE** `3ee22b2` — `fieldLines` animates `[from, to]` with `to` the newest
  LOADED frame; `TimeScrubber` gets `loadedTo`/`loadDone`, its max follows the newest loaded
  frame (Vue does not re-patch a range input whose bound value is unchanged, so a thumb dragged
  into the hole used to stay there), the loading label gives up once the load resolved, and a
  "N frame(s) missing" clause follows the stamp. `sunSurface`: `pending` guard on
  `loadTexture`, displaced textures disposed, eviction protects the active and hi-res maps.
  Verified by a Node harness on the compiled module (9 scenarios, 48 assertions) plus
  lint/typecheck/build. **NOT yet seen in a browser** (T8 still blocked).
- **Item 7 DONE** `2bde6b8` — `pipeline/manifest_urls.py` (`iter_manifest_urls`,
  `manifest_url_set`); per-product existence pass in the validator (stat / HEAD→ranged GET) before
  the decode sampling; orphan check behind `check_orphans` (root mode, `cmd_validate` only —
  orphans legitimately exist before pruning); `_prune_orphan_textures` derives its keep-set from
  the walker. Measured 20/20 pfss + 110/110 texture referenced files on disk, 0 orphans. The two
  dead imports at `texture/export.py:77` removed.
- **Item 2 DONE** `d1c5a43` — `validate_products()` → `{product: Report}`; `Tree` /
  `overlay_tree` (staging resolved before published, exactly what `promote()` produces);
  `cli._validate_before_promote` rolls back only the failing product with a `degraded` entry
  and `last_error: "validation failed: …"`; `plan_rollbacks` is pure and iterates consumers of
  a rolled-back producer to a fixed point. **Exit-code contract:** `pipeline all` returns 0
  whenever it promoted and wrote `index.json`; non-zero only when nothing was promoted. 13
  tests including footgun 51's exact record and footgun 50's shape.
- **Item 3 DONE** `1d33584` — `SeedSet.region_numbers` (SRS `rnumber`, persisted in the seed
  npz; an older npz derives it from the `regions_json` it already carries); manifest
  `seed_regions` + `SCHEMA_PFSS = "sol.pfss/2"`, with the validator accepting `{/1, /2}` because
  CI cannot retrace (footgun 33). Hard bound `max(ar_index) < len(seed_regions)`; the
  regions.json comparison is an ADVISORY warn (`Report.warn(strict_fatal=False)`) so `--strict`
  no longer turns a shrunken SRS into a discarded publish. **The live manifest stays `/1` until
  a rebuild from a GONG-reachable machine** — done this session, see below.
- **Item 4 DONE** `0751dfd` — `data.yml`: Build → Publish → Validate (tripwire) → Verdict →
  Notify → Artifact, `issues: write`; `freshness.yml` every 2 h against the live index
  (`pfss.data_age_hours`, thresholds 10 h index / 12 h pfss), issue titles
  `data pipeline: scheduled run failing` and `live data is stale`; README badge. Verified
  locally against the live site and with doctored inputs; **first real run pending the push.**
- **Republished with the new code** (the tenth T1, and the first that was not about
  staleness): `public/data` seeded from `gh-pages` (137 = 137, 0 each way), `pipeline all`
  without texture flags (texture was 1.55 h old and complete) — 19/19 slots, all 19 frames from
  the traced-frame cache in **11.8 s**, the new pre-promote validation printed `OK` for all five
  staged products, exit 0, `validate --root` 0/0. What this run fixed on the live site: the wind
  series' newest point is now **16:00Z against a 16:56Z run** (was 4.61 h ahead), and the pfss
  manifest is `sol.pfss/2` with `seed_regions [4520, 4521, 4522, 4523]`, so footgun 50's fuse
  is out for the served product too. Cost of purging the poisoned cache: the wind series
  restarts at **25 hourly points** (~1 day) and refills over the next runs. Published as
  `gh-pages` **`85230e5`** at 16:58Z, 137 data files, CI idle at push time.
- **Verified in CI after the push** (`68bb960`): `Deploy app` green with all 137 data files
  preserved on `gh-pages` (`9e96172`); `freshness.yml`'s first real run **green** —
  `FRESH: index 0.1 h, pfss data 0.7 h, all 6 products ok`; and a `data.yml` **dry run**
  (run 33658429829) that exercised the whole new shape: Build exit 0 with GONG unreachable
  (`slots: 0/19`, pfss stale, footgun 33), the pre-promote `[validate]` block `OK` for the five
  staged products (texture 1383 checks), Publish skipped (dry run), the post-publish tripwire
  0/0, **`Verdict` FAILED on `last_attempt_status: degraded`**, and `Notify on failure` opened
  the fixed-title issue `data pipeline: scheduled run failing`.
  **Read that last line as the design working, and as a consequence to decide on:** until T2
  lands, every scheduled `data` run will come out RED (pfss is stale on every one of them) and
  will add one comment to that issue, roughly three or four a day. That is the loud signal the
  review asked for in place of eleven sessions of silent staleness — but if the comment stream
  trains people to ignore the issue, the `Notify` step should skip commenting when the previous
  comment is under ~12 h old and names the same stale product. Decide when T2's go-live date is
  known; do NOT quiet it by exempting pfss from `Verdict`.

**Follow-ups this task deliberately left** (from the pipeline agent's report): `run_ephem`'s
own handler still returns `status: stale` for a minutes-old copy (pessimistic, not a lie, but
inconsistent with `_fallback_status`); `python -m pipeline <one stage>` does NOT run the
pre-promote validation, only `all` does; `_check_texture_frames`' pixel sampling is still 3 of
18 frames per channel (presence is now checked for all). Plus review items 9-13.

---

<a id="t21"></a>

### T21 — Review fixes, second batch (items 9-13)  *(DONE)*

**Why.** The five review items T20 left, worked in the same session because the user asked for
Option D next and item 12 (token leaks) gates it: `scripts/gong_mirror.py` writes its GitHub
token into its own error message on a failed push, and a Scheduled Task log is exactly where
that would land.

| item | what | where |
|---|---|---|
| 12 | Token in the publish script's push URL (unmasked when run by hand); token in the mirror's `RuntimeError` text | `scripts/publish_gh_pages.sh`, `scripts/gong_mirror.py` |
| 13 | `max_frames` dispatch input deletes published frames past N | `.github/workflows/data.yml`, `pipeline/cli.py` help + WARN |
| 9 | Vuetify loaded for one `<v-app>`: 85 KB gzip render-blocking CSS + 3.6 MB MDI fonts ahead of the engine-free entry chunk | `plugins/vuetify.ts`, `src/main.ts`, `src/sol.vue`, `vue.config.js`, `package.json` |
| 10 | `setFrameTime` / far-side hysteresis / `updateOffLimb` gated on the ephemeris product loading | `SolarView3D.vue` `updateSpacecraft` → `tick` |
| 11 | T5: `build.yml` never ran; `app-deploy` lacks typecheck and `--immutable`; the two check scripts and the new pytest suite wired to nothing | `build.yml`, `app-deploy.yml`, `package.json` scripts, `pipeline/tests/conftest.py` |

Also in this task: the go-live review of `scripts/gong_mirror.py` (T2 says "treat the diff as
unreviewed") and a `--dry-run` of it, both prerequisites for T2's go-live steps.

**Definition of done:** each item committed with lint/typecheck/build green, `build.yml`
observed running green on `main` after the push (its first run ever), `yarn why vuetify`
empty, and the token redaction covered by a test.

**Progress:**

- **Item 9 DONE** `04b8e02` (+ the `plugins/vuetify.ts` deletion, swept into `30d7ec1` by the
  other agent's broad add — content byte-identical). Measured, production build: render-blocking
  CSS **606,223 → 19,114 B raw** (89,847 → 4,645 gzip); `dist/fonts` **3.6 MB → 93 KB** (the four
  `materialdesignicons-webfont.*` files gone); webpack "app" entrypoint **885 → 265 KiB**;
  `chunk-vendors.js` 236 → 189 KB. Entry chunk still engine-free (0 `THREE.`/`wwtlib` hits in
  `app.*.js` and `chunk-vendors.*.js`). **Vuetify's bundled reset (ress.css + its `html` rule)
  was load-bearing**: `box-sizing: border-box`, `* { margin: 0; padding: 0 }`,
  `button { font: inherit; background: transparent; border: none }`, `line-height: 1.5`,
  `color-scheme: dark`, and `#app`'s text color were all restated explicitly in `common.less`
  after reading them out of the built vendor CSS (footgun 53). `#app` is no longer duplicated.
  Layout verified in a browser at a phone viewport. `yarn why vuetify` still shows ONE
  transitive path via `@cosmicds/vue-toolkit`, which the app imports nowhere — removal
  follow-up below.
- **Item 10 DONE** `fad2c52` — `setFrameTime` + far-side hysteresis + `updateOffLimb()` moved
  from `updateSpacecraft` (lines 1545-1559) into a new `updateSurfaceFrame()` called from
  `tick()`'s throttled block (`PROJECT_MS = 50`) immediately after `updateSpacecraft()`: same
  order, same cadence, no dependency on the ephemeris product. Trap met on the way:
  `unobservedFraction()` returns `number | null`, and dropping the `?? 0` passed `yarn typecheck`
  and failed `yarn build` with three errors — the CLAUDE.md note about `.vue` script blocks,
  confirmed live.
- **Item 11 DONE** (T5) — content in `095122f` (swept, byte-identical). `build.yml` runs on
  `push` to `main` and on PRs, two jobs: **app** (install `--immutable`, lint, typecheck, build,
  `yarn check:labels`) and **pipeline** (`check_pipeline_names.py`, pyflakes with the four
  intentional `sunpy.coordinates` lines filtered, `pytest pipeline/tests`; 20 min timeout).
  `app-deploy.yml`: `--immutable` + a Typecheck step. `package.json`: `check:labels`,
  `check:pipeline`, `test:pipeline`. The three test modules that read `public/data` already
  `skipif` on it — proved by running the suite from a tree with no `public/`: 59 passed, 16
  skipped, 0 failed.
- **Item 12 DONE** `30d7ec1` + `85e626c` — `publish_gh_pages.sh` authenticates with a
  per-invocation `-c http.extraheader` over a PLAIN URL plus `GIT_TERMINAL_PROMPT=0` (proved
  read-only with `ls-remote`; a bogus token fails in 1 s and the `fatal:` line now carries a
  token-free URL — exactly where the old form leaked). `gong_mirror.py`: `_redact_args` /
  `_redact_text` scrub argv and captured output before any error text is built; 3 tests.
- **Item 13 DONE** `095122f` — `max_frames` input and `MAX_FRAMES` plumbing removed from
  `data.yml`; `--max-frames` help + a runtime WARN naming `--out` and N.
- **Mirror go-live review DONE** (`85e626c`, 12 new tests in `pipeline/tests/test_gong_mirror.py`,
  total suite **75 passing**). Findings fixed: (1) an EMPTY state dir force-pushed an empty tree
  over a good branch and only then printed FAILURE — now refuses before `_ensure_local_repo`
  (the mirror-side twin of footgun 31, CLAUDE.md footgun 55); (2) a fresh `git init` inherits
  `core.autocrlf=true` from Git for Windows' SYSTEM config — `* -text` now written to the state
  repo (footgun 54); (3) `index.html` was written in text mode (CRLF on Windows) — now LF bytes;
  (4) a rejected push left only a traceback, no `SUMMARY:` line; (5) a `.format(None)` crash on
  the SUMMARY line when no filename parsed. Verified OK: the synthetic index round-trips through
  the REAL `_scrape_gong` parser back to canonical `gong2.nso.edu` URLs (footgun 37 pinned by
  test); `--retain-days 5` covers `today−4`, the oldest day the pipeline can ask for (4 exact, 3
  leaves a hole); force-push creates the branch on first run and keeps it at one commit; the lock
  releases a dead run after 30 min; env hygiene stops the mirror relaying through itself (proved
  with a bogus relay in the env); `.fits.gz` bytes are verbatim (sha256 against a live
  re-download); the ps1 picks the `sdo` interpreter, rotates to 15 logs, propagates exit codes.
  Dry run: 7 day dirs, **135 files / 31.3 MB in 61 s**, one expected 404 WARN for tomorrow's dir.
- Also this task: `fee65bb` removed `@cosmicds/vue-toolkit` (imported nowhere; the last resolver
  of `vuetify` and `@mdi/font` — `yarn why vuetify` is now empty) and the dead `plugins/*.ts`
  tsconfig include; `c5369c0` fixed the one stale local test (the footgun-50 shape test assumed a
  legacy manifest; against a `sol.pfss/2` manifest `events` is the consumer that fails).
- **Stale test the app agent found, `@live`-only, now fixed** — see `c5369c0` above.
- **`build.yml`'s first run ever** (33664222749, on `a2ae70e`): app job green; pipeline job red
  on ONE timing flake — a new tz test compared two `age_hours()` calls that each read
  `utcnow()`, and the 4 µs between them was 1.1e-9 h against a 1e-9 tolerance. Deflaked in
  `5c0d334` (explicit shared `now`); **run 2 (33664390163) green on both jobs.** T5 is closed
  by this.

---

<a id="t22"></a>

### T22 — The relay's CI read path serves a FROZEN view of `gong-cache`

**Why.** Measured 2026-09-09. `pfss` had been `degraded` on every scheduled run for at least
17 h, and **none of the three things the runbook tells you to suspect was at fault**:

- upstream `gong2.nso.edu` answered this workstation HTTP 200 in 0.18 s, with 24 files on
  09-06/09-08 and 15 on 09-09;
- `SolGongMirror` was `Ready`, `LastTaskResult 0`, running hourly, `+1 new` each run, newest
  mirrored file 09-09T14:04Z;
- the `gong-cache` branch itself was current — commit `18e9ecf` at 14:55:53Z, 133 files across
  6 days, and all four day indexes served **HTTP 200 with the right counts from here**.

What is broken is the **read** side. CI's listing counts were *byte-identical across four runs
spanning 17 hours* (09-05: 71, 09-06: 70, 09-07: 48, 09-08: 24, 09-09: 404 then 1), while a
direct scrape from this workstation at the same moment saw 09-07: 71, 09-08: 63, 09-09: 40.
A frozen, progressively truncated tail — not an outage. The signature is the slot count
decaying as the 72 h window slides past a fixed data cutoff: **15/19 → 14/19 → 12/19 → 10/19**
across successive runs, with `f12`..`f18` dropped as `no GONG within 3.0 h`.

`raw.githubusercontent.com` serves these with `Cache-Control: max-age=300` through Fastly
(`Via: 1.1 varnish`, `X-Served-By: cache-pdk-…`), so the edge a runner hits is not the edge a
workstation hits. A 5-minute TTL does not explain a 17-hour freeze; the exact CDN mechanism is
NOT yet established and should not be guessed at in a fix.

**This is why footgun 33's "resolved by routing around it" is only half true.** The block is
routed around; the mirror is not the single point of failure any more — *the CDN in front of it
is*. And the failure is quiet in the worst way: the mirror's own log says `SUMMARY: OK`, the
branch is verifiably correct, and every diagnostic in `docs/GONG-RELAY.md`'s "Check it" row
passes while CI still starves.

**Options, none yet measured from a runner:**

1. **Cache-bust the request.** Append a throwaway query parameter in `sources/gong.py:_relay`.
   Cheapest, and structurally consistent with footgun 37 (request time only, never stored) —
   but it depends on Fastly keying on the query string, which is unverified here.
2. **Read through the GitHub API** (`/repos/.../contents/...?ref=gong-cache`) with the
   workflow's own token. Not the same CDN path; costs an auth header and a different parser.
3. **Deploy Option A**, the Cloudflare Worker already written in `scripts/gong-proxy-worker.js`.
   Takes both the workstation and `raw.githubusercontent.com` out of the critical path, which
   is what `docs/GONG-RELAY.md` always said the upgrade was for.

**Definition of done:** a *scheduled* `data` run reports `slots: 19/19` and `pfss ok` without a
hand-publish, and the mechanism is written down — including whichever option was rejected and
why, measured rather than assumed.

**Until then** `pfss` will drift back to `degraded` within about a day of each hand-publish, and
`PFSS-UPDATE.md` is the fallback. Do NOT read a red `data` run as a mirror outage without first
checking the workstation, the branch, *and* what CI's log says the listing counts were — the
counts are the tell.

**Twelfth T1, 2026-09-15 — this one WAS a plain mirror outage, not T22's frozen read.**
`pfss` had been `degraded` for 5 straight scheduled runs (2026-09-14T20:16Z .. 09-15T22:51Z),
`data_age_hours` climbing 23.05 -> 49.63. `Get-ScheduledTaskInfo SolGongMirror` showed
`LastRunTime` stuck at 2026-09-13T16:55:52 with `NumberOfMissedRuns 51` — the task's trigger is
`LogonType Interactive` (`scripts/gong-mirror-task.ps1` via Task Scheduler), so it simply cannot
fire while the workstation is off or nobody is logged in, exactly the scenario footgun 55 and
`PFSS-UPDATE.md`'s preflight check ("LastRunTime within the hour") anticipate. The mirror's own
last log (`gong-mirror-20260913-165553.log`) ended clean, `SUMMARY: OK`, so this was not T22's
CDN-freeze signature — the branch just stopped being updated at all.
Ran `PFSS-UPDATE.md` end to end from this workstation (which reaches GONG directly, mirror or
not): seeded `public/data` from `gh-pages` (132 published / 142 local, 90/100 differing each
way), texture was 2.4 h old and complete so option (a) (no `--with-texture`), `pipeline all`
traced `19/19` slots fresh, pre-promote validate `OK` on all 5 staged products, `validate
--root --strict` 0 failed / 0 warnings, published as `gh-pages` **`8d7f91d`**, Pages built in
27 s, live `index.json` confirmed `last_attempt_status: ok` / all six products `ok` / `pfss` age
0.0 h, `validate --url --strict` 0/0.
Also `Start-ScheduledTask SolGongMirror` to resume the hourly mirror now that the workstation is
active — the manual kick's own run exited `0xC000013A` (STATUS_CONTROL_C_EXIT) with no new log,
apparently interrupted by the automation session rather than a real script fault (no orphaned
process afterward); left it alone rather than re-kick a second time; `NextRunTime` is back on
its normal hourly slot (20:55) and unaffected by the failed manual run. Not investigated further
since it's a one-off side effect, not a regression in `gong-mirror-task.ps1` itself — worth
confirming next session that the mirror's hourly log resumed on its own.

**Thirteenth T1, 2026-09-21 — the same plain mirror outage, and the answer to the question the
twelfth left open.** It did NOT resume on its own for long. The mirror's log directory jumped
straight from `gong-mirror-20260917-195553.log` to `gong-mirror-20260920-195553.log` — a 72 h
gap, and decisive because the directory keeps the **last 15 runs**: had the mirror been running
hourly through 09-18..09-20, all 15 would be dated 09-20, and instead 13 of them are 09-17.
So the hourly trigger stopped again roughly two days after the twelfth republish.

**Read the CI counts carefully — this looked exactly like T22 and was not.** Four scheduled runs
(04:44Z, 13:00Z, 18:41Z, 22:22Z on 09-20) reported byte-identical listings of 49/25/1/0 files
while the slot count decayed **6/19 → 4/19 → 3/19 → 2/19**, which is T22's published signature.
The distinguishing evidence is the mirror, not the branch: with the mirror stopped the branch was
*genuinely* frozen, so identical counts are the expected reading, not a CDN artifact. A check of
the `gong-cache` branch at 02:00Z on 09-21 showed 25 files for every day including 09-20 and
looked like proof of T22 — but the mirror had already caught up at 00:55Z and 01:55Z, **after**
the last of those CI runs. **A branch check only bears on T22 if it is taken while the mirror is
confirmed to have been running throughout the window the CI runs covered.** Check
`Get-ScheduledTaskInfo` and the log directory's date spread first; they are what separate the
two causes.

`Get-ScheduledTaskInfo SolGongMirror` is NOT sufficient on its own here: it read `LastRunTime
2026-09-20 20:55:52`, `LastTaskResult 0`, `NumberOfMissedRuns 0` — all healthy-looking — because
the task had resumed an hour earlier and Task Scheduler does not count runs it never attempted
while the machine was off. The **log directory's date spread** is the reliable tell.

Ran `PFSS-UPDATE.md` end to end: seeded `public/data` from `gh-pages` (129 published / 142 local,
90 published-only and 103 local-only — five days of drift, footgun 31), texture 3.7 h old and
complete on all five layers (19 frames, `high_res 8192`) so option (a), no `--with-texture`.
`pipeline all` traced **19/19 slots within 3 h**, 19 frames / 1,261 lines / 17,234 verts /
1.93 MB, dequant err 3.97e-05 R_sun, 263.9 s. Pre-promote validate `OK` on all five staged
products (pfss 504 checks), `validate --root --strict` 0 failed / 0 warnings, 26 files published.
Live as `gh-pages` **`77f5e24`**, Pages built in 23.5 s; live `index.json` reports
`last_attempt_status: ok`, all six products `ok`, `pfss` 0.0 h, texture 3.74 h with
`not regenerated this run` (correct under option (a)); `validate --url --strict` 0 failed /
0 warnings.

**One self-inflicted error worth copying down:** `publish_gh_pages.sh` printed nothing on its
first invocation, which was mistaken for a failure, and it was run a **second** time seconds
later. Both pushes auto-triggered a Pages build; the first (`ebb42a6`) came back `errored --
Page build failed` because the second push had already replaced the commit it was building.
This is footgun 49's mechanism reached without any explicit `POST /pages/builds` — two pushes
race just as a push and a POST do. The second build (`77f5e24`) was the branch head and built
cleanly, so the live outcome is correct. **The script is silent on success; check
`git log origin/gh-pages` before re-running it.**

**Fourteenth T1, 2026-09-22 — mirror down a third time, and a silent hi-res drop.** Live `pfss`
was `degraded`: `data_age_hours` **42.5**, 11 frames, scheduled run 35775476229 red. The mirror's
last log was `gong-mirror-20260920-205553` (~44 h before; the log directory's spread, footgun 56).
Seeded from `gh-pages` (130 published / 142 local, 51 published-only, 63 local-only). Texture was
1.9 h old but HMIIC/HMIB held 17/19 frames, so option (b) per the runbook. `pipeline all
--with-texture --with-hires` traced **19/19 slots**, 19 frames / 1,326 lines / 18,954 verts /
2.12 MB, 276.5 s; all six products passed pre-promote validation — **but 0171's hi-res map was
skipped with `Unable to allocate 768. MiB`**, leaving the default channel with no `high_res`
block while validate stayed green (new footgun 57). A second run, `pipeline texture --with-hires`
alone, built all five hi-res maps (0171 1.31 MB, 59.2 s). The 17/19 on HMIIC/HMIB is `4
unavailable upstream` and was left as is. `validate --root --strict` 0/0; live as `gh-pages`
**`ef1a1e3`**, Pages built in 28.8 s; live `index.json` `last_attempt_status: ok`, all six `ok`;
`validate --url --strict` 0 failed / 0 warnings.

**Fifteenth T1, 2026-09-30 — mirror down a fourth time, and DONKI moved.** Live `pfss` was `stale`:
age 52.0 h, `data_age_hours` **102.5**, `0 freshly traced frame(s) of 19 slot(s)`. The two latest
`data` runs (36732332563, 36774753094) were red. The mirror's log directory jumps from
`gong-mirror-20260926-095553` to `gong-mirror-20260930-201131` (local time), a ~106 h gap. It had
resumed about an hour before this check, after CI's 20:44Z run (footgun 56). Seeded from
`gh-pages`: 71 published / 138 local, 30 published-only, 97 local-only. Texture was 5.3 h old,
but AIA held 11/19 frames and HMI 1/19, so option (b). `pipeline all --with-texture --with-hires`
traced **19/19 slots**: 19 frames / 1,228 lines / 17,976 verts / 2.01 MB, 247.5 s. **All five
`hi-res 8192` lines** were present this time (footgun 57 did not recur). Texture history came
out as 27 reused, 3 built, **60 unavailable upstream**. Two SDO gaps cause that: AIA has no
browse frames from 2026-09-28T16Z to 09-29T20Z, and the HMI browse product has been stuck at
**2026-09-21T15:50Z** for nine days (`latest_*_HMIB.jpg` `Last-Modified`), so HMIIC/HMIB carry
only the newest frame. That data gap also fails
`test_walker_finds_every_texture_file_on_disk`, which wants more than 100 texture files in
`public/data` and found 55. The other 74 tests pass.
`events` came out `degraded` because CCMC retired the `kauai` DONKI base on 2026-09-30
(footgun 58). Pointed `DONKI_BASE` at `ccmc.gsfc.nasa.gov/DONKI-API/get/` (`1bc2081`) and re-ran
`pipeline events`: 1 flare, 7 CMEs, 2/2 AR matches. `validate --root --strict` 0/0. Live as
`gh-pages` **`ef9d547`**, and Pages built in 26.5 s. Live `index.json` reports
`last_attempt_status: ok` with all six `ok`, and `validate --url --strict` is 0 failed /
0 warnings. CI picks the DONKI fix up from `main` on its next run.

---

<a id="t23"></a>

### T23 — Desktop seam + info copy (asked for 2026-09-11)

Two guest-facing asks made in passing while the planet labels were being landed, both DONE
the same day; the measurements and the reasoning are in HANDOFF §3zzzzzzzzzzzzzzzz.

- **`e741321` — the desktop scrubber lines up with the stats panel.** Before: scrubber bottom
  5.6px below the stats panel's, and 26.4px between them against 12px between rail panels
  (0.4rem phone inset + 0.5rem grid column-gap + 0.75rem rail margin, stacked on one seam).
  After: bottoms equal, every seam in the wide layout 12px from the one `--sol-rail-gutter`
  token. `SolarView3D`'s root carries `is-wide`; the phone values are unchanged.
- **`bcd35c9` — "What am I looking at?" rewritten in plain sentences**, as a docent would say
  it. Also corrects "usually only a few minutes old" (the globe's texture is hours old), names
  the Spacecraft / Planet orbits labels and the AR chips as tappable, and keeps the far-side
  and DONKI caveats in the same voice.

**Left for T4/T12:** the two "Sun Now still works" error strings (`sol.vue`, `SolarView3D.vue`)
name a view that was deleted.

**Definition of done:** met. Verified in a 1920x911 window; not seen on a phone (T8).
