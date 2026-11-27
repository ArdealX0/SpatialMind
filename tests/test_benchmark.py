"""Independent scoring and operational checks for the frozen CPU benchmark."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from spatialmind.benchmark import run_benchmark, score_events, score_queries
from tests.test_eval_set import manifest

ROOT = Path(__file__).resolve().parents[1]
FROZEN_SHA256 = "27860bc7c4b37702c6f9169a441ec5187e17855f1db3dbab5737c13a928a2403"


def event(zone="shelf", confirmed=300):
    return {"type": "ZONE_CHANGED", "video": "v", "object_id": "bottle",
            "from_zone": "desk", "to_zone": zone, "before_t_ms": 100,
            "after_t_ms": 200, "confirmed_t_ms": confirmed}


class BenchmarkTests(unittest.TestCase):
    def test_event_exact_multiset_scoring_counts_duplicates_and_wrong_fields(self):
        expected = [event()]
        predicted = [event(), event(), event(zone="counter"), event(confirmed=301)]
        result = score_events(expected, predicted)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 3, 0))
        self.assertEqual((result["total_expected"], result["total_predicted"]), (1, 4))
        self.assertEqual(result["precision"], 0.25)
        self.assertEqual(result["recall"], 1.0)

        wrong_only = score_events([event()], [event(zone="counter")])
        self.assertEqual((wrong_only["tp"], wrong_only["fp"], wrong_only["fn"]), (0, 1, 1))
        self.assertEqual(wrong_only["precision"], 0.0)
        self.assertEqual(wrong_only["recall"], 0.0)

    def test_event_exact_evidence_distinguishes_boolean_from_number_and_empty_denominators(self):
        expected = [{"type": "ZONE_CHANGED", "confirmed_t_ms": 1}]
        predicted = [{"type": "ZONE_CHANGED", "confirmed_t_ms": True}]
        result = score_events(expected, predicted)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (0, 1, 1))
        empty = score_events([], [])
        self.assertEqual((empty["tp"], empty["fp"], empty["fn"]), (0, 0, 0))
        self.assertEqual((empty["total_expected"], empty["total_predicted"]), (0, 0))
        self.assertIsNone(empty["precision"])
        self.assertIsNone(empty["recall"])
        only_false = score_events([], [event()])
        self.assertEqual((only_false["tp"], only_false["fp"], only_false["fn"]), (0, 1, 0))
        self.assertEqual(only_false["precision"], 0.0)
        self.assertIsNone(only_false["recall"])

    def test_query_scoring_keeps_wrong_missing_and_unsupported_answers_in_denominators(self):
        cases = [
            {"case_id": "right", "expected_status": "answered", "expected_evidence": {"t_ms": 1}},
            {"case_id": "wrong-evidence", "expected_status": "answered", "expected_evidence": {"t_ms": 2}},
            {"case_id": "missing", "expected_status": "evidence_missing", "expected_evidence": None},
            {"case_id": "unsupported", "expected_status": "unsupported", "expected_evidence": None},
        ]
        predictions = [
            {"status": "answered", "evidence": {"t_ms": 1}},
            {"status": "answered", "evidence": {"t_ms": 3}},
            {"status": "answered", "evidence": {"t_ms": 4}},
            {"status": "unsupported"},
        ]
        result = score_queries(cases, predictions)
        self.assertEqual((result["correct"], result["total"], result["accuracy"]), (2, 4, 0.5))
        self.assertEqual(result["by_expected_status"]["answered"],
                         {"correct": 1, "total": 2, "accuracy": 0.5})
        self.assertEqual(result["by_expected_status"]["evidence_missing"],
                         {"correct": 0, "total": 1, "accuracy": 0.0})
        self.assertEqual(result["by_expected_status"]["unsupported"],
                         {"correct": 1, "total": 1, "accuracy": 1.0})
        self.assertEqual(result["unsupported"], {"expected": 1, "predicted": 1, "correct": 1})
        self.assertEqual(result["answered_on_unanswerable"], 1)
        self.assertFalse(result["results"][1]["correct"])

        no_cases = score_queries([], [])
        self.assertEqual((no_cases["total"], no_cases["correct"]), (0, 0))
        self.assertIsNone(no_cases["accuracy"])
        self.assertIsNone(no_cases["by_expected_status"]["unsupported"]["accuracy"])

    def test_frozen_corpus_run_has_separate_deterministic_dev_and_test_results(self):
        path = ROOT / "examples/evaluation_set.json"
        first = run_benchmark(path)
        second = run_benchmark(path)
        self.assertEqual(first, second)
        self.assertEqual(first["corpus"]["sha256"], FROZEN_SHA256)
        self.assertEqual(set(first["splits"]), {"dev", "test"})
        self.assertEqual(first["splits"]["dev"]["counts"]["sessions"], 2)
        self.assertEqual(first["splits"]["test"]["counts"]["sessions"], 1)
        self.assertEqual(first["config"], {"split": "all", "confirm_observations": 2, "max_gap_ms": 5000})

    def test_split_selection_cli_and_digest_mismatch_are_atomic_and_read_only(self):
        raw = (json.dumps(manifest(), separators=(",", ":")) + "\n").encode()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_bytes(raw)
            before = {p.name: p.read_bytes() for p in Path(tmp).iterdir()}
            command = [sys.executable, "-S", "-m", "spatialmind.benchmark", str(path), "--split", "test"]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15)
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            result = json.loads(first.stdout)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(result["config"]["split"], "test")
            self.assertEqual(set(result["splits"]), {"test"})
            self.assertEqual(result["corpus"]["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual({p.name: p.read_bytes() for p in Path(tmp).iterdir()}, before)

            bad = subprocess.run(command + ["--expected-sha256", "0" * 64], cwd=ROOT,
                                 capture_output=True, text=True, timeout=15)
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(bad.stdout, "")
            self.assertTrue(bad.stderr)
            self.assertEqual({p.name: p.read_bytes() for p in Path(tmp).iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
