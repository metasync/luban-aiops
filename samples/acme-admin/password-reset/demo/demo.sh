#!/bin/sh

# acme-admin password-reset demo (SPEC-059 R-8, ladder rung 4 of 4).
#
# The story: a bound browser flow with exactly one write-tier interaction —
# the "Confirm reset" click — parking exactly one card, of kind **flow**. This
# is the top of the ladder and the one rung the shipped static target could not
# honestly claim, because a page that echoes its own query parameters reports
# success for a user who does not exist. So the demo's deterministic legs spend
# their effort on the difference: the reset really mutates a store, and the
# confirmation page reports the store rather than the URL.
#
# Deterministic legs (always run, no model involved):
#   1. the flow's preconditions: browser surface on, credential set loaded,
#      both allowlists naming the origin, `web.click` registered write
#   2. the reset route really mutates — and the confirmation page reports the
#      store, not the query string it was handed
#   3. the refusals the skill's Interpretation section names: mismatched
#      passwords, an unknown user, and a signed-out POST
#   4. the one-time value is masked by the gateway and never rendered
#      server-side, and the reset form does not auto-submit
#
# Optional chat leg (RUN_CHAT_LEG=true): a scripted chat asks the agent to reset
# a password through the console. The assertion is **exactly one** card, that it
# is a `flow` card headed by the skill's `flow_intent`, that a second identity
# approves it, and that the store then carries the reset.
#
# Prerequisites: see demo-lib.sh's header.

set -eu

DEMO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
# shellcheck source=../../demo-lib.sh
. "$DEMO_DIR/../../demo-lib.sh"

acme_demo_init "password-reset" 4

SKILL_ID="samples/password-reset-resetacmepassword"
TARGET_USER="${TARGET_USER:-alice}"
NEW_PASSWORD="${NEW_PASSWORD:-TempPass-2026!}"

acme_leg "the flow's preconditions"

require_runtime_config GATEWAY_BROWSER_ENABLED true \
  "deploy with the browser-dev runtime profile"
require_runtime_config GATEWAY_MUTATING_TOOLS_ENABLED true \
  "deploy with the mutating-dev runtime profile, or web.click is not registered"
require_allowlisted GATEWAY_BROWSER_ALLOW_ORIGINS \
  "the browser-dev profile lists the sample app's origin"
require_credential_set
require_tools_registered "web.navigate:read" "web.fill_credential:read" \
  "web.wait_for:read" "web.extract:read" "web.click:write"
require_hitl_enabled

acme_leg "the reset really mutates, and the confirmation reports the store"

app_sign_in

app_post_session /admin/users/reset/ \
  "{\"user\":\"${TARGET_USER}\",\"new_password\":\"${NEW_PASSWORD}\",\"confirm_password\":\"${NEW_PASSWORD}\"}"
[ "$APP_CODE" = "200" ] || fail "the reset POST answered $APP_CODE: $APP_BODY"
printf '%s' "$APP_BODY" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("ok") is True, "ok is %r" % payload.get("ok")
assert payload.get("username") == sys.argv[1], "username is %r" % payload.get("username")
assert payload.get("revision") == 1, "revision is %r, expected 1 after one mutation" % payload.get("revision")
assert payload.get("password_changed_at"), "the reset recorded no password_changed_at"
assert payload.get("redirect", "").startswith("/admin/users/reset/done/"), \
    "redirect is %r" % payload.get("redirect")
print("  ok: the reset mutated the store (revision 1, password_changed_at %s)" % (
    payload.get("password_changed_at")))' "$TARGET_USER" \
  || fail "the reset response did not carry the post-mutation facts: $APP_BODY"

# The cross-check the JSON API gives the browser's claim.
app_http_authed "$ORIGIN/api/users/$TARGET_USER"
printf '%s' "$APP_BODY" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("password_changed_at"), \
    "the API records no password_changed_at for %s" % sys.argv[1]
assert payload.get("revision") == 1, "revision is %r" % payload.get("revision")' \
  "$TARGET_USER" || fail "the API does not corroborate the reset: $APP_BODY"
ok "GET /api/users/$TARGET_USER corroborates the reset (revision 1)"

# The confirmation page must report the store's own record. Asking it about a
# different user than the one just reset is the test: the static target this
# sample replaces echoed its query string and would have claimed success for
# `dave` too. This one must not.
app_http_session "$ORIGIN/admin/users/reset/done/?user=dave&at=whenever"
[ "$APP_CODE" = "200" ] || fail "the confirmation page answered $APP_CODE"
printf '%s' "$APP_BODY" | grep -q "Password for ${TARGET_USER} has been reset successfully." \
  || fail "the confirmation page did not report the store's real reset record"
