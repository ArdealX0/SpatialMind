# Local evidence viewer

Render the existing, recording-scoped `last_seen` result as a standalone HTML
page. No dependencies, server, network access, or browser launch are required.
The page shows source metadata and the last observed disclaimer. It does not
infer the object's current position or verify the supplied observations.

Create a UTF-8 JSON manifest that maps exact video IDs to local media paths:

```json
{"workbench_demo": "recordings/workbench.webm"}
```

Then run:

```sh
python -m spatialmind.evidence --db workbench.sqlite --media-root /path/to/media --manifest /path/to/manifest.json --video workbench_demo --object-id bottle_01 > evidence.html
```

Open the resulting HTML file manually in a browser that supports local media.
Its video source is an escaped absolute `file:` URI with `#t=seconds`. On
`loadedmetadata`, JavaScript sets `currentTime` from the recorded `t_ms / 1000`.
The fragment preserves integer-millisecond precision; browser seek APIs use
floating-point seconds, so extremely large timestamps can lose precision.
An out-of-duration timestamp or failed playback/seek is reported on the page;
source metadata remains visible. Browser local-file policies and installed
codecs can prevent playback. This command does not transcode or inspect media
content, and a supported filename extension does not guarantee a supported codec.

## Input and output contract

All five flags are required. The SQLite database must already exist and is
opened with SQLite `mode=ro`; there is no schema initialization or write.
Video and object IDs are exact, nonempty printable strings of at most 512
characters. The query always filters by both IDs.

The manifest is operator-selected, bounded to 65,536 bytes and 1–256 entries.
It must be one JSON object with unique keys and string values. Every registration
is validated, including unused entries. Media paths are printable relative POSIX
paths of at most 4,096 characters, with a lowercase `.webm` or `.mp4` extension.
Empty, `.` and `..` components, absolute paths, backslashes, colons, percent signs,
query strings and fragments are rejected. The media root must exist as a
directory. Each resolved media target must be an existing regular file inside
the resolved root. Symlinks resolving outside that root are rejected; contained
symlinks are accepted. Unknown video IDs are rejected before reading SQLite.

Successful commands print only a complete self-contained HTML document to stdout
and exit 0. A registered video with no matching observation produces a page
explaining that evidence is missing, with no video player, and also exits 0.
Invalid inputs, missing files, malformed manifests and database errors print an
error to stderr, emit no HTML, and exit 2. Shell redirection may still create an
empty destination file on failure.

The HTML uses escaped text/attribute values and embeds no source strings into
JavaScript. It has no external resources and its content security policy permits
only local media and its inline script/style. It includes local absolute paths
and observation metadata, so keep the generated HTML private alongside the
source footage. The manifest and media directory must remain under operator
control while the page is used: validation is a point-in-time check, not a
sandbox against later filesystem changes.

## Python helpers

`load_manifest(manifest, media_root)` returns a mapping of IDs to resolved
`pathlib.Path` files. `get_evidence(db_path, media_root, manifest, video,
object_id)` returns `status` (`answered` or `evidence_missing`), `video`,
`object_id`, `media_uri` and `observation` (the `last_seen` dictionary or `None`).
`render_html(evidence)` renders that result without filesystem or database I/O.
The renderer expects the validated result from `get_evidence`, not arbitrary
untrusted Python dictionaries.
