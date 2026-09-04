#!/bin/sh

# Password-reset tutorial demo (SPEC-050 browser web-check sample).
#
# Deterministic end-to-end assertions for the ResetUserPassword skill
# and its supporting infrastructure, runnable after `make deploy` and
# `make deploy-samples` (which installs this sample's skill).
#
# Deterministic legs (always run):
#   1. browser connector enabled, HITL bridging active
#   2. admin portal pages served by the browser-check-target nginx
#   3. admin-portal credential set loaded on the tool-gateway
#   4. ResetUserPassword skill ingested by the skills-hub
#   5. fifteen web.* tools in discovery with correct risk tiers
#
# Optional chat leg (RUN_CHAT_LEG=true): a scripted chat asks the
# agent to reset a user's password via the ResetUserPassword skill.
# The agent drives the browser through the admin login, user list,
# and reset form. Authentication is read-tier: the agent fills the
# admin credentials and the login form auto-submits (legacy SSO), so
# no click parks a card there. The agent then navigates to the reset
# URL (the form pre-fills but does not submit) and performs its
# write-tier interactions (e.g. clicking "Confirm reset"). The FIRST
# write-tier browser interaction parks exactly one HITL confirmation
# card; the demo approves it and the kernel resumes the flow.
# SPEC-051 enforces the one-gate-per-flow invariant kernel-side: every
# subsequent write-tier web.* interaction in the same flow is
# auto-signed under that one approval rather than parking its own
# card, so even a deviating model (which may mix web.click with
# web.evaluate) yields a single card. The demo then verifies the
# "Password reset successfully" outcome and the durable proof: exactly
# one approved card whose write-tier executions ALL carry signed
# receipts. The chat leg depends on the model choosing the right
# tools, so it is opt-in like the other demos' chat legs.
#
# Prerequisites:
#   - kubectl context pointed at the dev cluster
#   - `make deploy` completed (browser connector enabled, admin pages
#     mounted, admin-portal credential set synced)
#   - `make deploy-samples` completed (installs this sample's
#     ResetUserPassword skill into the skills-hub `samples` source)
#   - a port-forward for the identity broker (token issuance):
#       kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000
#   - for the chat leg additionally a port-forward for the platform-gateway:
#       kubectl -n dev-luban-aiops port-forward svc/platform-gateway 18083:8000
#
# Environment overrides:
#   NAMESPACE        (default dev-luban-aiops)
#   IDENTITY_URL     (default http://localhost:18081)
#   GATEWAY_URL      (default http://localhost:18083, chat leg)
#   TEST_USER        (default luban-operator)
#   APPROVER_USER    (default luban-approver, chat leg decider)
#   TARGET_USER      (default alice@example.com)
#   NEW_PASSWORD     (default TempPass-2026!)

set -eu

NAMESPACE="${NAMESPACE:-dev-luban-aiops}"
IDENTITY_URL="${IDENTITY_URL:-http://localhost:18081}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:18083}"
TEST_USER="${TEST_USER:-luban-operator}"
APPROVER_USER="${APPROVER_USER:-luban-approver}"
TARGET_USER="${TARGET_USER:-alice@example.com}"
NEW_PASSWORD="${NEW_PASSWORD:-TempPass-2026!}"
SKILL_ID="samples/password-reset-resetuserpassword"
ADMIN_URL="http://browser-check-target:8080/admin/"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

echo "==> [1/5] prerequisites: browser connector enabled"

BROWSER_ENABLED=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o jsonpath='{.data.GATEWAY_BROWSER_ENABLED}')
[ "${BROWSER_ENABLED:-}" = "true" ] \
  || fail "GATEWAY_BROWSER_ENABLED is not true ($BROWSER_ENABLED); run 'make deploy' with the browser-dev profile"
echo "browser connector enabled"

HITL_TIMEOUT=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o jsonpath='{.data.AGENT_HITL_CONFIRM_TIMEOUT}')
[ "${HITL_TIMEOUT:-600}" != "0" ] \
  || fail "AGENT_HITL_CONFIRM_TIMEOUT=0 disables HITL bridging; the chat leg cannot run"
