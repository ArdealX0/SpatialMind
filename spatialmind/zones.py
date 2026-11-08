"""Assign a normalized image point to a configured rectangular zone."""
import argparse
import json
import math
import sys
from pathlib import Path

MAX_CONFIG_BYTES = 65_536
MAX_ZONES = 100
UNKNOWN = "unknown"


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _finite_number(value):
    if type(value) not in (int, float):
        raise ValueError("coordinates must be finite numbers, not booleans")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("coordinates must be finite numbers")
    return value


def validate_config(payload):
    """Validate the strict config schema and return its zone definitions."""
    if not isinstance(payload, dict) or set(payload) != {"zones"}:
        raise ValueError("config must contain exactly the zones field")
    zones = payload["zones"]
    if not isinstance(zones, list) or len(zones) > MAX_ZONES:
        raise ValueError("zones must be an array of at most 100 rectangles")
    names = set()
    for zone in zones:
        if not isinstance(zone, dict) or set(zone) != {"name", "bounds"}:
            raise ValueError("each zone must contain exactly name and bounds")
        name = zone["name"]
        if (
            not isinstance(name, str)
            or not name.strip()
            or not name.isprintable()
            or len(name) > 512
        ):
            raise ValueError("zone name must be nonempty printable text of at most 512 characters")
        if name == UNKNOWN or name in names:
            raise ValueError("zone names must be unique and cannot be unknown")
        names.add(name)
        bounds = zone["bounds"]
        if not isinstance(bounds, list) or len(bounds) != 4:
            raise ValueError("bounds must be [x_min, y_min, x_max, y_max]")
        x_min, y_min, x_max, y_max = map(_finite_number, bounds)
        if not (0 <= x_min < x_max <= 1 and 0 <= y_min < y_max <= 1):
            raise ValueError("bounds must satisfy 0 <= min < max <= 1 on both axes")
    return zones


def load_config(path):
    """Read a bounded UTF-8 JSON file; duplicate fields are rejected."""
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_CONFIG_BYTES + 1)
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError("config exceeds 64 KiB")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys)
    except RecursionError as exc:
        raise ValueError("config nesting is too deep") from exc
    return validate_config(payload)


def classify_point(zones, x=None, y=None):
    """Classify a point against validated zones; ambiguity yields unknown."""
    if x is None and y is None:
        return UNKNOWN
    if x is None or y is None:
        raise ValueError("provide both x and y, or neither")
    x, y = _finite_number(x), _finite_number(y)
    if not (0 <= x <= 1 and 0 <= y <= 1):
        return UNKNOWN
    matches = []
    for zone in zones:
        x_min, y_min, x_max, y_max = zone["bounds"]
        within_x = x_min <= x and (x < x_max or x == x_max == 1)
        within_y = y_min <= y and (y < y_max or y == y_max == 1)
        if within_x and within_y:
            matches.append(zone["name"])
    return matches[0] if len(matches) == 1 else UNKNOWN


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="rectangular zone JSON config")
    parser.add_argument("--x", type=float, help="normalized horizontal coordinate")
    parser.add_argument("--y", type=float, help="normalized vertical coordinate")
    args = parser.parse_args(argv)
    try:
        zones = load_config(args.config)
        result = classify_point(zones, args.x, args.y)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"zone": result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
