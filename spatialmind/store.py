"""Persistence for observed objects. Time is relative to the source recording."""
import json
import sqlite3

FIELDS = ("video", "object_id", "t_ms", "label", "zone")
MAX_LINE_BYTES = 16_384


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS observations (
            video TEXT NOT NULL, object_id TEXT NOT NULL,
            t_ms INTEGER NOT NULL CHECK(t_ms >= 0),
            label TEXT NOT NULL, zone TEXT NOT NULL,
            PRIMARY KEY (video, object_id, t_ms)
        ) WITHOUT ROWID
    """)
    return db


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _parse(line):
    row = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_keys)
    if not isinstance(row, dict) or set(row) != set(FIELDS):
        raise ValueError("expected exactly video, object_id, t_ms, label and zone")
    for key in ("video", "object_id", "label", "zone"):
        value = row[key]
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ValueError(f"{key} must be nonempty text of at most 512 characters")
        if not value.isprintable():
            raise ValueError(f"{key} contains invalid characters")
    if type(row["t_ms"]) is not int or not 0 <= row["t_ms"] < 2**63:
        raise ValueError("t_ms must be a nonnegative 64-bit integer")
    return tuple(row[key] for key in FIELDS)


def ingest(db, stream):
    """Atomically import validated records from a binary JSONL stream."""
    inserted = unchanged = line_no = 0
    with db:
        while line := stream.readline(MAX_LINE_BYTES + 1):
            line_no += 1
            if len(line) > MAX_LINE_BYTES:
                raise ValueError(f"line {line_no}: record exceeds size limit")
            if not line.strip():
                continue
            try:
                values = _parse(line)
            except (ValueError, RecursionError) as exc:
                raise ValueError(f"line {line_no}: {exc}") from exc
            cursor = db.execute("""
                INSERT INTO observations (video, object_id, t_ms, label, zone)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT(video, object_id, t_ms) DO NOTHING
            """, values)
            if cursor.rowcount:
                inserted += 1
            else:
                existing = db.execute("""
                    SELECT label, zone FROM observations
                    WHERE video=? AND object_id=? AND t_ms=?
                """, values[:3]).fetchone()
                if tuple(existing) != values[3:]:
                    raise ValueError(f"line {line_no}: conflicting observation at same timestamp")
                unchanged += 1
    return {"inserted": inserted, "unchanged": unchanged}


def last_seen(db, object_id, video=None):
    """Return the latest supported observation within one recording, or None."""
    if video is None:
        candidates = db.execute("""
            SELECT DISTINCT video FROM observations WHERE object_id=? LIMIT 2
        """, (object_id,)).fetchall()
        if not candidates:
            return None
        if len(candidates) > 1:
            raise ValueError("object ID occurs in multiple recordings; specify --video")
        video = candidates[0]["video"]
    row = db.execute("""
        SELECT video, object_id, t_ms, label, zone FROM observations
        WHERE video=? AND object_id=? ORDER BY t_ms DESC LIMIT 1
    """, (video, object_id)).fetchone()
    return dict(row) if row is not None else None
