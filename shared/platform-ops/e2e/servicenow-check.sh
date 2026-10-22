#!/bin/sh

# ServiceNow read-tier Table-API ingestion live-check (SPEC-067 R-6).
#
# Deterministic end-to-end assertions for the ServiceNow ingestion surface (the
# six read-tier servicenow.* tools the gateway's native REST connector binds),
# runnable after `make deploy` of the dev-k8s overlay. It mirrors
# ansible-mcp-check.sh: it detects the committed state of
# GATEWAY_SERVICENOW_ENABLED and asserts the corresponding behaviour.
#
#   disabled (committed base default — servicenow_enabled=false in config.py):
#     1. unauthenticated discovery/invoke rejected (401)
#     2. no servicenow.* tool present in discovery
#     3. invoke fails closed with TOOL_NOT_FOUND
#   enabled (opt-in, runtime-profiles/servicenow-dev -> the in-cluster thin mock):
#     1. unauthenticated discovery/invoke rejected (401)
#     2. the six read tools present with risk_level=read; NO write verb and NO
#        deferred capability (problem/attachment) admitted — they are absent from
#        discovery (deny-by-default by absence, R-3)
#     3. fail-closed negatives that need no target contact:
#          - a non-admitted name -> TOOL_NOT_FOUND (allowlist denial)
#          - a missing/invalid required parameter -> INVALID_PARAMETERS
#            (gateway-owned JSON-Schema + sys_id validation, before any HTTP call)
#     4. live reads (GATED on the mock being reachable, proved by an
#        incident.list probe): incident list+get, change_request list+get, user
#        get, cmdb_ci get — each asserting the connector's field projection. The
#        user.get leg additionally asserts the mock's deliberately-returned
#        password/user_password columns are STRIPPED (the projection allowlist is
#        defense-in-depth, not a request hint). When the probe does not answer 200
#        the leg is skipped with a note AND the failure is asserted to be a clean
#        structured fail-closed code — never a hang and never a fabricated success.
#     5. redaction: the mock's client_secret and issued access_token (read from
#        the servicenow-mock-credentials secret) never appear in ANY tool-result
#        body — the connector rides them in an httpx Authorization header, so a
#        leak here would be a regression.
#
# Two run modes, and the difference between them is the whole point of this
# script's parameterisation:
#
#   default (LIVE_TARGET unset/false) — the in-cluster thin mock. Every expected
#     record identifier defaults to the mock's canned value
#     (mock_servicenow_table_api.py): incident INC0010001, change CHG0020001,
#     user mock.operator, CI "Mock DB Cluster". This is what `make e2e` runs.
#     OQ-5 means CI makes no live external call, so a green default run proves
#     registration, fail-closed behaviour, projection and redaction against the
#     mock — never against a real tenant.
#
#   LIVE_TARGET=true — a real ServiceNow instance in read-only mode. The canned
#     defaults cannot exist on a real tenant, so this mode REFUSES TO RUN unless
#     every expected identifier and sys_id is overridden explicitly. That
#     requirement is deliberate: a mock-bound assertion reported as a live pass
#     is worse than no live pass at all, because it is indistinguishable from
#     one. This mode implies STRICT_LIVE=true (a skipped live leg on a live run
#     is a failed run, never a note).
#
# Prerequisites:
#   - kubectl context pointed at the dev cluster
#   - a port-forward for the identity broker (token issuance):
#       kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000
#
# Environment overrides:
#   NAMESPACE     (default dev-luban-aiops)
#   IDENTITY_URL  (default http://localhost:18081)
#   TEST_USER     (default luban-operator)
#   STRICT_LIVE   (default false) set true for an operator run to turn the gated
#                 live leg from skip-with-a-note into a hard failure when the
#                 target is not reachable/credentialed. Implied by LIVE_TARGET.
#   LIVE_TARGET   (default false) set true only when the gateway's ServiceNow
#                 binding points at a real tenant. Requires every EXPECT_* and
#                 SERVICENOW_*_SYS_ID knob below plus REDACTION_SECRETS_FILE to
#                 be set explicitly.
#
# Expected-record knobs (defaults are the mock's; all REQUIRED under
# LIVE_TARGET=true). The four EXPECT_* values are what the projection assertions
# compare against; the four sys_ids are what the get reads resolve:
#   EXPECT_INCIDENT_NUMBER   (default INC0010001)
#   EXPECT_CHANGE_NUMBER     (default CHG0020001)
#   EXPECT_USER_NAME         (default mock.operator)
#   EXPECT_CI_NAME           (default Mock DB Cluster)
#   SERVICENOW_INCIDENT_SYS_ID  (default a1a1...a1a1, the mock's incident)
#   SERVICENOW_CHANGE_SYS_ID    (default c3c3...c3c3, the mock's change)
#   SERVICENOW_USER_SYS_ID      (default d4d4...d4d4, the mock's user)
#   SERVICENOW_CI_SYS_ID        (default e5e5...e5e5, the mock's CI)
#   REDACTION_SECRETS_FILE   (default unset) a file of credential literals — one
#                 per line, blanks and '#' comments ignored — that must not
#                 appear in any tool-result body. Under LIVE_TARGET=true this is
#                 how the redaction leg stays meaningful, since the in-cluster
#                 mock's secret does not exist on a live run. Values are only
#                 ever tested for, never echoed.
#
# Example (a live read-only run against a real instance):
#   LIVE_TARGET=true \
#   SERVICENOW_INCIDENT_SYS_ID=<32-hex> SERVICENOW_CHANGE_SYS_ID=<32-hex> \
#   SERVICENOW_USER_SYS_ID=<32-hex> SERVICENOW_CI_SYS_ID=<32-hex> \
#   EXPECT_INCIDENT_NUMBER=INC0001234 EXPECT_CHANGE_NUMBER=CHG0005678 \
#   EXPECT_USER_NAME=<integration user> EXPECT_CI_NAME='<a real CI name>' \
#   REDACTION_SECRETS_FILE=/tmp/snow-secrets.txt \
#     sh shared/platform-ops/e2e/servicenow-check.sh

