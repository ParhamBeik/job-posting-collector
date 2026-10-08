"""Full collection runs against the saved snapshot, with failures injected. No network."""

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup

from collector import storage
from collector.__main__ import main
from collector.core import collect
from collector.dates import parse_jalali_date
from collector.fetch import DirFetcher, HttpFetcher
from collector.models import Issue
from collector.sources import SOURCES

FIXTURES = Path(__file__).parent / "fixtures" / "eng_estekhdam"
SNAPSHOT = FIXTURES / "snapshot"
NOW = datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc)  # when the snapshot was taken (20:30 Tehran)
SOURCE = SOURCES["eng-estekhdam"]
MANIFEST = json.loads((SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))
FILES = {e["url"]: e["file"] for e in MANIFEST["pages"]}
POSTING_URLS = [e["url"] for e in MANIFEST["pages"] if e["kind"] == "posting"]


def page(url: str) -> str:
    return (SNAPSHOT / FILES[url]).read_text(encoding="utf-8")


def in_window_count(first=date(2026, 10, 1), last=date(2026, 10, 7)) -> int:
    """Independent of the collector: count window dates in the raw HTML of all saved listing pages."""
    return sum(
        first <= parse_jalali_date(text) <= last
        for n in range(1, 9)
        for text in re.findall(r'class="post-date-hidden">([^<]+)<', page(SOURCE.listing_url(n)))
    )


def with_cards(listing_url: str, cards: list) -> str:
    """A listing page whose cards are replaced by the given ones (in that order)."""
    soup = BeautifulSoup(page(listing_url), "lxml")
    box = soup.select_one(".typology-posts")
    for card in box.select("article.typology-post"):
        card.extract()
    for card in cards:
        box.append(BeautifulSoup(str(card), "lxml").article)
    return str(soup)


def cards(listing_url: str) -> list:
    return BeautifulSoup(page(listing_url), "lxml").select("article.typology-post")


class FakeSite(DirFetcher):
    """The saved snapshot, with chosen URLs replaced by other HTML, an issue, or an exception."""

    def __init__(self, overrides=None):
        super().__init__(SNAPSHOT)
        self.overrides, self.requested = overrides or {}, []

    def get(self, url):
        self.requested.append(url)
        value = self.overrides.get(url)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, Issue):
            return None, [value]
        if isinstance(value, str):
            return value, []
        return super().get(url)


@pytest.fixture
def conn(tmp_path):
    connection = storage.connect(tmp_path / "jobs.db")
    yield connection
    connection.close()


def run(conn, tmp_path, fetcher, now=NOW, **kwargs):
    return collect(conn, SOURCE, fetcher, lambda: now, tmp_path / "snapshots", **kwargs)


def count(conn, sql="SELECT count(*) FROM postings", *args):
    return conn.execute(sql, args).fetchone()[0]


def codes(report):
    return [issue.code for _, issue in report.issues]


# --- complete runs --------------------------------------------------------------------------

def test_full_run_collects_exactly_the_window_then_reruns_without_duplicates(conn, tmp_path):
    site = FakeSite()
    report = run(conn, tmp_path, site)
    expected = in_window_count()
    assert (report.status, report.exit_code, report.issues) == ("success", 0, [])
    assert report.found == report.results["new"] == count(conn) == expected == 68
    assert report.pages_listing == 7  # page 7 holds the first card older than 9 Mehr
    assert [u for u in site.requested if u not in POSTING_URLS] == [SOURCE.listing_url(n) for n in range(1, 8)]
    assert len([u for u in site.requested if u in POSTING_URLS]) == expected  # out-of-window ads never fetched

    again = run(conn, tmp_path, FakeSite(), now=NOW + timedelta(minutes=5))
    assert (again.status, again.results["unchanged"], count(conn)) == ("success", 68, 68)


def test_postings_are_stamped_with_the_run_clock(conn, tmp_path):
    run(conn, tmp_path, FakeSite())
    stamps = conn.execute("SELECT DISTINCT collected_at, updated_at, last_seen_at FROM postings").fetchall()
    assert [tuple(r) for r in stamps] == [("2026-10-07T17:00:00Z",) * 3]


def test_window_dates_stored_are_inside_the_utc_window(conn, tmp_path):
    run(conn, tmp_path, FakeSite())
    low, high = conn.execute("SELECT min(published_at), max(published_at) FROM postings").fetchone()
    assert low >= "2026-09-30T20:30:00Z" and high < "2026-10-07T20:30:00Z"


