"""HTTP API over the stored postings and runs (PLAN.md sections 9-11).

Read-only except POST /api/runs, which starts the same collect command as the terminal in a
separate process. Every response carries a strict Content-Security-Policy.
"""

import base64
import hashlib
import re
import subprocess
import sys
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

import jdatetime
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from collector import storage
from collector.core import utc_now
from collector.dates import TEHRAN, collection_window, format_utc, tehran_midnight_utc
from collector.models import Issue
from collector.normalize import normalize
from collector.sources import SOURCES

CSP = "default-src 'self'"
CDN = "https://cdn.jsdelivr.net"  # where FastAPI's Swagger page loads its script and style
SNIPPET = 160  # characters of body shown in a result row
TOP_TAGS = 10
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
YEARS = range(1900, 2101)  # far from date.min/max, so the UTC conversion cannot overflow
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


def create_app(db: Path | str = storage.DEFAULT_DB, launch=launch_collector, clock=utc_now) -> FastAPI:
    # /docs is served below with its own, narrower exception to the CSP; ReDoc is not needed.
    app = FastAPI(title="Job posting collector", docs_url=None, redoc_url=None)

    def connect():
        conn = storage.connect(db)
        conn.create_function("normalize", 1, normalize, deterministic=True)
        return closing(conn)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP)  # /docs sets its own
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/docs", include_in_schema=False)
    def docs():
        """Swagger UI. The one exception to the strict CSP: this page shows only our own API
        schema (never scraped HTML), loads Swagger from the CDN, and may run exactly one inline
        script, the startup script below, allowed by its hash rather than 'unsafe-inline'."""
        page = get_swagger_ui_html(openapi_url=app.openapi_url, title=f"{app.title} - API docs")
        startup = re.search(r"<script>(.*?)</script>", page.body.decode(), re.S).group(1)
        digest = base64.b64encode(hashlib.sha256(startup.encode()).digest()).decode()
        page.headers["Content-Security-Policy"] = (
            f"default-src 'self'; script-src {CDN} 'sha256-{digest}'; style-src {CDN}; "
            "img-src 'self' data: https://fastapi.tiangolo.com"
        )
        return page

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

    @app.get("/api/postings")
    def search(
        date_from: str | None = None,
        date_to: str | None = None,
        q: str | None = None,
        tag: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
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
                f"SELECT p.* FROM postings p{clause} ORDER BY p.published_at DESC, p.id DESC LIMIT ? OFFSET ?",
                [*args, page_size, (page - 1) * page_size],
            ).fetchall()
            tags = tags_of(conn, [r["id"] for r in rows])
        items = [posting_json(r, tags[r["id"]]) | {"snippet": snippet(r["body"], query)} for r in rows]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    @app.get("/api/postings/{posting_id}")
    def posting(posting_id: int):
        with connect() as conn:
            row = conn.execute("SELECT * FROM postings WHERE id = ?", (posting_id,)).fetchone()
            if row is None:
                raise HTTPException(404, f"no posting {posting_id}")
            return posting_json(row, tags_of(conn, [posting_id])[posting_id]) | {
                "body": row["body"], "last_seen_at": row["last_seen_at"], "parser_version": row["parser_version"],
            }

    @app.get("/api/tags")
    def tags():
        with connect() as conn:
            rows = conn.execute(
                "SELECT kind, slug, max(label) AS label, count(*) AS count FROM posting_tags"
                " GROUP BY kind, slug ORDER BY count DESC, kind, slug"
            ).fetchall()
        return {"items": [dict(r) for r in rows]}

    @app.get("/api/stats")
    def stats():
        window = collection_window(clock())
        start, end = format_utc(window.start), format_utc(window.end)
        with connect() as conn:
            per_instant = dict(conn.execute(
                "SELECT published_at, count(*) FROM postings WHERE published_at >= ? AND published_at < ?"
                " GROUP BY published_at", (start, end),
            ).fetchall())
            top = conn.execute(
                "SELECT t.kind, t.slug, max(t.label) AS label, count(*) AS count FROM posting_tags t"
                " JOIN postings p ON p.id = t.posting_id WHERE p.published_at >= ? AND p.published_at < ?"
                " GROUP BY t.kind, t.slug ORDER BY count DESC, t.kind, t.slug LIMIT ?", (start, end, TOP_TAGS),
            ).fetchall()
            total = conn.execute("SELECT count(*) FROM postings").fetchone()[0]
        per_day: dict[date, int] = {}
        for instant, n in per_instant.items():
            per_day[tehran_day(instant)] = per_day.get(tehran_day(instant), 0) + n
        days = [window.first_day + timedelta(days=i) for i in range((window.last_day - window.first_day).days + 1)]
        return {
            "window": {"first_day": window.first_day.isoformat(), "last_day": window.last_day.isoformat(),
                       "start": start, "end": end},
            "days": [{"date": d.isoformat(), "jalali": jalali(d), "count": per_day.get(d, 0)} for d in days],
            "top_tags": [dict(r) for r in top],
            "total_postings": total,
        }

    def run_json(conn, row) -> dict:
        counts = dict(conn.execute(
            "SELECT severity, count(*) FROM run_issues WHERE run_id = ? GROUP BY severity", (row["id"],)
        ).fetchall())
        return dict(row) | {"errors": counts.get("error", 0), "warnings": counts.get("warning", 0)}

    @app.get("/api/runs")
    def runs(limit: int = Query(20, ge=1, le=100)):
        with connect() as conn:
            storage.expire_stale_runs(conn, clock())  # a crashed run must not look "running" forever
            rows = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return {"items": [run_json(conn, r) for r in rows]}

    @app.get("/api/runs/{run_id}")
    def run(run_id: int):
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

    @app.post("/api/runs", status_code=202)
    def collect_now(x_collect_trigger: str | None = Header(None)):
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
