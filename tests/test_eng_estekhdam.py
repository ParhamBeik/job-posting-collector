"""eng-estekhdam adapter, against the saved real snapshot and hand-made edge cases."""

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from collector.dates import parse_jalali_date
from collector.models import ListingItem, Tag
from collector.sources import SOURCES

FIXTURES = Path(__file__).parent / "fixtures" / "eng_estekhdam"
SNAPSHOT = FIXTURES / "snapshot"
HANDMADE = FIXTURES / "handmade"
MANIFEST = json.loads((SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))
FILE_BY_URL = {entry["url"]: entry["file"] for entry in MANIFEST["pages"]}
LISTINGS = [e["file"] for e in MANIFEST["pages"] if e["kind"] == "listing"]
source = SOURCES["eng-estekhdam"]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def all_cards() -> list[ListingItem]:
    cards = []
    for name in LISTINGS:
        items, issues = source.parse_listing(read(SNAPSHOT / name))
        assert issues == []
        cards += items
    return cards


def posting_for(item: ListingItem):
    return source.parse_posting(read(SNAPSHOT / FILE_BY_URL[item.url]), item)


# --- page recognition -------------------------------------------------------------------

@pytest.mark.parametrize("name", LISTINGS)
def test_real_listing_pages_are_recognized(name):
    assert source.check_page(read(SNAPSHOT / name), "listing") is None


def test_real_posting_page_is_recognized():
    assert source.check_page(read(SNAPSHOT / "posting-205126.html"), "posting") is None


def test_recaptcha_script_on_real_pages_is_not_mistaken_for_a_firewall():
    html = read(SNAPSHOT / "posting-205126.html")
    assert "recaptcha" in html  # every real page loads it
    assert source.check_page(html, "listing") == "LAYOUT_UNRECOGNIZED"


def test_site_page_mentioning_a_security_check_is_not_called_a_firewall():
    html = read(SNAPSHOT / "posting-205126.html").replace("منبع :", "security check منبع :")
    assert source.check_page(html, "listing") == "LAYOUT_UNRECOGNIZED"


def test_firewall_page_is_reported_as_blocked():
    html = read(HANDMADE / "challenge_page.html")
    assert source.check_page(html, "listing") == "BLOCKED_CHALLENGE"
    assert source.check_page(html, "posting") == "BLOCKED_CHALLENGE"


def test_unknown_page_is_reported_as_unrecognized():
    assert source.check_page("<html><body><p>Under maintenance</p></body></html>", "listing") == "LAYOUT_UNRECOGNIZED"


# --- listing pages ------------------------------------------------------------------------

def test_first_listing_card_fields():
    items, issues = source.parse_listing(read(SNAPSHOT / "listing-00001.html"))
    assert issues == [] and len(items) == 10
    first = items[0]
    assert first.source_post_id == "205126"
    assert first.title == "استخدام طراح فاز دو و دیتیل اجرایی غرفه مسلط به تهیه نقشه‌های اجرایی دقیق"
    assert first.url.startswith("https://eng-estekhdam.com/1405/07/15/")
    assert first.published_date == date(2026, 10, 7)
    assert first.tags == (Tag("province", "tehran"), Tag("field", "memari"))
    assert items[1].tags == (Tag("province", "kerman"), Tag("field", "civil"), Tag("field", "surveying"))


def test_out_of_range_page_has_no_cards_and_no_issues():
    assert source.parse_listing(read(SNAPSHOT / "listing-99999.html")) == ([], [])


def test_every_card_in_the_snapshot_parses_and_dates_match_a_plain_text_count():
    cards = all_cards()
    assert len(cards) == len({c.source_post_id for c in cards}) == 80
    # Independent of the parser: count the date strings in the raw HTML.
    raw = Counter(
        parse_jalali_date(text)
        for name in LISTINGS
        for text in re.findall(r'class="post-date-hidden">([^<]+)<', read(SNAPSHOT / name))
    )
    assert Counter(c.published_date for c in cards) == raw


def test_invalid_cards_are_reported_one_by_one_and_valid_ones_kept():
    items, issues = source.parse_listing(read(HANDMADE / "listing_invalid_cards.html"))
    assert [i.source_post_id for i in items] == ["900001"]
    assert [(i.code, i.severity) for i in issues] == [
        ("FIELD_MISSING", "error"),  # no date
        ("DATE_UNPARSEABLE", "error"),  # "مهرماه"
        ("DATE_MISMATCH", "error"),  # card 15 Mehr, URL 14 Mehr
        ("URL_REJECTED", "error"),  # javascript:
        ("URL_REJECTED", "error"),  # off-site look-alike
        ("FIELD_MISSING", "error"),  # no post id
        ("FIELD_MISSING", "error"),  # empty title
    ]
    assert "no date" in issues[0].detail and "no title" in issues[6].detail


