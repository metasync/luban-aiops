#!/bin/sh

# Ansible read-tier MCP-ingestion live-check (SPEC-069 R-6).
#
# Deterministic end-to-end assertions for the Ansible MCP-ingestion surface
# (the six read-tier ansible.* tools the gateway's server-agnostic connector
# binds), runnable after `make deploy` of the dev-k8s overlay. It mirrors
# http-check-demo.sh: it detects the committed state of
# GATEWAY_ANSIBLE_MCP_ENABLED and asserts the corresponding behaviour.
#
#   disabled (committed base default):
#     1. unauthenticated discovery/invoke rejected (401)
#     2. no ansible.* tool present in discovery
#     3. invoke fails closed with TOOL_NOT_FOUND
#   enabled (opt-in, runtime-profiles/ansible-dev -> the in-cluster thin mock):
#     1. unauthenticated discovery/invoke rejected (401)
#     2. the six read tools present with risk_level=read; NO mutating verb
#        admitted (a launch/update name is absent from discovery)
#     3. fail-closed negatives that need no server contact:
#          - a non-admitted mutating verb -> TOOL_NOT_FOUND (allowlist denial)
#          - a missing required parameter -> INVALID_PARAMETERS (gateway-owned
#            JSON-Schema validation, before any MCP session opens)
#     4. live reads (GATED on the mock being reachable, proved by an
#        ansible.get_environment_health probe): inventory list, the demo
#        inventory's mock managed hosts, job templates, one job, and its
#        tail-bounded stdout. When the probe does not answer 200 the leg is
#        skipped with a note AND the failure is asserted to be a clean
#        structured fail-closed code — never a hang and never a fabricated
#        success. The accepted codes are exactly the ones the connector can
#        return WITHOUT a server answer: MCP_TRANSPORT_ERROR,
#        MCP_SDK_UNAVAILABLE, CREDENTIAL_SET_NOT_FOUND and
#        CREDENTIAL_SCHEME_UNSUPPORTED. This is the deployed counterpart to the
#        in-process Layer-2 wire test
#        (products/tool-gateway/tests/test_ansible_mcp_streamable_http.py).
#     5. redaction: the mock bearer (read from the ansible-mock-credentials
#        secret) never appears in ANY tool-result body — the connector rides it
#        in an httpx header, so a leak here would be a regression.
#
# The canned topology asserted in the live leg is the thin mock's
# (mock_ansible_mcp_server.py): inventories demo/prod, demo's hosts
# mock-host-01/mock-host-02, job template "Deploy App", job 1 successful. This
# check targets the in-cluster mock; validating a real licensed AAP in
# read-only mode is the separate operator runbook step (docs/guides), outside CI
# (OQ-5: CI makes no live external call).
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
#   STRICT_LIVE   (default false) set true for an operator run to turn the
#                 gated live leg from skip-with-a-note into a hard failure when
#                 the mock target is not reachable/credentialed. `make e2e`
#                 leaves it false: OQ-5 means CI must pass without a live
#                 external call, so a green `make e2e` proves registration,
#                 fail-closed behaviour and redaction — never the projection
#                 logic against a real server (that coverage is the Layer-2
#                 wire test). Run STRICT_LIVE=true after `make deploy` of the
#                 ansible-dev profile to close the gap.

set -eu

NAMESPACE="${NAMESPACE:-dev-luban-aiops}"
IDENTITY_URL="${IDENTITY_URL:-http://localhost:18081}"
TEST_USER="${TEST_USER:-luban-operator}"
STRICT_LIVE="${STRICT_LIVE:-false}"
RUN_SUFFIX="$(date +%s)-$$"

# A mutating verb the binding never admits (DENIED_SERVER_TOOLS has no canonical
# name); invoking it must fail closed with TOOL_NOT_FOUND even when enabled.
DENIED_TOOL="ansible.launch_job_template"
# The six admitted read-tier canonical names (ingestion/ansible_binding.py).
READ_TOOLS="ansible.list_inventories ansible.get_inventory ansible.list_job_templates ansible.get_job ansible.get_job_stdout ansible.get_environment_health"
# The structured codes the MCP connector can return WITHOUT the server answering
# (ingestion/mcp_adapter.py: transport, SDK-import, credential-set and
# credential-scheme failures). Anything else means the probe failed in a way this
# check does not understand, which must never be waved through as "unreachable".
FAIL_CLOSED_CODES='MCP_TRANSPORT_ERROR|MCP_SDK_UNAVAILABLE|CREDENTIAL_SET_NOT_FOUND|CREDENTIAL_SCHEME_UNSUPPORTED'

