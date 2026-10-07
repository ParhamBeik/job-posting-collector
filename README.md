# job-posting-collector

Collects recent job postings from [eng-estekhdam.com](https://eng-estekhdam.com/) into SQLite,
with an HTTP API and a search page.

> Work in progress. Sections marked *(step N)* are filled in by that build step
> (issues #1–#8). The design and the requirement checklist are in [`PLAN.md`](PLAN.md); the
> way each step is built and reviewed is in [`docs/WORKFLOW.md`](docs/WORKFLOW.md).

## Requirements

- Python 3.12
- Dependencies pinned in `pyproject.toml`

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the tests

```bash
pytest
```

Tests never touch the live website; they use saved pages in `tests/fixtures/`.
GitHub Actions runs them on every pull request.

## Initialize the database

```bash
python -m collector init-db            # creates var/jobs.db (safe to run again)
python -m collector --db other.db init-db
```

The collect command and the API also create the tables if they are missing.

## Collect postings *(step 5)*

## Start the API and the page *(steps 6–7)*

## Example API queries *(step 6)*

## How data is handled

### Dates and time zones

- The source shows Persian (Jalali) dates such as `۱۴ مهر ۱۴۰۵`, with no time of day.
  They are converted to Gregorian dates (`jdatetime`): 14 Mehr 1405 = 2026-10-06.
- **Storage convention:** a posting's publication timestamp is **00:00 in Tehran** on its date,
  stored in UTC: `2026-10-05T20:30:00Z`. This is not an observed publication time; the source
  page does not show one.
- All stored and returned timestamps are UTC, ISO 8601 with `Z`.
- Tehran's offset comes from the `Asia/Tehran` time zone database (`zoneinfo` + pinned `tzdata`),
  never a fixed `+03:30`, so past dates with daylight saving time stay correct.
- **Collection window:** "today" is decided in Tehran once, at the start of a run; the window is
  today and the previous six Tehran calendar days, converted to a UTC range that includes the
  first midnight and excludes the midnight after the last day. A run at 01:00 Tehran on 8 Oct
  (still 7 Oct in UTC) collects 2–8 Oct.
- **Date filters** use the same rule: `date_from=2026-10-04&date_to=2026-10-06` means
  `2026-10-03T20:30:00Z <= published_at < 2026-10-06T20:30:00Z`.
- An unreadable date (unknown month, impossible day such as 31 Mehr) is an error, never guessed.

### Search normalization and case handling

Stored text and queries pass through the same `normalize()`: Latin letters are case-folded
(`AutoCAD` = `autocad`); Arabic `ي`/`ك` become Persian `ی`/`ک` (the source mixes both); Persian
and Arabic-Indic digits become `0–9`; the zero-width non-joiner (half-space) and repeated
whitespace become one space.

### Tag mapping

Tags come only from the posting's own labels on the source; nothing is generated, and the
site-wide menu is never copied onto a posting.

| Source label | Stored tag | Where it is read |
|---|---|---|
| Province category, e.g. `category-tehran` → "تهران" | `kind=province`, `slug=tehran`, `label=تهران` | article class on the card; `rel="category tag"` link on the posting page (an ad can name two provinces) |
| Field tag, e.g. `tag-civil` → "عمران" | `kind=field`, `slug=civil`, `label=عمران` | article class on the card; `.entry-tags a[rel=tag]` on the posting page |

The posting page's labels are stored; if they differ from the card's, a `TAGS_MISMATCH` warning
is recorded. Field tags seen on the site (labels as the site writes them):

| slug | label | slug | label |
|---|---|---|---|
| `civil` | عمران | `structure` | سازه |
| `memari` | معماری | `marine` | سازه دریایی |
| `surveying` | نقشه برداري | `hydraulic` | سازه هیدرولیکی |
| `road` | راه ترابری | `geotechnic` | خاک پی |
| `rail` | راه آهن | `earthquake` | زلزله |
| `water` | آب فاضلاب | `environment` | محیط زیست |
| `transportation` | حمل نقل | `management` | مدیریت ساخت |

### Identity of a posting and how changes are handled

- **Identity:** `(source, source_post_id)`, the source's own WordPress post ID (e.g. `205126`),
  enforced by a `UNIQUE` constraint. Not the URL or title: the URL slug is built from the title
  and changes when the title is edited.
- **Re-collecting** the same posting never adds a row. A SHA-256 fingerprint of everything stored
  from the source (URL, title, body, date, tags, members-only flag) decides the result:
  - same fingerprint → `unchanged`; only `last_seen_at` moves;
  - different fingerprint → `updated`: fields, tags and search text replaced, `updated_at` moves.
- `collected_at` is the first time the posting was stored and never changes.
- **No data loss:** a new empty title, body or URL never overwrites stored text; the stored value
  is kept and an `EMPTY_FIELD_KEPT` warning is recorded.
- Old postings are never deleted.
- `members_only_omitted = 1` marks postings whose contact section was members-only on the
  source and therefore not collected.

## Design *(step 8)*

## Live collection evidence *(step 8)*

## Time spent, limitations and unfinished work *(step 8)*

See [`docs/TIME_LOG.md`](docs/TIME_LOG.md).

## AI use *(step 8)*

See [`docs/AI_NOTES.md`](docs/AI_NOTES.md).
