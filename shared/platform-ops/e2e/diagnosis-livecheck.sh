#!/bin/sh
# SPEC-076 R-8: gated bounded-diagnosis live-check (OQ-6). Proves the read-only
# orchestration loop actually runs BOUNDED and READ-ONLY end to end against the
# live cluster — the four-point gate's point 3 — which unit tests alone cannot.
# It mirrors observability-livecheck.sh (SPEC-065 R-4): the mocked leg is the one
# wired into make verify / make e2e; the live leg is an explicit operator step.
#
#   --local  (default) run the mocked-I/O pytest proof of this script's pipeline
#                       logic (tests/test_diagnosis_livecheck.py). No cluster, no
#                       network, no paid call. This is the leg collected by the
#                       ordinary suite, so the check cannot be skipped silently.
#   --live             read-only cluster pre-flight: assert the operator-invoked
#                       trigger is deployed AND gated on both tiers — an
#                       unauthenticated POST is 401 on agent /api/v2/diagnose and
#                       on gateway /api/v1/diagnose (404 = not deployed). Fires NO
#                       model call.
#   --live with LUBAN_DIAGNOSIS_DRIVE_PAID_TURN=1
#                      additionally drive ONE bounded read-only diagnosis per
#                      wired runbook — k8s-pod-degradation + observability-alert
#                      against the live cluster, servicenow-incident against the
#                      SPEC-067 in-cluster mock (OQ-6/OQ-7). For each: assert a
#                      bounded synthesis (status ok|partial, never a hang, never a
#                      mutation), that the run was audited as chat_completed with
#                      the runbook profile (point 1 live), and that NO
#                      execution_requested event fired for the session (point 3:
#                      the read-only loop dispatched no mutation — a proposal only
#                      parks, R-4). Then delete the throwaway session. The paid
#                      leg is explicitly gated and never runs by default. No live
#                      mutation is exercised.
#
# Prerequisites for --live (see make e2e):
#   kubectl context on the dev cluster. The pre-flight needs only kubectl (it
#   execs into the pods). The paid leg additionally needs port-forwards for
#   platform-gateway (svc/platform-gateway 18083:8000) and identity-service
#   (svc/identity-service 18081:8000).
#
# Configuration (env, with defaults): NAMESPACE (dev-luban-aiops),
#   AGENT_DEPLOYMENT (agent-service), GATEWAY_DEPLOYMENT (platform-gateway),
#   GATEWAY_URL (http://localhost:18083), IDENTITY_URL (http://localhost:18081).
set -euo pipefail
set +x
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
case "${1:---local}" in
  --local)
    uv run --directory "$ROOT/products/agent-platform" pytest -q tests/test_diagnosis_livecheck.py
    exit 0 ;;
  --live) ;;
  *) printf '%s\n' 'Usage: diagnosis-livecheck.sh [--local|--live]' >&2
     printf '%s\n' '  --local  mocked-I/O proof (default; no cluster, no paid call)' >&2
     printf '%s\n' '  --live   read-only cluster pre-flight; add' >&2
     printf '%s\n' '           LUBAN_DIAGNOSIS_DRIVE_PAID_TURN=1 for the gated,' >&2
     printf '%s\n' '           billable bounded read-only fan-out proof' >&2
     exit 2 ;;
esac
python3 - <<'PY'
import json
import os
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


# The runbooks the live drive leg exercises read-only (OQ-6/OQ-7): k8s +
# observability against the live cluster, ServiceNow against the SPEC-067
# in-cluster mock. post-deploy-verify is covered by scenario tests, not live-wired.
WIRED_RUNBOOKS = (
    ("k8s-pod-degradation",
     "Identify any degraded pod or workload in the namespace and its likely root "
     "cause. Read only; do not change anything."),
    ("observability-alert",
     "Correlate the current metric, trace and log signals and localize any "
     "anomaly. Read only; do not change anything."),
    ("servicenow-incident",
     "Diagnose the open incident against the ServiceNow mock with its related "
     "changes and CI. Read only; do not change anything."),
)


