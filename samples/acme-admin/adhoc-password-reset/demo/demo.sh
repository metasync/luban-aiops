#!/bin/sh

# acme-admin adhoc-password-reset demo (SPEC-060; the sample originated as the
# SPEC-054 unbound per-action browser-write tutorial).
#
# The story: the UNBOUND counterpart to ../password-reset. Both reset a password
# in the same acme-admin console, but password-reset binds a flow (one HITL gate,
# approval_kind=flow) while this runbook declares no web_target, so nothing binds
# and every write-tier browser interaction parks its OWN per-action change-request
# card (approval_kind=action) — the path SPEC-054 R-2 makes reachable.
#
# SPEC-060 moved this sample off the static browser-check-target mock onto the
# stateful acme-admin app, so the chat leg can now prove the approved reset really
# landed in the store (revision bump + password_changed_at) rather than pointing at
# a page that only echoes its own query string.
#
# Deterministic legs (always run, no model involved):
#   1. the browser + mutating surfaces are on, HITL bridging active, the origin is
#      allowlisted, and the acme-admin credential set resolves
#   2. the runbook is ingested and declares NO web_target and NO risk_class (the
#      unbound guarantee)
#   3. the fifteen web.* tools are registered at their correct risk tiers
#   4. the target really mutates: a console reset bumps the revision and records
#      password_changed_at, corroborated by the JSON API — so the chat leg's
#      post-approval check is a fact about a store, not a sentence a page prints
#
# Optional chat leg (RUN_CHAT_LEG=true): a scripted chat asks the agent to reset a
# password ad hoc, following the runbook but NOT binding a flow. The agent logs in
# by reference (web.fill_credential — read tier, admitted unbound by SPEC-054 R-2)
# and reaches the reset form through a read-tier navigate; its write-tier
# interaction(s) park per-action cards. The demo approves EVERY card in a bounded
# loop and asserts, count- and tool-agnostically, that each is approval_kind=action
# with a change-request projection and no flow_summary, that the durable record
# persists the same with every write-tier execution signed, and — the point of the
# move — that the store then carries the reset.
#
# Prerequisites: see demo-lib.sh's header.

set -eu

DEMO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
# shellcheck source=../../demo-lib.sh
. "$DEMO_DIR/../../demo-lib.sh"

acme_demo_init "adhoc-password-reset" 4

SKILL_ID="samples/adhoc-password-reset-resetpasswordadhoc"
RUNBOOK_FILE="ResetPasswordAdHoc.md"
TARGET_USER="${TARGET_USER:-alice}"
NEW_PASSWORD="${NEW_PASSWORD:-TempPass-2026!}"

acme_leg "the unbound write surfaces are on and the credential resolves"

require_runtime_config GATEWAY_BROWSER_ENABLED true \
  "deploy with the browser-dev runtime profile"
require_runtime_config GATEWAY_MUTATING_TOOLS_ENABLED true \
  "deploy with the mutating-dev runtime profile, or web.click is not registered"
require_allowlisted GATEWAY_BROWSER_ALLOW_ORIGINS \
  "the browser-dev profile lists the sample app's origin"
require_credential_set
require_hitl_enabled

acme_leg "the runbook is ingested and declares no web_target (stays unbound)"

require_skill adhoc-password-reset "$RUNBOOK_FILE" \
  'title: Reset a Password Ad Hoc' \
  'web.fill_credential'
# The defining property of this sample: the runbook declares NO web_target, so
# web.navigate(skill_id=…) cannot bind a flow (SKILL_NOT_WEB_FLOW) and every write
# stays unbound → per-action cards. If a web_target ever appears here the sample
# would silently regress to the one-gate flow model.
runbook_body=$(kubectl -n "$NAMESPACE" exec deployment/skills-hub -- \
  cat "/skills/samples/adhoc-password-reset-$RUNBOOK_FILE")
if printf '%s' "$runbook_body" | grep -q '^web_target:'; then
  fail "the ad-hoc runbook declares web_target — it must stay unbound to demonstrate per-action approval"
fi
if printf '%s' "$runbook_body" | grep -q '^risk_class:'; then
  fail "the ad-hoc runbook declares risk_class — an unbound runbook declares neither"
fi
ok "the runbook declares no web_target and no risk_class (the session stays platform-enforced unbound)"

acme_leg "the fifteen web.* tools are registered at their risk tiers"

require_tools_registered \
  "web.navigate:read" "web.snapshot:read" "web.screenshot:read" \
  "web.fill_credential:read" "web.extract:read" "web.wait_for:read" \
  "web.hover:read" "web.scroll:read" "web.switch_frame:read" \
  "web.click:write" "web.type:write" "web.select:write" \
  "web.press_key:write" "web.upload_file:write" "web.evaluate:write"

