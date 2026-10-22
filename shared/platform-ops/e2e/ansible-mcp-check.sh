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
# Two run modes, and the difference between them is the whole point of this
# script's parameterisation:
#
#   default (LIVE_TARGET unset/false) — the in-cluster thin mock. Every expected
#     value defaults to the mock's canned topology
#     (mock_ansible_mcp_server.py): inventories demo/prod, demo's hosts
#     mock-host-01/mock-host-02, job template "Deploy App", job 1 successful.
#     This is what `make e2e` runs. OQ-5 means CI makes no live external call, so
#     a green default run proves registration, fail-closed behaviour, projection
#     and redaction against the mock — never against a real server.
#
#   LIVE_TARGET=true — a real licensed AAP in read-only mode. The canned defaults
#     cannot exist on a real server, so this mode REFUSES TO RUN unless every
#     expected value is overridden explicitly. That requirement is deliberate: a
#     mock-bound assertion reported as a live pass is worse than no live pass at
#     all, because it is indistinguishable from one. This mode implies
#     STRICT_LIVE=true (a skipped live leg on a live run is a failed run, never a
#     note).
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
#   LIVE_TARGET   (default false) set true only when the gateway's Ansible MCP
#                 binding points at a real AAP. Requires every EXPECT_* knob
#                 below plus REDACTION_SECRETS_FILE to be set explicitly.
#
# Expected-value knobs (defaults are the mock's; all REQUIRED under
# LIVE_TARGET=true):
#   EXPECT_INVENTORY_NAME      (default demo) asserted in list_inventories AND
#                              passed as the get_inventory argument
#   EXPECT_INVENTORY_HOSTS     (default mock-host-01,mock-host-02) comma-separated
#                              managed-host names that must all be projected
#   EXPECT_JOB_TEMPLATE_NAME   (default Deploy App)
#   EXPECT_JOB_ID              (default 1) passed to get_job / get_job_stdout
#   EXPECT_JOB_STATUS          (default successful)
#   EXPECT_STDOUT_MARKER       (default mock-host-01) a substring the tail-bounded
#                              stdout must contain
#   REDACTION_SECRETS_FILE     (default unset) a file of credential literals — one
#                 per line, blanks and '#' comments ignored — that must not appear
#                 in any tool-result body. Under LIVE_TARGET=true this is how the
#                 redaction leg stays meaningful, since the in-cluster mock's
#                 secret does not exist on a live run. Values are only ever tested
#                 for, never echoed.
#
# Example (a live read-only run against a real AAP):
#   LIVE_TARGET=true \
#   EXPECT_INVENTORY_NAME='<a real inventory>' \
#   EXPECT_INVENTORY_HOSTS='<host-a>,<host-b>' \
#   EXPECT_JOB_TEMPLATE_NAME='<a real template>' \
#   EXPECT_JOB_ID='<a real job id>' EXPECT_JOB_STATUS=successful \
#   EXPECT_STDOUT_MARKER='<a string in that job recap>' \
#   REDACTION_SECRETS_FILE=/tmp/aap-secrets.txt \
#     sh shared/platform-ops/e2e/ansible-mcp-check.sh

set -eu

# Record which knobs the caller set EXPLICITLY, before any default is applied
# below. The defaults are the in-cluster mock's canned values, so a knob still
# holding its default cannot be evidence about a real server — and LIVE_TARGET
# needs to tell those two cases apart (see require_explicit).
EXPLICITLY_SET=" "
for _knob in EXPECT_INVENTORY_NAME EXPECT_INVENTORY_HOSTS \
  EXPECT_JOB_TEMPLATE_NAME EXPECT_JOB_ID EXPECT_JOB_STATUS \
  EXPECT_STDOUT_MARKER REDACTION_SECRETS_FILE; do
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

