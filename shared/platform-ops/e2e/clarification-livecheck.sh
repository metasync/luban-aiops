#!/bin/sh
# SPEC-080 R-8: gated agent-initiated-clarification live-check. Proves a
# read-only AskUser park → owner answer → SAME-turn resume runs end to end
# against the live cluster and never mutates, dispatches, or auto-approves —
# the four-point gate's point 3 (a clarification is strictly *less* than the
# confirmation path). It mirrors the confirmation live-check (mutating-demo.sh's
# RUN_HITL_LEG) and the standalone remediation live-checks: the mocked leg is the
# one wired into make verify / make e2e; the live leg is an explicit operator
# step. The entry difference from the confirmation leg is the surface — a
# clarification parks on the v14 clarification_request frame and is answered
# in-line by the OWNER over POST /api/v1/sessions/{id}/clarification/answer (no
# approver, no distinct-human routing, no tier/self-approval gate — OQ-5).
#
#   --local  (default) run the mocked-I/O pytest proof of this script's pipeline
#                       logic (tests/test_clarification_livecheck.py). No
#                       cluster, no network, no paid call. This is the leg
#                       collected by the ordinary suite, so the check cannot be
#                       skipped silently.
#   --live             read-only cluster pre-flight: assert the chat entry is
#                       deployed AND gated on both tiers (an unauthenticated POST
#                       is 401 on agent /api/v2/chat and gateway /api/v1/chat;
#                       404 = not deployed) and that the clarification answer
#                       route is deployed (an unauthenticated POST is 401, never
#                       404/405). Fires NO model call.
#   --live with LUBAN_CLARIFICATION_DRIVE_PAID_TURN=1
#                      additionally drive ONE gated, billable turn: with
#                      AGENT_ASKUSER_ENABLED committed on, prompt the agent to
#                      ask a clarifying question, assert the stream PARKS on a
#                      clarification_request (no message_end, no
#                      confirmation_request), answer it in-line as the owner over
#                      the answer route, and assert the SAME-turn resume carries
#                      clarification_result(status=answered) then message_end.
#                      Then prove the ceiling: the turn was audited as
#                      chat_completed (point 1 — the closed event type, no new
#                      event_type), the durable card is park_kind=clarification /
#                      status=answered with ZERO pending_calls (read-only), and
#                      there are ZERO execution_requested / execution_completed /
#                      confirmation_decided events across the whole session family
#                      (no mutation, no dispatch, no auto-approval). Finally
#                      delete the throwaway session. The paid leg is explicitly
#                      gated and never runs by default. No mutation is dispatched.
#
# Prerequisites for --live (see make e2e):
#   kubectl context on the dev cluster. The pre-flight needs only kubectl (it
#   execs into the pods). The paid leg additionally needs port-forwards for
#   platform-gateway (svc/platform-gateway 18083:8000) and identity-service
#   (svc/identity-service 18081:8000), and AGENT_ASKUSER_ENABLED committed on.
#
# Configuration (env, with defaults): NAMESPACE (dev-luban-aiops),
#   AGENT_DEPLOYMENT (agent-service), GATEWAY_DEPLOYMENT (platform-gateway),
#   GATEWAY_URL (http://localhost:18083), IDENTITY_URL (http://localhost:18081),
#   OWNER_USER (luban-operator), OWNER_ROLE (operator).
set -euo pipefail
set +x
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
case "${1:---local}" in
  --local)
    uv run --directory "$ROOT/products/agent-platform" pytest -q tests/test_clarification_livecheck.py
    exit 0 ;;
  --live) ;;
  *) printf '%s\n' 'Usage: clarification-livecheck.sh [--local|--live]' >&2
     printf '%s\n' '  --local  mocked-I/O proof (default; no cluster, no paid call)' >&2
     printf '%s\n' '  --live   read-only cluster pre-flight; add' >&2
     printf '%s\n' '           LUBAN_CLARIFICATION_DRIVE_PAID_TURN=1 for the gated,' >&2
     printf '%s\n' '           billable one-turn park → owner-answer → resume proof' >&2
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