# --- posting pages ------------------------------------------------------------------------

def test_every_posting_in_the_snapshot_parses_without_issues():
    for card in all_cards():
        posting, issues = posting_for(card)
        assert issues == [], card.url
        assert posting.body and posting.published_date == card.published_date


def test_body_excludes_related_ads_widgets_and_members_only_block():
    for card in all_cards():
        html = read(SNAPSHOT / FILE_BY_URL[card.url])
        posting, _ = source.parse_posting(html, card)
        related_titles = [
            " ".join(a.get_text().split())
            for a in BeautifulSoup(html, "lxml").select("article.typology-post:not(.typology-single-post) .entry-title a")
        ]
        assert related_titles  # every real posting page shows 4-5 related ads
        for title in related_titles:
            assert title not in posting.body
        for unwanted in ("گزارش کردن آگهی", "دسترسی اختصاصی اعضا", "rcp-graphical-message", "عضویت در سایت"):
            assert unwanted not in posting.body


def test_posting_body_keeps_paragraphs_and_list_items_as_lines():
    posting, _ = posting_for(all_cards()[0])
    lines = posting.body.splitlines()
    assert lines[0].startswith("به طراح فاز دو و دیتیل اجرایی غرفه")
    assert "- مسلط به AutoCAD و تهیه نقشه‌های اجرایی دقیق" in lines
    assert lines[-1].startswith("منبع :")  # the source credit line closes every ad


def test_tags_come_from_the_posting_with_persian_labels():
    cards = {c.source_post_id: c for c in all_cards()}
    posting, _ = posting_for(cards["205126"])
    assert posting.tags == (Tag("province", "tehran", "تهران"), Tag("field", "memari", "معماری"))
    two_provinces, _ = posting_for(cards["205018"])
    assert {t for t in two_provinces.tags if t.kind == "province"} == {
        Tag("province", "alborz", "البرز"),
        Tag("province", "tehran", "تهران"),
    }


def test_posting_page_must_be_the_post_the_card_points_to():
    card = all_cards()[0]
    wrong = ListingItem("1", card.url, card.title, card.published_date, card.tags)
    posting, issues = posting_for(wrong)
    assert posting is None and [i.code for i in issues] == ["ID_MISMATCH"]


def test_posting_date_must_match_the_card():
    card = all_cards()[0]
    shifted = ListingItem(card.source_post_id, card.url, card.title, date(2026, 10, 6), card.tags)
    posting, issues = posting_for(shifted)
    assert posting is None and [i.code for i in issues] == ["DATE_MISMATCH"]


def test_tag_disagreement_is_a_warning_not_a_rejection():
    card = all_cards()[0]
    other_tags = ListingItem(card.source_post_id, card.url, card.title, card.published_date, (Tag("field", "civil"),))
    posting, issues = posting_for(other_tags)
    assert posting is not None
    assert [(i.code, i.severity) for i in issues] == [("TAGS_MISMATCH", "warning")]


# --- untrusted HTML -----------------------------------------------------------------------

MALICIOUS_CARD = ListingItem(
    "900001",
    "https://eng-estekhdam.com/1405/07/15/harmless-test/",
    "مهندس عمران",
    date(2026, 10, 7),
    (Tag("province", "tehran"), Tag("field", "civil")),
)


def test_malicious_posting_yields_plain_text_only():
    html = read(HANDMADE / "posting_malicious.html")
    assert source.check_page(html, "posting") is None
    posting, issues = source.parse_posting(html, MALICIOUS_CARD)
    assert issues == []
    # No markup and no script source survives; event handlers and URLs are gone with their tags.
    assert "window.__pwned" not in posting.body
    assert "<" not in posting.body and "javascript" not in posting.body
    # Hidden text (a common way to plant instructions) and members-only contact details are dropped.
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" not in posting.body
    assert "hidden paragraph" not in posting.body
    assert "09120000000" not in posting.body
    # A related ad placed before the main one is ignored.
    assert "آگهی مرتبط" not in posting.body and posting.source_post_id == "900001"
    # Visible text is kept, as text.
    assert posting.body.splitlines() == [
        "متن عادی آگهی برای مهندس عمران با سه سال سابقه کار.",
        "متن با رویداد ماوس",
        "لینک اجرایی",
        "منبع : ای استخدام",
    ]


def test_markup_shown_as_text_on_the_source_stays_literal_text():
    posting, _ = source.parse_posting(read(HANDMADE / "posting_malicious.html"), MALICIOUS_CARD)
    # The real <img> tag is dropped; the escaped text the site displayed is kept as characters.
    # It is safe because the page renders it with textContent (step 7 browser test).
    assert posting.title == "مهندس عمران <img src=x onerror=window.__pwned=1>"
