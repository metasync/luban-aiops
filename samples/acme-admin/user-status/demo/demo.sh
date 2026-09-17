#!/bin/sh

# acme-admin user-status demo (SPEC-059 R-8, ladder rung 2 of 4).
#
# The story: a read-only skill over the **browser** surface that still parks
# **zero** cards, even though it signs into a console and reads a rendered
# table. That is the rung the ladder exists to show — a browser flow is not
# mutating just because it is a browser flow. Signing in here costs no click:
# the console auto-submits its login form once both fields are filled, so the
# flow's interactions are all read tier.
#
# Deterministic legs (always run, no model involved):
#   1. the browser surface is enabled, the origin is allowlisted, the
#      credential set is loaded, and the tools this skill uses are registered
#      read (with web.click registered write, to show the tier line is real)
#   2. the human surface really renders: six routes, a signed-out
#      `/admin/users/` redirecting to `/admin/`, and a signed-in table with
#      four rows whose Status cell reads `active` at revision 0
#   3. the element-id contract the skill's selectors address is present in the
#      served HTML — the ids a `web.snapshot` ref and a `web.extract` selector
#      both depend on
#   4. the skill is ingested, declares `web_target`, and declares no
#      `risk_class`
#
# Optional chat leg (RUN_CHAT_LEG=true): a scripted chat asks the agent to read
# a user's status from the console. The assertion is zero confirmation cards
# and at least one `web.extract`.
#
# Prerequisites: see demo-lib.sh's header.

set -eu

DEMO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
# shellcheck source=../../demo-lib.sh
. "$DEMO_DIR/../../demo-lib.sh"

acme_demo_init "user-status" 4

SKILL_ID="samples/user-status-checkuserstatus"
TARGET_USER="${TARGET_USER:-alice}"

acme_leg "browser surface enabled, origin allowlisted, credential set loaded"

require_runtime_config GATEWAY_BROWSER_ENABLED true \
  "deploy with the browser-dev runtime profile"
require_allowlisted GATEWAY_BROWSER_ALLOW_ORIGINS \
  "the browser-dev profile lists the sample app's origin for the browser surface too"
require_credential_set
# The tier line this rung sits on: every tool CheckUserStatus uses is read, and
# the one write-tier interaction it deliberately avoids (clicking "Sign in") is
# registered write. If web.click were read, "zero cards" would prove nothing.
require_tools_registered \
  "web.navigate:read" "web.snapshot:read" "web.fill_credential:read" \
  "web.wait_for:read" "web.extract:read" "web.screenshot:read" \
  "web.click:write"

acme_leg "the human surface renders real state"

# All six routes answer, with the trailing-slash shapes R-2 requires.
for path in / /status /admin/ /admin/users/ /admin/users/reset/ /admin/users/reset/done/; do
  app_http "$ORIGIN$path"
  case "$APP_CODE" in
    200|302|307) ;;
    *) fail "GET $path answered $APP_CODE" ;;
  esac
done
ok "all six routes answer (200, or a redirect where the page requires a session)"

app_http "$ORIGIN/admin/"
[ "$APP_CODE" = "200" ] || fail "GET /admin/ answered $APP_CODE"
for element in admin-login-form admin-username admin-password admin-sign-in admin-login-status; do
  printf '%s' "$APP_BODY" | grep -q "id=\"$element\"" \
    || fail "the login page carries no id=\"$element\""
done
ok "the login page carries the ids the skill fills and waits on"

# Signed out, the user list must redirect — this is the failure the skill's
# Interpretation section names, so the demo proves it is a redirect and not a
# 200 with an empty table (which would let a skill report "no users"). The
# target is in the `Location` header and not in the body: a 302 carries
# `content-length: 0`, so grepping the body would fail against a correct app.
app_http_redirect "$ORIGIN/admin/users/"
[ "$APP_CODE" = "302" ] || fail "GET /admin/users/ signed out answered $APP_CODE, expected 302"
[ "$APP_REDIRECT" = "/admin/" ] \
  || fail "the signed-out redirect points at ${APP_REDIRECT:-<no Location header>}, expected /admin/"
ok "signed out, /admin/users/ redirects 302 to $APP_REDIRECT"

app_sign_in
app_http_session "$ORIGIN/admin/users/"
[ "$APP_CODE" = "200" ] || fail "GET /admin/users/ signed in answered $APP_CODE"
printf '%s' "$APP_BODY" | python3 -c '
import re, sys
html = sys.stdin.read()
rows = re.findall(
    r"<tr id=\"user-row-([a-z]+)\"[^>]*data-locked=\"(true|false)\"(.*?)</tr>",
    html, re.S)