# Collects every enabled-state tool-result body for the redaction assertion.
RESPONSES=$(mktemp)
trap 'rm -f "$RESPONSES"' EXIT

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

# Invoke an ansible.* tool as the operator; records the body for redaction.
invoke() {
  # $1 = tool_name, $2 = parameters JSON, $3 = request tag
  gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
    -H "Authorization: Bearer $OPERATOR_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"$1\",\"parameters\":$2,\"request_id\":\"ansible-check-$3-$RUN_SUFFIX\"}"
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

# Normalize a tool result's payload: the MCP connector returns the server's JSON
# as data.text (a string); parse it so assertions read the real structure. Falls
# back to data unchanged if a future SDK populates structured_content directly.
mcp_payload() {
  printf '%s' "$1" | python3 -c "
import json, sys
body = json.load(sys.stdin)
data = body.get('data') if isinstance(body, dict) else None
if isinstance(data, dict) and isinstance(data.get('text'), str):
    try:
        data = json.loads(data['text'])
    except ValueError:
        pass
print(json.dumps(data if data is not None else {}))"
}

echo "==> [1/6] control check: tool-gateway rejects unauthenticated callers"

gateway_http http://localhost:8000/api/v2/tools
[ "$HTTP_CODE" = "401" ] || fail "discovery without token answered $HTTP_CODE, expected 401"

gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"ansible.list_inventories","parameters":{},"request_id":"ansible-check-unauth"}'
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

ANSIBLE_ENABLED=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o jsonpath='{.data.GATEWAY_ANSIBLE_MCP_ENABLED}')
[ -n "$ANSIBLE_ENABLED" ] || ANSIBLE_ENABLED=false
echo "GATEWAY_ANSIBLE_MCP_ENABLED=$ANSIBLE_ENABLED"

DISCOVERY=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -c tool-gateway -- \
  curl -fsS -H "Authorization: Bearer $OPERATOR_TOKEN" \
  http://localhost:8000/api/v2/tools)

if [ "$ANSIBLE_ENABLED" != "true" ]; then
  echo "==> [3/6] deny-by-default: no ansible.* tool in discovery"

  printf '%s' "$DISCOVERY" | python3 -c "
import json, sys
names = {t['name'] for t in json.load(sys.stdin)}
leaked = sorted(n for n in names if n.startswith('ansible.'))
assert not leaked, 'ansible.* registered while disabled: %r' % leaked" \
    || fail "an ansible.* tool is registered despite GATEWAY_ANSIBLE_MCP_ENABLED=$ANSIBLE_ENABLED"
  echo "no ansible.* tool registered (connector gated off)"

  echo "==> [4/6] deny-by-default: invoke fails closed"

  gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
    -H "Authorization: Bearer $OPERATOR_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"ansible.list_inventories\",\"parameters\":{},\"request_id\":\"ansible-check-disabled-$RUN_SUFFIX\"}"
  [ "$HTTP_CODE" = "400" ] || fail "invoke answered $HTTP_CODE, expected 400"
  printf '%s' "$GATEWAY_BODY" | grep -q 'TOOL_NOT_FOUND' \
    || fail "invoke did not fail with TOOL_NOT_FOUND: $GATEWAY_BODY"
  echo "operator invoke of ansible.list_inventories rejected with TOOL_NOT_FOUND"

  # STRICT_LIVE means "prove the live read leg", which the deny-by-default
  # overlay structurally cannot: fail rather than report a vacuous pass.
  [ "$STRICT_LIVE" != "true" ] \
    || fail "STRICT_LIVE=true but GATEWAY_ANSIBLE_MCP_ENABLED=$ANSIBLE_ENABLED; deploy the ansible-dev profile first"

  echo ""
  echo "Ansible MCP-ingestion live-check passed (deny-by-default):"
  echo "  - unauthenticated callers rejected (401)"
  echo "  - no ansible.* tool in discovery"
  echo "  - invoke fails closed with TOOL_NOT_FOUND"
  exit 0
fi

echo "==> [3/6] opt-in: the six read tools present (read tier); no mutating verb admitted"

printf '%s' "$DISCOVERY" | python3 -c "
import json, sys
expected = set(sys.argv[1].split())
denied = sys.argv[2]
tools = {t['name']: t for t in json.load(sys.stdin)}
missing = sorted(expected - set(tools))
assert not missing, 'admitted read tools missing from discovery: %r' % missing
for name in expected:
    rl = tools[name].get('risk_level')
    assert rl == 'read', '%s risk_level is %r, expected read' % (name, rl)
