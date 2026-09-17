#!/bin/sh

# acme-admin lock-unlock-user demo (SPEC-059 R-8, ladder rung 3 of 4).
#
# The story: one `http.post`, one confirmation card, of kind **action**. This
# is the rung that makes the card count non-zero, so the demo spends most of
# its deterministic effort on the thing that makes a card *mean* something —
# a target that really distinguishes a mutation from a no-op from a missing
# row. SPEC-058 R-3's `mutation_confirmed` marker is only informative because
# this app answers 200, 409 and 404 separately.
#
# Deterministic legs (always run, no model involved):
#   1. the mutating surface is on: `http.post` registered write, HITL bridging
#      active
#   2. the target distinguishes 200 / 409 / 404 / 401 over curl, and a 409
#      does not bump the revision
#   3. `http.post` projects `mutation_confirmed` true on a 200 and false on a
#      409 — the same call, two honest answers
#   4. the refusals are structural: a non-allowlisted origin never opens a
#      socket, a secret-bearing query is refused outright, and `http.post`'s
#      published schema has **no** `headers` parameter at all
#   5. the skill is ingested, declares `risk_class: write`, and declares no
#      `web_target`
#
# Optional chat leg (RUN_CHAT_LEG=true): a scripted chat asks the agent to lock
# an account. The assertion is **exactly one** card, that it is an `action`
# card naming `http.post` at write tier with a legible `change_request.summary`,
# that a second identity approves it, and that the mutation then really landed.
#
# Prerequisites: see demo-lib.sh's header.

set -eu

DEMO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
# shellcheck source=../../demo-lib.sh
. "$DEMO_DIR/../../demo-lib.sh"

acme_demo_init "lock-unlock-user" 5

SKILL_ID="samples/lock-unlock-user-lockunlockuser"
TARGET_USER="${TARGET_USER:-carol}"
DENIED_ORIGIN="${DENIED_ORIGIN:-http://acme-denied.invalid:8080}"

acme_leg "mutating surface on: http.post registered write"

require_runtime_config GATEWAY_MUTATING_TOOLS_ENABLED true \
  "deploy with the mutating-dev runtime profile"
require_tools_registered "http.post:write" "http.get:read"
require_hitl_enabled

acme_leg "the target distinguishes 200 / 409 / 404 / 401"

# `mutation_confirmed` is a projection of the upstream status, so a target that
# answered 200 for everything would make it a tautology. These are the four
# answers the app really gives.
app_http_authed -X POST "$ORIGIN/api/users/alice/lock"
[ "$APP_CODE" = "200" ] || fail "locking alice answered $APP_CODE: $APP_BODY"
printf '%s' "$APP_BODY" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("action") == "lock", "action is %r" % payload.get("action")
assert payload.get("locked") is True, "locked is %r" % payload.get("locked")
assert payload.get("revision") == 1, "revision is %r, expected 1 after one mutation" % payload.get("revision")
assert payload.get("last_modified"), "the mutation stamped no last_modified"' \
  || fail "the lock response did not carry the post-mutation facts: $APP_BODY"
ok "lock alice -> 200, action=lock, locked=true, revision=1, last_modified stamped"

app_http_authed -X POST "$ORIGIN/api/users/alice/lock"
[ "$APP_CODE" = "409" ] || fail "locking an already-locked user answered $APP_CODE, expected 409"
printf '%s' "$APP_BODY" | grep -q 'NO_OP_MUTATION' \
  || fail "the 409 did not name NO_OP_MUTATION: $APP_BODY"
ok "lock alice again -> 409 NO_OP_MUTATION"

app_http_authed "$ORIGIN/api/users/alice"
printf '%s' "$APP_BODY" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("revision") == 1, \
    "revision is %r; the refused no-op must not have bumped it" % payload.get("revision")' \
  || fail "the 409 moved the revision: $APP_BODY"
ok "the refused no-op left the revision at 1 (it changed nothing)"

app_http_authed -X POST "$ORIGIN/api/users/nobody/lock"
[ "$APP_CODE" = "404" ] || fail "locking an unknown user answered $APP_CODE, expected 404"
printf '%s' "$APP_BODY" | grep -q 'UNKNOWN_USER' \
  || fail "the 404 did not name UNKNOWN_USER: $APP_BODY"
ok "lock nobody -> 404 UNKNOWN_USER"

app_http "$ORIGIN/api/users"
[ "$APP_CODE" = "401" ] || fail "unauthenticated GET /api/users answered $APP_CODE, expected 401"
challenge=$(pod_curl -sS -D - -o /dev/null "$ORIGIN/api/users" </dev/null) \
  || fail "could not read the 401's headers"
printf '%s' "$challenge" | grep -qi 'WWW-Authenticate: Basic realm="acme-admin"' \
  || fail "the 401 carried no Basic challenge naming the acme-admin realm"
ok "unauthenticated -> 401 with WWW-Authenticate: Basic realm=\"acme-admin\""

app_http_authed -X POST "$ORIGIN/api/users/alice/unlock"
[ "$APP_CODE" = "200" ] || fail "unlocking alice answered $APP_CODE: $APP_BODY"
ok "unlock alice -> 200 (the reverse direction is the same call shape)"

