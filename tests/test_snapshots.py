"""Video-scoped source-time snapshots retain supported evidence only."""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spatialmind.store import connect, ingest, snapshot

ROOT = Path(__file__).resolve().parents[1]


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        self.addCleanup(self.db.close)
        with (ROOT/"examples/snapshot_samples.jsonl").open("rb") as stream:
            ingest(self.db, stream)

    def test_before_after_order_scope_unknown_and_source_fields(self):
        before = snapshot(self.db, "snapshot_demo", 2500)
        after = snapshot(self.db, "snapshot_demo", 3000)
        self.assertEqual(before["semantics"], "last_observed")
        self.assertEqual([entry["observation"]["object_id"] for entry in before["objects"]], ["bottle", "mug"])
        bottle, mug = before["objects"]
        self.assertEqual(bottle["age_ms"], 1500)
        self.assertEqual(bottle["observation"]["zone"], "desk")
        self.assertEqual(bottle["observation"]["tracklet_id"], "track_before")
        self.assertEqual(mug["observation"]["zone"], "unknown")
        self.assertNotIn("tracklet_id", mug["observation"])
        self.assertEqual(after["objects"][0]["observation"]["zone"], "shelf")
        self.assertEqual(after["objects"][0]["age_ms"], 0)
        self.assertEqual(after["objects"][0]["observation"]["tracklet_id"], "track_after")
        self.assertEqual(snapshot(self.db, "another_recording", 2500)["objects"][0]["observation"]["zone"], "drawer")

    def test_no_future_leakage_and_backfill_semantics(self):
        before = snapshot(self.db, "snapshot_demo", 2500)
        future = dict(video="snapshot_demo", object_id="bottle", t_ms=10000, label="future label",
                      zone="future zone", tracklet_id="future track")
        ingest(self.db, io.BytesIO((json.dumps(future)+"\n").encode()))
        self.assertEqual(snapshot(self.db, "snapshot_demo", 2500), before)
        self.assertEqual(snapshot(self.db, "snapshot_demo", 999)["objects"], [])
        self.assertEqual(snapshot(self.db, "absent", 2500)["objects"], [])
        backfill = dict(video="snapshot_demo", object_id="bottle", t_ms=2400, label="blue bottle", zone="bench")
        ingest(self.db, io.BytesIO((json.dumps(backfill)+"\n").encode()))
        self.assertEqual(snapshot(self.db, "snapshot_demo", 2500)["objects"][0]["observation"]["zone"], "bench")

    def test_validation_cap_and_no_mutation(self):
        before = list(self.db.iterdump())
        for video, at in (("", 1), ("demo", True), ("demo", -1), ("demo", 1.2), ("demo", 2**63)):
            with self.assertRaises(ValueError):
                snapshot(self.db, video, at)
        with patch("spatialmind.store.MAX_SNAPSHOT_OBJECTS", 1):
            with self.assertRaises(ValueError):
                snapshot(self.db, "snapshot_demo", 5000)
            self.assertEqual(len(snapshot(self.db, "another_recording", 5000)["objects"]), 1)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_cli_valid_and_invalid_before_db_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/"scene.sqlite"
            base = [sys.executable, "-S", "-m", "spatialmind", "--db", str(db)]
            for at in ("-1", "1.2", str(2**63)):
                result = subprocess.run(base+["snapshot","--video","demo","--at-ms",at],
                                        cwd=ROOT,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,2)
                self.assertEqual(result.stdout,"")
                self.assertFalse(db.exists())
            result = subprocess.run(base+["ingest","examples/snapshot_samples.jsonl"],
                                    cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            result = subprocess.run(base+["snapshot","--video","snapshot_demo","--at-ms","2500"],
                                    cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),snapshot(self.db,"snapshot_demo",2500))


if __name__ == "__main__":
    unittest.main()
