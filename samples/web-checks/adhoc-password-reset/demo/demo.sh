#!/bin/sh

# Ad-hoc per-action browser-write tutorial demo (SPEC-054 sample).
#
# Deterministic end-to-end assertions for the ResetPasswordAdHoc runbook
# and its supporting infrastructure, runnable after `make deploy` and
# `make deploy-samples` (which installs this sample's runbook).
#
# This is the UNBOUND counterpart to samples/web-checks/password-reset.
# Both reset a password in the same admin portal, but password-reset binds
# a flow (one HITL gate, approval_kind=flow) while this runbook declares no
# web_target, so nothing binds and every write-tier browser interaction
# parks its OWN per-action change-request card (approval_kind=action) — the
# path SPEC-054 R-2 makes reachable for the first time.
#
# Deterministic legs (always run):
#   1. browser connector enabled, HITL bridging active
#   2. admin portal pages served by the browser-check-target nginx
#   3. admin-portal credential set loaded on the tool-gateway
#   4. ad-hoc runbook ingested WITHOUT a web_target (the unbound guarantee)
#   5. fifteen web.* tools in discovery with correct risk tiers
#
# Optional chat leg (RUN_CHAT_LEG=true): a scripted chat asks the agent to
# reset a user's password ad hoc, following the runbook but NOT binding a
# flow. The agent logs in by reference (web.fill_credential — read tier,
# admitted unbound by SPEC-054 R-2) and reaches the reset form through a
# read-tier navigate; its write-tier interaction(s) park per-action cards.
# The demo approves EVERY card in a bounded loop and asserts, count- and
# tool-agnostically, that each is approval_kind=action with a change-request
# projection and no flow_summary, and that the durable record persists the
# same for every card with all write-tier executions signed. The chat leg
# depends on the model choosing the right tools, so it is opt-in like the
# other demos' chat legs.
#
# Prerequisites:
#   - kubectl context pointed at the dev cluster
#   - `make deploy` completed (browser connector enabled, admin pages
#     mounted, admin-portal credential set synced)
#   - `make deploy-samples` completed (installs this sample's runbook into
#     the skills-hub `samples` source)
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
SKILL_ID="samples/adhoc-password-reset-resetpasswordadhoc"
RUNBOOK_PATH="/skills/samples/adhoc-password-reset-ResetPasswordAdHoc.md"
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

echo "==> [4/5] ad-hoc runbook ingested WITHOUT a web_target"

RUNBOOK=$(kubectl -n "$NAMESPACE" exec deployment/skills-hub -- \
  cat "$RUNBOOK_PATH") \
  || fail "ad-hoc runbook not found in skills-hub at $RUNBOOK_PATH (run 'make deploy-samples')"
printf '%s' "$RUNBOOK" | grep -q '^title:' \
  || fail "the ad-hoc runbook has no title frontmatter"
# The defining property of this sample: the runbook declares NO web_target, so
# web.navigate(skill_id=…) cannot bind a flow (SKILL_NOT_WEB_FLOW) and every
# write stays unbound → per-action cards. If a web_target ever appears here the
# sample would silently regress to the one-gate flow model.
if printf '%s' "$RUNBOOK" | grep -q '^web_target:'; then
  fail "the ad-hoc runbook declares web_target — it must stay unbound (no web_target) to demonstrate per-action approval"
