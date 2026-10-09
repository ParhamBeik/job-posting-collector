"""HTTP API over the stored postings and runs (PLAN.md sections 9-11).

Read-only except POST /api/runs, which starts the same collect command as the terminal in a
separate process. Every response carries a strict Content-Security-Policy.
"""

import re
import subprocess
import sys
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

import jdatetime
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from collector import storage
from collector.core import utc_now
from collector.dates import TEHRAN, collection_window, format_utc, tehran_midnight_utc
from collector.models import Issue
from collector.industry import GROUPS, primary_group
from collector.normalize import normalize
from collector.sources import SOURCES

CSP = "default-src 'self'"
# FastAPI's own docs pages (/docs Swagger, /redoc ReDoc) load their code from a CDN and run inline
# scripts. They show only our API schema, never scraped HTML, so they get a looser policy.
DOC_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc"}
DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: https:; worker-src 'self' blob:"
)
# The site gives only a day, so within one day the site's post ID (assigned in creation order,
# so nearly the site's own listing order) decides; our row id only breaks remaining ties.
NEWEST_FIRST = "p.published_at DESC, CAST(p.source_post_id AS INTEGER) DESC, p.id DESC"
SNIPPET = 160  # characters of body shown in a result row
TOP_TAGS = 10
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
YEARS = range(1900, 2101)  # far from date.min/max, so the UTC conversion cannot overflow
MAX_ID = 2**63 - 1  # SQLite's largest integer; a bigger number would be a 500, not a 422
MAX_PAGE = 10**9  # keeps the row offset far inside SQLite's integer range
# Host names the page may be opened under. Checking the Host header stops DNS rebinding: a
# hostile site that points its own name at 127.0.0.1 would otherwise count as same-origin and
# could send the X-Collect-Trigger header.
LOCAL_HOSTS = ("127.0.0.1", "localhost")
LOG_DIR = Path("var/logs")
STATIC = Path(__file__).parent / "static"


