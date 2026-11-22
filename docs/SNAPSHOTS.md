# Historical scene snapshots

A scene snapshot returns each object's latest stored observation at or before
a requested time in one recording. It is **last-observed evidence**, not a claim
that every object was present, visible or still at that location at query time.

```sh
python -m spatialmind --db snapshots.sqlite ingest examples/snapshot_samples.jsonl
python -m spatialmind --db snapshots.sqlite snapshot --video snapshot_demo --at-ms 2500
python -m spatialmind --db snapshots.sqlite snapshot --video snapshot_demo --at-ms 3000
```

At 2,500 ms, the bottle's supporting observation is desk at 1,000 ms (age 1,500)
with track_before. At 3,000 ms, it is shelf at 3,000 ms (age 0) with track_after.
Both snapshots include the mug's unknown location from 2,000 ms. Its later shelf
observation at 4,000 ms cannot leak into earlier snapshots. The same bottle ID
in another_recording is never considered. Fixture input order is deliberately
different from source-time order.

## API and result

```python
from spatialmind.store import snapshot
result = snapshot(db, video="snapshot_demo", at_ms=2500)
```

The result is an object with video, at_ms, semantics="last_observed", and an
objects array sorted by exact object_id. Each array entry has age_ms and the
complete original observation. Legacy rows retain five fields; tracked rows also
retain their original tracklet_id. Age is query time minus observation time.

A timestamp equal to an observation includes that observation. Objects with only
future observations are absent. An unknown recording, empty database or query
before all observations succeeds with an empty objects array. This does not mean
the physical scene was empty or those objects had been removed.

No freshness cutoff is imposed. A very old observation is retained with its age;
it must not be presented as a current position. A latest unknown-zone observation
is preserved rather than replaced with an older known position. The snapshot
does not consult the standalone visibility stream or infer state from silence.

The store's existing unique (video,object_id,t_ms) key makes the latest row
deterministic. Label, zone and tracklet are all taken from that same selected row,
never from a future row. Historical results can change when observations are
backfilled: this is an as-of-source-time query over currently stored data, not a
versioned database snapshot.

## Validation and limits

Video is required, with the same nonempty printable string limit of 512
characters. at_ms is an integer in [0, 2**63-1]. Booleans, floats, negative and
out-of-range values are rejected by the API. CLI invalid/missing settings exit 2
with stderr and no JSON, before connecting to the database. Successful queries
exit 0, including empty results.

A snapshot supports at most 10,000 objects. More objects at/before the query time
raise an error, never a silently truncated snapshot. The query fetches at most
10,001 result rows to detect this overflow; database history scanning is not
time-bounded. There is no pagination in this first version.

Query values are bound SQL parameters. The snapshot function does not update
observations or identity links. The existing CLI connection helper can still
create/migrate a database schema when opening a path; this command is not a
strict filesystem read-only connection mode. No images, models, depth estimates
or real-camera measurements are involved.