def test_run_row_has_window_counters_and_health_numbers(conn, tmp_path):
    report = run(conn, tmp_path, FakeSite())
    row = dict(conn.execute("SELECT * FROM runs WHERE id = ?", (report.run_id,)).fetchone())
    assert row["status"] == "success" and row["finished_at"] == "2026-10-07T17:00:00Z"
    assert (row["window_start"], row["window_end"]) == ("2026-09-30T20:30:00Z", "2026-10-07T20:30:00Z")
    assert (row["pages_listing"], row["pages_posting"], row["new"], row["rejected"]) == (7, 68, 68, 0)
    assert (row["cards_per_page_avg"], row["date_ok_pct"], row["body_ok_pct"], row["tags_ok_pct"]) == (10.0, 100.0, 100.0, 100.0)
    assert row["parser_version"] == "eng-estekhdam/1"


def test_ads_dated_after_the_window_are_not_collected(conn, tmp_path):
    report = run(conn, tmp_path, FakeSite(), now=NOW - timedelta(days=2))  # window 29 Sep - 5 Oct
    assert report.found == count(conn) == in_window_count(date(2026, 9, 29), date(2026, 10, 5))
    assert conn.execute("SELECT max(published_at) FROM postings").fetchone()[0] < "2026-10-05T20:30:00Z"


def test_window_with_no_postings_is_a_successful_empty_run(conn, tmp_path):
    report = run(conn, tmp_path, FakeSite(), now=NOW + timedelta(days=13))  # window 22-28 Mehr
    assert (report.status, report.exit_code, report.found, report.pages_listing) == ("success_empty", 0, 0, 1)


# --- incomplete runs look different from empty ones ------------------------------------------

def test_empty_page_before_the_window_ends_is_incomplete_not_empty(conn, tmp_path):
    report = run(conn, tmp_path, FakeSite({SOURCE.listing_url(2): page(SOURCE.listing_url(99999))}))
    assert (report.status, report.exit_code) == ("incomplete", 2)
    assert "LISTING_EMPTY_EARLY" in codes(report)
    assert count(conn) == report.found > 0  # what was read before the gap is still stored


def test_listing_page_that_cannot_be_fetched_is_incomplete(conn, tmp_path):
    timeout = Issue.error("FETCH_TIMEOUT", "no answer in time after 3 attempts", SOURCE.listing_url(3))
    report = run(conn, tmp_path, FakeSite({SOURCE.listing_url(3): timeout}))
    assert (report.status, codes(report)) == ("incomplete", ["FETCH_TIMEOUT"])


def test_page_cap_stops_pagination_and_marks_the_run_incomplete(conn, tmp_path):
    report = run(conn, tmp_path, FakeSite(), page_cap=3)
    assert (report.status, report.pages_listing) == ("incomplete", 3)
    assert codes(report) == ["PAGE_CAP_REACHED"]


# --- partial runs -----------------------------------------------------------------------------

def test_one_failed_posting_page_makes_the_run_partial(conn, tmp_path):
    failed = POSTING_URLS[0]
    report = run(conn, tmp_path, FakeSite({failed: Issue.error("FETCH_TIMEOUT", "no answer", failed)}))
    assert (report.status, report.exit_code, codes(report)) == ("partial", 1, ["FETCH_TIMEOUT"])
    assert (report.rejected, count(conn)) == (1, 67)
    assert count(conn, "SELECT count(*) FROM run_issues WHERE code = 'FETCH_TIMEOUT'") == 1


def test_shifted_ads_are_counted_once_and_order_problems_are_reported(conn, tmp_path):
    # Page 2 answers with page 1's ads again, as if new ads pushed them down mid-run.
    report = run(conn, tmp_path, FakeSite({SOURCE.listing_url(2): page(SOURCE.listing_url(1))}))
    assert "LISTING_ORDER_BROKEN" in codes(report)
    assert count(conn) == report.found == count(conn, "SELECT count(DISTINCT source_post_id) FROM postings")


def test_broken_order_keeps_paging_until_a_page_is_wholly_older(conn, tmp_path):
    # Page 7 (two 10 Mehr, six 9 Mehr, two 8 Mehr) is split: the two older cards come first, and
    # three in-window cards slip onto page 8. Stopping at the first older card would miss them.
    seven, eight = cards(SOURCE.listing_url(7)), cards(SOURCE.listing_url(8))
    site = FakeSite({
        SOURCE.listing_url(7): with_cards(SOURCE.listing_url(7), seven[8:] + seven[:5]),
        SOURCE.listing_url(8): with_cards(SOURCE.listing_url(8), seven[5:8] + eight),
        SOURCE.listing_url(9): page(SOURCE.listing_url(8)),
    })
    report = run(conn, tmp_path, site)
    assert (report.status, report.found, count(conn), report.pages_listing) == ("success_with_warnings", 68, 68, 9)
    assert "LISTING_ORDER_BROKEN" in codes(report)


