# Time log

Working time as Parham reported it: 2026-10-07 from about 18:00 to 22:00 and 2026-10-08 from
13:30 to 17:00 (Tehran time), about **7 h 30 min** of focused work; lighter follow-up later on
2026-10-08 is not counted. The split per step follows the commit times in `git log`.

| Step | Date | Time (approx.) | Commits (Tehran) | Notes |
|---|---|---|---|---|
| 0 · Reading the brief, site research, plan, issues | 2026-10-07 | 2 h 20 min | until 20:20 | Live site exploration, `PLAN.md`, issues #1–#8 |
| 1 · Skeleton, fixtures, CI, docs | 2026-10-07 | 35 min | 20:19–20:55 | PR #9 |
| 2 · Dates, Tehran/UTC window, normalization | 2026-10-07 | 15 min | 20:59–21:09 | PR #10 |
| 3 · eng-estekhdam adapter, fixtures, tag mapping | 2026-10-07 | 40 min | 21:16–21:50 | PR #11 |
| 4 · SQLite storage, runs and issues | 2026-10-07/08 | 1 h 35 min | 21:53–22:15, 14:53–14:55 | PR #12; next day 13:30–14:55 incl. the Codex finding and questions |
| 5 · Collect command: fetching, stop rule, statuses | 2026-10-08 | 1 h | 15:10–15:57 | PR #13 |
| 6 · HTTP API: search, tags, stats, runs, Collect now | 2026-10-08 | 20 min | 16:02–16:17 | PR #14 |
| 7 · Web page: search, detail, run monitor, Collect now, XSS test | 2026-10-08 | 35 min | 16:21–16:49 | PR #15 |
| 8 · Live run, design doc, README, clean-clone check | 2026-10-08 | 10 min + light follow-up | from 16:50 | PR #16 (page redesign and fixes in the evening, not counted) |
| **Total** | | **≈ 7 h 30 min** | | |

## Unfinished work and known limitations

- Designed but not built: health drift alert, layout fingerprint, daily smoke run, per-source
  on/off switch (`docs/DESIGN.md`).
- One source only; runs are started by hand; no login (server stays on `127.0.0.1`).
- Within one Tehran day, order follows the site's post IDs, since the site shows no times.
- Members-only contact details are never collected.