# A mutating verb the binding never admits (DENIED_SERVER_TOOLS has no canonical
# name); invoking it must fail closed with TOOL_NOT_FOUND even when enabled.
DENIED_TOOL="ansible.launch_job_template"
# The six admitted read-tier canonical names (ingestion/ansible_binding.py).
READ_TOOLS="ansible.list_inventories ansible.get_inventory ansible.list_job_templates ansible.get_job ansible.get_job_stdout ansible.get_environment_health"
# Expected values, defaulted to mock_ansible_mcp_server.py's canned topology.
# Exported so the python3 assertions read them from the environment rather than
# from interpolated source: a value carrying a quote or a backslash then cannot
# change what the assertion means.
EXPECT_INVENTORY_NAME="${EXPECT_INVENTORY_NAME:-demo}"
EXPECT_INVENTORY_HOSTS="${EXPECT_INVENTORY_HOSTS:-mock-host-01,mock-host-02}"
EXPECT_JOB_TEMPLATE_NAME="${EXPECT_JOB_TEMPLATE_NAME:-Deploy App}"
EXPECT_JOB_ID="${EXPECT_JOB_ID:-1}"
EXPECT_JOB_STATUS="${EXPECT_JOB_STATUS:-successful}"
EXPECT_STDOUT_MARKER="${EXPECT_STDOUT_MARKER:-mock-host-01}"
export EXPECT_INVENTORY_NAME EXPECT_INVENTORY_HOSTS EXPECT_JOB_TEMPLATE_NAME
export EXPECT_JOB_ID EXPECT_JOB_STATUS EXPECT_STDOUT_MARKER
# The structured codes the MCP connector can return WITHOUT the server answering
# (ingestion/mcp_adapter.py: transport, SDK-import, credential-set and
# credential-scheme failures). Anything else means the probe failed in a way this
# check does not understand, which must never be waved through as "unreachable".
FAIL_CLOSED_CODES='MCP_TRANSPORT_ERROR|MCP_SDK_UNAVAILABLE|CREDENTIAL_SET_NOT_FOUND|CREDENTIAL_SCHEME_UNSUPPORTED'

# Collects every enabled-state tool-result body for the redaction assertion, plus
# every credential literal that assertion tests for. Neither is ever echoed.
RESPONSES=$(mktemp)
REDACTION_LITERALS=$(mktemp)
trap 'rm -f "$RESPONSES" "$REDACTION_LITERALS"' EXIT

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# LIVE_TARGET=true claims "the assertions below are about a real server", so every
# knob whose default is a mock canned value must have been overridden explicitly.
# Without this the mode would assert 'demo' / mock-host-01 against a live AAP and
# fail in a way indistinguishable from a genuine projection regression — or,
# worse, invite someone to weaken the assertion to make it pass. Refusing to run
# is the only outcome that cannot be mistaken for evidence.
require_explicit() {
  case "$EXPLICITLY_SET" in
    *" $1 "*) return 0 ;;
  esac
  fail "LIVE_TARGET=true requires $1 to be set explicitly: its default is the in-cluster mock's canned value, which cannot exist on a real server"
}

if [ "$LIVE_TARGET" = "true" ]; then
  TARGET_LABEL="live AAP"
  # A live run exists to prove the live leg, so a skipped leg is a failed run and
  # never a note. Implied here so the two knobs cannot disagree.
  STRICT_LIVE=true
  for _knob in EXPECT_INVENTORY_NAME EXPECT_INVENTORY_HOSTS \
    EXPECT_JOB_TEMPLATE_NAME EXPECT_JOB_ID EXPECT_JOB_STATUS \
    EXPECT_STDOUT_MARKER REDACTION_SECRETS_FILE; do
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
  echo "LIVE_TARGET=true: asserting against a live AAP, not the in-cluster mock."
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

