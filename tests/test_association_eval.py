"""Unit-only prediction examples validate arithmetic, not model performance."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from spatialmind.association_eval import compare_runs

ROOT = Path(__file__).resolve().parents[1]


def run(*outcomes):
    return {"predictions": [
        {"case_id": case_id, "status": status, "object_id": object_id}
        for case_id, status, object_id in outcomes
    ]}


class PairedEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.cases = {"provenance": "unit-only authored labels", "cases": [
            {"case_id": "a", "candidate_ids": ["right", "wrong"], "expected": {"status": "matched", "object_id": "right"}},
            {"case_id": "b", "candidate_ids": ["wrong"], "expected": {"status": "unmatched", "object_id": None}},
            {"case_id": "c", "candidate_ids": ["right"], "expected": {"status": "ambiguous", "object_id": None}},
        ]}
        self.baseline = run(("a", "matched", "wrong"), ("b", "unmatched", None), ("c", "unmatched", None))
        self.appearance = run(("c", "unmatched", None), ("b", "matched", "wrong"), ("a", "matched", "right"))

    def test_missing_runs_remain_not_run_without_fabricated_deltas(self):
        result = compare_runs(self.cases)
        self.assertEqual(result["appearance_status"], "NOT_RUN")
        self.assertEqual(result["baseline_status"], "NOT_RUN")
        self.assertIsNone(result["appearance"])
        self.assertIsNone(result["accuracy_delta"])
        self.assertIsNone(result["paired_counts"])
        self.assertTrue(all(case["verdict"] is None for case in result["cases"]))
        result = compare_runs(self.cases, self.baseline)
        self.assertEqual(result["baseline_status"], "SUPPLIED")
        self.assertIsNone(result["appearance"])
        self.assertIsNone(result["accuracy_delta"])

    def test_exact_counts_pairing_and_no_source_mutation(self):
        original = copy.deepcopy((self.cases, self.baseline, self.appearance))
        result = compare_runs(self.cases, self.baseline, self.appearance)
        self.assertEqual((self.cases, self.baseline, self.appearance), original)
        self.assertEqual(result["paired_counts"], {"improved": 1, "regressed": 1, "unchanged": 1})
        self.assertEqual(result["baseline"]["false_links"], 1)
        self.assertEqual(result["appearance"]["false_links"], 1)
        self.assertEqual(result["baseline"]["correct_abstentions"], 2)
        self.assertEqual(result["appearance"]["correct_abstentions"], 1)
        self.assertEqual(result["baseline"]["correct"], 1)
        self.assertEqual(result["appearance"]["correct"], 1)
        self.assertEqual(result["baseline"]["accuracy"], 1/3)
        self.assertEqual([case["case_id"] for case in result["cases"]], ["a", "b", "c"])

    def test_incomplete_duplicate_unknown_and_invalid_candidates_rejected(self):
        for field, value in (("case_id", "absent"), ("case_id", "b"), ("object_id", "not_a_candidate"),
                             ("status", "invented")):
            invalid = copy.deepcopy(self.baseline)
            invalid["predictions"][0][field] = value
            with self.assertRaises(ValueError):
                compare_runs(self.cases, invalid, self.appearance)
        incomplete = copy.deepcopy(self.baseline)
        incomplete["predictions"].pop()
        with self.assertRaises(ValueError):
            compare_runs(self.cases, incomplete, self.appearance)
        invalid = copy.deepcopy(self.cases)
        invalid["cases"][0]["candidate_ids"].append("right")
        with self.assertRaises(ValueError):
            compare_runs(invalid, self.baseline, self.appearance)

    def test_fixture_is_labels_only_and_cli_handles_failures_atomically(self):
        fixture = json.loads((ROOT/"examples/appearance_cases.json").read_text())
        oracle = {"predictions": [
            {"case_id": case["case_id"], **case["expected"]} for case in fixture["cases"]
        ]}
        # This oracle is constructed solely to check manifest consistency.
        self.assertEqual(compare_runs(fixture, oracle, oracle)["baseline"]["correct"], 3)
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp)/name for name in ("cases.json", "baseline.json", "appearance.json")]
            for path, value in zip(paths, (self.cases, self.baseline, self.appearance)):
                path.write_text(json.dumps(value))
            command = [sys.executable, "-S", "-m", "spatialmind.association_eval", *map(str, paths)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["case_count"], 3)
            for invalid in (b'{"predictions":[],"predictions":[]}', b" "*1048577, b"\xff", b'{"predictions":NaN}'):
                paths[-1].write_bytes(invalid)
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr)


if __name__ == "__main__":
    unittest.main()
