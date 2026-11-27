"""Real loopback HTTP requests exercise the fixed read-only query boundary."""
from contextlib import closing
import http.client
import io
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from spatialmind.api import make_server
from spatialmind.store import connect, ingest


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/"observations.sqlite"
        with closing(connect(self.db)) as db:
            ingest(db, io.BytesIO(b'{"video":"v","object_id":"bottle","label":"blue bottle","t_ms":1000,"zone":"desk"}\n'))
        self.server = make_server(self.db, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, payload=None, *, raw=None, headers=None, path="/query", method="POST"):
        body = raw if raw is not None else json.dumps(payload).encode()
        final_headers = {"Content-Type":"application/json"}
        final_headers.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=final_headers)
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(data), dict(response.getheaders())
        finally:
            connection.close()

    def test_evidence_missing_unsupported_and_no_database_mutation(self):
        before = self.db.read_bytes()
        code, result, headers = self.request({"video":"v","prompt":'Where was "bottle" last seen?'})
        self.assertEqual(code,200)
        self.assertEqual(result["evidence"]["t_ms"],1000)
        self.assertEqual(headers["Cache-Control"],"no-store")
        self.assertEqual(self.request({"video":"v","prompt":'Where was "absent" last seen?'})[1]["status"],"evidence_missing")
        self.assertEqual(self.request({"video":"v","prompt":"Delete everything"})[1]["status"],"unsupported")
        self.assertEqual(self.db.read_bytes(),before)

    def test_strict_request_schema_json_methods_and_paths(self):
        for raw in (b'{"video":"v","video":"w","prompt":"x"}', b'{"video":NaN,"prompt":"x"}',
                    b'{"video":"v","prompt":"x","db":"/etc/passwd"}', b"\xff", b"[]"):
            with self.subTest(raw=raw):
                self.assertEqual(self.request(raw=raw)[0],400)
        self.assertEqual(self.request({},path="/query?db=other")[0],404)
        self.assertEqual(self.request({},method="GET")[0],405)
        status, result, headers = self.request({}, method="BREW")
        self.assertEqual(status,405)
        self.assertEqual(result,{"error":"method_not_allowed"})
        self.assertEqual(headers["Content-Type"],"application/json; charset=utf-8")
        self.assertEqual(self.request({},headers={"Content-Type":"text/plain"})[0],415)
        self.assertEqual(self.request(raw=b" "*16385)[0],413)

    def test_browser_guards_and_no_cors(self):
        self.assertEqual(self.request({},headers={"Origin":"http://evil.example"})[0],403)
        status, _, headers = self.request({},headers={"Host":"evil.example"})
        self.assertEqual(status,403)
        self.assertNotIn("Access-Control-Allow-Origin",headers)
        self.assertEqual(self.request({},method="OPTIONS")[0],405)

    def test_http_framing_rejected(self):
        for headers, expected in (("Content-Type: application/json\r\n",411),
                                  ("Content-Length: 2\r\nContent-Length: 2\r\n",400),
                                  ("Transfer-Encoding: chunked\r\nContent-Length: 2\r\n",400)):
            with socket.create_connection(("127.0.0.1",self.server.server_port),timeout=5) as sock:
                sock.sendall((f"POST /query HTTP/1.1\r\nHost: 127.0.0.1:{self.server.server_port}\r\n"
                              +headers+"\r\n{}").encode())
                response = http.client.HTTPResponse(sock)
                response.begin()
                self.assertEqual(response.status,expected)
                response.read()

    def test_no_file_creation_unsupported_no_db_open_and_safe_errors(self):
        self.db.unlink()
        with patch("spatialmind.api.sqlite3.connect",side_effect=AssertionError("must not open")):
            self.assertEqual(self.request({"video":"v","prompt":"unsupported words"})[1]["status"],"unsupported")
        status, result, _ = self.request({"video":"v","prompt":'Where was "bottle" last seen?'})
        self.assertEqual(status,503)
        self.assertEqual(result,{"error":"database_unavailable"})
        self.assertFalse(self.db.exists())

    def test_history_cap_and_query_share_snapshot_under_external_writes(self):
        from spatialmind.queries import _execute as execute
        with closing(sqlite3.connect(self.db)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
        def add_after_preflight(db, compiled):
            with closing(sqlite3.connect(self.db)) as writer:
                writer.executemany(
                    "INSERT INTO observations (video,object_id,t_ms,label,zone) VALUES (?,?,?,?,?)",
                    [("v","bottle",2000,"blue bottle","shelf"),
                     ("v","bottle",3000,"blue bottle","shelf")],
                )
                writer.commit()
            return execute(db, compiled)
        with patch("spatialmind.api.MAX_QUERY_OBSERVATIONS",1):
            with patch("spatialmind.api._execute",side_effect=add_after_preflight):
                status,result,_=self.request({"video":"v","prompt":'Show zone changes for "bottle"'})
            self.assertEqual(status,200)
            self.assertEqual(result["evidence"],[])
            self.assertEqual(self.request({"video":"v","prompt":'Show zone changes for "bottle"'})[0],422)

    def test_query_and_response_limits(self):
        with patch("spatialmind.api.MAX_QUERY_OBSERVATIONS",0):
            status,result,_=self.request({"video":"v","prompt":'Show zone changes for "bottle"'})
            self.assertEqual(status,422)
            self.assertEqual(result["error"],"query_limit_exceeded")
        with patch("spatialmind.api.MAX_RESPONSE_BYTES",32):
            status,result,_=self.request({"video":"v","prompt":'Where was "bottle" last seen?'})
            self.assertEqual(status,422)
            self.assertEqual(result["error"],"response_limit_exceeded")


if __name__ == "__main__":
    unittest.main()
