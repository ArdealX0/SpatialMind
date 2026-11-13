"""Synthetic caller-authored scenarios exercise conservative memory behavior."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = PROJECT_ROOT / "examples"


class OcclusionScenarioTests(unittest.TestCase):
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

    def query(self, command, object_id, video, *options):
        result = self.cli(command, object_id, "--video", video, *options)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def import_fixture(self, name):
        path = EXAMPLES / name
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        result = self.cli("ingest", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"inserted": len(rows), "unchanged": 0})
        return rows

    def snapshot(self):
        with closing(sqlite3.connect(f"{self.db.as_uri()}?mode=ro", uri=True)) as db:
            return list(db.iterdump())

    def test_unknown_and_long_gap_do_not_create_zone_changes(self):
        rows = self.import_fixture("synthetic_occlusion.jsonl")
        history = self.query("history", "bottle_01", "occlusion_demo")
        self.assertEqual(history, rows)
        self.assertEqual([r["t_ms"] for r in history],
                         [0, 1000, 2000, 3000, 4000, 64000, 65000])
        self.assertEqual([r["zone"] for r in history],
                         ["desk", "desk", "unknown", "shelf", "shelf", "drawer", "drawer"])
        self.assertEqual({r["tracklet_id"] for r in history},
                         {"track_before", "track_after_short", "track_after_long"})
        self.assertEqual(self.query("zone-changes", "bottle_01", "occlusion_demo"), [])
        self.assertEqual(self.query("last-seen", "bottle_01", "occlusion_demo"), rows[-1])
        # A future query window is not evidence of a removal event.
        before = self.snapshot()
        self.assertEqual(self.query("zone-changes", "bottle_01", "occlusion_demo",
                                    "--start-ms", 100000), [])
        self.assertEqual(self.snapshot(), before)

    def test_identical_labels_never_merge_unresolved_track_into_candidates(self):
        rows = self.import_fixture("synthetic_lookalikes.jsonl")
        self.assertEqual({r["label"] for r in rows}, {"blue bottle"})
        self.assertEqual({r["object_id"] for r in rows},
                         {"bottle_left", "bottle_right", "unresolved_01"})
        before = self.snapshot()
        for object_id in ("bottle_left", "bottle_right", "unresolved_01"):
            expected = [r for r in rows if r["object_id"] == object_id]
            with self.subTest(object_id=object_id):
                self.assertEqual(self.query("history", object_id, "lookalike_demo"), expected)
                self.assertEqual(self.query("last-seen", object_id, "lookalike_demo"), expected[-1])
                self.assertEqual(self.query("zone-changes", object_id, "lookalike_demo"), [])
        # Later evidence for an unresolved object leaves both old sightings intact.
        for object_id in ("bottle_left", "bottle_right"):
            self.assertEqual(self.query("last-seen", object_id, "lookalike_demo")["t_ms"], 1000)
        result = self.cli("ingest", EXAMPLES / "synthetic_lookalikes.jsonl")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"inserted": 0, "unchanged": 6})
        self.assertEqual(self.snapshot(), before)

    def test_manifest_ambiguity_is_authored_annotation_and_matches_fixtures(self):
        manifest = json.loads((EXAMPLES / "scenario_expectations.json").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertIn("human-authored", manifest["provenance"])
        self.assertIn("not model output", manifest["provenance"])
        scenarios = {scenario["id"]: scenario for scenario in manifest["scenarios"]}
        occlusion = scenarios["occlusion"]
        rows = self.import_fixture(occlusion["fixture"])
        self.assertEqual(occlusion["identity_status"], "caller-supplied")
        self.assertEqual(occlusion["expected_history_t_ms"], [r["t_ms"] for r in rows])
        self.assertEqual(occlusion["expected_tracklet_ids"], [r["tracklet_id"] for r in rows])
        self.assertEqual(self.query("last-seen", occlusion["object_id"], occlusion["video"]),
                         occlusion["expected_last_seen"])
        self.assertEqual(self.query("zone-changes", occlusion["object_id"], occlusion["video"]),
                         occlusion["expected_zone_changes"])
        lookalikes = scenarios["lookalikes"]
        self.import_fixture(lookalikes["fixture"])
        self.assertEqual(lookalikes["identity_status"], "ambiguous")
        self.assertEqual(set(lookalikes["candidate_object_ids"]), {"bottle_left", "bottle_right"})
        unresolved_id = lookalikes["unresolved_object_id"]
        self.assertNotIn(unresolved_id, lookalikes["candidate_object_ids"])
        unresolved = self.query("history", unresolved_id, lookalikes["video"])
        self.assertEqual([r["t_ms"] for r in unresolved],
                         lookalikes["expected_unresolved_history_t_ms"])
        self.assertEqual({r["tracklet_id"] for r in unresolved},
                         {lookalikes["unresolved_tracklet_id"]})
        for object_id in lookalikes["candidate_object_ids"]:
            self.assertEqual(self.query("last-seen", object_id, lookalikes["video"])["t_ms"],
                             lookalikes["expected_candidate_last_seen_t_ms"])
        for object_id, expected in lookalikes["expected_zone_changes_per_object"].items():
            self.assertEqual(self.query("zone-changes", object_id, lookalikes["video"]), expected)


if __name__ == "__main__":
    unittest.main()