acme_leg "http.post projects mutation_confirmed honestly"

# Reseed so this leg's revision arithmetic starts from a known zero. The reseed
# also re-proves the header gate, which is why it is a helper and not a curl.
reseed_demo
ensure_tokens

# A direct invoke of a write-tier tool carries no card: the gate lives in the
# kernel's HITL bridge, not in the gateway, and `operator` holds the
# `tools:mutate` grant. This leg therefore proves the *projection*, and the
# chat leg below proves the *gate*. Conflating the two is how a demo ends up
# claiming an approval it never exercised.

invoke_tool http.post \
  "{\"url\":\"$ORIGIN/api/users/bob/lock\",\"body\":{\"locked\":true},\"credential_set\":\"$CREDENTIAL_SET\"}" \
  lock-bob
[ "$HTTP_CODE" = "200" ] || fail "http.post lock bob answered $HTTP_CODE: $GATEWAY_BODY"
printf '%s' "$GATEWAY_BODY" | python3 -c '
import json, sys
data = json.load(sys.stdin)["data"]
assert data["status"] == 200, "upstream status is %r" % data["status"]
assert data["mutation_confirmed"] is True, \
    "mutation_confirmed is %r on a 200" % data["mutation_confirmed"]
# An untruncated application/json body projects parsed (SPEC-058 R-1).
body = data["body"]
assert isinstance(body, dict), \
    "an untruncated application/json body must project parsed, got %s" % type(body).__name__
assert body["action"] == "lock" and body["locked"] is True, "body is %r" % body
assert body["revision"] == 1, "revision is %r" % body["revision"]
assert "set-cookie" not in {str(k).lower() for k in (data["headers"] or {})}, \
    "the projection leaked a set-cookie header"
print("  ok: http.post 200 -> mutation_confirmed=true, action=lock, revision=1")' \
  || fail "http.post did not project a confirmed mutation: $GATEWAY_BODY"

invoke_tool http.post \
  "{\"url\":\"$ORIGIN/api/users/bob/lock\",\"body\":{\"locked\":true},\"credential_set\":\"$CREDENTIAL_SET\"}" \
  lock-bob-again
[ "$HTTP_CODE" = "200" ] \
  || fail "an upstream 409 is still a successful tool call, got $HTTP_CODE: $GATEWAY_BODY"
printf '%s' "$GATEWAY_BODY" | python3 -c '
import json, sys
data = json.load(sys.stdin)["data"]
assert data["status"] == 409, "upstream status is %r, expected 409" % data["status"]
assert data["mutation_confirmed"] is False, \
    "mutation_confirmed is %r on a 409 — a rejection must not read as a success" % data["mutation_confirmed"]
body = data["body"]
assert isinstance(body, dict), \
    "an untruncated application/json body must project parsed, got %s" % type(body).__name__
assert body.get("error") == "NO_OP_MUTATION", "body is %r" % body
print("  ok: the same http.post repeated -> status 409, mutation_confirmed=false, NO_OP_MUTATION")' \
  || fail "http.post did not report the no-op honestly: $GATEWAY_BODY"

acme_leg "the refusals are structural, not conventional"

ensure_tokens

# A policy denial maps to 403 and a structured tool error to 400, so the two
# refusals below are distinguishable by status as well as by code.
invoke_tool http.post \
  "{\"url\":\"$DENIED_ORIGIN/api/users/bob/lock\",\"body\":{\"locked\":true}}" \
  denied-origin
[ "$HTTP_CODE" = "403" ] || fail "a denied origin answered $HTTP_CODE, expected 403: $GATEWAY_BODY"
printf '%s' "$GATEWAY_BODY" | grep -q 'HTTP_ORIGIN_NOT_ALLOWED' \
  || fail "the denial did not name HTTP_ORIGIN_NOT_ALLOWED: $GATEWAY_BODY"
ok "an origin outside GATEWAY_HTTP_ALLOW_ORIGINS is refused (403) before any socket is opened"

invoke_tool http.post \
  "{\"url\":\"$ORIGIN/api/users/bob/password?newpw=TempPass-2026!\",\"body\":{\"password\":\"TempPass-2026!\"},\"credential_set\":\"$CREDENTIAL_SET\"}" \
  secret-query
[ "$HTTP_CODE" = "400" ] \
  || fail "a secret-bearing query answered $HTTP_CODE, expected 400: $GATEWAY_BODY"
printf '%s' "$GATEWAY_BODY" | grep -q 'HTTP_URL_SECRET_NOT_ALLOWED' \
  || fail "the refusal did not name HTTP_URL_SECRET_NOT_ALLOWED: $GATEWAY_BODY"
ok "http.post refuses a URL carrying a secret-bearing query parameter (400)"

# The credential is a *reference* because the schema offers nothing else. This
# asserts the published contract, not the implementation: there is no `headers`
# parameter for a model to put a literal secret into, so the graduation
# pipeline has no credential hole to fill (SPEC-055 R-4).
discovery=$(fetch_discovery) || fail "tool discovery failed"
printf '%s' "$discovery" | python3 -c '
import json, sys
tools = {t["name"]: t for t in json.load(sys.stdin)}
for name in ("http.get", "http.post"):
    props = (tools[name].get("parameters_schema") or {}).get("properties") or {}
    assert "headers" not in props, "%s publishes a headers parameter" % name
    assert "credential_set" in props, "%s publishes no credential_set" % name