set -eu

# Record which knobs the caller set EXPLICITLY, before any default is applied
# below. The defaults are the in-cluster mock's canned values, so a knob still
# holding its default cannot be evidence about a real tenant — and LIVE_TARGET
# needs to tell those two cases apart (see require_explicit).
EXPLICITLY_SET=" "
for _knob in SERVICENOW_INCIDENT_SYS_ID SERVICENOW_CHANGE_SYS_ID \
  SERVICENOW_USER_SYS_ID SERVICENOW_CI_SYS_ID EXPECT_INCIDENT_NUMBER \
  EXPECT_CHANGE_NUMBER EXPECT_USER_NAME EXPECT_CI_NAME REDACTION_SECRETS_FILE; do
  if eval "[ -n \"\${${_knob}+x}\" ]"; then
    EXPLICITLY_SET="${EXPLICITLY_SET}${_knob} "
  fi
done

NAMESPACE="${NAMESPACE:-dev-luban-aiops}"
IDENTITY_URL="${IDENTITY_URL:-http://localhost:18081}"
TEST_USER="${TEST_USER:-luban-operator}"
STRICT_LIVE="${STRICT_LIVE:-false}"
LIVE_TARGET="${LIVE_TARGET:-false}"
REDACTION_SECRETS_FILE="${REDACTION_SECRETS_FILE:-}"
RUN_SUFFIX="$(date +%s)-$$"

