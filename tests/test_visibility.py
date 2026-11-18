"""Explicit visibility is separate from zone unknown and observed motion."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from spatialmind.visibility import visibility_events

ROOT = Path(__file__).resolve().parents[1]


def sample(time, state="visible", **changes):
    return dict(video="demo", object_id="bottle", state=state, t_ms=time, **changes)


class VisibilityTests(unittest.TestCase):
    def test_transitions_preserve_source_evidence_without_duplicates(self):
        rows = [sample(1, tracklet_id="first"), sample(2, "missing"),
                sample(3, "missing"), sample(4, tracklet_id="second"), sample(5)]
        original = copy.deepcopy(rows)
        result = visibility_events(rows)
        self.assertEqual(rows, original)
        self.assertEqual(result, [
            {"type": "MISSING", "video": "demo", "object_id": "bottle",
             "before": rows[0], "after": rows[1]},
            {"type": "REOBSERVED", "video": "demo", "object_id": "bottle",
             "before": rows[2], "after": rows[3]},
        ])

    def test_silence_and_different_scopes_never_infer_removal_or_merge(self):
        self.assertEqual(visibility_events([sample(0), sample(60000)]), [])
        self.assertEqual(visibility_events([]), [])
        rows = [sample(100), dict(sample(0), video="other"),
                dict(sample(1), object_id="other"), sample(101, "missing")]
        result = visibility_events(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["before"], rows[0])
        self.assertEqual(result[0]["after"], rows[-1])

    def test_invalid_first_order_metadata_and_limits(self):
        invalid_sequences = [
            [sample(0, "missing")], [sample(1), sample(1)], [sample(2), sample(1)],
            [sample(True)], [sample(-1)], [sample(2**63)], [sample(1, "unknown")],
            [sample(1, tracklet_id=None)], [dict(sample(1), zone="unknown")],
            [dict(sample(1), object_id="")], [dict(sample(1), label="bottle")],
            [sample(i) for i in range(10001)],
        ]
        for rows in invalid_sequences:
            with self.subTest(first=rows[0]):
                with self.assertRaises(ValueError):
                    visibility_events(rows)

    def test_cli_emits_array_only_after_whole_input_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"samples.jsonl"
            cmd = [sys.executable, "-S", "-m", "spatialmind.visibility", str(path)]
            path.write_text(json.dumps(sample(1))+"\n"+json.dumps(sample(2, "missing"))+"\n")
            run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)[0]["type"], "MISSING")
            for invalid in ('{"state":"visible","state":"missing"}', '{}',
                            '{"state":', ' '*16385):
                path.write_text(json.dumps(sample(1))+"\n"+invalid)
                run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=10)
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, "")
                self.assertTrue(run.stderr)


if __name__ == "__main__":
    unittest.main()