echo "HITL bridging active (timeout=${HITL_TIMEOUT:-600}s)"

echo "==> [2/5] admin portal pages served"

kubectl -n "$NAMESPACE" exec deployment/browser-check-target -- \
  curl -fsS http://localhost:8080/admin/ | grep -q 'Admin Portal' \
  || fail "admin portal login page not served"
echo "admin portal login page served at /admin/"

kubectl -n "$NAMESPACE" exec deployment/browser-check-target -- \
  curl -fsS http://localhost:8080/admin/users/ | grep -q 'User Management' \
  || fail "admin user list page not served"
echo "admin user list served at /admin/users/"

kubectl -n "$NAMESPACE" exec deployment/browser-check-target -- \
  curl -fsS "http://localhost:8080/admin/users/reset/?user=test" | grep -q 'Reset Password' \
  || fail "admin reset page not served"
echo "admin reset form served at /admin/users/reset/"

echo "==> [3/5] admin-portal credential set loaded"

CRED_JSON=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -- \
  cat /etc/luban/browser-credentials/credential-sets.json)
printf '%s' "$CRED_JSON" | python3 -c "
import json, sys
sets = json.load(sys.stdin)
assert 'admin-portal' in sets, 'admin-portal credential set missing'
assert sets['admin-portal'].get('username') == 'admin', \
    'admin-portal username is %r, expected admin' % sets['admin-portal'].get('username')
assert sets['admin-portal'].get('password'), 'admin-portal password is empty'
assert 'browser-check-target' in sets, 'browser-check-target set missing (regression)'" \
  || fail "admin-portal credential set not loaded correctly"
echo "admin-portal credential set loaded (username=admin, password present)"

echo "==> [4/5] ResetUserPassword skill ingested"

kubectl -n "$NAMESPACE" exec deployment/skills-hub -- \
  cat /skills/samples/password-reset-ResetUserPassword.md \
  | grep -q 'risk_class: write' \
  || fail "ResetUserPassword skill not found in skills-hub (run 'make deploy-samples')"
echo "ResetUserPassword skill ingested from the samples source (risk_class: write)"

echo "==> [5/5] fifteen web.* tools with correct risk tiers"

# Dev platform tokens from the identity broker.
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

DISCOVERY=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -- \
  curl -fsS -H "Authorization: Bearer $OPERATOR_TOKEN" \
  http://localhost:8000/api/v2/tools)

printf '%s' "$DISCOVERY" | python3 -c "
import json, sys
tools = {t['name']: t for t in json.load(sys.stdin)}
expect = {
    'web.navigate': 'read',
    'web.snapshot': 'read',
    'web.screenshot': 'read',
    'web.fill_credential': 'read',
    'web.extract': 'read',
    'web.wait_for': 'read',
    'web.hover': 'read',
    'web.scroll': 'read',
    'web.switch_frame': 'read',
    'web.click': 'write',
    'web.type': 'write',
    'web.select': 'write',
    'web.press_key': 'write',
    'web.upload_file': 'write',
    'web.evaluate': 'write',
}
for name, risk in expect.items():
    tool = tools.get(name)
    assert tool is not None, '%s missing from discovery' % name
    assert tool.get('risk_level') == risk, \
        '%s risk_level is %r, expected %s' % (name, tool.get('risk_level'), risk)" \
  || fail "discovery does not carry the fifteen web.* tools with expected risk tiers"
echo "all fifteen web.* tools registered (9 read, 6 write)"