# Names the binding never admits: a write verb (no mutation exists) and a deferred
# capability (problem/attachment, OQ-4). Invoking either must fail closed with
# TOOL_NOT_FOUND even when enabled — deny-by-default by absence (R-3).
DENIED_WRITE="servicenow.incident.update"
DENIED_DEFERRED="servicenow.problem.get"
# The six admitted read-tier canonical names (ingestion/servicenow_binding.py).
READ_TOOLS="servicenow.incident.list servicenow.incident.get servicenow.change_request.list servicenow.change_request.get servicenow.user.get servicenow.cmdb_ci.get"
# Expected record identifiers, defaulted to mock_servicenow_table_api.py's canned
# rows. Exported so the python3 assertions read them from the environment rather
# than from interpolated source: a value carrying a quote or a backslash then
# cannot change what the assertion means.
EXPECT_INCIDENT_NUMBER="${EXPECT_INCIDENT_NUMBER:-INC0010001}"
EXPECT_CHANGE_NUMBER="${EXPECT_CHANGE_NUMBER:-CHG0020001}"
EXPECT_USER_NAME="${EXPECT_USER_NAME:-mock.operator}"
EXPECT_CI_NAME="${EXPECT_CI_NAME:-Mock DB Cluster}"
export EXPECT_INCIDENT_NUMBER EXPECT_CHANGE_NUMBER EXPECT_USER_NAME EXPECT_CI_NAME
# The sys_ids the four get reads resolve: mock canned defaults, operator-supplied
# (32-hex, from the real tenant) under LIVE_TARGET=true.
INCIDENT_SYS_ID="${SERVICENOW_INCIDENT_SYS_ID:-a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1}"
CHANGE_SYS_ID="${SERVICENOW_CHANGE_SYS_ID:-c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3}"
USER_SYS_ID="${SERVICENOW_USER_SYS_ID:-d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4}"
CI_SYS_ID="${SERVICENOW_CI_SYS_ID:-e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5}"
# The structured codes the connector can return WITHOUT a good target answer
# (ingestion/servicenow_native.py + the SPEC-068 credential seam). Anything else
# means the probe failed in a way this check does not understand, which must never
# be waved through as "unreachable". CREDENTIAL_SCHEME_UNSUPPORTED is deliberately
# absent: only the MCP adapter emits it, and this connector resolves through
# tools/auth_resolution.py, whose unsupported-scheme branch returns
# CREDENTIAL_ACQUISITION_FAILED. Listing an unreachable code here would only
# widen what this guard waves through.
FAIL_CLOSED_CODES='SERVICENOW_NOT_CONFIGURED|SERVICENOW_INVALID_BASE_URL|SERVICENOW_TIMEOUT|SERVICENOW_UNREACHABLE|SERVICENOW_UPSTREAM_ERROR|SERVICENOW_RESPONSE_INVALID|CREDENTIAL_SET_NOT_FOUND|CREDENTIAL_ACQUISITION_FAILED'

# Collects every enabled-state tool-result body for the redaction assertion, plus
# every credential literal that assertion tests for. Neither is ever echoed.
RESPONSES=$(mktemp)
REDACTION_LITERALS=$(mktemp)
trap 'rm -f "$RESPONSES" "$REDACTION_LITERALS"' EXIT

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# LIVE_TARGET=true claims "the assertions below are about a real tenant", so every
# knob whose default is a mock canned value must have been overridden explicitly.
# Without this the mode would assert INC0010001 / mock.operator against a live
# instance and fail in a way indistinguishable from a genuine projection
# regression — or, worse, invite someone to weaken the assertion to make it pass.
# Refusing to run is the only outcome that cannot be mistaken for evidence.
require_explicit() {
  case "$EXPLICITLY_SET" in
    *" $1 "*) return 0 ;;
  esac
  fail "LIVE_TARGET=true requires $1 to be set explicitly: its default is the in-cluster mock's canned value, which cannot exist on a real tenant"
}