# The owner answers their own parked question in-line (OQ-5): a single identity
# that holds `chat` both parks the clarification and answers it — there is no
# approver, no distinct-human routing, and no self-approval concern, because a
# read-only clarification carries no security decision.
OWNER_USER = os.environ.get("OWNER_USER", "luban-operator")
OWNER_ROLE = os.environ.get("OWNER_ROLE", "operator")
# A prompt engineered to elicit the AskUser builtin (flag-gated, R-5): it asks the
# agent to clarify an ambiguous target rather than assume, so the turn PARKS on a
# clarification_request. It requests no mutation and names no tool, so a parked
# clarification can never carry a mutating pending_call.
CLARIFY_MESSAGE = (
    "I want to check on a deployment but I have not told you which environment. "
    "Before doing anything, use the AskUser tool to ask me which environment I "
    "mean (for example production or staging) and wait for my answer. Do not "
    "assume an environment, do not call any other tool, and do not change "
    "anything — just ask the clarifying question."
)


def main():
    namespace = os.environ.get("NAMESPACE", "dev-luban-aiops")
    agent = os.environ.get("AGENT_DEPLOYMENT", "agent-service")
    gateway_deploy = os.environ.get("GATEWAY_DEPLOYMENT", "platform-gateway")
    gateway = os.environ.get("GATEWAY_URL", "http://localhost:18083").rstrip("/")
    identity = os.environ.get("IDENTITY_URL", "http://localhost:18081").rstrip("/")
    drive = os.environ.get("LUBAN_CLARIFICATION_DRIVE_PAID_TURN", "") == "1"

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
            # A 401/4xx is an expected, asserted outcome here (the pre-flight
            # gate probe and the drive leg's structured races), not a transport
            # failure — surface the code and body rather than aborting the run.
            return error.code, error.read().decode()

    def kubectl(*args):
        result = subprocess.run(
            ["kubectl", "-n", namespace, *args],
            text=True, capture_output=True, timeout=120)
        require(result.returncode == 0,
                "kubectl %s failed: %s" % (args[0], (result.stderr or "").strip()[:200]))
        return result.stdout

    def probe_route(deployment, method, path, body):
        # An unauthenticated request to a deployed route is identity/auth gated
        # (401); an undeployed route is 404 (or 405 for a wrong method). curl -w
        # prints just the code, so nothing about the body is echoed.
        return kubectl("exec", "deployment/" + deployment, "--",
                       "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                       "-X", method, "-H", "Content-Type: application/json",
                       "-d", json.dumps(body), "localhost:8000" + path).strip()

    # (1) Pre-flight: the chat entry is deployed on BOTH tiers and gated (401,
    #     never 404), and the clarification answer route is deployed (401, never
    #     404/405). No model call, no port-forward, no token.
    probe = {"message": "pre-flight route probe"}
    agent_code = probe_route(agent, "POST", "/api/v2/chat", probe)
    require(agent_code == "401",
            "agent-service POST /api/v2/chat answered %s, expected 401 "
            "(404 = the chat entry is not deployed)" % agent_code)
    gateway_code = probe_route(gateway_deploy, "POST", "/api/v1/chat", probe)
    require(gateway_code == "401",
            "platform-gateway POST /api/v1/chat answered %s, expected 401 "
            "(404 = the chat entry proxy is not deployed)" % gateway_code)
    answer_probe = {"clarification_id": "cl-probe", "answers": []}
    answer_code = probe_route(
        gateway_deploy, "POST",
        "/api/v1/sessions/probe/clarification/answer", answer_probe)
    require(answer_code == "401",
            "platform-gateway POST /api/v1/sessions/{id}/clarification/answer "
            "answered %s, expected 401 (404/405 = the SPEC-080 R-4 answer route "
            "is not deployed)" % answer_code)

    if not drive:
        print("CLARIFICATION_LIVECHECK_LIVE_OK: the chat entry is deployed and "
              "gated on both tiers (agent /api/v2/chat 401, gateway /api/v1/chat "
              "401) and the clarification answer route is deployed (401); no "
              "model call. Set LUBAN_CLARIFICATION_DRIVE_PAID_TURN=1 (with "
              "AGENT_ASKUSER_ENABLED committed on) to drive one gated, billable "
              "clarification park → owner-answer → same-turn resume and prove it "
              "never mutates, dispatches, or auto-approves")
        return

    # (2) Drive leg. The AskUser builtin is flag-gated (R-5, default off), so the
    #     paid leg first asserts the committed flag is on — otherwise the model
    #     has no AskUser tool and the turn cannot park a clarification.
    flag = kubectl("get", "configmap", "platform-runtime-config",
                   "-o", "jsonpath={.data.AGENT_ASKUSER_ENABLED}").strip()
    require(flag == "true",
            "AGENT_ASKUSER_ENABLED is %r, expected 'true' — the AskUser builtin "
            "is flag-gated off (R-5), so no clarification can park; opt the dev "
            "overlay in before driving the paid leg" % flag)

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

    # ONE identity parks and answers (the owner answers in-line, OQ-5).
    owner = mint(OWNER_USER, [OWNER_ROLE], [OWNER_ROLE + "s"])

    def sse_frames(body):
        frames = []
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            try:
                frames.append(json.loads(line[5:].strip()))
            except ValueError:
                continue
        return frames

    def audit_events(session_id, event_type):
        url = gateway + "/api/v1/audit/events?" + urlencode(
            {"session_id": session_id, "event_type": event_type, "limit": 50})
        status, body = http("GET", url, auth=owner)
        require(status == 200, "audit query answered HTTP %s" % status)
        return json.loads(body).get("events", [])

    def session_family_mutations(session_id, event_type):
        # POINT 3 sensitivity: the audit API matches session_id exactly, so
        # inspect the parent and its entire derived family, exhausting bounded
        # pagination rather than trusting only the newest page.
        cursor = None
        found = []
        for _ in range(20):
            params = {"event_type": event_type, "limit": 200}
            if cursor:
                params["cursor"] = cursor
            url = gateway + "/api/v1/audit/events?" + urlencode(params)
            status, body = http("GET", url, auth=owner)
            require(status == 200, "audit query answered HTTP %s" % status)
            page = json.loads(body)
            found.extend(e for e in page.get("events", [])
                         if e.get("session_id") == session_id
                         or (e.get("session_id") or "").startswith(session_id + "::"))
            cursor = page.get("next_cursor")
            if not cursor:
                return found
        raise RuntimeError("audit pagination exceeded bound; cannot prove zero dispatch")

    status, body = http("POST", gateway + "/api/v1/sessions", body={}, auth=owner)
    require(status == 200, "session create answered HTTP %s" % status)
    session = json.loads(body).get("session_id", "")
    require(session, "session create returned no session_id")
    try:
        # (2a) The ONE gated, billable turn: prompt the agent to ask a clarifying
        #      question. The stream must PARK on a clarification_request and end
        #      WITHOUT message_end (R-2), and must NOT be a confirmation_request
        #      (a clarification is not an approval).
        stream_url = gateway + "/api/v1/chat/stream?" + urlencode(
            {"session_id": session, "message": CLARIFY_MESSAGE})
        status, body = http("GET", stream_url, auth=owner)
        require(status == 200, "chat stream answered HTTP %s" % status)
        parked = sse_frames(body)
        requests = [f for f in parked if f.get("type") == "clarification_request"]
        require(len(requests) == 1,
                "chat stream carried %d clarification_request frames, expected "
                "exactly 1 (did the model choose AskUser?)" % len(requests))
        require(not any(f.get("type") == "confirmation_request" for f in parked),
                "the parked turn carried a confirmation_request — a clarification "
                "must never route to the approval bridge")
        require(not any(f.get("type") == "message_end" for f in parked),
                "the parked turn carried a message_end — a clarification park ends "
                "the stream WITHOUT completing the turn (R-2)")
        request = requests[0]
        clarification_id = request.get("clarification_id", "")
        questions = request.get("questions") or []
        require(clarification_id, "clarification_request carried no clarification_id")
        require(questions, "clarification_request carried no questions")
        # Read-only posture: a clarification question carries options, never a
        # mutating pending_call / risk_level.
        require(all(q.get("options") for q in questions),
                "a parked clarification question carried no options")
        require("risk_level" not in body and "pending_calls" not in body,
                "the parked clarification leaked a mutating pending_call/risk_level")
        print("PARK_PROOF: session=%s clarification_id=%s questions=%d"
              % (session, clarification_id, len(questions)))

        # (2b) The OWNER answers in-line over the R-4 answer route (no approver).
        #      Build one answer per parked question, selecting its first option.
        answers = [{"question": q.get("question", ""),
                    "selected": [(q.get("options") or [{}])[0].get("label", "")]}
                   for q in questions]
        status, body = http(
            "POST", gateway + "/api/v1/sessions/" + session + "/clarification/answer",
            auth=owner, body={"clarification_id": clarification_id, "answers": answers})
        require(status == 200, "clarification answer answered HTTP %s" % status)
        resumed = sse_frames(body)
        results = [f for f in resumed if f.get("type") == "clarification_result"]
        require(len(results) == 1,
                "resumed stream carried %d clarification_result frames, expected 1"
                % len(results))
        require(results[0].get("status") == "answered",
                "clarification_result status %r is not 'answered'"
                % results[0].get("status"))
        # SAME-turn resume: the reply continues to a message_end on the one turn.
        require(any(f.get("type") == "message_end" for f in resumed),
                "the resumed stream carried no message_end — the same turn did not "
                "complete after the answer (R-2 resume-by-injection)")
        print("RESUME_PROOF: session=%s clarification_id=%s status=answered "
              "message_end=true" % (session, clarification_id))

        # POINT 1 (audit live): the resumed turn completed and was audited as
        # chat_completed — the CLOSED event type (no new event_type is minted,
        # R-8). Ingest can lag, so retry until it lands; its presence is what
        # makes the zero-dispatch check below sensitive rather than vacuous.
        completed = []
        for _ in range(15):
            completed = audit_events(session, "chat_completed")
            if completed:
                break
            time.sleep(2)
        require(completed,
                "no chat_completed audit event landed for the clarification "
                "session %s (point-1 attribution via the closed enum is not live)"
                % session)

        # POINT 3 (the ceiling): NO execution was requested and NO approval was
        # decided across the session family — a clarification is read-only, it
        # never stages, dispatches, or auto-approves.
        for event_type in ("execution_requested", "execution_completed",
                           "confirmation_decided"):
            events = session_family_mutations(session, event_type)
            require(not events, "%s events found across session family; a "
                    "clarification must not mutate, dispatch, or auto-approve"
                    % event_type)

        # Positive evidence BEFORE cleanup: the durable card is a read-only
        # answered clarification (park_kind=clarification, status=answered, ZERO
        # pending_calls), attributable to the owner who answered in-line.
        status, body = http("GET", gateway + "/api/v1/sessions/" + session, auth=owner)
        require(status == 200, "session detail answered HTTP %s" % status)
        cards = json.loads(body).get("confirmations") or []
        clarifications = [c for c in cards
                          if c.get("session_id") == session
                          and c.get("park_kind") == "clarification"
                          and c.get("status") == "answered"
                          and not (c.get("pending_calls") or [])]
        require(len(cards) == 1 and len(clarifications) == 1,
                "no single answered read-only clarification card for this "
                "owner/session before cleanup; narrative completion is not proof")
        print("DURABLE_PROOF: session=%s park_kind=clarification status=answered "
              "pending_calls=0" % session)
    finally:
        # The clarification is already answered (resolved), so no park blocks the
        # delete — contrast the confirmation leg, which must deny first. Assert no
        # mutation surfaced during the run, then delete the throwaway session.
        for event_type in ("execution_requested", "execution_completed"):
            require(not session_family_mutations(session, event_type),
                    "%s found during cleanup; no mutation is authorized" % event_type)
        cleanup_status, _ = http("DELETE", gateway + "/api/v1/sessions/" + session,
                                 auth=owner)
        require(cleanup_status in (200, 204),
                "throwaway session cleanup failed (HTTP %s)" % cleanup_status)
        print("CLEANUP_PROOF: session=%s disposed_without_mutation=true deleted=true"
              % session)

    print("CLARIFICATION_LIVECHECK_TURN_OK: with AGENT_ASKUSER_ENABLED on, one "
          "authorized %s turn PARKED a read-only clarification (no message_end, no "
          "confirmation_request), the owner answered it in-line over the R-4 route, "
          "the SAME turn resumed to a message_end, the completion was audited as "
          "chat_completed (the closed enum — no new event_type), the durable card "
          "is park_kind=clarification/status=answered with ZERO pending_calls, and "
          "there were ZERO execution_requested/execution_completed/"
          "confirmation_decided across the session family (no mutation, no dispatch, "
          "no auto-approval); throwaway session deleted" % OWNER_ROLE)


try:
    main()
except (RuntimeError, URLError, HTTPError, json.JSONDecodeError, KeyError) as error:
    # Single-line, secret-free failure: never echo tokens, credentials or bodies.
    reason = str(error) or error.__class__.__name__
    print("CLARIFICATION_LIVECHECK_FAILED: %s" % reason, file=sys.stderr)
    sys.exit(1)
PY
