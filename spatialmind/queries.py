"""Compile two controlled-language requests into fixed read-only operations."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import sys

from .store import last_seen, validate_event_interval, zone_changes

MAX_PROMPT_CHARS = 2048
QUOTED = r'("(?:[^"\\]|\\.)*")'
LAST_SEEN = re.compile(r"Where was " + QUOTED + r" last seen[?.]?", re.IGNORECASE)
CHANGES = re.compile(r"Show zone changes for " + QUOTED
                     + r"(?: between ([0-9]+) and ([0-9]+) ms)?[?.]?", re.IGNORECASE)


def _identifier(value):
    if (not isinstance(value, str) or not value.strip()
            or not value.isprintable() or len(value) > 512):
        raise ValueError("identifiers must be nonempty printable strings of at most 512 characters")
    return value


def compile_request(prompt, video):
    """Return an allowlisted operation, or None for unsupported wording."""
    _identifier(video)
    if (not isinstance(prompt, str) or not prompt.strip()
            or len(prompt) > MAX_PROMPT_CHARS or not prompt.isprintable()):
        raise ValueError("prompt must be nonempty printable text of at most 2048 characters")
    text = prompt.strip()
    match = LAST_SEEN.fullmatch(text)
    if match is not None:
        return {"operation": "last_seen",
                "parameters": {"video": video, "object_id": _identifier(json.loads(match[1]))}}
    match = CHANGES.fullmatch(text)
    if match is not None:
        parameters = {"video": video, "object_id": _identifier(json.loads(match[1]))}
        if match[2] is not None:
            start_ms, end_ms = int(match[2]), int(match[3])
            validate_event_interval(start_ms, end_ms)
            parameters.update(start_ms=start_ms, end_ms=end_ms)
        return {"operation": "zone_changes", "parameters": parameters}
    return None


def _execute(db, compiled):
    # Only compiler-produced operations reach these fixed call sites.
    if compiled["operation"] == "last_seen":
        evidence = last_seen(db, **compiled["parameters"])
    elif compiled["operation"] == "zone_changes":
        evidence = zone_changes(db, **compiled["parameters"])
    else:
        raise ValueError("unsupported operation")
    return {"status": "evidence_missing" if evidence is None else "answered",
            "query": compiled, "evidence": evidence}


def answer(db, prompt, video):
    """Answer using an existing connection; unsupported requests never access it."""
    compiled = compile_request(prompt, video)
    if compiled is None:
        return {"status": "unsupported", "reason": "unsupported_pattern"}
    return _execute(db, compiled)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--video", required=True)
    parser.add_argument("prompt")
    args = parser.parse_args(argv)
    try:
        compiled = compile_request(args.prompt, args.video)
        if compiled is None:
            result = {"status": "unsupported", "reason": "unsupported_pattern"}
        else:
            # as_uri escapes path punctuation before SQLite's read-only option.
            uri = args.db.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as db:
                db.row_factory = sqlite3.Row
                result = _execute(db, compiled)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
