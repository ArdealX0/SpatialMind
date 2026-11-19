# Supplied track points to zone observations

This CPU-only bridge combines the existing rectangle classifier and observation
validator. It converts one supplied track point into an ingestible observation.
It does not detect objects, decode video, associate identities or decide visibility.
Only call it for an observation you intend to record; silence produces no record.

## One-record CLI

From the repository root:

```sh
python -m spatialmind.track_zones examples/workbench_zones.json examples/track_point.json > observation.jsonl
python -m spatialmind --db points.sqlite ingest observation.jsonl
```

Continue to ingestion only if the first command exits 0. The example emits the
original video/object/tracklet/label/time fields plus `"zone":"desk-left"`.
Coordinates are not retained in the current observation schema.

The input is exactly one UTF-8 JSON object, capped at 16,384 bytes including
whitespace. Multiple objects, duplicate JSON keys, invalid UTF-8, extra fields,
invalid metadata or coordinates, and unreadable files exit 2 with stderr and no
JSON output. Config limits remain 64 KiB and 100 rectangles. No database is
opened by this bridge; `ingest` separately enforces replay and identity conflicts.

## Python API

```python
from spatialmind.track_zones import build_observation

config = {"zones": [
    {"name": "left", "bounds": [0, 0, 0.5, 1]},
    {"name": "right", "bounds": [0.5, 0, 1, 1]}
]}
track = {"video": "demo", "object_id": "bottle", "label": "blue bottle",
         "t_ms": 1000, "tracklet_id": "track_1", "x": 0.25, "y": 0.4}
observation = build_observation(track, config)
```

The `zones` argument is the full config dictionary containing `zones`, not a
bare rectangle list. Both config and record are validated without mutation.
The required record fields are `video`, `object_id`, `label` and `t_ms`.
`tracklet_id` is optional. `x` and `y` must be supplied together or both
omitted. No other field, including an existing `zone`, is accepted.

Metadata validation shares merged `store._parse` so ID/string/timestamp rules
remain identical to ingestion. No pending adapter or public-parser module is
required. Output has the five required observation fields and retains
`tracklet_id` only if supplied. IDs and timestamps are not synthesized, rebased,
or replaced.

Coordinates follow [the zone convention](ZONES.md): normalized top-left origin,
x rightward and y downward. Supplied coordinates must be finite numbers;
booleans and explicit nulls are invalid. Missing both coordinates, points outside
the image, uncovered points and multiple matching regions produce `unknown`.
Shared edges belong to the rectangle beginning at that edge, except the image's
outer edge is included. Unknown denotes unresolved location, not invisibility or
removal. The API validates schema and config but the file-size limit applies to
the CLI input, not already allocated Python objects.

## Synthetic acceptance and limits

With the left/right config above, supplied points at 1,000 ms x=0.25, 2,000 ms
x=0.75 and 3,000 ms x=0.75 produce left/right/right observations. After ingestion,
default zone-change querying yields one event with before=1,000, after=2,000 and
confirmed=3,000 ms. This checks coordinate classification, preserved identity,
source-time evidence and the existing debounce rule.

These are synthetic supplied points, not measured camera tracking results.
Pixel-to-normalized conversion and point selection (for example a mask centroid)
belong to the caller. Use the correct fixed-camera config for the recording:
the bridge does not persist config versions, bind configs to recordings, or
recover discarded coordinates. Real-clip agreement remains unverified.