if [ "$LIVE_TARGET" = "true" ]; then
  TARGET_LABEL="live tenant"
  # A live run exists to prove the live leg, so a skipped leg is a failed run and
  # never a note. Implied here so the two knobs cannot disagree.
  STRICT_LIVE=true
  for _knob in SERVICENOW_INCIDENT_SYS_ID SERVICENOW_CHANGE_SYS_ID \
    SERVICENOW_USER_SYS_ID SERVICENOW_CI_SYS_ID EXPECT_INCIDENT_NUMBER \
    EXPECT_CHANGE_NUMBER EXPECT_USER_NAME EXPECT_CI_NAME REDACTION_SECRETS_FILE; do
    require_explicit "$_knob"
  done
  # An explicitly-set-but-empty value passes require_explicit, so test the file
  # too: on a live run the mock's secret does not exist, and this file is the only
  # thing keeping the [6/6] redaction leg from passing vacuously. Refuse here
  # rather than letting the run proceed and fail five legs later.
  [ -r "$REDACTION_SECRETS_FILE" ] \
    || fail "REDACTION_SECRETS_FILE is not readable: $REDACTION_SECRETS_FILE"
  [ -s "$REDACTION_SECRETS_FILE" ] \
    || fail "LIVE_TARGET=true requires a non-empty REDACTION_SECRETS_FILE: $REDACTION_SECRETS_FILE"
  # grep -v exits 0 when at least one line is neither blank nor a comment, i.e.
  # when the file really does carry a literal to test for.
  grep -qvE '^[[:space:]]*(#|$)' "$REDACTION_SECRETS_FILE" \
    || fail "REDACTION_SECRETS_FILE carries no credential literal (only blanks/comments): $REDACTION_SECRETS_FILE"
  echo "LIVE_TARGET=true: asserting against a live ServiceNow tenant, not the in-cluster mock."
else
  TARGET_LABEL="in-cluster mock"
fi

# Cluster-side HTTP call; sets HTTP_CODE and GATEWAY_BODY without printing.
gateway_http() {
  HTTP_CODE=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -c tool-gateway -- \
    curl -sS -o /tmp/gateway-body -w "%{http_code}" "$@") \
    || fail "in-cluster gateway call did not complete"
  GATEWAY_BODY=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -c tool-gateway -- \
    cat /tmp/gateway-body)
}

# Invoke a servicenow.* tool as the operator; records the body for redaction.
invoke() {
  # $1 = tool_name, $2 = parameters JSON, $3 = request tag
  gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
    -H "Authorization: Bearer $OPERATOR_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"$1\",\"parameters\":$2,\"request_id\":\"servicenow-check-$3-$RUN_SUFFIX\"}"
  printf '%s\n' "$GATEWAY_BODY" >> "$RESPONSES"
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

# The native REST connector returns its payload as structured `data` (a list read
# is {table,count,records}; a get read is {table,record}) — no MCP data.text
# wrapping. Emit `data` (or {}) as JSON so assertions read the real structure.
snow_data() {
  printf '%s' "$1" | python3 -c "
import json, sys
body = json.load(sys.stdin)
data = body.get('data') if isinstance(body, dict) else None
print(json.dumps(data if data is not None else {}))"
}

echo "==> [1/6] control check: tool-gateway rejects unauthenticated callers"

gateway_http http://localhost:8000/api/v2/tools
[ "$HTTP_CODE" = "401" ] || fail "discovery without token answered $HTTP_CODE, expected 401"

gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"servicenow.incident.list","parameters":{},"request_id":"servicenow-check-unauth"}'
[ "$HTTP_CODE" = "401" ] || fail "invoke without token answered $HTTP_CODE, expected 401"
echo "unauthenticated discovery and invoke rejected (401)"

echo "==> [2/6] delegated token for the operator"

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

SERVICENOW_ENABLED=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o jsonpath='{.data.GATEWAY_SERVICENOW_ENABLED}')
[ -n "$SERVICENOW_ENABLED" ] || SERVICENOW_ENABLED=false
echo "GATEWAY_SERVICENOW_ENABLED=$SERVICENOW_ENABLED"

DISCOVERY=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -c tool-gateway -- \
  curl -fsS -H "Authorization: Bearer $OPERATOR_TOKEN" \
  http://localhost:8000/api/v2/tools)

if [ "$SERVICENOW_ENABLED" != "true" ]; then
  echo "==> [3/6] deny-by-default: no servicenow.* tool in discovery"

  printf '%s' "$DISCOVERY" | python3 -c "
