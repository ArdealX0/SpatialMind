# Controlled-language observation queries

This deterministic parser supports two narrow English patterns. It uses no LLM,
model, embeddings, label search or general-purpose agent execution.

```sh
python -m spatialmind.queries --db snapshots.sqlite --video snapshot_demo 'Where was "bottle" last seen?'
python -m spatialmind.queries --db snapshots.sqlite --video snapshot_demo 'Show zone changes for "bottle" between 1000 and 3000 ms.'
```

The database must already exist with the current SpatialMind observation schema.
Use the normal ingestion command to create/populate it. Querying opens SQLite
in read-only mode and never creates or migrates a database.

The example zone-change query may return an empty array: the default detector
requires two consecutive observations in the target zone, while the small
fixture has only one. An empty event list is still a successfully answered
request; it does not mean that the parser failed.

## Supported grammar

- `Where was "OBJECT_ID" last seen?`
- `Show zone changes for "OBJECT_ID"`
- `Show zone changes for "OBJECT_ID" between START and END ms.`

The English keywords are case-insensitive. Final ? or . is optional; leading
and trailing spaces are ignored. Internal phrase spacing follows the examples.
The **entire prompt** must match: extra instructions, two commands, negation and
unsupported wording abstain. Quotes are required. The quoted ID is a JSON string,
so escaped quotes and Unicode escapes are decoded as literal ID characters.
The decoded ID's case is preserved; no label, nickname or fuzzy-ID lookup occurs.

Recording ID is an explicit separate `--video` argument. Both IDs must be
nonempty printable strings of at most 512 characters. A prompt must be nonempty
printable text of at most 2,048 characters. Controls and embedded newlines are
invalid. SQL-looking or shell-looking text inside a valid ID remains data; it is
not executed, opened as a file or interpreted as a media path.

START and END are decimal source-video milliseconds, inclusive, from 0 through
2**63-1. Equal endpoints are valid; reversed or overflowing recognized bounds
are invalid. Signed, fractional, wall-clock and relative-time wording does not
match the grammar. There is no implicit current time or “last minute” anchor.
Zone-change requests use the existing default debounce/gap settings and filter
on `confirmed_t_ms`, deriving events from full history before filtering.

## Structured results and APIs

`compile_request(prompt, video)` returns a dictionary with an allowlisted
operation (`last_seen` or `zone_changes`) and validated parameters, or None
for unsupported wording. Compilation does not access a database or network.

`answer(db, prompt, video)` uses an already open SQLite connection configured
with `sqlite3.Row`; it makes no writes itself. The caller controls that
connection's permissions. The CLI always uses a read-only connection.

Valid requests produce structured results:

- `status: "answered"`: includes `query` and unmodified source `evidence`.
  An empty zone-change array is a valid answered result.
- `status: "evidence_missing"`: the supported request has no matching object
  observations in that recording; evidence is null.
- `status: "unsupported"`: wording is outside the grammar. Reason is
  `unsupported_pattern`, and no database is opened or accessed.

All three outcomes exit 0 with one JSON object. Invalid prompt/ID/bound values,
file/database errors or malformed quoted JSON exit 2 with stderr and no JSON.
Unsupported requests abstain even if the specified database does not exist.
Supported requests to a nonexistent database fail without creating one.

Only compiler output is routed through fixed Python call sites. No prompt text
becomes SQL syntax, a Python expression or a shell command. Existing store
functions bind literal parameters and preserve source timestamps and tracklets.
Last-seen evidence does not prove current location or visibility. Zone changes
retain their existing evidence and confirmation semantics.

`examples/query_cases.json` is a human-authored grammar fixture; it is not a
prediction or conversational benchmark. Broader phrasing, semantic object
resolution, natural-language snapshots and multi-object reasoning remain outside
this initial interface.
