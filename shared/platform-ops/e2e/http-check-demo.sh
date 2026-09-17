#!/bin/sh

# HTTP service-check tools smoke test (SPEC-058 R-8).
#
# Deterministic end-to-end assertions for the bounded HTTP surface
# (http.get read tier, http.post write tier), runnable after `make deploy`.
# The script detects the committed state of GATEWAY_HTTP_ENABLED and asserts
# the corresponding fail-closed behaviour:
#
#   disabled (committed default):
#     1. unauthenticated discovery/invoke rejected (401)
#     2. http.get and http.post absent from discovery even for an operator
#     3. invoke fails closed with TOOL_NOT_FOUND
#   enabled (opt-in, runtime-profiles/browser-dev):
#     1. unauthenticated discovery/invoke rejected (401)
#     2. http.get present with risk_level=read; http.post present with
#        risk_level=write only when GATEWAY_MUTATING_TOOLS_ENABLED=true
#     3. an origin outside GATEWAY_HTTP_ALLOW_ORIGINS is denied
#        (HTTP_ORIGIN_NOT_ALLOWED, 403) before any socket is opened
#     4. a live http.get against the first allowlisted origin projects the
#        upstream status — skipped with a note when that origin is not
#        reachable, because SPEC-059's acme-admin app supplies the real
#        target and this base demo must pass without it
#
# Optional HITL leg (RUN_HITL_LEG=true, enabled-state only): a scripted chat
# asks the agent to lock a user with http.post against the allowlisted
# target. The demo asserts the stream parks a confirmation_request carrying
# approval_kind=action — the SPEC-054 discriminator that separates a
# non-browser write from a browser flow — with risk_level=write and a
# change_request.summary naming the origin and path (the SPEC-058 R-5
# card-legibility proof), then a second approver identity approves it via
# /api/v1/chat/confirm and the confirmation_result reports approved. The leg
# depends on the model choosing the tool, so it is opt-in like the other
# demos' chat legs.
#
# Prerequisites:
#   - kubectl context pointed at the dev cluster
#   - a port-forward for the identity broker (token issuance):
#       kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000
#   - for the HITL leg additionally a port-forward for the platform-gateway:
#       kubectl -n dev-luban-aiops port-forward svc/platform-gateway 18083:8000
#
# Environment overrides:
#   NAMESPACE          (default dev-luban-aiops)
#   IDENTITY_URL       (default http://localhost:18081)
#   GATEWAY_URL        (default http://localhost:18083, HITL leg)
#   TEST_USER          (default luban-operator)
#   APPROVER_USER      (default luban-approver, HITL leg: tier_2 decider)
#   DENIED_ORIGIN      (default http://http-check-denied.invalid:8080)
#   RUN_HITL_LEG=true  to run the opt-in chat leg (enabled-state only)

set -eu

NAMESPACE="${NAMESPACE:-dev-luban-aiops}"
IDENTITY_URL="${IDENTITY_URL:-http://localhost:18081}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:18083}"
TEST_USER="${TEST_USER:-luban-operator}"
APPROVER_USER="${APPROVER_USER:-luban-approver}"
DENIED_ORIGIN="${DENIED_ORIGIN:-http://http-check-denied.invalid:8080}"
RUN_SUFFIX="$(date +%s)-$$"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# Cluster-side HTTP call; sets HTTP_CODE and GATEWAY_BODY without printing.
gateway_http() {
  HTTP_CODE=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -c tool-gateway -- \
    curl -sS -o /tmp/gateway-body -w "%{http_code}" "$@") \
    || fail "in-cluster gateway call did not complete"
  GATEWAY_BODY=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -c tool-gateway -- \
    cat /tmp/gateway-body)
}

json_field() {
  printf '%s' "$1" | python3 -c "
import json, sys
payload = json.load(sys.stdin)
value = payload
for key in sys.argv[1].split('.'):
    value = value.get(key) if isinstance(value, dict) else None
print(value if value is not None else '')" "$2"
}

echo "==> [1/5] control check: tool-gateway rejects unauthenticated callers"

gateway_http http://localhost:8000/api/v2/tools
[ "$HTTP_CODE" = "401" ] || fail "discovery without token answered $HTTP_CODE, expected 401"

gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"http.get","parameters":{"url":"http://example.invalid/"},"request_id":"http-demo-unauth"}'
[ "$HTTP_CODE" = "401" ] || fail "invoke without token answered $HTTP_CODE, expected 401"
echo "unauthenticated discovery and invoke rejected (401)"

echo "==> [2/5] delegated token for the operator"

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

HTTP_ENABLED=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o jsonpath='{.data.GATEWAY_HTTP_ENABLED}')
[ -n "$HTTP_ENABLED" ] || HTTP_ENABLED=false
HTTP_ALLOW_ORIGINS=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o jsonpath='{.data.GATEWAY_HTTP_ALLOW_ORIGINS}')
MUTATING_ENABLED=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o jsonpath='{.data.GATEWAY_MUTATING_TOOLS_ENABLED}')
[ -n "$MUTATING_ENABLED" ] || MUTATING_ENABLED=false
echo "GATEWAY_HTTP_ENABLED=$HTTP_ENABLED GATEWAY_MUTATING_TOOLS_ENABLED=$MUTATING_ENABLED"
echo "GATEWAY_HTTP_ALLOW_ORIGINS=${HTTP_ALLOW_ORIGINS:-<empty>}"

DISCOVERY=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -- \
  curl -fsS -H "Authorization: Bearer $OPERATOR_TOKEN" \
  http://localhost:8000/api/v2/tools)

if [ "$HTTP_ENABLED" != "true" ]; then
  echo "==> [3/5] deny-by-default: http.get and http.post absent from discovery"

  printf '%s' "$DISCOVERY" | python3 -c "
import json, sys
names = {t['name'] for t in json.load(sys.stdin)}
assert 'http.get' not in names, 'http.get registered while disabled'
assert 'http.post' not in names, 'http.post registered while disabled'" \
    || fail "an http.* tool is registered despite GATEWAY_HTTP_ENABLED=$HTTP_ENABLED"
  echo "no http.* tool registered (connector gated off)"

  echo "==> [4/5] deny-by-default: invoke fails closed"

  gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
    -H "Authorization: Bearer $OPERATOR_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"http.get\",\"parameters\":{\"url\":\"$DENIED_ORIGIN/healthz\"},\"request_id\":\"http-demo-$RUN_SUFFIX\"}"
  [ "$HTTP_CODE" = "400" ] || fail "invoke answered $HTTP_CODE, expected 400"
  printf '%s' "$GATEWAY_BODY" | grep -q 'TOOL_NOT_FOUND' \
    || fail "invoke did not fail with TOOL_NOT_FOUND: $GATEWAY_BODY"
  echo "operator invoke of http.get rejected with TOOL_NOT_FOUND"

  echo ""
  echo "HTTP service-check smoke test passed (deny-by-default):"
  echo "  - unauthenticated callers rejected"
  echo "  - http.get and http.post absent from discovery"
  echo "  - invoke fails closed with TOOL_NOT_FOUND"
  exit 0
fi

echo "==> [3/5] opt-in: http.get present (read); http.post tracks the mutating flag"

printf '%s' "$DISCOVERY" | python3 -c "
import json, sys
tools = {t['name']: t for t in json.load(sys.stdin)}
tool = tools.get('http.get')
assert tool is not None, 'http.get missing from discovery'
assert tool.get('risk_level') == 'read', \
    'http.get risk_level is %r, expected read' % tool.get('risk_level')" \
  || fail "discovery does not carry http.get with risk_level=read"
echo "http.get registered with risk_level=read"

if [ "$MUTATING_ENABLED" = "true" ]; then
  printf '%s' "$DISCOVERY" | python3 -c "
import json, sys
tools = {t['name']: t for t in json.load(sys.stdin)}
tool = tools.get('http.post')
assert tool is not None, 'http.post missing from discovery'
assert tool.get('risk_level') == 'write', \
    'http.post risk_level is %r, expected write' % tool.get('risk_level')" \
    || fail "discovery does not carry http.post with risk_level=write"
  echo "http.post registered with risk_level=write (mutating tools enabled)"
else
  printf '%s' "$DISCOVERY" | python3 -c "
