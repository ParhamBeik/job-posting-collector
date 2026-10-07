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

## How data is handled *(steps 2–5)*

- Dates, time zones and the midnight-Tehran convention
- Tag mapping
- Identity of a posting and how changes are handled
- Search normalization and case handling

## Design *(step 8)*

## Live collection evidence *(step 8)*

## Time spent, limitations and unfinished work *(step 8)*

See [`docs/TIME_LOG.md`](docs/TIME_LOG.md).

## AI use *(step 8)*

See [`docs/AI_NOTES.md`](docs/AI_NOTES.md).
