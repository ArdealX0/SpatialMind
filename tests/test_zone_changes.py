"""Derived zone changes retain source evidence and recording boundaries."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ZoneChangesCLITests(unittest.TestCase):
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
    def row(t_ms, zone, video="bench", object_id="bottle"):
        return dict(video=video, object_id=object_id, t_ms=t_ms,
                    label="blue bottle", zone=zone)

    @staticmethod
    def event(before, after, from_zone, to_zone, video="bench", object_id="bottle"):
        return dict(type="ZONE_CHANGED", video=video, object_id=object_id,
                    from_zone=from_zone, to_zone=to_zone,
                    before_t_ms=before, after_t_ms=after, confirmed_t_ms=after)

    def ingest(self, *rows):
        path = self.work / "observations.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        result = self.cli("ingest", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)

    def assert_events(self, expected, *args):
        result = self.cli("zone-changes", *args, "--confirm-observations", "1",
                          "--max-gap-ms", "10000")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)

    def snapshot(self):
        with closing(sqlite3.connect(f"{self.db.as_uri()}?mode=ro", uri=True)) as db:
            return list(db.iterdump())

    def test_sorted_transitions_use_latest_same_zone_evidence_without_mutation(self):
        self.ingest(
            self.row(4000, "desk"), self.row(2000, "desk"),
            self.row(5000, "shelf"), self.row(1000, "desk"),
            self.row(9000, "drawer"), self.row(7000, "shelf"),
            self.row(4500, "floor", object_id="other"),
        )
        before = self.snapshot()
        expected = [self.event(4000, 5000, "desk", "shelf"),
                    self.event(7000, 9000, "shelf", "drawer")]
        self.assert_events(expected, "bottle")
        self.assert_events(expected, "bottle")
        self.assertEqual(self.snapshot(), before)

    def test_unknown_resets_chain_and_later_known_crossing_remains(self):
        self.ingest(
            self.row(0, "unknown"), self.row(1000, "desk"),
            self.row(2000, "unknown"), self.row(3000, "unknown"),
            self.row(4000, "shelf"), self.row(5000, "drawer"),
            self.row(6000, "unknown"),
        )
        self.assert_events([self.event(4000, 5000, "shelf", "drawer")], "bottle")

    def test_existing_histories_without_changes_return_successful_empty_array(self):
        for index, zones in enumerate((["desk"], ["desk", "desk"],
                                       ["unknown", "unknown"], ["desk", "unknown", "shelf"])):
            object_id = f"object-{index}"
            self.ingest(*(self.row(i * 1000, zone, object_id=object_id)
                          for i, zone in enumerate(zones)))
            with self.subTest(zones=zones):
                self.assert_events([], object_id)

    def test_recording_scope_never_combines_independent_timelines(self):
        self.ingest(
            self.row(1000, "desk"), self.row(2000, "shelf"),
            self.row(1000, "floor", video="other"), self.row(9000, "drawer", video="other"),
        )
        self.assert_events([self.event(1000, 2000, "desk", "shelf")],
                           "bottle", "--video", "bench")
        self.assert_events([self.event(1000, 9000, "floor", "drawer", video="other")],
                           "bottle", "--video", "other")
        result = self.cli("zone-changes", "bottle")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), "")
        self.assertIn("--video", result.stderr)

    def test_missing_object_or_recording_is_distinct_from_no_changes(self):
        self.ingest(self.row(1000, "desk"), self.row(1000, "shelf", video="other",
                                                    object_id="other-object"))
        for args in (("missing",), ("missing", "--video", "bench"),
                     ("bottle", "--video", "missing"), ("bottle", "--video", "other")):
            with self.subTest(args=args):
                result = self.cli("zone-changes", *args,
                          "--confirm-observations", "1", "--max-gap-ms", "10000")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout.strip(), "")
                self.assertTrue(result.stderr.strip())


if __name__ == "__main__":
    unittest.main()