print("  ok: neither verb publishes a headers parameter; both publish credential_set")' \
  || fail "the published http.* schemas are not the ones this sample relies on"

acme_leg "skill ingested, write-class, unbound"

require_skill lock-unlock-user LockUnlockUser.md \
  'title: Lock or Unlock an ACME Admin User Account' \
  'risk_class: write' \
  'http.post'
# The mirror of rung 2's assertion: a mutating skill that never opens a browser
# declares risk_class and no web_target (SPEC-055 R-3 decoupled the two).
body=$(kubectl -n "$NAMESPACE" exec deployment/skills-hub -- \
  cat /skills/samples/lock-unlock-user-LockUnlockUser.md)
if printf '%s' "$body" | grep -q '^web_target:'; then
  fail "LockUnlockUser declares web_target; an http-only mutation must not bind a flow"
fi
ok "LockUnlockUser declares risk_class: write and no web_target"

if [ "${RUN_CHAT_LEG:-}" = "true" ]; then
  echo ""
  echo "==> [CHAT] one http.post parks exactly one action card"

  # A fresh seed, so the post-approval revision check has a known baseline.
  reseed_demo
  ensure_tokens

  CHAT_SESSION=$(chat_session_new)
  [ -n "$CHAT_SESSION" ] || fail "session creation returned no session_id"

  CHAT_MESSAGE="Lock the acme-admin account for '${TARGET_USER}'. Use skill ${SKILL_ID}. The admin credentials are in the ${CREDENTIAL_SET} credential set — do not ask me for a password."

  STREAM_OUTPUT=$(chat_send "$CHAT_SESSION" "$CHAT_MESSAGE")

  # require_card_shape prints its own reporting and leaves the confirm_id in
  # CARD_CONFIRM_ID. It asserts SPEC-054's discriminator: `action`, not `flow`.
  require_card_shape "$STREAM_OUTPUT" action http.post
  [ -n "$CARD_CONFIRM_ID" ] || fail "the parked action card carried no confirm_id"

  # The card must be legible: an approver decides on the origin, the path and
  # the field, not on `url: *** body: ***` (SPEC-058 R-5).
  summary=$(first_card_field "$STREAM_OUTPUT" "pending_calls.0.change_request.summary")
  case "$summary" in
    *acme-admin:8080*) ;;
    *) fail "change_request.summary does not name the origin: '$summary'" ;;
  esac
  case "$summary" in
    *"/api/users/$TARGET_USER/lock"*) ;;
    *) fail "change_request.summary does not name the path: '$summary'" ;;
  esac
  ok "the card's summary names the origin and the path: $summary"

  # SPEC-030 R-4: a second identity decides. The operator cannot approve their
  # own mutating call, so this is not a formality the demo could skip.
  CONFIRM_OUTPUT=$(chat_confirm "$CHAT_SESSION" "$CARD_CONFIRM_ID" approve)
  printf '%s' "$CONFIRM_OUTPUT" | grep -q '"status": *"approved"\|"status":"approved"' \
    || fail "confirmation_result did not report the approval: $CONFIRM_OUTPUT"
  ok "$APPROVER_USER approved the action card; the parked http.post executed"

  require_card_count "$CHAT_SESSION" 1 \
    "one gated call parks exactly one card"

  # The durable proof that the approved call actually ran: the store moved.
  app_http_authed "$ORIGIN/api/users/$TARGET_USER"
  [ "$APP_CODE" = "200" ] || fail "GET /api/users/$TARGET_USER answered $APP_CODE"
  printf '%s' "$APP_BODY" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("locked") is True, \
    "%s is not locked after an approved lock: %r" % (sys.argv[1], payload)
assert payload.get("revision", 0) >= 1, \
    "revision is %r; the approved mutation did not move it" % payload.get("revision")
print("  ok: %s is locked at revision %s (last_modified %s)" % (
    payload.get("username"), payload.get("revision"), payload.get("last_modified")))' \
    "$TARGET_USER" || fail "the store does not reflect the approved mutation: $APP_BODY"
else
  chat_leg_skipped "a scripted lock asserting exactly one action card and a tier-2 approval"
fi

acme_demo_summary \
  "GATEWAY_MUTATING_TOOLS_ENABLED=true and http.post is registered at risk_level=write" \
  "the target answers 200, 409 NO_OP_MUTATION, 404 UNKNOWN_USER and 401 with a Basic challenge separately" \
  "a 409 leaves the revision unmoved, so mutation_confirmed=false is a fact about the store" \
  "http.post projects mutation_confirmed=true on a 200 and false on a 409" \
  "a non-allowlisted origin and a secret-bearing query are both refused before any request is sent" \
  "neither verb publishes a headers parameter, so the credential can only be a reference" \
  "LockUnlockUser declares risk_class: write and no web_target"