def launch_collector(db: Path, run_id: int) -> None:
    """Run the collect command for an existing run row, detached from the API process."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / f"run-{run_id}.log", "ab") as log:
        subprocess.Popen(
            [sys.executable, "-m", "collector", "--db", str(db), "collect", "--run-id", str(run_id)],
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True,
        )


def tehran_day(published_at: str) -> date:
    return datetime.fromisoformat(published_at.replace("Z", "+00:00")).astimezone(TEHRAN).date()


def jalali(day: date) -> str:
    return jdatetime.date.fromgregorian(date=day).strftime("%Y-%m-%d")


def parse_day(name: str, value: str | None) -> date | None:
    if value is None or value == "":
        return None
    try:
        if not _DAY.match(value):
            raise ValueError
        day = date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, f"{name} must be a real date written YYYY-MM-DD (Tehran day), got {value!r}")
    if day.year not in YEARS:
        raise HTTPException(422, f"{name} must be between {YEARS.start} and {YEARS.stop - 1}, got {value!r}")
    return day


def like_pattern(text: str) -> str:
    """Substring pattern for LIKE ... ESCAPE '\\': the user's % and _ are literal characters."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def snippet(body: str, query: str) -> str:
    """Start of the body, or the part around the first match of the (normalized) keyword."""
    text = " ".join(body.split())
    start = normalize(text).find(query) if query else -1  # positions match closely enough for a preview
    start = max(0, start - SNIPPET // 4) if start > 0 else 0
    part = text[start:start + SNIPPET]
    return ("…" if start else "") + part + ("…" if start + SNIPPET < len(text) else "")


def create_app(db: Path | str = storage.DEFAULT_DB, launch=launch_collector, clock=utc_now,
               hosts=LOCAL_HOSTS) -> FastAPI:
    app = FastAPI(title="Job posting collector")  # docs at /docs (Swagger) and /redoc
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(hosts))  # any other Host → 400

    def connect():
        conn = storage.connect(db)
        conn.create_function("normalize", 1, normalize, deterministic=True)
        return closing(conn)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = DOCS_CSP if request.url.path in DOC_PATHS else CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-cache"  # always revalidate: an updated page or data is never stale
        return response

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    def tags_of(conn, ids: list[int]) -> dict[int, list[dict]]:
        found: dict[int, list[dict]] = {i: [] for i in ids}
        if ids:
            rows = conn.execute(
                f"SELECT posting_id, kind, slug, label FROM posting_tags WHERE posting_id IN ({','.join('?' * len(ids))})"
                " ORDER BY kind DESC, slug", ids,
            )
            for r in rows:
                found[r["posting_id"]].append({"kind": r["kind"], "slug": r["slug"], "label": r["label"]})
        return found

    def posting_json(row, tags: list[dict]) -> dict:
        day = tehran_day(row["published_at"])
        return {
            "id": row["id"],
            "source": row["source"],
            "source_post_id": row["source_post_id"],
            "url": row["url"],
            "title": row["title"],
            "published_at": row["published_at"],
            "published_date_tehran": day.isoformat(),
            "published_date_jalali": jalali(day),
            "collected_at": row["collected_at"],
            "updated_at": row["updated_at"],
            "members_only_omitted": bool(row["members_only_omitted"]),
            "tags": tags,
        }

    @app.get("/api/postings", tags=["postings"])
    def search(
        date_from: str | None = Query(None, description="First Tehran day, YYYY-MM-DD, included", examples=["2026-10-02"]),
        date_to: str | None = Query(None, description="Last Tehran day, YYYY-MM-DD, included", examples=["2026-10-08"]),
        q: str | None = Query(None, description="Keyword: one phrase, matched in title or body; any case, "
                              "Persian/Arabic letter and digit variants match", examples=["autocad"]),
        tag: str | None = Query(None, description="One tag, by slug (civil) or Persian label (عمران)", examples=["civil"]),
        page: int = Query(1, ge=1, le=MAX_PAGE),
        page_size: int = Query(20, ge=1, le=100),
    ):
        """Search postings. Filters combine with AND; newest first; timestamps are UTC with Z."""
        first, last = parse_day("date_from", date_from), parse_day("date_to", date_to)
        if first and last and first > last:
            raise HTTPException(422, f"date_from {first} is after date_to {last}")
        where, args = [], []
        if first:
            where.append("p.published_at >= ?")
            args.append(format_utc(tehran_midnight_utc(first)))
        if last:
            where.append("p.published_at < ?")
            args.append(format_utc(tehran_midnight_utc(last + timedelta(days=1))))
        query = normalize(q or "")
        if query:
            where.append("p.search_text LIKE ? ESCAPE '\\'")
            args.append(like_pattern(query))
        wanted_tag = normalize(tag or "")
        if wanted_tag:
            where.append(
                "EXISTS (SELECT 1 FROM posting_tags t WHERE t.posting_id = p.id"
                " AND (t.slug = ? OR normalize(coalesce(t.label, '')) = ?))"
            )
            args += [wanted_tag, wanted_tag]
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        with connect() as conn:
            total = conn.execute(f"SELECT count(*) FROM postings p{clause}", args).fetchone()[0]
            rows = conn.execute(
                f"SELECT p.* FROM postings p{clause} ORDER BY {NEWEST_FIRST} LIMIT ? OFFSET ?",
                [*args, page_size, (page - 1) * page_size],
            ).fetchall()
            tags = tags_of(conn, [r["id"] for r in rows])
        items = [posting_json(r, tags[r["id"]]) | {"snippet": snippet(r["body"], query)} for r in rows]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    @app.get("/api/postings/{posting_id}", tags=["postings"])
    def posting(posting_id: int = PathParam(ge=0, le=MAX_ID)):
        """One posting with its full text, original URL, tags and collected/updated/last-seen times."""
        with connect() as conn:
            row = conn.execute("SELECT * FROM postings WHERE id = ?", (posting_id,)).fetchone()
            if row is None:
                raise HTTPException(404, f"no posting {posting_id}")
            return posting_json(row, tags_of(conn, [posting_id])[posting_id]) | {
                "body": row["body"], "last_seen_at": row["last_seen_at"], "parser_version": row["parser_version"],
            }

    @app.get("/api/tags", tags=["postings"])
    def tags():
        """Every stored tag with its kind (province or field), Persian label and number of postings."""
        with connect() as conn:
            rows = conn.execute(
                "SELECT kind, slug, max(label) AS label, count(*) AS count FROM posting_tags"
                " GROUP BY kind, slug ORDER BY count DESC, kind, slug"
            ).fetchall()
        return {"items": [dict(r) for r in rows]}

    @app.get("/api/stats", tags=["postings"])
    def stats():
        """Postings per Tehran day of the current 7-day window, split by industry group, and the top tags."""
        window = collection_window(clock())
        start, end = format_utc(window.start), format_utc(window.end)
        with connect() as conn:
            ads = conn.execute(
                "SELECT p.source, p.published_at, group_concat(t.slug) AS fields FROM postings p"
                " LEFT JOIN posting_tags t ON t.posting_id = p.id AND t.kind = 'field'"
                " WHERE p.published_at >= ? AND p.published_at < ? GROUP BY p.id", (start, end),
            ).fetchall()
            top = conn.execute(
                "SELECT t.kind, t.slug, max(t.label) AS label, count(*) AS count FROM posting_tags t"
                " JOIN postings p ON p.id = t.posting_id WHERE p.published_at >= ? AND p.published_at < ?"
                " GROUP BY t.kind, t.slug ORDER BY count DESC, t.kind, t.slug LIMIT ?", (start, end, TOP_TAGS),
            ).fetchall()
            total = conn.execute("SELECT count(*) FROM postings").fetchone()[0]
        days = [window.first_day + timedelta(days=i) for i in range((window.last_day - window.first_day).days + 1)]
        per_day = {d: {key: 0 for key, _, _ in GROUPS} for d in days}
        for ad in ads:
            mapping = getattr(SOURCES.get(ad["source"]), "field_groups", {})
            per_day[tehran_day(ad["published_at"])][primary_group((ad["fields"] or "").split(","), mapping)] += 1
        return {
            "window": {"first_day": window.first_day.isoformat(), "last_day": window.last_day.isoformat(),
                       "start": start, "end": end},
            "groups": [{"key": key, "label": label, "label_fa": label_fa} for key, label, label_fa in GROUPS],
            "days": [{"date": d.isoformat(), "jalali": jalali(d), "count": sum(per_day[d].values()),
                      "groups": per_day[d]} for d in days],
            "top_tags": [dict(r) for r in top],
            "total_postings": total,
        }

    def run_json(conn, row) -> dict:
        counts = dict(conn.execute(
            "SELECT severity, count(*) FROM run_issues WHERE run_id = ? GROUP BY severity", (row["id"],)
        ).fetchall())
        return dict(row) | {"errors": counts.get("error", 0), "warnings": counts.get("warning", 0)}

    @app.get("/api/runs", tags=["runs"])
    def runs(limit: int = Query(20, ge=1, le=100)):
        """Collection runs, newest first: status, window, counts, health numbers, errors and warnings."""
        with connect() as conn:
            storage.expire_stale_runs(conn, clock())  # a crashed run must not look "running" forever
            rows = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return {"items": [run_json(conn, r) for r in rows]}

    @app.get("/api/runs/{run_id}", tags=["runs"])
    def run(run_id: int = PathParam(ge=0, le=MAX_ID)):
        """One run with every issue, grouped by code, with the page URLs involved."""
        with connect() as conn:
            storage.expire_stale_runs(conn, clock())
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise HTTPException(404, f"no run {run_id}")
            groups: dict[tuple[str, str], list[dict]] = {}
            for i in conn.execute(
                "SELECT severity, stage, code, url, detail, snapshot_path FROM run_issues WHERE run_id = ? ORDER BY id",
                (run_id,),
            ):
                groups.setdefault((i["severity"], i["code"]), []).append(
                    {"stage": i["stage"], "url": i["url"], "detail": i["detail"], "snapshot_path": i["snapshot_path"]}
                )
            issues = [
                {"severity": s, "code": c, "count": len(items), "items": items}
                for (s, c), items in sorted(groups.items(), key=lambda g: (g[0][0] != "error", -len(g[1]), g[0][1]))
            ]
            return run_json(conn, row) | {"issues": issues}

    @app.post("/api/runs", status_code=202, tags=["runs"])
    def collect_now(x_collect_trigger: str | None = Header(None, description="Must be 1")):
        """Collect now: start a collection run (202), or 409 if one is running, or 403 without the header."""
        # A custom header cannot be added by another website's form or link (CORS is never enabled),
        # so a page open in the same browser cannot start runs behind the user's back.
        if x_collect_trigger != "1":
            raise HTTPException(403, "missing header X-Collect-Trigger: 1")
        source = next(iter(SOURCES))
        with connect() as conn:
            try:
                run_id = storage.start_run(conn, source, clock())  # same lock as the command line
            except storage.RunActive:
                active = conn.execute("SELECT id FROM runs WHERE status = 'running' ORDER BY id DESC").fetchone()
                return JSONResponse({"detail": "a collection run is already in progress",
                                     "run_id": active["id"] if active else None}, status_code=409)
            try:
                launch(Path(db), run_id)
            except OSError as error:
                storage.add_issue(conn, run_id, Issue.error("UNEXPECTED_ERROR", f"could not start: {error}"), "run")
                storage.finish_run(conn, run_id, "failed", clock())
                raise HTTPException(500, "could not start the collector process")
        return {"run_id": run_id, "status": "running"}

    return app