assert len(rows) == 4, "the user table rendered %d rows, expected 4" % len(rows)
for username, locked, body in rows:
    status = re.search(r"<td class=\"user-status\">([^<]*)</td>", body)
    revision = re.search(r"<td class=\"user-revision\">([^<]*)</td>", body)
    assert status and revision, "row %s lacks a status or revision cell" % username
    expected = "locked" if locked == "true" else "active"
    assert status.group(1) == expected, \
        "row %s Status reads %r but data-locked is %s" % (username, status.group(1), locked)
    assert revision.group(1) == "0", \
        "row %s Revision reads %r; the demo reseeds first, so 0 is expected" % (
            username, revision.group(1))
print("  ok: the rendered table carries 4 rows, each Status agreeing with data-locked, all at revision 0")' \
  || fail "the rendered user table did not match the seeded store"

acme_leg "the element-id contract the skill's selectors address"

# `web.extract` takes a CSS selector and `web.snapshot` hands back refs into
# these same elements, so a template edit that renames one silently breaks a
# shipped skill. The app's own test suite walks every page for its id set;
# this leg asserts the contract from the *outside*, over HTTP, against the
# deployed image.
for element in user-table last-reset-status no-resets store-revision; do
  printf '%s' "$APP_BODY" | grep -q "id=\"$element\"" \
    || fail "the user list carries no id=\"$element\""
done
for username in alice bob carol dave; do
  printf '%s' "$APP_BODY" | grep -q "id=\"user-row-$username\"" \
    || fail "the user list carries no id=\"user-row-$username\""
done
ok "user-table, the four user-row-* ids and the revision/reset elements are all served"

app_http_session "$ORIGIN/admin/users/reset/?user=${TARGET_USER}&newpw=TempPass-2026!"
[ "$APP_CODE" = "200" ] || fail "GET /admin/users/reset/ signed in answered $APP_CODE"
for element in target-user reset-form new-password confirm-password confirm-reset reset-status; do
  printf '%s' "$APP_BODY" | grep -q "id=\"$element\"" \
    || fail "the reset page carries no id=\"$element\""
done
# The one-time value is pre-filled client-side, so it must NOT appear in the
# served HTML: a `web.snapshot` of this page cannot leak it. (`if`, not
# `grep -q ... && fail`: under `set -e` a failed grep at the head of an `&&`
# list would end the script, inverting the assertion.)
if printf '%s' "$APP_BODY" | grep -q 'TempPass-2026!'; then
  fail "the served reset page contains the newpw value; the pre-fill must stay client-side"
fi
ok "the reset page serves its ids and never renders the one-time value server-side"

acme_leg "skill ingested, bound to a target, read-only by declaration"

require_skill user-status CheckUserStatus.md \
  'title: Check ACME Admin User Account Status' \
  "web_target: $ORIGIN/admin/" \
  'web.extract'
require_no_risk_class user-status CheckUserStatus.md

if [ "${RUN_CHAT_LEG:-}" = "true" ]; then
  echo ""
  echo "==> [CHAT] a signed-in browser read parks zero cards"

  require_hitl_enabled
  ensure_tokens

  CHAT_SESSION=$(chat_session_new)
  [ -n "$CHAT_SESSION" ] || fail "session creation returned no session_id"

  CHAT_MESSAGE="Read the current status of the acme-admin user '${TARGET_USER}' from the admin console and tell me whether the account is active or locked, plus its revision. Use skill ${SKILL_ID}. Admin credentials are in the ${CREDENTIAL_SET} credential set."

  STREAM_OUTPUT=$(chat_send "$CHAT_SESSION" "$CHAT_MESSAGE")
  require_zero_cards "$STREAM_OUTPUT" \
    "signing in and reading a table are read-tier, so a bound flow here parks nothing"

  printf '%s' "$STREAM_OUTPUT" | grep -q '"tool_name": *"web.extract"\|"tool_name":"web.extract"' \
    || fail "the turn never called web.extract — it cannot have read the rendered table"
  ok "the turn read the rendered table with web.extract"

  require_card_count "$CHAT_SESSION" 0 \
    "a read-only browser flow leaves no durable card either"
else
  chat_leg_skipped "a scripted console read asserting zero confirmation cards"
fi

acme_demo_summary \
  "GATEWAY_BROWSER_ENABLED=true and $ORIGIN is on GATEWAY_BROWSER_ALLOW_ORIGINS" \
  "the '$CREDENTIAL_SET' credential set is loaded, so web.fill_credential can resolve it by name" \
  "every tool CheckUserStatus uses is registered read, and web.click is registered write" \
  "all six routes answer; signed out /admin/users/ redirects 302 to /admin/" \
  "signed in, the rendered table carries four rows whose Status cells agree with data-locked at revision 0" \
  "the element-id contract is served from the deployed image, and the one-time newpw value never appears in served HTML" \
  "CheckUserStatus declares web_target and no risk_class — a bound browser flow that parks nothing"
