"""Save a snapshot of real eng-estekhdam pages as test fixtures.

Run by hand, rarely: tests never touch the network. Saves listing pages 1..N, one
out-of-range listing page, and every posting linked from those listing pages, plus a
manifest mapping each URL to its file. One request per second, honest User-Agent,
public pages only.

    python scripts/capture_fixtures.py --max-page 8

The new capture is written to a temporary folder and replaces the snapshot only after
every page succeeded, so a refresh never mixes old and new files.
"""

import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

BASE = "https://eng-estekhdam.com"
HOST = "eng-estekhdam.com"
USER_AGENT = "job-posting-collector/0.1 (+https://github.com/ParhamBeik/job-posting-collector)"
OUT_OF_RANGE_PAGE = 99999
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "eng_estekhdam" / "snapshot"


def listing_url(page: int) -> str:
    return f"{BASE}/" if page == 1 else f"{BASE}/page/{page}/"


def check_source_url(url: str) -> None:
    """Listing HTML is untrusted: only ever request http(s) URLs on the source host."""
    parts = urlsplit(url)  # a malformed URL raises ValueError and stops the capture too
    if parts.scheme not in ("http", "https") or parts.netloc != HOST:
        raise ValueError(f"refusing to fetch non-source URL: {url!r}")


def posting_links(html: str) -> list[tuple[str, str]]:
    """(post_id, url) for each card on a listing page, in page order."""
    links = []
    for article in BeautifulSoup(html, "lxml").select("article.typology-post"):
        match = re.search(r"\bpost-(\d+)\b", " ".join(article.get("class", [])))
        anchor = article.select_one(".entry-title a")
        if match and anchor and anchor.get("href"):
            links.append((match.group(1), anchor["href"]))
    return links


def capture(client: httpx.Client, out: Path, max_page: int, sleep=time.sleep) -> int:
    """Capture into a temporary folder, then swap it in for `out`. Returns pages saved."""
    tmp = out.with_name(out.name + ".partial")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    entries = []

    def save(url: str, kind: str, filename: str) -> str:
        check_source_url(url)
        if entries:
            sleep(1)  # pacing: one request per second
        response = client.get(url)
        # Redirects are not followed, so a 3xx (possibly off-site) also stops the capture.
        if response.status_code != 200:
            raise RuntimeError(f"{url} answered {response.status_code}; capture aborted")
        (tmp / filename).write_text(response.text, encoding="utf-8")
        entries.append({"url": url, "kind": kind, "file": filename, "status": response.status_code})
        print(f"{response.status_code} {kind:8} {filename}", file=sys.stderr)
        return response.text

    postings = []
    for page in [*range(1, max_page + 1), OUT_OF_RANGE_PAGE]:
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
        "max_page": max_page,
        "pages": entries,
    }
    (tmp / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)
    return len(entries)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-page", type=int, default=8, help="last listing page to save")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=False)
    saved = capture(client, args.out, args.max_page)
    print(f"saved {saved} pages to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
