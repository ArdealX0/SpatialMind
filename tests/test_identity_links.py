"""Supplied tracklet identities remain traceable and recording-scoped."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class IdentityLinkCLITests(unittest.TestCase):
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

    @staticmethod
    def row(t_ms=1000, object_id="bottle", video="bench", **extra):
        return dict(video=video, object_id=object_id, t_ms=t_ms,
                    label="blue bottle", zone="desk", **extra)

    def ingest(self, *rows):
        path = self.work / "input.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return self.cli("ingest", path)

    def assert_counts(self, result, inserted, unchanged):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"inserted": inserted, "unchanged": unchanged})

    def assert_history(self, expected, object_id="bottle", video="bench"):
        result = self.cli("history", object_id, "--video", video)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)

    def snapshot(self):
        with closing(sqlite3.connect(f"{self.db.as_uri()}?mode=ro", uri=True)) as db:
            return list(db.iterdump())

    def assert_conflict(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout.strip(), "")
        self.assertTrue(result.stderr.strip())

    def test_multiple_tracklets_preserve_order_original_ids_and_replay(self):
        first = self.row(1000, tracklet_id="track-1")
        last = self.row(3000, tracklet_id="track-2")
        self.assert_counts(self.ingest(last, first), 2, 0)
        self.assert_history([first, last])
        result = self.cli("last-seen", "bottle", "--video", "bench")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), last)
        before = self.snapshot()
        self.assert_counts(self.ingest(first, last), 0, 2)
        self.assertEqual(self.snapshot(), before)

    def test_tracklet_name_is_scoped_to_recording(self):
        first = self.row(tracklet_id="track-1")
        other = self.row(object_id="different", video="other", tracklet_id="track-1")
        self.assert_counts(self.ingest(first, other), 2, 0)
        self.assert_history([first])
        self.assert_history([other], "different", "other")

    def test_reassignment_rolls_back_fresh_observations_and_links(self):
        first = self.row(tracklet_id="track-1")
        self.assert_counts(self.ingest(first), 1, 0)
        before = self.snapshot()
        fresh = self.row(2000, tracklet_id="track-2")
        wrong = self.row(3000, object_id="different", tracklet_id="track-1")
        self.assert_conflict(self.ingest(fresh, wrong))
        self.assertEqual(self.snapshot(), before)
        # A rolled-back fresh tracklet must remain free for a corrected import.
        retry = self.row(2000, object_id="different", tracklet_id="track-2")
        self.assert_counts(self.ingest(retry), 1, 0)
        self.assert_history([first])
        self.assert_history([retry], "different")

    def test_contradictory_mapping_within_fresh_batch_is_atomic(self):
        self.assert_conflict(self.ingest(self.row(tracklet_id="track-1"),
                                       self.row(2000, object_id="different", tracklet_id="track-1")))
        first = self.row(object_id="different", tracklet_id="track-1")
        self.assert_counts(self.ingest(first), 1, 0)
        self.assert_history([first], "different")
        missing = self.cli("history", "bottle", "--video", "bench")
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(missing.stdout.strip(), "")

    def test_same_observation_key_cannot_change_or_drop_tracklet(self):
        original = self.row(tracklet_id="track-1")
        self.assert_counts(self.ingest(original), 1, 0)
        before = self.snapshot()
        for conflicting in (self.row(tracklet_id="track-2"), self.row()):
            with self.subTest(conflicting=conflicting):
                self.assert_conflict(self.ingest(self.row(2000), conflicting))
                self.assertEqual(self.snapshot(), before)

    def test_existing_legacy_database_migrates_without_rewriting_evidence(self):
        legacy = self.row()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("""CREATE TABLE observations (
                video TEXT NOT NULL, object_id TEXT NOT NULL,
                t_ms INTEGER NOT NULL CHECK(t_ms >= 0), label TEXT NOT NULL,
                zone TEXT NOT NULL, PRIMARY KEY(video, object_id, t_ms)
            ) WITHOUT ROWID""")
            db.execute("INSERT INTO observations VALUES (?,?,?,?,?)",
                       tuple(legacy[k] for k in ("video", "object_id", "t_ms", "label", "zone")))
            db.commit()
        tracked = self.row(2000, tracklet_id="track-1")
        self.assert_counts(self.ingest(tracked, legacy), 1, 1)
        self.assert_history([legacy, tracked])
        before = self.snapshot()
        self.assert_conflict(self.ingest(self.row(tracklet_id="track-2")))
        self.assertEqual(self.snapshot(), before)

    def test_invalid_tracklet_values_are_rejected_atomically(self):
        original = self.row()
        self.assert_counts(self.ingest(original), 1, 0)
        before = self.snapshot()
        for invalid in (None, True, 4, "", "   ", "x" * 513, "bad\nname"):
            with self.subTest(value=invalid):
                self.assert_conflict(self.ingest(self.row(2000), self.row(3000, tracklet_id=invalid)))
                self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
