"""Synthetic session-disjoint evaluation manifest validation; no model runs."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from spatialmind.eval_set import MAX_BYTES, load_manifest, validate_manifest

ROOT = Path(__file__).resolve().parents[1]


def manifest():
    sessions = []
    for index, split in enumerate(("dev", "dev", "test"), 1):
        video = f"video-{index}"
        obs = [
            {"video": video, "object_id": "bottle", "t_ms": 100, "label": "blue bottle", "zone": "desk"},
            {"video": video, "object_id": "bottle", "t_ms": 200, "label": "blue bottle", "zone": "shelf"},
            {"video": video, "object_id": "bottle", "t_ms": 300, "label": "blue bottle", "zone": "shelf"},
        ]
        event = {"type": "ZONE_CHANGED", "video": video, "object_id": "bottle",
                 "from_zone": "desk", "to_zone": "shelf", "before_t_ms": 100,
                 "after_t_ms": 200, "confirmed_t_ms": 300}
        sessions.append({
            "session_id": f"session-{index}", "split": split, "video": video,
            "objects": [{"object_id": "bottle", "label": "blue bottle"}],
            "observations": obs, "expected_events": [event],
            "query_cases": [
                {"case_id": f"last-{index}", "prompt": 'Where was "bottle" last seen?',
                 "expected_status": "answered", "expected_evidence": obs[-1]},
                {"case_id": f"missing-{index}", "prompt": 'Where was "absent" last seen?',
                 "expected_status": "evidence_missing", "expected_evidence": None},
                {"case_id": f"unsupported-{index}", "prompt": "What is nearby?",
                 "expected_status": "unsupported", "expected_evidence": None},
                {"case_id": f"events-{index}", "prompt": 'Show zone changes for "bottle"',
                 "expected_status": "answered", "expected_evidence": [event]},
            ],
        })
    return {"version": 1, "provenance": {"kind": "synthetic", "labels": "authored_not_inference"},
            "sessions": sessions}


class EvalSetTests(unittest.TestCase):
    def test_authored_corpus_is_frozen_and_has_session_disjoint_split_counts(self):
        path = ROOT / "examples/evaluation_set.json"
        summary = load_manifest(path)
        self.assertEqual(summary["sha256"], "27860bc7c4b37702c6f9169a441ec5187e17855f1db3dbab5737c13a928a2403")
        self.assertEqual(summary["splits"], {
            "dev": {"sessions": 2, "objects": 2, "observations": 9, "events": 1, "query_cases": 10},
            "test": {"sessions": 1, "objects": 1, "observations": 3, "events": 1, "query_cases": 5},
        })

    def test_cli_returns_raw_byte_hash_and_split_counts(self):
        value = manifest()
        raw = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_bytes(raw)
            result = subprocess.run([sys.executable, "-S", "-m", "spatialmind.eval_set", str(path)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(output["version"], 1)
            self.assertEqual(output["provenance"], value["provenance"])
            self.assertEqual(output["splits"], {
                "dev": {"sessions": 2, "objects": 2, "observations": 6, "events": 2, "query_cases": 8},
                "test": {"sessions": 1, "objects": 1, "observations": 3, "events": 1, "query_cases": 4},
            })
            self.assertEqual(set(p.name for p in Path(tmp).iterdir()), {"manifest.json"})

    def test_duplicate_sessions_videos_and_global_case_ids_rejected(self):
        for mutate in (
            lambda x: x["sessions"][1].update(session_id=x["sessions"][0]["session_id"]),
            lambda x: x["sessions"][1].update(video=x["sessions"][0]["video"]),
            lambda x: x["sessions"][1]["query_cases"][0].update(case_id=x["sessions"][0]["query_cases"][0]["case_id"]),
        ):
            value = manifest(); mutate(value)
            with self.assertRaises(ValueError):
                validate_manifest(value)

    def test_observation_event_query_status_and_provenance_references_are_checked(self):
        mutations = (
            lambda x: x["sessions"][0]["observations"][0].update(video="wrong-video"),
            lambda x: x["sessions"][0]["observations"][0].update(object_id="ghost"),
            lambda x: x["sessions"][0]["observations"][0].update(t_ms=True),
            lambda x: x["sessions"][0]["expected_events"][0].update(confirmed_t_ms=201),
            lambda x: x["sessions"][0]["expected_events"][0].update(to_zone="other"),
            lambda x: x["sessions"][0]["query_cases"][0].update(expected_evidence={"object_id": "bottle", "t_ms": 100}),
            lambda x: x["sessions"][0]["query_cases"][0]["expected_evidence"].update(t_ms=True),
            lambda x: x["sessions"][0]["query_cases"][1].update(expected_status="answered"),
            lambda x: x["sessions"][0]["query_cases"][2].update(expected_evidence={}),
            lambda x: x.update(provenance={"kind": "synthetic", "labels": "model_generated"}),
        )
        for mutate in mutations:
            value = manifest(); mutate(value)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                validate_manifest(value)

    def test_session_split_and_count_bounds(self):
        value = manifest()
        value["sessions"] = value["sessions"][:2]
        with self.assertRaises(ValueError):
            validate_manifest(value)
        value = manifest()
        value["sessions"][2]["split"] = "dev"
        with self.assertRaises(ValueError):
            validate_manifest(value)  # test split must remain represented
        value = manifest(); value["sessions"][0]["objects"] = []
        with self.assertRaises(ValueError):
            validate_manifest(value)
        value = manifest()
        value["sessions"][0]["objects"] = [{"object_id": str(i), "label": "object"} for i in range(101)]
        with self.assertRaises(ValueError):
            validate_manifest(value)

    def test_malformed_duplicate_nonfinite_utf8_and_oversize_inputs_fail_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            valid = json.dumps(manifest(), separators=(",", ":")).encode()
            invalids = [b'{"version":1,"version":1}', b'{"x":NaN}', b'{"x":1e999}', b"\xff", b" " * (MAX_BYTES + 1)]
            for raw in invalids:
                path.write_bytes(raw)
                before = set(p.name for p in Path(tmp).iterdir())
                result = subprocess.run([sys.executable, "-S", "-m", "spatialmind.eval_set", str(path)],
                                        cwd=ROOT, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr)
                self.assertEqual(set(p.name for p in Path(tmp).iterdir()), before)
            path.write_bytes(valid)
            self.assertIn("sha256", load_manifest(path))


if __name__ == "__main__":
    unittest.main()
