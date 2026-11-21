"""Inspect conservative position-and-gap identity suggestions without writes."""
import argparse
import json
import math
import sys
from pathlib import Path

MAX_INPUT_BYTES = 65_536
MAX_CANDIDATES = 100


def _number(value, name, lower, upper):
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite number")
    try:
        valid = math.isfinite(value) and lower <= value <= upper
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} is outside its finite allowed range")
    return value


def _point(record, identity):
    if not isinstance(record, dict) or set(record) != {"video", identity, "t_ms", "x", "y"}:
        raise ValueError(f"point requires exactly video, {identity}, t_ms, x and y")
    for field in ("video", identity):
        value = record[field]
        if (not isinstance(value, str) or not value.strip()
                or not value.isprintable() or len(value) > 512):
            raise ValueError(f"{field} must be nonempty printable text of at most 512 characters")
    if type(record["t_ms"]) is not int or not 0 <= record["t_ms"] < 2**63:
        raise ValueError("t_ms must be a nonnegative 64-bit integer")
    _number(record["x"], "x", 0, 1)
    _number(record["y"], "y", 0, 1)
    return dict(record)


def suggest_association(incoming, candidates, *, max_gap_ms=5000, max_distance=0.15):
    """Return a proposal only when exactly one supplied candidate passes both gates."""
    if type(max_gap_ms) is not int or not 1 <= max_gap_ms <= 60000:
        raise ValueError("max_gap_ms must be an integer from 1 to 60000")
    _number(max_distance, "max_distance", 0, math.sqrt(2))
    incoming = _point(incoming, "tracklet_id")
    if not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES:
        raise ValueError("candidates must be an array of at most 100 points")
    points = [_point(candidate, "object_id") for candidate in candidates]
    keys = [(point["video"], point["object_id"]) for point in points]
    if len(set(keys)) != len(keys):
        raise ValueError("provide at most one candidate per recording/object")
    diagnostics = []
    eligible_ids = []
    for candidate in sorted(points, key=lambda point: (point["video"], point["object_id"])):
        gap = distance = None
        reasons = []
        if candidate["video"] != incoming["video"]:
            reasons.append("different_video")
        else:
            gap = incoming["t_ms"] - candidate["t_ms"]
            distance = math.hypot(incoming["x"] - candidate["x"], incoming["y"] - candidate["y"])
            if gap <= 0:
                reasons.append("nonpositive_gap")
            elif gap > max_gap_ms:
                reasons.append("gap_exceeded")
            if distance > max_distance:
                reasons.append("distance_exceeded")
        eligible = not reasons
        if eligible:
            eligible_ids.append(candidate["object_id"])
        diagnostics.append({"candidate": candidate, "gap_ms": gap, "distance": distance,
                            "eligible": eligible, "reasons": reasons})
    status = "unmatched" if not eligible_ids else "matched" if len(eligible_ids) == 1 else "ambiguous"
    return {
        "incoming": incoming, "status": status,
        "proposed_object_id": eligible_ids[0] if len(eligible_ids) == 1 else None,
        "eligible_object_ids": eligible_ids, "candidates": diagnostics,
        "max_gap_ms": max_gap_ms, "max_distance": max_distance,
    }


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="one local JSON association job")
    args = parser.parse_args(argv)
    try:
        with args.input.open("rb") as source:
            raw = source.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("association input exceeds 64 KiB")
        try:
            job = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys)
        except RecursionError as exc:
            raise ValueError("association input nesting is too deep") from exc
        if (not isinstance(job, dict) or not {"incoming", "candidates"} <= set(job)
                or set(job) - {"incoming", "candidates", "max_gap_ms", "max_distance"}):
            raise ValueError("expected incoming, candidates and optional max_gap_ms/max_distance")
        result = suggest_association(**job)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
