#!/bin/sh
# SPEC-062 R-8: safe local cross-product demo by default; --live is explicit.
# --local needs installed uv/npm product dependencies, no service or real secret.
# --live generates and consumes one throwaway handoff in a new chat session.
# It sends no email, resets no account, and never prints or writes the value.
# Export SECRET_DEMO_TOKEN (operator) and SECRET_DEMO_AUDIT_TOKEN (audit:read)
# securely; GATEWAY_URL defaults to http://localhost:18083. Enable generation
# and delegation beforehand. kubectl logs access is required for live log checks.
# NAMESPACE defaults to dev-luban-aiops. No provisioning or deployment occurs.
set -eu
set +x
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
case "${1:---local}" in
  --local)
    uv run --directory "$ROOT/products/agent-platform" pytest -q tests/test_secret_delivery_integration.py
    uv run --directory "$ROOT/products/tool-gateway" pytest -q tests/test_secret_delivery.py tests/test_secrets_connector.py
    uv run --directory "$ROOT/products/platform-gateway" pytest -q tests/test_workspace_proxies.py tests/test_chat_confirm.py
    npm --prefix "$ROOT/products/operator-portal/web-ui/app" test -- --run src/chat/__tests__/TurnGroup.test.tsx src/stream/__tests__/decoder.test.ts src/views/__tests__/ApprovalsView.test.tsx
    exit 0 ;;
  --live) ;;
  *) printf '%s\n' 'Usage: secret-delivery-demo.sh [--local|--live]' >&2; exit 2 ;;
esac
python3 - <<'PY'
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, quote, quote_plus
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID, uuid4


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    base = os.environ.get("GATEWAY_URL", "http://localhost:18083").rstrip("/")
    parsed = urlsplit(base)
    require(parsed.hostname and not parsed.path and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment,
            "GATEWAY_URL must be an origin without credentials, path or query")
    require(parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}),
            "Live demo requires HTTPS except on loopback")
    token = os.environ.get("SECRET_DEMO_TOKEN", "")
    audit_token = os.environ.get("SECRET_DEMO_AUDIT_TOKEN", "")
    require(token and audit_token, "Provide operator and audit tokens securely in the environment")
    opener = build_opener(NoRedirect())
    started = datetime.now(timezone.utc).isoformat()

    def request(path, body=None, auth=None, request_id=None):
        headers = {"Authorization": "Bearer " + (auth or token), "Cache-Control": "no-store",
                   "X-Request-ID": request_id or str(uuid4())}
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = Request(base + path, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
        try:
            with opener.open(req, timeout=180) as response:
                return response.status, response.headers, response.read().decode()
        except HTTPError as error:
            # Never include a response body or URL in an error report.
            return error.code, error.headers, ""

    def get_json(path, **kwargs):
        status, headers, text = request(path, **kwargs)
        require(status == 200, "Required API call failed")
        return json.loads(text)

    catalog = get_json("/api/v1/tools")
    require(any(t.get("name") == "secrets.generate_password" and t.get("risk_level") == "read" for t in catalog),
            "Read-tier generation is unavailable; review activation configuration")
    session = get_json("/api/v1/sessions", body={})["session_id"]
    status, _, stream = request("/api/v1/chat/stream?" + urlencode({
        "session_id": session,
        "message": "Generate one strong password with a one-time portal copy handoff. Do not reset an account, send email, or print the password.",
    }))
    require(status == 200, "Chat stream failed")
    frames = [json.loads(line[5:].strip()) for line in stream.splitlines()
              if line.startswith("data:") and line[5:].strip() not in {"", "[DONE]"}]
    require(not any(f.get("type") == "confirmation_request" for f in frames), "Generation unexpectedly parked an approval")
    delivery = [f for f in frames if f.get("type") == "secret_delivery"]
    require(len(delivery) == 1, "Expected exactly one delivery handle")
    handle = delivery[0]["delivery_id"]
    require(str(UUID(handle)) == handle, "Noncanonical delivery handle")
    redemption_id = str(uuid4())
    status, headers, text = request("/api/v1/secrets/delivery/" + handle, request_id=redemption_id)
    require(status == 200 and headers.get("Cache-Control") == "no-store", "Redemption failed or cache control missing")
    value = json.loads(text).get("value")
    require(isinstance(value, str) and bool(value), "Redemption returned no value")
    status, _, _ = request("/api/v1/secrets/delivery/" + handle)
    require(status == 404, "Second redemption was not unavailable")
    detail = get_json("/api/v1/sessions/" + quote(session, safe=""))
    require(detail.get("transcript_available"), "Durable transcript unavailable")
    evidence = detail.get("evidence_turns")
    require(isinstance(evidence, list) and any(f.get("delivery_id") == handle for turn in evidence for f in turn["frames"]),
            "Delivery metadata missing from durable replay")
    audit = None
    for _ in range(20):
        audit = get_json("/api/v1/audit/events?" + urlencode({
            "request_id": redemption_id, "event_type": "secret_delivered", "limit": 200,
        }), auth=audit_token)
        if any(e.get("details", {}).get("delivery_id") == handle for e in audit.get("events", [])):
            break
        time.sleep(1)
    else:
        raise RuntimeError("Delivery audit event did not arrive")

    variants = {value, quote(value, safe=""), quote_plus(value)}

    def clean(node):
        if isinstance(node, str):
            return all(v not in node for v in variants)
        if isinstance(node, dict):
            return all(clean(k) and clean(v) for k, v in node.items())
        if isinstance(node, list):
            return all(clean(v) for v in node)
        return True

    require(clean([frames, detail, audit]), "Secret appeared in a projection")
    namespace = os.environ.get("NAMESPACE", "dev-luban-aiops")
    for deployment in ("tool-gateway", "agent-service", "platform-gateway"):
        result = subprocess.run([
            "kubectl", "-n", namespace, "logs", "deployment/" + deployment,
            "--all-containers=true", "--since-time=" + started,
        ], text=True, capture_output=True, timeout=30)
        require(result.returncode == 0, "Cannot verify service logs")
        require(clean(result.stdout), "Secret appeared in a service log")
    value = text = None
    print("SECRET_DELIVERY_OK: one-time redemption, masked stream/replay/title/logs, delivery audit present")


try:
    main()
except Exception:
    # Tracebacks, response bodies and exception strings may carry a value.
    print("SECRET_DELIVERY_FAILED: check activation, credentials, projections, and audit/log access; no payload printed", file=sys.stderr)
    sys.exit(1)
PY