fi
echo "ad-hoc runbook ingested from the samples source (no web_target — stays unbound)"

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
  echo "==> [CHAT] ad-hoc unbound password-reset with per-action approval"

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

  CHAT_MESSAGE="Ad-hoc, WITHOUT binding any browser flow, reset the password for user '${TARGET_USER}' in the legacy admin panel to '${NEW_PASSWORD}'. Follow runbook ${SKILL_ID} for the steps, but do NOT pass skill_id to web.navigate — this session must stay UNBOUND so each write parks its own per-action card. Admin credentials are in the admin-portal credential set: use web.fill_credential (never web.type) for them. Pass the new password as the newpw URL parameter on the reset page, then click Confirm reset."

  STREAM=$(curl -fsS --max-time 300 -N \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    "$GATEWAY_URL/api/v1/chat/stream?session_id=$CHAT_SESSION&message=$(python3 -c "
import urllib.parse, sys
print(urllib.parse.quote(sys.argv[1]))" "$CHAT_MESSAGE")") \
    || fail "chat stream request failed"

  # Approve every per-action card the unbound write(s) park, in a bounded
  # loop. Each approval resumes the turn; the resumed stream may park the
  # next card (there is no flow-unlock for unbound writes) or complete.
  CARDS=0
  i=0
  while [ "$i" -lt 8 ]; do
    i=$((i+1))
    printf '%s' "$STREAM" | grep -q '"type": *"confirmation_request"\|"type":"confirmation_request"' || break

    CONFIRM_ID=$(printf '%s' "$STREAM" | python3 -c "
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line.startswith('data:'):
        continue
    try:
        frame = json.loads(line[5:].strip())
    except ValueError:
        continue
    if frame.get('type') != 'confirmation_request':
        continue
    kind = frame.get('approval_kind')
    assert kind == 'action', 'card approval_kind is %r, expected action (did the model bind a flow?)' % (kind,)
    assert not frame.get('flow_summary'), 'an action card must carry no flow_summary, got %r' % (frame.get('flow_summary'),)
    assert isinstance(frame.get('message'), str) and frame.get('message'), 'action card carries no top-line message (SPEC-054 R-4)'
    calls = frame.get('pending_calls') or []
    assert calls, 'action card has no pending_calls'
    found_cr = False
    for c in calls:
        cr = c.get('change_request')
        if isinstance(cr, dict) and isinstance(cr.get('summary'), str) and cr.get('summary'):
            found_cr = True
    assert found_cr, 'no pending_call carries a change_request projection (SPEC-054 R-3)'
    print(frame.get('confirm_id', ''))
    break
") || fail "a parked card is not a per-action change-request card (SPEC-054 R-1/R-3)"
    [ -n "$CONFIRM_ID" ] || fail "confirmation_request frame carried no confirm_id"
    CARDS=$((CARDS+1))
    echo "  card ${CARDS}: per-action change-request card parked (confirm_id=${CONFIRM_ID}); approving"

    STREAM=$(curl -fsS --max-time 300 -X POST \
      -H "Authorization: Bearer $APPROVER_PLATFORM_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"session_id\": \"$CHAT_SESSION\", \"confirm_id\": \"$CONFIRM_ID\", \"decision\": \"approve\"}" \
      "$GATEWAY_URL/api/v1/chat/confirm") || fail "approver approve call failed for card ${CARDS}"
    printf '%s' "$STREAM" | grep -q '"status": *"approved"\|"status":"approved"' \
      || fail "confirmation_result did not report the approval for card ${CARDS}"
  done

  [ "$CARDS" -ge 1 ] \
    || fail "no per-action card parked (did the model reach an unbound write-tier interaction?)"
  if printf '%s' "$STREAM" | grep -q '"type": *"confirmation_request"\|"type":"confirmation_request"'; then
    fail "more than 8 per-action cards parked; aborting the bounded approve loop"
  fi
  echo "approved ${CARDS} per-action card(s): one card per unbound write, no flow-unlock (SPEC-054 R-2)"

  # The bounded loop terminated with no further parked card, so the resumed turn
  # ran to completion. Prove completion durably — never by the model's natural
  # -language phrasing, which varies run to run — via the session-detail check
  # below (no pending confirmation; every card action-kind + approved with a
  # change request; every write-tier execution signed).
  echo "the resumed turn ran to completion (durable proof via the session detail below)"

  # Durable proof: every persisted card is action-kind with a change request
  # and a message, and all its write-tier executions are signed.
  SESSION_DETAIL=$(curl -fsS --max-time 30 \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    "$GATEWAY_URL/api/v1/sessions/$CHAT_SESSION") \
    || fail "owner session detail fetch failed"
  printf '%s' "$SESSION_DETAIL" | python3 -c "
import json, sys
detail = json.load(sys.stdin)
assert detail.get('pending_confirmation') is not True, 'the session still parks a confirmation after the resume completed'
cards = detail.get('confirmations') or []
assert cards, 'session detail carries no confirmation cards'
WRITE_TIER = {'web.click', 'web.type', 'web.select', 'web.press_key', 'web.upload_file', 'web.evaluate'}
signed = 0
for idx, card in enumerate(cards):
    assert card.get('approval_kind') == 'action', 'durable card %d approval_kind is %r, expected action' % (idx, card.get('approval_kind'))
    assert not card.get('flow_summary'), 'durable action card %d carries a flow_summary %r' % (idx, card.get('flow_summary'))
    assert card.get('status') == 'approved', 'durable card %d status is %r, expected approved' % (idx, card.get('status'))
    assert isinstance(card.get('message'), str) and card.get('message'), 'durable card %d persisted no message (SPEC-054 R-4)' % idx
    calls = card.get('pending_calls') or []
    found_cr = False
    for c in calls:
        cr = c.get('change_request')
        if isinstance(cr, dict) and isinstance(cr.get('summary'), str) and cr.get('summary'):
            found_cr = True
    assert found_cr, 'durable card %d persisted no change_request projection (SPEC-054 R-3)' % idx
    executions = card.get('executions') or []
    assert executions, 'durable approved card %d carries no execution rows' % idx
    for row in executions:
        assert row.get('tool_name') in WRITE_TIER, 'execution row names %r, expected a write-tier web.* tool' % row.get('tool_name')
        assert row.get('receipt', {}).get('signature'), 'execution %r carries no signed receipt' % row.get('tool_name')
        signed += 1
print('  %d per-action card(s), all action-kind with a change request; %d signed write-tier execution(s)' % (len(cards), signed))" \
    || fail "session detail lacks the per-action change-request cards with signed executions"
  echo "session detail carries only action-kind cards, each with a change request and signed executions (SPEC-054 R-1/R-2/R-3/R-4)"

  echo ""
  echo "==> [CHAT] verification URLs (open in your browser to see the reset result):"
  echo "    Admin portal user list: http://localhost:9090/admin/users/?reset=${TARGET_USER}"
  echo "    Confirmation page:      http://localhost:9090/admin/users/reset/done/?user=${TARGET_USER}"
else
  echo "==> [CHAT] chat leg skipped (RUN_CHAT_LEG unset; opt-in)"
fi

echo ""
echo "Ad-hoc per-action browser-write tutorial demo passed:"
echo "  - browser connector enabled, HITL bridging active"
echo "  - admin portal pages served (login, users, reset form)"
echo "  - admin-portal credential set loaded"
echo "  - ad-hoc runbook ingested with no web_target (stays unbound)"
echo "  - fifteen web.* tools registered with correct risk tiers"