import json, sys
names = {t['name'] for t in json.load(sys.stdin)}
leaked = sorted(n for n in names if n.startswith('servicenow.'))
assert not leaked, 'servicenow.* registered while disabled: %r' % leaked" \
    || fail "a servicenow.* tool is registered despite GATEWAY_SERVICENOW_ENABLED=$SERVICENOW_ENABLED"
  echo "no servicenow.* tool registered (connector gated off)"

  echo "==> [4/6] deny-by-default: invoke fails closed"

  gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
    -H "Authorization: Bearer $OPERATOR_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"servicenow.incident.list\",\"parameters\":{},\"request_id\":\"servicenow-check-disabled-$RUN_SUFFIX\"}"
  [ "$HTTP_CODE" = "400" ] || fail "invoke answered $HTTP_CODE, expected 400"
  printf '%s' "$GATEWAY_BODY" | grep -q 'TOOL_NOT_FOUND' \
    || fail "invoke did not fail with TOOL_NOT_FOUND: $GATEWAY_BODY"
  echo "operator invoke of servicenow.incident.list rejected with TOOL_NOT_FOUND"

  # STRICT_LIVE means "prove the live read leg", which the deny-by-default
  # overlay structurally cannot: fail rather than report a vacuous pass.
  [ "$STRICT_LIVE" != "true" ] \
    || fail "STRICT_LIVE=true but GATEWAY_SERVICENOW_ENABLED=$SERVICENOW_ENABLED; the connector is gated off, so enable a binding first (the servicenow-dev profile for the mock, or a live one for LIVE_TARGET=true)"

  echo ""
  echo "ServiceNow ingestion live-check passed (deny-by-default):"
  echo "  - unauthenticated callers rejected (401)"
  echo "  - no servicenow.* tool in discovery"
  echo "  - invoke fails closed with TOOL_NOT_FOUND"
  exit 0
fi

echo "==> [3/6] opt-in: the six read tools present (read tier); no write/deferred verb admitted"

printf '%s' "$DISCOVERY" | python3 -c "
import json, sys
expected = set(sys.argv[1].split())
denied = sys.argv[2:]
tools = {t['name']: t for t in json.load(sys.stdin)}
missing = sorted(expected - set(tools))
assert not missing, 'admitted read tools missing from discovery: %r' % missing
for name in expected:
    rl = tools[name].get('risk_level')
    assert rl == 'read', '%s risk_level is %r, expected read' % (name, rl)
snow_names = {n for n in tools if n.startswith('servicenow.')}
extra = sorted(snow_names - expected)
assert not extra, 'unexpected servicenow.* tool admitted: %r' % extra
for d in denied:
    assert d not in tools, 'non-admitted verb %r is admitted' % d" \
  "$READ_TOOLS" "$DENIED_WRITE" "$DENIED_DEFERRED" \
  || fail "discovery does not carry exactly the six read-tier servicenow.* tools"
echo "six servicenow.* read tools registered (risk_level=read); no write/deferred verb admitted"

echo "==> [4/6] fail-closed negatives (no target contact)"

# (a) a non-admitted name (write verb + deferred capability) is denied by absence.
invoke "$DENIED_WRITE" '{}' denied-write
[ "$HTTP_CODE" = "400" ] || fail "write-verb invoke answered $HTTP_CODE, expected 400"
printf '%s' "$GATEWAY_BODY" | grep -q 'TOOL_NOT_FOUND' \
  || fail "write verb did not fail with TOOL_NOT_FOUND: $GATEWAY_BODY"
echo "non-admitted write verb ($DENIED_WRITE) rejected with TOOL_NOT_FOUND"

invoke "$DENIED_DEFERRED" '{}' denied-deferred
[ "$HTTP_CODE" = "400" ] || fail "deferred-capability invoke answered $HTTP_CODE, expected 400"
printf '%s' "$GATEWAY_BODY" | grep -q 'TOOL_NOT_FOUND' \
  || fail "deferred capability did not fail with TOOL_NOT_FOUND: $GATEWAY_BODY"
echo "deferred capability ($DENIED_DEFERRED) rejected with TOOL_NOT_FOUND"

# (b) a get with a missing/invalid sys_id is caught by the gateway-owned schema +
#     sys_id validation before any HTTP call (proves validation is gateway-side).
invoke servicenow.incident.get '{}' missing-param
[ "$HTTP_CODE" = "400" ] || fail "missing-param invoke answered $HTTP_CODE, expected 400"
printf '%s' "$GATEWAY_BODY" | grep -q 'INVALID_PARAMETERS' \
  || fail "missing sys_id did not fail with INVALID_PARAMETERS: $GATEWAY_BODY"
