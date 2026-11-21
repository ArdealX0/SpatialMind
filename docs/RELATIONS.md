# Temporal image-space LEFT_OF

This standalone CPU helper derives intervals for one selected pair of objects
from supplied normalized positions. It does not read images, estimate depth or
modify stored observations. The current SQLite schema does not store x/y, so this
is a separate bounded position-stream interface.

```sh
python -m spatialmind.relation_intervals examples/left_of_samples.jsonl --video relation_demo --subject bottle --object laptop --end-ms 10000
```

The example yields [1000, 6000) and [7000, 8000). The laptop sighting at 1000
expires at 6000 even though the bottle was refreshed. Both objects are refreshed
at 7000, reopening the relation. The coordinate-less bottle signal at 8000 closes
it immediately. No interval bridges the stale gap.

## Input and interpretation

Each JSONL sample has exactly video, object_id and t_ms, with optional **paired**
x/y. IDs are nonempty printable text up to 512 characters. Time is a nonnegative
integer below 2**63 in video-relative milliseconds; booleans and floats are
rejected. Coordinates, if supplied, are finite numbers in [0,1], excluding
booleans and null. A sample omitting both coordinates explicitly clears the
object's position; it does not establish why the position is unavailable or
whether the object was removed.

Source order may be arbitrary. Samples are sorted and all changes at the same
timestamp are applied together before checking the relation. Duplicate
(video,object_id,t_ms) samples are rejected even if identical. Other objects and
videos are validated but excluded from the selected pair. The selected objects
must have distinct IDs in one recording; no cross-video clock comparison occurs.

The subject is LEFT_OF the object when subject.x < object.x and both positions
are fresh. Equal x gives no direction. Reversing their positions closes this
directed relation; query the opposite pair separately for the reverse direction.

## Freshness, horizon and query

`--max-age-ms` defaults to 5000 and accepts integers from 1 through 60000.
A position at time t is held only over [t, t+max_age_ms). This is a configurable
freshness assumption, not proof of continuous observation. At exact expiry it
is stale; a relation closes when **either** position expires, even if no later
sample arrives. Refreshes at the same instant may maintain a contiguous interval
because no positive-duration stale gap remains.

`--end-ms` is a required exclusive query horizon. All intervals are clipped
there; samples at or after it cannot affect the result. The horizon is a
nonnegative integer below 2**63. A zero horizon returns no intervals.
Intervals are half-open [start_ms,end_ms), and contiguous true segments coalesce.

`--at-ms T` returns only derived intervals satisfying start_ms <= T < end_ms.
It uses no future position to infer the relation at T. The returned interval can
extend beyond T because it describes the complete bounded history, not an
online forecast of the endpoint. Queries at or beyond the exclusive horizon
return no intervals.

```python
from spatialmind.relation_intervals import left_of_intervals
intervals = left_of_intervals(samples, "demo", "bottle", "laptop",
                             end_ms=10000, max_age_ms=5000, at_ms=2000)
```

Results contain video, subject_id, predicate, object_id, start_ms and end_ms.
The original position stream remains the supporting evidence; this API does not
persist evidence pointers or assign permanent relation IDs.

## Validation and limitations

The API accepts at most 10,000 samples, computes only the requested directed
pair, and validates settings before consuming input. It returns a complete
list, never partial results on error. Input dictionaries are not mutated.
Both CLI and API validate the entire supplied stream, including samples outside
the selected recording/horizon. Thus malformed future or unrelated input can
reject the request but cannot influence a valid interval.

The CLI caps input at 1 MiB and lines at 16,384 bytes, including whitespace and
line endings. Duplicate JSON keys, missing/extra fields, partial coordinates,
invalid UTF-8 and unreadable files fail with exit 2, stderr and no JSON result.
Successful empty results return [] and exit 0. The API's sample cap applies to
an iterable; already allocated caller memory is outside its control.

Coordinates are comparable fixed-camera image points. There is no camera-motion
compensation, physical 3D relation, visibility inference or occlusion model.
Unknown positions and expired positions simply make this relation unsupported.
