"""Bridge a supplied normalized track point to the stored observation schema."""
import argparse
import json
import sys
from pathlib import Path

from .store import MAX_LINE_BYTES, _parse
from .zones import _unique_keys, classify_point, load_config, validate_config

REQUIRED = {"video", "object_id", "label", "t_ms"}


def build_observation(track, zones):
    """Validate a config and track record without changing either input."""
    rectangles = validate_config(zones)
    if not isinstance(track, dict):
        raise ValueError("track must be an object")
    if not REQUIRED <= set(track) or set(track) - (REQUIRED | {"tracklet_id", "x", "y"}):
        raise ValueError("expected video, object_id, label, t_ms, optional tracklet_id and paired x/y")
    if ("x" in track) != ("y" in track):
        raise ValueError("provide both x and y, or neither")
    if "x" in track and (type(track["x"]) not in (int, float)
                         or type(track["y"]) not in (int, float)):
        raise ValueError("supplied x/y must be finite numbers, not null or booleans")
    observation = {key: value for key, value in track.items() if key not in ("x", "y")}
    observation["zone"] = classify_point(rectangles, track.get("x"), track.get("y"))
    try:
        # Use the merged ingestion validator; no dependency on pending parser/adapter PRs.
        _parse(json.dumps(observation).encode("utf-8"))
    except (TypeError, RecursionError) as exc:
        raise ValueError("invalid observation metadata") from exc
    return observation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("track", type=Path, help="one local JSON track-point record")
    args = parser.parse_args(argv)
    try:
        rectangles = load_config(args.config)
        with args.track.open("rb") as source:
            raw = source.read(MAX_LINE_BYTES + 1)
        if len(raw) > MAX_LINE_BYTES:
            raise ValueError("track record exceeds 16384 bytes")
        try:
            record = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys)
        except RecursionError as exc:
            raise ValueError("track record nesting is too deep") from exc
        observation = build_observation(record, {"zones": rectangles})
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(observation, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
