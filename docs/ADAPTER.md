# Offline observation replay adapter

The replay adapter is the first CPU-only perception boundary. It emits validated
observation dictionaries from a local JSONL file. It does not read video, infer
objects, calculate timestamps or associate identities. Future perception
implementations can supply the same observations to the existing ingestion path.

No network requests, model weights, third-party dependencies or GPU are used.

## Python interface

```python
from spatialmind.adapter import ReplayAdapter

adapter = ReplayAdapter("examples/synthetic_occlusion.jsonl")
for observation in adapter.observations():
    print(observation)
```

Each call to `observations()` opens the file anew. It preserves source order,
duplicate rows, exact field values, and video-relative timestamps, including
out-of-order timestamps. It does not sort, deduplicate, interpolate gaps or
invent wall-clock time. Legacy rows retain five fields; `tracklet_id` is
included only when supplied. Changes to the source file between calls are
visible on the next call; the adapter does not take a persistent snapshot.

The iterator yields validated rows lazily. A malformed later row raises
`ValueError` after earlier rows may already have been consumed. Callers that
persist iterator results must provide their own transaction or staging boundary.
File access failures propagate as `OSError`.

## CLI

From the repository root:

```sh
python -m spatialmind.adapter examples/synthetic_occlusion.jsonl > replay.jsonl
python -m spatialmind --db replay.sqlite ingest replay.jsonl
python -m spatialmind --db replay.sqlite history bottle_01 --video occlusion_demo
```

Only continue to ingestion if replay exits successfully. The replay command
outputs one validated JSON object per line and exits 0. Empty or blank-only
input succeeds with no output. Whitespace and key ordering may change; field
values do not.

Invalid source data, exceeded limits and file access errors exit 2 with a
diagnostic on stderr and no observation output. The CLI first stages the
**entire validated output** in a temporary spool, then copies it to stdout.
It retains at most 1 MiB of spool content in memory before spilling to a
temporary disk file, which is closed and removed on completion. Output delivery
is not atomic: a closed pipe or other output error can interrupt transmission
after some bytes were delivered. Temporary output contains the supplied
observations; use a suitable private temporary directory for sensitive inputs.

## Validation and resource limits

The adapter deliberately reuses the internal ingestion parser, `store._parse`,
to keep field and value validation identical. This is a narrow internal
dependency, not a second public schema. See [the observation contract](OBSERVATIONS.md).

Both API and CLI enforce:

- At most 64 MiB (67,108,864 bytes) of raw input, including blank lines and line endings.
- The existing 16,384-byte limit per physical line, including any line ending.
- UTF-8 JSON objects with exactly the five required fields and optional tracklet ID.
- Duplicate-key rejection, printable text limits and nonnegative integer timestamps.

Both limits accept equality. Blank lines count toward resource limits but
produce no observations. The final row need not end in a newline.
Output size is bounded by validated input and record serialization; the
temporary disk spool avoids retaining the entire file in RAM.

Validation is **per observation**, not relational. Replay accepts two individually
valid rows that conflict at the same evidence key, or that assign a tracklet to
different objects. Database ingestion remains responsible for rejecting those
conflicts atomically. The adapter never opens a database or edits source records.

Inputs are explicitly selected local paths, not URLs; the adapter does not
download remote files or resolve recording IDs to media. It is intended for
trusted local files, not as a filesystem sandbox for untrusted clients.
