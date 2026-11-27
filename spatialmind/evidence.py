"""Render last-observed evidence as a standalone, local-only HTML page."""
import argparse
from contextlib import closing
from html import escape
import json
from pathlib import Path
import sqlite3
import sys

from .queries import _identifier
from .store import last_seen

MAX_MANIFEST_BYTES = 65536
MAX_MANIFEST_ENTRIES = 256


def _resolve_existing(path):
    try:
        return Path(path).resolve(strict=True)
    except RuntimeError as exc:
        raise ValueError("media path cannot be resolved") from exc


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key")
        result[key] = value
    return result


def load_manifest(manifest, media_root):
    """Validate every ID/path registration and return resolved local file paths."""
    root = _resolve_existing(media_root)
    if not root.is_dir():
        raise ValueError("media root must be a directory")
    with Path(manifest).open("rb") as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds 65536 bytes")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(data, dict) or not 1 <= len(data) <= MAX_MANIFEST_ENTRIES:
        raise ValueError("manifest must map 1 to 256 video IDs to relative media paths")
    registered = {}
    for video, relative in data.items():
        _identifier(video)
        if (not isinstance(relative, str) or not relative or len(relative) > 4096
                or not relative.isprintable() or any(c in relative for c in "\\:%?#")
                or any(part in ("", ".", "..") for part in relative.split("/"))
                or Path(relative).is_absolute()
                or Path(relative).suffix not in (".webm", ".mp4")):
            raise ValueError("media paths must be plain relative .webm or .mp4 paths")
        target = _resolve_existing(root / relative)
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError("media file must exist inside media root")
        registered[video] = target
    return registered


def get_evidence(db_path, media_root, manifest, video, object_id):
    """Read the latest sighting from an existing SQLite database opened read-only."""
    _identifier(video)
    _identifier(object_id)
    registered = load_manifest(manifest, media_root)
    if video not in registered:
        raise ValueError("unknown video ID in manifest")
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        observation = last_seen(db, object_id=object_id, video=video)
    if observation is not None:
        t_ms = observation.get("t_ms")
        if type(t_ms) is not int or not 0 <= t_ms < 2**63:
            raise ValueError("invalid source timestamp")
    return {"status": "evidence_missing" if observation is None else "answered",
            "video": video, "object_id": object_id,
            "media_uri": registered[video].as_uri(), "observation": observation}


def render_html(evidence):
    """Render escaped metadata and a local video seek; perform no I/O."""
    observation = evidence["observation"]
    details = {"video": evidence["video"], "object_id": evidence["object_id"],
               "media_uri": evidence["media_uri"]}
    player = "<p>No recorded observation was found for this object in this video.</p>"
    if observation is not None:
        t_ms = observation["t_ms"]
        if type(t_ms) is not int or not 0 <= t_ms < 2**63:
            raise ValueError("invalid source timestamp")
        whole_seconds, milliseconds = divmod(t_ms, 1000)
        seconds = str(whole_seconds)
        if milliseconds:
            seconds += "." + f"{milliseconds:03d}".rstrip("0")
        source = escape(evidence["media_uri"] + "#t=" + seconds, quote=True)
        player = (f'<video id="evidence-video" controls preload="metadata" src="{source}"></video>'
                  '<p id="playback-status">Playback depends on local file access and codec support.</p>'
                  '<script>"use strict";\n'
                  'const player = document.getElementById("evidence-video");\n'
                  f'const sourceTimeMs = {t_ms};\n'
                  'player.addEventListener("loadedmetadata", () => {\n'
                  '  try {\n'
                  '    if (Number.isFinite(player.duration) && sourceTimeMs / 1000 > player.duration) {\n'
                  '      document.getElementById("playback-status").textContent = "Source timestamp exceeds media duration.";\n'
                  '    } else { player.currentTime = sourceTimeMs / 1000; }\n'
                  '  } catch (error) {\n'
                  '    document.getElementById("playback-status").textContent = "Unable to seek to source timestamp.";\n'
                  '  }\n'
                  '});\n'
                  'player.addEventListener("error", () => {\n'
                  '  document.getElementById("playback-status").textContent = '
                  '"Unable to play local media. Check file access and codec support.";\n'
                  '});\n</script>')
        details.update(observation)
    metadata = "".join(f"<dt>{escape(str(key))}</dt><dd>{escape(str(value))}</dd>"
                       for key, value in details.items())
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'media-src file:; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; '
            'base-uri \'none\'; form-action \'none\'">'
            '<title>SpatialMind local evidence</title>'
            '<style>body{font:16px system-ui;max-width:900px;margin:2rem auto;padding:0 1rem}'
            'video{width:100%;max-height:65vh}dt{font-weight:bold}dd{overflow-wrap:anywhere;'
            'margin-bottom:1rem}</style></head><body><h1>Last observed evidence</h1>'
            '<p>This is the last recorded observation, not a prediction of the object’s '
            'current position. Source time is relative to the recording.</p>'
            + player + '<h2>Source metadata</h2><dl>' + metadata + '</dl></body></html>\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--media-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--video", required=True)
    parser.add_argument("--object-id", required=True)
    args = parser.parse_args(argv)
    try:
        page = render_html(get_evidence(args.db, args.media_root, args.manifest,
                                        args.video, args.object_id))
    except (ValueError, OSError, sqlite3.Error, RecursionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(page, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
