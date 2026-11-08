# Rectangular image zones

The standalone zone classifier maps a supplied image point to a manually defined
region. It does not read a camera, detect an object, estimate depth, or write to
the observation database.

## Coordinate convention

Coordinates are normalized to the range [0, 1]. The top-left image corner is
(0, 0); x increases rightward and y increases downward. A caller must supply a
point already expressed in this convention. The classifier does not choose an
object's centroid or convert pixel coordinates.

Each rectangle has bounds `[x_min, y_min, x_max, y_max]`. Lower edges are
inclusive; upper edges are exclusive unless the upper bound is exactly 1, where
the image's outer edge is included. Thus adjacent rectangles do not both match a
point on their shared edge.

## Configuration

`examples/workbench_zones.json` divides an image into desk-left, desk-right and
shelf regions. The schema is:

```json
{"zones": [{"name": "desk-left", "bounds": [0, 0, 0.5, 0.8]}]}
```

The UTF-8 file is limited to 65,536 bytes (64 KiB) and at most 100 zones.
An empty zones array is valid and always produces `unknown`.
The root must contain exactly `zones`; each zone must contain exactly
`name` and `bounds`. Duplicate JSON keys, missing fields and extra fields
are rejected.

Names must be unique, printable strings with non-whitespace content and at most
512 characters. Names are preserved exactly, without trimming or case
normalization. The exact name `unknown` is reserved.
Bounds must be an array of four finite numbers, excluding booleans, and satisfy
`0 <= min < max <= 1` on both axes. Degenerate or reversed rectangles are invalid.
Overlapping rectangles are permitted; ambiguous points do not receive a label.

## CLI

Run from the repository root:

```sh
python -m spatialmind.zones examples/workbench_zones.json --x 0.25 --y 0.4
```

Stdout is `{"zone": "desk-left"}`. The command exits 0 for every valid
classification, including `unknown`.

| Point or input | Example fixture result |
| --- | --- |
| x=0.5, y=0.4 | `desk-right` |
| x=0.25, y=0.8 | `shelf` |
| x=1, y=1 | `shelf` |
| Finite point outside [0, 1] | `unknown` |
| Both coordinates omitted | `unknown` |

For any valid config, zero matching rectangles or multiple matching rectangles
produce `unknown`. Exactly one match produces its configured name.
Missing both coordinates does not bypass config validation.

Supplying only one coordinate, a nonnumeric value, NaN, infinity, invalid config
or an unreadable file exits 2 with a diagnostic on stderr and no JSON on stdout.
Use `--x=-0.1` if needed to pass a negative coordinate unambiguously.

## Observation integration and limits

A caller can copy the returned zone string into an observation's `zone` field,
then import that observation through the existing ingest command. The classifier
does not perform that integration automatically. The string `unknown` is valid
under the observation contract; it means location is unresolved, not that
the object is absent, invisible or removed. It does not distinguish an overlapping match
from missing coordinates or an out-of-image point.

Use the correct fixed-camera config for each recording. No automatic per-video
binding is implemented. Existing arbitrary observation zone labels remain valid;
this helper does not validate or restrict labels already in the database.

Configs are not stored or versioned in the database. Changing a config does not
reclassify existing observations, and stored zone labels cannot identify which
config produced them. Keep the config alongside the input data if reproducibility
is required. Zone locations are image-relative; they do not establish physical
distances or relationships in 3D.
