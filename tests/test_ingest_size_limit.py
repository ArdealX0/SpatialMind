"""Direct ingestion enforces total raw-byte limits atomically."""
import io
import json
import unittest
from unittest.mock import patch

from spatialmind.store import connect, ingest, last_seen


def row(video, object_id, tracklet_id):
    return {
        "video": video, "object_id": object_id, "t_ms": 1,
        "label": "blue bottle", "zone": "bench", "tracklet_id": tracklet_id,
    }


def encode(*rows):
    return b"".join(json.dumps(item).encode("utf-8") + b"\n" for item in rows)


class IngestSizeLimitTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        self.addCleanup(self.db.close)

    def test_exact_total_byte_limit_is_accepted(self):
        content = encode(row("session", "bottle", "track-1"))
        with patch("spatialmind.store.MAX_INPUT_BYTES", len(content)):
            result = ingest(self.db, io.BytesIO(content))
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(last_seen(self.db, "bottle", "session")["tracklet_id"], "track-1")

    def test_blank_lines_count_toward_total_limit(self):
        with patch("spatialmind.store.MAX_INPUT_BYTES", 3):
            with self.assertRaisesRegex(ValueError, "input exceeds"):
                ingest(self.db, io.BytesIO(b"\n\n\n\n"))
        self.assertEqual(self.db.execute("SELECT count(*) FROM observations").fetchone()[0], 0)

    def test_late_overflow_rolls_back_new_observation_and_tracklet_link(self):
        original = row("session", "existing", "track-existing")
        self.assertEqual(ingest(self.db, io.BytesIO(encode(original)))["inserted"], 1)
        candidate = row("session", "new-object", "track-new")
        content = encode(candidate)
        with patch("spatialmind.store.MAX_INPUT_BYTES", len(content) + 1):
            with self.assertRaisesRegex(ValueError, "input exceeds"):
                ingest(self.db, io.BytesIO(content + b"\n\n"))
        self.assertIsNone(last_seen(self.db, "new-object", "session"))
        self.assertIsNone(self.db.execute(
            "SELECT 1 FROM tracklet_links WHERE video=? AND tracklet_id=?",
            ("session", "track-new"),
        ).fetchone())
        self.assertEqual(last_seen(self.db, "existing", "session")["tracklet_id"], "track-existing")


if __name__ == "__main__":
    unittest.main()
