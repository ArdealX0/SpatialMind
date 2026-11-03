# SpatialMind: first 30 days

November 3 – December 2, 2026 (America/Toronto). This is a plan, not a list of completed features. The month aims to answer “where was this object last observed?” and “when did it change zones?” for one fixed camera, with source timestamps. It is the first increment of the longer research project.

One small, reviewable increment per day. Read the latest log and repository state first; if an earlier milestone slipped, resume it before taking the next dependency. When a run cannot deliver a meaningful change, record the blocker and next action rather than manufacturing a commit. Never backdate commits. Use actual, approved test footage; never commit private recordings, credentials, weights, or generated databases.

| Day | Toronto date | Increment | Acceptance evidence |
|---:|---|---|---|
| 1 | Nov 3 | Ingest labeled JSONL observations into SQLite; query last seen. | Synthetic example, CLI output, persistence and rollback tests. |
| 2 | Nov 4 | Define video-relative milliseconds, object ID scope and evidence references. | Two-video test prevents accidental identity or clock comparisons across recordings. |
| 3 | Nov 5 | Document and test replay policy. | Importing the same fixture twice has explicitly tested semantics. |
| 4 | Nov 6 | Expose a time-ordered object history. | Out-of-order input yields correctly sorted history for a single recording. |
| 5 | Nov 7 | Define named workbench zones and unknown locations. | Boundary and unknown-zone fixtures. |
| 6 | Nov 8 | Add zone-change events from confirmed observations. | Crossing produces one event with before/after times. |
| 7 | Nov 9 | Debounce noisy zone boundaries. | Repeated jitter produces no spurious transitions; minute-long gaps remain uncertain. |
| 8 | Nov 10 | Implement “changes during interval” with source object and time. | Tests for endpoint inclusion and empty intervals. |
| 9 | Nov 11 | Split tracklet IDs from session object IDs. | Reappearing tracklets can refer to one object without erasing original IDs. |
| 10 | Nov 12 | Build synthetic occlusion and look-alike scenarios. | Explicit ambiguity outcomes; silence never proves removal. |
| 11 | Nov 13 | Define a perception adapter yielding the validated observation contract. | Replay adapter works without network, model weights or GPU. |
| 12 | Nov 14 | Add optional video reader with source timestamps. | Tiny authorized clip or generated frames; non-monotonic timestamps handled. |
| 13 | Nov 15 | Check model feasibility on available hardware. | Log hardware, checkpoint permission, revision, resolution, memory and measured throughput, or exact blocker. |
| 14 | Nov 16 | Integrate one text-prompted segmenter/tracker if feasible. | Mask and timestamps from a short approved clip; otherwise strengthen adapter contract checks. |
| 15 | Nov 17 | Connect a visible object's track to a zone. | Clip timestamp and zone agreement checked by hand; replay path maintained. |
| 16 | Nov 18 | Add explicit missing and reobserved states. | Short occlusion changes visibility without fabricating confirmed movement. |
| 17 | Nov 19 | Implement a position-and-gap association baseline. | Reassociation choices can be inspected on labeled examples. |
| 18 | Nov 20 | Add a guarded appearance-matching experiment. | Compare on identical detections; if no encoder is available, prepare paired evaluation cases. |
| 19 | Nov 21 | Record temporal spatial relations in image space. | LEFT_OF intervals close when either observation becomes stale. |
| 20 | Nov 22 | Query a historical snapshot. | Snapshot before and after a move gives different supported answers. |
| 21 | Nov 23 | Add narrow natural-language query patterns. | Last-seen and changed-zone requests compile into validated operations; unsupported prompts abstain. |
| 22 | Nov 24 | Expose read-only query operations through a local API. | Valid and malformed calls checked without executing arbitrary SQL or opening arbitrary files. |
| 23 | Nov 25 | Add an evidence viewer or playable local evidence link. | A result opens its recording at the cited time; unknown media is rejected. |
| 24 | Nov 26 | Freeze an evaluation set split by recording session. | Manifest with event/object labels, unanswerable cases and data provenance. |
| 25 | Nov 27 | Benchmark event and query accuracy. | Report raw counts, event precision/recall, answer correctness and unsupported answers. |
| 26 | Nov 28 | Compare against latest-frame or frame-only retrieval. | Same questions and held-out recordings; document both wins and losses. |
| 27 | Nov 29 | Profile the slowest stage and attempt one targeted fix. | Before/after measurement on the same input and hardware or documented negative result. |
| 28 | Nov 30 | Audit inputs, artifact paths, dependencies and media handling. | Record findings, fixes and unresolved risks with test references. |
| 29 | Dec 1 | Reproduce a clean install and run the end-to-end demo. | Setup transcript, sample queries, clip provenance and limitations. |
| 30 | Dec 2 | Prepare the first release report and handoff. | Verified feature list, reproducible metrics, demo evidence, deferred issues and final status. |

## Decisions and gates

- The fixture demonstrates storage and querying, **not** perception. Report synthetic and camera-derived results separately. If video, GPU or checkpoint access is unavailable, continue the CPU/replay path and record perception as blocked.
- Reserve depth in metres, general VLM reasoning, robotics and cross-camera identity for later milestones. No “real-time” or metric claims without measured evidence.
- For changes spanning roles, development owns implementation, testing checks positive/negative cases, QA reproduces user-visible behavior and security reviews the relevant inputs and permissions. Let the coordinator integrate one coherent change after resolving findings.
- For each accepted increment log test evidence, the actual commit/PR link when available, and the next decision. Mirror to Notion after access to the destination is confirmed. Never count a local commit as a GitHub push or an attempted sync as a successful Notion update.
