"""Start the API: python -m api [--db var/jobs.db] [--host 127.0.0.1] [--port 8000]."""

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
    args = parser.parse_args()
    uvicorn.run(create_app(args.db, hosts=(*LOCAL_HOSTS, args.host)), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
