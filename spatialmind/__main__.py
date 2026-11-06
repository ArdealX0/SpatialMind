"""Command-line interface for SpatialMind's recording-scoped memory."""
import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from .store import connect, history, ingest, last_seen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest_parser = sub.add_parser("ingest", help="atomically ingest JSONL observations")
    ingest_parser.add_argument("file", type=Path)
    for command, description in (
        ("last-seen", "retrieve an object's last observed position"),
        ("history", "retrieve an object's observations in timestamp order"),
    ):
        query = sub.add_parser(command, help=description)
        query.add_argument("object_id")
        query.add_argument("--video", help="source recording ID")
    args = parser.parse_args(argv)
    try:
        with closing(connect(args.db)) as db:
            if args.command == "ingest":
                with args.file.open("rb") as stream:
                    result = ingest(db, stream)
            else:
                lookup = history if args.command == "history" else last_seen
                result = lookup(db, args.object_id, args.video)
                if not result:
                    print("no matching observation", file=sys.stderr)
                    return 1
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
