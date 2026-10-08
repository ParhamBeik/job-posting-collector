"""Shared fixture for the browser tests: a real API server on a temp database."""

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
MANY = 24  # more issues of one code than the page shows unfolded


@pytest.fixture
def server(tmp_path):
    """The malicious posting, and one finished run whose issues include an attack and many timeouts."""
    db = tmp_path / "jobs.db"
    conn = storage.connect(db)
    posting, _ = SOURCES["eng-estekhdam"].parse_posting(MALICIOUS.read_text(encoding="utf-8"), CARD)
    storage.upsert_posting(conn, posting, NOW)
    run_id = storage.start_run(conn, "eng-estekhdam", NOW)
    # Issue text and URLs come from the site too: an attack there must stay inert as well.
    storage.add_issue(conn, run_id, Issue.error("FIELD_MISSING", "<img src=x onerror=window.__pwned=2>",
                                                "javascript:window.__pwned=3"), "listing")
    for n in range(MANY):
        storage.add_issue(conn, run_id, Issue.error("FETCH_TIMEOUT", "no answer", f"https://eng-estekhdam.com/p/{n}/"), "fetch")
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
