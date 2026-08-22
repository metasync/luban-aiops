#!/bin/sh

# Mutating tools smoke test (SPEC-021 R-6).
#
# Deterministic end-to-end assertions for the bounded mutating capability
# (k8s.delete_pod), runnable after `make deploy`. The script detects the
# committed state of GATEWAY_MUTATING_TOOLS_ENABLED and asserts the
# corresponding fail-closed behavior:
#
#   disabled (committed default):
#     1. unauthenticated discovery/invoke rejected (401)
#     2. k8s.delete_pod absent from discovery even for an operator
#     3. invoke fails closed with TOOL_NOT_FOUND
#     4. the tool-gateway service account cannot delete pods
#   enabled (opt-in):
#     1. unauthenticated discovery/invoke rejected (401)
#     2. k8s.delete_pod present in discovery with risk_level=write
#     3. observer invoke denied 403 (no tools:mutate grant)
#     4. operator invoke passes the policy gate (deleting a deliberately
#        nonexistent pod ends in a structured K8s tool error, never a
#        policy denial) and reports RBAC status
#
# Optional HITL leg (RUN_HITL_LEG=true, enabled-state only): a scripted
# chat asks the agent to delete a deliberately nonexistent pod; the demo
# asserts the stream parks with a confirmation_request carrying
# risk_level=write, approves it via /api/v1/chat/confirm, and checks the
# durable trail carries both confirmation_decided and the tool_invoked
# attempt. The deny path (leaves everything untouched) is covered by the
# agent-platform/platform-gateway unit suites because a parked
# confirmation is single-shot. The chat leg depends on the model choosing
# the tool, so it is opt-in like the other demos' chat legs.
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
#   OBSERVER_USER      (default luban-observer)
#   RUN_HITL_LEG=true  to run the opt-in chat leg (enabled-state only)

set -eu

NAMESPACE="${NAMESPACE:-dev-luban-aiops}"
IDENTITY_URL="${IDENTITY_URL:-http://localhost:18081}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:18083}"
TEST_USER="${TEST_USER:-luban-operator}"
OBSERVER_USER="${OBSERVER_USER:-luban-observer}"
RUN_SUFFIX="$(date +%s)-$$"
MISSING_POD="luban-mutating-demo-$RUN_SUFFIX"

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
  -d '{"tool_name":"k8s.delete_pod","parameters":{"name":"x"},"request_id":"mut-demo-unauth"}'
[ "$HTTP_CODE" = "401" ] || fail "invoke without token answered $HTTP_CODE, expected 401"
echo "unauthenticated discovery and invoke rejected (401)"

echo "==> [2/5] delegated tokens for operator and observer"

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

OBSERVER_PLATFORM_TOKEN=$(platform_token "$OBSERVER_USER" read-only-observer ops-observers)
OBSERVER_TOKEN=$(delegate "$OBSERVER_PLATFORM_TOKEN")
[ -n "$OBSERVER_TOKEN" ] || fail "no delegated token for $OBSERVER_USER"
echo "delegated tool-gateway tokens issued for $TEST_USER and $OBSERVER_USER"

MUTATING_ENABLED=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o jsonpath='{.data.GATEWAY_MUTATING_TOOLS_ENABLED}')
[ -n "$MUTATING_ENABLED" ] || MUTATING_ENABLED=false
echo "GATEWAY_MUTATING_TOOLS_ENABLED=$MUTATING_ENABLED (from platform-runtime-config)"

DISCOVERY=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -- \
  curl -fsS -H "Authorization: Bearer $OPERATOR_TOKEN" \
  http://localhost:8000/api/v2/tools)

RBAC_ALLOWED=$(kubectl auth can-i delete pods -n "$NAMESPACE" \
  --as="system:serviceaccount:$NAMESPACE:tool-gateway")