acme_leg "the target really mutates, so verification is a fact not a page"

# The difference SPEC-060 buys: a console reset moves the store, and the JSON API
# corroborates it. The static mock this sample replaced echoed its query string and
# reported success for any user, so there was nothing to verify against.
reseed_demo
app_sign_in
app_post_session /admin/users/reset/ \
  "{\"user\":\"${TARGET_USER}\",\"new_password\":\"${NEW_PASSWORD}\",\"confirm_password\":\"${NEW_PASSWORD}\"}"
[ "$APP_CODE" = "200" ] || fail "the reset POST answered $APP_CODE: $APP_BODY"
printf '%s' "$APP_BODY" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("ok") is True, "ok is %r" % payload.get("ok")
assert payload.get("revision") == 1, "revision is %r, expected 1 after one mutation" % payload.get("revision")
assert payload.get("password_changed_at"), "the reset recorded no password_changed_at"' \
  || fail "the reset response did not carry the post-mutation facts: $APP_BODY"
app_http_authed "$ORIGIN/api/users/$TARGET_USER"
printf '%s' "$APP_BODY" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("password_changed_at"), "the API records no password_changed_at for %s" % sys.argv[1]
assert payload.get("revision") == 1, "revision is %r" % payload.get("revision")
print("  ok: GET /api/users/%s corroborates the reset (revision 1, password_changed_at %s)" % (
    sys.argv[1], payload.get("password_changed_at")))' "$TARGET_USER" \
  || fail "the API does not corroborate the reset: $APP_BODY"

