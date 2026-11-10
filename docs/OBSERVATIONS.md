# Observation contract

SpatialMind currently imports supplied observations and retrieves an object's
last recorded observation or chronological observation history. It does not derive observations from video, infer physical
identity, or predict an object's current position. The included examples are synthetic.

## JSONL input

Each nonblank line is a UTF-8 JSON object containing exactly these five fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `video` | String | Source recording identifier |
| `object_id` | String | Object identifier scoped to that recording |
| `t_ms` | Integer | Milliseconds from the start of the source recording |
| `label` | String | Supplied human-readable object description |
| `zone` | String | Supplied location or region label |

Every string must contain non-whitespace text, contain only printable characters,
and be at most 512 characters long. Strings are stored unchanged, compared exactly,
and are not trimmed or case-normalized. Printable Unicode is accepted.
For example, `"B"` and `"b"` identify different recordings.

`t_ms` must be an integer in the inclusive range 0 to 9,223,372,036,854,775,807.
Booleans, floating-point numbers, numeric strings and negative values are rejected.
It is not a Unix timestamp or wall-clock time. Times from different recordings
cannot establish which recording happened later.

Extra fields, missing fields, duplicate JSON keys and non-object JSON values are
rejected. A physical line may contain at most 16,384 bytes, including its line
ending when present. Blank lines within that limit are ignored. The final line
does not require a newline. Empty input succeeds with zero inserted records.

## Identity and evidence

An object's lookup scope is the pair `(video, object_id)`. Reusing `bottle_01`
in recordings A and B does not establish that they show the same physical bottle.

An observation's unique evidence reference is the tuple
`(video, object_id, t_ms)`. The stored `label` and `zone` describe that
observation. They may change at subsequent timestamps.

The reference identifies an imported database record. It is **not** a playable
media link: the current implementation does not resolve `video` to a file or
URL, verify a recording exists, validate its duration, or attach a frame or mask.
A later video adapter must provide that grounding.

## Import and conflict behavior

Run commands from the repository root with Python 3.11 or newer:

```sh
python -m spatialmind --db two-recordings.sqlite ingest examples/two_recordings.jsonl
```

On a fresh database, stdout is:

```json
{"inserted": 3, "unchanged": 0}
```

Input does not have to be ordered by timestamp. Importing the same fixture again
returns `{"inserted": 0, "unchanged": 3}`.

Replay uses the evidence reference `(video, object_id, t_ms)` as the record key:

| Incoming observation | Result |
| --- | --- |
| Key absent from both stored records and earlier lines in this batch | Insert; increment `inserted` |
| Same key, label and zone as a stored observation, including one inserted earlier in this batch | Leave unchanged; increment `unchanged` |
| Same key but a changed label or zone, including a conflicting repeat in the same batch | Reject the import; roll back all new observations from this invocation |

Counters describe processed record occurrences in a successful import, not the
number of unique unchanged records. Three identical lines in a fresh database
return `{"inserted": 1, "unchanged": 2}`; replaying those three lines returns
`{"inserted": 0, "unchanged": 3}`.

Retrying identical input is safe, but replay is not a correction mechanism:
it never replaces an existing observation's label or zone. Corrections are not
supported by the current CLI.

A malformed or conflicting record rolls back every new observation from that
invocation, preserving previously committed records. Failed imports return no
success counters. An attempted import can still create an empty database and schema.

## Scoped last-seen queries

The fixture deliberately inserts recording B's 3,000 ms observation before its
1,000 ms observation. Last-seen selects the greatest timestamp within the requested
recording and object scope, not the last inserted row.

```sh
python -m spatialmind --db two-recordings.sqlite last-seen bottle_01 --video A
```

```json
{"label": "blue bottle", "object_id": "bottle_01", "t_ms": 9000, "video": "A", "zone": "shelf"}
```

```sh
python -m spatialmind --db two-recordings.sqlite last-seen bottle_01 --video B
```

```json
{"label": "blue bottle", "object_id": "bottle_01", "t_ms": 3000, "video": "B", "zone": "bench"}
```

An unscoped query is allowed only when that object ID occurs in one recording in
the database. With this fixture, the following command fails rather than comparing
9,000 ms in A with 3,000 ms in B:

```sh
python -m spatialmind --db two-recordings.sqlite last-seen bottle_01
```

Its stderr message is
`error: object ID occurs in multiple recordings; specify --video`.
Matching is by object ID, not by label or natural-language description.

## Scoped history queries

`history` returns all observations for one object within one recording, in
ascending `t_ms` order. It uses the same scope and ambiguity rules as
`last-seen`: omit `--video` only when the object ID occurs in one recording.

```sh
python -m spatialmind --db two-recordings.sqlite history bottle_01 --video B
```

The output is a JSON array (formatted here for readability):

```json
[
  {"label": "blue bottle", "object_id": "bottle_01", "t_ms": 1000, "video": "B", "zone": "desk"},
  {"label": "blue bottle", "object_id": "bottle_01", "t_ms": 3000, "video": "B", "zone": "bench"}
]
```

Each element contains the same five fields as a last-seen result. A one-observation
history is still an array. No match exits 1 without JSON; an ambiguous unscoped
query exits 2 without JSON. History does not infer continuous visibility or
movement between observations.

This local MVP loads the complete matching history into memory before producing
JSON. It has no pagination or time filter and is intended for small histories;
memory use grows with the number and size of matching observations.

## Derived zone-change queries

`zone-changes` uses a known-zone baseline and requires consecutive observations
of a different target zone before emitting an event. It uses the same recording
scope as `history` and `last-seen`.

```sh
python -m spatialmind --db two-recordings.sqlite zone-changes bottle_01 --video B
```

