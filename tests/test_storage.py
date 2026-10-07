"""SQLite storage: identity, change handling, no data loss, and one run at a time."""

import json
import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from collector import storage
from collector.__main__ import main
from collector.models import Issue, Posting, Tag
from collector.sources import SOURCES

T0 = datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(days=1)

POSTING = Posting(
    source="eng-estekhdam",
    source_post_id="205126",
    url="https://eng-estekhdam.com/1405/07/15/a/",
    title="استخدام مهندس عمران",
    body="به مهندس عمران نیازمندیم.\n- سه سال سابقه",
    published_date=date(2026, 10, 7),
    tags=(Tag("province", "tehran", "تهران"), Tag("field", "civil", "عمران")),
    parser_version="eng-estekhdam/1",
    members_only_omitted=True,
)


@pytest.fixture
def conn(tmp_path):
    connection = storage.connect(tmp_path / "jobs.db")
    yield connection
    connection.close()


def rows(conn, sql, *args):
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def test_init_db_command_is_safe_to_repeat(tmp_path, capsys):
    db = tmp_path / "nested" / "jobs.db"
    assert main(["--db", str(db), "init-db"]) == 0
    assert main(["--db", str(db), "init-db"]) == 0
    tables = {r["name"] for r in rows(storage.connect(db), "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"postings", "posting_tags", "runs", "run_issues"} <= tables


def test_new_posting_is_stored_with_utc_timestamps(conn):
    assert storage.upsert_posting(conn, POSTING, T0) == ("new", [])
    [row] = rows(conn, "SELECT * FROM postings")
    assert row["published_at"] == "2026-10-06T20:30:00Z"  # 00:00 Tehran on 15 Mehr 1405
    assert row["collected_at"] == row["updated_at"] == row["last_seen_at"] == "2026-10-07T17:00:00Z"
    assert row["members_only_omitted"] == 1
    assert row["search_text"] == "استخدام مهندس عمران به مهندس عمران نیازمندیم. - سه سال سابقه"
    assert rows(conn, "SELECT kind, slug, label FROM posting_tags ORDER BY kind") == [
        {"kind": "field", "slug": "civil", "label": "عمران"},
        {"kind": "province", "slug": "tehran", "label": "تهران"},
    ]


def test_same_posting_again_is_unchanged_and_not_duplicated(conn):
    storage.upsert_posting(conn, POSTING, T0)
    assert storage.upsert_posting(conn, POSTING, T1) == ("unchanged", [])
    [row] = rows(conn, "SELECT collected_at, updated_at, last_seen_at FROM postings")
    assert row == {
        "collected_at": "2026-10-07T17:00:00Z",
        "updated_at": "2026-10-07T17:00:00Z",
        "last_seen_at": "2026-10-08T17:00:00Z",
    }


def test_changed_body_updates_the_same_row(conn):
    storage.upsert_posting(conn, POSTING, T0)
    edited = replace(POSTING, body="متن ویرایش شده آگهی")
    assert storage.upsert_posting(conn, edited, T1) == ("updated", [])
    [row] = rows(conn, "SELECT body, search_text, collected_at, updated_at FROM postings")
    assert row["body"] == "متن ویرایش شده آگهی"
    assert "ویرایش" in row["search_text"]
    assert row["collected_at"] == "2026-10-07T17:00:00Z"
    assert row["updated_at"] == "2026-10-08T17:00:00Z"


def test_changed_title_and_url_update_the_same_row(conn):
    storage.upsert_posting(conn, POSTING, T0)
    retitled = replace(POSTING, title="عنوان جدید", url="https://eng-estekhdam.com/1405/07/15/b/")
    assert storage.upsert_posting(conn, retitled, T1)[0] == "updated"
    assert rows(conn, "SELECT count(*) AS n FROM postings") == [{"n": 1}]


def test_empty_field_never_overwrites_stored_text(conn):
    storage.upsert_posting(conn, POSTING, T0)
    result, issues = storage.upsert_posting(conn, replace(POSTING, body="   ", title="عنوان جدید"), T1)
    assert result == "updated"  # the title change is still applied
    assert [(i.code, i.severity) for i in issues] == [("EMPTY_FIELD_KEPT", "warning")]
    [row] = rows(conn, "SELECT title, body FROM postings")
    assert row == {"title": "عنوان جدید", "body": POSTING.body}


def test_tags_are_replaced_on_update_not_added(conn):
    storage.upsert_posting(conn, POSTING, T0)
    storage.upsert_posting(conn, replace(POSTING, tags=(Tag("province", "kerman", "کرمان"),)), T1)
    assert rows(conn, "SELECT kind, slug FROM posting_tags") == [{"kind": "province", "slug": "kerman"}]


def test_database_itself_refuses_a_second_row_for_the_same_post(conn):
    """Backstop below the code: even a buggy insert cannot create a duplicate."""
    storage.upsert_posting(conn, POSTING, T0)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO postings (source, source_post_id, url, title, body, published_at, collected_at,"
            " updated_at, last_seen_at, content_hash, search_text, parser_version)"
            " VALUES ('eng-estekhdam', '205126', 'https://other/', 't', 'b', 'x', 'x', 'x', 'x', 'h', 's', 'v')"
        )


def test_same_post_id_from_another_source_is_a_different_posting(conn):
    storage.upsert_posting(conn, POSTING, T0)
    assert storage.upsert_posting(conn, replace(POSTING, source="other-site"), T0)[0] == "new"
    assert rows(conn, "SELECT count(*) AS n FROM postings") == [{"n": 2}]


def test_text_that_looks_like_sql_is_stored_literally(conn):
    sneaky = replace(POSTING, title="x'); DROP TABLE postings; --")
    storage.upsert_posting(conn, sneaky, T0)
    assert rows(conn, "SELECT title FROM postings") == [{"title": "x'); DROP TABLE postings; --"}]


def test_whole_snapshot_twice_gives_80_rows_then_all_unchanged(conn):
    source = SOURCES["eng-estekhdam"]
    snapshot = Path(__file__).parent / "fixtures" / "eng_estekhdam" / "snapshot"
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    files = {e["url"]: e["file"] for e in manifest["pages"]}
    postings = []
    for entry in manifest["pages"]:
        if entry["kind"] == "listing":
            for card in source.parse_listing((snapshot / entry["file"]).read_text(encoding="utf-8"))[0]:
                postings.append(source.parse_posting((snapshot / files[card.url]).read_text(encoding="utf-8"), card)[0])

    first = [storage.upsert_posting(conn, p, T0)[0] for p in postings]
    second = [storage.upsert_posting(conn, p, T1)[0] for p in postings]
    assert first.count("new") == 80 and second.count("unchanged") == 80
    assert rows(conn, "SELECT count(*) AS n FROM postings") == [{"n": 80}]


# --- runs -------------------------------------------------------------------------------

def test_only_one_run_at_a_time(tmp_path):
    first, second = storage.connect(tmp_path / "jobs.db"), storage.connect(tmp_path / "jobs.db")
    run_id = storage.start_run(first, "eng-estekhdam", T0)
    with pytest.raises(storage.RunActive):
        storage.start_run(second, "eng-estekhdam", T0 + timedelta(minutes=29))
    storage.finish_run(first, run_id, "success", T0 + timedelta(minutes=2))
    assert storage.start_run(second, "eng-estekhdam", T0 + timedelta(minutes=3)) == run_id + 1


def test_stale_running_row_does_not_block_and_is_marked_failed(conn):
    stale = storage.start_run(conn, "eng-estekhdam", T0)
    fresh = storage.start_run(conn, "eng-estekhdam", T0 + timedelta(minutes=31))
    assert fresh != stale
    assert rows(conn, "SELECT status FROM runs WHERE id = ?", stale) == [{"status": "failed"}]
    assert rows(conn, "SELECT code FROM run_issues WHERE run_id = ?", stale) == [{"code": "UNEXPECTED_ERROR"}]


def test_run_counters_issues_and_final_status(conn):
    run_id = storage.start_run(conn, "eng-estekhdam", T0)
    storage.update_run(conn, run_id, new=3, pages_listing=2, window_start="2026-09-30T20:30:00Z")
    storage.add_issue(conn, run_id, Issue.error("FETCH_TIMEOUT", "no answer in 20 s", "https://x"), "fetch", "var/s/1.html")
    storage.finish_run(conn, run_id, "partial", T1)
    [run] = rows(conn, "SELECT status, finished_at, new, pages_listing, window_start FROM runs")
    assert run == {
        "status": "partial", "finished_at": "2026-10-08T17:00:00Z",
        "new": 3, "pages_listing": 2, "window_start": "2026-09-30T20:30:00Z",
    }
    assert rows(conn, "SELECT severity, stage, code, snapshot_path FROM run_issues") == [
        {"severity": "error", "stage": "fetch", "code": "FETCH_TIMEOUT", "snapshot_path": "var/s/1.html"}
    ]


def test_unknown_run_fields_and_statuses_are_rejected(conn):
    run_id = storage.start_run(conn, "eng-estekhdam", T0)
    with pytest.raises(ValueError):
        storage.update_run(conn, run_id, status="success")  # status changes only through finish_run
    with pytest.raises(ValueError):
        storage.finish_run(conn, run_id, "running", T1)
    with pytest.raises(ValueError):
        storage.finish_run(conn, run_id, "done", T1)