echo "servicenow.incident.get with no sys_id rejected with INVALID_PARAMETERS"

invoke servicenow.incident.get '{"sys_id":"not-a-sys-id"}' bad-param
[ "$HTTP_CODE" = "400" ] || fail "bad-param invoke answered $HTTP_CODE, expected 400"
printf '%s' "$GATEWAY_BODY" | grep -q 'INVALID_PARAMETERS' \
  || fail "malformed sys_id did not fail with INVALID_PARAMETERS: $GATEWAY_BODY"
echo "servicenow.incident.get with a malformed sys_id rejected with INVALID_PARAMETERS"

echo "==> [5/6] live reads against the $TARGET_LABEL (gated on reachability)"

invoke servicenow.incident.list '{}' probe
LIVE_OK=false
if [ "$HTTP_CODE" = "200" ]; then
  LIVE_OK=true
  echo "incident.list probe answered 200 ($TARGET_LABEL reachable and credentialed)"
else
  # Not reachable / not credentialed: assert a CLEAN fail-closed structured error
  # (never a hang, never a fabricated success), then skip the live reads.
  printf '%s' "$GATEWAY_BODY" | grep -qE "$FAIL_CLOSED_CODES" \
    || fail "incident.list probe failed with an unexpected (non-fail-closed) body: $GATEWAY_BODY"
  CODE=$(json_field "$GATEWAY_BODY" error.code)
  if [ "$STRICT_LIVE" = "true" ]; then
    fail "STRICT_LIVE=true but the $TARGET_LABEL was not reachable/credentialed (fail-closed: ${CODE:-unknown}); the live read leg must not be skipped"
  fi
  # Only reachable on the mock path — LIVE_TARGET=true implies STRICT_LIVE=true and
  # so fails above — which is why this remediation advice is mock-shaped.
  echo "NOTE: the $TARGET_LABEL is not reachable/credentialed (fail-closed: ${CODE:-unknown})."
  echo "      Deploy the servicenow-dev profile (make deploy) and run"
  echo "      sync-servicenow-credentials.sh to exercise the live read leg, then"
  echo "      re-run with STRICT_LIVE=true. The registration and fail-closed"
  echo "      negatives above already hold."
fi

if [ "$LIVE_OK" = "true" ]; then
  snow_data "$GATEWAY_BODY" | python3 -c "
import json, os, sys
d = json.load(sys.stdin)
want = os.environ['EXPECT_INCIDENT_NUMBER']
numbers = {r.get('number') for r in d.get('records', [])}
assert want in numbers, 'incident %s absent: %r' % (want, numbers)
assert d.get('count', 0) >= 1, 'incident count is %r' % d.get('count')" \
    || fail "incident.list did not project $EXPECT_INCIDENT_NUMBER"
  echo "servicenow.incident.list projected $EXPECT_INCIDENT_NUMBER"

  invoke servicenow.incident.get "{\"sys_id\":\"$INCIDENT_SYS_ID\"}" incident-get
  [ "$HTTP_CODE" = "200" ] || fail "incident.get answered $HTTP_CODE: $GATEWAY_BODY"
  snow_data "$GATEWAY_BODY" | python3 -c "
import json, os, sys
r = json.load(sys.stdin).get('record', {})
want = os.environ['EXPECT_INCIDENT_NUMBER']
assert r.get('number') == want, 'incident.get returned %r, expected %r' % (r.get('number'), want)" \
    || fail "incident.get did not project $EXPECT_INCIDENT_NUMBER"
  echo "servicenow.incident.get projected $EXPECT_INCIDENT_NUMBER"

  invoke servicenow.change_request.list '{}' change-list
  [ "$HTTP_CODE" = "200" ] || fail "change_request.list answered $HTTP_CODE: $GATEWAY_BODY"
  snow_data "$GATEWAY_BODY" | python3 -c "
