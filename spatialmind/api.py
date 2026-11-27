"""Loopback-only, read-only HTTP access to controlled-language queries."""
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import socket
import sqlite3

from .queries import compile_request, _execute

MAX_BODY_BYTES = 16_384
MAX_RESPONSE_BYTES = 1_048_576
MAX_QUERY_OBSERVATIONS = 10_000
REQUEST_TIMEOUT_SECONDS = 5


class QueryLimitError(ValueError):
    pass


def query(database_uri, payload):
    """Validate one fixed-schema request, then dispatch a compiled read-only query."""
    if not isinstance(payload, dict) or set(payload) != {"video", "prompt"}:
        raise ValueError("invalid request fields")
    compiled = compile_request(payload["prompt"], payload["video"])
    if compiled is None:
        return {"status": "unsupported", "reason": "unsupported_pattern"}
    with closing(sqlite3.connect(database_uri, uri=True, timeout=1)) as db:
        db.row_factory = sqlite3.Row
        # Keep the cap check and evidence query on one read snapshot.
        db.execute("BEGIN")
        if compiled["operation"] == "zone_changes":
            parameters = compiled["parameters"]
            excess = db.execute("""
                SELECT 1 FROM observations WHERE video=? AND object_id=?
                LIMIT 1 OFFSET ?
            """, (parameters["video"], parameters["object_id"],
                  MAX_QUERY_OBSERVATIONS)).fetchone()
            if excess is not None:
                raise QueryLimitError("query observation limit exceeded")
        return _execute(db, compiled)


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON constant")


def make_server(database, port=8765):
    """Bind only IPv4 loopback; the database is configured once, never by requests."""
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("port must be an integer from 0 to 65535")
    database_uri = Path(database).resolve().as_uri() + "?mode=ro"

    class Handler(BaseHTTPRequestHandler):
        server_version = "SpatialMind"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

        def log_message(self, format, *args):
            # Do not log prompt/video values or request paths.
            pass

        def _send(self, status, value):
            body = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
            if len(body) > MAX_RESPONSE_BYTES:
                status = 422
                body = b'{"error":"response_limit_exceeded"}'
            self.close_connection = True
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                try:
                    self.wfile.write(body)
                except OSError:
                    pass

        def _error(self, status, code):
            self._send(status, {"error": code})

        def send_error(self, code, message=None, explain=None):
            # Normalize stdlib parser/unknown-method errors without reflecting input.
            if code == 501:
                return self._error(405, "method_not_allowed")
            self._error(code, "http_protocol_error")

        def do_POST(self):
            if self.headers.get_all("Origin"):
                return self._error(403, "origin_not_allowed")
            hosts = self.headers.get_all("Host", [])
            allowed = {f"127.0.0.1:{self.server.server_port}",
                       f"localhost:{self.server.server_port}"}
            if len(hosts) != 1 or hosts[0] not in allowed:
                return self._error(403, "host_not_allowed")
            if self.path != "/query":
                return self._error(404, "not_found")
            if self.headers.get_all("Transfer-Encoding"):
                return self._error(400, "transfer_encoding_not_supported")
            lengths = self.headers.get_all("Content-Length", [])
            if not lengths:
                return self._error(411, "content_length_required")
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                return self._error(400, "invalid_content_length")
            if len(lengths[0]) > 10 or int(lengths[0]) > MAX_BODY_BYTES:
                return self._error(413, "body_too_large")
            types = self.headers.get_all("Content-Type", [])
            if len(types) != 1 or types[0].lower() not in (
                "application/json", "application/json; charset=utf-8",
            ):
                return self._error(415, "unsupported_content_type")
            length = int(lengths[0])
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    return self._error(400, "incomplete_body")
                payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys,
                                     parse_constant=_reject_constant)
                result = query(database_uri, payload)
            except (socket.timeout, TimeoutError):
                return self._error(408, "request_timeout")
            except QueryLimitError:
                return self._error(422, "query_limit_exceeded")
            except (ValueError, RecursionError):
                return self._error(400, "invalid_request")
            except (sqlite3.Error, OSError):
                return self._error(503, "database_unavailable")
            self._send(200, result)

        def do_GET(self):
            self._error(405, "method_not_allowed")

        do_HEAD = do_GET
        do_OPTIONS = do_GET
        do_PUT = do_GET
        do_PATCH = do_GET
        do_DELETE = do_GET
        do_TRACE = do_GET
        do_CONNECT = do_GET

    return HTTPServer(("127.0.0.1", port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        with make_server(args.db, args.port) as server:
            print(f"SpatialMind API on http://127.0.0.1:{server.server_port}/query", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except (ValueError, OSError) as exc:
        parser.exit(2, f"API could not start: {type(exc).__name__}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
