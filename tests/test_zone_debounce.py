"""Debounced transitions require contiguous evidence without bridging gaps."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ZoneDebounceCLITests(unittest.TestCase):
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

    def ingest(self, points, object_id="bottle"):
        path = self.work / "input.jsonl"
        rows = [dict(video="bench", object_id=object_id, t_ms=t, zone=z,
                     label="blue bottle") for t, z in points]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        result = self.cli("ingest", path)
        self.assertEqual(result.returncode, 0, result.stderr)

    @staticmethod
    def event(before, after, confirmed, source="desk", target="shelf", object_id="bottle"):
        return dict(type="ZONE_CHANGED", video="bench", object_id=object_id,
                    from_zone=source, to_zone=target, before_t_ms=before,
                    after_t_ms=after, confirmed_t_ms=confirmed)

    def assert_events(self, expected, *options, object_id="bottle"):
        result = self.cli("zone-changes", object_id, *options)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)

    def test_default_cancels_jitter_and_keeps_first_and_confirming_evidence(self):
        self.ingest([(800, "drawer"), (0, "desk"), (100, "shelf"), (200, "desk"),
                     (300, "shelf"), (400, "shelf"), (500, "shelf"), (700, "drawer")])
        self.assert_events([self.event(200, 300, 400),
                            self.event(500, 700, 800, "shelf", "drawer")])

    def test_alternating_targets_cannot_accumulate_confirmation(self):
        self.ingest([(0, "desk"), (100, "shelf"), (200, "drawer"),
                     (300, "shelf"), (400, "drawer"), (500, "drawer")])
        self.assert_events([self.event(0, 400, 500, target="drawer")])

    def test_unknown_and_gap_break_chain_then_allow_new_transition(self):
        cases = [
            [(0, "desk"), (100, "shelf"), (200, "unknown"),
             (300, "shelf"), (400, "shelf"), (500, "drawer"), (600, "drawer")],
            [(0, "desk"), (100, "shelf"), (60100, "shelf"),
             (60200, "shelf"), (60300, "drawer"), (60400, "drawer")],
        ]
        for index, points in enumerate(cases):
            object_id = f"object-{index}"
            self.ingest(points, object_id)
            self.assert_events([self.event(points[-3][0], points[-2][0], points[-1][0],
                                            "shelf", "drawer", object_id)],
                               object_id=object_id)

    def test_gap_limit_is_inclusive_and_configurable(self):
        self.ingest([(0, "desk"), (5000, "shelf"), (10000, "shelf")])
        self.assert_events([self.event(0, 5000, 10000)])
        self.assert_events([], "--max-gap-ms", 4999)

    def test_confirmation_count_options_and_unconfirmed_tail(self):
        self.ingest([(0, "desk"), (100, "shelf"), (200, "shelf"), (300, "shelf"),
                     (400, "drawer")])
        self.assert_events([self.event(0, 100, 300)], "--confirm-observations", 3)
        self.assert_events([self.event(0, 100, 100),
                            self.event(300, 400, 400, "shelf", "drawer")],
                           "--confirm-observations", 1)
        self.assert_events([], "--confirm-observations", 4)

    def test_invalid_cli_thresholds_fail_without_success_json(self):
        self.ingest([(0, "desk")])
        for flag in ("--confirm-observations", "--max-gap-ms"):
            for value in ("0", "-1", "1.5", "NaN", "True", str(2**63)):
                with self.subTest(flag=flag, value=value):
                    result = self.cli("zone-changes", "bottle", flag, value)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stdout.strip(), "")
                    self.assertTrue(result.stderr.strip())


if __name__ == "__main__":
    unittest.main()
