# Local read-only query API

For a synthetic example, create a database from the supplied fixture, then start
the standard-library server with that fixed database:

```sh
python -m spatialmind --db observations.sqlite ingest examples/snapshot_samples.jsonl
python -m spatialmind.api --db observations.sqlite --port 8765
```

It binds only 127.0.0.1; there is no configurable non-loopback host. Port 0
requests an available ephemeral port. Stop with Ctrl+C. No dependency installs,
models, public hosting, database creation or migrations occur.

Send one POST to the exact /query path:

```sh
curl http://127.0.0.1:8765/query -H 'Content-Type: application/json' --data '{"video":"snapshot_demo","prompt":"Where was \"bottle\" last seen?"}'
```

The example returns HTTP 200 with `status: "answered"` and source evidence for
the bottle on the shelf at 3,000 ms, preserving `tracklet_id: "track_after"`.
These are supplied synthetic observations, not camera inference.

The JSON body must contain exactly video and prompt. The existing
[controlled-language grammar](QUERIES.md) applies. Literal IDs remain data;
there is no client-selectable database path, SQL statement or operation name.
Database path is fixed at startup and is never derived from requests.

## Responses

HTTP 200 carries the existing structured query result: answered with source
evidence, evidence_missing with null evidence, or unsupported with a reason.
An empty zone-change array is answered. Unsupported wording is handled before
opening the database, even when the configured path does not exist.

Errors contain only `{"error":"fixed_error_code"}`, without paths, prompts,
SQL details or tracebacks:

| HTTP status | Meaning |
| --- | --- |
| 400 | Invalid body/schema/query values, duplicate keys, malformed length or unsupported transfer encoding |
| 403 | Origin header present, or Host not exactly loopback hostname plus server port |
| 404 | POST path is not exactly /query (query strings are not accepted) |
| 405 | Unsupported HTTP methods, including unknown methods |
| 408 | Body read timeout |
| 411 | Content-Length missing |
| 413 | Body exceeds 16,384 bytes |
| 415 | Content-Type unsupported |
| 422 | Query observation or serialized response limit exceeded |
| 503 | Configured database cannot be opened/read with the required schema |

Other standard-library HTTP parser errors retain their HTTP status with the
fixed JSON code `http_protocol_error`; request text is not reflected.

Content-Type must be application/json or application/json; charset=utf-8
(case-insensitive). Exactly one ASCII decimal Content-Length is required.
Transfer-Encoding, duplicate length/type headers, duplicate JSON keys, NaN,
Infinity, extra fields and invalid UTF-8 are rejected. Responses close the
connection and include no-store and nosniff headers.

## Local boundary and resource limits

Requests with any Origin header are rejected. There is no CORS support; browser
preflights fail. Host must be exactly 127.0.0.1:PORT or localhost:PORT. These
checks reduce browser-to-local request and DNS-rebinding risk; they are not
authentication. Trusted local programs/users can query the configured database.
Do not forward the port or expose this unauthenticated development server through
a proxy or public network.

Connections have a five-second socket timeout. The server handles one request
at a time and has no production concurrency, rate limiting or TLS. Standard
library HTTP header limits also apply. A slow local client can temporarily
delay another client; the socket timeout is not a total request deadline.

Each zone-change request is limited to 10,000 matching history observations.
The cap check and query share one read transaction, so concurrent inserts cannot
change the checked history mid-request. The bound applies before interval filtering so required earlier evidence is
not silently dropped. Serialized responses over 1 MiB return 422, never partial
evidence. Serialization happens before this size check, so the limit bounds
transport size, not peak Python allocation. Database query duration is not
hard-limited; the SQLite lock wait is one second.

SQLite is opened with mode=ro using the escaped, fixed startup file URI.
No ingestion endpoints, arbitrary files, image serving or identity updates are
available. Existing database schema is required; errors cannot create a missing
database. This API returns stored evidence and does not claim current visibility,
physical location, or general natural-language understanding.
