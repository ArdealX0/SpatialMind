"""Evaluate fixed CPU operations against authored synthetic labels."""
import argparse
from collections import Counter
from contextlib import closing
import io
import json
from pathlib import Path
import re
import sqlite3
import sys

from .eval_set import read_manifest
from .queries import answer
from .store import connect, ingest, zone_changes

STATUSES = ('answered', 'evidence_missing', 'unsupported')


def _canonical(value):
    # JSON serialization preserves distinctions such as true versus 1 and 1.0.
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'))


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def score_events(expected, predicted):
    """Score full exact JSON events as multisets, including repeated predictions."""
    expected = Counter(map(_canonical, expected))
    predicted = Counter(map(_canonical, predicted))
    tp = sum((expected & predicted).values())
    fp = sum((predicted - expected).values())
    fn = sum((expected - predicted).values())
    return dict(tp=tp, fp=fp, fn=fn, total_expected=tp + fn, total_predicted=tp + fp, precision=_ratio(tp, tp + fp),
                recall=_ratio(tp, tp + fn))


def score_queries(cases, predictions):
    """Score aligned answers by exact status and evidence; reject missing answers."""
    cases, predictions = list(cases), list(predictions)
    if len(cases) != len(predictions):
        raise ValueError('one prediction is required per query case')
    groups = {status: dict(correct=0, total=0) for status in STATUSES}
    unsupported = dict(expected=0, predicted=0, correct=0)
    results = []
    answered_on_unanswerable = 0
    for case, prediction in zip(cases, predictions):
        expected_status, predicted_status = case['expected_status'], prediction['status']
        if expected_status not in STATUSES or predicted_status not in STATUSES:
            raise ValueError('invalid query status')
        expected_evidence = case['expected_evidence']
        predicted_evidence = prediction.get('evidence')
        correct = (expected_status == predicted_status
                   and _canonical(expected_evidence) == _canonical(predicted_evidence))
        group = groups[expected_status]
        group['total'] += 1
        group['correct'] += int(correct)
        unsupported['expected'] += int(expected_status == 'unsupported')
        unsupported['predicted'] += int(predicted_status == 'unsupported')
        unsupported['correct'] += int(expected_status == 'unsupported' and correct)
        answered_on_unanswerable += int(expected_status in ('evidence_missing', 'unsupported')
                                       and predicted_status == 'answered')
        results.append(dict(case_id=case['case_id'], expected_status=expected_status,
                            predicted_status=predicted_status, expected_evidence=expected_evidence,
                            predicted_evidence=predicted_evidence, correct=correct))
    for group in groups.values():
        group['accuracy'] = _ratio(group['correct'], group['total'])
    correct = sum(group['correct'] for group in groups.values())
    return dict(correct=correct, total=len(cases), accuracy=_ratio(correct, len(cases)),
                by_expected_status=groups, unsupported=unsupported,
                answered_on_unanswerable=answered_on_unanswerable, results=results)


def run_benchmark(path, split='all', expected_sha256=None):
    """Validate one bounded read, then evaluate independent in-memory sessions."""
    if split not in ('all', 'dev', 'test'):
        raise ValueError('split must be all, dev or test')
    if expected_sha256 is not None and (not isinstance(expected_sha256, str)
            or re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha256) is None):
        raise ValueError('expected_sha256 must contain 64 hexadecimal characters')
    manifest, corpus = read_manifest(path)
    if expected_sha256 is not None and corpus['sha256'] != expected_sha256.lower():
        raise ValueError('manifest SHA-256 does not match expected digest')
    splits = {}
    for selected in (('dev', 'test') if split == 'all' else (split,)):
        expected_events, predicted_events, cases, predictions, sessions = [], [], [], [], []
        for session in manifest['sessions']:
            if session['split'] != selected:
                continue
            with closing(connect(':memory:')) as db:
                payload = '\n'.join(_canonical(row) for row in session['observations']) + '\n'
                ingest(db, io.BytesIO(payload.encode('utf-8')))
                events = []
                for obj in session['objects']:
                    events.extend(zone_changes(db, obj['object_id'], session['video']) or [])
                answers = [answer(db, case['prompt'], session['video'])
                           for case in session['query_cases']]
            sessions.append(dict(session_id=session['session_id'],
                                 expected_events=session['expected_events'], predicted_events=events,
                                 events=score_events(session['expected_events'], events),
                                 queries=score_queries(session['query_cases'], answers)))
            expected_events.extend(session['expected_events']); predicted_events.extend(events)
            cases.extend(session['query_cases']); predictions.extend(answers)
        splits[selected] = dict(counts=corpus['splits'][selected],
                                events=score_events(expected_events, predicted_events),
                                queries=score_queries(cases, predictions), sessions=sessions)
    return dict(corpus=corpus, config=dict(split=split, confirm_observations=2, max_gap_ms=5000),
                splits=splits)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--split', choices=('all', 'dev', 'test'), default='all')
    parser.add_argument('--expected-sha256')
    args = parser.parse_args(argv)
    try:
        result = run_benchmark(args.manifest, args.split, args.expected_sha256)
    except (OSError, ValueError, RecursionError, OverflowError, TypeError, sqlite3.Error) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