import json, os, sys
d = json.load(sys.stdin)
want = os.environ['EXPECT_CHANGE_NUMBER']
numbers = {r.get('number') for r in d.get('records', [])}
assert want in numbers, 'change %s absent: %r' % (want, numbers)" \
    || fail "change_request.list did not project $EXPECT_CHANGE_NUMBER"
  echo "servicenow.change_request.list projected $EXPECT_CHANGE_NUMBER"

  invoke servicenow.change_request.get "{\"sys_id\":\"$CHANGE_SYS_ID\"}" change-get
  [ "$HTTP_CODE" = "200" ] || fail "change_request.get answered $HTTP_CODE: $GATEWAY_BODY"
  snow_data "$GATEWAY_BODY" | python3 -c "
import json, os, sys
r = json.load(sys.stdin).get('record', {})
want = os.environ['EXPECT_CHANGE_NUMBER']
assert r.get('number') == want, 'change_request.get returned %r, expected %r' % (r.get('number'), want)" \
    || fail "change_request.get did not project $EXPECT_CHANGE_NUMBER"
  echo "servicenow.change_request.get projected $EXPECT_CHANGE_NUMBER"

  invoke servicenow.user.get "{\"sys_id\":\"$USER_SYS_ID\"}" user-get
  [ "$HTTP_CODE" = "200" ] || fail "user.get answered $HTTP_CODE: $GATEWAY_BODY"
  # The credential-column half of this assertion is target-independent and stays
  # unconditional: whatever the tenant, password/user_password must not survive the
  # gateway-owned projection allowlist. On the mock the row deliberately carries
  # both columns, so it is the only target that can actually catch a regression.
  snow_data "$GATEWAY_BODY" | python3 -c "
import json, os, sys
r = json.load(sys.stdin).get('record', {})
want = os.environ['EXPECT_USER_NAME']
assert r.get('user_name') == want, 'user.get returned %r, expected %r' % (r.get('user_name'), want)
leaked = sorted(k for k in ('password', 'user_password') if k in r)
assert not leaked, 'credential column survived projection: %r' % leaked" \
    || fail "user.get did not project $EXPECT_USER_NAME OR leaked a credential column"
  echo "servicenow.user.get projected $EXPECT_USER_NAME; password/user_password stripped by projection"

  invoke servicenow.cmdb_ci.get "{\"sys_id\":\"$CI_SYS_ID\"}" ci-get
  [ "$HTTP_CODE" = "200" ] || fail "cmdb_ci.get answered $HTTP_CODE: $GATEWAY_BODY"
  snow_data "$GATEWAY_BODY" | python3 -c "
import json, os, sys
r = json.load(sys.stdin).get('record', {})
want = os.environ['EXPECT_CI_NAME']
assert r.get('name') == want, 'cmdb_ci.get returned %r, expected %r' % (r.get('name'), want)" \
    || fail "cmdb_ci.get did not project $EXPECT_CI_NAME"
  echo "servicenow.cmdb_ci.get projected '$EXPECT_CI_NAME'"
fi

echo "==> [6/6] redaction: no credential ever appears in a tool result"

# Two literal sources, collected into one file and tested in a single pass. Which
# one applies depends on the target: the in-cluster mock's credential secret on a
# default run, REDACTION_SECRETS_FILE on a live run (where that secret does not
# exist, so without the file this leg would have nothing to test and would pass
# vacuously — hence LIVE_TARGET=true requires it).

# Source 1: the mock's credentials, read WITHOUT swallowing errors (mirrors the
# hardened ansible-mcp-check.sh leg): a renamed key, an RBAC failure, or a base64
# failure must fail loudly rather than collapse into a reassuring no-op. Skipped
# under LIVE_TARGET=true, where the secret legitimately does not exist.
if [ "$LIVE_TARGET" != "true" ] && \
   kubectl -n "$NAMESPACE" get secret servicenow-mock-credentials >/dev/null 2>&1; then
  for key in client-secret access-token; do
    ENCODED=$(kubectl -n "$NAMESPACE" get secret servicenow-mock-credentials \
      -o jsonpath="{.data.$key}") \
      || fail "servicenow-mock-credentials exists but $key could not be read (renamed? RBAC?)"
    [ -n "$ENCODED" ] \
      || fail "servicenow-mock-credentials carries no $key key (sync-servicenow-credentials.sh sink 2)"
    DECODED=$(printf '%s' "$ENCODED" | base64 -d) \
      || fail "servicenow-mock-credentials $key is not valid base64"
    printf '%s\n' "$DECODED" >> "$REDACTION_LITERALS"
  done
  echo "loaded the mock's client-secret and access-token as redaction literals"
