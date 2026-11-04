# Observation contract

SpatialMind currently imports supplied observations and retrieves the last recorded
observation of an object. It does not derive observations from video, infer physical
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

If an existing evidence reference has exactly the same label and zone, the record
is unchanged. If either differs, import fails as a conflict; it does not overwrite
the prior observation. This also applies to repeated references within one file.
A malformed or conflicting record rolls back every new observation from that
invocation, preserving previously committed records. An attempted import can still
create an empty database and schema.

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

## CLI results

| Exit code | Meaning | Output |
| --- | --- | --- |
| 0 | Import or query succeeded | One JSON object on stdout |
| 1 | No matching observation for the requested scope | `no matching observation` on stderr |
| 2 | Invalid invocation, input, ambiguous scope, conflict, or handled file/database error | Diagnostic on stderr |

Failed commands do not emit a successful-result JSON object. The required
`--db PATH` option precedes the subcommand; `--video VIDEO` belongs to
`last-seen`. Database parent directories must already exist.
