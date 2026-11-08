"""Normalized zones classify evidence without changing observation storage."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ZonesCLITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.config = self.work / "zones.json"
        self.write_config([self.zone("left", [0, 0, .5, 1]),
                           self.zone("right", [.5, 0, 1, 1])])

    @staticmethod
    def zone(name, bounds):
        return {"name": name, "bounds": bounds}

    def write_config(self, zones):
        self.config.write_text(json.dumps({"zones": zones}), encoding="utf-8")

    def run_module(self, module, *args):
        return subprocess.run([sys.executable, "-m", module, *map(str, args)],
                              cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=15)

    def classify(self, *args):
        return self.run_module("spatialmind.zones", self.config, *args)

    def assert_zone(self, expected, *args):
        result = self.classify(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"zone": expected})
        return expected

    def assert_rejected(self, *args):
        result = self.classify(*args)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout.strip(), "")
        self.assertTrue(result.stderr.strip())

    def test_shared_boundaries_and_frame_corners_have_single_owner(self):
        for x, y, expected in ((0, 0, "left"), (.499999, 1, "left"),
                               (.5, 0, "right"), (1, 1, "right")):
            with self.subTest(x=x, y=y):
                self.assert_zone(expected, "--x", x, "--y", y)
        self.write_config([self.zone("top", [0, 0, 1, .5]),
                           self.zone("bottom", [0, .5, 1, 1])])
        self.assert_zone("bottom", "--x", .2, "--y", .5)

    def test_overlap_is_unknown_regardless_of_configuration_order(self):
        zones = [self.zone("desk", [0, 0, .8, .8]),
                 self.zone("shelf", [.2, .2, 1, 1])]
        for ordered in (zones, zones[::-1]):
            self.write_config(ordered)
            self.assert_zone("unknown", "--x", .4, "--y", .4)
            self.assert_zone("desk", "--x", .1, "--y", .1)

    def test_missing_gap_and_outside_coordinates_are_unknown(self):
        self.assert_zone("unknown")
        for x, y in ((-0.01, .5), (1.01, .5), (.5, -1), (.5, 2)):
            with self.subTest(x=x, y=y):
                self.assert_zone("unknown", "--x", x, "--y", y)
        self.write_config([self.zone("desk", [.2, .2, .8, .8])])
        self.assert_zone("unknown", "--x", .1, "--y", .1)
        self.assert_zone("unknown", "--x", .8, "--y", .4)

    def test_partial_and_nonfinite_coordinates_are_errors(self):
        for args in (("--x", .5), ("--y", .5),
                     ("--x", "nan", "--y", .5),
                     ("--x", .5, "--y", "inf")):
            with self.subTest(args=args):
                self.assert_rejected(*args)

    def test_invalid_names_and_bounds_are_rejected(self):
        invalid = [
            [self.zone("unknown", [0, 0, 1, 1])],
            [self.zone("x" * 513, [0, 0, 1, 1])],
            [self.zone("", [0, 0, 1, 1])],
            [self.zone(True, [0, 0, 1, 1])],
            [self.zone("desk", [0, 0, .5, 1]), self.zone("desk", [.5, 0, 1, 1])],
        ]
        invalid += [[self.zone("desk", bounds)] for bounds in (
            [0, 0, 0, 1], [.8, 0, .2, 1], [0, .5, 1, .5],
            [-.1, 0, 1, 1], [0, 0, 1.1, 1], [False, 0, 1, 1],
            [0, 0, float("nan"), 1], [0, 0, float("inf"), 1], [0, 0, 1],
        )]
        for zones in invalid:
            with self.subTest(zones=zones):
                self.write_config(zones)
                self.assert_rejected()

    def test_malformed_duplicate_keys_and_resource_limits_are_rejected(self):
        invalid = [
            "{", '{"zones":[],"zones":[]}', '{"zones":true}',
            '{"zones":[{"name":"a","name":"b","bounds":[0,0,1,1]}]}',
            json.dumps({"zones": [self.zone(str(i), [0, 0, 1, 1]) for i in range(101)]}),
            json.dumps({"zones": []}) + " " * 65536,
        ]
        for raw in invalid:
            with self.subTest(prefix=raw[:80], length=len(raw)):
                self.config.write_text(raw, encoding="utf-8")
                self.assert_rejected()

    def test_valid_limits_and_empty_zone_set_are_accepted(self):
        name = "x" * 512
        self.write_config([self.zone(name, [0, 0, 1, 1])])
        self.assert_zone(name, "--x", .5, "--y", .5)
        self.write_config([self.zone(str(i), [0, 0, 1, 1]) for i in range(100)])
        self.assert_zone("unknown", "--x", .5, "--y", .5)
        self.write_config([])
        self.assert_zone("unknown", "--x", .5, "--y", .5)

    def test_unknown_classification_roundtrips_existing_history_schema(self):
        zone = self.assert_zone("unknown")
        row = dict(video="bench", object_id="bottle-01", t_ms=1000,
                   label="blue bottle", zone=zone)
        source = self.work / "observations.jsonl"
        source.write_text(json.dumps(row) + "\n", encoding="utf-8")
        db = self.work / "memory.db"
        result = self.run_module("spatialmind", "--db", db, "ingest", source)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_module("spatialmind", "--db", db, "history", "bottle-01")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [row])


if __name__ == "__main__":
    unittest.main()
