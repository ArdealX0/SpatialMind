"""Object histories retain ordered evidence within a single recording."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class HistoryCLITests(unittest.TestCase):
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
    def row(t_ms, zone, video="first.mp4", object_id="bottle-01", label="blue bottle"):
        return dict(video=video, object_id=object_id, t_ms=t_ms, label=label, zone=zone)

    def ingest(self, *rows):
        path = self.work / "input.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        result = self.cli("ingest", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)

    def assert_history(self, args, expected):
        result = self.cli("history", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        history = json.loads(result.stdout)
        self.assertEqual(history, expected)
        latest = self.cli("last-seen", *args)
        self.assertEqual(latest.returncode, 0, latest.stderr)
        self.assertEqual(json.loads(latest.stdout), history[-1])

    def test_scoped_history_orders_and_preserves_each_observation(self):
        first = self.row(0, "desk-left", label="bottle")
        middle = self.row(2000, "desk-right")
        last = self.row(9000, "shelf", label="blue water bottle")
        other_video = self.row(100000, "drawer", video="second.mp4", label="red bottle")
        self.ingest(
            last, other_video, middle,
            self.row(15000, "floor", object_id="bottle-02"), first,
        )
        self.assert_history(("bottle-01", "--video", "first.mp4"), [first, middle, last])
        self.assert_history(("bottle-01", "--video", "second.mp4"), [other_video])

    def test_single_recording_can_be_resolved_implicitly(self):
        first = self.row(10, "desk")
        last = self.row(3000, "shelf")
        self.ingest(last, first, self.row(5000, "floor", object_id="other"))
        self.assert_history(("bottle-01",), [first, last])

    def test_shared_id_without_video_has_no_ambiguous_success_output(self):
        self.ingest(self.row(1000, "desk"), self.row(9000, "shelf", video="second.mp4"))
        result = self.cli("history", "bottle-01")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), "")
        self.assertIn("--video", result.stderr)

    def test_missing_match_never_falls_back_to_other_objects_or_recordings(self):
        self.ingest(
            self.row(1000, "desk"),
            self.row(9000, "shelf", video="second.mp4", object_id="other"),
        )
        for args in (
            ("unknown",),
            ("unknown", "--video", "first.mp4"),
            ("bottle-01", "--video", "missing.mp4"),
            ("bottle-01", "--video", "second.mp4"),
        ):
            with self.subTest(args=args):
                result = self.cli("history", *args)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout.strip(), "")
                self.assertTrue(result.stderr.strip())


if __name__ == "__main__":
    unittest.main()
