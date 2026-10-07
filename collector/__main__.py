"""Command line: python -m collector <command>."""

import argparse
import sys
from pathlib import Path

from collector import storage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collector")
    parser.add_argument("--db", type=Path, default=storage.DEFAULT_DB, help="SQLite file (default: %(default)s)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="create the database file and tables (safe to repeat)")
    args = parser.parse_args(argv)

    if args.command == "init-db":
        storage.connect(args.db).close()
        print(f"database ready: {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
