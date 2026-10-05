# Republish log

One line per hand-publish of the data tree from the workstation (`PFSS-UPDATE.md`). New failure
modes go in `CLAUDE.md` as footguns, not here. Add a row, keep it to one line, and put the
story in the commit message.

Columns: run number (T1 numbering), date and time in UTC where recorded, the `gh-pages` commit,
how stale `pfss` was on the live `index.json` before the run, the cause, the PFSS slots traced,
and anything a later run should know. Gathered on 2026-10-05 from `TASKS.md` T1/T20/T22 (now in
`docs/tasks-archive.md`), `HANDOFF.md`'s session sections (now in `docs/handoff-archive/`) and
`git log`.

| # | Date (UTC) | `gh-pages` | pfss before | Cause | Slots | Notes |
|---|---|---|---|---|---|---|
| 0 | 2026-08-24 | not recorded | stale, age not recorded | GONG unreachable from CI (footgun 33) | 19/19 | before T1 existed; `handoff-archive/2026-08.md` §3zzz |
| 1 | 2026-08-25 20:54Z | `cb0ba1a` | stale 26 h (newest frame 30.1 h) | footgun 33 | 19/19 | texture not regenerated; seed proved necessary (132 vs 117 files) |
| 2 | 2026-08-26 07:07Z | `94fbdfb` | stale 8.0 h | footgun 33 | 19/19 | full `all` run; commit `b130ff4` |
| 3 | 2026-08-26 ~15:09Z | not recorded | not recorded | footgun 33, plus the off-limb ladder | 19/19 | commit `90cd733`; the Pages build race that became footgun 49 |
| 4 | 2026-08-27 15:50Z | `e6e22d9` | stale 18.3 h | footgun 33 | 19/19 | commit `6761ad8` |
| 5 | 2026-08-29 17:39Z | `4e80021` | stale 46.1 h | footgun 33 | 19/19 | commit `1394128` |
| 6 | 2026-08-30 11:59Z | `98536eb` | stale 18.2 h; index 13.2 h old | footgun 33; stale seeds failed `Validate` and blocked the whole publish (footgun 50) | 19/19 | commit `f618e0f`; `PFSS-UPDATE.md` written |
| 7 | 2026-08-31 16:22Z | `c0d0f1f` | stale 17.6 h; index 10.8 h old | footgun 33; GitHub skipped two cron slots | 19/19 | commit `d270ed3`; runbook corrected in eight places |
| 8 | 2026-09-01 16:40Z | `5f915030` | stale 12.66 h; index 11.5 h old | footgun 33; NOAA region at latitude 98 blocked the publish (footgun 51) | 19/19 | commit `777b85d` |
| 9 | 2026-09-02 15:36Z | `726f69a` | stale 22.92 h | footgun 33 | 19/19 | commit `c2cd7fc`; wind series found 5 h in the future (footgun 52) |
| 10 | 2026-09-02 16:58Z | `85230e5` | just republished | T20 fixes needed a retrace (`seed_regions`, clean wind cache) | 19/19 from cache | commit `68bb960`; relay went live the same day (T2) |
| 11 | 2026-09-09 | `ac6b53d` | degraded 36.7 h | CI read a frozen view of `gong-cache` (T22); mirror fine | 19/19 | `handoff-archive/2026-09.md` §3zzzzzzzzzzzzzzz |
| 12 | 2026-09-15 | `8d7f91d` | degraded 49.6 h | mirror down ~53 h, interactive-logon gate (footgun 56) | 19/19 | commit `84cd84a` |
| 13 | 2026-09-21 | `77f5e24` | stale 66.6 h; CI 3/19 | mirror down 72 h, same gate (footgun 56) | 19/19 | commit `3669666`; `Get-ScheduledTaskInfo` read healthy |
| 14 | 2026-09-22 | `ef1a1e3` | degraded 42.5 h, 11 frames | mirror down ~44 h (footgun 56) | 19/19 | commit `2a65067`; 0171 hi-res dropped by a MemoryError, rebuilt (footgun 57) |
| 15 | 2026-09-30 | `ef9d547` | stale 102.5 h; CI 0/19 | mirror down ~106 h (footgun 56) | 19/19 | commit `319729b`; DONKI API moved, fixed in `1bc2081` (footgun 58) |
