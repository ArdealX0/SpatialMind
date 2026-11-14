"""Synthetic decoder tests for source timestamps and deterministic cleanup."""
import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeCapture:
    def __init__(self, timestamps, images=None, failure=None):
        self.timestamps = timestamps
        self.images = images if images is not None else [
            [[index, index + 1]] for index in range(len(timestamps))
        ]
        self.failure = failure
        self.position = -1
        self.closed = 0

    def read(self):
        if self.failure is not None:
            raise self.failure
        self.position += 1
        if self.position >= len(self.timestamps):
            return False, None
        return True, self.images[self.position]

    def timestamp_ms(self):
        return self.timestamps[self.position]

    def close(self):
        self.closed += 1


class VideoReaderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "synthetic.video"
        self.path.write_bytes(b"fake decoder input")
        self.module = importlib.import_module("spatialmind.video")

    def reader(self, capture, **options):
        def factory(path):
            self.assertEqual(path, str(self.path))
            return capture
        return self.module.VideoReader(self.path, capture_factory=factory, **options)

    def test_floors_source_time_and_preserves_generated_frames(self):
        capture = FakeCapture([0, 33.4, 66.8])
        frames = list(self.reader(capture).frames())
        self.assertEqual([frame.index for frame in frames], [0, 1, 2])
        self.assertEqual([frame.t_ms for frame in frames], [0, 33, 66])
        for index, frame in enumerate(frames):
            self.assertIs(frame.image, capture.images[index])
        self.assertEqual(capture.closed, 1)

    def test_invalid_repeated_decreasing_and_colliding_timestamps_close(self):
        for timestamps in ([0, 0], [10, 9], [.1, .2], [1.9, 1.8],
                           [-1], [float("nan")], [float("inf")], [True], [2**63]):
            with self.subTest(timestamps=timestamps):
                capture = FakeCapture(timestamps)
                with self.assertRaises(ValueError):
                    list(self.reader(capture).frames())
                self.assertEqual(capture.closed, 1)

    def test_empty_eof_and_explicit_early_close_release_backend(self):
        empty = FakeCapture([])
        self.assertEqual(list(self.reader(empty).frames()), [])
        self.assertEqual(empty.closed, 1)
        capture = FakeCapture([0, 100])
        iterator = self.reader(capture).frames()
        self.assertEqual(next(iterator).t_ms, 0)
        iterator.close()
        self.assertEqual(capture.closed, 1)

    def test_read_error_and_empty_successful_frame_release_backend(self):
        failed = FakeCapture([0], failure=RuntimeError("synthetic decoder failure"))
        with self.assertRaises(Exception):
            list(self.reader(failed).frames())
        self.assertEqual(failed.closed, 1)
        missing = FakeCapture([0], images=[None])
        with self.assertRaises(ValueError):
            list(self.reader(missing).frames())
        self.assertEqual(missing.closed, 1)

    def test_exact_frame_cap_succeeds_but_extra_frame_is_error(self):
        exact = FakeCapture([0, 100])
        self.assertEqual(len(list(self.reader(exact, max_frames=2).frames())), 2)
        self.assertEqual(exact.closed, 1)
        extra = FakeCapture([0, 100, 200])
        with self.assertRaises(ValueError):
            list(self.reader(extra, max_frames=2).frames())
        self.assertEqual(extra.closed, 1)

    def test_invalid_limits_and_sources_do_not_open_backend(self):
        opened = []
        def factory(path):
            opened.append(path)
            return FakeCapture([])
        for cap in (0, -1, True, 1.5):
            with self.subTest(cap=cap):
                with self.assertRaises(ValueError):
                    list(self.module.VideoReader(self.path, capture_factory=factory,
                                                 max_frames=cap).frames())
        for source in (self.path.parent, self.path.parent / "missing.video",
                       "https://example.invalid/video.mp4"):
            with self.subTest(source=source):
                with self.assertRaises((ValueError, OSError)):
                    list(self.module.VideoReader(source, capture_factory=factory).frames())
        self.assertEqual(opened, [])

    def test_package_and_reader_import_without_opencv_or_site_packages(self):
        code = """
import importlib.abc
import sys
class RejectCV2(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'cv2' or fullname.startswith('cv2.'):
            raise AssertionError('OpenCV import must be deferred')
sys.meta_path.insert(0, RejectCV2())
import spatialmind
import spatialmind.video
"""
        result = subprocess.run([sys.executable, "-S", "-c", code], cwd=PROJECT_ROOT,
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