import json, sys
names = {t['name'] for t in json.load(sys.stdin)}
assert 'http.post' not in names, 'http.post registered while mutating tools are off'" \
    || fail "http.post is registered despite GATEWAY_MUTATING_TOOLS_ENABLED=$MUTATING_ENABLED"
  echo "http.post absent (risk-tier admission gate closed)"
fi

echo "==> [4/5] allowlist denial: an origin outside GATEWAY_HTTP_ALLOW_ORIGINS is refused"

gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"tool_name\":\"http.get\",\"parameters\":{\"url\":\"$DENIED_ORIGIN/healthz\"},\"request_id\":\"http-demo-denied-$RUN_SUFFIX\"}"
[ "$HTTP_CODE" = "403" ] || fail "denied-origin invoke answered $HTTP_CODE, expected 403: $GATEWAY_BODY"
printf '%s' "$GATEWAY_BODY" | grep -q 'HTTP_ORIGIN_NOT_ALLOWED' \
  || fail "denied-origin invoke did not report HTTP_ORIGIN_NOT_ALLOWED: $GATEWAY_BODY"
echo "http.get to $DENIED_ORIGIN denied with HTTP_ORIGIN_NOT_ALLOWED (no socket opened)"

echo "==> [5/5] live http.get against the allowlisted target"

FIRST_ORIGIN=$(printf '%s' "$HTTP_ALLOW_ORIGINS" | tr ',' '\n' \
  | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | grep -v '^$' | head -n1 || true)

LIVE_OK=false
if [ -z "$FIRST_ORIGIN" ]; then
  echo "NOTE: GATEWAY_HTTP_ALLOW_ORIGINS is empty; no live target to check."
  echo "      The registration and allowlist-denial assertions above are the"
  echo "      whole enabled-state proof when no origin is listed."
else
  gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
    -H "Authorization: Bearer $OPERATOR_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"http.get\",\"parameters\":{\"url\":\"$FIRST_ORIGIN/healthz\"},\"request_id\":\"http-demo-live-$RUN_SUFFIX\"}"
  if [ "$HTTP_CODE" = "200" ]; then
    UPSTREAM_STATUS=$(json_field "$GATEWAY_BODY" data.status)
    [ -n "$UPSTREAM_STATUS" ] || fail "live http.get projected no data.status: $GATEWAY_BODY"
    echo "live http.get $FIRST_ORIGIN/healthz projected upstream status $UPSTREAM_STATUS"
    LIVE_OK=true
  else
    echo "NOTE: $FIRST_ORIGIN/healthz answered $HTTP_CODE (origin allowlisted but not"
    echo "      reachable). SPEC-059's acme-admin app supplies the live target; run"
    echo "      'make deploy-sample-app' to exercise the live get/post legs."
  fi
fi