# Encode a shell string as a JSON string literal. Free-text target identifiers (an
# inventory name, say) can carry a quote or a backslash, which would otherwise
# change the SHAPE of the request body rather than just one of its values — and
# surface as a confusing INVALID_PARAMETERS on an otherwise valid live run.
json_str() {
  printf '%s' "$1" | python3 -c "
import json, sys
print(json.dumps(sys.stdin.read()), end='')"
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
    || fail "STRICT_LIVE=true but GATEWAY_ANSIBLE_MCP_ENABLED=$ANSIBLE_ENABLED; the connector is gated off, so enable a binding first (the ansible-dev profile for the mock, or a live one for LIVE_TARGET=true)"

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

echo "==> [5/6] live reads against the $TARGET_LABEL (gated on reachability)"

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
    fail "STRICT_LIVE=true but the $TARGET_LABEL was not reachable/credentialed (fail-closed: ${CODE:-unknown}); the live read leg must not be skipped"
  fi
  # Only reachable on the mock path — LIVE_TARGET=true implies STRICT_LIVE=true and
  # so fails above — which is why this remediation advice is mock-shaped.
  echo "NOTE: the $TARGET_LABEL is not reachable/credentialed (fail-closed: ${CODE:-unknown})."
  echo "      Deploy the ansible-dev profile (make deploy) and run"
  echo "      sync-ansible-credentials.sh to exercise the live read leg, then"
  echo "      re-run with STRICT_LIVE=true. The registration and fail-closed"
  echo "      negatives above already hold."
fi

if [ "$LIVE_OK" = "true" ]; then
  invoke ansible.list_inventories '{}' inventories
  [ "$HTTP_CODE" = "200" ] || fail "list_inventories answered $HTTP_CODE: $GATEWAY_BODY"
  mcp_payload "$GATEWAY_BODY" | python3 -c "
import json, os, sys
d = json.load(sys.stdin)
want = os.environ['EXPECT_INVENTORY_NAME']
names = {r.get('name') for r in d.get('results', [])}
assert want in names, 'inventory %r absent: %r' % (want, names)
assert d.get('count', 0) >= 1, 'inventory count is %r' % d.get('count')" \
    || fail "list_inventories did not project $EXPECT_INVENTORY_NAME"
  echo "ansible.list_inventories projected the $EXPECT_INVENTORY_NAME inventory"

  invoke ansible.get_inventory "{\"inventory\":$(json_str "$EXPECT_INVENTORY_NAME")}" inventory-detail
  [ "$HTTP_CODE" = "200" ] || fail "get_inventory answered $HTTP_CODE: $GATEWAY_BODY"
  mcp_payload "$GATEWAY_BODY" | python3 -c "
import json, os, sys
d = json.load(sys.stdin)
want = {h.strip() for h in os.environ['EXPECT_INVENTORY_HOSTS'].split(',') if h.strip()}
hosts = {h.get('name') for h in d.get('hosts', [])}
assert want <= hosts, 'expected managed hosts %r absent: %r' % (sorted(want), hosts)" \
    || fail "get_inventory($EXPECT_INVENTORY_NAME) did not project the expected managed hosts"
  echo "ansible.get_inventory($EXPECT_INVENTORY_NAME) projected managed hosts $EXPECT_INVENTORY_HOSTS"

  invoke ansible.list_job_templates '{}' job-templates
  [ "$HTTP_CODE" = "200" ] || fail "list_job_templates answered $HTTP_CODE: $GATEWAY_BODY"
  mcp_payload "$GATEWAY_BODY" | python3 -c "
import json, os, sys
d = json.load(sys.stdin)
want = os.environ['EXPECT_JOB_TEMPLATE_NAME']
names = {r.get('name') for r in d.get('results', [])}
assert want in names, 'job template %r absent: %r' % (want, names)" \
    || fail "list_job_templates did not project $EXPECT_JOB_TEMPLATE_NAME"
  echo "ansible.list_job_templates projected the $EXPECT_JOB_TEMPLATE_NAME template"

  invoke ansible.get_job "{\"job_id\":$(json_str "$EXPECT_JOB_ID")}" job
  [ "$HTTP_CODE" = "200" ] || fail "get_job answered $HTTP_CODE: $GATEWAY_BODY"
  STATUS=$(mcp_payload "$GATEWAY_BODY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))")
  [ "$STATUS" = "$EXPECT_JOB_STATUS" ] \
    || fail "get_job($EXPECT_JOB_ID) status is '$STATUS', expected '$EXPECT_JOB_STATUS'"
  echo "ansible.get_job($EXPECT_JOB_ID) projected status $EXPECT_JOB_STATUS"

  invoke ansible.get_job_stdout "{\"job_id\":$(json_str "$EXPECT_JOB_ID"),\"tail\":3}" job-stdout
  [ "$HTTP_CODE" = "200" ] || fail "get_job_stdout answered $HTTP_CODE: $GATEWAY_BODY"
  mcp_payload "$GATEWAY_BODY" | python3 -c "
import json, os, sys
d = json.load(sys.stdin)
want = os.environ['EXPECT_STDOUT_MARKER']
out = d.get('stdout', '')
assert want in out, 'tail-bounded stdout missing %r: %r' % (want, out)" \
    || fail "get_job_stdout($EXPECT_JOB_ID, tail=3) did not project $EXPECT_STDOUT_MARKER"
  echo "ansible.get_job_stdout($EXPECT_JOB_ID, tail=3) projected the tail-bounded recap"
fi

echo "==> [6/6] redaction: no credential ever appears in a tool result"

# Two literal sources, collected into one file and tested in a single pass. Which
# one applies depends on the target: the in-cluster mock's bearer secret on a
# default run, REDACTION_SECRETS_FILE on a live run (where that secret does not
# exist, so without the file this leg would have nothing to test and would pass
# vacuously — hence LIVE_TARGET=true requires it).

# Source 1: the mock's bearer, read WITHOUT swallowing errors. `|| true` plus
# `2>/dev/null` on both stages used to collapse four distinct outcomes — key
# absent, key renamed, kubectl/RBAC failure, base64 failure — into one reassuring
# NOTE and a zero exit, silently turning the only assertion covering the two-sink
# credential invariant into a no-op. Skipped under LIVE_TARGET=true, where the
# secret legitimately does not exist.
if [ "$LIVE_TARGET" != "true" ] && \
   kubectl -n "$NAMESPACE" get secret ansible-mock-credentials >/dev/null 2>&1; then
  ENCODED=$(kubectl -n "$NAMESPACE" get secret ansible-mock-credentials \
    -o jsonpath='{.data.bearer-token}') \
    || fail "ansible-mock-credentials exists but bearer-token could not be read (renamed? RBAC?)"
  [ -n "$ENCODED" ] \
    || fail "ansible-mock-credentials carries no bearer-token key (sync-ansible-credentials.sh sink 2)"
  BEARER=$(printf '%s' "$ENCODED" | base64 -d) \
    || fail "ansible-mock-credentials bearer-token is not valid base64"
  printf '%s\n' "$BEARER" >> "$REDACTION_LITERALS"
  echo "loaded the mock's bearer-token as a redaction literal"
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
  # LIVE_OK=true requires a 200 health probe, which requires BOTH a resolved
  # credential set and a bearer the server accepted — so a successful live read
  # with no literal to test is provably a defect, not a trivially-satisfied check.
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
  echo "no credential literal ($LITERAL_COUNT tested) appears in any tool-result body (it rides the httpx header only)"
fi

echo ""
echo "Ansible MCP-ingestion live-check passed (opt-in, target: $TARGET_LABEL):"
echo "  - unauthenticated callers rejected (401)"
echo "  - six ansible.* read tools registered read; no mutating verb admitted"
echo "  - a non-admitted verb and a missing parameter fail closed (no server contact)"
if [ "$LIVE_OK" = "true" ]; then
  echo "  - live reads projected inventory $EXPECT_INVENTORY_NAME, its hosts, template"
  echo "    $EXPECT_JOB_TEMPLATE_NAME, job $EXPECT_JOB_ID ($EXPECT_JOB_STATUS) and its stdout"
else
  echo "  - live reads SKIPPED (target not reachable/credentialed, fail-closed above);"
  echo "    re-run with STRICT_LIVE=true after deploying the ansible-dev profile"
fi
echo "  - no credential literal appears in any tool result"
