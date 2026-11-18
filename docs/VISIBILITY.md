# Explicit missing and reobserved signals

This standalone CPU module derives visibility transitions from supplied signals.
It does not infer missingness from silence, timeouts, wall-clock time, an unknown
zone, or video pixels. A producer must explicitly say whether a tracked object
is `visible` or `missing` at a source-video timestamp.

```sh
python -m spatialmind.visibility examples/visibility_samples.jsonl
```

The input is JSONL; successful output is **one JSON array** of events, not JSONL.
The synthetic example yields two events: MISSING at 2,000 ms and REOBSERVED at
3,000 ms. Repeated missing and visible samples produce no extra events.

## Sample and event contract

Every sample contains exactly `video`, `object_id`, `state`, `t_ms`, and
optionally `tracklet_id`. State is exactly `visible` or `missing`.
Strings follow nonempty printable-text limits of 512 characters. Timestamp is
an integer from 0 through 9,223,372,036,854,775,807 in video-relative milliseconds;
booleans, floats, nulls and numeric strings are rejected. Optional tracklet IDs
must be strings when present; null is not accepted.

Each recording/object pair must start with a visible sample. Timestamps must
strictly increase within that pair; repeated timestamps are invalid even for
identical samples. Different objects or recordings may be interleaved in any
global time order. Identity is caller-supplied; equal labels or tracklet strings
never merge objects. A new tracklet does not itself create an event.

Each event contains `type`, `video`, `object_id`, `before` and `after`.
The nested before/after values are complete source samples preserving optional
tracklet IDs. The example's first event is:

```json
{
  "type": "MISSING",
  "video": "visibility_demo",
  "object_id": "bottle_01",
  "before": {"video":"visibility_demo","object_id":"bottle_01","state":"visible","t_ms":1000,"tracklet_id":"track_7"},
  "after": {"video":"visibility_demo","object_id":"bottle_01","state":"missing","t_ms":2000}
}
```

The REOBSERVED event uses the most recent missing sample (2,500 ms) as before,
and the visible sample (3,000 ms, track_19) as after. Repeated states update the
previous evidence even though they do not emit events. Thus before is not
necessarily when the preceding state first began. Events retain input encounter
order; times from different videos are not globally comparable.

MISSING means the producer explicitly reported no visibility. It does not prove
physical removal, departure, or an occlusion cause. REOBSERVED expresses the
supplied session identity; it is not learned re-identification. No motion event,
distance, zone transition, or probability is fabricated.

## Python API and limits

```python
from spatialmind.visibility import visibility_events
events = visibility_events(samples)
```

The API consumes an iterable, validates samples without changing their data and
returns a list. Empty input or all-visible samples return an empty list.
Malformed samples, invalid initial state/order or exceeded limits raise
`ValueError`; no partial result is returned. Processing a generator can consume
a prefix before an error, so callers must not assume the iterable can be reused.

The API and CLI accept at most 10,000 nonblank samples. The CLI additionally caps
raw input at 64 MiB and each physical line at 16,384 bytes including line endings.
Blank lines count toward byte limits but produce no samples. Duplicate JSON
keys, extra fields, malformed JSON and invalid UTF-8 are rejected. Missing or
unreadable files fail. Errors exit 2 with stderr and no JSON result; success
exits 0, including empty input. Output is built only after validation completes.

This module does not open or migrate a database, alter stored observations, or
assign permanent event IDs. Its visibility samples are a separate schema and
cannot be ingested as zone observations. Existing zone-change queries are not
automatically aware of these events; this module does not suppress or rewrite
their results. A future integrated perception producer must coordinate visibility
and spatial observations. No automatic timeout policy or camera validation is
implemented here.