ansible_names = {n for n in tools if n.startswith('ansible.')}
extra = sorted(ansible_names - expected)
assert not extra, 'unexpected ansible.* tool admitted: %r' % extra
assert denied not in tools, 'mutating verb %r is admitted' % denied" \
  "$READ_TOOLS" "$DENIED_TOOL" \
  || fail "discovery does not carry exactly the six read-tier ansible.* tools"
echo "six ansible.* read tools registered (risk_level=read); no mutating verb admitted"

echo "==> [4/6] fail-closed negatives (no server contact)"

# (a) a non-admitted mutating verb is denied by the allowlist.
invoke "$DENIED_TOOL" '{}' denied-verb
[ "$HTTP_CODE" = "400" ] || fail "mutating-verb invoke answered $HTTP_CODE, expected 400"
printf '%s' "$GATEWAY_BODY" | grep -q 'TOOL_NOT_FOUND' \
  || fail "mutating verb did not fail with TOOL_NOT_FOUND: $GATEWAY_BODY"
echo "non-admitted mutating verb ($DENIED_TOOL) rejected with TOOL_NOT_FOUND"

# (b) a missing required parameter is caught by the gateway-owned schema before
#     any MCP session opens (proves validation is gateway-side, not server-side).
invoke ansible.get_inventory '{}' missing-param
[ "$HTTP_CODE" = "400" ] || fail "missing-param invoke answered $HTTP_CODE, expected 400"
printf '%s' "$GATEWAY_BODY" | grep -q 'INVALID_PARAMETERS' \
  || fail "missing required param did not fail with INVALID_PARAMETERS: $GATEWAY_BODY"
echo "ansible.get_inventory with no 'inventory' rejected with INVALID_PARAMETERS"

echo "==> [5/6] live reads against the mock target (gated on reachability)"

invoke ansible.get_environment_health '{}' health
LIVE_OK=false
if [ "$HTTP_CODE" = "200" ]; then
  LIVE_OK=true
  HEALTH=$(mcp_payload "$GATEWAY_BODY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))")
  [ "$HEALTH" = "healthy" ] || fail "health probe returned status '$HEALTH', expected healthy"
  echo "control-plane health probe answered healthy"
else
  # Not reachable / not credentialed: assert a CLEAN fail-closed structured
  # error (never a hang, never a fabricated success), then skip the live reads.
  printf '%s' "$GATEWAY_BODY" | grep -qE "$FAIL_CLOSED_CODES" \
    || fail "health probe failed with an unexpected (non-fail-closed) body: $GATEWAY_BODY"
  CODE=$(json_field "$GATEWAY_BODY" error.code)
  if [ "$STRICT_LIVE" = "true" ]; then
    fail "STRICT_LIVE=true but the mock target was not reachable/credentialed (fail-closed: ${CODE:-unknown}); the live read leg must not be skipped"
  fi
  echo "NOTE: the mock target is not reachable/credentialed (fail-closed: ${CODE:-unknown})."
  echo "      Deploy the ansible-dev profile (make deploy) and run"
  echo "      sync-ansible-credentials.sh to exercise the live read leg, then"
  echo "      re-run with STRICT_LIVE=true. The registration and fail-closed"
  echo "      negatives above already hold."
fi

if [ "$LIVE_OK" = "true" ]; then
  invoke ansible.list_inventories '{}' inventories
  [ "$HTTP_CODE" = "200" ] || fail "list_inventories answered $HTTP_CODE: $GATEWAY_BODY"
  mcp_payload "$GATEWAY_BODY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
names = {r.get('name') for r in d.get('results', [])}
assert 'demo' in names, 'demo inventory absent: %r' % names
assert d.get('count', 0) >= 1, 'inventory count is %r' % d.get('count')" \
    || fail "list_inventories did not project the mock's demo inventory"
  echo "ansible.list_inventories projected the demo inventory"

  invoke ansible.get_inventory '{"inventory":"demo"}' inventory-detail
  [ "$HTTP_CODE" = "200" ] || fail "get_inventory answered $HTTP_CODE: $GATEWAY_BODY"
  mcp_payload "$GATEWAY_BODY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
hosts = {h.get('name') for h in d.get('hosts', [])}
assert {'mock-host-01', 'mock-host-02'} <= hosts, 'mock managed hosts absent: %r' % hosts" \
    || fail "get_inventory(demo) did not project the mock managed hosts"
  echo "ansible.get_inventory(demo) projected mock managed hosts mock-host-01/02"

  invoke ansible.list_job_templates '{}' job-templates
  [ "$HTTP_CODE" = "200" ] || fail "list_job_templates answered $HTTP_CODE: $GATEWAY_BODY"
  mcp_payload "$GATEWAY_BODY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