if [ "${RUN_CHAT_LEG:-}" = "true" ]; then
  echo "==> [CHAT] scripted password-reset with HITL approval"

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

  CHAT_MESSAGE="Reset the password for user '${TARGET_USER}' in the legacy admin panel. Use skill ${SKILL_ID}. The new temporary password is '${NEW_PASSWORD}'. Admin credentials are in the admin-portal credential set."

  STREAM_OUTPUT=$(curl -fsS --max-time 300 -N \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    "$GATEWAY_URL/api/v1/chat/stream?session_id=$CHAT_SESSION&message=$(python3 -c "
import urllib.parse, sys
print(urllib.parse.quote(sys.argv[1]))" "$CHAT_MESSAGE")") \
    || fail "chat stream request failed"

  printf '%s' "$STREAM_OUTPUT" | grep -q '"type": *"confirmation_request"\|"type":"confirmation_request"' \
    || fail "no confirmation_request frame (did the model reach a write-tier browser interaction?)"
  echo "the first write-tier browser interaction parked the single confirmation card"

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

  CONFIRM_OUTPUT=$(curl -fsS --max-time 300 -X POST \
    -H "Authorization: Bearer $APPROVER_PLATFORM_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$CHAT_SESSION\", \"confirm_id\": \"$CONFIRM_ID\", \"decision\": \"approve\"}" \
    "$GATEWAY_URL/api/v1/chat/confirm") || fail "approver approve call failed"
  printf '%s' "$CONFIRM_OUTPUT" | grep -q '"status": *"approved"\|"status":"approved"' \
    || fail "confirmation_result did not report the approval: $CONFIRM_OUTPUT"
  echo "approval applied; the kernel resumed and completed the password reset"

  # SPEC-051: exactly one gate per flow. The single approval above
  # resumes the flow to completion — there is no second card to handle.
  FINAL_OUTPUT="$CONFIRM_OUTPUT"

  printf '%s' "$FINAL_OUTPUT" | grep -qi 'reset successfully\|Password for' \
    || fail "the resumed turn did not reach the password-reset confirmation"
  echo "the confirm stream carried the resumed turn to the password-reset confirmation"

  # Durable proof: exactly one approved card with a signed execution receipt.
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
    'expected exactly one confirmation card (SPEC-051 one-gate-per-flow), got %d' % len(cards)
card = cards[0]
assert card.get('status') == 'approved', \
    'card status is %r, expected approved' % card.get('status')
executions = card.get('executions') or []
assert executions, 'approved card carries no execution rows'
# SPEC-051 R-1/R-3: every write-tier browser interaction in the flow rode
# the ONE approval, so each execution is auto-signed under the approving
# card's authority and carries a signed receipt. The model may drive the
# reset with any write-tier web.* tool (web.click, web.evaluate, ...), so
# assert the tier and the signature — not one specific tool name.
WRITE_TIER = {'web.click', 'web.type', 'web.select', 'web.press_key', 'web.upload_file', 'web.evaluate'}
for row in executions:
    assert row.get('tool_name') in WRITE_TIER, \
        'execution row names %r, expected a write-tier web.* tool' % row.get('tool_name')
    assert row.get('receipt', {}).get('signature'), \
        'execution %r carries no signed receipt' % row.get('tool_name')
print('  %d write-tier execution(s) all signed under the one card: %s' % (
    len(executions), ', '.join(sorted({r.get('tool_name') for r in executions}))))" \
    || fail "session detail lacks the single approved card with all write-tier executions signed"
  echo "session detail carries exactly one approved card (SPEC-051 one-gate-per-flow); all its write-tier executions are signed"
  
  echo ""
  echo "==> [CHAT] verification URLs (open in your browser to see the reset result):"
  echo "    Admin portal user list: http://localhost:9090/admin/users/?reset=${TARGET_USER}"
  echo "    Confirmation page:      http://localhost:9090/admin/users/reset/done/?user=${TARGET_USER}"
else
  echo "==> [CHAT] chat leg skipped (RUN_CHAT_LEG unset; opt-in)"
fi

echo ""
echo "Password-reset tutorial demo passed:"
echo "  - browser connector enabled, HITL bridging active"
echo "  - admin portal pages served (login, users, reset form)"
echo "  - admin-portal credential set loaded"
echo "  - ResetUserPassword skill ingested"
echo "  - fifteen web.* tools registered with correct risk tiers"
