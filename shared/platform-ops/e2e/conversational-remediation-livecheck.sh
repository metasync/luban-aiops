#!/bin/sh
# SPEC-078 R-7 (OQ-6): gated conversational-remediation live-check. Proves the
# human-requested, remediation-intent CHAT turn drives diagnose → propose → stage
# in-process and actually PARKS one proposed remediation end to end against the
# live cluster — and never dispatches it — which unit tests alone cannot (the
# four-point gate's point 3, the mutation ceiling). It mirrors
# remediation-livecheck.sh (SPEC-077 R-8): the mocked leg is the one wired into
# make verify / make e2e; the live leg is an explicit operator step. The ONLY
# entry difference is the surface — SPEC-078 rides POST /api/v1/chat with the
# coupled opt-in remediation_intent + remediation_profile flag, not the dedicated
# /api/v1/remediate trigger, so it proves the SAME ceiling through the
# conversational composition.
#
#   --local  (default) run the mocked-I/O pytest proof of this script's pipeline
#                       logic (tests/test_conversational_remediation_livecheck.py).
#                       No cluster, no network, no paid call. This is the leg
#                       collected by the ordinary suite, so the check cannot be
#                       skipped silently.
#   --live             read-only cluster pre-flight: assert the intent-carrying
#                       chat entry is deployed AND gated on both tiers — an
#                       unauthenticated POST is 401 on agent /api/v2/chat and on
#                       gateway /api/v1/chat (404 = not deployed). Fires NO model
#                       call. (Unlike SPEC-077's dedicated /remediate route, the
#                       conversational entry rides the existing chat route, so the
#                       intent-specific behavior — the remediate:stage widening
#                       gate, the diagnosis-only fail-closed, and the park +
#                       zero-dispatch ceiling — is proven in the drive leg below.)
#   --live with LUBAN_CONVERSATIONAL_REMEDIATION_DRIVE_PAID_TURN=1
#                      additionally, in order: (a) a token that holds chat but NOT
#                      remediate:stage (approver — the stager/approver disjointness)
#                      is denied 403 at the gateway naming detail.action
#                      =remediate:stage (R-3/R-5 deny-by-default widening gate,
#                      non-billable); (b) a diagnosis-only profile (servicenow-
#                      incident) fails closed 4xx with NO executor turn (R-2,
#                      non-billable — the handler pre-checks remediation_shape
#                      before any model call); (c) drive ONE authorized, billable
#                      conversational remediation turn for a stageable profile
#                      (k8s-pod-degradation) and assert the proposal PARKS: a
#                      bounded ok|partial chat turn on the existing frame (no
#                      agent_role/execution wire field), audited as chat_completed
#                      (point 1 live), with ZERO execution_requested across the
#                      whole session family and NO HITL auto-approval (point 3 — a
#                      staged proposal only parks for a DISTINCT human; the
#                      SPEC-030 self-approval block is unchanged). Then deny the
#                      test proposal (or close its expiry) and delete the throwaway
#                      session. Denial may include a billable model continuation.
#                      The paid leg is explicitly gated and
#                      never runs by default. No live mutation is dispatched.
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
    uv run --directory "$ROOT/products/agent-platform" pytest -q tests/test_conversational_remediation_livecheck.py
    exit 0 ;;
  --live) ;;
  *) printf '%s\n' 'Usage: conversational-remediation-livecheck.sh [--local|--live]' >&2
     printf '%s\n' '  --local  mocked-I/O proof (default; no cluster, no paid call)' >&2
     printf '%s\n' '  --live   read-only cluster pre-flight; add' >&2
     printf '%s\n' '           LUBAN_CONVERSATIONAL_REMEDIATION_DRIVE_PAID_TURN=1 for' >&2
     printf '%s\n' '           the gated, billable one-turn park + zero-dispatch proof' >&2
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


