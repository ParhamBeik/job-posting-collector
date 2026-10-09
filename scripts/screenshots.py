"""Take the README screenshots of the page and the API docs in a real browser (Playwright).

By default the committed site snapshot is replayed into a temporary database with the clock set
to the moment it was saved, so anyone gets the same pictures without touching the website:

    python scripts/screenshots.py                    # replayed snapshot → docs/screenshots/
    python scripts/screenshots.py --db var/jobs.db   # your own collected data, real clock

The Swagger page loads its code from cdn.jsdelivr.net, so that one picture needs the internet.
"""

import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from conftest import serve  # noqa: E402  (the same local server the browser tests use)

from api.app import create_app  # noqa: E402
from collector import storage  # noqa: E402
from collector.core import collect, utc_now  # noqa: E402
from collector.fetch import DirFetcher  # noqa: E402
from collector.sources import SOURCES  # noqa: E402

SNAPSHOT = ROOT / "tests" / "fixtures" / "eng_estekhdam" / "snapshot"
SAVED_AT = datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc)  # when the snapshot was captured
DESKTOP = {"width": 1280, "height": 900}
PHONE = {"width": 375, "height": 812}


def replayed_db(folder: Path) -> Path:
    db = folder / "jobs.db"
    collect(storage.connect(db), SOURCES["eng-estekhdam"], DirFetcher(SNAPSHOT), lambda: SAVED_AT, folder / "s")
    return db


def shoot(base: str, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    taken = []

    def save(page, name):
        page.screenshot(path=out / name)
        taken.append(out / name)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=DESKTOP)
        page.goto(base)
        page.locator("#results li").first.wait_for()
        page.locator(".day").first.wait_for()
        save(page, "page-search.png")

        page.locator("#results li").first.click()
        page.locator("#detail-body").wait_for()
        page.locator("#results").scroll_into_view_if_needed()
        save(page, "page-detail.png")

        page.locator("#detail-close").click()
        page.locator("#runs tr").first.click()
        page.locator("#run-issues").scroll_into_view_if_needed()
        save(page, "page-run-history.png")

        page.goto(base + "/docs")
        page.locator(".opblock").first.wait_for(timeout=20_000)
        save(page, "page-api-docs.png")

        phone = browser.new_page(viewport=PHONE, device_scale_factor=2, is_mobile=True)
        phone.goto(base)
        phone.locator("#results li").first.wait_for()
        save(phone, "page-phone.png")
        phone.locator("#results li").first.click()
        phone.locator("#detail-body").wait_for()
        save(phone, "page-phone-detail.png")
        browser.close()
    return taken


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, help="use this database and the real clock instead of the replayed snapshot")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "screenshots")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        db, clock = (args.db, utc_now) if args.db else (replayed_db(Path(folder)), lambda: SAVED_AT)
        server = serve(create_app(db, launch=lambda path, run_id: None, clock=clock))
        base = next(server)
        try:
            for path in shoot(base, args.out):
                print(f"saved {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
        finally:
            next(server, None)  # stops the server


if __name__ == "__main__":
    main()
