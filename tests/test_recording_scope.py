"""Recording isolation checks using the public CLI in fresh processes."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RecordingScopeTests(unittest.TestCase):
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

    def ingest(self, *rows):
        source = self.work / "input.jsonl"
        source.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8",
        )
        result = self.cli("ingest", str(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    @staticmethod
    def row(video, t_ms, zone, object_id="object-01", label="blue bottle"):
        return dict(video=video, object_id=object_id, t_ms=t_ms, zone=zone, label=label)

    def assert_query_row(self, expected):
        result = self.cli("last-seen", expected["object_id"], "--video", expected["video"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)

    def test_unscoped_shared_id_is_ambiguous_without_answer_json(self):
        self.ingest(
            self.row("morning.mp4", 1000, "desk"),
            self.row("evening.mp4", 50000, "shelf"),
        )
        result = self.cli("last-seen", "object-01")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), "")
        self.assertIn("--video", result.stderr)

    def test_explicit_scope_uses_latest_timestamp_only_in_that_recording(self):
        latest = self.row("morning.mp4", 4000, "desk-right")
        other = self.row("evening.mp4", 50000, "shelf", label="red toolbox")
        self.ingest(latest, other, self.row("morning.mp4", 1000, "desk-left"))
        self.assert_query_row(latest)
        self.assert_query_row(other)

    def test_identical_object_timestamp_is_independent_between_recordings(self):
        first = self.row("first.mp4", 1000, "desk", label="blue bottle")
        second = self.row("second.mp4", 1000, "shelf", label="red toolbox")
        result = self.ingest(first, second)
        self.assertEqual(result, {"inserted": 2, "unchanged": 0})
        self.assert_query_row(first)
        self.assert_query_row(second)

    def test_missing_video_or_object_never_falls_back_to_another_recording(self):
        self.ingest(
            self.row("first.mp4", 1000, "desk"),
            self.row("second.mp4", 2000, "shelf", object_id="object-02"),
        )
        cases = (
            ("object-01", "--video", "missing.mp4"),
            ("object-01", "--video", "second.mp4"),
            ("missing-object", "--video", "first.mp4"),
            ("missing-object",),
        )
        for args in cases:
            with self.subTest(args=args):
                result = self.cli("last-seen", *args)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout.strip(), "")
                self.assertTrue(result.stderr.strip())

    def test_unscoped_single_recording_preserves_evidence(self):
        latest = self.row("one.mp4", 3000, "shelf")
        self.ingest(latest, self.row("one.mp4", 1000, "desk"))
        result = self.cli("last-seen", "object-01")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), latest)


if __name__ == "__main__":
    unittest.main()
