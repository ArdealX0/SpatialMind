"""Validate an authored synthetic evaluation manifest without running a model."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from .queries import compile_request
from .store import _parse, _unique_keys

MAX_BYTES = 1024 * 1024


def _fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError('expected fields: ' + names)


def _text(value):
    if not isinstance(value, str) or not value.strip() or not value.isprintable() or len(value) > 512:
        raise ValueError('expected nonempty printable text of at most 512 characters')


def _list(value, limit, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= limit:
        raise ValueError(f'expected list with {minimum}..{limit} entries')


def _time(value):
    if type(value) is not int or not 0 <= value < 2**63:
        raise ValueError('expected nonnegative 64-bit timestamp')


def validate_manifest(manifest):
    """Check authored labels and references, never calculate expected answers."""
    _fields(manifest, 'version provenance sessions')
    if type(manifest['version']) is not int or manifest['version'] != 1:
        raise ValueError('version must be 1')
    _fields(manifest['provenance'], 'kind labels')
    if manifest['provenance'] != {'kind': 'synthetic', 'labels': 'authored_not_inference'}:
        raise ValueError('provenance must declare synthetic authored_not_inference labels')
    _list(manifest['sessions'], 100, 3)
    seen_sessions, seen_videos, seen_cases = set(), set(), set()
    counts = {split: dict(sessions=0, objects=0, observations=0, events=0, query_cases=0)
              for split in ('dev', 'test')}
    for session in manifest['sessions']:
        _fields(session, 'session_id split video objects observations expected_events query_cases')
        for key, seen in (('session_id', seen_sessions), ('video', seen_videos)):
            _text(session[key])
            if session[key] in seen:
                raise ValueError(f'duplicate {key}; sessions and videos must be independent')
            seen.add(session[key])
        split = session['split']
        if not isinstance(split, str) or split not in counts:
            raise ValueError('split must be dev or test')
        objects = {}
        _list(session['objects'], 100, 1)
        for obj in session['objects']:
            _fields(obj, 'object_id label')
            _text(obj['object_id']); _text(obj['label'])
            if obj['object_id'] in objects:
                raise ValueError('duplicate object_id')
            objects[obj['object_id']] = obj['label']
        rows = {}
        tracklets = {}
        _list(session['observations'], 5000, 1)
        for row in session['observations']:
            _parse(json.dumps(row, allow_nan=False).encode('utf-8'))
            if row['video'] != session['video'] or objects.get(row['object_id']) != row['label']:
                raise ValueError('observation video/object/label does not match session')
            key = (row['object_id'], row['t_ms'])
            if key in rows:
                raise ValueError('duplicate observation object/time')
            rows[key] = row
            if 'tracklet_id' in row:
                prior = tracklets.setdefault(row['tracklet_id'], row['object_id'])
                if prior != row['object_id']:
                    raise ValueError('tracklet belongs to multiple objects')
        def event(value):
            _fields(value, 'type video object_id from_zone to_zone before_t_ms after_t_ms confirmed_t_ms')
            if value['type'] != 'ZONE_CHANGED' or value['video'] != session['video']:
                raise ValueError('invalid event type/video')
            _text(value['object_id']); _text(value['from_zone']); _text(value['to_zone'])
            if value['object_id'] not in objects or value['from_zone'] == value['to_zone']:
                raise ValueError('invalid event object/zones')
            times = [value[k] for k in ('before_t_ms', 'after_t_ms', 'confirmed_t_ms')]
            for t in times:
                _time(t)
                if (value['object_id'], t) not in rows:
                    raise ValueError('event time must reference an observation of its object')
            if not times[0] < times[1] <= times[2]:
                raise ValueError('event times must be ordered')
            for t, zone in zip(times, (value['from_zone'], value['to_zone'], value['to_zone'])):
                if rows[(value['object_id'], t)]['zone'] != zone:
                    raise ValueError('event zone does not match referenced observation')
        _list(session['expected_events'], 5000)
        event_keys = set()
        for value in session['expected_events']:
            event(value)
            key = json.dumps(value, sort_keys=True)
            if key in event_keys:
                raise ValueError('duplicate expected event')
            event_keys.add(key)
        _list(session['query_cases'], 1000, 1)
        for case in session['query_cases']:
            _fields(case, 'case_id prompt expected_status expected_evidence')
            _text(case['case_id'])
            if case['case_id'] in seen_cases:
                raise ValueError('duplicate case_id')
            seen_cases.add(case['case_id'])
            compiled = compile_request(case['prompt'], session['video'])
            status, evidence = case['expected_status'], case['expected_evidence']
            if not isinstance(status, str) or status not in ('answered', 'evidence_missing', 'unsupported'):
                raise ValueError('invalid expected_status')
            if (compiled is None) != (status == 'unsupported'):
                raise ValueError('expected_status disagrees with query pattern')
            if status != 'answered':
                if evidence is not None:
                    raise ValueError('non-answered cases require null expected_evidence')
                if status == 'evidence_missing' and any(
                        key[0] == compiled['parameters']['object_id'] for key in rows):
                    raise ValueError('evidence_missing object has embedded observations')
                continue
            object_id = compiled['parameters']['object_id']
            if object_id not in objects:
                raise ValueError('answered case must reference a declared object')
            if compiled['operation'] == 'last_seen':
                if not isinstance(evidence, dict) or evidence.get('object_id') != object_id:
                    raise ValueError('last_seen evidence must reference queried object')
                _time(evidence.get('t_ms'))
                if rows.get((object_id, evidence['t_ms'])) != evidence:
                    raise ValueError('last_seen evidence must reference an embedded observation')
            else:
                _list(evidence, 5000)
                for value in evidence:
                    event(value)
                    if value['object_id'] != object_id or json.dumps(value, sort_keys=True) not in event_keys:
                        raise ValueError('query event must reference an authored expected event')
                    t = value['confirmed_t_ms']
                    params = compiled['parameters']
                    if not params.get('start_ms', 0) <= t <= params.get('end_ms', 2**63 - 1):
                        raise ValueError('query event outside requested interval')
        count = counts[split]
        for key, amount in (('sessions', 1), ('objects', len(objects)), ('observations', len(rows)),
                            ('events', len(session['expected_events'])), ('query_cases', len(session['query_cases']))):
            count[key] += amount
    if any(not count['sessions'] for count in counts.values()):
        raise ValueError('dev and test must both contain sessions')
    return counts


def load_manifest(path):
    """Read at most 1 MiB; digest identifies exact frozen manifest bytes."""
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('manifest exceeds 1 MiB limit')
    def reject_constant(value):
        raise ValueError('nonfinite JSON number: ' + value)
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('nonfinite JSON number')
        return number
    manifest = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_keys,
                          parse_constant=reject_constant, parse_float=finite_float)
    counts = validate_manifest(manifest)
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'version': manifest['version'],
            'provenance': manifest['provenance'], 'splits': counts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args(argv)
    try:
        result = load_manifest(args.manifest)
    except (OSError, ValueError, RecursionError, OverflowError, TypeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
