"""HTTP API against a temp database: the replayed site snapshot plus a few hand-made postings."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app, like_pattern
from collector import storage
from collector.core import collect
from collector.fetch import DirFetcher
from collector.models import Posting, Tag
from collector.sources import SOURCES

SNAPSHOT = Path(__file__).parent / "fixtures" / "eng_estekhdam" / "snapshot"
NOW = datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc)


def handmade(post_id, title, body, day, tags=(), published_at=None):
    return Posting("handmade", post_id, f"https://example.test/{post_id}", title, body, day, tags, "test/1"), published_at


EXTRA = [
    handmade("b1", "Last second of 5 Oct", "boundary", date(2026, 10, 5), published_at="2026-10-05T20:29:59Z"),
    handmade("b2", "First second of 6 Oct", "boundary", date(2026, 10, 6), published_at="2026-10-05T20:30:00Z"),
    # Made-up words (زیگورات, AutoCADZ, ۷۳۹) so no real ad matches; k2 would match only if % or _ acted as wildcards.
    handmade("k1", "Senior AutoCADZ drafter", "کارشناس زیگورات با ۷۳۹ سال سابقه، 99.5% حضوری؛ zig_zag",
             date(2026, 9, 1), (Tag("field", "civil", "عمران"),)),
    handmade("k2", "Wildcard decoy", "99.5 percent, zigXzag", date(2026, 9, 1)),
]


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("api") / "jobs.db"
    conn = storage.connect(path)
    collect(conn, SOURCES["eng-estekhdam"], DirFetcher(SNAPSHOT), lambda: NOW, tmp_path_factory.mktemp("snaps"))
    for posting, published_at in EXTRA:
        storage.upsert_posting(conn, posting, NOW)
        if published_at:
            conn.execute("UPDATE postings SET published_at = ? WHERE source_post_id = ?", (published_at, posting.source_post_id))
    conn.close()
    return path


@pytest.fixture
def launched():
    return []


@pytest.fixture
def client(db, launched):
    return TestClient(create_app(db, launch=lambda path, run_id: launched.append(run_id), clock=lambda: NOW))


def search(client, **params):
    response = client.get("/api/postings", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def all_ids(client, **params):
    return {item["source_post_id"] for item in search(client, page_size=100, **params)["items"]}


def sql(db, query, *args):
    conn = storage.connect(db)
    try:
        return conn.execute(query, args).fetchall()
    finally:
        conn.close()


# --- search ---------------------------------------------------------------------------------

def test_no_filters_returns_everything_newest_first_with_paging(client):
    first = search(client, page_size=30)
    assert first["total"] == 72 and len(first["items"]) == 30
    dates = [item["published_at"] for item in search(client, page_size=100)["items"]]
    assert dates == sorted(dates, reverse=True)
    last = search(client, page=3, page_size=30)
    assert len(last["items"]) == 12
    pages = [search(client, page=p, page_size=30)["items"] for p in (1, 2, 3)]
    assert len({item["id"] for page in pages for item in page}) == 72  # no overlap, nothing lost


def test_posting_fields_carry_utc_tehran_and_jalali_dates(client):
    item = next(i for i in search(client, page_size=100)["items"] if i["source_post_id"] == "b2")
    assert item["published_at"] == "2026-10-05T20:30:00Z"
    assert (item["published_date_tehran"], item["published_date_jalali"]) == ("2026-10-06", "1405-07-14")
    assert item["collected_at"].endswith("Z") and item["updated_at"].endswith("Z")


def test_date_filter_uses_inclusive_tehran_days(client):
    assert {"b1", "b2"} - all_ids(client, date_from="2026-10-06") == {"b1"}
    assert {"b1", "b2"} - all_ids(client, date_to="2026-10-05") == {"b2"}
    assert {"b1", "b2"} & all_ids(client, date_from="2026-10-06", date_to="2026-10-06") == {"b2"}


def test_date_filter_matches_an_independent_count(client, db):
    expected = sql(db, "SELECT count(*) FROM postings WHERE published_at >= '2026-10-02T20:30:00Z'"
                       " AND published_at < '2026-10-04T20:30:00Z'")[0][0]
    assert search(client, date_from="2026-10-03", date_to="2026-10-04")["total"] == expected > 0


@pytest.mark.parametrize("q", ["autocadz", "AUTOCADZ", "كارشناس زيگورات", "739 سال", "۷۳۹ سال", "99.5%", "zig_zag"])
def test_keyword_matches_across_case_letter_and_digit_variants(client, q):
    assert all_ids(client, q=q) == {"k1"}


def test_keyword_percent_and_underscore_are_literal(client):
    assert all_ids(client, q="99.5%") == {"k1"} and all_ids(client, q="g_z") == {"k1"}
    assert like_pattern("a%b_c\\") == "%a\\%b\\_c\\\\%"


def test_keyword_is_one_phrase(client, db):
    phrase = "مهندس عمران"
    expected = sql(db, "SELECT count(*) FROM postings WHERE instr(search_text, ?) > 0", phrase)[0][0]
    assert search(client, q=phrase)["total"] == expected > 0
    assert search(client, q="عمران مهندس")["total"] < expected


def test_keyword_result_has_a_snippet_around_the_match(client):
    [item] = search(client, q="739 سال")["items"]
    assert "۷۳۹ سال" in item["snippet"]


def test_tag_by_slug_or_label_including_spelling_variants(client, db):
    civil = sql(db, "SELECT count(*) FROM posting_tags WHERE kind = 'field' AND slug = 'civil'")[0][0]
    assert search(client, tag="civil")["total"] == search(client, tag="عمران")["total"] == civil
    surveying = sql(db, "SELECT count(*) FROM posting_tags WHERE slug = 'surveying'")[0][0]
    assert search(client, tag="نقشه برداری")["total"] == surveying > 0  # site writes برداري (Arabic ي)
    assert search(client, tag="no-such-tag")["total"] == 0


def test_all_filters_combine_with_and(client):
    both = all_ids(client, tag="civil", q="autocadz", date_from="2026-09-01", date_to="2026-09-01")
    assert both == {"k1"}
    assert all_ids(client, tag="tehran", q="autocadz") == set()
    assert all_ids(client, tag="civil", q="autocadz", date_from="2026-09-02") == set()


@pytest.mark.parametrize(
    "params",
    [{"date_from": "2026-13-01"}, {"date_to": "06/10/2026"}, {"date_from": "2026-10-7"}, {"date_to": "20261007"}, {"date_from": "0001-01-01"}, {"date_to": "9999-12-31"},
     {"date_from": "2026-10-07", "date_to": "2026-10-01"}, {"page": 0}, {"page_size": 101}],
)
def test_bad_parameters_are_422_with_a_message(client, params):
    response = client.get("/api/postings", params=params)
    assert response.status_code == 422 and response.json()["detail"]


def test_one_posting_has_the_full_body(client, db):
    row_id, body = sql(db, "SELECT id, body FROM postings WHERE source_post_id = 'k1'")[0]
    data = client.get(f"/api/postings/{row_id}").json()
    assert data["body"] == body and data["tags"] == [{"kind": "field", "slug": "civil", "label": "عمران"}]
    assert client.get("/api/postings/999999").status_code == 404


# --- tags and stats -------------------------------------------------------------------------

def test_tags_have_kind_label_and_counts(client):
    items = client.get("/api/tags").json()["items"]
    civil = next(t for t in items if t["slug"] == "civil")
    assert (civil["kind"], civil["label"], civil["count"]) == ("field", "عمران", 48)  # 47 site + 1 handmade
    assert [t["count"] for t in items] == sorted((t["count"] for t in items), reverse=True)


def test_stats_cover_the_seven_tehran_days_with_jalali_labels(client):
    data = client.get("/api/stats").json()
    assert [d["date"] for d in data["days"]][::6] == ["2026-10-01", "2026-10-07"]
    assert (data["days"][0]["jalali"], data["days"][-1]["jalali"]) == ("1405-07-09", "1405-07-15")
    assert sum(d["count"] for d in data["days"]) == 68 + 2  # the snapshot window plus b1 and b2
    assert data["top_tags"][0]["slug"] == "civil" and data["total_postings"] == 72


# --- runs and Collect now -------------------------------------------------------------------

def test_run_history_and_issues_grouped_by_code(client, db):
    conn = storage.connect(db)
    run_id = storage.start_run(conn, "eng-estekhdam", NOW)
    for _ in range(2):
        storage.add_issue(conn, run_id, storage.Issue.error("FETCH_TIMEOUT", "slow", "https://x"), "fetch")
    storage.add_issue(conn, run_id, storage.Issue.warning("TITLE_MISMATCH", "t"), "posting")
    storage.finish_run(conn, run_id, "partial", NOW)
    conn.close()

    newest = client.get("/api/runs", params={"limit": 1}).json()["items"]
    assert [(r["id"], r["status"], r["errors"], r["warnings"]) for r in newest] == [(run_id, "partial", 2, 1)]
    detail = client.get(f"/api/runs/{run_id}").json()
    assert [(g["code"], g["count"]) for g in detail["issues"]] == [("FETCH_TIMEOUT", 2), ("TITLE_MISMATCH", 1)]
    first = client.get("/api/runs/1").json()
    assert (first["status"], first["new"], first["window_start"]) == ("success", 68, "2026-09-30T20:30:00Z")
    assert client.get("/api/runs/999").status_code == 404


def test_collect_now_needs_the_trigger_header(client, launched):
    assert client.post("/api/runs").status_code == 403
    assert client.post("/api/runs", headers={"X-Collect-Trigger": "yes"}).status_code == 403
    assert launched == []


def test_collect_now_starts_one_run_and_refuses_a_second(client, launched, db):
    started = client.post("/api/runs", headers={"X-Collect-Trigger": "1"})
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    assert launched == [run_id]
    assert sql(db, "SELECT status FROM runs WHERE id = ?", run_id)[0][0] == "running"

    again = client.post("/api/runs", headers={"X-Collect-Trigger": "1"})
    assert (again.status_code, again.json()["run_id"], launched) == (409, run_id, [run_id])

    conn = storage.connect(db)
    storage.finish_run(conn, run_id, "success", NOW)
    conn.close()


def test_a_process_that_cannot_start_ends_its_run_as_failed(db):
    def broken(path, run_id):
        raise OSError("no python")

    client = TestClient(create_app(db, launch=broken, clock=lambda: NOW), raise_server_exceptions=False)
    response = client.post("/api/runs", headers={"X-Collect-Trigger": "1"})
    assert response.status_code == 500
    assert sql(db, "SELECT status FROM runs ORDER BY id DESC LIMIT 1")[0][0] == "failed"


def test_every_response_has_a_strict_content_security_policy(client):
    for response in (client.get("/api/tags"), client.get("/api/postings/999999"), client.post("/api/runs")):
        assert response.headers["content-security-policy"] == "default-src 'self'"
        assert response.headers["x-content-type-options"] == "nosniff"


def test_the_real_launcher_runs_the_same_command_as_the_terminal(monkeypatch, tmp_path):
    import api.app as app_module

    calls = []
    monkeypatch.setattr(app_module, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(app_module.subprocess, "Popen", lambda command, **kw: calls.append((command, kw)))
    app_module.launch_collector(Path("var/jobs.db"), 7)
    [(command, kw)] = calls
    assert command[1:] == ["-m", "collector", "--db", "var/jobs.db", "collect", "--run-id", "7"]
    assert kw["start_new_session"] and (tmp_path / "logs" / "run-7.log").exists()


def test_docs_pages_work_under_their_own_looser_csp(client):
    from api.app import DOCS_CSP

    for path in ("/docs", "/redoc"):
        page = client.get(path)
        assert page.status_code == 200 and page.headers["content-security-policy"] == DOCS_CSP
    assert "cdn.jsdelivr.net" in DOCS_CSP and "'unsafe-inline'" in DOCS_CSP
    for path in ("/", "/api/tags", "/static/app.js", "/openapi.json"):  # everything else stays strict
        assert client.get(path).headers["content-security-policy"] == "default-src 'self'"
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/api/postings", "/api/postings/{posting_id}", "/api/tags", "/api/stats", "/api/runs", "/api/runs/{run_id}"} <= set(paths)


def test_reading_runs_expires_a_run_that_died(client, db):
    conn = storage.connect(db)
    dead = storage.start_run(conn, "eng-estekhdam", NOW - timedelta(minutes=4))
    conn.close()
    run = client.get(f"/api/runs/{dead}").json()
    assert run["status"] == "failed" and [g["code"] for g in run["issues"]] == ["UNEXPECTED_ERROR"]
    assert client.post("/api/runs", headers={"X-Collect-Trigger": "1"}).status_code == 202  # not blocked

    conn = storage.connect(db)
    for (run_id,) in conn.execute("SELECT id FROM runs WHERE status = 'running'").fetchall():
        storage.finish_run(conn, run_id, "success", NOW)
    conn.close()


def test_reading_runs_leaves_a_live_run_alone(client, db):
    conn = storage.connect(db)
    live = storage.start_run(conn, "eng-estekhdam", NOW - timedelta(minutes=2))
    conn.close()
    assert client.get("/api/runs", params={"limit": 1}).json()["items"][0]["status"] == "running"
    conn = storage.connect(db)
    storage.finish_run(conn, live, "success", NOW)
    conn.close()


def test_within_one_day_the_newest_post_id_comes_first(tmp_path):
    db = tmp_path / "order.db"
    conn = storage.connect(db)
    for post_id in ("205137", "205131", "205134"):  # stored in this order (row ids 1, 2, 3)
        storage.upsert_posting(conn, handmade(post_id, f"ad {post_id}", "body text", date(2026, 10, 8))[0], NOW)
    conn.close()
    client = TestClient(create_app(db, clock=lambda: NOW))
    assert [i["source_post_id"] for i in search(client)["items"]] == ["205137", "205134", "205131"]
