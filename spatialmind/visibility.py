"""Derive visibility transitions only from explicit, supplied state samples."""
import argparse
import json
import sys
from pathlib import Path

MAX_LINE_BYTES = 16_384
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_SAMPLES = 10_000
REQUIRED = {"video", "object_id", "state", "t_ms"}


def _validate_sample(sample):
    if not isinstance(sample, dict) or set(sample) not in (REQUIRED, REQUIRED | {"tracklet_id"}):
        raise ValueError("expected video, object_id, state, t_ms and optional tracklet_id")
    for key in ("video", "object_id", "state", "tracklet_id"):
        if key in sample:
            value = sample[key]
            if (not isinstance(value, str) or not value.strip()
                    or not value.isprintable() or len(value) > 512):
                raise ValueError(f"{key} must be nonempty printable text of at most 512 characters")
    if sample["state"] not in ("visible", "missing"):
        raise ValueError("state must be visible or missing")
    if type(sample["t_ms"]) is not int or not 0 <= sample["t_ms"] < 2**63:
        raise ValueError("t_ms must be a nonnegative 64-bit integer")
    return dict(sample)


def visibility_events(samples):
    """Return scoped transitions without guessing identity, missingness or motion."""
    previous = {}
    events = []
    for index, raw in enumerate(samples):
        if index >= MAX_SAMPLES:
            raise ValueError("visibility input exceeds 10000 samples")
        current = _validate_sample(raw)
        key = (current["video"], current["object_id"])
        before = previous.get(key)
        if before is None:
            if current["state"] != "visible":
                raise ValueError("first state for each recording/object must be visible")
        else:
            if current["t_ms"] <= before["t_ms"]:
                raise ValueError("timestamps must strictly increase within each recording/object")
            if current["state"] != before["state"]:
                events.append({
                    "type": "MISSING" if current["state"] == "missing" else "REOBSERVED",
                    "video": current["video"],
                    "object_id": current["object_id"],
                    "before": before,
                    "after": current,
                })
        previous[key] = current
    return events


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _samples(path):
    total = 0
    with Path(path).open("rb") as source:
        line_number = 0
        while line := source.readline(MAX_LINE_BYTES + 1):
            line_number += 1
            total += len(line)
            if total > MAX_INPUT_BYTES:
                raise ValueError("visibility input exceeds 64 MiB")
            if len(line) > MAX_LINE_BYTES:
                raise ValueError(f"line {line_number}: record exceeds size limit")
            if not line.strip():
                continue
            try:
                yield json.loads(line.decode("utf-8"), object_pairs_hook=_unique_keys)
            except (ValueError, RecursionError) as exc:
                raise ValueError(f"line {line_number}: invalid JSON sample") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="local explicit visibility JSONL samples")
    args = parser.parse_args(argv)
    try:
        events = visibility_events(_samples(args.input))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(events, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
