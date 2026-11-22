"""Compare complete, paired identity predictions against independent case labels."""
import argparse
import json
import sys
from pathlib import Path

MAX_BYTES = 1_048_576
MAX_CASES = 1000


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and value.isprintable() and len(value) <= 512


def _outcome(value, candidates):
    if not isinstance(value, dict) or set(value) != {"status", "object_id"}:
        raise ValueError("outcome requires exactly status and object_id")
    status, object_id = value["status"], value["object_id"]
    if status not in ("matched", "ambiguous", "unmatched"):
        raise ValueError("invalid outcome status")
    if status == "matched":
        if not _text(object_id) or object_id not in candidates:
            raise ValueError("matched object_id must be a supplied candidate")
    elif object_id is not None:
        raise ValueError("abstaining outcome object_id must be null")
    return dict(value)


def _cases(manifest):
    if (not isinstance(manifest, dict) or set(manifest) != {"provenance", "cases"}
            or not _text(manifest["provenance"])):
        raise ValueError("case manifest requires provenance and cases")
    rows = manifest["cases"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CASES:
        raise ValueError("provide 1 to 1000 cases")
    cases = {}
    for row in rows:
        if (not isinstance(row, dict) or not {"case_id", "candidate_ids", "expected"} <= set(row)
                or set(row) - {"case_id", "candidate_ids", "expected", "context"}):
            raise ValueError("invalid case fields")
        case_id = row["case_id"]
        if not _text(case_id) or case_id in cases:
            raise ValueError("case IDs must be valid and unique")
        candidates = row["candidate_ids"]
        if (not isinstance(candidates, list) or len(candidates) > 100
                or any(not _text(value) for value in candidates)
                or len(set(candidates)) != len(candidates)):
            raise ValueError("candidate IDs must be a unique array of at most 100 strings")
        if "context" in row and not isinstance(row["context"], dict):
            raise ValueError("context must be an object")
        cases[case_id] = {
            "candidate_ids": candidates,
            "expected": _outcome(row["expected"], candidates),
        }
    return cases


def _predictions(run, cases):
    if not isinstance(run, dict) or set(run) != {"predictions"}:
        raise ValueError("run requires exactly predictions")
    rows = run["predictions"]
    if not isinstance(rows, list) or len(rows) != len(cases):
        raise ValueError("each run must predict every case exactly once")
    predictions = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"case_id", "status", "object_id"}:
            raise ValueError("prediction requires case_id, status and object_id")
        case_id = row["case_id"]
        if not _text(case_id) or case_id not in cases or case_id in predictions:
            raise ValueError("prediction case IDs must be known and unique")
        predictions[case_id] = _outcome(
            {"status": row["status"], "object_id": row["object_id"]},
            cases[case_id]["candidate_ids"],
        )
    return predictions


def compare_runs(manifest, baseline=None, appearance=None):
    """Compare supplied outputs; never execute a model or generate predictions."""
    cases = _cases(manifest)
    baseline = _predictions(baseline, cases) if baseline is not None else None
    appearance = _predictions(appearance, cases) if appearance is not None else None
    totals = {}
    for name, run in (("baseline", baseline), ("appearance", appearance)):
        if run is None:
            totals[name] = None
            continue
        correct = false_links = correct_abstentions = predicted_matches = 0
        for case_id, case in cases.items():
            prediction, expected = run[case_id], case["expected"]
            exact = prediction == expected
            correct += exact
            is_match = prediction["status"] == "matched"
            predicted_matches += is_match
            false_links += is_match and not exact
            correct_abstentions += not is_match and expected["status"] != "matched"
        totals[name] = {
            "correct": correct, "incorrect": len(cases) - correct,
            "false_links": false_links, "correct_abstentions": correct_abstentions,
            "predicted_matches": predicted_matches, "accuracy": correct / len(cases),
        }
    details = []
    paired = baseline is not None and appearance is not None
    counts = {"improved": 0, "regressed": 0, "unchanged": 0} if paired else None
    for case_id in sorted(cases):
        expected = cases[case_id]["expected"]
        old = baseline[case_id] if baseline is not None else None
        new = appearance[case_id] if appearance is not None else None
        verdict = None
        if paired:
            old_correct, new_correct = old == expected, new == expected
            verdict = "improved" if new_correct and not old_correct else (
                "regressed" if old_correct and not new_correct else "unchanged")
            counts[verdict] += 1
        details.append({"case_id": case_id, "expected": expected,
                        "baseline": old, "appearance": new, "verdict": verdict})
    return {
        "case_count": len(cases), **totals, "paired_counts": counts, "cases": details,
        "baseline_status": "NOT_RUN" if baseline is None else "SUPPLIED",
        "appearance_status": "NOT_RUN" if appearance is None else "SUPPLIED",
        "accuracy_delta": (totals["appearance"]["accuracy"] - totals["baseline"]["accuracy"])
        if paired else None,
    }


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON constant")


def _load(path):
    with Path(path).open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("evaluation file exceeds 1 MiB")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys,
                          parse_constant=_reject_constant)
    except RecursionError as exc:
        raise ValueError("evaluation file nesting is too deep") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("baseline", type=Path, nargs="?")
    parser.add_argument("appearance", type=Path, nargs="?")
    args = parser.parse_args(argv)
    try:
        result = compare_runs(_load(args.cases),
                              _load(args.baseline) if args.baseline is not None else None,
                              _load(args.appearance) if args.appearance is not None else None)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