# --- blocked, broken parser, crash -------------------------------------------------------------

def test_firewall_page_blocks_the_run_and_is_saved_for_inspection(conn, tmp_path):
    challenge = (FIXTURES / "handmade" / "challenge_page.html").read_text(encoding="utf-8")
    report = run(conn, tmp_path, FakeSite({SOURCE.listing_url(1): challenge}))
    assert (report.status, report.exit_code, codes(report)) == ("blocked", 3, ["BLOCKED_CHALLENGE"])
    assert count(conn) == 0
    [path] = [r[0] for r in conn.execute("SELECT snapshot_path FROM run_issues")]
    assert "Checking your browser" in Path(path).read_text(encoding="utf-8")

    # Replay the saved problem page offline: same result.
    replay = run(conn, tmp_path, DirFetcher(Path(path).parent))
    assert (replay.status, codes(replay)) == ("blocked", ["BLOCKED_CHALLENGE"])


def test_firewall_on_a_posting_page_stops_asking(conn, tmp_path):
    challenge = (FIXTURES / "handmade" / "challenge_page.html").read_text(encoding="utf-8")
    site = FakeSite({POSTING_URLS[0]: challenge})
    report = run(conn, tmp_path, site)
    assert report.status == "blocked"
    assert site.requested[-1] == POSTING_URLS[0]  # no request after the refusal


def test_problem_run_folder_replays_the_whole_run(conn, tmp_path):
    # A problem on a posting page: the folder also holds the listing pages and the other postings.
    bad = POSTING_URLS[5]
    report = run(conn, tmp_path, FakeSite({bad: page(POSTING_URLS[6])}))
    assert (report.status, codes(report)) == ("partial", ["ID_MISMATCH"])
    folder = tmp_path / "snapshots" / str(report.run_id)
    replay = run(conn, tmp_path, DirFetcher(folder))
    assert (replay.status, codes(replay), replay.found) == ("partial", ["ID_MISMATCH"], 68)


def test_unrecognized_first_page_trips_the_breaker(conn, tmp_path):
    report = run(conn, tmp_path, FakeSite({SOURCE.listing_url(1): "<html><body><p>New design!</p></body></html>"}))
    assert (report.status, report.exit_code) == ("parser_broken", 4)
    assert codes(report) == ["LAYOUT_UNRECOGNIZED", "BREAKER_TRIPPED"]


def test_mostly_invalid_postings_trip_the_breaker_and_store_nothing(conn, tmp_path):
    # Every posting URL answers with some other ad's page: all fail the ID check.
    wrong = {url: page(POSTING_URLS[(i + 1) % len(POSTING_URLS)]) for i, url in enumerate(POSTING_URLS)}
    report = run(conn, tmp_path, FakeSite(wrong))
    assert (report.status, report.exit_code) == ("parser_broken", 4)
    assert codes(report).count("ID_MISMATCH") == 68 and codes(report)[-1] == "BREAKER_TRIPPED"
    assert count(conn) == 0
    row = conn.execute("SELECT rejected, pages_posting, new FROM runs").fetchone()
    assert tuple(row) == (68, 68, 0)  # the run row tells the same story as the printed report


def test_a_few_invalid_postings_do_not_trip_the_breaker(conn, tmp_path):
    wrong = {url: page(POSTING_URLS[(i + 1) % len(POSTING_URLS)]) for i, url in enumerate(POSTING_URLS[:3])}
    report = run(conn, tmp_path, FakeSite(wrong))
    assert report.status == "partial" and count(conn) == 65


@pytest.mark.parametrize("bad, status", [(20, "partial"), (21, "parser_broken")])
def test_breaker_trips_only_above_thirty_percent(conn, tmp_path, bad, status):
    # 20 of 68 invalid = 29.4 % (kept), 21 of 68 = 30.9 % (tripped)
    wrong = {url: page(POSTING_URLS[(i + 1) % len(POSTING_URLS)]) for i, url in enumerate(POSTING_URLS[:bad])}
    assert run(conn, tmp_path, FakeSite(wrong)).status == status


def test_a_bug_ends_the_run_as_failed_and_recorded(conn, tmp_path):
    report = run(conn, tmp_path, FakeSite({POSTING_URLS[0]: RuntimeError("boom")}))
    assert (report.status, report.exit_code, codes(report)) == ("failed", 5, ["UNEXPECTED_ERROR"])
    row = conn.execute("SELECT status, finished_at FROM runs").fetchone()
    assert tuple(row) == ("failed", "2026-10-07T17:00:00Z")


