#!/bin/sh

# Incident demo smoke test (SPEC-015 R-7).
#
# Deterministic end-to-end assertions for the incident triage and
# collaboration slice, runnable after `make deploy`:
#   1. control check: webhook intake rejects missing/bad bearer tokens
#   2. a simulated Alertmanager payload creates an incident; the same
#      groupKey dedupes (updated, same id) and 'resolved' closes it
#   3. a second incident is visible through the query API exactly as the
#      portal and the incidents.* tools see it (platform caller credential)
#   4. triage leg: operator-initiated triage through the platform-gateway
#      yields a validated report and dispatches it to the audit connector
#   5. the durable trail carries the incident_triaged event
#
# Prerequisites:
#   - kubectl context pointed at the dev cluster
#   - a port-forward for the platform-gateway (triage leg), e.g.:
#       kubectl -n dev-luban-aiops port-forward svc/platform-gateway 18083:8000
#   - a port-forward for the identity broker (triage leg token issuance):
#       kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000
#
# Environment overrides:
#   NAMESPACE          (default dev-luban-aiops)
#   GATEWAY_URL        (default http://localhost:18083)
#   IDENTITY_URL       (default http://localhost:18081)
#   TEST_USER          (default luban-operator)
#   SKIP_TRIAGE_LEG=true to run only the cluster-side assertions.

set -eu