if [ "$MUTATING_ENABLED" != "true" ]; then
  echo "==> [3/5] deny-by-default: k8s.delete_pod absent from discovery"

  printf '%s' "$DISCOVERY" | grep -q 'k8s.delete_pod' \
    && fail "mutating tools disabled but k8s.delete_pod appears in discovery"
  echo "k8s.delete_pod not registered (risk-tier admission gate closed)"

  echo "==> [4/5] deny-by-default: invoke fails closed"

  gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
    -H "Authorization: Bearer $OPERATOR_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"k8s.delete_pod\",\"parameters\":{\"name\":\"$MISSING_POD\"},\"request_id\":\"mut-demo-$RUN_SUFFIX\"}"
  [ "$HTTP_CODE" = "400" ] || fail "invoke answered $HTTP_CODE, expected 400"
  printf '%s' "$GATEWAY_BODY" | grep -q 'TOOL_NOT_FOUND' \
    || fail "invoke did not fail with TOOL_NOT_FOUND: $GATEWAY_BODY"
  echo "operator invoke rejected with TOOL_NOT_FOUND"

  [ "$RBAC_ALLOWED" = "no" ] \
    || fail "mutating tools disabled but the service account can delete pods"
  echo "the tool-gateway service account cannot delete pods (opt-in RBAC absent)"

  echo ""
  echo "Mutating tools smoke test passed (deny-by-default):"
  echo "  - unauthenticated callers rejected"
  echo "  - k8s.delete_pod absent from discovery"
  echo "  - invoke fails closed with TOOL_NOT_FOUND"
  echo "  - no pod-delete RBAC granted"
  exit 0
fi

echo "==> [3/5] opt-in: k8s.delete_pod present with risk_level=write"

printf '%s' "$DISCOVERY" | python3 -c "
import json, sys
tools = {t['name']: t for t in json.load(sys.stdin)}
tool = tools.get('k8s.delete_pod')
assert tool is not None, 'k8s.delete_pod missing from discovery'
assert tool.get('risk_level') == 'write', \
    'risk_level is %r, expected write' % tool.get('risk_level')" \
  || fail "discovery does not carry k8s.delete_pod with risk_level=write"
echo "k8s.delete_pod registered with risk_level=write"

echo "==> [4/5] policy gate: observer denied, operator admitted"

gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
  -H "Authorization: Bearer $OBSERVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"tool_name\":\"k8s.delete_pod\",\"parameters\":{\"name\":\"$MISSING_POD\"},\"request_id\":\"mut-demo-observer-$RUN_SUFFIX\"}"
[ "$HTTP_CODE" = "403" ] || fail "observer invoke answered $HTTP_CODE, expected 403"
printf '%s' "$GATEWAY_BODY" | grep -q 'denied' \
  || fail "observer invoke was not a policy denial: $GATEWAY_BODY"
echo "observer invoke denied (no tools:mutate grant)"

gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"tool_name\":\"k8s.delete_pod\",\"parameters\":{\"name\":\"$MISSING_POD\"},\"request_id\":\"mut-demo-operator-$RUN_SUFFIX\"}"
[ "$HTTP_CODE" = "200" ] || fail "operator invoke answered $HTTP_CODE, expected 200: $GATEWAY_BODY"
printf '%s' "$GATEWAY_BODY" | grep -q '"status": *"denied"\|"status":"denied"' \
  && fail "operator invoke was denied despite the tools:mutate grant"
printf '%s' "$GATEWAY_BODY" | grep -q 'risk_level.*write\|"write"' \
  || fail "operator invoke evidence carried no write risk tier: $GATEWAY_BODY"
# The target pod deliberately does not exist: the call must reach the
# connector and fail there with a structured K8s error, proving every
# policy gate opened.
printf '%s' "$GATEWAY_BODY" | grep -qi 'error\|not found' \
  || fail "operator invoke did not reach the connector: $GATEWAY_BODY"
echo "operator invoke passed the admission and policy gates (connector-level error for the nonexistent pod)"

echo "==> [5/5] RBAC status for the tool-gateway service account"

if [ "$RBAC_ALLOWED" = "yes" ]; then
  echo "pod-delete RBAC applied: the service account can delete pods"
else
  echo "NOTE: pod-delete RBAC not applied; deletes will fail with K8S_PERMISSION_DENIED."
  echo "Apply it with (it rides the mutating-dev runtime profile, SPEC-022):"
  echo "  kubectl apply -f shared/platform-ops/gitops/runtime-profiles/mutating-dev/tool-gateway-pod-delete.yaml"
fi

