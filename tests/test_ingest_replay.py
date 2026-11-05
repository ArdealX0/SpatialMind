"""CLI replay and conflict recovery preserve complete observation histories."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("video", "object_id", "t_ms", "label", "zone")


class IngestReplayTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.db = self.work / "memory.db"

    @staticmethod
    def row(t_ms=1000, **changes):
        row = dict(video="bench.mp4", object_id="bottle-01", t_ms=t_ms,
                   label="blue bottle", zone="desk")
        row.update(changes)
        return row

    def import_file(self, path):
        return subprocess.run(
            [sys.executable, "-m", "spatialmind", "--db", str(self.db),
             "ingest", str(path)],
            cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=15,
        )

    def ingest(self, *rows):
        path = self.work / "batch.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows),
                        encoding="utf-8")
        return self.import_file(path)

    def snapshot(self):
        with closing(sqlite3.connect(f"{self.db.as_uri()}?mode=ro", uri=True)) as db:
            return db.execute(
                "SELECT video, object_id, t_ms, label, zone FROM observations "
                "ORDER BY video, object_id, t_ms"
            ).fetchall()

    def assert_rows(self, *rows):
        expected = sorted(tuple(row[field] for field in FIELDS) for row in rows)
        self.assertEqual(self.snapshot(), expected)

    def assert_counts(self, result, inserted, unchanged):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         {"inserted": inserted, "unchanged": unchanged})

    def assert_conflict(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout.strip(), "")
        self.assertTrue(result.stderr.strip())

    def test_replaying_fixture_in_new_process_preserves_every_record(self):
        fixture = PROJECT_ROOT / "examples" / "workbench.jsonl"
        rows = [json.loads(line) for line in fixture.read_text().splitlines() if line.strip()]
        self.assert_counts(self.import_file(fixture), len(rows), 0)
        self.assert_rows(*rows)
        before = self.snapshot()
        self.assert_counts(self.import_file(fixture), 0, len(rows))
        self.assertEqual(self.snapshot(), before)

    def test_identical_duplicates_in_one_batch_are_counted_once(self):
        row = self.row()
        self.assert_counts(self.ingest(row, row, row), 1, 2)
        self.assert_rows(row)

    def test_mixed_existing_new_and_repeated_rows_have_exact_counts(self):
        existing = self.row()
        fresh = self.row(2000, zone="shelf")
        other = self.row(500, object_id="meter-01", label="multimeter")
        self.assert_counts(self.ingest(existing), 1, 0)
        self.assert_counts(self.ingest(existing, fresh, fresh, other, existing), 2, 3)
        self.assert_rows(existing, fresh, other)

    def test_changed_existing_label_or_zone_rolls_back_all_new_rows(self):
        original = self.row()
        later = self.row(4000, zone="shelf")
        self.assert_counts(self.ingest(original, later), 2, 0)
        before = self.snapshot()
        for field, changed in (("label", "red bottle"), ("zone", "drawer")):
            with self.subTest(field=field):
                conflict = dict(original, **{field: changed})
                result = self.ingest(
                    self.row(2000), self.row(1000, object_id="fresh-object"), conflict,
                )
                self.assert_conflict(result)
                self.assertEqual(self.snapshot(), before)

    def test_contradictory_duplicates_in_fresh_batch_leave_no_records(self):
        original = self.row()
        self.assert_conflict(self.ingest(original, self.row(zone="shelf")))
        self.assert_rows()

    def test_corrected_retry_succeeds_after_failed_batch(self):
        original = self.row()
        fresh = self.row(2000, zone="shelf")
        self.assert_counts(self.ingest(original), 1, 0)
        before = self.snapshot()
        self.assert_conflict(self.ingest(fresh, self.row(label="red bottle")))
        self.assertEqual(self.snapshot(), before)
        self.assert_counts(self.ingest(fresh, original), 1, 1)
        self.assert_rows(original, fresh)


if __name__ == "__main__":
    unittest.main()
