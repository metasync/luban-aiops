#!/bin/sh

# Browser web-check tools smoke test (SPEC-049).
#
# Deterministic end-to-end assertions for the browser connector
# (web.* tools), runnable after `make deploy`. The script detects the
# committed state of GATEWAY_BROWSER_ENABLED and asserts the
# corresponding fail-closed behavior:
#
#   disabled (base default; the browser-dev profile is committed, so a
#   live dev deploy usually takes the enabled branch):
#     1. no web.* tool in discovery for an operator
#     2. web.navigate invoke fails closed with TOOL_NOT_FOUND
#   enabled (browser-dev posture):
#     1. all six web.* tools present in discovery with the right risk
#        tiers (read: navigate/snapshot/screenshot/fill_credential;
#        write: click/type)
#     2. navigation outside the allowlist is denied server-side
#        (BROWSER_ORIGIN_NOT_ALLOWED) even for an operator
#     3. navigation to the sample target succeeds and reports the page
#        title (sidecar reachable, CDP connected)
#     4. the CDP endpoint answers /json/version from the gateway pod
#
# Optional chat leg (RUN_CHAT_LEG=true, enabled-state only): a scripted
# chat asks the agent to run the sample web-check skill
# (platform-runbooks/web-checks/inventoryhealth): bind the write-class
# flow via web.navigate (read tier — auto-allowed), fill both login
# fields via web.fill_credential (read tier), then submit. The single
# write-tier interaction — the sign-in web.click — parks one
# confirmation_request (the one HITL gate per mutating flow, D-3); the
# demo approves it via /api/v1/chat/confirm. The confirm response IS the
# resumed-turn stream (SPEC-020 R-2): it opens with the confirmation_
# result frame and carries the resumed turn to completion, so the demo
# asserts the "Signed in"/operational outcome on that stream, then
# verifies the durable surfaces (exactly one approved card carrying the
# signed web.click execution receipt, no park left pending). It never
# sends a follow-up message — a new turn while the resume is active is
# rejected 409. The chat leg depends on the model choosing the tools, so
# it is opt-in like the other demos' chat legs.
#
# Prerequisites:
#   - kubectl context pointed at the dev cluster
#   - a port-forward for the identity broker (token issuance):
#       kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000
#   - for the chat leg additionally a port-forward for the platform-gateway:
#       kubectl -n dev-luban-aiops port-forward svc/platform-gateway 18083:8000
#   - the browser credential sets synced (shared/platform-ops/gitops/
#     sync-browser-credentials.sh; `make deploy` runs it)
#
# Environment overrides:
#   NAMESPACE        (default dev-luban-aiops)
#   IDENTITY_URL     (default http://localhost:18081)
#   GATEWAY_URL      (default http://localhost:18083, chat leg)
#   TEST_USER        (default luban-operator)
#   APPROVER_USER    (default luban-approver, chat leg decider)
#   RUN_CHAT_LEG=true to run the opt-in chat leg (enabled-state only)

set -eu

NAMESPACE="${NAMESPACE:-dev-luban-aiops}"
IDENTITY_URL="${IDENTITY_URL:-http://localhost:18081}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:18083}"
TEST_USER="${TEST_USER:-luban-operator}"
APPROVER_USER="${APPROVER_USER:-luban-approver}"
SKILL_ID="platform-runbooks/web-checks/inventoryhealth"
TARGET_URL="http://browser-check-target:8080/"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# Cluster-side HTTP call against tool-gateway; echoes the body and returns
# the status code in $HTTP_CODE.
gateway_http() {
  GATEWAY_BODY=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -- \
    curl -s -o /tmp/gateway-body -w "%{http_code}" "$@")
  HTTP_CODE="$GATEWAY_BODY"
  GATEWAY_BODY=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -- \
    cat /tmp/gateway-body)
}

echo "==> [1/5] control check: tool-gateway rejects unauthenticated callers"

gateway_http http://localhost:8000/api/v2/tools
[ "$HTTP_CODE" = "401" ] || fail "discovery without token answered $HTTP_CODE, expected 401"

gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
  -H "Content-Type: application/json" \
  -d "{\"tool_name\":\"web.navigate\",\"parameters\":{\"url\":\"$TARGET_URL\"},\"request_id\":\"browser-demo-unauth\"}"
[ "$HTTP_CODE" = "401" ] || fail "invoke without token answered $HTTP_CODE, expected 401"
echo "unauthenticated discovery and invoke rejected (401)"

echo "==> [2/5] delegated operator token"

