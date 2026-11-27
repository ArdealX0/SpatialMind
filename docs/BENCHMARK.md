# Synthetic CPU benchmark

```sh
python -m spatialmind.benchmark examples/evaluation_set.json
python -m spatialmind.benchmark examples/evaluation_set.json --split test \
  --expected-sha256 27860bc7c4b37702c6f9169a441ec5187e17855f1db3dbab5737c13a928a2403
```

The benchmark evaluates fixed observation-store and controlled-language query operations against the [authored evaluation set](EVALUATION_SET.md). This is a synthetic contract check, not a detector, identity model or real-video accuracy evaluation. It does not establish generalization. Preserve the frozen fixture and its authored labels when comparing changes; do not tune labels against test answers.

`--split` selects `all` (default), `dev`, or `test`. The bounded manifest is read and validated once; an optional SHA-256 pin must match those exact bytes before evaluation starts. Both splits are validated even when only one is evaluated. Invalid input exits 2, emits an error on stderr and produces no partial JSON on stdout.

Each selected session receives a fresh in-memory SQLite database. Its supplied observations are ingested, zone changes are derived independently for each declared object, and each prompt is passed to the existing fixed query answer function. Event and query execution use the existing defaults: two confirming observations and a 5000 ms maximum gap. No referenced media, database files or network resources are opened; video identifiers remain opaque text. No model executes.

The deterministic JSON includes corpus digest, version, authored synthetic provenance and full corpus split counts; `config` identifies the split selection and event defaults. `splits` contains only evaluated splits, each with counts, event/query scores and per-session diagnoses. Session records include expected and predicted events. Query `results` retain case IDs, expected/predicted statuses and evidence, and correctness. Output is written only to stdout; save it outside the repository if needed.

## Metrics

| Field | Meaning |
| --- | --- |
| Event `tp`, `fp`, `fn` | Multiset intersection, excess predictions and missed authored events, respectively |
| Event `total_expected`, `total_predicted` | Raw authored and predicted event denominators |
| Event `precision`, `recall` | `tp / (tp + fp)` and `tp / (tp + fn)` |
| Query `correct`, `total`, `accuracy` | Exact status-and-evidence matches, all cases, and `correct / total` |
| Query `by_expected_status` | `correct`, `total`, `accuracy` separately for each authored status, including zero-count statuses |
| Query `unsupported` | Counts of expected unsupported, predicted unsupported, and correct unsupported cases |
| Query `answered_on_unanswerable` | Cases authored as `evidence_missing` or `unsupported` that predict `answered` |

Zero denominators produce JSON `null`, never an invented perfect score. Split scores pool raw cases/events across sessions, rather than averaging session percentages. Incorrect, missing-evidence and unsupported cases remain in query denominators. A predicted unsupported status counts as correct only when its evidence also matches the authored null evidence.

An event matches only if its complete JSON value matches exactly. Canonical object-key ordering makes dictionary order irrelevant, while JSON value types remain distinct (`true`, `1`, and `1.0` differ). Duplicate predictions count as false positives beyond the authored multiplicity. Query evidence uses the same exact canonical JSON comparison: array order, extra fields, optional tracklet identity and numeric types matter. Query metadata such as the compiled request or explanatory reason is not scored. Empty event-list evidence is an answered negative case, distinct from missing evidence.

For independent checks, `score_events(expected, predicted)` accepts event iterables, and `score_queries(cases, predictions)` accepts equally sized aligned iterables of authored cases and answer dictionaries. These pure scoring helpers can receive deliberately incorrect predictions without altering the fixture. The CLI accepts no external predictions. `run_benchmark(path, split='all', expected_sha256=None)` returns the same object as the CLI.
