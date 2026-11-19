# Optional source-timestamp video reader

`spatialmind.video.VideoReader` reads frames from a trusted local video file.
OpenCV is optional and imported only when the default capture backend opens.
Importing this module or using the JSONL replay/storage paths does not require
OpenCV. No video decoder dependency is installed automatically.

```python
from contextlib import closing
from spatialmind.video import VideoReader

with closing(VideoReader("approved-local-clip.mp4").frames()) as frames:
    for frame in frames:
        print(frame.index, frame.t_ms, frame.image.shape)
        # OpenCV image arrays use its normal BGR channel convention.
```

The file must exist and be a regular file. Camera device IDs and remote-stream
URLs are not supported. A missing optional `cv2` dependency raises
`RuntimeError` when iteration attempts to open a valid file. Missing files
raise `FileNotFoundError`; non-file inputs and decoder-open failures raise
`ValueError`.

Each `SourceFrame` contains a zero-based decode-order `index`, an integer
`t_ms`, and the decoded `image`. It is **not** an object observation: no object
ID, tracklet, label, region, mask or visibility is inferred. The application
makes no network requests or database writes and does not export images. This
code does not sandbox native decoder or filesystem behavior; network-mounted
files are not excluded by the regular-file check.

## Timestamp policy

The default backend asks OpenCV for `CAP_PROP_POS_MSEC` **after** each successful
frame read. This is decoder-reported source-relative time, not wall-clock time.
The first timestamp may be nonzero and is not rebased to zero.

Raw timestamps must be finite, nonnegative numbers below 2**63 milliseconds.
Repeated or regressing timestamps are rejected. Conversion uses **floor**, not
nearest rounding: 10.9 ms becomes 10 ms. The converted integer timestamps must
also strictly increase; 10.1 then 10.9 ms is rejected as an integer-precision
collision even though the raw values increase.

There is no frame-index/FPS fallback, interpolation or silent timestamp repair.
A decoder that reports zero for every frame therefore fails on its second frame.
Timestamp support depends on the OpenCV backend, codec and media. Reported times
are not independently validated presentation timestamps; variable-frame-rate,
reordered and unsupported streams require real-media checks before relying on them.

## Limits and cleanup

The default `max_frames` is 10,000; an explicit value must be an integer between
1 and 1,000,000 (booleans are rejected). Exactly that many frames can succeed
when the following read reports EOF. An additional decoded frame raises
`ValueError`, rather than silently truncating the video. This involves at most
one lookahead frame beyond the limit.

Frames are yielded lazily, so an invalid later timestamp or exceeded limit can
raise after earlier frames have been consumed. The reader does not hold the
whole video in memory. Callers retaining images are responsible for their memory
use. There is no byte, resolution, decode-time or per-frame allocation bound:
a frame-count cap is not a safe codec sandbox. Use approved, trusted local media.

A capture is closed on normal completion, errors and explicit generator close.
Use `contextlib.closing` as shown above when breaking out of iteration early;
`break` alone does not guarantee immediate cleanup. Every new `frames()` call
opens a fresh capture. The default backend releases a capture that fails to open.

OpenCV's failed read is treated as end of input. It can represent either EOF or
a decode failure, so successful iteration does not prove the whole file decoded.
A successful read with missing image data is rejected.

## Offline test backend

A supplied `capture_factory` receives the local path string and returns an
object with `read() -> (success, image)`, `timestamp_ms() -> number` for the
last successful frame, and `close()`. The timestamp method is called only after
a successful read. The backend should release its own resources if its factory
fails before returning. It must supply timestamps in milliseconds.

This interface allows small generated image buffers and controlled source times
to exercise sequencing, validation and cleanup without NumPy, OpenCV, codecs,
network access or model weights. It does not validate actual OpenCV decoding,
color layout, codec compatibility or real-media timestamp correctness. Those
remain unverified until OpenCV and an approved clip are available.