# Dev platform tokens from the identity broker, exchanged for tool-gateway
# audience using the committed service-client credential (SPEC-008).
CLIENTS=$(kubectl -n "$NAMESPACE" get secret identity-service-runtime-secrets \
  -o jsonpath='{.data.IDENTITY_SERVICE_CLIENTS}' | base64 -d)
CLIENT_ENTRY=$(printf '%s' "$CLIENTS" | tr ',' '\n' | grep '^platform-gateway:')
[ -n "$CLIENT_ENTRY" ] || fail "platform-gateway client missing from IDENTITY_SERVICE_CLIENTS"
CLIENT_SECRET=$(printf '%s' "$CLIENT_ENTRY" | cut -d: -f2)

platform_token() {
  TOKEN_RESPONSE=$(
    curl -fsS -X POST "$IDENTITY_URL/api/v1/auth/token" \
      -H "Content-Type: application/json" \
      -d "{\"username\": \"$1\", \"email\": \"$1@luban-aiops.local\", \"roles\": [\"$2\"], \"groups\": [\"$3\"]}"
  ) || fail "failed to obtain a platform token for $1"
  printf '%s' "$TOKEN_RESPONSE" | python3 -c "
import json, sys
print(json.load(sys.stdin).get('access_token', ''))"
}

delegate() {
  EXCHANGE_RESPONSE=$(
    curl -fsS -X POST "$IDENTITY_URL/api/v1/auth/exchange" \
      -u "platform-gateway:$CLIENT_SECRET" \
      -H "Content-Type: application/json" \
      -d "{\"subject_token\": \"$1\", \"audience\": \"tool-gateway\"}"
  ) || fail "delegation exchange failed"
  printf '%s' "$EXCHANGE_RESPONSE" | python3 -c "
import json, sys
print(json.load(sys.stdin).get('access_token', ''))"
}

OPERATOR_PLATFORM_TOKEN=$(platform_token "$TEST_USER" operator ops-operators)
[ -n "$OPERATOR_PLATFORM_TOKEN" ] || fail "broker issued no platform token for $TEST_USER"
OPERATOR_TOKEN=$(delegate "$OPERATOR_PLATFORM_TOKEN")
[ -n "$OPERATOR_TOKEN" ] || fail "no delegated token for $TEST_USER"
echo "delegated tool-gateway token issued for $TEST_USER"

BROWSER_ENABLED=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o jsonpath='{.data.GATEWAY_BROWSER_ENABLED}')
[ -n "$BROWSER_ENABLED" ] || BROWSER_ENABLED=false
echo "GATEWAY_BROWSER_ENABLED=$BROWSER_ENABLED (from platform-runtime-config)"

DISCOVERY=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -- \
  curl -fsS -H "Authorization: Bearer $OPERATOR_TOKEN" \
  http://localhost:8000/api/v2/tools)

if [ "$BROWSER_ENABLED" != "true" ]; then
  echo "==> [3/5] deny-by-default: no web.* tools in discovery"

  printf '%s' "$DISCOVERY" | grep -q '"web\.' \
    && fail "browser connector disabled but web.* tools appear in discovery"
  echo "no web.* tools registered (connector flag off)"

  echo "==> [4/5] deny-by-default: invoke fails closed"

  gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
    -H "Authorization: Bearer $OPERATOR_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"web.navigate\",\"parameters\":{\"url\":\"$TARGET_URL\"},\"request_id\":\"browser-demo-off\"}"
  [ "$HTTP_CODE" = "400" ] || fail "invoke answered $HTTP_CODE, expected 400"
  printf '%s' "$GATEWAY_BODY" | grep -q 'TOOL_NOT_FOUND' \
    || fail "invoke did not fail with TOOL_NOT_FOUND: $GATEWAY_BODY"
  echo "operator web.navigate rejected with TOOL_NOT_FOUND"

  echo ""
  echo "Browser web-check smoke test passed (deny-by-default):"
  echo "  - unauthenticated callers rejected"
  echo "  - no web.* tools in discovery"
  echo "  - invoke fails closed with TOOL_NOT_FOUND"
  exit 0
fi

echo "==> [3/5] browser-dev: six web.* tools with correct risk tiers"

printf '%s' "$DISCOVERY" | python3 -c "
import json, sys
tools = {t['name']: t for t in json.load(sys.stdin)}
expect = {
    'web.navigate': 'read',
    'web.snapshot': 'read',
    'web.screenshot': 'read',
    'web.fill_credential': 'read',
    'web.click': 'write',
    'web.type': 'write',
}
for name, risk in expect.items():
    tool = tools.get(name)
    assert tool is not None, '%s missing from discovery' % name
    assert tool.get('risk_level') == risk, \
        '%s risk_level is %r, expected %s' % (name, tool.get('risk_level'), risk)
    assert tool.get('category') == 'browser', \
        '%s category is %r, expected browser' % (name, tool.get('category'))" \
  || fail "discovery does not carry the six web.* tools with expected risk tiers"
