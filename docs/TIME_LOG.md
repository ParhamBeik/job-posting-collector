# Time log

Actual working time per step is Parham's to confirm. The commit span shows when each step's
commits landed (Tehran time, from `git log`); it is a fact from the history, not a work-time claim.

| Step | Date | Commit span (Tehran) | Time | Notes |
|---|---|---|---|---|
| 0 · Reading the brief, site research, plan, issues | 2026-10-07 | until 20:20 | _to confirm_ | Live site exploration, `PLAN.md`, issues #1–#8 |
| 1 · Skeleton, fixtures, CI, docs | 2026-10-07 | 20:19–20:55 | _to confirm_ | PR #9 |
| 2 · Dates, Tehran/UTC window, normalization | 2026-10-07 | 20:59–21:09 | _to confirm_ | PR #10 |
| 3 · eng-estekhdam adapter, fixtures, tag mapping | 2026-10-07 | 21:16–21:50 | _to confirm_ | PR #11 |
| 4 · SQLite storage, runs and issues | 2026-10-07/08 | 21:53 – 14:55 next day | _to confirm_ | PR #12 (overnight pause) |
| 5 · Collect command: fetching, stop rule, statuses | 2026-10-08 | 15:10–15:57 | _to confirm_ | PR #13 |
| 6 · HTTP API: search, tags, stats, runs, Collect now | 2026-10-08 | 16:02–16:17 | _to confirm_ | PR #14 |
| 7 · Web page: search, detail, run monitor, Collect now, XSS test | 2026-10-08 | 16:21–16:49 | _to confirm_ | PR #15 |
| 8 · Live run, design doc, README, clean-clone check | 2026-10-08 | from 16:50 | _to confirm_ | this PR |

## Unfinished work and known limitations

- Designed but not built: health drift alert, layout fingerprint, daily smoke run, per-source
  on/off switch (`docs/DESIGN.md`).
- One source only; runs are started by hand; no login (server stays on `127.0.0.1`).
- Within one Tehran day, order follows the site's post IDs, since the site shows no times.
- Members-only contact details are never collected.
