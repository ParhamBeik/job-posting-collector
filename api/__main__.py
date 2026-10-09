"""Start the API: python -m api [--db var/jobs.db] [--host 127.0.0.1] [--port 8000] [--allow-host NAME]."""

import argparse
from pathlib import Path

import uvicorn

from api.app import LOCAL_HOSTS, create_app
from collector import storage


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m api")
    parser.add_argument("--db", type=Path, default=storage.DEFAULT_DB)
    # Localhost only by default: there is no login, and Collect now starts a process.
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    # Extra host names the page may be opened under, e.g. a remote dev box or a cloud editor's
    # forwarded address. Every other name gets 400 (DNS rebinding protection).
    parser.add_argument("--allow-host", action="append", default=[], metavar="NAME")
    args = parser.parse_args()
    hosts = (*LOCAL_HOSTS, args.host, *args.allow_host)
    uvicorn.run(create_app(args.db, hosts=hosts), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
