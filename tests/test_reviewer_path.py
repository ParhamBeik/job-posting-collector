"""The path a reviewer takes, in a real browser, on the replayed site snapshot (offline).

Collect (replay) → open the page → see the last run → search by each filter and all together →
open a posting → follow its original link. Counts on the page must equal the API's counts.
"""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from playwright.sync_api import expect

from api.app import create_app
from collector import storage
from collector.core import collect
from collector.fetch import DirFetcher
from collector.sources import SOURCES
from conftest import NOW, serve

SNAPSHOT = Path(__file__).parent / "fixtures" / "eng_estekhdam" / "snapshot"
EDITED = "https://eng-estekhdam.com/1405/07/15/"  # first posting URL of 15 Mehr gets an edited body
RUNS = 13  # 10 runs per page on the page


class EditedSite(DirFetcher):
    """The snapshot, with one posting's text changed, as if the site edited the ad later."""

    def get(self, url):
        html, issues = super().get(url)
        if html and url == self.edited:
            html = html.replace("</p>", " (ویرایش شد)</p>", 1)
        return html, issues


@pytest.fixture
def site(tmp_path):
    db = tmp_path / "jobs.db"
    conn = storage.connect(db)
    collect(conn, SOURCES["eng-estekhdam"], DirFetcher(SNAPSHOT), lambda: NOW, tmp_path / "s")
    edited = EditedSite(SNAPSHOT)
    edited.edited = next(url for url in edited.files if url.startswith(EDITED))
    collect(conn, SOURCES["eng-estekhdam"], edited, lambda: NOW + timedelta(hours=1), tmp_path / "s")
    for _ in range(RUNS - 2):  # enough history for two pages of runs
        storage.finish_run(conn, storage.start_run(conn, "eng-estekhdam", NOW), "success", NOW)
    conn.close()
    yield from serve(create_app(db, launch=lambda path, run_id: None, clock=lambda: NOW))


def showing(page) -> str:
    page.locator("#results li").first.wait_for()
    return page.locator("#showing").inner_text()


def expect_total(page, total: int) -> None:
    """Waits until the list says '… of <total>' (the list reloads after each search)."""
    expect(page.locator("#showing")).to_have_text(re.compile(rf" of {total}$"))


def api_total(page, base, query) -> int:
    return page.request.get(f"{base}/api/postings?{query}").json()["total"]


def test_reviewer_path_search_each_filter_together_and_open_a_posting(page, site):
    errors = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))

    page.goto(site)
    assert showing(page) == "Showing 1–20 of 68"  # 20 per page unless the reader picks more
    assert "success" in page.locator("#run-status").inner_text()  # the second (edit) run
    assert page.locator(".day").count() == 7

    for query in ("q=autocad", "tag=civil", "date_from=2026-10-06&date_to=2026-10-06",
                  "q=autocad&tag=civil&date_from=2026-10-01&date_to=2026-10-07"):
        page.goto(f"{site}/?{query}")
        total = api_total(page, site, query)
        assert total > 0, query
        expect_total(page, total)

    page.goto(site)
    page.fill("[name=q]", "AutoCAD")
    page.select_option("[name=tag]", "civil")
    page.click("#search button[type=submit]")
    page.wait_for_url("**q=AutoCAD**")
    expect_total(page, api_total(page, site, "q=AutoCAD&tag=civil"))

    first = page.locator("#results li").first
    title = first.locator(".title").inner_text()
    first.click()
    page.locator("#detail-body").wait_for()
    assert page.locator("#detail-title").inner_text() == title
    assert len(page.locator("#detail-body").inner_text()) > 40
    assert page.get_attribute("#detail-link", "href").startswith("https://eng-estekhdam.com/1405/07/")
    assert "collected" in page.locator("#detail-meta").inner_text()
    assert errors == []


def test_an_ad_edited_on_the_site_is_marked_and_the_others_are_not(page, site):
    page.goto(site)
    showing(page)
    marked = page.locator("#results li", has_text="edited on the site")
    assert marked.count() == 1
    marked.click()
    page.locator("#detail-body").wait_for()
    assert "edited on the site since first collected" in page.locator("#detail-meta").inner_text()
    assert "(ویرایش شد)" in page.locator("#detail-body").inner_text()


def test_phone_width_has_no_sideways_scroll(page, site):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(site)
    showing(page)
    assert page.evaluate("document.documentElement.scrollWidth") <= 375


def test_postings_page_size_and_page_turning_keep_the_filters(page, site):
    page.goto(site + "/?tag=civil")
    total = api_total(page, site, "tag=civil")
    assert total > 20
    expect(page.locator("#showing")).to_have_text(f"Showing 1–20 of {total}")
    page.select_option("#page-size", "50")
    expect(page.locator("#showing")).to_have_text(f"Showing 1–{min(50, total)} of {total}")
    assert "page_size=50" in page.url and "tag=civil" in page.url

    page.goto(site)
    showing(page)
    page.select_option("#page-size", "50")
    expect(page.locator("#page-of")).to_have_text("Page 1 of 2")
    page.click("#next")
    expect(page.locator("#showing")).to_have_text("Showing 51–68 of 68")
    expect(page.locator("#results li")).to_have_count(18)
    assert page.locator("#next").is_disabled() and "page=2" in page.url
    page.reload()  # the URL keeps the page and the size
    expect(page.locator("#showing")).to_have_text("Showing 51–68 of 68")
    page.click("#prev")
    expect(page.locator("#showing")).to_have_text("Showing 1–50 of 68")
    page.select_option("#page-size", "100")
    expect(page.locator("#showing")).to_have_text("Showing 1–68 of 68")
    assert page.locator("#pager").is_hidden()


def test_run_history_shows_ten_runs_per_page(page, site):
    page.goto(site)
    expect(page.locator("#runs tr")).to_have_count(10)
    expect(page.locator("#runs-page-of")).to_have_text(f"Page 1 of 2 · {RUNS} runs")
    newest = page.locator("#runs tr").first.get_attribute("data-id")
    page.click("#runs-next")
    expect(page.locator("#runs tr")).to_have_count(RUNS - 10)
    assert page.locator("#runs-next").is_disabled()
    assert page.locator("#runs tr").last.get_attribute("data-id") == "1"
    # The "Last run" tile still shows the newest run, not the first row of page 2.
    assert f"#{newest} ·" in page.locator("#run-status").inner_text()
    page.click("#runs-prev")
    expect(page.locator("#runs tr")).to_have_count(10)
