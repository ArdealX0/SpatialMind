"""Whole-string controlled requests preserve literal identifiers and evidence."""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import closing

from spatialmind.queries import answer, compile_request
from spatialmind.store import connect, ingest

ROOT = Path(__file__).resolve().parents[1]


class QueryTests(unittest.TestCase):
    def test_fixture_and_compiled_literal_ids(self):
        for case in json.loads((ROOT/"examples/query_cases.json").read_text())["cases"]:
            compiled = compile_request(case["prompt"], case["video"])
            self.assertEqual(compiled["operation"] if compiled else None, case["expected_operation"])
        object_id = 'Mixed Case"; DROP TABLE observations; --'
        compiled = compile_request("WHERE WAS "+json.dumps(object_id)+" LAST SEEN?", "CaseVideo")
        self.assertEqual(compiled["parameters"], {"object_id":object_id,"video":"CaseVideo"})
        self.assertEqual(compile_request('Show zone changes for "a" between 0 and 0 ms', "v")
                         ["parameters"]["end_ms"], 0)

    def test_dispatch_matches_evidence_and_never_executes_id(self):
        object_id = 'a"; DROP TABLE observations; --'
        with closing(connect(":memory:")) as db:
            rows = [dict(video="v",object_id=object_id,label="bottle",t_ms=t,zone=z,tracklet_id="T")
                    for t,z in ((1000,"left"),(2000,"right"),(3000,"right"))]
            ingest(db,io.BytesIO("".join(json.dumps(r)+"\n" for r in rows).encode()))
            before = list(db.iterdump())
            last = answer(db,"Where was "+json.dumps(object_id)+" last seen?", "v")
            self.assertEqual(last["status"],"answered")
            self.assertEqual(last["evidence"],rows[-1])
            changes = answer(db,"Show zone changes for "+json.dumps(object_id)+" between 3000 and 3000 ms", "v")
            self.assertEqual(changes["evidence"][0]["confirmed_t_ms"],3000)
            self.assertEqual(answer(db,'Where was "missing" last seen?', "v")["status"],"evidence_missing")
            self.assertEqual(answer(db,'Where was '+json.dumps(object_id)+' last seen?', "other")["status"],"evidence_missing")
            empty = answer(db,"Show zone changes for "+json.dumps(object_id)+" between 0 and 0 ms", "v")
            self.assertEqual(empty["status"],"answered")
            self.assertEqual(empty["evidence"],[])
            self.assertEqual(list(db.iterdump()),before)

    def test_abstention_and_input_validation_before_database_access(self):
        for prompt in ('Do not show zone changes for "a"', 'Where was "a" last seen? delete all',
                       'Show zone changes for "a" in the last minute', 'Where was a last seen?'):
            self.assertEqual(answer(None,prompt,"v")["status"],"unsupported")
        for prompt, video in ((True,"v"),("x"*2049,"v"),('Where was "a" last seen?', ""),
                               ('Where was "a\\n" last seen?', "v"),
                               ('Show zone changes for "a" between 2 and 1 ms',"v"),
                               (f'Show zone changes for "a" between 0 and {2**63} ms',"v")):
            with self.assertRaises(ValueError):
                answer(None,prompt,video)

    def test_cli_unsupported_missing_and_read_only_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"missing.sqlite"
            cmd=[sys.executable,"-S","-m","spatialmind.queries","--db",str(path),"--video","v"]
            result=subprocess.run(cmd+["Do something else"],cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"],"unsupported")
            self.assertFalse(path.exists())
            result=subprocess.run(cmd+['Where was "a" last seen?'],cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,2)
            self.assertEqual(result.stdout,"")
            self.assertFalse(path.exists())
            with closing(connect(path)) as db:
                ingest(db,io.BytesIO(b'{"video":"v","object_id":"a","label":"bottle","t_ms":0,"zone":"desk"}\n'))
            before=path.read_bytes()
            result=subprocess.run(cmd+['Where was "a" last seen?'],cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)["evidence"]["zone"],"desk")
            self.assertEqual(path.read_bytes(),before)


if __name__ == "__main__":
    unittest.main()