fi

# Source 2: operator-supplied literals — one per line, blanks and '#' comments
# ignored. Readability was already checked when LIVE_TARGET=true demanded the
# file; re-check here because a default run may set it too.
if [ -n "$REDACTION_SECRETS_FILE" ]; then
  [ -r "$REDACTION_SECRETS_FILE" ] \
    || fail "REDACTION_SECRETS_FILE is not readable: $REDACTION_SECRETS_FILE"
  # `|| true`: a file of only comments makes grep exit 1, which is not an error —
  # the count check below is what rejects an empty literal set.
  grep -vE '^[[:space:]]*(#|$)' "$REDACTION_SECRETS_FILE" >> "$REDACTION_LITERALS" || true
  echo "loaded redaction literals from REDACTION_SECRETS_FILE"
fi

if [ ! -s "$REDACTION_LITERALS" ]; then
  # Legitimate only when the connector never reached a credentialed target:
  # LIVE_OK=true requires a 200 probe, which requires BOTH a resolved credential
  # set and an access_token the target accepted — so a successful live read with
  # no literal to test is provably a defect, not a trivially-satisfied check.
  [ "$LIVE_OK" != "true" ] \
    || fail "live reads succeeded but no credential literal could be loaded; the two-sink credential invariant is unverifiable"
  echo "NOTE: no credential literal is available for the $TARGET_LABEL, so the"
  echo "      connector had nothing to leak and redaction is trivially satisfied"
  echo "      (and reads fail closed above)."
else
  # A non-empty capture file is what makes the loop below meaningful: without it
  # "no literal appears in any response" would hold because there were no
  # responses at all.
  [ -s "$RESPONSES" ] \
    || fail "no tool-result body was captured; the redaction assertion would pass vacuously"
  LITERAL_COUNT=0
  # -F fixed-string, -q quiet: a literal is never echoed, only tested for. The
  # `|| [ -n "$LITERAL" ]` keeps a final line that carries no trailing newline.
  while IFS= read -r LITERAL || [ -n "$LITERAL" ]; do
    [ -n "$LITERAL" ] || continue
    LITERAL_COUNT=$((LITERAL_COUNT + 1))
    if grep -qF "$LITERAL" "$RESPONSES"; then
      fail "credential literal $LITERAL_COUNT of the redaction set leaked into a tool-result body"
    fi
  done < "$REDACTION_LITERALS"
  [ "$LITERAL_COUNT" -ge 1 ] \
    || fail "the redaction set carried no usable literal; the assertion would pass vacuously"
  echo "no credential literal ($LITERAL_COUNT tested) appears in any tool-result body (they ride the httpx header only)"
fi

echo ""
echo "ServiceNow ingestion live-check passed (opt-in, target: $TARGET_LABEL):"
echo "  - unauthenticated callers rejected (401)"
echo "  - six servicenow.* read tools registered read; no write/deferred verb admitted"
echo "  - a non-admitted name and a missing/malformed sys_id fail closed (no target contact)"
if [ "$LIVE_OK" = "true" ]; then
  echo "  - live reads projected $EXPECT_INCIDENT_NUMBER, $EXPECT_CHANGE_NUMBER,"
  echo "    $EXPECT_USER_NAME (password/user_password stripped) and '$EXPECT_CI_NAME'"
else
  echo "  - live reads SKIPPED (target not reachable/credentialed, fail-closed above);"
  echo "    re-run with STRICT_LIVE=true after deploying the servicenow-dev profile"
fi
echo "  - no credential literal appears in any tool result"
