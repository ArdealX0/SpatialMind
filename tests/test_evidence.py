"""Read-only local HTML rendering of timestamped, registered evidence."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EvidencePageCLITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.db = self.work / "memory.db"
        self.media_root = self.work / "media"
        self.media_root.mkdir()
        self.media = self.media_root / "bench clip.mp4"
        self.media.write_bytes(b"placeholder media")
        self.manifest = self.work / "videos.json"
        self.write_manifest({"bench": "bench clip.mp4"})

    def cli(self, db=None, manifest=None, video="bench", object_id="bottle-01"):
        return subprocess.run(
            [sys.executable, "-m", "spatialmind.evidence", "--db", str(db or self.db),
             "--media-root", str(self.media_root), "--manifest", str(manifest or self.manifest),
             "--video", video, "--object-id", object_id],
            cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=15,
        )

    def write_manifest(self, value):
        if isinstance(value, str):
            self.manifest.write_text(value, encoding="utf-8")
        else:
            self.manifest.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def row(object_id="bottle-01", t_ms=12345, **extra):
        row = dict(video="bench", object_id=object_id, t_ms=t_ms,
                   label="blue bottle", zone="desk")
        row.update(extra)
        return row

    def ingest(self, *rows):
        source = self.work / "observations.jsonl"
        source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "spatialmind", "--db", str(self.db), "ingest", str(source)],
            cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def db_snapshot(self):
        with closing(sqlite3.connect(f"{self.db.as_uri()}?mode=ro", uri=True)) as db:
            return list(db.iterdump())

    def test_page_uses_registered_file_uri_source_time_and_escaped_tracklet_metadata(self):
        malicious = '<b> & " bottle'
        row = self.row(label=malicious, tracklet_id="track-7")
        self.ingest(row)
        before = self.db_snapshot()

        result = self.cli()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn(f'src="{self.media.as_uri()}#t=12.345"', result.stdout)
        self.assertIn("const sourceTimeMs = 12345;", result.stdout)
        self.assertIn("track-7", result.stdout)
        self.assertIn("&lt;b&gt; &amp; &quot; bottle", result.stdout)
        self.assertNotIn("<b> & \" bottle", result.stdout)
        self.assertEqual(self.db_snapshot(), before)

    def test_missing_sighting_is_clear_and_has_no_video_player(self):
        self.ingest(self.row(object_id="another-object"))
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No recorded observation was found", result.stdout)
        self.assertNotIn("<video", result.stdout)

    def test_unknown_registration_and_missing_media_fail_without_partial_stdout(self):
        self.ingest(self.row())
        unknown = self.cli(video="other-video")
        self.assertEqual(unknown.returncode, 2)
        self.assertEqual(unknown.stdout, "")
        self.assertTrue(unknown.stderr.strip())

        self.write_manifest({"bench": "absent.mp4"})
        absent = self.cli()
        self.assertEqual(absent.returncode, 2)
        self.assertEqual(absent.stdout, "")
        self.assertTrue(absent.stderr.strip())

    def test_manifest_rejects_duplicate_keys_unknown_types_and_size_or_count_overflow(self):
        self.ingest(self.row())
        invalid_manifests = [
            '{"bench":"bench clip.mp4","bench":"bench clip.mp4"}',
            "[]", '"bench clip.mp4"', '{"bench":7}', '{"bench":null}',
            "{}", json.dumps({f"video-{i}": "bench clip.mp4" for i in range(257)}),
            " " * 65537,
        ]
        for text in invalid_manifests:
            with self.subTest(manifest_prefix=text[:50]):
                self.write_manifest(text)
                result = self.cli()
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.strip())

    def test_manifest_rejects_absolute_traversal_and_symlink_escape_paths(self):
        self.ingest(self.row())
        outside_dir = self.work / "outside"
        outside_dir.mkdir()
        outside = outside_dir / "secret.mp4"
        outside.write_bytes(b"private")
        link = self.media_root / "linked.mp4"
        try:
            link.symlink_to(outside)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        for unsafe in (str(outside), "../outside/secret.mp4", "linked.mp4"):
            with self.subTest(path=unsafe):
                self.write_manifest({"bench": unsafe})
                result = self.cli()
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_sql_like_identifier_is_literal_and_unknown_identifier_is_not_a_query(self):
        literal = "x' OR 1=1 --"
        self.ingest(self.row(object_id="other", t_ms=90000), self.row(object_id=literal, t_ms=2345))
        result = self.cli(object_id=literal)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("#t=2.345", result.stdout)
        self.assertIn("x&#x27; OR 1=1 --", result.stdout)
        self.assertNotIn(literal, result.stdout)
        missing = self.cli(object_id="missing")
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertIn("No recorded observation was found", missing.stdout)
        self.assertNotIn("<video", missing.stdout)

    def test_subsecond_timestamp_is_kept_in_the_video_fragment(self):
        self.ingest(self.row(t_ms=1))
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'src="{self.media.as_uri()}#t=0.001"', result.stdout)
        self.assertIn("const sourceTimeMs = 1;", result.stdout)

    def test_maximum_signed_sqlite_timestamp_fragment_is_formatted_exactly(self):
        max_sqlite_integer = 2**63 - 1
        self.ingest(self.row(t_ms=max_sqlite_integer))
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'src="{self.media.as_uri()}#t=9223372036854775.807"', result.stdout)

    def test_missing_database_is_not_created_and_fails_without_page_output(self):
        missing_db = self.work / "does-not-exist.db"
        result = self.cli(db=missing_db)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertFalse(missing_db.exists())


if __name__ == "__main__":
    unittest.main()
