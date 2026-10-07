"""The saved snapshot is complete and contains the kinds of pages the manifest claims.

Guards against a capture that silently saved a firewall page, an error page, or a
truncated set, which would make every later fixture-based test meaningless.
"""

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

SNAPSHOT = Path(__file__).parent / "fixtures" / "eng_estekhdam" / "snapshot"
MANIFEST = json.loads((SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))
PAGES = MANIFEST["pages"]


def soup(entry):
    return BeautifulSoup((SNAPSHOT / entry["file"]).read_text(encoding="utf-8"), "lxml")


def test_manifest_and_files_match_exactly():
    listed = {entry["file"] for entry in PAGES}
    on_disk = {path.name for path in SNAPSHOT.glob("*.html")}
    assert listed == on_disk


def test_every_posting_linked_from_saved_listings_was_saved():
    saved_urls = {entry["url"] for entry in PAGES if entry["kind"] == "posting"}
    linked = {
        anchor["href"]
        for entry in PAGES
        if entry["kind"] == "listing"
        for anchor in soup(entry).select("article.typology-post .entry-title a")
    }
    assert linked == saved_urls


@pytest.mark.parametrize("entry", [e for e in PAGES if e["kind"] == "listing"], ids=lambda e: e["file"])
def test_listing_pages_have_ten_cards_except_out_of_range(entry):
    cards = soup(entry).select("article.typology-post")
    expected = 0 if entry["url"].endswith("/page/99999/") else 10
    assert len(cards) == expected


@pytest.mark.parametrize("entry", [e for e in PAGES if e["kind"] == "posting"], ids=lambda e: e["file"])
def test_posting_pages_have_exactly_one_main_posting(entry):
    assert len(soup(entry).select("article.typology-single-post")) == 1
