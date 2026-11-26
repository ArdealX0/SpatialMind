# Frozen synthetic evaluation set

```sh
python -m spatialmind.eval_set examples/evaluation_set.json
```

This CPU-only, standard-library validator checks an embedded manifest. It prints one JSON summary with `version`, `provenance`, exact-file-byte `sha256`, and `splits` counts for sessions, objects, observations, events and query cases. Invalid input exits 2 with an error on stderr and no partial stdout. It neither writes a database nor opens referenced media or network resources.

The example is a small authored contract fixture, not sensor data, model inference, accuracy measurement or evidence of generalization. Three independent synthetic sessions use distinct video identifiers; two are development sessions and one is held out as test. The cases cover confirmed zone changes, jitter/unknown/long-gap observations without a confirmed event, last-seen answers, empty interval answers, unobserved-object requests and unsupported wording. The held-out session reuses an object ID in a distinct video and supplies tracklet identity. `video` is an opaque identifier, never a path to load. Preserve the file and its reported SHA256 when comparing future benchmark runs. Changing labels or whitespace changes that identity; author a new versioned fixture deliberately rather than tuning labels against test answers.

The frozen example SHA256 is `27860bc7c4b37702c6f9169a441ec5187e17855f1db3dbab5737c13a928a2403`; regression coverage pins both these bytes and their split counts.

## Version 1 schema

All object fields below are required and unknown fields are rejected, except observation rows allow the existing optional `tracklet_id` field.

| Location | Fields and meaning |
| --- | --- |
| Root | `version`: integer 1; `provenance`: exactly `{"kind":"synthetic","labels":"authored_not_inference"}`; `sessions`: array |
| Session | `session_id`: globally unique text; `split`: `dev` or `test`; `video`: globally unique text; `objects`, `observations`, `expected_events`, `query_cases`: arrays |
| Object | `object_id`: unique in session; `label`: authored object label |
| Observation | `video`, `object_id`, `t_ms`, `label`, `zone`, optional `tracklet_id`, following the [observation contract](OBSERVATIONS.md) |
| Expected event | `type`: `ZONE_CHANGED`; `video`, `object_id`, `from_zone`, `to_zone`, `before_t_ms`, `after_t_ms`, `confirmed_t_ms` |
| Query case | `case_id`: globally unique text; `prompt`: controlled-language request or unsupported wording; `expected_status`: `answered`, `evidence_missing` or `unsupported`; `expected_evidence`: authored label |

Both splits must be nonempty and every session belongs wholly to one split. Repeated video identifiers are rejected even within a split to prevent session leakage. Object IDs may recur across independent sessions. Observation video/object/label references must agree with the containing session; duplicate object/time rows and conflicting tracklet identities are rejected.

Events reference declared objects and embedded observation times, with `before_t_ms < after_t_ms <= confirmed_t_ms` and matching source/destination zones. Query patterns use the existing [controlled-language compiler](QUERIES.md). Unsupported patterns require `unsupported`; supported patterns require `answered` or `evidence_missing`. Non-answered cases carry null evidence. Answered last-seen evidence references an embedded observation; answered zone-change evidence is a list referencing authored expected events within any requested inclusive interval. An empty event list is a valid negative answer.

The validator does **not** execute queries, derive events, choose the latest observation or calculate correctness of the authored answer. It rejects `evidence_missing` for an object with embedded observations. The author remains responsible for selecting the latest sighting and supplying complete, semantically correct event lists. This separation preserves labels for a later evaluator instead of generating ground truth from the system being evaluated. The example labels follow the existing default event settings: two confirming observations and a 5000 ms maximum gap.

## Input bounds

The read is capped at 1 MiB. UTF-8 JSON duplicate keys and nonfinite constants are rejected. There are 3–100 sessions, 1–100 objects and 1–5000 observations per session, 0–5000 events, and 1–1000 query cases. Identifiers/labels/zones are nonempty printable strings up to 512 characters; prompts follow the compiler's 2048-character bound. Timestamps are nonnegative integers below `2**63` (booleans are rejected). These limits make the fixture deliberately modest; this is not an unrestricted dataset import format.
