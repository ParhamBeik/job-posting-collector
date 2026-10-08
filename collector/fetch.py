"""Getting pages: politely from the live site, or from a saved snapshot folder (replay).

Both fetchers return (html or None, issues). A page that could not be fetched is never an
exception: it is an issue the run reports.
"""

import json
import time
from pathlib import Path

import httpx

from collector.models import Issue

USER_AGENT = "job-posting-collector/0.1 (+https://github.com/ParhamBeik/job-posting-collector)"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)
ATTEMPTS = 3
BACKOFF = (2.0, 4.0)  # seconds to wait before attempts 2 and 3
PACE = 1.0  # at least this many seconds between the starts of two requests


class HttpFetcher:
    """One request at a time, at most one per second, bounded retries for temporary failures."""

    def __init__(self, client: httpx.Client | None = None, sleep=time.sleep, clock=time.monotonic):
        # Redirects are not followed: a redirected page is reported, never silently replaced.
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=False
        )
        self.sleep, self.clock = sleep, clock
        self._last_start: float | None = None

    def get(self, url: str) -> tuple[str | None, list[Issue]]:
        failure = None
        for attempt in range(1, ATTEMPTS + 1):
            if attempt > 1:
                self.sleep(BACKOFF[attempt - 2])
            self._pace()
            try:
                response = self.client.get(url)
            except httpx.TimeoutException:
                failure = ("FETCH_TIMEOUT", "no answer in time")
                continue
            except httpx.TransportError as error:
                failure = ("FETCH_CONNECTION", type(error).__name__)
                continue
            status = response.status_code
            if status == 200:
                if failure is None:
                    return response.text, []
                return response.text, [Issue.warning("RETRY_RECOVERED", f"ok on attempt {attempt}: {failure[1]}", url)]
            if status == 429:
                failure = ("HTTP_RATE_LIMITED", "429 Too Many Requests")
            elif status >= 500:
                failure = ("HTTP_SERVER_ERROR", f"HTTP {status}")
            else:  # 3xx and other 4xx are not temporary: no retry
                where = f" to {response.headers.get('location')}" if 300 <= status < 400 else ""
                return None, [Issue.error("HTTP_CLIENT_ERROR", f"HTTP {status}{where}", url)]
        code, detail = failure
        return None, [Issue.error(code, f"{detail} after {ATTEMPTS} attempts", url)]

    def _pace(self) -> None:
        now = self.clock()
        if self._last_start is not None and now - self._last_start < PACE:
            self.sleep(PACE - (now - self._last_start))
            now = self.clock()
        self._last_start = now


class DirFetcher:
    """Serves pages from a saved snapshot folder (manifest.json maps URL → file). No network."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        manifest = json.loads((self.folder / "manifest.json").read_text(encoding="utf-8"))
        self.files = {entry["url"]: entry["file"] for entry in manifest["pages"]}

    def get(self, url: str) -> tuple[str | None, list[Issue]]:
        if url not in self.files:
            return None, [Issue.error("FETCH_CONNECTION", f"not in saved snapshot {self.folder}", url)]
        return (self.folder / self.files[url]).read_text(encoding="utf-8"), []