# The stageable profile the live drive leg stages ONE proposal for (OQ-6/R-7):
# k8s-pod-degradation against the live cluster, driven through the conversational
# chat entry. post-deploy-verify is covered by scenario tests, not live-wired
# (mirroring remediation-livecheck). The diagnosis-only profile fails closed at
# the trigger (R-2), asserted non-billably.
STAGEABLE_PROFILE = "k8s-pod-degradation"
STAGEABLE_MESSAGE = (
    "This is an approval-only rehearsal, not a report of a real outage. "
    "Inspect the existing scratch-restart-demo deployment in namespace "
    + os.environ.get("NAMESPACE", "dev-luban-aiops") + ". "
    "Report its actual pod health without inventing degradation. I explicitly "
    "request a staged proposal to restart its current pod, even if it is healthy: "
    "use k8s.delete_pod for exactly one pod belonging to that deployment, with "
    "the live-discovered name and namespace. Submit that tool call so the runtime "
    "parks it BEFORE execution for a distinct human. Do not merely describe the "
    "call in prose, approve it, or dispatch it. If the target cannot be found, "
    "report that limitation; do not substitute another workload."
)
DIAGNOSIS_ONLY_PROFILE = "servicenow-incident"
DIAGNOSIS_ONLY_MESSAGE = "why is INC-1234 breaching its SLA"
# The approver holds `chat` but NOT `remediate:stage` (policy-default.yaml keeps
# the stager and the approver disjoint), so it is exactly the role that proves the
# conversational widening is gated on remediate:stage — it passes the chat gate and
# is denied at the staging gate (R-3/R-5), not merely denied chat.
DENIED_ROLE = "approver"


