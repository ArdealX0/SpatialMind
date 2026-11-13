# Synthetic occlusion and look-alike acceptance cases

These fixtures exercise storage and query behavior with supplied identities.
They contain no camera footage, model predictions or real-world performance
measurements. The scenario names describe an imagined scene; the observation
stream alone does not establish whether an occlusion occurred.

Run from the repository root with a fresh local database:

```sh
python -m spatialmind --db scenarios.sqlite ingest examples/synthetic_occlusion.jsonl
python -m spatialmind --db scenarios.sqlite ingest examples/synthetic_lookalikes.jsonl
python -m spatialmind --db scenarios.sqlite history bottle_01 --video occlusion_demo
python -m spatialmind --db scenarios.sqlite zone-changes bottle_01 --video occlusion_demo
python -m spatialmind --db scenarios.sqlite last-seen bottle_left --video lookalike_demo
python -m spatialmind --db scenarios.sqlite history unresolved_01 --video lookalike_demo
```

The imports insert seven and six observations respectively on a fresh database.
The JSONL files follow the existing observation contract. Replaying them is
idempotent.

## Unresolved location and a minute without observations

In `synthetic_occlusion.jsonl`, one caller-supplied object appears on three
tracklets. Its location is desk at 0/1,000 ms, unknown at 2,000 ms, shelf at
3,000/4,000 ms, and drawer at 64,000/65,000 ms.

The unknown location resets zone-change comparison. The 60,000 ms gap from the
last shelf observation to the first drawer observation also resets comparison
under the default 5,000 ms maximum gap. The default zone-change query returns
`[]`, despite different zones on either side of these uncertain intervals.

`unknown` means unresolved location, not invisible. During the minute-long gap
there are no observations at all: no synthetic disappearance, removal or
visibility-state record is inserted. History contains only the seven supplied
rows and preserves the three original tracklet IDs. Last-seen returns the drawer
sighting at 65,000 ms; it does not establish the object's current position.

The caller has assigned all three tracklets to `bottle_01`. This is an explicit
fixture assumption, not a demonstration of automatic re-identification.
Changing debounce/gap options can change event results; these expectations use
defaults.

## Similar appearance does not establish identity

In `synthetic_lookalikes.jsonl`, `bottle_left` and `bottle_right` have the
same label, `blue bottle`, but different object IDs and original tracklets.
After a long gap a new tracklet appears. Its connection to either prior bottle
is unresolved, so the fixture uses a separate provisional ID, `unresolved_01`.

The history of each prior bottle remains at 0/1,000 ms. Their last-seen results
remain at 1,000 ms; neither is overwritten by the new sighting. The unresolved
history contains only 64,000/65,000 ms with `track_reappeared`. All three objects
have empty default zone-change arrays.

The prefix `unresolved_` is a naming convention in this fixture, not a reserved
runtime state. The engine does not infer ambiguity, generate candidates, or
assign special meaning to that ID. It stores the explicit supplied identities
and never merges them merely because labels match. There is no API to resolve
this provisional ID into a prior object, revise links, or infer removal.

## Expected-outcome manifest

`examples/scenario_expectations.json` is a **human-authored** acceptance oracle
for these fixtures. Its paths are relative to the examples directory. It names
expected histories, last-seen evidence and event outputs for repeatable checks.

For look-alikes, `identity_status: "ambiguous"` and the two candidate object IDs
are explicit annotations describing the intentionally unresolved association.
They are not output from a running perception or association algorithm. They
also do not prove the new sighting is one of those candidates; an unseen third
object remains possible. No probability or confidence is assigned.

The manifest is not accepted by `ingest` and is not stored in the database.
The CLI still queries exact object IDs and recording scopes. Automatic occlusion
recognition, missing/reobserved states and learned association remain unimplemented.
