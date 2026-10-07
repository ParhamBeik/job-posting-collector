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

## Initialize the database *(step 4)*

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

### Tag mapping *(step 3)*

### Identity of a posting and how changes are handled *(step 4)*

## Design *(step 8)*

## Live collection evidence *(step 8)*

## Time spent, limitations and unfinished work *(step 8)*

See [`docs/TIME_LOG.md`](docs/TIME_LOG.md).

## AI use *(step 8)*

See [`docs/AI_NOTES.md`](docs/AI_NOTES.md).
