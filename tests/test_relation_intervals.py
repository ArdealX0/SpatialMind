"""Freshness-bound relations on supplied CPU-only synthetic positions."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from spatialmind.relation_intervals import left_of_intervals

ROOT = Path(__file__).resolve().parents[1]


def row(obj, t, x=None, video="demo"):
    value = dict(video=video, object_id=obj, t_ms=t)
    if x is not None:
        value.update(x=x, y=.5)
    return value


def spans(rows, **kwargs):
    return [(r["start_ms"], r["end_ms"]) for r in
            left_of_intervals(rows, "demo", "a", "b", end_ms=kwargs.pop("end_ms", 10000), **kwargs)]


class RelationTests(unittest.TestCase):
    def test_expiry_horizon_and_asof_without_future_leakage(self):
        rows = [row("a",1000,.2), row("b",1000,.8), row("a",3000,.3)]
        self.assertEqual(spans(rows), [(1000,6000)])
        self.assertEqual(spans(rows,end_ms=4000), [(1000,4000)])
        self.assertEqual(spans(rows,at_ms=1000), [(1000,6000)])
        self.assertEqual(spans(rows,at_ms=6000), [])
        self.assertEqual(spans(rows,at_ms=999), [])
        self.assertEqual(spans(rows,end_ms=0), [])

    def test_batched_out_of_order_ties_reversal_unknown_and_gap(self):
        rows = [row("a",1000,.2),row("b",1000,.8),
                row("a",2000,.7),row("b",2000,.9),
                row("a",3000,.9),row("b",3000,.9),
                row("a",4000,1),row("b",4000,.1),
                row("a",5000,.1),row("b",5000,.8),row("a",5500),
                row("a",7000,.1),row("b",7000,.8)]
        original = copy.deepcopy(rows)
        self.assertEqual(spans(list(reversed(rows))), [(1000,3000),(5000,5500),(7000,10000)])
        self.assertEqual(rows,original)
        self.assertEqual(spans([row("a",0,.2),row("b",0,.8),row("a",6000,.2),row("b",6000,.8)]),
                         [(0,5000),(6000,10000)])
        self.assertEqual(spans([row("a",0,.2),row("b",0,.8),row("a",5000,.2),row("b",5000,.8)]),
                         [(0,10000)])

    def test_scope_and_validation(self):
        self.assertEqual(spans([row("a",0,.2),row("b",0,.8,video="other")]), [])
        bad = [dict(row("a",0,.2),x=True),dict(row("a",0,.2),x=float("nan")),
               dict(row("a",0),x=.2),dict(row("a",0,.2),t_ms=True),
               dict(row("a",0,.2),label="unexpected")]
        for value in bad:
            with self.assertRaises(ValueError):
                spans([value])
        with self.assertRaises(ValueError):
            spans([row("a",0,.2)]*2)
        with self.assertRaises(ValueError):
            spans([row("a",i,.2) for i in range(10001)])
        for options in ({"max_age_ms":0},{"max_age_ms":True},{"end_ms":-1},{"at_ms":True}):
            with self.assertRaises(ValueError):
                spans([],**options)
        with self.assertRaises(ValueError):
            left_of_intervals([], "demo","a","a",end_ms=1000)

    def test_cli_fixture_and_atomic_errors(self):
        command=[sys.executable,"-S","-m","spatialmind.relation_intervals"]
        options=["--video","relation_demo","--subject","bottle","--object","laptop","--end-ms","10000"]
        result=subprocess.run(command+["examples/left_of_samples.jsonl"]+options,cwd=ROOT,
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual([(r["start_ms"],r["end_ms"]) for r in json.loads(result.stdout)],
                         [(1000,6000),(7000,8000)])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"bad.jsonl"
            for raw in (b'{"video":"one","video":"two"}',b" "*16385,b"\xff"):
                path.write_bytes(raw)
                result=subprocess.run(command+[str(path)]+options,cwd=ROOT,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,2)
                self.assertEqual(result.stdout,"")


if __name__ == "__main__":
    unittest.main()
