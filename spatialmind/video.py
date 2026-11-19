"""Optional local-video decoding with decoder-provided source timestamps."""
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol


class CaptureBackend(Protocol):
    """A backend owns its capture and reports time for the last decoded frame."""

    def read(self) -> tuple[bool, Any]: ...
    def timestamp_ms(self) -> float: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class SourceFrame:
    index: int
    t_ms: int
    image: Any


class _OpenCVCapture:
    def __init__(self, path: str):
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("video decoding requires optional OpenCV (cv2)") from exc
        self._capture = cv2.VideoCapture(path)
        self._time_property = cv2.CAP_PROP_POS_MSEC
        if not self._capture.isOpened():
            self._capture.release()
            raise ValueError("video could not be opened by OpenCV")

    def read(self):
        return self._capture.read()

    def timestamp_ms(self):
        return self._capture.get(self._time_property)

    def close(self):
        self._capture.release()


class VideoReader:
    """Read trusted local video, without synthesizing times or observations."""

    def __init__(self, path, *, capture_factory: Callable[[str], CaptureBackend] | None = None,
                 max_frames=10000):
        if type(max_frames) is not int or not 1 <= max_frames <= 1_000_000:
            raise ValueError("max_frames must be an integer from 1 to 1000000")
        self.path = Path(path)
        self.capture_factory = capture_factory if capture_factory is not None else _OpenCVCapture
        self.max_frames = max_frames

    def frames(self) -> Iterator[SourceFrame]:
        """Yield frames lazily; close this iterator explicitly if stopping early."""
        if not self.path.exists():
            raise FileNotFoundError("video file does not exist")
        if not self.path.is_file():
            raise ValueError("video input must be a local regular file")
        capture = self.capture_factory(str(self.path))
        previous_source = previous_ms = None
        index = 0
        try:
            while True:
                ok, image = capture.read()
                if not ok:
                    return
                if index >= self.max_frames:
                    raise ValueError("video exceeds max_frames")
                if image is None:
                    raise ValueError("backend returned a successful frame without image data")
                source_ms = capture.timestamp_ms()
                if type(source_ms) not in (int, float):
                    raise ValueError("source timestamp must be a finite number")
                try:
                    finite = math.isfinite(source_ms)
                except OverflowError:
                    finite = False
                if not finite or not 0 <= source_ms < 2**63:
                    raise ValueError("source timestamp must be finite, nonnegative and below 2**63 ms")
                t_ms = math.floor(source_ms)
                if previous_source is not None and source_ms <= previous_source:
                    raise ValueError("source timestamps must strictly increase")
                if previous_ms is not None and t_ms <= previous_ms:
                    raise ValueError("timestamps collide at integer-millisecond precision")
                previous_source, previous_ms = source_ms, t_ms
                yield SourceFrame(index=index, t_ms=t_ms, image=image)
                index += 1
        finally:
            capture.close()
