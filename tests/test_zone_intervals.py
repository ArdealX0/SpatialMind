"""Interval queries filter confirmation times without clipping their evidence."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ZoneIntervalCLITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.db = self.work / "memory.db"

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "spatialmind", "--db", str(self.db), *map(str, args)],
            cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=15,
        )

    def ingest(self, video="bench", object_id="bottle"):
        path = self.work / "input.jsonl"
        points = [(6000, "drawer"), (1000, "desk"), (2000, "shelf"),
                  (5000, "drawer"), (3000, "shelf")]
        rows = [dict(video=video, object_id=object_id, t_ms=t, zone=z,
                     label="blue bottle") for t, z in points]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        result = self.cli("ingest", path)
        self.assertEqual(result.returncode, 0, result.stderr)

    @staticmethod
    def events(video="bench"):
        return [
            dict(type="ZONE_CHANGED", video=video, object_id="bottle",
                 from_zone="desk", to_zone="shelf", before_t_ms=1000,
                 after_t_ms=2000, confirmed_t_ms=3000),
            dict(type="ZONE_CHANGED", video=video, object_id="bottle",
                 from_zone="shelf", to_zone="drawer", before_t_ms=3000,
                 after_t_ms=5000, confirmed_t_ms=6000),
        ]

    def assert_selection(self, expected, *options):
        result = self.cli("zone-changes", "bottle", *options)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)

    def test_inclusive_endpoints_and_equal_endpoint_keep_full_evidence(self):
        self.ingest()
        events = self.events()
        self.assert_selection(events, "--start-ms", 3000, "--end-ms", 6000)
        self.assert_selection(events[:1], "--start-ms", 3000, "--end-ms", 3000)
        self.assert_selection(events[1:], "--start-ms", 6000, "--end-ms", 6000)

    def test_membership_uses_confirmation_not_candidate_or_baseline_time(self):
        self.ingest()
        self.assert_selection([], "--start-ms", 1000, "--end-ms", 2999)
        self.assert_selection([], "--start-ms", 3001, "--end-ms", 5999)
        self.assert_selection([], "--start-ms", 6001)
        self.assert_selection([], "--start-ms", 0, "--end-ms", 0)

    def test_omitted_bounds_are_unbounded_and_zero_is_valid(self):
        self.ingest()
        events = self.events()
        self.assert_selection(events)
        self.assert_selection(events, "--start-ms", 0)
        self.assert_selection(events[:1], "--end-ms", 3000)
        self.assert_selection(events[1:], "--start-ms", 3001)
        self.assert_selection(events, "--end-ms", 2**63 - 1)

    def test_filter_preserves_recording_scope_and_error_distinctions(self):
        self.ingest()
        self.ingest(video="other")
        self.assert_selection(self.events("other")[:1], "--video", "other",
                              "--start-ms", 3000, "--end-ms", 3000)
        cases = [
            (2, ("bottle", "--start-ms", 999999)),
            (1, ("missing", "--start-ms", 0)),
            (1, ("bottle", "--video", "missing", "--end-ms", 6000)),
        ]
        for code, args in cases:
            with self.subTest(args=args):
                result = self.cli("zone-changes", *args)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(result.stdout.strip(), "")
                self.assertTrue(result.stderr.strip())

    def test_invalid_bounds_fail_before_creating_database(self):
        cases = [
            ("--start-ms", 6000, "--end-ms", 3000),
            ("--start-ms", -1), ("--end-ms", -1),
            ("--start-ms", "1.5"), ("--end-ms", "NaN"),
            ("--start-ms", "True"), ("--end-ms", 2**63),
            ("--start-ms", 2**63),
        ]
        for args in cases:
            with self.subTest(args=args):
                result = self.cli("zone-changes", "bottle", *args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout.strip(), "")
                self.assertTrue(result.stderr.strip())
                self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
