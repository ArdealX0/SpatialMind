"""Synthetic point-to-observation integration without perception dependencies."""
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import closing

from spatialmind.store import connect, ingest, history, zone_changes
from spatialmind.track_zones import build_observation

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"zones": [
    {"name": "left", "bounds": [0, 0, .5, 1]},
    {"name": "right", "bounds": [.5, 0, 1, 1]},
]}


def point(t=1000, x=.25):
    return dict(video="demo", object_id="bottle", tracklet_id="track_7",
                label="blue bottle", t_ms=t, x=x, y=.4)


class TrackZoneTests(unittest.TestCase):
    def test_synthetic_transition_preserves_evidence_and_inputs(self):
        tracks = [point(1000), point(2000, .75), point(3000, .75)]
        before = copy.deepcopy((tracks, CONFIG))
        rows = [build_observation(row, CONFIG) for row in tracks]
        self.assertEqual((tracks, CONFIG), before)
        with closing(connect(":memory:")) as db:
            ingest(db, io.BytesIO("".join(json.dumps(row)+"\n" for row in rows).encode()))
            self.assertEqual(history(db, "bottle"), rows)
            self.assertEqual(zone_changes(db, "bottle"), [{
                "type": "ZONE_CHANGED", "video": "demo", "object_id": "bottle",
                "from_zone": "left", "to_zone": "right",
                "before_t_ms": 1000, "after_t_ms": 2000, "confirmed_t_ms": 3000,
            }])

    def test_edges_missing_outside_and_overlap(self):
        for x, expected in ((0, "left"), (.5, "right"), (1, "right"), (-.1, "unknown")):
            self.assertEqual(build_observation(point(x=x), CONFIG)["zone"], expected)
        track = point()
        del track["x"], track["y"], track["tracklet_id"]
        self.assertEqual(set(build_observation(track, CONFIG)),
                         {"video", "object_id", "label", "t_ms", "zone"})
        self.assertEqual(build_observation(track, CONFIG)["zone"], "unknown")
        overlap = {"zones": CONFIG["zones"] + [{"name": "all", "bounds": [0, 0, 1, 1]}]}
        self.assertEqual(build_observation(point(), overlap)["zone"], "unknown")

    def test_unknown_breaks_chain_and_same_labels_do_not_merge(self):
        unknown = point(2000)
        del unknown["x"], unknown["y"]
        other = dict(point(1500, .75), object_id="other", tracklet_id="other_track")
        records = [point(1000), unknown, point(3000, .75), point(4000, .75), other]
        rows = [build_observation(row, CONFIG) for row in records]
        with closing(connect(":memory:")) as db:
            ingest(db, io.BytesIO("".join(json.dumps(row)+"\n" for row in rows).encode()))
            self.assertEqual(zone_changes(db, "bottle"), [])
            self.assertEqual([row["t_ms"] for row in history(db, "bottle")],
                             [1000, 2000, 3000, 4000])
            self.assertEqual(history(db, "other"), [rows[-1]])

    def test_invalid_fields_coordinates_and_config(self):
        invalid = [
            dict(point(), zone="override"), dict(point(), x=None, y=None),
            dict(point(), x=True), dict(point(), x=float("nan")),
            dict(point(), y=float("inf")), dict(point(), t_ms=True),
            dict(point(), tracklet_id=None), dict(point(), label=""),
        ]
        partial = point()
        del partial["y"]
        invalid.append(partial)
        for record in invalid:
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    build_observation(record, CONFIG)
        with self.assertRaises(ValueError):
            build_observation(point(), {"zones": [{"name": "bad", "bounds": [1, 0, 0, 1]}]})

    def test_cli_success_and_invalid_input_have_no_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, record = Path(tmp)/"zones.json", Path(tmp)/"point.json"
            config.write_text(json.dumps(CONFIG))
            cmd = [sys.executable, "-S", "-m", "spatialmind.track_zones", str(config), str(record)]
            record.write_text(json.dumps(point()))
            run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout), build_observation(point(), CONFIG))
            for raw in (b'{"video":"one","video":"two"}', b"{}\n{}", b" "*16385, b"\xff"):
                record.write_bytes(raw)
                run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=10)
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, "")
                self.assertTrue(run.stderr)


if __name__ == "__main__":
    unittest.main()
