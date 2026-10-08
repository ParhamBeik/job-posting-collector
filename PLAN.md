# Build plan: job posting collector

Agreed build plan. Every requirement sentence
of the brief maps to a row in section 13. Site facts were observed live on 2026-10-07 (15 Mehr 1405).

## 1. What we are building

One command collects the last 7 Tehran calendar days of postings from eng-estekhdam.com into
SQLite. An HTTP API searches them and reports run health. One HTML page calls the API to search
postings and to monitor collection runs.

```
eng-estekhdam.com ──HTML──▶ Collector ──upsert──▶ SQLite ──SQL──▶ API ──JSON──▶ Web page
saved fixtures ────HTML──▶ (same code path, used by tests)          (search + run monitor)
```

Stack: Python 3.12, `httpx` (HTTP with timeouts), `beautifulsoup4` + `lxml` (HTML parsing),
`jdatetime` (Persian calendar), `zoneinfo` + pinned `tzdata` (Asia/Tehran), `sqlite3` (stdlib),
FastAPI + uvicorn (API and static page), `pytest`, `pytest-playwright` (one browser test only).
The page uses no front-end framework and no CDN: plain HTML, CSS and JavaScript.

## 2. Facts about the source (observed, not assumed)

| Fact | Evidence | Consequence |
|---|---|---|
| WordPress, theme "typology" | `<meta name="generator">`, body classes | Stable CSS classes to target |
| Listing: `/` then `/page/N/`, 10 cards per page, newest first | pages 1–20 fetched | Walk pages until a card is older than the window |
| Window on 2026-10-07 ≈ 70 postings, pages 1–7 | per-day counts 15→8, 14→22, 13→3, 12→8, 11→14, 10→6, 9→6 | Live run ≈ 80 requests ≈ 2 min at 1 req/s |
| Card date only: `<div class="post-date-hidden">۱۵ مهر ۱۴۰۵</div>`, Persian digits, no time | listing + posting HTML; no `article:published_time`, no JSON-LD | Midnight-Tehran storage convention for every posting |
| URL contains the Jalali date: `/1405/07/15/<slug>/` | every posting URL | Independent cross-check of the card date |
| Stable WordPress post ID in article class: `post-205122` | listing and posting page | Identity key for de-duplication |
| Labels in article class: `category-<province>`, `tag-<field>` | `category-kerman tag-civil tag-surveying` | Per-posting tags; Persian labels from `rel="tag"` links |
| Listing excerpt is cut off with "..." | card `entry-content` | Fetch each posting page for the full body |
| Posting page = main ad + 5 related ads with the same `typology-post` class | 6 articles on one page | Select only `article.typology-single-post` |
| Members-only block `div.rcp_restricted` hides contact details | posting page | Exclude; record as access limit; never log in |
| "Report this ad" widget `div.wprc-container` inside the body | posting page | Strip from body |
| `/page/99999/` returns **HTTP 200** with 0 articles | live probe | Zero cards ≠ "no postings" (code `LISTING_EMPTY_EARLY`) |
| Server header `BitNinja-WafPro` (firewall) | response headers | Possible challenge page with HTTP 200 (code `BLOCKED_CHALLENGE`) |
| Some labels use Arabic letters (`نقشه برداري`) | tag label | Normalize ي→ی, ك→ک for search and tag matching |
| RSS `/feed/`: 40 newest items, title, link, exact UTC `pubDate`, province; no full body | fetched once to understand the site | **Not used** (brief forbids feeds); explains why HTML has no time |
| `/wp-json/` exists; request timed out | probe | **Not used** (brief forbids source APIs) |

## 3. Dates and time zones

- Tehran is UTC+03:30 all year (no DST since 2022). Use `zoneinfo("Asia/Tehran")` with pinned
  `tzdata`, never a hard-coded offset.
- **Today** = `now(Asia/Tehran).date()`, computed once at run start.
- **Window** = Tehran days `today-6 … today`; UTC bounds `[00:00 Tehran today-6, 00:00 Tehran today+1)`.
- **Conversion**: `۱۴ مهر ۱۴۰۵` → `14/7/1405` → `2026-10-06` → `2026-10-06T00:00+03:30` → stored
  `2026-10-05T20:30:00Z`.
- README sentence: "00:00 Tehran is a storage convention; the source page shows only a date."
- Trap test: clock frozen at 2026-10-08 01:00 Tehran (= 2026-10-07T21:30Z) → today must be 2026-10-08.

