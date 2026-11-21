"""Temporal image-space LEFT_OF for one pair of supplied position histories."""
import argparse
import json
import math
import sys
from pathlib import Path

MAX_SAMPLES = 10_000
MAX_INPUT_BYTES = 1_048_576
MAX_LINE_BYTES = 16_384


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and value.isprintable() and len(value) <= 512


def _time(value, name):
    if type(value) is not int or not 0 <= value < 2**63:
        raise ValueError(f"{name} must be a nonnegative 64-bit integer")


def _options(video, subject_id, object_id, end_ms, max_age_ms, at_ms):
    if not all(_text(value) for value in (video, subject_id, object_id)):
        raise ValueError("recording and object IDs must be nonempty printable text up to 512 characters")
    if subject_id == object_id:
        raise ValueError("relation operands must be distinct")
    _time(end_ms, "end_ms")
    if at_ms is not None:
        _time(at_ms, "at_ms")
    if type(max_age_ms) is not int or not 1 <= max_age_ms <= 60000:
        raise ValueError("max_age_ms must be an integer from 1 to 60000")


def _sample(row):
    required = {"video", "object_id", "t_ms"}
    if not isinstance(row, dict) or set(row) not in (required, required | {"x", "y"}):
        raise ValueError("sample requires video, object_id, t_ms and optional paired x/y")
    if not _text(row["video"]) or not _text(row["object_id"]):
        raise ValueError("invalid recording/object ID")
    _time(row["t_ms"], "t_ms")
    if "x" in row:
        for key in ("x", "y"):
            value = row[key]
            if type(value) not in (int, float):
                raise ValueError("coordinates must be finite normalized numbers")
            try:
                valid = math.isfinite(value) and 0 <= value <= 1
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError("coordinates must be finite normalized numbers")
    return dict(row)


def left_of_intervals(samples, video, subject_id, object_id, *, end_ms,
                      max_age_ms=5000, at_ms=None):
    """Derive half-open intervals, clipped to an explicit exclusive horizon."""
    _options(video, subject_id, object_id, end_ms, max_age_ms, at_ms)
    changes = {}
    boundaries = {end_ms}
    seen = set()
    for index, raw in enumerate(samples):
        if index >= MAX_SAMPLES:
            raise ValueError("relation input exceeds 10000 samples")
        row = _sample(raw)
        key = (row["video"], row["object_id"], row["t_ms"])
        if key in seen:
            raise ValueError("duplicate recording/object/timestamp sample")
        seen.add(key)
        if row["video"] != video or row["object_id"] not in (subject_id, object_id) or row["t_ms"] >= end_ms:
            continue
        time = row["t_ms"]
        changes.setdefault(time, []).append(row)
        boundaries.add(time)
        if "x" in row:
            boundaries.add(min(end_ms, time + max_age_ms))
    times = sorted(boundaries)
    latest = {}
    intervals = []
    for time, next_time in zip(times, times[1:]):
        for row in changes.get(time, []):
            latest[row["object_id"]] = row
        a, b = latest.get(subject_id), latest.get(object_id)
        fresh = all(row is not None and "x" in row
                    and time - row["t_ms"] < max_age_ms for row in (a, b))
        if fresh and a["x"] < b["x"]:
            if intervals and intervals[-1]["end_ms"] == time:
                intervals[-1]["end_ms"] = next_time
            else:
                intervals.append({
                    "video": video, "subject_id": subject_id,
                    "predicate": "LEFT_OF", "object_id": object_id,
                    "start_ms": time, "end_ms": next_time,
                })
    if at_ms is not None:
        return [interval for interval in intervals
                if interval["start_ms"] <= at_ms < interval["end_ms"]]
    return intervals


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _samples(path):
    total = 0
    with Path(path).open("rb") as stream:
        while line := stream.readline(MAX_LINE_BYTES + 1):
            total += len(line)
            if total > MAX_INPUT_BYTES:
                raise ValueError("relation input exceeds 1 MiB")
            if len(line) > MAX_LINE_BYTES:
                raise ValueError("relation input line exceeds 16384 bytes")
            if not line.strip():
                continue
            try:
                yield json.loads(line.decode("utf-8"), object_pairs_hook=_unique_keys)
            except RecursionError as exc:
                raise ValueError("relation input nesting is too deep") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--video", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--object", dest="object_id", required=True)
    parser.add_argument("--end-ms", type=int, required=True)
    parser.add_argument("--max-age-ms", type=int, default=5000)
    parser.add_argument("--at-ms", type=int)
    args = parser.parse_args(argv)
    try:
        result = left_of_intervals(_samples(args.input), args.video, args.subject,
                                   args.object_id, end_ms=args.end_ms,
                                   max_age_ms=args.max_age_ms, at_ms=args.at_ms)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
