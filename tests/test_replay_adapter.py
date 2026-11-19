"""Offline replay preserves supplied evidence and validates before CLI output."""
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReplayAdapterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.source = self.work / "source.jsonl"

    @staticmethod
    def row(t_ms=0, **extra):
        return dict(video="bench", object_id="bottle", t_ms=t_ms,
                    label="blue bottle", zone="desk", **extra)

    def write_rows(self, *rows):
        self.source.write_text("".join(json.dumps(row) + "\n" for row in rows),
                               encoding="utf-8")

    def replay(self, path=None):
        return subprocess.run(
            [sys.executable, "-S", "-m", "spatialmind.adapter",
             str(self.source if path is None else path)],
            cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=20,
        )

    def assert_rejected(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.strip())
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_preserves_fields_source_order_timestamps_and_duplicates(self):
        rows = [self.row(5000, tracklet_id="later"), self.row(),
                self.row(), self.row(2**63 - 1, tracklet_id="last")]
        self.write_rows(*rows)
        result = self.replay()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([json.loads(line) for line in result.stdout.splitlines()], rows)

    def test_iterator_is_offline_and_preserves_validated_observations(self):
        rows = [self.row(1000), self.row(0, tracklet_id="track-01")]
        self.write_rows(*rows)
        with patch("socket.socket", side_effect=AssertionError("network is forbidden")):
            module = importlib.import_module("spatialmind.adapter")
            self.assertEqual(list(module.ReplayAdapter(self.source).observations()), rows)

    def test_late_invalid_rows_never_emit_partial_success(self):
        valid = json.dumps(self.row()).encode() + b"\n"
        invalid_rows = [
            b"{", b"\xff\n", b'{"video":"a","video":"b"}',
            json.dumps(self.row(True)).encode(),
            json.dumps(self.row(-1)).encode(),
            json.dumps(self.row(1.5)).encode(),
            json.dumps(self.row(2**63)).encode(),
            json.dumps(self.row(tracklet_id=None)).encode(),
            json.dumps(self.row(extra="not-allowed")).encode(),
            json.dumps({k: v for k, v in self.row().items() if k != "zone"}).encode(),
        ]
        for invalid in invalid_rows:
            with self.subTest(invalid=invalid[:100]):
                self.source.write_bytes(valid + invalid + b"\n")
                self.assert_rejected(self.replay())

    def test_blank_file_and_blank_lines_are_accepted_without_fabrication(self):
        for content in (b"", b"\n \n\t\n"):
            self.source.write_bytes(content)
            result = self.replay()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
        self.source.write_bytes(b"\n" + json.dumps(self.row()).encode() + b"\n \n")
        result = self.replay()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([json.loads(line) for line in result.stdout.splitlines()], [self.row()])

    def test_missing_source_and_oversized_line_fail_cleanly(self):
        self.assert_rejected(self.replay(self.work / "missing.jsonl"))
        self.source.write_bytes(json.dumps(self.row()).encode() + b"\n" + b" " * 16385)
        self.assert_rejected(self.replay())

    def test_total_input_limit_includes_blank_lines(self):
        # Short whitespace lines individually fit the line cap.
        with self.source.open("wb") as stream:
            block = b" " * 1023 + b"\n"
            for _ in range(65537):
                stream.write(block)
        self.assert_rejected(self.replay())

    def test_replayed_output_ingests_with_legacy_and_tracked_evidence(self):
        rows = [self.row(1000, tracklet_id="track-01"), self.row()]
        self.write_rows(*rows)
        replayed = self.replay()
        self.assertEqual(replayed.returncode, 0, replayed.stderr)
        output = self.work / "replayed.jsonl"
        output.write_text(replayed.stdout, encoding="utf-8")
        db = self.work / "memory.db"
        command = [sys.executable, "-m", "spatialmind", "--db", str(db)]
        result = subprocess.run(command + ["ingest", str(output)], cwd=PROJECT_ROOT,
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"inserted": 2, "unchanged": 0})
        result = subprocess.run(command + ["history", "bottle"], cwd=PROJECT_ROOT,
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), rows[::-1])


if __name__ == "__main__":
    unittest.main()