echo "all six web.* tools registered (4 read, 2 write)"

echo "==> [4/5] origin allowlist: outside denied, sample target admitted"

gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"web.navigate","parameters":{"url":"https://evil.example/login"},"request_id":"browser-demo-deny"}'
printf '%s' "$GATEWAY_BODY" | grep -q 'BROWSER_ORIGIN_NOT_ALLOWED' \
  || fail "off-allowlist navigation was not denied server-side: $GATEWAY_BODY"
echo "off-allowlist origin denied server-side (BROWSER_ORIGIN_NOT_ALLOWED)"

gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"tool_name\":\"web.navigate\",\"parameters\":{\"url\":\"$TARGET_URL\"},\"request_id\":\"browser-demo-open\"}"
[ "$HTTP_CODE" = "200" ] || fail "allowed navigation answered $HTTP_CODE: $GATEWAY_BODY"
printf '%s' "$GATEWAY_BODY" | grep -q '"status": *"success"\|"status":"success"' \
  || fail "allowed navigation did not succeed: $GATEWAY_BODY"
printf '%s' "$GATEWAY_BODY" | grep -q 'Inventory Portal' \
  || fail "navigation result lacks the sample target's page title: $GATEWAY_BODY"
echo "navigation to the sample target succeeded (page title reported)"

gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"web.snapshot","parameters":{},"request_id":"browser-demo-snapshot"}'
printf '%s' "$GATEWAY_BODY" | grep -q 'Sign in' \
  || fail "snapshot of the login page lacks the Sign in button: $GATEWAY_BODY"
echo "snapshot enumerates the login form's interactive elements"

echo "==> [5/5] CDP endpoint reachable from the gateway pod"

kubectl -n "$NAMESPACE" exec deployment/tool-gateway -- \
  curl -fsS http://localhost:9222/json/version >/dev/null \
  || fail "CDP endpoint ws://localhost:9222 not reachable from the gateway pod"
echo "chromium-headless-shell sidecar answers /json/version"