def main():
    namespace = os.environ.get("NAMESPACE", "dev-luban-aiops")
    agent = os.environ.get("AGENT_DEPLOYMENT", "agent-service")
    gateway_deploy = os.environ.get("GATEWAY_DEPLOYMENT", "platform-gateway")
    gateway = os.environ.get("GATEWAY_URL", "http://localhost:18083").rstrip("/")
    identity = os.environ.get("IDENTITY_URL", "http://localhost:18081").rstrip("/")
    drive = os.environ.get("LUBAN_DIAGNOSIS_DRIVE_PAID_TURN", "") == "1"

    opener = build_opener()

    def http(method, url, body=None, auth=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Cache-Control": "no-store"}
        if auth:
            headers["Authorization"] = auth
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        with opener.open(request, timeout=180) as response:
            return response.status, response.read().decode()

    def kubectl(*args):
        result = subprocess.run(
            ["kubectl", "-n", namespace, *args],
            text=True, capture_output=True, timeout=120)
        require(result.returncode == 0,
                "kubectl %s failed: %s" % (args[0], (result.stderr or "").strip()[:200]))
        return result.stdout

    def probe_route(deployment, path, body):
        # An unauthenticated POST to a deployed diagnose route is identity/auth
        # gated (401); an undeployed route is 404. curl -w prints just the code,
        # so nothing about the body is echoed.
        return kubectl("exec", "deployment/" + deployment, "--",
                       "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                       "-X", "POST", "-H", "Content-Type: application/json",
                       "-d", json.dumps(body), "localhost:8000" + path).strip()

    # (1) Pre-flight: the operator-invoked trigger is deployed on BOTH tiers and
    #     gated (401, never 404). No model call, no port-forward, no token.
    probe = {"profile": "k8s-pod-degradation", "goal": "pre-flight route probe"}
    agent_code = probe_route(agent, "/api/v2/diagnose", probe)
    require(agent_code == "401",
            "agent-service POST /api/v2/diagnose answered %s, expected 401 "
            "(404 = the SPEC-076 trigger is not deployed)" % agent_code)
    gateway_code = probe_route(gateway_deploy, "/api/v1/diagnose", probe)
    require(gateway_code == "401",
            "platform-gateway POST /api/v1/diagnose answered %s, expected 401 "
            "(404 = the SPEC-076 trigger proxy is not deployed)" % gateway_code)

    if not drive:
        print("DIAGNOSIS_LIVECHECK_LIVE_OK: the operator-invoked diagnose trigger "
              "is deployed and gated on both tiers (agent /api/v2/diagnose 401, "
              "gateway /api/v1/diagnose 401); no model call. Set "
              "LUBAN_DIAGNOSIS_DRIVE_PAID_TURN=1 to drive the bounded read-only "
              "fan-out for %s" % ", ".join(name for name, _ in WIRED_RUNBOOKS))
        return

    # (2) Paid leg: mint a platform-admin token (chat to trigger the diagnosis +
    #     audit:read to prove it stayed read-only), then drive ONE bounded
    #     read-only diagnosis per wired runbook. No mutation is dispatched; a
    #     proposal would only park on HITL for a distinct human (R-4).
    status, body = http("POST", identity + "/api/v1/auth/token", body={
        "username": "luban-diagnosis-livecheck",
        "email": "luban-diagnosis-livecheck@luban-aiops.local",
        "roles": ["platform-admin"], "groups": ["platform-admins"]})
    require(status == 200, "identity token mint answered HTTP %s" % status)
    token = json.loads(body).get("access_token", "")
    require(token, "identity broker issued no access_token")
    bearer = "Bearer " + token

    def audit_events(session_id, event_type):
        url = gateway + "/api/v1/audit/events?" + urlencode(
            {"session_id": session_id, "event_type": event_type, "limit": 50})
        status, body = http("GET", url, auth=bearer)
        require(status == 200, "audit query answered HTTP %s" % status)
        return json.loads(body).get("events", [])

    def session_family_mutations(session_id):
        # POINT 3 sensitivity (M4): a member turn audits under
        # "<session>::orch::<task>", never the bare parent id, and the audit
        # query matches session_id EXACTLY — so a parent-scoped query would miss
        # a member mutation and pass vacuously. Query the newest
        # execution_requested events cluster-wide (no session filter) and
        # prefix-match this run's whole session family. Newest-first over a rare
        # event type means a dev-cluster read-only drive's own events, if any,
        # sit well within the 200-row page.
        url = gateway + "/api/v1/audit/events?" + urlencode(
            {"event_type": "execution_requested", "limit": 200})
        status, body = http("GET", url, auth=bearer)
        require(status == 200, "audit query answered HTTP %s" % status)
        family = (session_id, session_id + "::")
        return [e for e in json.loads(body).get("events", [])
                if (e.get("session_id") or "").startswith(family)]

    proven = []
    for profile, goal in WIRED_RUNBOOKS:
        status, body = http("POST", gateway + "/api/v1/sessions", body={}, auth=bearer)
        require(status == 200, "session create answered HTTP %s" % status)
        session = json.loads(body).get("session_id", "")
        require(session, "session create returned no session_id")
        try:
            status, body = http("POST", gateway + "/api/v1/diagnose", auth=bearer,
                                body={"profile": profile, "goal": goal,
                                      "session_id": session})
            require(status == 200, "diagnose(%s) answered HTTP %s" % (profile, status))
            result = json.loads(body)
            # BOUNDED: the loop terminated and reported a synthesis — never hung,
            # never widened to a mutation. status is ok, or a budget-limited
            # partial (R-1 fail-closed); anything else is not a bounded diagnosis.
            require(result.get("status") in ("ok", "partial"),
                    "diagnose(%s) status %r is not a bounded ok|partial"
                    % (profile, result.get("status")))
            require((result.get("content") or "").strip(),
                    "diagnose(%s) returned an empty synthesis" % profile)
            # NO NEW FRAME (OQ-5): the response rides the existing chat-response
            # keys — no role, no execution/mutation field crosses the wire.
            require("agent_role" not in result and "execution" not in result,
                    "diagnose(%s) leaked a multi-agent/mutation wire field" % profile)

            # POINT 1 (audit live): the run was audited as a chat_completed
            # carrying the runbook profile. Ingest can lag, so retry until it
            # lands; its presence is what makes the read-only check below
            # sensitive rather than vacuously true over an empty trail.
            completed = []
            for _ in range(15):
                completed = [e for e in audit_events(session, "chat_completed")
                             if (e.get("details") or {}).get("profile") == profile]
                if completed:
                    break
                time.sleep(2)
            require(completed,
                    "no chat_completed audit event with profile=%s landed for "
                    "session %s (point-1 attribution is not live)" % (profile, session))

            # POINT 3 (read-only): NO execution was requested by this run OR any
            # of its member turns — the loop dispatched no mutation. Members audit
            # under "<session>::orch::<task>", so this prefix-matches the whole
            # session family, not the bare parent id (M4: an exact parent-scoped
            # query would miss a member mutation). A proposed remediation would
            # only park on HITL (R-4), never emit execution_requested from the loop.
            executions = session_family_mutations(session)
            require(not executions,
                    "diagnose(%s) dispatched a mutation (%d execution_requested "
                    "events across the session family) — the read-only loop must "
                    "never mutate" % (profile, len(executions)))
            proven.append(profile)
        finally:
            # Always clean up the throwaway session (idempotent; ignore its result).
            try:
                http("DELETE", gateway + "/api/v1/sessions/" + session, auth=bearer)
            except Exception:
                pass

    print("DIAGNOSIS_LIVECHECK_TURN_OK: bounded read-only diagnosis proven live "
          "for %s — each returned a bounded synthesis, was audited as "
          "chat_completed(profile), and requested NO execution (read-only held; a "
          "proposal only parks); throwaway sessions deleted; no mutation, no HITL "
          "auto-approval" % ", ".join(proven))


try:
    main()
except (RuntimeError, URLError, HTTPError, json.JSONDecodeError, KeyError) as error:
    # Single-line, secret-free failure: never echo tokens, credentials or bodies.
    reason = str(error) or error.__class__.__name__
    print("DIAGNOSIS_LIVECHECK_FAILED: %s" % reason, file=sys.stderr)
    sys.exit(1)
PY