if printf '%s' "$APP_BODY" | grep -q 'Password for dave'; then
  fail "the confirmation page echoed its query string instead of the store"
fi
ok "the confirmation page reports the store's record (${TARGET_USER}), not the query it was handed (dave)"

app_http_session "$ORIGIN/admin/users/"
printf '%s' "$APP_BODY" | grep -q "id=\"last-reset-user\"> ${TARGET_USER} " \
  || fail "the user list does not surface the last reset from the store"
printf '%s' "$APP_BODY" | grep -q 'id="store-revision">1<' \
  || fail "the user list does not render store revision 1"
ok "the rendered user list carries the last-reset record and store revision 1"

acme_leg "the refusals the skill's Interpretation names"

reseed_demo
app_sign_in

app_post_session /admin/users/reset/ \
  "{\"user\":\"${TARGET_USER}\",\"new_password\":\"${NEW_PASSWORD}\",\"confirm_password\":\"different\"}"
[ "$APP_CODE" = "400" ] || fail "mismatched passwords answered $APP_CODE, expected 400"
printf '%s' "$APP_BODY" | grep -q 'PASSWORD_MISMATCH' \
  || fail "the mismatch refusal did not name PASSWORD_MISMATCH: $APP_BODY"
ok "mismatched confirm field -> 400 PASSWORD_MISMATCH (the form stays usable)"

app_post_session /admin/users/reset/ \
  "{\"user\":\"nobody\",\"new_password\":\"${NEW_PASSWORD}\",\"confirm_password\":\"${NEW_PASSWORD}\"}"
[ "$APP_CODE" = "404" ] || fail "an unknown user answered $APP_CODE, expected 404"
printf '%s' "$APP_BODY" | grep -q 'UNKNOWN_USER' \
  || fail "the unknown-user refusal did not name UNKNOWN_USER: $APP_BODY"
ok "an unknown target -> 404 UNKNOWN_USER (no reset for a similar-looking account)"

# Signed out, the reset POST must be refused rather than silently succeeding —
# a session is authority, not decoration.
ACME_SESSION_COOKIE="luban_session=not-a-real-token"
app_post_session /admin/users/reset/ \
  "{\"user\":\"${TARGET_USER}\",\"new_password\":\"${NEW_PASSWORD}\",\"confirm_password\":\"${NEW_PASSWORD}\"}"
[ "$APP_CODE" = "401" ] || fail "a signed-out reset POST answered $APP_CODE, expected 401"
printf '%s' "$APP_BODY" | grep -q 'SESSION_REQUIRED' \
  || fail "the signed-out refusal did not name SESSION_REQUIRED: $APP_BODY"
ok "a stale or forged session cookie -> 401 SESSION_REQUIRED"

acme_leg "the one-time value is masked, and the form does not auto-submit"

app_sign_in
app_http_session "$ORIGIN/admin/users/reset/?user=${TARGET_USER}&newpw=${NEW_PASSWORD}"
[ "$APP_CODE" = "200" ] || fail "the reset page answered $APP_CODE"
if printf '%s' "$APP_BODY" | grep -q "$NEW_PASSWORD"; then
  fail "the served reset page contains the one-time value; the pre-fill must stay client-side"
fi
printf '%s' "$APP_BODY" | grep -q 'onsubmit="return doReset(event)"' \
  || fail "the reset form is not bound to doReset"
if printf '%s' "$APP_BODY" | grep -q '\.submit()'; then
  fail "the served reset page calls .submit() — the click must stay the flow's single gate"
fi
ok "the served page pre-fills nothing server-side and never submits itself"

# The gateway masks the same value in the URL it projects back, while every
# other byte survives. This is the seam a `web.navigate` result and an evidence
# frame both pass through (SPEC-049 R-5 / SPEC-058 R-2's shared redactor).
ensure_tokens
invoke_tool http.get \
  "{\"url\":\"$ORIGIN/admin/?user=${TARGET_USER}&newpw=${NEW_PASSWORD}\"}" masked-url
