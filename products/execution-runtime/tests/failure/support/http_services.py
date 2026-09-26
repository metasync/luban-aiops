"""Independent durable counters and non-retrying HTTP faults on either leg."""
from __future__ import annotations

from contextlib import closing
import base64
from datetime import datetime, timezone
import hmac
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import socket
import sqlite3
from urllib.parse import urlsplit
from uuid import uuid4

FAULTS = {"none", "drop_reply", "malformed", "truncated", "http_error", "delayed_headers",
          "disconnect_read", "disconnect_write"}


def initialize(path):
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, "
                   "kind TEXT NOT NULL, operation_id TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS correlation (request_id TEXT, execution_id TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS audit (event TEXT NOT NULL)")
        db.commit()


def record(path, kind, operation_id):
    with closing(sqlite3.connect(path, timeout=2)) as db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("INSERT INTO events(kind,operation_id) VALUES (?,?)", (kind, operation_id))
        db.commit()


def counts(path):
    """Fresh connection outside the worker; absence/failure never becomes zero."""
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)) as db:
        rows = db.execute("SELECT kind, count(*) FROM events GROUP BY kind").fetchall()
        operations = db.execute("SELECT kind,operation_id FROM events ORDER BY seq").fetchall()
    result = {"attempt": 0, "accepted": 0, "effect": 0}
    result.update(dict(rows))
    result["operations"] = operations
    return result


def correlation_facts(path):
    """Read only bounded IDs and audit metadata, never bodies or credentials."""
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)) as db:
        headers = db.execute("SELECT request_id,execution_id FROM correlation ORDER BY rowid").fetchall()
        audits = [json.loads(row[0]) for row in db.execute("SELECT event FROM audit ORDER BY rowid")]
    return {"headers": headers, "audits": audits}


def record_headers(path, headers):
    request_id, execution_id = headers.get("x-request-id", ""), headers.get("x-execution-id", "")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", request_id):
        request_id = ""
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", execution_id):
        execution_id = ""
    with closing(sqlite3.connect(path, timeout=2)) as db:
        db.execute("INSERT INTO correlation VALUES (?,?)", (request_id, execution_id))
        db.commit()


def launch_http(sock, path, token, barriers, upstream=None, fault="none", report=None, audit_status=None,
                canaries=(), malformed_body=None):
    if fault not in FAULTS:
        raise ValueError("unknown fault")
    if audit_status not in (None, 202, 503):
        raise ValueError("unknown audit mode")
    if upstream and (urlsplit(upstream).hostname != "127.0.0.1"
                     or urlsplit(upstream).scheme != "http"):
        raise ValueError("fault proxy upstream must be disposable loopback HTTP")
    initialize(path)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health/live":
                self.reply(200, {"status": "ok"})
            else:
                self.reply(404, {})

        def do_POST(self):
            expected_auth = ("Basic " + base64.b64encode(f"failure-harness:{token}".encode()).decode()
                             if audit_status is not None else f"Bearer {token}")
            if not hmac.compare_digest(self.headers.get("Authorization", "").encode(),
                                       expected_auth.encode()):
                self.reply(401, {})
                return
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536:
                self.reply(400, {})
                return
            if fault == "disconnect_write":
                self.rfile.read(min(size, 1))
                self.connection.shutdown(socket.SHUT_RDWR)
                return
            raw = self.rfile.read(size)
            try:
                payload = json.loads(raw)
                operation = str(uuid4())
                if audit_status is not None:
                    record(path, "audit_attempt", operation)
                    if canaries:
                        # Inspect the emitter's entire wire payload BEFORE allowlisting.
                        record(path, "audit_scanned", operation)
                        if any(value.encode() in raw for value in canaries):
                            record(path, "audit_canary", operation)
                    if audit_status == 202:
                        # Explicit metadata allowlist; no raw audit payload in evidence.
                        for event in payload.get("events", []):
                            details = event.get("details", {})
                            safe = {name: event[name] for name in ("event_type", "request_id")}
                            safe.update({name: details[name] for name in (
                                "execution_id", "attempt_request_id", "state", "reason_code", "observation_id"
                            ) if name in details})
                            encoded = json.dumps(safe)
                            if len(encoded) > 2048:
                                raise ValueError("audit metadata exceeded bound")
                            with closing(sqlite3.connect(path, timeout=2)) as db:
                                db.execute("INSERT INTO audit VALUES (?)", (encoded,))
                                db.commit()
                            record(path, "audit_stored", operation)
                    self.reply(audit_status, {})
                    return
                record_headers(path, self.headers)
                if upstream:
                    record(path, "attempt", operation)
                    barriers.hit("B2")
                    parsed = urlsplit(upstream)
                    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=40)
                    try:
                        # One request, no redirects or retry, even on disconnect.
                        headers = {name: self.headers[name] for name in
                                   ("Authorization", "x-request-id", "x-execution-id")
                                   if name in self.headers}
                        headers["Content-Type"] = "application/json"
                        conn.request("POST", self.path, body=raw, headers=headers)
                        response = conn.getresponse()
                        expected = response.getheader("Content-Length")
                        status, body = response.status, response.read(131073)
                        if expected is not None and int(expected) != len(body):
                            raise http.client.IncompleteRead(body)
                    finally:
                        conn.close()
                    if len(body) > 131072:
                        raise ValueError("bounded response exceeded")
                else:
                    record(path, "accepted", operation)
                    if canaries:
                        encoded_args = json.dumps(payload["parameters"], sort_keys=True,
                                                  separators=(",", ":")).encode()
                        record(path, "args_digest", hashlib.sha256(encoded_args).hexdigest())
                    # Separate committed transactions distinguish acceptance from effect.
                    record(path, "effect", operation)
                    barriers.hit("B3")
                    status = 200
                    envelope = {"tool_name": payload.get("tool_name", "test.increment"),
                                "status": "success", "data": {"incremented": True},
                                "evidence": {"executed_at": datetime.now(timezone.utc).isoformat(),
                                             "duration_ms": 1, "risk_level": "write",
                                             "source_system": "disposable-counter"}}
                    if report is not None:
                        # F-16: a configurable tool report lets the disposable target
                        # emit a schema-valid failure after a partial effect, or a
                        # success carrying an upstream 500, so HTTP/tool/business
                        # outcomes stay distinct. Additive: report=None is byte-identical.
                        envelope = {**envelope, **report}
                    body = json.dumps(envelope).encode()
                    if canaries:
                        encoded_result = json.dumps(envelope, sort_keys=True,
                                                    separators=(",", ":")).encode()
                        record(path, "result_digest", hashlib.sha256(encoded_result).hexdigest())
                if fault in {"drop_reply", "disconnect_read"}:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                if fault == "delayed_headers":
                    barriers.hit("B5")
                if fault == "malformed":
                    body = malformed_body if malformed_body is not None else b"{invalid"
                if fault == "http_error":
                    status, body = 502, b"{}"
                self.send_response(status)
                self.send_header("x-request-id", self.headers.get("x-request-id", ""))
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if fault == "truncated":
                    self.wfile.write(body[:1])
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionError, http.client.HTTPException, OSError):
                self.close_connection = True

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            # No raw request/exception text in artifacts. Parent watchdog and
            # independent counters fail assertions if the service is unhealthy.
            pass

    server = Server(("127.0.0.1", 0), Handler, bind_and_activate=False)
    server.socket.close()
    server.socket = sock
    server.server_address = sock.getsockname()
    server.serve_forever(poll_interval=0.05)
