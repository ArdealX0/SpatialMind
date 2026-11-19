# Position-and-gap association suggestions

This standalone CPU baseline proposes which supplied session object a new
tracklet might belong to. It does not update observation records or immutable
tracklet links, and it does not establish physical identity.

```python
from spatialmind.association import suggest_association
result = suggest_association(
    {"video":"demo","tracklet_id":"new_track","t_ms":2000,"x":0.25,"y":0.5},
    [{"video":"demo","object_id":"bottle","t_ms":1000,"x":0.2,"y":0.5}],
)
```

Incoming points require exactly video, tracklet_id, t_ms, x and y. Candidate
points require exactly video, object_id, t_ms, x and y. Supply at most one latest
known position per recording/object, and at most 100 candidates. Duplicate
recording/object keys are rejected rather than arbitrarily choosing a position.
The caller selects the candidate population; the helper does not query a database.

Coordinates are finite normalized image positions in [0, 1], with top-left
origin. The caller chooses a comparable point, such as a centroid, for both
incoming and candidate data. No pixel conversion, camera calibration, depth or
motion compensation is performed. IDs are nonempty printable text up to 512
characters. Time is a nonnegative integer below 2**63, in source-video
milliseconds. Booleans and explicit null values are invalid.

## Gates and outcomes

A candidate is eligible only when its video matches, its timestamp is strictly
earlier, its gap is at most `max_gap_ms` (default 5,000), and normalized 2D
Euclidean distance is at most `max_distance` (default 0.15). Both upper limits
are inclusive. Configurable gap must be an integer from 1 to 60,000 ms;
distance must be finite from 0 to sqrt(2), inclusive. Zero distance requires
exactly matching coordinates. No score is interpreted as a probability.

- Exactly one eligible candidate: `matched` with a proposed object ID.
- No eligible candidates: `unmatched` with a null proposed ID.
- Multiple eligible candidates: `ambiguous` with a null proposed ID, even
  when one is closer. No forced nearest-neighbor decision is made.

The result includes the supplied incoming point, configured thresholds, eligible
object IDs, and diagnostic entries for every supplied candidate. Diagnostics
include the unchanged candidate point, gap, distance, eligibility and rejection
reasons. Different-video candidates have null gap/distance: their clocks and
positions are not compared. Equal/future times have `nonpositive_gap`;
large gaps and distances have `gap_exceeded` and `distance_exceeded`.
Results sort by video then object ID, independent of candidate input ordering.
Input records are not changed.

## CLI and labeled examples

Save one job with required `incoming` and `candidates`, and optional
`max_gap_ms` and `max_distance`, then run:

```sh
python -m spatialmind.association job.json
```

One JSON result is emitted on exit 0 for all three valid outcomes. Invalid input
exits 2 with stderr and no result. CLI input is one UTF-8 JSON object capped at
65,536 bytes; duplicate JSON keys, extra fields and malformed input are rejected.
The Python API enforces schema/count/value limits but cannot limit memory already
allocated by the caller. There is no network, model dependency or database access.

`examples/association_cases.json` contains human-authored synthetic cases with
expected outcomes. To try a case, save its `input` object as job.json or pass
that object as keyword arguments to `suggest_association`. The surrounding
manifest and expected labels are not CLI job fields. Its look-alike case requires
abstention despite unequal distances; the minute-gap case is unmatched by default.

These labels verify policy, not real-world identity accuracy. A unique plausible
candidate can still be the wrong object, and unseen candidates can change the
answer. Fixed-camera comparable geometry and reliable supplied timestamps are
assumptions. No appearance matching, global one-to-one assignment across multiple
incoming tracks, occlusion detection or link correction is implemented.
A proposal must be reviewed before a caller uses it in new observations;
this helper cannot bypass the store's immutable-link conflict checks.
