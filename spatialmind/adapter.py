"""Offline replay boundary for externally supplied perception observations."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

from .store import FIELDS, MAX_LINE_BYTES, _parse

MAX_INPUT_BYTES = 64 * 1024 * 1024
SPOOL_MEMORY_BYTES = 1024 * 1024


class ReplayAdapter:
    """Replay validated rows in source order; each iteration reopens the file."""

    def __init__(self, path):
        self.path = Path(path)

    def observations(self):
        """Yield rows lazily; later invalid input can fail after earlier yields."""
        total = line_number = 0
        with self.path.open("rb") as source:
            while line := source.readline(MAX_LINE_BYTES + 1):
                line_number += 1
                total += len(line)
                if total > MAX_INPUT_BYTES:
                    raise ValueError("replay input exceeds 64 MiB")
                if len(line) > MAX_LINE_BYTES:
                    raise ValueError(f"line {line_number}: record exceeds size limit")
                if not line.strip():
                    continue
                try:
                    # Deliberately share ingest's exact parser until it has a
                    # public interface, rather than maintaining a second schema.
                    values = _parse(line)
                except (ValueError, RecursionError) as exc:
                    raise ValueError(f"line {line_number}: {exc}") from exc
                row = dict(zip(FIELDS, values[:len(FIELDS)]))
                if values[-1] is not None:
                    row["tracklet_id"] = values[-1]
                yield row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="local UTF-8 observation JSONL file")
    args = parser.parse_args(argv)
    try:
        with tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY_BYTES, mode="w+b") as output:
            for row in ReplayAdapter(args.input).observations():
                output.write((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                             .encode("utf-8"))
            output.seek(0)
            # Invalid source input never reaches stdout. Delivery itself may
            # still be interrupted by a closed pipe or another output I/O error.
            while chunk := output.read(64 * 1024):
                sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