def test_a_second_run_cannot_start_while_one_is_running(conn, tmp_path):
    storage.start_run(conn, "eng-estekhdam", NOW)
    with pytest.raises(storage.RunActive):
        run(conn, tmp_path, FakeSite())


def test_run_started_by_the_api_is_continued_not_duplicated(conn, tmp_path):
    run_id = storage.start_run(conn, "eng-estekhdam", NOW)
    report = run(conn, tmp_path, FakeSite(), run_id=run_id)
    assert report.run_id == run_id and count(conn, "SELECT count(*) FROM runs") == 1


# --- polite HTTP ------------------------------------------------------------------------------

def http_fetcher(handler):
    sleeps, clock = [], [0.0]

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    fetcher = HttpFetcher(httpx.Client(transport=httpx.MockTransport(handler)), sleep, lambda: clock[0])
    return fetcher, sleeps


def test_live_client_identifies_itself_and_never_follows_redirects():
    client = HttpFetcher().client
    assert client.follow_redirects is False
    assert "job-posting-collector" in client.headers["user-agent"]


def test_requests_are_paced_one_per_second():
    fetcher, sleeps = http_fetcher(lambda request: httpx.Response(200, text="ok"))
    fetcher.get("https://eng-estekhdam.com/")
    fetcher.get("https://eng-estekhdam.com/page/2/")
    assert sleeps == [1.0]


def test_temporary_failure_is_retried_and_reported_as_recovered():
    answers = iter([httpx.Response(503), httpx.Response(200, text="ok")])
    fetcher, sleeps = http_fetcher(lambda request: next(answers))
    html, issues = fetcher.get("https://eng-estekhdam.com/")
    assert html == "ok" and [(i.code, i.severity) for i in issues] == [("RETRY_RECOVERED", "warning")]
    assert 2.0 in sleeps


@pytest.mark.parametrize(
    "fail, code",
    [
        (httpx.ReadTimeout("slow"), "FETCH_TIMEOUT"),
        (httpx.ConnectError("refused"), "FETCH_CONNECTION"),
        (httpx.Response(429), "HTTP_RATE_LIMITED"),
        (httpx.Response(502), "HTTP_SERVER_ERROR"),
    ],
)
def test_retries_are_bounded_to_three_attempts(fail, code):
    attempts = []

    def handler(request):
        attempts.append(request)
        if isinstance(fail, Exception):
            raise fail
        return fail

    fetcher, sleeps = http_fetcher(handler)
    html, issues = fetcher.get("https://eng-estekhdam.com/")
    assert html is None and len(attempts) == 3
    assert [(i.code, i.severity) for i in issues] == [(code, "error")]
    assert [s for s in sleeps if s in (2.0, 4.0)] == [2.0, 4.0]


@pytest.mark.parametrize("status", [404, 403, 301])
def test_permanent_errors_and_redirects_are_not_retried_or_followed(status):
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(status, headers={"location": "https://elsewhere.example/"})

    fetcher, _ = http_fetcher(handler)
    html, issues = fetcher.get("https://eng-estekhdam.com/")
    assert html is None and len(attempts) == 1 and issues[0].code == "HTTP_CLIENT_ERROR"


def test_live_fetcher_end_to_end_with_one_slow_posting(conn, tmp_path):
    slow = POSTING_URLS[0]

    def handler(request):
        url = str(request.url)
        if url == slow:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, text=page(url)) if url in FILES else httpx.Response(404)

    fetcher, sleeps = http_fetcher(handler)
    report = run(conn, tmp_path, fetcher)
    assert (report.status, codes(report), count(conn)) == ("partial", ["FETCH_TIMEOUT"], 67)


# --- command line -----------------------------------------------------------------------------

def test_cli_replays_a_snapshot_and_returns_the_status_exit_code(tmp_path, capsys):
    args = ["--db", str(tmp_path / "j.db"), "collect", "--from-dir", str(SNAPSHOT),
            "--now", "2026-10-07T17:00:00Z", "--snapshots", str(tmp_path / "s")]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "SUCCESS" in out and "68 found, 68 new" in out and "2026-09-30T20:30:00Z" in out


def test_cli_refuses_a_fake_clock_for_live_runs(tmp_path):
    with pytest.raises(SystemExit):
        main(["--db", str(tmp_path / "j.db"), "collect", "--now", "2026-10-07T17:00:00Z"])


def test_cli_reports_a_run_already_in_progress(tmp_path, capsys):
    db = tmp_path / "j.db"
    storage.start_run(storage.connect(db), "eng-estekhdam", datetime.now(timezone.utc))
    assert main(["--db", str(db), "collect", "--from-dir", str(SNAPSHOT), "--now", "2026-10-07T17:00:00Z"]) == 6
    assert "not started" in capsys.readouterr().err
