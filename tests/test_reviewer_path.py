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
    assert showing(page) == "Showing 1–68 of 68"
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