NAMESPACE="${NAMESPACE:-dev-luban-aiops}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:18083}"
IDENTITY_URL="${IDENTITY_URL:-http://localhost:18081}"
TEST_USER="${TEST_USER:-luban-operator}"
RUN_SUFFIX="$(date +%s)-$$"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# Cluster-side HTTP call against incident-service; echoes the body and
# returns the status code in $HTTP_CODE.
incident_http() {
  INCIDENT_BODY=$(kubectl -n "$NAMESPACE" exec deployment/incident-service -- \
    curl -s -o /tmp/incident-body -w "%{http_code}" "$@")
  HTTP_CODE="$INCIDENT_BODY"
  INCIDENT_BODY=$(kubectl -n "$NAMESPACE" exec deployment/incident-service -- \
    cat /tmp/incident-body)
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

echo "==> [1/5] control check: webhook rejects missing and bad tokens"

incident_http -X POST http://localhost:8000/api/v1/webhooks/alertmanager \
  -H "Content-Type: application/json" -d '{"status":"firing"}'
[ "$HTTP_CODE" = "401" ] || fail "webhook without token answered $HTTP_CODE, expected 401"

incident_http -X POST http://localhost:8000/api/v1/webhooks/alertmanager \
  -H "Authorization: Bearer not-the-token" \
  -H "Content-Type: application/json" -d '{"status":"firing"}'
[ "$HTTP_CODE" = "401" ] || fail "webhook with bad token answered $HTTP_CODE, expected 401"
echo "unauthenticated webhook intake rejected (401)"

WEBHOOK_TOKEN=$(kubectl -n "$NAMESPACE" get secret incident-service-runtime-secrets \
  -o jsonpath='{.data.INCIDENT_WEBHOOK_TOKEN}' | base64 -d)
[ -n "$WEBHOOK_TOKEN" ] || fail "INCIDENT_WEBHOOK_TOKEN missing from incident-service-runtime-secrets"

echo "==> [2/5] Alertmanager intake: create, dedupe, resolve"

FIRE_PAYLOAD='{"version":"4","status":"firing","groupKey":"{}:{alertname=DemoPodCrashLooping/'"$RUN_SUFFIX"'}","commonLabels":{"alertname":"DemoPodCrashLooping","severity":"critical","namespace":"dev-luban-aiops","pod":"demo-worker-1"},"commonAnnotations":{"summary":"demo pod crash-looping","description":"Synthetic Alertmanager payload for the SPEC-015 demo."},"alerts":[{"status":"firing","labels":{"alertname":"DemoPodCrashLooping"}}]}'

incident_http -X POST http://localhost:8000/api/v1/webhooks/alertmanager \
  -H "Authorization: Bearer $WEBHOOK_TOKEN" \
  -H "Content-Type: application/json" -d "$FIRE_PAYLOAD"
[ "$HTTP_CODE" = "201" ] || fail "firing webhook answered $HTTP_CODE, expected 201: $INCIDENT_BODY"
ACTION=$(json_field "$INCIDENT_BODY" action)
INCIDENT_A=$(json_field "$INCIDENT_BODY" incident_id)
[ "$ACTION" = "created" ] || fail "first firing intake action was '$ACTION', expected created"
[ -n "$INCIDENT_A" ] || fail "intake response carried no incident_id"
echo "created $INCIDENT_A"

incident_http -X POST http://localhost:8000/api/v1/webhooks/alertmanager \
  -H "Authorization: Bearer $WEBHOOK_TOKEN" \
  -H "Content-Type: application/json" -d "$FIRE_PAYLOAD"
[ "$HTTP_CODE" = "200" ] || fail "duplicate firing webhook answered $HTTP_CODE, expected 200"
DEDUPE_ID=$(json_field "$INCIDENT_BODY" incident_id)
[ "$(json_field "$INCIDENT_BODY" action)" = "updated" ] || fail "duplicate intake did not dedupe"
[ "$DEDUPE_ID" = "$INCIDENT_A" ] || fail "dedupe created a new incident ($DEDUPE_ID != $INCIDENT_A)"
echo "duplicate fingerprint deduped onto $INCIDENT_A"

RESOLVE_PAYLOAD=$(printf '%s' "$FIRE_PAYLOAD" | sed 's/"status":"firing"/"status":"resolved"/g')
incident_http -X POST http://localhost:8000/api/v1/webhooks/alertmanager \
  -H "Authorization: Bearer $WEBHOOK_TOKEN" \
  -H "Content-Type: application/json" -d "$RESOLVE_PAYLOAD"
[ "$HTTP_CODE" = "200" ] || fail "resolution webhook answered $HTTP_CODE, expected 200"
[ "$(json_field "$INCIDENT_BODY" action)" = "resolved" ] || fail "resolution not applied"
[ "$(json_field "$INCIDENT_BODY" incident_id)" = "$INCIDENT_A" ] || fail "resolution hit the wrong incident"
echo "resolution closed $INCIDENT_A"

echo "==> [3/5] query API visibility (platform caller credential)"

QUERY_CLIENTS=$(kubectl -n "$NAMESPACE" get secret incident-service-runtime-secrets \
  -o jsonpath='{.data.INCIDENT_QUERY_CLIENTS}' | base64 -d)
PG_QUERY_SECRET=$(printf '%s' "$QUERY_CLIENTS" | tr ',' '\n' \
  | grep '^platform-gateway=' | cut -d= -f2-)
[ -n "$PG_QUERY_SECRET" ] || fail "platform-gateway entry missing from INCIDENT_QUERY_CLIENTS"

TRIAGE_PAYLOAD='{"version":"4","status":"firing","groupKey":"{}:{alertname=DemoTriage/'"$RUN_SUFFIX"'}","commonLabels":{"alertname":"DemoTriage","severity":"warning","namespace":"dev-luban-aiops","deployment":"demo-api"},"commonAnnotations":{"summary":"demo deployment needs triage","description":"Synthetic incident for the SPEC-015 triage leg."},"alerts":[{"status":"firing","labels":{"alertname":"DemoTriage"}}]}'
incident_http -X POST http://localhost:8000/api/v1/webhooks/alertmanager \
  -H "Authorization: Bearer $WEBHOOK_TOKEN" \
  -H "Content-Type: application/json" -d "$TRIAGE_PAYLOAD"
[ "$HTTP_CODE" = "201" ] || fail "triage-target intake answered $HTTP_CODE: $INCIDENT_BODY"
INCIDENT_B=$(json_field "$INCIDENT_BODY" incident_id)
echo "created $INCIDENT_B for the triage leg"

LIST_RESULT=$(kubectl -n "$NAMESPACE" exec deployment/incident-service -- \
  curl -fsS -u "platform-gateway:${PG_QUERY_SECRET}" \
  "http://localhost:8000/api/v1/incidents?limit=50")
printf '%s' "$LIST_RESULT" | grep -q "\"$INCIDENT_B\"" \
  || fail "incident $INCIDENT_B not visible through the query API"
echo "$INCIDENT_B is visible through the same query surface the portal uses"

if [ "${SKIP_TRIAGE_LEG:-}" = "true" ]; then
  echo "==> [4/5] triage leg skipped (SKIP_TRIAGE_LEG=true)"
  echo "==> [5/5] audit dispatch leg skipped (SKIP_TRIAGE_LEG=true)"
  echo "Incident smoke test passed (intake, dedupe, resolve, visibility)."
  exit 0
fi

echo "==> [4/5] operator-initiated triage through the platform-gateway"

# The gateway verifies broker-issued platform tokens only (issuer
# luban-identity-broker), so the scripted leg asks the identity broker for a
# dev platform token instead of using the raw Keycloak access token.
TOKEN_RESPONSE=$(
  curl -fsS -X POST "$IDENTITY_URL/api/v1/auth/token" \
    -H "Content-Type: application/json" \
    -d "{\"username\": \"$TEST_USER\", \"email\": \"$TEST_USER@luban-aiops.local\", \"roles\": [\"operator\"], \"groups\": [\"ops-operators\"]}"
) || fail "failed to obtain a platform token for $TEST_USER"

ACCESS_TOKEN=$(printf '%s' "$TOKEN_RESPONSE" | python3 -c "
import json, sys
print(json.load(sys.stdin).get('access_token', ''))
")
[ -n "$ACCESS_TOKEN" ] || fail "broker response carried no access_token"

TRIAGE_RESULT=$(curl -fsS --max-time 180 -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  "$GATEWAY_URL/api/v1/incidents/$INCIDENT_B/triage") \
  || fail "triage request through the gateway failed"

TRIAGE_STATUS=$(json_field "$TRIAGE_RESULT" incident.status)
[ "$TRIAGE_STATUS" = "triaged" ] \
  || fail "triage ended with status '$TRIAGE_STATUS', expected triaged"
REPORT_SUMMARY=$(json_field "$TRIAGE_RESULT" report.summary)
[ -n "$REPORT_SUMMARY" ] || fail "triage response carried no report summary"
echo "triage report captured for $INCIDENT_B"

echo "==> [5/5] audit connector dispatch on the durable trail"

printf '%s' "$TRIAGE_RESULT" | grep -q '"connector":"audit"\|"connector": "audit"' \
  || fail "triage response carried no audit connector dispatch"
printf '%s' "$TRIAGE_RESULT" | grep -q '"status":"delivered"\|"status": "delivered"' \
  || fail "audit connector dispatch was not delivered"

AUDIT_CLIENTS=$(kubectl -n "$NAMESPACE" get secret audit-service-runtime-secrets \
  -o jsonpath='{.data.AUDIT_INGEST_CLIENTS}' | base64 -d)
AUDIT_QUERY_SECRET=$(printf '%s' "$AUDIT_CLIENTS" | tr ',' '\n' \
  | grep '^platform-gateway=' | cut -d= -f2-)
AUDIT_EVENTS=$(kubectl -n "$NAMESPACE" exec deployment/audit-service -- \
  curl -fsS -u "platform-gateway:${AUDIT_QUERY_SECRET}" \
  "http://localhost:8000/api/v1/audit/events?event_type=incident_triaged&limit=20")
printf '%s' "$AUDIT_EVENTS" | grep -q "$INCIDENT_B" \
  || fail "no incident_triaged event for $INCIDENT_B on the durable trail"
echo "incident_triaged event for $INCIDENT_B is on the durable trail"

echo ""
echo "Incident smoke test passed:"
echo "  - webhook intake rejects unauthenticated callers"
echo "  - Alertmanager intake creates, dedupes, and resolves incidents"
echo "  - incidents are visible through the portal's query surface"
echo "  - operator triage produced a validated report ($INCIDENT_B)"
echo "  - the audit connector dispatched the report to the durable trail"