[ "$HTTP_CODE" = "200" ] || fail "http.get answered $HTTP_CODE: $GATEWAY_BODY"
printf '%s' "$GATEWAY_BODY" | python3 -c '
import json, sys
secret = sys.argv[1]
user = sys.argv[2]
data = json.load(sys.stdin)["data"]
url = data["url"]
assert secret not in url, "the projected url still carries the one-time value: %r" % url
assert "newpw=***" in url, "the secret parameter was not masked in %r" % url
assert "user=%s" % user in url, "a non-secret parameter was masked too: %r" % url
print("  ok: http.get projected %r" % url)' "$NEW_PASSWORD" "$TARGET_USER" \
  || fail "the gateway did not mask the one-time value in the projected URL"

if [ "${RUN_CHAT_LEG:-}" = "true" ]; then
  echo ""
  echo "==> [CHAT] one write-tier click parks exactly one flow card"

  reseed_demo
  ensure_tokens

  CHAT_SESSION=$(chat_session_new)
  [ -n "$CHAT_SESSION" ] || fail "session creation returned no session_id"

  CHAT_MESSAGE="Reset the acme-admin password for '${TARGET_USER}' through the admin console UI. Use skill ${SKILL_ID}. The new temporary password is '${NEW_PASSWORD}'. Admin credentials are in the ${CREDENTIAL_SET} credential set."

  STREAM_OUTPUT=$(chat_send "$CHAT_SESSION" "$CHAT_MESSAGE")

  require_card_shape "$STREAM_OUTPUT" flow "$WRITE_TIER_WEB_TOOLS"
  [ -n "$CARD_CONFIRM_ID" ] || fail "the parked flow card carried no confirm_id"

  # The card leads with the skill's authored flow_intent (SPEC-053 R-4), inside
  # the flow_summary a bound flow's card carries, so the approver reads what the
  # gated mutation achieves before any DOM detail.
  intent=$(first_card_field "$STREAM_OUTPUT" "flow_summary.flow_intent")
  case "$intent" in
    *"password reset"*) ;;
    *) fail "the flow card carries no flow_intent headline (got '$intent')" ;;
  esac
  ok "the card leads with the authored flow_intent"

  # The one-time value must not survive into the card an approver reads.
  require_no_plaintext_in_cards "$STREAM_OUTPUT" "$NEW_PASSWORD"

  CONFIRM_OUTPUT=$(chat_confirm "$CHAT_SESSION" "$CARD_CONFIRM_ID" approve)
  printf '%s' "$CONFIRM_OUTPUT" | grep -q '"status": *"approved"\|"status":"approved"' \
    || fail "confirmation_result did not report the approval: $CONFIRM_OUTPUT"
  ok "$APPROVER_USER approved the flow card; the click executed and the stream resumed"

  # …nor into the resumed turn's confirmation frames.
  require_no_plaintext_in_cards "$CONFIRM_OUTPUT" "$NEW_PASSWORD"

  # SPEC-049 R-4 / SPEC-051: one gate per flow. The resumed turn must not park
  # a second card, however the model drives the remaining steps.
  cards=$(count_cards "$CONFIRM_OUTPUT")
  [ "$cards" = "0" ] \
    || fail "the resumed turn parked $cards further card(s); a bound flow collapses to one gate"
  require_card_count "$CHAT_SESSION" 1 \
    "one write-tier interaction in a bound flow parks exactly one card"

  # The durable proof: the store moved, and the confirmation page reports it.
  app_http_authed "$ORIGIN/api/users/$TARGET_USER"
  printf '%s' "$APP_BODY" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("password_changed_at"), \
    "no password_changed_at after an approved reset: %r" % payload
assert payload.get("revision", 0) >= 1, \
    "revision is %r; the approved reset did not move it" % payload.get("revision")
print("  ok: %s carries password_changed_at %s at revision %s" % (
    payload.get("username"), payload.get("password_changed_at"), payload.get("revision")))' \
    || fail "the store does not reflect the approved reset: $APP_BODY"
else
  chat_leg_skipped "a scripted console reset asserting exactly one flow card and a tier-2 approval"
fi

acme_demo_summary \
  "the browser and mutating surfaces are both on, the origin is allowlisted, and the credential set resolves" \
  "web.click is registered write while every other step of the flow is read" \
  "the reset route really mutates: revision 1, password_changed_at recorded, corroborated by the JSON API" \
  "the confirmation page reports the store's record and refuses to echo a query string naming a different user" \
  "mismatched passwords, an unknown target and a forged session are refused 400, 404 and 401" \
  "the one-time value is absent from served HTML and masked to *** in the URL the gateway projects back" \
  "the reset form never submits itself, so the operator's click stays the flow's single gate"