## 4. Data model

```
postings
  id, source, source_post_id        UNIQUE(source, source_post_id)
  url                               http(s) only, on the source's domain
  title, body                       plain text
  published_at                      UTC 'Z' (midnight-Tehran convention)
  collected_at                      UTC, first stored
  updated_at                        UTC, last content change
  last_seen_at                      UTC, last run that saw it
  content_hash                      sha256(title, body, date, tags): detects edits
  search_text                       normalize(title + "\n" + body)
  parser_version                    e.g. 'eng-estekhdam/1': which parser produced the row
  members_only_omitted              1 if the source hid part of the posting (contact details)

posting_tags (posting_id, kind 'province'|'field', slug 'civil', label 'عمران')

runs   (id, source, started_at, finished_at, window_start, window_end, status,
        pages_listing, pages_posting, new, updated, unchanged, rejected,
        cards_per_page_avg, body_ok_pct, date_ok_pct, tags_ok_pct, parser_version)

run_issues (run_id, severity 'error'|'warning', stage, code, url, detail, snapshot_path)
```

Identity is `(source, source_post_id)`, not the URL: the URL slug is derived from the title and
changes if the title is edited.
Change handling: same ID + new hash → update, set `updated_at`; same hash → touch `last_seen_at`.
Never deleted. **Never overwrite a stored non-empty field with an empty one** (a broken parser
must not erase good data).

## 5. Collection frequency and pacing

| Question | Answer |
|---|---|
| How often does collection run? | Only when a person starts it: by typing `python -m collector collect`, or by pressing **Collect now** on the page (§11), which launches that same command. The brief requires a manual start and says scheduling is not required. |
| Recommended cadence | Once a day. Each run covers 7 days, so a missed day loses nothing. The README shows a one-line cron example as an optional idea (not built). |
| Running twice in a row | Safe: upsert matches post IDs, so a second run reports `unchanged`, never duplicates. |
| Two runs at the same time | Prevented: one storage function `start_run()` refuses if another run row is `running` and alive. A run refreshes `heartbeat_at` after every page request; no heartbeat for 3 min (about twice the longest healthy silence, one request with all retries ≈ 97 s) means the process died, and the run is marked `failed`, also when the API reads runs, so the page never waits on a dead run. The command and the button both go through it. |
| Requests per run | ≈ 7 listing pages + ≈ 70 posting pages ≈ 80 requests. |
| Speed inside a run | 1 request per second, one at a time (no parallel requests). ≈ 2 minutes. |
| Timeouts / retries | 10 s connect, 20 s read; up to 3 attempts with 2 s then 4 s waits; only for timeouts, connection errors, 429 and 5xx. |
| Identity | Honest User-Agent: `job-posting-collector/0.1 (+https://github.com/ParhamBeik/job-posting-collector)`. |

## 6. Errors: exact codes instead of a vague "partial"

Every problem is one `run_issues` row: **severity**, **stage**, **code**, **URL**, **detail** and
a **saved HTML snapshot** where there is a page. The summary groups by code with counts, so
"partial" always comes with exactly which codes caused it.

| Stage | Code | Severity | Meaning |
|---|---|---|---|
| fetch | `FETCH_TIMEOUT` | error | No answer within 20 s after all retries |
| fetch | `FETCH_CONNECTION` | error | DNS, TLS or connection reset after all retries |
| fetch | `HTTP_RATE_LIMITED` | error | 429 after all retries |
| fetch | `HTTP_SERVER_ERROR` | error | 5xx after all retries |
| fetch | `HTTP_CLIENT_ERROR` | error | 4xx such as 403/404 (not retried) |
| fetch | `RETRY_RECOVERED` | warning | Failed at first, succeeded on retry |
| page check | `BLOCKED_CHALLENGE` | error | Firewall / "checking your browser" page |
| page check | `LOGIN_REQUIRED` | error | Page demands login for the main content |
| page check | `LAYOUT_UNRECOGNIZED` | error | Required markers missing: the site changed or a different page came back |
| listing | `LISTING_EMPTY_EARLY` | error | 0 cards before the window end was reached |
| listing | `LISTING_FEW_CARDS` | warning | Fewer than 10 cards on a non-final page |
| listing | `LISTING_ORDER_BROKEN` | warning | Dates not newest-first |
| listing | `PAGE_CAP_REACHED` | error | Stopped at the 40-page safety cap |
| record | `FIELD_MISSING` | error | ID, URL, title, date or body missing (detail names the field) |
| record | `DATE_UNPARSEABLE` | error | Unknown month name or digits |
| record | `DATE_MISMATCH` | error | Card, URL and posting-page dates disagree |
| record | `URL_REJECTED` | error | Not http(s) or not on the source domain |
| record | `TAGS_MISMATCH` | warning | Listing tags ≠ posting page tags |
| record | `BODY_SHORT` | warning | Body under 40 characters |
| record | `ID_MISMATCH` | error | Posting page is not the post the card links to |
| record | `TITLE_MISMATCH` | warning | Listing title ≠ posting page title (page title stored) |
| record | `FALLBACK_USED` | warning | Card date missing; validated URL date used |
| store | `DB_WRITE_FAILED` | error | SQLite error for one record |
| store | `EMPTY_FIELD_KEPT` | warning | New title/body/URL or tag label empty; stored value kept |
| run | `BREAKER_TRIPPED` | error | Too many failures; source stopped (see §8) |
| run | `UNEXPECTED_ERROR` | error | Bug: traceback saved in detail |

