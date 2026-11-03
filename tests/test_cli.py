"""End-to-end checks for SpatialMind's persistent last-seen query."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class VisualMemoryCLITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.db = self.work / "memory.db"

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "spatialmind", "--db", str(self.db), *args],
            cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=15,
        )

    @staticmethod
    def observation(object_id, t_ms, zone):
        return {
            "video": "bench.mp4", "object_id": object_id, "label": "blue bottle",
            "t_ms": t_ms, "zone": zone,
        }

    def ingest(self, *records):
        input_path = self.work / "observations.jsonl"
        input_path.write_text(
            "".join(json.dumps(row) + "\n" for row in records), encoding="utf-8",
        )
        return self.cli("ingest", str(input_path))

    def assert_last_seen(self, expected):
        result = self.cli("last-seen", expected["object_id"])
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads(result.stdout)
        for key, value in expected.items():
            self.assertEqual(row[key], value, key)

    def test_last_seen_survives_restart_and_uses_video_time_for_one_identity(self):
        latest = self.observation("bottle-01", 12000, "shelf")
        result = self.ingest(
            latest,
            self.observation("bottle-01", 3000, "bench"),
            self.observation("bottle-02", 15000, "drawer"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_last_seen(latest)

    def test_failed_batch_rolls_back_without_changing_prior_history(self):
        original = self.observation("bottle-01", 3000, "bench")
        result = self.ingest(original)
        self.assertEqual(result.returncode, 0, result.stderr)
        invalid = self.observation("bottle-01", 13000, "shelf")
        del invalid["t_ms"]
        result = self.ingest(self.observation("bottle-01", 12000, "shelf"), invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assert_last_seen(original)


if __name__ == "__main__":
    unittest.main()