if [ "${RUN_CHAT_LEG:-}" = "true" ]; then
  echo "==> [CHAT] scripted web check: login flow with the single HITL gate"

  HITL_TIMEOUT=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
    -o jsonpath='{.data.AGENT_HITL_CONFIRM_TIMEOUT}')
  [ "${HITL_TIMEOUT:-600}" != "0" ] \
    || fail "AGENT_HITL_CONFIRM_TIMEOUT=0 disables HITL bridging; the chat leg cannot run"

  # SPEC-030 R-4 style: the default bundle requires a designated approver
  # for tools:mutate, so the confirm step runs under a second identity.
  APPROVER_PLATFORM_TOKEN=$(platform_token "$APPROVER_USER" approver ops-approvers)
  [ -n "$APPROVER_PLATFORM_TOKEN" ] \
    || fail "broker issued no platform token for $APPROVER_USER"

  SESSION_RESPONSE=$(curl -fsS --max-time 30 -X POST \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}' \
    "$GATEWAY_URL/api/v1/sessions") || fail "session creation failed"
  CHAT_SESSION=$(printf '%s' "$SESSION_RESPONSE" | python3 -c "
import json, sys
print(json.load(sys.stdin).get('session_id', ''))")
  [ -n "$CHAT_SESSION" ] || fail "session creation returned no session_id"

  CHAT_MESSAGE="Run the browser web check from skill $SKILL_ID: navigate to $TARGET_URL binding that skill id, sign in to the inventory portal filling both the username and the password from the browser-check-target credential set with web.fill_credential (never web.type), so the sign-in click is the only write-tier step, confirm the page shows Signed in, then reach /status on the same origin with web.navigate (a read-tier step — never another click; the sign-in click is the flow's one and only write-tier interaction) and report the component statuses."

  STREAM_OUTPUT=$(curl -fsS --max-time 300 -N \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    "$GATEWAY_URL/api/v1/chat/stream?session_id=$CHAT_SESSION&message=$(python3 -c "
import urllib.parse, sys
print(urllib.parse.quote(sys.argv[1]))" "$CHAT_MESSAGE")") \
    || fail "chat stream request failed"

  printf '%s' "$STREAM_OUTPUT" | grep -q '"type": *"confirmation_request"\|"type":"confirmation_request"' \
    || fail "no confirmation_request frame (did the model reach the sign-in web.click?)"
  echo "the sign-in write-tier interaction parked the single confirmation card (one HITL gate)"

  CONFIRM_ID=$(printf '%s' "$STREAM_OUTPUT" | python3 -c "
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line.startswith('data:'):
        continue
    try:
        frame = json.loads(line[5:].strip())
    except ValueError:
        continue
    if frame.get('type') == 'confirmation_request':
        print(frame.get('confirm_id', ''))
        break
")
  [ -n "$CONFIRM_ID" ] || fail "confirmation_request frame carried no confirm_id"

  # The confirm response is the resumed-turn stream (SPEC-020 R-2): it
  # opens with the confirmation_result frame, then the approved web.click
  # executes and the agent continues the flow to /status and reports the
  # outcome — all in this one stream. Give it the first turn's budget (it
  # carries a navigate + snapshot + final reply).
  CONFIRM_OUTPUT=$(curl -fsS --max-time 300 -X POST \
    -H "Authorization: Bearer $APPROVER_PLATFORM_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$CHAT_SESSION\", \"confirm_id\": \"$CONFIRM_ID\", \"decision\": \"approve\"}" \
    "$GATEWAY_URL/api/v1/chat/confirm") || fail "approver approve call failed"
  printf '%s' "$CONFIRM_OUTPUT" | grep -q '"status": *"approved"\|"status":"approved"' \
    || fail "confirmation_result did not report the approval: $CONFIRM_OUTPUT"
  echo "approval applied; the kernel resumed the login flow"

  # The resumed turn completes inside the confirm stream — no follow-up
  # message (a new turn while the resume is active is rejected 409). Had
  # the flow parked a second card, the stream would have ended on that
  # confirmation_request instead of the outcome text.
  printf '%s' "$CONFIRM_OUTPUT" | grep -qi 'operational\|Signed in' \
    || fail "the resumed turn reached neither a signed-in state nor operational components: $CONFIRM_OUTPUT"
  echo "the confirm stream carried the resumed turn to the verification point"

  # Durable proof (SPEC-031/037): the owner's session detail carries
  # exactly one approved card — the sign-in web.click — with a signed
  # execution receipt produced under the approver's identity inside the
  # operator-bound flow. That receipt is what the chat-session-keyed
  # browser pool (SPEC-049 R-1) makes survive the owner→approver switch.
  SESSION_DETAIL=$(curl -fsS --max-time 30 \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    "$GATEWAY_URL/api/v1/sessions/$CHAT_SESSION") \
    || fail "owner session detail fetch failed"
  printf '%s' "$SESSION_DETAIL" | python3 -c "
import json, sys
detail = json.load(sys.stdin)
assert detail.get('pending_confirmation') is not True, \
    'the session still parks a confirmation after the resume completed'
cards = detail.get('confirmations') or []
assert len(cards) == 1, \
    'expected exactly one confirmation card (one write gate), got %d' % len(cards)
card = cards[0]
assert card.get('confirm_id') == sys.argv[1], 'the single card is not the decided one'
assert card.get('status') == 'approved', \
    'card status is %r, expected approved' % card.get('status')
assert card.get('decider_user_id'), 'approved card carries no decider'
executions = card.get('executions') or []
assert executions, 'approved card carries no execution rows'
row = executions[0]
assert row.get('tool_name') == 'web.click', \
    'execution row names %r, expected web.click' % row.get('tool_name')
assert row.get('status') in ('succeeded', 'failed', 'timeout'), \
    'execution row status is %r, expected a closed receipt status' % row.get('status')
assert row.get('digest_match') is True, \
    'invoked arguments did not match the signed request'
receipt = row.get('receipt') or {}
assert receipt.get('execution_id'), 'receipt carries no execution_id'
assert receipt.get('signature'), 'receipt carries no signature'
assert receipt.get('outcome_digest'), 'receipt carries no outcome digest'" "$CONFIRM_ID" \
    || fail "owner session detail lacks the single approved web.click card with a signed receipt"
  echo "session detail carries exactly one approved card (web.click) with a signed receipt"
else
  echo "==> [CHAT] chat leg skipped (RUN_CHAT_LEG unset; opt-in)"
fi

echo ""
echo "Browser web-check smoke test passed (browser-dev posture):"
echo "  - unauthenticated callers rejected"
echo "  - six web.* tools registered with correct risk tiers"
echo "  - off-allowlist navigation denied server-side"
echo "  - allowed navigation and snapshot succeeded on the sample target"
echo "  - CDP sidecar reachable from the gateway pod"