if [ "${RUN_CHAT_LEG:-}" = "true" ]; then
  echo ""
  echo "==> [CHAT] ad-hoc unbound password-reset with per-action approval"

  # A fresh seed, so the post-approval store check has a known baseline.
  reseed_demo
  ensure_tokens

  CHAT_SESSION=$(chat_session_new)
  [ -n "$CHAT_SESSION" ] || fail "session creation returned no session_id"

  CHAT_MESSAGE="Ad-hoc, WITHOUT binding any browser flow, reset the password for user '${TARGET_USER}' in the acme-admin console to '${NEW_PASSWORD}'. Follow runbook ${SKILL_ID} for the steps, but do NOT pass skill_id to web.navigate — this session must stay UNBOUND so each write parks its own per-action card. Admin credentials are in the ${CREDENTIAL_SET} credential set: use web.fill_credential (never web.type) for them. Pass the new password as the newpw URL parameter on the reset page, then click Confirm reset."

  STREAM=$(chat_send "$CHAT_SESSION" "$CHAT_MESSAGE")

  # Approve every per-action card the unbound write(s) park, in a bounded loop.
  # Each approval resumes the turn; the resumed stream may park the next card
  # (there is no flow-unlock for unbound writes) or complete. The assertions are
  # count- and tool-agnostic: whatever the model drove the write with, each card
  # must be an action-kind change request with no flow_summary.
  CARDS=0
  i=0
  while [ "$i" -lt 8 ]; do
    i=$((i+1))
    printf '%s' "$STREAM" | grep -q '"type": *"confirmation_request"\|"type":"confirmation_request"' || break

    CONFIRM_ID=$(printf '%s' "$STREAM" | python3 -c '
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line.startswith("data:"):
        continue
    try:
        frame = json.loads(line[5:].strip())
    except ValueError:
        continue
    if frame.get("type") != "confirmation_request":
        continue
    kind = frame.get("approval_kind")
    assert kind == "action", "card approval_kind is %r, expected action (did the model bind a flow?)" % (kind,)
    assert not frame.get("flow_summary"), "an action card must carry no flow_summary, got %r" % (frame.get("flow_summary"),)
    assert isinstance(frame.get("message"), str) and frame.get("message"), "action card carries no top-line message (SPEC-054 R-4)"
    calls = frame.get("pending_calls") or []
    assert calls, "action card has no pending_calls"
    found_cr = False
    for c in calls:
        cr = c.get("change_request")
        if isinstance(cr, dict) and isinstance(cr.get("summary"), str) and cr.get("summary"):
            found_cr = True
    assert found_cr, "no pending_call carries a change_request projection (SPEC-054 R-3)"
    print(frame.get("confirm_id", ""))
    break') || fail "a parked card is not a per-action change-request card (SPEC-054 R-1/R-3)"
    [ -n "$CONFIRM_ID" ] || fail "confirmation_request frame carried no confirm_id"
    CARDS=$((CARDS+1))
    echo "  card ${CARDS}: per-action change-request card parked (confirm_id=${CONFIRM_ID}); approving"

    # The one-time value must not survive into the card an approver reads.
    require_no_plaintext_in_cards "$STREAM" "$NEW_PASSWORD"

    STREAM=$(chat_confirm "$CHAT_SESSION" "$CONFIRM_ID" approve)
    printf '%s' "$STREAM" | grep -q '"status": *"approved"\|"status":"approved"' \
      || fail "confirmation_result did not report the approval for card ${CARDS}"
  done

  [ "$CARDS" -ge 1 ] \
    || fail "no per-action card parked (did the model reach an unbound write-tier interaction?)"
  if printf '%s' "$STREAM" | grep -q '"type": *"confirmation_request"\|"type":"confirmation_request"'; then
    fail "more than 8 per-action cards parked; aborting the bounded approve loop"
  fi
  ok "approved ${CARDS} per-action card(s): one card per unbound write, no flow-unlock (SPEC-054 R-2)"

  # Durable proof: every persisted card is action-kind with a change request and a
  # message, and all its write-tier executions are signed.
  SESSION_DETAIL=$(curl -fsS --max-time 30 \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    "$GATEWAY_URL/api/v1/sessions/$CHAT_SESSION") \
    || fail "owner session detail fetch failed"
  printf '%s' "$SESSION_DETAIL" | python3 -c '
import json, sys
detail = json.load(sys.stdin)
assert detail.get("pending_confirmation") is not True, "the session still parks a confirmation after the resume completed"
cards = detail.get("confirmations") or []
assert cards, "session detail carries no confirmation cards"
WRITE_TIER = {"web.click", "web.type", "web.select", "web.press_key", "web.upload_file", "web.evaluate"}
signed = 0
for idx, card in enumerate(cards):
    assert card.get("approval_kind") == "action", "durable card %d approval_kind is %r, expected action" % (idx, card.get("approval_kind"))
    assert not card.get("flow_summary"), "durable action card %d carries a flow_summary %r" % (idx, card.get("flow_summary"))
    assert card.get("status") == "approved", "durable card %d status is %r, expected approved" % (idx, card.get("status"))
    assert isinstance(card.get("message"), str) and card.get("message"), "durable card %d persisted no message (SPEC-054 R-4)" % idx
    calls = card.get("pending_calls") or []
    found_cr = False
    for c in calls:
        cr = c.get("change_request")
        if isinstance(cr, dict) and isinstance(cr.get("summary"), str) and cr.get("summary"):
            found_cr = True
    assert found_cr, "durable card %d persisted no change_request projection (SPEC-054 R-3)" % idx
    executions = card.get("executions") or []
    assert executions, "durable approved card %d carries no execution rows" % idx
    for row in executions:
        assert row.get("tool_name") in WRITE_TIER, "execution row names %r, expected a write-tier web.* tool" % row.get("tool_name")
        assert row.get("receipt", {}).get("signature"), "execution %r carries no signed receipt" % row.get("tool_name")
        signed += 1
print("  ok: %d per-action card(s), all action-kind with a change request; %d signed write-tier execution(s)" % (len(cards), signed))' \
    || fail "session detail lacks the per-action change-request cards with signed executions"

  # The point of the move: the approved reset really landed in the store. The
  # static mock this sample replaced could only ever point at a page that echoes
  # its query string; acme-admin answers from state.
  app_http_authed "$ORIGIN/api/users/$TARGET_USER"
  [ "$APP_CODE" = "200" ] || fail "GET /api/users/$TARGET_USER answered $APP_CODE"
  printf '%s' "$APP_BODY" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("password_changed_at"), "no password_changed_at after an approved reset: %r" % payload
assert payload.get("revision", 0) >= 1, "revision is %r; the approved reset did not move it" % payload.get("revision")
print("  ok: %s carries password_changed_at %s at revision %s — the approved ad-hoc reset landed in the store" % (
    payload.get("username"), payload.get("password_changed_at"), payload.get("revision")))' \
    || fail "the store does not reflect the approved ad-hoc reset: $APP_BODY"
else
  chat_leg_skipped "a scripted unbound reset asserting one action card per write and a tier-2 approval"
fi

acme_demo_summary \
  "the browser and mutating surfaces are on, the origin is allowlisted, and the acme-admin credential set resolves" \
  "the runbook declares no web_target and no risk_class, so the session stays platform-enforced unbound" \
  "all fifteen web.* tools are registered (9 read, 6 write)" \
  "the console reset really mutates the store — revision 1, password_changed_at recorded, corroborated by the JSON API" \
  "under RUN_CHAT_LEG, every parked card is action-kind with a change request and no flow_summary, every write-tier execution is signed, and the approved reset lands in the store"
