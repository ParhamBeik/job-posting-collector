# Live collection runs

Two recorded checks against https://eng-estekhdam.com/, each from a **fresh clone**, following
the README only. Nothing below was edited by hand except the layout.

| | 8 Oct (first live run) | 9 Oct (final check before submission) |
|---|---|---|
| Code | `main` after PR #15 | branch `step-9-review-fixes` |
| Python | 3.12.13 | 3.12.13 (tests also pass on 3.14.6) |
| Window (Tehran) | 2026-10-02 .. 2026-10-08 | 2026-10-03 .. 2026-10-09 |
| Pacing | 1 request per second | 2 requests per second |
| Result | `success`, 69 new, 76 requests, 1 min 17 s | `success`, 63 new, 70 requests, 38.6 s |
| Run again | 67 unchanged (earlier database) | 63 unchanged, twice (terminal and **Collect now** on the page) |
| Issues | none | none |

## Final check from a fresh clone (2026-10-09)

```text
$ git clone … && cd job-posting-collector        # branch step-9-review-fixes
$ uv venv --python 3.12 .venv && source .venv/bin/activate && uv pip install -e ".[dev]"
$ python -m playwright install chromium
$ pytest                                          316 passed
$ python -m collector init-db                     database ready: var/jobs.db
$ python -m collector collect                     # started 2026-10-09T09:36:19Z (13:06 Tehran)
run 1: SUCCESS
window: 2026-10-03 .. 2026-10-09 Tehran = 2026-10-02T20:30:00Z .. 2026-10-09T20:30:00Z (end excluded)
pages: 7 listing, 63 posting
postings in window: 63 found, 63 new, 0 updated, 0 unchanged, 0 rejected
issues: none                                      # exit 0, 38.6 s
$ python -m collector collect                     # run 2
postings in window: 63 found, 0 new, 0 updated, 63 unchanged, 0 rejected
$ python -m sqlite3 var/jobs.db "SELECT count(*), count(DISTINCT source_post_id) FROM postings"
(63, 63)                                          # no duplicates
```

Then `python -m api`, and on `http://127.0.0.1:8000/`: **Collect now** started run 3 (progress
line updating, then `success`, 63 unchanged); no console errors; `/docs` rendered. Every example
query in the README answered:

```text
GET /api/postings?date_from=2026-10-08&date_to=2026-10-08                   total 7
GET /api/postings?tag=civil                                                 total 44
GET /api/postings?q=autocad                                                 total 11
GET /api/postings?q=AutoCAD&tag=civil&date_from=2026-10-02&date_to=2026-10-08   total 4
GET /api/postings?tag=civil&date_from=2026-10-03&date_to=2026-10-05         total 20
GET /api/postings?q=مهندس عمران                                            total 14
GET /api/postings?tag=تهران&page=2&page_size=10                              total 31
POST /api/runs without the header                                           403
GET /api/tags with Host: evil.example                                       400
GET http://localhost:8000/api/tags                                          200
```

In the same clone, a second environment made with plain `python3 -m venv` on Python 3.14.6 also
passes all 316 tests. The README screenshots were taken from this database with `scripts/screenshots.py --db`.

The pacing was halved only after one separate live run at 0.5 s (2026-10-09, scratch database):
70 requests in 42.7 s, every answer HTTP 200, no firewall challenge; response times median 0.32 s,
90th percentile 0.80 s, slowest 1.88 s.

## Order compared with the site

On 2026-10-09 the order of the running app (`GET /api/postings?page_size=100`, 63 postings after a
live run) was compared with the site's own listing pages 1–7, read live (7 requests):

```text
in the window on the site and in the app:   63 = 63   (none missing, none extra)
same position:                              62 of 63
the one difference (3 Oct = 11 Mehr):
  site  … 204971  204966  204968  204964 …
  app   … 204971  204968  204966  204964 …
```

The site orders ads by an exact publish time that its HTML does not show; the app orders by the
Tehran day, then by post ID (creation order). Ad 204966 was created before 204968 but published
after it, so the site lists it first and the app second. Nothing else differs. The brief allows
only HTML, so this is kept and documented rather than worked around.

---

# First live run (2026-10-08)

One real run made from a **fresh clone** of `main` (merge of PR #15) by following the README
only, then checked against the site by an independent script.

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
| Requests | 76 = 7 listing pages (10 ads each: 70 cards seen, 69 in the window, the 70th older, which stops the reading) + 69 posting pages (one per ad, for its full text); at least 1 s apart, 1 min 17 s in total |
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