if [ "${RUN_HITL_LEG:-}" = "true" ]; then
  echo "==> [HITL] scripted chat: park an http.post action card, tier_2 approve"

  [ "$MUTATING_ENABLED" = "true" ] \
    || fail "RUN_HITL_LEG=true needs GATEWAY_MUTATING_TOOLS_ENABLED=true so http.post registers"
  [ -n "$FIRST_ORIGIN" ] \
    || fail "RUN_HITL_LEG=true needs a non-empty GATEWAY_HTTP_ALLOW_ORIGINS to name a target"

  HITL_TIMEOUT=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
    -o jsonpath='{.data.AGENT_HITL_CONFIRM_TIMEOUT}')
  [ "${HITL_TIMEOUT:-600}" != "0" ] \
    || fail "AGENT_HITL_CONFIRM_TIMEOUT=0 disables HITL bridging; the chat leg cannot run"

  # SPEC-030 R-4: the default bundle requires a designated approver for
  # tools:mutate, so the confirm step runs under a second identity.
  APPROVER_PLATFORM_TOKEN=$(platform_token "$APPROVER_USER" approver ops-approvers)
  [ -n "$APPROVER_PLATFORM_TOKEN" ] \
    || fail "broker issued no platform token for $APPROVER_USER"

  LOCK_URL="$FIRST_ORIGIN/api/users/alice/lock"

  # Agent-platform rejects unknown session ids on the chat stream, so the
  # leg creates a dedicated session through the gateway first.
  SESSION_RESPONSE=$(curl -fsS --max-time 30 -X POST \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}' \
    "$GATEWAY_URL/api/v1/sessions") || fail "session creation failed"
  HITL_SESSION=$(printf '%s' "$SESSION_RESPONSE" | python3 -c "
import json, sys
print(json.load(sys.stdin).get('session_id', ''))")
  [ -n "$HITL_SESSION" ] || fail "session creation returned no session_id"
  CHAT_MESSAGE="Please lock the acme-admin account 'alice' right now by calling the http.post tool with url $LOCK_URL and body {\"locked\": true}. This is a routine demonstration against the allowlisted acme-admin sample app; use the acme-admin credential set for the request."

  STREAM_OUTPUT=$(curl -fsS --max-time 180 -N \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    "$GATEWAY_URL/api/v1/chat/stream?session_id=$HITL_SESSION&message=$(python3 -c "
import urllib.parse, sys
print(urllib.parse.quote(sys.argv[1]))" "$CHAT_MESSAGE")") \
    || fail "chat stream request failed"

  # The parked frame must carry the action discriminator, a write-tier
  # http.post pending call, and a change_request.summary naming the origin
  # and path (SPEC-058 R-5's card-legibility proof — an uncurated card would
  # read url: *** body: *** and prove nothing).
  printf '%s' "$STREAM_OUTPUT" | python3 -c "
import json, sys
origin = sys.argv[1]
frame = None
for line in sys.stdin:
    line = line.strip()
    if not line.startswith('data:'):
        continue
    try:
        candidate = json.loads(line[5:].strip())
    except ValueError:
        continue
    if candidate.get('type') == 'confirmation_request':
        frame = candidate
        break
assert frame is not None, 'no confirmation_request frame (did the model choose http.post?)'
assert frame.get('approval_kind') == 'action', \
    'approval_kind is %r, expected action' % frame.get('approval_kind')
calls = frame.get('pending_calls') or []
post = next((c for c in calls if c.get('tool_name') == 'http.post'), None)
assert post is not None, 'no http.post pending call on the parked frame'
assert post.get('risk_level') == 'write', \
    'http.post risk_level is %r, expected write' % post.get('risk_level')
change = post.get('change_request') or {}
summary = change.get('summary') or ''
assert origin.split('//', 1)[-1].split('/', 1)[0] in summary, \
    'change_request.summary %r does not name the origin' % summary
assert '/api/users/alice/lock' in summary, \
    'change_request.summary %r does not name the path' % summary
print(frame.get('confirm_id', ''))" "$FIRST_ORIGIN" > /tmp/http-demo-confirm-id \
    || fail "the parked http.post card did not carry the expected action/write/summary shape"
  CONFIRM_ID=$(cat /tmp/http-demo-confirm-id)
  rm -f /tmp/http-demo-confirm-id
  [ -n "$CONFIRM_ID" ] || fail "confirmation_request frame carried no confirm_id"
  echo "parked confirmation $CONFIRM_ID is an action card naming the origin and path"

  CONFIRM_OUTPUT=$(curl -fsS --max-time 120 -X POST \
    -H "Authorization: Bearer $APPROVER_PLATFORM_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$HITL_SESSION\", \"confirm_id\": \"$CONFIRM_ID\", \"decision\": \"approve\"}" \
    "$GATEWAY_URL/api/v1/chat/confirm") || fail "approver approve call failed"

  printf '%s' "$CONFIRM_OUTPUT" | grep -q '"type": *"confirmation_result"\|"type":"confirmation_result"' \
    || fail "approve stream carried no confirmation_result frame"
  printf '%s' "$CONFIRM_OUTPUT" | grep -q '"status": *"approved"\|"status":"approved"' \
    || fail "confirmation_result did not report the approval: $CONFIRM_OUTPUT"
  echo "approval by $APPROVER_USER applied; the parked http.post resumed"
else
  echo "==> [HITL] chat leg skipped (RUN_HITL_LEG unset; opt-in)"
fi

echo ""
echo "HTTP service-check smoke test passed (opt-in):"
echo "  - unauthenticated callers rejected"
echo "  - http.get registered read; http.post tracks the mutating flag"
echo "  - an out-of-allowlist origin is denied before any socket is opened"
if [ "$LIVE_OK" = "true" ]; then
  echo "  - a live http.get projected the allowlisted target's upstream status"
fi
