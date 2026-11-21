"""Conservative spatial/time candidate policy on supplied synthetic positions."""
import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from spatialmind.association import suggest_association

ROOT = Path(__file__).resolve().parents[1]
INCOMING = dict(video="demo", tracklet_id="new", t_ms=5000, x=.5, y=.5)


def candidate(**changes):
    return dict(dict(video="demo", object_id="bottle", t_ms=0, x=.375, y=.5), **changes)


class AssociationTests(unittest.TestCase):
    def test_labeled_cases_and_input_immutability(self):
        cases = json.loads((ROOT/"examples/association_cases.json").read_text())["cases"]
        for case in cases:
            before = copy.deepcopy(case["input"])
            result = suggest_association(**case["input"])
            self.assertEqual(case["input"], before)
            self.assertEqual(result["status"], case["expected_status"])
            self.assertEqual(result["proposed_object_id"], case["expected_object_id"])

    def test_inclusive_gates_rejections_and_deterministic_ambiguity(self):
        rows = [candidate(), candidate(object_id="closer", x=.49)]
        result = suggest_association(INCOMING, rows, max_distance=.125)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result, suggest_association(INCOMING, list(reversed(rows)), max_distance=.125))
        self.assertIsNone(result["proposed_object_id"])
        self.assertEqual(result["eligible_object_ids"], ["bottle", "closer"])
        self.assertEqual(suggest_association(INCOMING, [candidate()], max_gap_ms=4999)["status"], "unmatched")
        for row, reason in ((candidate(video="other"), "different_video"),
                            (candidate(t_ms=5000), "nonpositive_gap"),
                            (candidate(t_ms=6000), "nonpositive_gap"),
                            (candidate(x=0), "distance_exceeded")):
            diagnostic = suggest_association(INCOMING, [row])["candidates"][0]
            self.assertIn(reason, diagnostic["reasons"])
            if reason == "different_video":
                self.assertIsNone(diagnostic["gap_ms"])
                self.assertIsNone(diagnostic["distance"])
        self.assertEqual(suggest_association(INCOMING, [])["status"], "unmatched")

    def test_strict_validation(self):
        invalid = [dict(INCOMING, x=True), dict(INCOMING, x=math.nan),
                   dict(INCOMING, t_ms=True), dict(INCOMING, zone="left"),
                   dict(INCOMING, tracklet_id=None), dict(INCOMING, y=1.1)]
        for incoming in invalid:
            with self.assertRaises(ValueError):
                suggest_association(incoming, [])
        for candidates in ([candidate(), candidate()], [candidate()]*101, None):
            with self.assertRaises(ValueError):
                suggest_association(INCOMING, candidates)
        for options in ({"max_gap_ms":True}, {"max_gap_ms":60001},
                        {"max_distance":math.inf}, {"max_distance":-1}):
            with self.assertRaises(ValueError):
                suggest_association(INCOMING, [], **options)

    def test_offline_cli_and_no_partial_invalid_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"job.json"
            command = [sys.executable, "-S", "-m", "spatialmind.association", str(path)]
            path.write_text(json.dumps({"incoming": INCOMING, "candidates": [candidate()]}))
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "matched")
            for raw in (b'{"incoming":{},"incoming":{}}', b" "*65537, b"\xff",
                        b'{"incoming":{},"candidates":[],"extra":1}'):
                path.write_bytes(raw)
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr)


if __name__ == "__main__":
    unittest.main()
