"""Disposable F-35 wire witness. No retries, payload logs, or persisted secrets.

Deployed ONLY in the explicitly authorized acceptance namespace. For the crash
path it withholds a real gateway response after the target acted, allowing the
controller to kill the worker deterministically. Counters are independent of the
ledger. A boot-id change invalidates the campaign, never resets its arithmetic.
"""
import hmac
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
from uuid import uuid4

LOCK = threading.Lock()
RELEASE = threading.Event()
RELEASE.set()
STATE = {"boot_id": str(uuid4()), "attempts": 0, "completed": 0, "held": False, "block_next": False}
TOKEN = os.environ["EXECUTION_HANDOFF_TOKEN"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def controlled(self):
        return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + TOKEN)

    def do_GET(self):
        if self.path != "/status" or not self.controlled():
            return self.reply(404, {})
        with LOCK:
            state = dict(STATE)
        self.reply(200, state)

    def do_POST(self):
        if self.path.startswith("/control/"):
            if not self.controlled():
                return self.reply(404, {})
            with LOCK:
                if self.path == "/control/block" and not STATE["held"]:
                    STATE["block_next"] = True
                    RELEASE.clear()
                elif self.path == "/control/release":
                    STATE["block_next"] = False
                    RELEASE.set()
                else:
                    return self.reply(409, {})
            return self.reply(200, {"ok": True})
        if self.path != "/api/v2/tools/invoke":
            return self.reply(404, {})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1048576:
                return self.reply(413, {})
            body = self.rfile.read(length)
            with LOCK:
                STATE["attempts"] += 1
                block = STATE["block_next"]
                STATE["block_next"] = False
            connection = HTTPConnection("tool-gateway", 8000, timeout=60)
            headers = {key: value for key, value in self.headers.items()
                       if key.lower() not in {"host", "connection", "transfer-encoding"}}
            connection.request("POST", self.path, body=body, headers=headers)
            response = connection.getresponse()
            output = response.read(1048577)
            if len(output) > 1048576:
                raise ValueError
            status = response.status
            response_headers = list(response.getheaders())
            connection.close()
            with LOCK:
                STATE["completed"] += 1
                if block:
                    STATE["held"] = True
            if block:
                # Bounded safety watchdog: failure never becomes a silent retry.
                RELEASE.wait(120)
                with LOCK:
                    STATE["held"] = False
            self.send_response(status)
            for key, value in response_headers:
                if key.lower() not in {"content-length", "transfer-encoding", "connection", "server", "date"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)
        except (OSError, ValueError):
            # No exception text: it could contain a URL or credential.
            try:
                self.reply(502, {"error": "acceptance_wire_failure"})
            except OSError:
                pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