Run status:

| Status | Meaning | Exit code |
|---|---|---|
| `success` | Window fully covered, no errors | 0 |
| `success_empty` | Window fully covered, 0 postings in it | 0 |
| `success_with_warnings` | Covered, only warnings | 0 |
| `partial` | Covered, but some records or posting pages failed | 1 |
| `incomplete` | Could not cover the whole window | 2 |
| `blocked` | Access refused (firewall, login) | 3 |
| `parser_broken` | Circuit breaker tripped | 4 |
| `failed` | Crash | 5 |

## 7. Source adapters (how another site is added)

A **module** is one Python file. An **adapter** is the module that translates one website's HTML
into our standard `Posting` shape. Everything else is shared and site-agnostic.

```
collector/
  core.py              run loop: window, pages, stop rule, retries, pacing, statuses
  fetch.py             fetch with timeout/retry/pacing, or replay a saved folder; injectable for tests
  dates.py             Jalali parsing, Tehran ⇄ UTC helpers
  normalize.py         one normalize() for search and tags
  storage.py           SQLite schema, upsert, runs, issues
  models.py            ListingItem, Posting dataclasses
  sources/
    __init__.py        SOURCES = {"eng-estekhdam": EngEstekhdam()}
    eng_estekhdam.py   the adapter: URLs, selectors, page checks, tag mapping
api/
  app.py               FastAPI routes
  static/              the page: index.html, style.css, app.js
tests/
  fixtures/eng_estekhdam/   saved HTML
  test_*.py
```

Adapter contract (what core asks every site):

```python
class Source(Protocol):
    name: str
    parser_version: str
    def listing_url(self, page: int) -> str: ...
    def check_page(self, html: str, kind: str) -> str | None: ...        # None or an issue code
    def parse_listing(self, html: str) -> tuple[list[ListingItem], list[Issue]]: ...
    def parse_posting(self, html: str, item: ListingItem) -> tuple[Posting | None, list[Issue]]: ...
```

Adding Site B = `sources/site_b.py` + its fixtures + one line in `SOURCES`. Database, API, page
and core stay untouched. No plugin loader: one site does not justify it.

## 8. Broken parser: prevent, detect, contain, isolate, repair

