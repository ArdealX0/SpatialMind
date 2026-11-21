# Paired identity evaluation preparation

This CPU-only harness compares two **externally supplied** prediction sets on the
same independently labeled cases. It neither runs the position baseline nor
loads an appearance encoder. The appearance experiment and prediction collection
are **NOT_RUN**. No embeddings, synthetic feature vectors or model scores are
provided as measured results.

The human-authored cases in `examples/appearance_cases.json` include a nearby
wrong candidate while the true object is farther away, a true object absent from
the candidate set, and an unresolved identity. Labels specify the scenario's
physical identity or uncertainty; they are not copied from either model's output.
They are synthetic policy cases, not a real-camera accuracy benchmark.

## Run contract

A case manifest contains `provenance` and 1–1,000 `cases`. Each case has
`case_id`, unique `candidate_ids` (at most 100), and an `expected` outcome;
an optional `context` object holds explanatory evidence. Outcomes contain exactly
`status` and `object_id`. Status is matched, unmatched or ambiguous.
Matched outcomes must name a supplied candidate; abstentions require null IDs.

Each run file has this shape:

```json
{"predictions": [
  {"case_id": "your-case-id", "status": "unmatched", "object_id": null}
]}
```

This is a format illustration, not a collected prediction. Supply every case
exactly once in both runs. Duplicate, missing and unknown case IDs are rejected,
as are predicted matched IDs outside that case's candidate set. Runs may order
cases differently. Labels and IDs are nonempty printable text up to 512 characters.

To validate/freeze the labeled cases without inventing predictions:

```sh
python -m spatialmind.association_eval examples/appearance_cases.json
```

With no run files, both statuses are `NOT_RUN`, run metrics, paired counts,
per-case verdicts and accuracy delta are null. Supplying only a baseline file
leaves appearance `NOT_RUN` with null comparison results. A supplied file is
marked `SUPPLIED`, not authenticated as a real model run; provenance must be
verified separately.

After collecting approved outputs:

```sh
python -m spatialmind.association_eval examples/appearance_cases.json baseline.json appearance.json
```

The CLI accepts a case file and up to two local UTF-8 prediction JSON files, each capped at 1 MiB. Malformed JSON,
duplicate keys, nonfinite JSON constants, unknown fields in the schemas and
invalid outcome combinations exit 2 with stderr and no result. Valid comparison
exits 0 with one JSON object. The optional context is not scored or used for
inference; only its object shape is checked. The Python API is
`compare_runs(manifest, baseline=None, appearance=None)`; file byte limits apply to the
CLI, while schema/count limits apply to both.

## Counts and interpretation

For each run, exact correctness requires both expected status and object ID.
Accuracy is exact correct count divided by total case count; the output includes
correct/incorrect counts and the total denominator. A false link is any matched
prediction that is not exactly correct, including a link on an ambiguous or
candidate-absent case. Predicted-match count is provided alongside false links.

Correct abstention means the prediction and expected outcome both decline a
match. Thus predicting unmatched for an ambiguous case counts as a correct
abstention but is **not** exact correctness. The two measures answer different
questions; do not substitute one for the other.

Per-case verdict is improved when appearance is exact-correct and baseline is
wrong, regressed for the reverse, and unchanged when both are right or both are
wrong. Different wrong answers are unchanged under this definition, but both
predictions remain visible. Results are sorted by case ID and include expected
labels, both outputs and aggregate verdict counts.

## Later experiment procedure

Freeze an approved recording-level split, source frames/crops, detector outputs,
tracklet IDs, candidate IDs and reference labels before comparing methods.
Use the same detections and candidate population for both methods. Tune gates
and appearance thresholds on development data, then freeze them before test
evaluation. Record encoder revision, preprocessing and runtime separately.

Keep cases where spatial matching selects a plausible wrong object and cases
where the true identity is absent; these reveal whether appearance helps identity
rather than merely reproducing spatial decisions. Permit abstention when evidence
is insufficient. The evaluator checks pairing by case ID, not file hashes or
image equality: the experiment owner must verify identical underlying inputs.

Unit tests use deliberately constructed predictions to check arithmetic and
rejection behavior. Passing those tests is not evidence that appearance improves
matching. No accuracy claim should be made until real, authorized outputs exist.
