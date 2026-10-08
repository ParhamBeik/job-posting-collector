"""Command line: python -m collector <command>."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from collector import storage
from collector.core import collect, summary, utc_now
from collector.fetch import DirFetcher, HttpFetcher
from collector.sources import SOURCES

NOT_STARTED = 6  # exit code when another run is already in progress


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collector")
    parser.add_argument("--db", type=Path, default=storage.DEFAULT_DB, help="SQLite file (default: %(default)s)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="create the database file and tables (safe to repeat)")
    run = commands.add_parser("collect", help="collect today's and the previous six days' postings (Tehran)")
    run.add_argument("--source", choices=sorted(SOURCES), default="eng-estekhdam")
    run.add_argument("--run-id", type=int, help="use a run row created by the API's Collect now button")
    run.add_argument("--from-dir", type=Path, help="replay a saved snapshot folder instead of the live site")
    run.add_argument("--now", help="with --from-dir only: the moment the snapshot was taken (ISO 8601 with Z)")
    run.add_argument("--snapshots", type=Path, default=Path("var/snapshots"), help="where problem pages are saved")
    args = parser.parse_args(argv)

    conn = storage.connect(args.db)
    if args.command == "init-db":
        print(f"database ready: {args.db}")
        return 0

    if args.now and not args.from_dir:
        parser.error("--now is only for replaying a saved snapshot (--from-dir); a live run uses the real time")
    clock = utc_now
    if args.now:
        fixed = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        if fixed.tzinfo is None:
            parser.error("--now needs a time zone, e.g. 2026-10-07T17:00:00Z")
        clock = lambda: fixed  # noqa: E731
    fetcher = DirFetcher(args.from_dir) if args.from_dir else HttpFetcher()
    try:
        report = collect(conn, SOURCES[args.source], fetcher, clock, args.snapshots, args.run_id)
    except storage.RunActive as error:
        print(f"not started: {error}", file=sys.stderr)
        return NOT_STARTED
    print(summary(report))
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