if [ "${RUN_HITL_LEG:-}" = "true" ]; then
  echo "==> [HITL] scripted chat: park with risk_level=write, then approve"

  HITL_TIMEOUT=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
    -o jsonpath='{.data.AGENT_HITL_CONFIRM_TIMEOUT}')
  [ "${HITL_TIMEOUT:-600}" != "0" ] \
    || fail "AGENT_HITL_CONFIRM_TIMEOUT=0 disables HITL bridging; the chat leg cannot run"

  HITL_SESSION="mut-demo-session-$RUN_SUFFIX"
  CHAT_MESSAGE="Delete the pod named $MISSING_POD in namespace $NAMESPACE with the k8s.delete_pod tool right away; no need to inspect anything first."

  STREAM_OUTPUT=$(curl -fsS --max-time 180 -N \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    "$GATEWAY_URL/api/v1/chat/stream?session_id=$HITL_SESSION&message=$(python3 -c "
import urllib.parse, sys
print(urllib.parse.quote(sys.argv[1]))" "$CHAT_MESSAGE")") \
    || fail "chat stream request failed"

  printf '%s' "$STREAM_OUTPUT" | grep -q '"type": *"confirmation_request"\|"type":"confirmation_request"' \
    || fail "no confirmation_request frame (did the model choose k8s.delete_pod?)"
  printf '%s' "$STREAM_OUTPUT" | grep -q '"risk_level": *"write"\|"risk_level":"write"' \
    || fail "the parked confirmation carried no risk_level=write pending call"

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
  echo "parked confirmation $CONFIRM_ID carries risk_level=write"

  CONFIRM_OUTPUT=$(curl -fsS --max-time 120 -X POST \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$HITL_SESSION\", \"confirm_id\": \"$CONFIRM_ID\", \"decision\": \"approve\"}" \
    "$GATEWAY_URL/api/v1/chat/confirm") || fail "approve call failed"

  printf '%s' "$CONFIRM_OUTPUT" | grep -q '"type": *"confirmation_result"\|"type":"confirmation_result"' \
    || fail "approve stream carried no confirmation_result frame"
  printf '%s' "$CONFIRM_OUTPUT" | grep -q '"status": *"approved"\|"status":"approved"' \
    || fail "confirmation_result did not report the approval: $CONFIRM_OUTPUT"
  echo "approval applied; the kernel resumed and executed the call"

  echo "==> [AUDIT] confirmation_decided and tool_invoked on the durable trail"

  AUDIT_CLIENTS=$(kubectl -n "$NAMESPACE" get secret audit-service-runtime-secrets \
    -o jsonpath='{.data.AUDIT_INGEST_CLIENTS}' | base64 -d)
  AUDIT_QUERY_SECRET=$(printf '%s' "$AUDIT_CLIENTS" | tr ',' '\n' \
    | grep '^platform-gateway=' | cut -d= -f2-)
  [ -n "$AUDIT_QUERY_SECRET" ] || fail "platform-gateway entry missing from AUDIT_INGEST_CLIENTS"

  DECIDED_EVENTS=$(kubectl -n "$NAMESPACE" exec deployment/audit-service -- \
    curl -fsS -u "platform-gateway:${AUDIT_QUERY_SECRET}" \
    "http://localhost:8000/api/v1/audit/events?event_type=confirmation_decided&limit=50")
  printf '%s' "$DECIDED_EVENTS" | grep -q "$CONFIRM_ID" \
    || fail "no confirmation_decided event for $CONFIRM_ID on the durable trail"
  echo "confirmation_decided for $CONFIRM_ID is on the durable trail"

  GATEWAY_AUDIT_SECRET=$(printf '%s' "$AUDIT_CLIENTS" | tr ',' '\n' \
    | grep '^tool-gateway=' | cut -d= -f2-)
  INVOKED_EVENTS=$(kubectl -n "$NAMESPACE" exec deployment/audit-service -- \
    curl -fsS -u "tool-gateway:${GATEWAY_AUDIT_SECRET}" \
    "http://localhost:8000/api/v1/audit/events?event_type=tool_invoked&limit=100")
  printf '%s' "$INVOKED_EVENTS" | grep -q "$MISSING_POD" \
    || fail "no tool_invoked event for k8s.delete_pod($MISSING_POD) on the durable trail"
  echo "tool_invoked for k8s.delete_pod($MISSING_POD) is on the durable trail"
else
  echo "==> [HITL] chat leg skipped (RUN_HITL_LEG unset; opt-in)"
fi

echo ""
echo "Mutating tools smoke test passed (opt-in):"
echo "  - unauthenticated callers rejected"
echo "  - k8s.delete_pod registered with risk_level=write"
echo "  - observer denied (tools:mutate withheld)"
echo "  - operator admitted through every policy gate"