def main():
    namespace = os.environ.get("NAMESPACE", "dev-luban-aiops")
    agent = os.environ.get("AGENT_DEPLOYMENT", "agent-service")
    gateway_deploy = os.environ.get("GATEWAY_DEPLOYMENT", "platform-gateway")
    gateway = os.environ.get("GATEWAY_URL", "http://localhost:18083").rstrip("/")
    identity = os.environ.get("IDENTITY_URL", "http://localhost:18081").rstrip("/")
    drive = os.environ.get(
        "LUBAN_CONVERSATIONAL_REMEDIATION_DRIVE_PAID_TURN", "") == "1"

    opener = build_opener()

    def http(method, url, body=None, auth=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Cache-Control": "no-store"}
        if auth:
            headers["Authorization"] = auth
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with opener.open(request, timeout=300) as response:
                return response.status, response.read().decode()
        except HTTPError as error:
            # A 403/4xx is an expected, asserted outcome here (the R-3/R-5 staging
            # gate and the R-2 fail-closed), not a transport failure — surface the
            # code and body rather than letting it abort the run.
            return error.code, error.read().decode()

    def kubectl(*args):
        result = subprocess.run(
            ["kubectl", "-n", namespace, *args],
            text=True, capture_output=True, timeout=120)
        require(result.returncode == 0,
                "kubectl %s failed: %s" % (args[0], (result.stderr or "").strip()[:200]))
        return result.stdout

    def probe_route(deployment, path, body):
        # An unauthenticated POST to a deployed chat route is identity/auth gated
        # (401); an undeployed route is 404. The probe body is a schema-valid
        # coupled intent chat (remediation_intent + remediation_profile together,
        # R-1) so the gate — not body validation — is what answers. curl -w prints
        # just the code, so nothing about the body is echoed.
        return kubectl("exec", "deployment/" + deployment, "--",
                       "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                       "-X", "POST", "-H", "Content-Type: application/json",
                       "-d", json.dumps(body), "localhost:8000" + path).strip()

    # (1) Pre-flight: the intent-carrying chat entry is deployed on BOTH tiers and
    #     gated (401, never 404). No model call, no port-forward, no token.
    probe = {"message": "pre-flight route probe", "remediation_intent": True,
             "remediation_profile": STAGEABLE_PROFILE}
    agent_code = probe_route(agent, "/api/v2/chat", probe)
    require(agent_code == "401",
            "agent-service POST /api/v2/chat answered %s, expected 401 "
            "(404 = the chat entry is not deployed)" % agent_code)
    gateway_code = probe_route(gateway_deploy, "/api/v1/chat", probe)
    require(gateway_code == "401",
            "platform-gateway POST /api/v1/chat answered %s, expected 401 "
            "(404 = the chat entry proxy is not deployed)" % gateway_code)

    if not drive:
        print("CONVERSATIONAL_REMEDIATION_LIVECHECK_LIVE_OK: the intent-carrying "
              "chat entry is deployed and gated on both tiers (agent /api/v2/chat "
              "401, gateway /api/v1/chat 401); no model call. Set "
              "LUBAN_CONVERSATIONAL_REMEDIATION_DRIVE_PAID_TURN=1 to drive one "
              "gated, billable conversational remediation turn for %s and prove it "
              "parks with zero dispatch" % STAGEABLE_PROFILE)
        return

    # (2) Drive leg. Mint a platform-admin token (chat + remediate:stage to
    #     trigger + audit:read to prove the ceiling) and an approver token (chat
    #     but NO remediate:stage) for the R-3/R-5 widening-gate assertion. Token
    #     mints are non-billable (identity broker, no model call).
    def mint(username, roles, groups):
        status, body = http("POST", identity + "/api/v1/auth/token", body={
            "username": username,
            "email": username + "@luban-aiops.local",
            "roles": roles, "groups": groups})
        require(status == 200, "identity token mint (%s) answered HTTP %s"
                % (username, status))
        token = json.loads(body).get("access_token", "")
        require(token, "identity broker issued no access_token for %s" % username)
        return "Bearer " + token

    admin = mint("luban-conversational-livecheck",
                 ["platform-admin"], ["platform-admins"])
    denied = mint("luban-conversational-denied",
                  [DENIED_ROLE], [DENIED_ROLE + "s"])

    def intent_chat(message, profile, session_id=None, auth=None):
        # The conversational entry: the coupled opt-in flag on the existing chat
        # body (R-1). No agent_role crosses (SPEC-073 R-3) — the composition binds
        # orchestrator/diagnostician/executor in-process.
        body = {"message": message, "remediation_intent": True,
                "remediation_profile": profile}
        if session_id:
            body["session_id"] = session_id
        return http("POST", gateway + "/api/v1/chat", auth=auth, body=body)

    # (2a) R-3/R-5 deny-by-default widening gate: a token that holds chat but NOT
    #      remediate:stage is refused 403 at the gateway BEFORE any proxy or model
    #      call (non-billable), and the denial names the remediate:stage widening —
    #      proving the gate fired on the staging widening, not on chat.
    status, body = intent_chat(STAGEABLE_MESSAGE, STAGEABLE_PROFILE, auth=denied)
    require(status == 403,
            "intent chat with a %s token (chat but no remediate:stage) answered "
            "HTTP %s, expected 403 (the R-3/R-5 staging-widening gate is not "
            "enforced)" % (DENIED_ROLE, status))
    require("remediate:stage" in body,
            "the %s 403 did not name the remediate:stage widening (detail.action) "
            "— the gate may be firing on chat, not on the staging widening"
            % DENIED_ROLE)

    # (2b) R-2 fail-closed: a diagnosis-only profile is refused 4xx with NO
    #      executor turn — the handler pre-checks remediation_shape before any
    #      model call, so this is non-billable.
    status, _body = intent_chat(DIAGNOSIS_ONLY_MESSAGE, DIAGNOSIS_ONLY_PROFILE,
                                auth=admin)
    require(400 <= status < 500,
            "intent chat(%s) (diagnosis-only) answered HTTP %s, expected 4xx "
            "(the R-2 fail-closed guard did not fire)"
            % (DIAGNOSIS_ONLY_PROFILE, status))

    def audit_events(session_id, event_type):
        url = gateway + "/api/v1/audit/events?" + urlencode(
            {"session_id": session_id, "event_type": event_type, "limit": 50})
        status, body = http("GET", url, auth=admin)
        require(status == 200, "audit query answered HTTP %s" % status)
        return json.loads(body).get("events", [])

    def session_family_mutations(session_id, event_type="execution_requested"):
        # POINT 3 sensitivity: diagnostics use derived ::orch::* ids, while
        # executor staging uses the real parent session. The audit API matches
        # session_id exactly, so inspect both the parent and its entire family.
        # Exhaust bounded pagination rather than trusting only the newest page.
        cursor = None
        found = []
        for _ in range(20):
            params = {"event_type": event_type, "limit": 200}
            if cursor:
                params["cursor"] = cursor
            url = gateway + "/api/v1/audit/events?" + urlencode(params)
            status, body = http("GET", url, auth=admin)
            require(status == 200, "audit query answered HTTP %s" % status)
            page = json.loads(body)
            found.extend(e for e in page.get("events", [])
                         if e.get("session_id") == session_id
                         or (e.get("session_id") or "").startswith(session_id + "::"))
            cursor = page.get("next_cursor")
            if not cursor:
                return found
        raise RuntimeError("audit pagination exceeded bound; cannot prove zero dispatch")

    # (2c) The ONE gated, billable conversational remediation turn: an authorized
    #      platform-admin drives diagnose → propose → stage in ONE chat turn. The
    #      executor PROPOSES; the kernel PARKS it on the existing HITL card. Assert
    #      the turn completed (bounded, never hung), rode the existing frame (no
    #      agent_role/execution wire field), was audited (point 1), and — the
    #      mutation ceiling — requested ZERO execution across the session family
    #      (point 3) with no HITL auto-approval.
    status, body = http("POST", gateway + "/api/v1/sessions", body={}, auth=admin)
    require(status == 200, "session create answered HTTP %s" % status)
    session = json.loads(body).get("session_id", "")
    require(session, "session create returned no session_id")
    try:
        status, body = intent_chat(STAGEABLE_MESSAGE, STAGEABLE_PROFILE,
                                   session_id=session, auth=admin)
        require(status == 200,
                "intent chat(%s) answered HTTP %s" % (STAGEABLE_PROFILE, status))
        result = json.loads(body)
        # BOUNDED: the conversational turn terminated and reported — never hung.
        # status is ok, or partial when the diagnosis was budget-limited or the
        # proposal parked awaiting a distinct human.
        require(result.get("status") in ("ok", "partial"),
                "intent chat(%s) status %r is not a bounded ok|partial"
                % (STAGEABLE_PROFILE, result.get("status")))
        require((result.get("content") or "").strip(),
                "intent chat(%s) returned empty content" % STAGEABLE_PROFILE)
        # NO NEW FRAME (R-5): the response rides the existing chat-response keys —
        # no agent_role, no execution/mutation field crosses the wire.
        require("agent_role" not in result and "execution" not in result,
                "intent chat(%s) leaked a multi-agent/mutation wire field"
                % STAGEABLE_PROFILE)

        # POINT 1 (audit live): the conversational turn was audited as
        # chat_completed (the gateway reuses the existing event type — no new
        # event_type is minted, R-4). Ingest can lag, so retry until it lands; its
        # presence is what makes the zero-dispatch check below sensitive rather
        # than vacuously true over an empty trail.
        completed = []
        for _ in range(15):
            completed = audit_events(session, "chat_completed")
            if completed:
                break
            time.sleep(2)
        require(completed,
                "no chat_completed audit event landed for the conversational "
                "session %s (point-1 attribution is not live)" % session)

        # POINT 3 (the mutation ceiling): NO execution was requested by the
        # conversational turn OR any of its derived ::orch::* turns — the proposal
        # PARKED for a distinct human, it never dispatched and never auto-approved.
        for event_type in ("execution_requested", "execution_completed", "confirmation_decided"):
            events = session_family_mutations(session, event_type)
            require(not events, "%s events found across session family; "
                    "staging must not dispatch or auto-approve" % event_type)

        # Positive evidence is mandatory BEFORE cleanup: prose and an empty
        # execution trail alone do not prove that the HITL integration worked.
        status, body = http("GET", gateway + "/api/v1/sessions/" + session, auth=admin)
        require(status == 200, "session detail answered HTTP %s" % status)
        cards = json.loads(body).get("confirmations") or []
        pending = [card for card in cards
                   if card.get("session_id") == session
                   and card.get("owner_user_id") == "luban-conversational-livecheck"
                   and card.get("confirm_id") and card.get("status") == "pending"
                   and not card.get("decision") and not card.get("decider_user_id")
                   and len(card.get("pending_calls") or []) == 1
                   and card["pending_calls"][0].get("risk_level") in ("write", "admin")]
        require(len(cards) == 1 and len(pending) == 1,
                "no single pending mutating confirmation card for this owner/session "
                "before cleanup; narrative completion is not parking proof")
        print("PARK_PROOF: session=%s confirm_id=%s status=pending mutation_calls=1"
              % (session, pending[0]["confirm_id"]))
    finally:
        # DELETE deliberately refuses a parked session. Cancel only this owner's
        # test proposal through the existing deny/expiry lifecycle, never approve.
        # http() drains the SSE response before inspecting the durable outcome.
        status, body = http("GET", gateway + "/api/v1/sessions/" + session, auth=admin)
        require(status == 200, "cleanup session detail answered HTTP %s" % status)
        cleanup_cards = json.loads(body).get("confirmations") or []
        require(all(card.get("session_id") == session
                    and card.get("owner_user_id") == "luban-conversational-livecheck"
                    for card in cleanup_cards),
                "cleanup refused a foreign owner/session card")
        parked = [card for card in cleanup_cards if card.get("status") == "pending"]
        require(len(parked) <= 1, "cleanup refused multiple pending cards")
        cleanup_ids = set()
        if parked:
            confirm_id = parked[0].get("confirm_id")
            require(confirm_id, "cleanup pending card has no confirmation id")
            cleanup_ids.add(confirm_id)
            status, _ = http("POST", gateway + "/api/v1/chat/confirm", auth=admin, body={
                "session_id": session, "confirm_id": confirm_id, "decision": "deny"})
            # Expiry and a concurrent denial are safe only if independently
            # confirmed below; neither HTTP 200 nor 409 alone proves disposal.
            require(status in (200, 409, 410),
                    "cleanup denial failed (HTTP %s)" % status)
            status, body = http("GET", gateway + "/api/v1/sessions/" + session, auth=admin)
            require(status == 200, "cleanup outcome lookup answered HTTP %s" % status)
            cleanup_cards = json.loads(body).get("confirmations") or []
            resolved = [card for card in cleanup_cards if card.get("confirm_id") == confirm_id]
            require(len(resolved) == 1 and resolved[0].get("status") in ("denied", "expired"),
                    "cleanup did not durably deny or expire the test confirmation")
        require(all(card.get("session_id") == session
                    and card.get("owner_user_id") == "luban-conversational-livecheck"
                    and ((card.get("status") == "denied" and card.get("decision") == "deny")
                         or (card.get("status") == "expired" and not card.get("decision")))
                    for card in cleanup_cards),
                "cleanup found a pending, approved, or unexpected confirmation")
        for event_type in ("execution_requested", "execution_completed"):
            require(not session_family_mutations(session, event_type),
                    "%s found during cleanup; no mutation is authorized" % event_type)
        decisions = session_family_mutations(session, "confirmation_decided")
        require(all(event.get("session_id") == session
                    and event.get("outcome") == "deny"
                    and event.get("details", {}).get("decision") == "deny"
                    and event.get("details", {}).get("confirm_id") in cleanup_ids
                    for event in decisions),
                "unexpected confirmation_decided event during cleanup")
        cleanup_status, _ = http("DELETE", gateway + "/api/v1/sessions/" + session, auth=admin)
        require(cleanup_status in (200, 204),
                "throwaway session cleanup failed (HTTP %s)" % cleanup_status)
        print("CLEANUP_PROOF: session=%s disposed_without_approval=true deleted=true" % session)

    print("CONVERSATIONAL_REMEDIATION_LIVECHECK_TURN_OK: the %s token (chat but no "
          "remediate:stage) was denied 403 naming the staging widening (R-3/R-5), "
          "the diagnosis-only %s profile failed closed 4xx (R-2), and one authorized "
          "%s conversational turn completed, was audited as chat_completed, and "
          "requested ZERO execution — the proposal parked for a distinct human with "
          "no HITL auto-approval (the mutation ceiling held); test proposal safely "
          "denied or expired and throwaway session deleted"
          % (DENIED_ROLE, DIAGNOSIS_ONLY_PROFILE, STAGEABLE_PROFILE))


try:
    main()
except (RuntimeError, URLError, HTTPError, json.JSONDecodeError, KeyError) as error:
    # Single-line, secret-free failure: never echo tokens, credentials or bodies.
    reason = str(error) or error.__class__.__name__
    print("CONVERSATIONAL_REMEDIATION_LIVECHECK_FAILED: %s" % reason, file=sys.stderr)
    sys.exit(1)
PY
