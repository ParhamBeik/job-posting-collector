# Time log

All times are Tehran time. They come from the timestamps of the Claude Code sessions for this
repository: the main session ("Candidate assignment review"), a second one used to set up the
Codex review workflow, and the review session of step 9. Re-checked on 9 Oct: the times of
7 and 8 Oct in the transcripts are unchanged. Step boundaries are the moments I asked for the next step or a merge.

```text
7 Oct  17:58 ████████████████████████████████████ 22:16    4 h 18 min  plan, steps 1–4
8 Oct  13:31 █████████████████████████████ 17:02           3 h 31 min  steps 4–8
8 Oct  21:56 ███ 22:15                                        19 min   step 8 page fixes
                                                          ≈ 8 h 10 min  steps 0–8
8 Oct  22:25 ████ 22:58                                         33 min   step 9 self-review
9 Oct  12:47 ████ 13:15                                       28 min   step 9 final pass
                                                          ≈ 9 h 10 min  in all
```

| Step | When | Time | What |
|---|---|---|---|
| 0 · Brief, site research, plan, issues | 7 Oct 17:58–20:18 | 2 h 20 min | Live site exploration, `PLAN.md`, issues #1–#8. The Codex workflow was set up in parallel (19:53–20:07) |
| 1 · Skeleton, fixtures, CI, docs | 7 Oct 20:18–20:56 | 38 min | PR #9 |
| 2 · Dates, Tehran/UTC window, normalization | 7 Oct 20:56–21:09 | 13 min | PR #10 |
| 3 · eng-estekhdam adapter, fixtures, tag mapping | 7 Oct 21:09–21:47 | 38 min | PR #11 |
| 4 · SQLite storage, runs and issues | 7 Oct 21:47–22:16, 8 Oct 13:57–14:55 | 1 h 27 min | PR #12; on 8 Oct this includes my private Codex review of PR #12 (its finding is in the PR thread) |
| — · Fixing the Codex review workflow | 8 Oct 13:31–13:57 | 26 min | Second session; `docs/WORKFLOW.md` |
| 5 · Collect command: fetching, stop rule, statuses | 8 Oct 14:55–15:56 | 1 h 01 min | PR #13 |
| 6 · HTTP API: search, tags, stats, runs, Collect now | 8 Oct 15:56–16:17 | 21 min | PR #14 |
| 7 · Web page, run monitor, Collect now, XSS test | 8 Oct 16:17–16:49 | 32 min | PR #15 |
| 8 · Live run, design, README; page font, phone layout, industry chart | 8 Oct 16:49–17:02, 21:56–22:15 | 32 min | PR #16 |
| **Total, steps 0–8** | | **≈ 8 h 10 min** | |
| 9 · Self-review against the brief, fixes, docs | 8 Oct 22:25–22:58 | 33 min | Host check, two run-report fixes, this time log, shorter docs |
| 9 · Final pass: Parham's answers, live pacing test, odd-input and browser tests, fresh-clone check, reviewer docs | 9 Oct 12:47–13:15 | 28 min | Same PR; the pull request was opened right after |
| **Total, all steps** | | **≈ 9 h 10 min** | |

Most build steps are short because Claude Code wrote the code; my time went into the plan,
questions, review of each PR and Codex's findings, and checks against the live site.

An earlier version of this log said "about 7 h 30 min", written from memory, and left the 8 Oct
evening out as "not counted". It now counts every session.

## Unfinished work and known limitations

- Designed but not built: health drift alert, layout fingerprint, daily smoke run, per-source
  on/off switch, and a second read of the listing pages to catch an ad hidden by a deletion
  during a run (`docs/DESIGN.md`).
- One source only; runs are started by hand; no login (server stays on `127.0.0.1`).
- Within one Tehran day, order follows the site's post IDs, since the site shows no times.
- Members-only contact details are never collected.
