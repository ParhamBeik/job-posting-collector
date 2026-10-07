"""SQLite storage: postings, their tags, collection runs and the issues each run found.

Identity of a posting is (source, source_post_id): the source's own stable post ID, never the
URL or title (the URL slug is derived from the title and changes when the title is edited).
Re-collecting a posting updates that one row; nothing is ever deleted.
All timestamps are stored as UTC ISO 8601 text with "Z", which also sorts correctly as text.
"""

import hashlib
import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from collector.dates import format_utc
from collector.models import Issue, Posting
from collector.normalize import normalize

DEFAULT_DB = Path("var/jobs.db")
STALE_RUN = timedelta(minutes=30)
RUN_STATUSES = (
    "running",
    "success",
    "success_empty",
    "success_with_warnings",
    "partial",
    "incomplete",
    "blocked",
    "parser_broken",
    "failed",
)
RUN_FIELDS = (
    "window_start", "window_end", "pages_listing", "pages_posting",
    "new", "updated", "unchanged", "rejected",
    "cards_per_page_avg", "body_ok_pct", "date_ok_pct", "tags_ok_pct", "parser_version",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    id                   INTEGER PRIMARY KEY,
    source               TEXT NOT NULL,
    source_post_id       TEXT NOT NULL,
    url                  TEXT NOT NULL,
    title                TEXT NOT NULL,
    body                 TEXT NOT NULL,
    published_at         TEXT NOT NULL,
    collected_at         TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    last_seen_at         TEXT NOT NULL,
    content_hash         TEXT NOT NULL,
    search_text          TEXT NOT NULL,
    parser_version       TEXT NOT NULL,
    members_only_omitted INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source, source_post_id)
);
CREATE INDEX IF NOT EXISTS postings_newest ON postings (published_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS posting_tags (
    posting_id INTEGER NOT NULL REFERENCES postings (id) ON DELETE CASCADE,
    kind       TEXT NOT NULL CHECK (kind IN ('province', 'field')),
    slug       TEXT NOT NULL,
    label      TEXT,
    PRIMARY KEY (posting_id, kind, slug)
);

CREATE TABLE IF NOT EXISTS runs (
    id                 INTEGER PRIMARY KEY,
    source             TEXT NOT NULL,
    started_at         TEXT NOT NULL,
    finished_at        TEXT,
    status             TEXT NOT NULL,
    window_start       TEXT,
    window_end         TEXT,
    pages_listing      INTEGER NOT NULL DEFAULT 0,
    pages_posting      INTEGER NOT NULL DEFAULT 0,
    new                INTEGER NOT NULL DEFAULT 0,
    updated            INTEGER NOT NULL DEFAULT 0,
    unchanged          INTEGER NOT NULL DEFAULT 0,
    rejected           INTEGER NOT NULL DEFAULT 0,
    cards_per_page_avg REAL,
    body_ok_pct        REAL,
    date_ok_pct        REAL,
    tags_ok_pct        REAL,
    parser_version     TEXT
);

CREATE TABLE IF NOT EXISTS run_issues (
    id            INTEGER PRIMARY KEY,
    run_id        INTEGER NOT NULL REFERENCES runs (id),
    severity      TEXT NOT NULL CHECK (severity IN ('error', 'warning')),
    stage         TEXT NOT NULL,
    code          TEXT NOT NULL,
    url           TEXT,
    detail        TEXT NOT NULL,
    snapshot_path TEXT
);
"""


class RunActive(Exception):
    """Another collection run is in progress; only one runs at a time."""


def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    """Open the database, creating the file and tables if needed (safe to repeat)."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)  # explicit BEGIN/COMMIT below
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # the API can read while a collection writes
    conn.executescript(SCHEMA)
    return conn


def content_hash(posting: Posting) -> str:
    """Fingerprint of everything stored from the source; a change means 'updated'."""
    payload = [
        posting.url,
        posting.title,
        posting.body,
        format_utc(posting.published_at),
        sorted((t.kind, t.slug, t.label or "") for t in posting.tags),
        posting.members_only_omitted,
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def upsert_posting(conn: sqlite3.Connection, posting: Posting, now: datetime) -> tuple[str, list[Issue]]:
    """Insert or update one posting in its own transaction. Returns ('new'|'updated'|'unchanged', issues)."""
    stamp = format_utc(now)
    issues: list[Issue] = []
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT id, url, title, body, content_hash FROM postings WHERE source = ? AND source_post_id = ?",
            (posting.source, posting.source_post_id),
        ).fetchone()

        fields = {"url": posting.url, "title": posting.title, "body": posting.body}
        if row:
            for name, value in fields.items():
                if not value.strip() and row[name].strip():  # a broken parse must not erase good data
                    fields[name] = row[name]
                    issues.append(Issue.warning(
                        "EMPTY_FIELD_KEPT", f"post {posting.source_post_id}: new {name} empty, stored one kept", posting.url
                    ))
        posting = replace(posting, **fields)  # what will actually be stored
        digest = content_hash(posting)

        if row and row["content_hash"] == digest:
            # Content unchanged, but record which parser confirmed it (repair flow, PLAN §8).
            conn.execute(
                "UPDATE postings SET last_seen_at = ?, parser_version = ? WHERE id = ?",
                (stamp, posting.parser_version, row["id"]),
            )
            result = "unchanged"
        else:
            values = {
                "url": posting.url,
                "title": posting.title,
                "body": posting.body,
                "published_at": format_utc(posting.published_at),
                "content_hash": digest,
                "search_text": normalize(posting.title + "\n" + posting.body),
                "parser_version": posting.parser_version,
                "members_only_omitted": int(posting.members_only_omitted),
                "updated_at": stamp,
                "last_seen_at": stamp,
            }
            if row:
                posting_id = row["id"]
                assignments = ", ".join(f"{column} = :{column}" for column in values)
                conn.execute(f"UPDATE postings SET {assignments} WHERE id = :id", {**values, "id": posting_id})
                conn.execute("DELETE FROM posting_tags WHERE posting_id = ?", (posting_id,))
                result = "updated"
            else:
                values |= {"source": posting.source, "source_post_id": posting.source_post_id, "collected_at": stamp}
                columns = ", ".join(values)
                placeholders = ", ".join(f":{column}" for column in values)
                posting_id = conn.execute(f"INSERT INTO postings ({columns}) VALUES ({placeholders})", values).lastrowid
                result = "new"
            conn.executemany(
                "INSERT OR IGNORE INTO posting_tags (posting_id, kind, slug, label) VALUES (?, ?, ?, ?)",
                [(posting_id, t.kind, t.slug, t.label) for t in posting.tags],
            )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return result, issues


def start_run(conn: sqlite3.Connection, source: str, now: datetime) -> int:
    """Create a 'running' run row, or raise RunActive. The single rule for 'one run at a time'.

    A 'running' row older than 30 minutes is a run that died without finishing: it is marked
    'failed' with an issue instead of blocking collection forever.
    """
    stale_before = format_utc(now - STALE_RUN)
    conn.execute("BEGIN IMMEDIATE")  # takes the write lock, so two starters cannot both pass the check
    try:
        if conn.execute(
            "SELECT 1 FROM runs WHERE status = 'running' AND started_at >= ?", (stale_before,)
        ).fetchone():
            raise RunActive("another collection run is in progress")
        for (stale_id,) in conn.execute(
            "SELECT id FROM runs WHERE status = 'running' AND started_at < ?", (stale_before,)
        ).fetchall():
            conn.execute(
                "UPDATE runs SET status = 'failed', finished_at = ? WHERE id = ?", (format_utc(now), stale_id)
            )
            _insert_issue(conn, stale_id, Issue.error("UNEXPECTED_ERROR", "run never finished (stale after 30 min)"), "run")
        run_id = conn.execute(
            "INSERT INTO runs (source, started_at, status) VALUES (?, ?, 'running')", (source, format_utc(now))
        ).lastrowid
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return run_id


def update_run(conn: sqlite3.Connection, run_id: int, **fields) -> None:
    """Set run counters and details as the run progresses (absolute values)."""
    unknown = set(fields) - set(RUN_FIELDS)
    if unknown:
        raise ValueError(f"unknown run fields: {sorted(unknown)}")
    if fields:
        assignments = ", ".join(f"{name} = :{name}" for name in fields)
        conn.execute(f"UPDATE runs SET {assignments} WHERE id = :id", {**fields, "id": run_id})


def finish_run(conn: sqlite3.Connection, run_id: int, status: str, now: datetime) -> None:
    if status not in RUN_STATUSES or status == "running":
        raise ValueError(f"not a final run status: {status!r}")
    conn.execute("UPDATE runs SET status = ?, finished_at = ? WHERE id = ?", (status, format_utc(now), run_id))


def add_issue(conn: sqlite3.Connection, run_id: int, issue: Issue, stage: str, snapshot_path: str | None = None) -> None:
    _insert_issue(conn, run_id, issue, stage, snapshot_path)


def _insert_issue(conn, run_id, issue: Issue, stage: str, snapshot_path: str | None = None) -> None:
    conn.execute(
        "INSERT INTO run_issues (run_id, severity, stage, code, url, detail, snapshot_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (run_id, issue.severity, stage, issue.code, issue.url, issue.detail, snapshot_path),
    )
