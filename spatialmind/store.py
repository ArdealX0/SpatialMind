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
            label TEXT NOT NULL, zone TEXT NOT NULL, tracklet_id TEXT,
            PRIMARY KEY (video, object_id, t_ms)
        ) WITHOUT ROWID
    """)
    columns = {row["name"] for row in db.execute("PRAGMA table_info(observations)")}
    if "tracklet_id" not in columns:
        db.execute("ALTER TABLE observations ADD COLUMN tracklet_id TEXT")
    db.execute("""
        CREATE TABLE IF NOT EXISTS tracklet_links (
            video TEXT NOT NULL, tracklet_id TEXT NOT NULL, object_id TEXT NOT NULL,
            PRIMARY KEY (video, tracklet_id)
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
    if not isinstance(row, dict) or set(row) not in (set(FIELDS), set(FIELDS) | {"tracklet_id"}):
        raise ValueError("expected video, object_id, t_ms, label, zone and optional tracklet_id")
    text_fields = ("video", "object_id", "label", "zone")
    if "tracklet_id" in row:
        text_fields += ("tracklet_id",)
    for key in text_fields:
        value = row[key]
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ValueError(f"{key} must be nonempty text of at most 512 characters")
        if not value.isprintable():
            raise ValueError(f"{key} contains invalid characters")
    if type(row["t_ms"]) is not int or not 0 <= row["t_ms"] < 2**63:
        raise ValueError("t_ms must be a nonnegative 64-bit integer")
    return tuple(row[key] for key in FIELDS) + (row.get("tracklet_id"),)


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
            if values[5] is not None:
                db.execute("""
                    INSERT INTO tracklet_links (video, tracklet_id, object_id)
                    VALUES (?, ?, ?) ON CONFLICT(video, tracklet_id) DO NOTHING
                """, (values[0], values[5], values[1]))
                linked = db.execute("""
                    SELECT object_id FROM tracklet_links WHERE video=? AND tracklet_id=?
                """, (values[0], values[5])).fetchone()
                if linked["object_id"] != values[1]:
                    raise ValueError(f"line {line_no}: tracklet already belongs to another object")
            cursor = db.execute("""
                INSERT INTO observations (video, object_id, t_ms, label, zone, tracklet_id)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(video, object_id, t_ms) DO NOTHING
            """, values)
            if cursor.rowcount:
                inserted += 1
            else:
                existing = db.execute("""
                    SELECT label, zone, tracklet_id FROM observations
                    WHERE video=? AND object_id=? AND t_ms=?
                """, values[:3]).fetchone()
                if tuple(existing) != values[3:]:
                    raise ValueError(f"line {line_no}: conflicting observation at same timestamp")
                unchanged += 1
    return {"inserted": inserted, "unchanged": unchanged}


def _resolve_video(db, object_id, video):
    """Resolve an unambiguous recording without comparing recording-relative times."""
    if video is None:
        candidates = db.execute("""
            SELECT DISTINCT video FROM observations WHERE object_id=? LIMIT 2
        """, (object_id,)).fetchall()
        if not candidates:
            return None
        if len(candidates) > 1:
            raise ValueError("object ID occurs in multiple recordings; specify --video")
        video = candidates[0]["video"]
    return video


def _observation_result(row):
    result = dict(row)
    if result["tracklet_id"] is None:
        del result["tracklet_id"]
    return result


def last_seen(db, object_id, video=None):
    """Return the latest supported observation within one recording, or None."""
    video = _resolve_video(db, object_id, video)
    if video is None:
        return None
    row = db.execute("""
        SELECT video, object_id, t_ms, label, zone, tracklet_id FROM observations
        WHERE video=? AND object_id=? ORDER BY t_ms DESC LIMIT 1
    """, (video, object_id)).fetchone()
    return _observation_result(row) if row is not None else None


def history(db, object_id, video=None):
    """Return all observations in ascending timestamp order within one recording."""
    video = _resolve_video(db, object_id, video)
    if video is None:
        return []
    rows = db.execute("""
        SELECT video, object_id, t_ms, label, zone, tracklet_id FROM observations
        WHERE video=? AND object_id=? ORDER BY t_ms ASC
    """, (video, object_id))
    return [_observation_result(row) for row in rows]


def validate_event_options(confirm_observations, max_gap_ms):
    """Reject invalid debounce settings before loading observations."""
    for name, value in (
        ("confirm_observations", confirm_observations),
        ("max_gap_ms", max_gap_ms),
    ):
        if type(value) is not int or not 1 <= value < 2**63:
            raise ValueError(f"{name} must be a positive 64-bit integer")


def validate_event_interval(start_ms, end_ms):
    """Validate optional inclusive bounds on an event's confirmation timestamp."""
    for name, value in (("start_ms", start_ms), ("end_ms", end_ms)):
        if value is not None and (type(value) is not int or not 0 <= value < 2**63):
            raise ValueError(f"{name} must be a nonnegative 64-bit integer")
    if start_ms is not None and end_ms is not None and start_ms > end_ms:
        raise ValueError("start_ms must be less than or equal to end_ms")


def zone_changes(db, object_id, video=None, *, confirm_observations=2, max_gap_ms=5000,
                 start_ms=None, end_ms=None):
    """Derive confirmed zone differences; unknown locations and long gaps reset."""
    validate_event_options(confirm_observations, max_gap_ms)
    validate_event_interval(start_ms, end_ms)
    observations = history(db, object_id, video)
    if not observations:
        return None
    events = []
    baseline = candidate = None
    candidate_count = 0
    previous_time = None
    for current in observations:
        if previous_time is not None and current["t_ms"] - previous_time > max_gap_ms:
            baseline = candidate = None
            candidate_count = 0
        previous_time = current["t_ms"]
        if current["zone"] == "unknown":
            baseline = candidate = None
            candidate_count = 0
            continue
        if baseline is None or current["zone"] == baseline["zone"]:
            baseline = current
            candidate = None
            candidate_count = 0
            continue
        if candidate is None or candidate["zone"] != current["zone"]:
            candidate = current
            candidate_count = 1
        else:
            candidate_count += 1
        if candidate_count >= confirm_observations:
            events.append({
                "type": "ZONE_CHANGED",
                "video": current["video"],
                "object_id": current["object_id"],
                "from_zone": baseline["zone"],
                "to_zone": current["zone"],
                "before_t_ms": baseline["t_ms"],
                "after_t_ms": candidate["t_ms"],
                "confirmed_t_ms": current["t_ms"],
            })
            baseline = current
            candidate = None
            candidate_count = 0
    return [
        event for event in events
        if (start_ms is None or event["confirmed_t_ms"] >= start_ms)
        and (end_ms is None or event["confirmed_t_ms"] <= end_ms)
    ]
