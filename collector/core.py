"""One collection run: window → listing pages → posting pages → checks → storage → status.

Everything is fetched and checked before anything is stored, so the circuit breaker can stop a
run that is producing bad data without writing any of it. Every problem becomes an issue with a
code (PLAN.md section 6); the run status says whether the window was fully covered.
"""

import json
import sqlite3
import traceback
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from collector import storage
from collector.dates import DayRange, collection_window, format_utc
from collector.models import Issue, ListingItem, Posting

PAGE_CAP = 40  # safety stop for pagination
CARDS_PER_PAGE = 10
BREAKER_MIN_RECORDS = 5
BREAKER_RATIO = 0.30  # more than 30% invalid records → stop the source, store nothing
BLOCKING_CODES = {"BLOCKED_CHALLENGE", "LOGIN_REQUIRED"}
EXIT_CODES = {
    "success": 0,
    "success_empty": 0,
    "success_with_warnings": 0,
    "partial": 1,
    "incomplete": 2,
    "blocked": 3,
    "parser_broken": 4,
    "failed": 5,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RunReport:
    run_id: int
    window: DayRange
    status: str = "running"
    pages_listing: int = 0
    pages_posting: int = 0
    found: int = 0  # postings in the window listed on the source
    results: Counter = field(default_factory=Counter)  # new / updated / unchanged
    rejected: int = 0
    issues: list[tuple[str, Issue]] = field(default_factory=list)  # (stage, issue)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.status]

    def codes(self) -> Counter:
        return Counter((issue.severity, issue.code) for _, issue in self.issues)


class _Run:
    def __init__(self, conn, source, fetcher, report: RunReport, snapshot_dir: Path, page_cap: int):
        self.conn, self.source, self.fetcher, self.report = conn, source, fetcher, report
        self.snapshot_dir, self.page_cap = snapshot_dir, page_cap
        self.saved: dict[str, str] = {}  # url → snapshot file

    # --- recording ------------------------------------------------------------------------

    def record(self, stage: str, issues: list[Issue], page_url: str | None = None, html: str | None = None, kind: str = "") -> None:
        path = self._snapshot(page_url, html, kind) if issues and html is not None else None
        for issue in issues:
            self.report.issues.append((stage, issue))
            storage.add_issue(self.conn, self.report.run_id, issue, stage, path)

    def _snapshot(self, url: str, html: str, kind: str) -> str:
        """Save a problem page so it can become a test fixture (repair flow)."""
        if url not in self.saved:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
            name = f"{len(self.saved) + 1:03d}-{kind}.html"
            (self.snapshot_dir / name).write_text(html, encoding="utf-8")
            self.saved[url] = name
            pages = [{"url": u, "kind": f.split("-", 1)[1][:-5], "file": f, "status": 200} for u, f in self.saved.items()]
            (self.snapshot_dir / "manifest.json").write_text(
                json.dumps({"pages": pages}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        return str(self.snapshot_dir / self.saved[url])

    def progress(self) -> None:
        storage.update_run(
            self.conn, self.report.run_id,
            pages_listing=self.report.pages_listing, pages_posting=self.report.pages_posting,
        )

    # --- phases ---------------------------------------------------------------------------

    def run(self) -> str:
        window = self.report.window
        candidates, covered, stop = self.read_listings(window)
        if stop:
            return stop
        postings, posting_errors, blocked = self.read_postings(candidates)
        card_errors = self.card_errors
        self.report.found = len(candidates)
        self.report.rejected = card_errors + len(candidates) - len(postings)
        self.health(postings)
        if blocked:
            return "blocked"
        total, invalid = len(candidates) + card_errors, card_errors + posting_errors
        if total >= BREAKER_MIN_RECORDS and invalid / total > BREAKER_RATIO:
            self.record("run", [Issue.error("BREAKER_TRIPPED", f"{invalid} of {total} records invalid; nothing stored")])
            return "parser_broken"
        self.store(postings)
        if not covered:
            return "incomplete"
        severities = {issue.severity for _, issue in self.report.issues}
        if "error" in severities:
            return "partial"
        if "warning" in severities:
            return "success_with_warnings"
        return "success" if candidates else "success_empty"

    def read_listings(self, window: DayRange) -> tuple[dict[str, ListingItem], bool, str | None]:
        """Walk listing pages until a card older than the window. Returns (candidates, covered, stop)."""
        candidates: dict[str, ListingItem] = {}
        self.cards_seen = self.card_errors = self.date_problems = 0
        previous = None
        for page in range(1, self.page_cap + 1):
            url = self.source.listing_url(page)
            html, issues = self.fetcher.get(url)
            self.record("fetch", issues)
            if html is None:
                return candidates, False, None
            self.report.pages_listing += 1
            self.progress()

            code = self.source.check_page(html, "listing")
            if code:
                self.record("page", [Issue.error(code, f"listing page {page} not recognized", url)], url, html, "listing")
                if code in BLOCKING_CODES:
                    return candidates, False, "blocked"
                if page == 1:  # the very first page is unreadable: the parser no longer fits the site
                    self.record("run", [Issue.error("BREAKER_TRIPPED", "first listing page unrecognized; nothing stored")])
                    return candidates, False, "parser_broken"
                return candidates, False, None

            items, issues = self.source.parse_listing(html)
            self.record("listing", issues, url, html, "listing")
            errors = sum(issue.severity == "error" for issue in issues)
            self.card_errors += errors
            self.cards_seen += len(items) + errors
            self.date_problems += sum(issue.code in {"FALLBACK_USED", "DATE_UNPARSEABLE", "DATE_MISMATCH"} for issue in issues)
            if not items and not errors:
                self.record("listing", [Issue.error("LISTING_EMPTY_EARLY", f"page {page} has no cards before the window ended", url)], url, html, "listing")
                return candidates, False, None

            reached_end = False
            for item in items:
                if previous and item.published_date > previous:
                    self.record("listing", [Issue.warning("LISTING_ORDER_BROKEN", f"page {page}: {item.published_date} after {previous}", url)])
                previous = item.published_date
                if item.published_date < window.first_day:
                    reached_end = True
                elif item.published_date <= window.last_day:
                    candidates.setdefault(item.source_post_id, item)  # an ad can shift onto the next page mid-run
            if reached_end:
                return candidates, True, None
            if len(items) + errors < CARDS_PER_PAGE:
                self.record("listing", [Issue.warning("LISTING_FEW_CARDS", f"page {page} has {len(items) + errors} cards", url)])
        self.record("listing", [Issue.error("PAGE_CAP_REACHED", f"window not finished after {self.page_cap} pages")])
        return candidates, False, None

    def read_postings(self, candidates: dict[str, ListingItem]) -> tuple[list[Posting], int, bool]:
        postings, invalid = [], 0
        for item in candidates.values():
            html, issues = self.fetcher.get(item.url)
            self.record("fetch", issues)
            if html is None:
                continue
            self.report.pages_posting += 1
            self.progress()
            code = self.source.check_page(html, "posting")
            if code:
                self.record("page", [Issue.error(code, f"post {item.source_post_id}: page not recognized", item.url)], item.url, html, "posting")
                if code in BLOCKING_CODES:
                    return postings, invalid, True  # stop asking a site that is refusing us
                invalid += 1
                continue
            posting, issues = self.source.parse_posting(html, item)
            self.record("posting", issues, item.url, html, "posting")
            if posting is None:
                invalid += 1
            else:
                postings.append(posting)
        return postings, invalid, False

    def store(self, postings: list[Posting]) -> None:
        for posting in postings:
            try:
                result, issues = storage.upsert_posting(self.conn, posting, utc_now())
            except sqlite3.Error as error:
                self.report.rejected += 1
                self.record("store", [Issue.error("DB_WRITE_FAILED", f"post {posting.source_post_id}: {error}", posting.url)])
                continue
            self.report.results[result] += 1
            self.record("store", issues)
        storage.update_run(
            self.conn, self.report.run_id,
            new=self.report.results["new"], updated=self.report.results["updated"],
            unchanged=self.report.results["unchanged"], rejected=self.report.rejected,
        )

    def health(self, postings: list[Posting]) -> None:
        """Numbers that drift when the source changes its HTML (PLAN.md section 8, detect)."""
        def pct(part, whole):
            return round(100 * part / whole, 1) if whole else None

        storage.update_run(
            self.conn, self.report.run_id,
            cards_per_page_avg=round(self.cards_seen / self.report.pages_listing, 2) if self.report.pages_listing else None,
            date_ok_pct=pct(self.cards_seen - self.date_problems, self.cards_seen),
            body_ok_pct=pct(len(postings), self.report.pages_posting),
            tags_ok_pct=pct(sum(bool(p.tags) for p in postings), len(postings)),
        )


def collect(conn, source, fetcher, clock=utc_now, snapshot_root: Path = Path("var/snapshots"),
            run_id: int | None = None, page_cap: int = PAGE_CAP) -> RunReport:
    """Run one collection. Raises storage.RunActive if another run is in progress."""
    started = clock()
    if run_id is None:
        run_id = storage.start_run(conn, source.name, started)
    report = RunReport(run_id, collection_window(started))  # "today" is decided once, here
    storage.update_run(
        conn, run_id,
        window_start=format_utc(report.window.start), window_end=format_utc(report.window.end),
        parser_version=source.parser_version,
    )
    run = _Run(conn, source, fetcher, report, snapshot_root / str(run_id), page_cap)
    try:
        report.status = run.run()
    except Exception:  # a bug must still end the run visibly
        run.record("run", [Issue.error("UNEXPECTED_ERROR", traceback.format_exc(limit=5))])
        report.status = "failed"
    storage.finish_run(conn, run_id, report.status, clock())
    return report


def summary(report: RunReport) -> str:
    window = report.window
    lines = [
        f"run {report.run_id}: {report.status.upper()}",
        f"window: {window.first_day} .. {window.last_day} Tehran = "
        f"{format_utc(window.start)} .. {format_utc(window.end)} (end excluded)",
        f"pages: {report.pages_listing} listing, {report.pages_posting} posting",
        f"postings in window: {report.found} found, {report.results['new']} new, "
        f"{report.results['updated']} updated, {report.results['unchanged']} unchanged, {report.rejected} rejected",
    ]
    codes = report.codes()
    if codes:
        lines.append("issues:")
        lines += [f"  {count:3d} × {severity:7} {code}" for (severity, code), count in sorted(codes.items())]
    else:
        lines.append("issues: none")
    return "\n".join(lines)