names = {r.get('name') for r in d.get('results', [])}
assert 'Deploy App' in names, 'Deploy App template absent: %r' % names" \
    || fail "list_job_templates did not project the mock's Deploy App template"
  echo "ansible.list_job_templates projected the Deploy App template"

  invoke ansible.get_job '{"job_id":"1"}' job
  [ "$HTTP_CODE" = "200" ] || fail "get_job answered $HTTP_CODE: $GATEWAY_BODY"
  STATUS=$(mcp_payload "$GATEWAY_BODY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))")
  [ "$STATUS" = "successful" ] || fail "get_job(1) status is '$STATUS', expected successful"
  echo "ansible.get_job(1) projected status successful"

  invoke ansible.get_job_stdout '{"job_id":"1","tail":3}' job-stdout
  [ "$HTTP_CODE" = "200" ] || fail "get_job_stdout answered $HTTP_CODE: $GATEWAY_BODY"
  mcp_payload "$GATEWAY_BODY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
out = d.get('stdout', '')
assert 'mock-host-01' in out, 'tail-bounded stdout missing the mock host: %r' % out" \
    || fail "get_job_stdout(1, tail=3) did not project the mock host recap"
  echo "ansible.get_job_stdout(1, tail=3) projected the tail-bounded recap"
fi

echo "==> [6/6] redaction: the mock bearer never appears in a tool result"

# Read the mock's bearer WITHOUT swallowing errors. `|| true` plus `2>/dev/null`
# on both stages used to collapse four distinct outcomes — key absent, key
# renamed, kubectl/RBAC failure, base64 failure — into one reassuring NOTE and a
# zero exit, silently turning the only assertion covering the two-sink
# credential invariant into a no-op.
BEARER=""
if kubectl -n "$NAMESPACE" get secret ansible-mock-credentials >/dev/null 2>&1; then
  ENCODED=$(kubectl -n "$NAMESPACE" get secret ansible-mock-credentials \
    -o jsonpath='{.data.bearer-token}') \
    || fail "ansible-mock-credentials exists but bearer-token could not be read (renamed? RBAC?)"
  [ -n "$ENCODED" ] \
    || fail "ansible-mock-credentials carries no bearer-token key (sync-ansible-credentials.sh sink 2)"
  BEARER=$(printf '%s' "$ENCODED" | base64 -d) \
    || fail "ansible-mock-credentials bearer-token is not valid base64"
fi

if [ -z "$BEARER" ]; then
  # Legitimate only when the connector never reached a credentialed target:
  # LIVE_OK=true requires a 200 health probe, which requires BOTH a resolved
  # credential set and a bearer the mock accepted — so an empty bearer alongside
  # a successful live read is provably a defect, not a trivially-satisfied check.
  [ "$LIVE_OK" != "true" ] \
    || fail "live reads succeeded but no mock bearer could be read; the two-sink credential invariant is unverifiable"
  echo "NOTE: ansible-mock-credentials secret absent; the connector had no bearer to"
  echo "      leak, so redaction is trivially satisfied (and reads fail closed above)."
else
  # A non-empty capture file is what makes the grep below meaningful: without it
  # "the bearer appears in no response" would hold because there were no
  # responses at all.
  [ -s "$RESPONSES" ] \
    || fail "no tool-result body was captured; the redaction assertion would pass vacuously"
  # -F fixed-string, -q quiet: the token is never echoed, only tested for.
  if grep -qF "$BEARER" "$RESPONSES"; then
    fail "the mock bearer leaked into a tool-result body"
  fi
  echo "the mock bearer appears in no tool-result body (rides the httpx header only)"
fi

echo ""
echo "Ansible MCP-ingestion live-check passed (opt-in):"
echo "  - unauthenticated callers rejected (401)"
echo "  - six ansible.* read tools registered read; no mutating verb admitted"
echo "  - a non-admitted verb and a missing parameter fail closed (no server contact)"
if [ "$LIVE_OK" = "true" ]; then
  echo "  - live reads projected the mock's inventory, hosts, templates, job, stdout"
else
  echo "  - live reads SKIPPED (target not reachable/credentialed, fail-closed above);"
  echo "    re-run with STRICT_LIVE=true after deploying the ansible-dev profile"
fi
echo "  - the mock bearer never appears in a tool result"
