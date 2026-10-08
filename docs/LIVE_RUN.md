# Live collection run

One real run against https://eng-estekhdam.com/, made from a **fresh clone** of `main` (merge of
PR #15) by following the README only, then checked against the site by an independent script.
Nothing below was edited by hand except the layout.

## The run

```text
$ python -m collector init-db
database ready: var/jobs.db

$ python -m collector collect          # started 2026-10-08T13:21:06Z (16:51 Tehran)
run 1: SUCCESS
window: 2026-10-02 .. 2026-10-08 Tehran = 2026-10-01T20:30:00Z .. 2026-10-08T20:30:00Z (end excluded)
pages: 7 listing, 69 posting
postings in window: 69 found, 69 new, 0 updated, 0 unchanged, 0 rejected
issues: none
exit code: 0                           # ended 2026-10-08T13:22:23Z, 1 min 17 s
```

| | |
|---|---|
| Window (Tehran) | 2026-10-02 .. 2026-10-08 = ۱۰ to ۱۶ مهر ۱۴۰۵, today and the 6 days before |
| Window (UTC, stored and queried) | `2026-10-01T20:30:00Z` ≤ published_at < `2026-10-08T20:30:00Z` |
| Status | `success`, exit code 0 |
| Requests | 76 (7 listing pages, 69 posting pages), at least 1 s apart, 1 min 17 s in total |
| Postings | 69 found in the window, 69 stored, 0 rejected |
| Failed pages / invalid records | none (`run_issues` is empty for this run) |
| Health numbers | 10.0 cards per listing page; date OK 100 %; body OK 100 %; tags OK 100 % |
| Parser version | `eng-estekhdam/1` |
| Blockers | none: no firewall challenge and no login was met; the members-only contact block (`rcp_restricted`) was left out of every body, as designed, and flagged on all 69 rows |

Postings per Tehran day (from `GET /api/stats`):

| Tehran day | Jalali | Postings |
|---|---|---|
| 2026-10-02 | 1405-07-10 | 6 |
| 2026-10-03 | 1405-07-11 | 14 |
| 2026-10-04 | 1405-07-12 | 8 |
| 2026-10-05 | 1405-07-13 | 3 |
| 2026-10-06 | 1405-07-14 | 22 |
| 2026-10-07 | 1405-07-15 | 9 |
| 2026-10-08 | 1405-07-16 | 7 (the day was not over) |

Stored: 69 postings, 173 tags (17 provinces, 10 fields). Top tags: عمران 47, تهران 34, معماری 17,
نقشه برداري 17, راه ترابری 9, خراسان رضوی 7.

## Independent check against the site

A separate script (not using the collector's parsing code: plain regular expressions and its own
Jalali conversion) re-read the listing pages and every posting page, one request per second, and
compared them with the database:

```text
window from run row: 2026-10-02 .. 2026-10-08 Tehran
site: 69 ads in the window over 7 listing pages
db: 69 postings; missing from db: []; not on site now: []
re-read 69 posting pages
problems: none
```

It checked, for every row: the post ID appears on its own page; title equals the page's `<h1>`;
URL equals the card link; Tehran day equals the card date; `published_at` is 00:00 Tehran inside
the window; stored tag labels appear on the page; the body starts with text from the page and has
no markup, script or members-only block; every timestamp is ISO 8601 UTC with `Z`.

## API on the live data

```text
GET /api/postings?tag=civil&date_from=2026-10-03&date_to=2026-10-05      total 20
GET /api/postings?q=مهندس عمران                                         total 15
GET /api/postings?tag=تهران&page=2&page_size=10                           total 34, 10 items
GET /api/postings?date_from=2026-10-08&date_to=2026-10-08                total 7
GET /api/postings?q=AutoCAD&tag=civil&date_from=2026-10-02&date_to=2026-10-08   total 5
GET /api/postings?date_from=2026-02-30
  422 {"detail":"date_from must be a real date written YYYY-MM-DD (Tehran day), got '2026-02-30'"}
```

On an earlier live database of the same day, every API answer was compared with SQL: all postings
reachable by paging, newest first; every detail equal to its row; per-day counts, all 27 tag
filters (slug and Persian label) and four keyword searches equal to direct SQL counts.

## Collect now and a dead run, live

On that earlier database, through the API:

- `POST /api/runs` without the header → 403; with `X-Collect-Trigger: 1` → 202, run 2; again
  while it ran → 409 pointing at run 2. Run 2 finished `success`, 67 unchanged, no issues.
- A third run was started and its process killed on purpose 6 s in (13:16:11Z). At 2 minutes the
  run still showed `running`; after 3 minutes without a heartbeat it was `failed` with
  `UNEXPECTED_ERROR: no sign of life for 3 min: the process stopped without finishing`, and
  Collect now worked again (202; that run finished `success`, 1 new, 67 unchanged).
- The page (`/`), `/docs` and `/redoc` were opened in a browser on this data with no console errors.

## Offline replay (for comparison)

The committed snapshot of the site (captured 2026-10-07T17:00:00Z) replays without network:

```bash
python -m collector --db var/replay.db collect --from-dir tests/fixtures/eng_estekhdam/snapshot --now 2026-10-07T17:00:00Z
```

It reports `success`, 68 postings for 2026-10-01..07 Tehran, the same number a raw-HTML count of
those pages gives (`tests/test_collect.py`).