**[to build #N]**: planned, implemented by issue #N; relabelled **[built #N]** when that PR merges. **[design]**: written design answer only, deliberately not implemented.

**Prevent**
- **[built #3]** Select by meaning, not position: post ID class, `rel="tag"`, `.post-date-hidden`,
  `article.typology-single-post`. Never "the third div".
- **[built #3]** Independent sources for key facts: date from card + URL + posting page
  (`DATE_MISMATCH`); the posting page must carry the card's post ID (`ID_MISMATCH`); listing
  title vs `<h1>` (`TITLE_MISMATCH` warning; the `<h1>` is stored).
- **[built #3]** Body text drops active content, widgets, the members-only block and hidden
  elements (`[hidden]`, `display:none`): hidden text is a common way to plant instructions.

**Detect during a run (hard checks)**
- **[built #3]** Page check before parsing (`check_page`): listing = body class `home` + the
  `.typology-section` frame (the out-of-range page has the frame but no `.typology-posts`, so it
  stays a listing and step 5 reports it as `LISTING_EMPTY_EARLY`); posting = body class
  `single-post` + `article.typology-single-post`. Otherwise `BLOCKED_CHALLENGE` only when the page
  lacks the site's theme frame and its *visible* text mentions a browser check (every real page
  loads a reCAPTCHA script), else `LAYOUT_UNRECOGNIZED`.
- **[built #3]** Per-record validation (§6 record codes).

**Detect across runs (soft checks)**
- **[built #5]** Health numbers stored per run: cards per page, % body OK, % date OK, % tags OK.
  The page shows them next to the previous runs.
- **[design]** Drift alert: compare to the median of the last 10 successful runs; a drop over
  20 points raises `HEALTH_DRIFT`.
- **[design]** Layout fingerprint: hash of the class names along the path to key elements;
  change from last success = early warning even while parsing still works.
- **[design]** Daily smoke run of listing page 1 that only checks the page shape.

**Contain (stop bad data from spreading)**
- **[built #5]** Circuit breaker: if the first listing page fails the page check, or more than
  30% of records in a run fail validation (minimum 5 records), stop the source, write nothing
  new for it, status `parser_broken`. Protects good stored data and stops hammering the site.
- **[built #5]** Rejected records never enter `postings`; they appear only in `run_issues`, with a snapshot.
- **[built #4]** No-empty-overwrite rule (§4): stored text kept, `EMPTY_FIELD_KEPT` warning.
- **[built #3]** One fallback: when the card date is missing, the already-validated URL date is
  used and `FALLBACK_USED` is raised; the posting page date is still checked against it, so two
  independent sources remain. Nothing else is guessed.

**Isolate**
- **[built #5]** `--source` runs one source; a source's failure never touches another.
- **[design]** `sources.toml` with `enabled = false` to park a broken source; API keeps serving
  its stored data; page shows the source as "paused".

**Repair**
1. Read the run's issues on the page: which code, which URL.
2. Copy the saved snapshot from `var/snapshots/<run>/` into `tests/fixtures/`.
3. Write a test that fails on it.
4. Fix the selectors; bump `parser_version`.
5. **[built #5]** Replay: `collect --from-dir var/snapshots/<run>/` re-parses saved pages offline
   (the same code path the tests use).
6. Re-enable, re-collect. Rows from the old `parser_version` are refreshed by upsert.

## 9. Search (keyword, date, tag)

- One `normalize()` used for stored text and the query (prevents the two drifting apart):
  lowercase Latin (`AutoCAD` = `autocad`); Arabic ي/ك → Persian ی/ک; Persian/Arabic digits →
  0–9; zero-width non-joiner and extra spaces → one space.
- `q` is matched as one substring of `search_text` (title + body) with SQL `LIKE`, `%`/`_`
  escaped, parameterized query. "مهندس عمران" matches only that exact phrase (documented).
  Decided 2026-10-07: phrase match, as the brief describes; word-by-word matching is listed as a
  possible improvement.
- Date filter: `date_from`/`date_to` as `YYYY-MM-DD` Gregorian Tehran days, inclusive both ends.
- Tag filter: one tag, matched against slug (`civil`) or normalized label (`عمران`).
- All filters ANDed; newest first; `page_size` default 20, max 100. ≈ 70 new rows a week, so no
  search engine or index is needed (brief excludes one).

## 10. API

| Route | Purpose |
|---|---|
| `GET /api/postings?date_from&date_to&q&tag&page&page_size` | Search; returns `{items, total, page, page_size}` with snippets |
| `GET /api/postings/{id}` | One posting with full body |
| `GET /api/tags` | Tags with kind, Persian label and counts (fills the dropdown) |
| `GET /api/stats` | Postings per Tehran day (with Jalali label) and top tags, for charts |
| `GET /api/runs?limit=20` | Run history with status, counts and health numbers |
| `GET /api/runs/{id}` | One run with its issues grouped by code; live counters while running |
| `POST /api/runs` | **Collect now**: starts `python -m collector collect --run-id N` in the background; `202` with `run_id`, `409` if a run is active, `403` without the trigger header |

Timestamps returned as `...Z`. Postings also include `published_date_tehran` (`2026-10-06`) and
`published_date_jalali` (`1405-07-14`) so clients need no conversion. Bad date → 422 with message.
Every response sets `Content-Security-Policy: default-src 'self'`.

## 11. The web page

One `index.html`, right-to-left aware (`dir="auto"` on Persian text), no framework.

| Area | Shows | Data source |
|---|---|---|
| Run status bar | Last run time (Tehran), status badge, window, new/updated/unchanged/rejected | `/api/runs?limit=1` |
| Postings per day | 7 bars labelled with Jalali + Gregorian date; click a bar = filter that day | `/api/stats` |
| Search panel | Date from/to (with Jalali shown beside each), keyword, tag dropdown with counts, Search / Reset; filters copied into the page URL so a search can be shared | `/api/tags` |
| Results | "Showing 1–20 of 70"; each row: title, Jalali + Gregorian date "(Tehran)", tag chips, snippet; prev/next | `/api/postings` |
| Posting detail | Click a row: full body, collected/updated times (UTC), "Open original" link | `/api/postings/{id}` |
| Run history | Last 10 runs: status, counts, health %; click → issues grouped by code with URLs | `/api/runs`, `/api/runs/{id}` |
| Collect now button | Starts a collection; disabled while a run is active; shows live progress (listing pages, postings fetched, issues so far) by polling every 2 s; refreshes results when done | `POST /api/runs`, `/api/runs/{id}` |

**Collect now: how it works and why it is safe**
- The API inserts the run row (`start_run()`, the same lock as the command), then launches the
  exact CLI command as a separate process with `--run-id N`. Output goes to `var/logs/run-N.log`.
- Separate process, not a thread inside the API: the button and the terminal run identical code;
  a collector crash cannot take the API down; the web server never blocks for 2 minutes.
- The core updates the run row's counters as it goes, so the page can show progress.
- No login (the brief excludes authentication), so: the server listens on `127.0.0.1` only by
  default; the request must carry header `X-Collect-Trigger: 1`, which another website cannot
  add to a cross-site request without permission we never grant (blocks drive-by triggering
  from a malicious page in the same browser); one run at a time; README warns not to expose
  the server publicly.
- Tests: `202` + process launched (launcher replaced by a fake); `409` while running; `403`
  without the header; a `running` row with no heartbeat for 3 min is marked failed and does not block.

Safety rules for the page: every value inserted with `textContent` / `createElement`, never
`innerHTML`; links only if `http:`/`https:`, `rel="noopener noreferrer"`; no inline scripts
(CSP); bars drawn with plain CSS widths, so no chart library and no CDN.

## 12. Tests

**Where:** `tests/fixtures/eng_estekhdam/`.

| Files | Kind | Purpose |
|---|---|---|
| `snapshot/listing-00001…00008.html` | real, one consistent capture 2026-10-07T17:00Z | listings; window ends on page 7 |
| `snapshot/listing-99999.html` | real (`/page/99999/`) | 200 with zero cards |
| `snapshot/posting-<id>.html` (80) | real | every posting linked from pages 1–8: bodies, tags, related ads, paywall, report widget |
| `snapshot/manifest.json` | generated | URL → file map used by the fake network |
| `challenge_page.html` | hand-made | firewall page |
| `listing_missing_date.html` | hand-made (edited real page) | `FIELD_MISSING` |
| `posting_malicious.html` | hand-made, harmless | XSS checks |

`scripts/capture_fixtures.py` re-captures the snapshot; `fixtures/eng_estekhdam/README.md`
records when and how. A full snapshot (not a few pages) lets step 5 run a complete offline
collection and doubles as evidence if a live run is blocked.

**How:** no test touches the network. The HTTP layer is injected; tests swap in a fake that maps
URL → fixture file (or → timeout / 503 to simulate failures). The clock is injected and frozen.
Each test gets a fresh SQLite file in a temp folder.

| Layer | Example | Speed |
|---|---|---|
| Unit | `parse_jalali("۱۴ مهر ۱۴۰۵")`, `normalize("نقشه برداري")` | ms |
| Integration | collect from fixtures into a temp DB, run twice, query the API | < 1 s |
| Browser (1 test) | Playwright opens the page against a DB seeded with the malicious posting | ~3 s |

**When:**
1. After every change while building: `pytest` locally.
2. Automatically on every push and pull request: GitHub Actions runs the full suite; a red check blocks the merge.
3. By reviewers from a clean clone, following the README.

**Coverage map (brief §4):**

| Brief area | Tests |
|---|---|
| Listing + posting extraction, tag mapping | fields from page 1; related ads absent from body; paywall absent; `tag-civil` → field/civil/عمران |
| Persian dates, UTC, Tehran days | all 12 months, Esfand 29/30, digits; midnight convention; 01:00-Tehran run; 20:29:59Z in / 20:30:00Z out |
| No duplicates | collect twice → same count, second run all `unchanged`; edited fixture → `updated` |
| Each filter and combined | date, q, tag alone; all three; inclusive ends; paging; bad date 422 |
| Visible failure | timeout, 503→ok (`RETRY_RECOVERED`), challenge, out-of-range page, missing date, breaker |
| Untrusted HTML | stored text has no tags; `javascript:` link → `URL_REJECTED`; browser test: literal text shown, nothing executes |

## 13. Requirement checklist (every sentence of the brief)

Status 2026-10-08: every row below is built and has its proof in the repository (PRs #9–#15 and
the step 8 PR); the live run is in `docs/LIVE_RUN.md`.

| Brief | Plan | Proof |
|---|---|---|
| Manual collect command | §5 | README + live run log |
| Today + previous 6 Tehran days, decided at run start | §3 | frozen-clock tests |
| Select by publication date | §3 | test |
| Persian dates correct | §3 | table test |
| UTC storage; midnight convention documented | §3, §4 | test + README |
| Window bounds converted to UTC | §3 | boundary tests |
| Parse HTML; paginate; posting pages; no feed/API | §2, §7 | fixture tests |
| All seven fields | §4 | parser + storage tests |
| Body without navigation/unrelated content | §8 prevent | related-ads test |
| Tags from the posting's own labels; mapping documented | §4 | tag test + README table |
| No AI tags; no site-wide menu | adapter reads article only | test |
| No duplicates; identity + change handling documented | §4 | re-run tests |
| Pacing, timeouts, bounded retries | §5 | fake-transport tests |
| Failed pages / invalid records reported; incomplete ≠ empty | §6 | failure tests |
| Public content only; blockers recorded; fixture demo if blocked | §2, §6 `blocked` | README evidence |
| API filters, AND, newest first, bounded | §9, §10 | filter tests |
| Date format, normalization, case handling documented | §9 | README |
| UTC `Z`; inclusive via exclusive next midnight | §3, §10 | tests |
| UI: controls, list, full text, source link, labelled Tehran dates | §11 | browser test + screenshot |
| Untrusted HTML handled safely | §11 rules, §8 | XSS tests |
| Design doc: components, new source, broken parser, isolation, tradeoffs | §7, §8 | `docs/DESIGN.md` + diagram |
| Offline tests covering six areas | §12 | `pytest`, CI |
| One live run: window, count, failures | step 8 | `docs/LIVE_RUN.md` |
| Repo, real history, setup, versions, DB init, commands, example queries | §14 | README from clean clone |
| Time, limitations, unfinished work | `docs/TIME_LOG.md` | README |
| AI-use note, 2–3 concrete decisions | `docs/AI_NOTES.md` | README |

## 14. Steps (one issue + branch + PR each, reviewed by Parham)

| # | Step | Est. |
|---|---|---|
| 0 | Planning and site research (done) | 2.5 h |
| 1 | Skeleton, pinned deps, README outline, capture fixtures, CI workflow, time log | 1.25 h |
| 2 | Dates + normalize modules, tests | 1.5 h |
| 3 | Adapter: page checks, listing + posting parser, tag mapping, tests | 2.5 h |
| 4 | Storage: schema, upsert, no-empty-overwrite, runs/issues tables, tests | 1.5 h |
| 5 | Collect command: HTTP layer, stop rule, issue codes, statuses, breaker, snapshots, replay, tests | 2.5 h |
| 6 | API: postings, tags, stats, runs, Collect now trigger; tests | 2.5 h |
| 7 | Page: search, results, detail, Jalali, charts, run monitor, Collect now button; Playwright test | 3 h |
| 8 | Live run evidence, DESIGN.md + diagram, AI notes, clean-clone check | 1.5 h |
|   | **Total** | **≈ 18 h** |

Estimates are for pacing only (Parham, 2026-10-07: the 12–16 h guide is not a hard limit).
Actual time per step goes in `docs/TIME_LOG.md`; the README reports the real total.

Review gate per step (full loop in `docs/WORKFLOW.md`): CI green → Codex review → Claude triages
each finding (fix / evidence / "Needs Parham") → Parham settles open points and merges with a merge
commit (never squash).

## 15. Open decisions

- When you received the assignment: sets the 4-day submission deadline.

Decided: tag filter accepts slug or Persian label; keyword = phrase substring; Collect now button
built; issue + PR per step; one Playwright test; Jalali dates, run history and monitor included.