Defaults are `--confirm-observations 2` and `--max-gap-ms 5000`. The sample
recording B has only one desk and one bench observation, so this default query
returns `[]`: the target is not yet confirmed. To request immediate confirmation:

```sh
python -m spatialmind --db two-recordings.sqlite zone-changes bottle_01 --video B --confirm-observations 1
```

This produces the following array (formatted for readability):

```json
[
  {
    "type": "ZONE_CHANGED",
    "video": "B",
    "object_id": "bottle_01",
    "from_zone": "desk",
    "to_zone": "bench",
    "before_t_ms": 1000,
    "after_t_ms": 3000,
    "confirmed_t_ms": 3000
  }
]
```

Both options must be integers from 1 through 9,223,372,036,854,775,807. Invalid
options exit 2 without JSON, before opening the database. The Python API accepts
the same options as keyword-only `confirm_observations` and `max_gap_ms`;
it rejects booleans and non-integer values.

### Confirmation rules

- The first known observation establishes a baseline without an event.
- A different known zone starts a candidate. Only consecutive observations of
  that same target count toward confirmation.
- Returning to the baseline cancels the candidate and updates the latest baseline
  timestamp. A third zone replaces the candidate and restarts its count.
- When the count reaches the configured threshold, emit one event and use the
  confirming observation as the new baseline. Repeated sightings in that baseline
  zone do not emit more events.
- The exact sentinel `unknown` clears both baseline and candidate. The next
  known observation establishes a new baseline without bridging the unknown.
- A gap **greater than** `max_gap_ms` between adjacent observations also clears
  baseline and candidate. Equality is allowed. The current known observation
  becomes a fresh baseline, so no event bridges the long gap.

For example, with default settings A at 0 ms, B at 5,000 ms, and B at 10,000 ms
confirm one A-to-B event: each adjacent gap is at most 5,000 ms. This setting is
not a maximum total transition duration. A at 0 ms followed by B at 60,000 ms
and B at 61,000 ms produces no event: the minute-long gap resets the baseline.

A, B, A, B, A produces no event with the default threshold. Two consecutive B
observations after the latest A confirm one transition. This is an
observation-count filter, not a minimum dwell-time rule; its behavior depends on
sampling cadence. It suppresses brief jitter but does not prove physical movement.

### Event evidence and limits

`before_t_ms` is the latest baseline-zone sighting before the confirmed candidate
run. `after_t_ms` is the **first** sighting in that candidate run.
`confirmed_t_ms` is its confirming sighting. For A at 100 ms, A at 200 ms,
B at 300 ms, and B at 400 ms, the default event times are 200, 300, and 400.
Combine each timestamp with `video` and `object_id` to recover its stored
evidence reference. None of these timestamps claims the exact movement instant.

Other imported zone strings are compared exactly, without consulting a rectangle
config. Unknown means unresolved location, not removal or invisibility. A reset
suppresses unsupported transitions; it does not itself emit an uncertainty or
visibility event.

An existing object's history with no confirmed changes returns `[]` and exit 0,
including a single observation or an all-unknown history. No observations in the
requested scope returns exit 1 without JSON; ambiguous unscoped IDs return exit 2
without JSON.

Events are derived on demand, not stored or assigned permanent IDs. Replaying
identical input with identical options preserves results. Importing earlier
observations or changing query options can change derived events. These options
are not persisted in the database. No continuous visibility or movement path is
inferred between sightings. Queries load the complete history and event list into
memory; there is no pagination. Interval filtering does not reduce history loading.

### Filtering by confirmation time

Use `--start-ms` and/or `--end-ms` to select events by their
`confirmed_t_ms`, in milliseconds relative to the selected recording.
Both endpoints are inclusive; omitting a bound leaves that side unbounded.

```sh
python -m spatialmind --db two-recordings.sqlite zone-changes bottle_01 --video B --confirm-observations 1 --start-ms 3000 --end-ms 3000
```

This single-instant interval returns the sample event confirmed at 3,000 ms.
A bound of 3,001 ms on the start would exclude it. Equal endpoints are valid;
an empty selection returns `[]` with exit 0 when the object's history exists.
This differs from an absent object/recording (exit 1) or ambiguous unscoped object
ID (exit 2), even if the requested interval would contain no events.

Bounds must be integers from 0 through 9,223,372,036,854,775,807, and start must
not exceed end. Invalid bounds exit 2 with no JSON before opening the database.
The Python API accepts keyword-only `start_ms=None` and `end_ms=None`,
validates the same limits, and rejects booleans and non-integers.

Debounce runs over the **complete history before filtering**. For A at 100 ms,
B at 200 ms and B at 300 ms with default confirmation settings, interval
[300, 300] includes the event with evidence times 100, 200 and 300. Those
observations are not clipped or rewritten to the query interval. Interval
[200, 200] excludes that event: a first target sighting is not yet confirmation.
Likewise, events with evidence overlapping a window but confirmed outside it
are excluded. This query answers when zone changes became supported, not when
physical movement definitely occurred.

Omitting both bounds preserves the unfiltered result. Bounds do not change
recording-scope resolution, debounce settings, event fields, or stored data;
they are query options and are not persisted.

## CLI results

| Exit code | Meaning | Output |
| --- | --- | --- |
| 0 | Import or query succeeded | One JSON object for import/last-seen; a JSON array for history/zone-changes, on stdout |
| 1 | No matching observation for the requested scope | `no matching observation` on stderr |
| 2 | Invalid invocation, input, ambiguous scope, conflict, or handled file/database error | Diagnostic on stderr |

Failed commands do not emit a successful-result JSON object. The required
`--db PATH` option precedes the subcommand; `--video VIDEO` belongs to
`last-seen`, `history` or `zone-changes`. Database parent directories must already exist.
