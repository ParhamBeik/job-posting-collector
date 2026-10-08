"""The one browser test: scraped text shown on the page can never run as code (Playwright)."""

import socket
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import uvicorn

from api.app import create_app
from collector import storage
from collector.models import Issue, ListingItem, Tag
from collector.sources import SOURCES

MALICIOUS = Path(__file__).parent / "fixtures" / "eng_estekhdam" / "handmade" / "posting_malicious.html"
CARD = ListingItem(
    "900001",
    "https://eng-estekhdam.com/1405/07/15/harmless-test/",
    "مهندس عمران <img src=x onerror=window.__pwned=1>",
    date(2026, 10, 7),
    (Tag("province", "tehran"), Tag("field", "civil")),
)
NOW = datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc)


@pytest.fixture
def server(tmp_path):
    db = tmp_path / "jobs.db"
    conn = storage.connect(db)
    posting, _ = SOURCES["eng-estekhdam"].parse_posting(MALICIOUS.read_text(encoding="utf-8"), CARD)
    storage.upsert_posting(conn, posting, NOW)
    run_id = storage.start_run(conn, "eng-estekhdam", NOW)
    # Issue text and URLs come from the site too: an attack there must stay inert as well.
    storage.add_issue(conn, run_id, Issue.error("FIELD_MISSING", "<img src=x onerror=window.__pwned=2>",
                                                "javascript:window.__pwned=3"), "listing")
    storage.finish_run(conn, run_id, "partial", NOW)
    conn.close()

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(db, launch=lambda path, run_id: None, clock=lambda: NOW)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join()


def test_malicious_posting_is_shown_as_text_and_never_runs(page, server):
    page.goto(server)
    title = page.locator("#results .title")
    title.wait_for()
    # The attack is visible as literal characters...
    assert "<img src=x onerror=window.__pwned=1>" in title.inner_text()
    title.click()
    page.locator("#detail:not([hidden])").wait_for()
    assert "<img src=x" in page.locator("#detail-title").inner_text()
    page.locator("#runs tr").first.click()
    issues = page.locator("#run-issues")
    issues.wait_for()
    assert "<img src=x onerror=window.__pwned=2>" in issues.inner_text()

    # ...and nothing from it became markup or ran.
    assert page.locator("main img").count() == 0
    assert page.locator("#run-issues a").count() == 0  # the javascript: URL got no link
    assert page.evaluate("window.__pwned") is None
    assert page.locator("#detail-link").get_attribute("href").startswith("https://eng-estekhdam.com/")
    body = page.locator("#detail-body").inner_text()
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" not in body and "09120000000" not in body
