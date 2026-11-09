"""Command-line interface for SpatialMind's recording-scoped memory."""
import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from .store import (
    connect, history, ingest, last_seen, validate_event_options, zone_changes,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest_parser = sub.add_parser("ingest", help="atomically ingest JSONL observations")
    ingest_parser.add_argument("file", type=Path)
    for command, description in (
        ("last-seen", "retrieve an object's last observed position"),
        ("history", "retrieve an object's observations in timestamp order"),
        ("zone-changes", "retrieve observed zone differences for one object"),
    ):
        query = sub.add_parser(command, help=description)
        query.add_argument("object_id")
        query.add_argument("--video", help="source recording ID")
        if command == "zone-changes":
            query.add_argument("--confirm-observations", type=int, default=2,
                               help="consecutive target observations required (default: 2)")
            query.add_argument("--max-gap-ms", type=int, default=5000,
                               help="maximum adjacent observation gap in ms (default: 5000)")
    args = parser.parse_args(argv)
    try:
        event_options = {}
        if args.command == "zone-changes":
            validate_event_options(args.confirm_observations, args.max_gap_ms)
            event_options = dict(confirm_observations=args.confirm_observations,
                                 max_gap_ms=args.max_gap_ms)
        with closing(connect(args.db)) as db:
            if args.command == "ingest":
                with args.file.open("rb") as stream:
                    result = ingest(db, stream)
            else:
                lookup = {
                    "history": history,
                    "last-seen": last_seen,
                    "zone-changes": zone_changes,
                }[args.command]
                result = lookup(db, args.object_id, args.video, **event_options)
                if result is None or (args.command == "history" and not result):
                    print("no matching observation", file=sys.stderr)
                    return 1
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
