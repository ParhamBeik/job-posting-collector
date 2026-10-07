"""Save a snapshot of real eng-estekhdam pages as test fixtures.

Run by hand, rarely: tests never touch the network. Saves listing pages 1..N, one
out-of-range listing page, and every posting linked from those listing pages, plus a
manifest mapping each URL to its file. One request per second, honest User-Agent,
public pages only.

    python scripts/capture_fixtures.py --max-page 8
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

BASE = "https://eng-estekhdam.com"
USER_AGENT = "job-posting-collector/0.1 (+https://github.com/ParhamBeik/job-posting-collector)"
OUT_OF_RANGE_PAGE = 99999
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "eng_estekhdam" / "snapshot"


def listing_url(page: int) -> str:
    return f"{BASE}/" if page == 1 else f"{BASE}/page/{page}/"


def posting_links(html: str) -> list[tuple[str, str]]:
    """(post_id, url) for each card on a listing page, in page order."""
    links = []
    for article in BeautifulSoup(html, "lxml").select("article.typology-post"):
        match = re.search(r"\bpost-(\d+)\b", " ".join(article.get("class", [])))
        anchor = article.select_one(".entry-title a")
        if match and anchor and anchor.get("href"):
            links.append((match.group(1), anchor["href"]))
    return links


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-page", type=int, default=8, help="last listing page to save")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True)
    entries = []

    def save(url: str, kind: str, filename: str) -> str:
        if entries:
            time.sleep(1)  # pacing: one request per second
        response = client.get(url)
        response.raise_for_status()  # a failed capture must stop loudly, not save an error page
        (args.out / filename).write_text(response.text, encoding="utf-8")
        entries.append({"url": url, "kind": kind, "file": filename, "status": response.status_code})
        print(f"{response.status_code} {kind:8} {filename}", file=sys.stderr)
        return response.text

    postings = []
    for page in [*range(1, args.max_page + 1), OUT_OF_RANGE_PAGE]:
        html = save(listing_url(page), "listing", f"listing-{page:05d}.html")
        postings += posting_links(html)

    seen = set()
    for post_id, url in postings:
        if post_id not in seen:  # an ad can appear on two pages if new ads arrive mid-capture
            seen.add(post_id)
            save(url, "posting", f"posting-{post_id}.html")

    manifest = {
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": BASE,
        "max_page": args.max_page,
        "pages": entries,
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"saved {len(entries)} pages to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
