#!/bin/sh

# acme-admin health-check demo (SPEC-059 R-8, ladder rung 1 of 4).
#
# The story: a read-only skill over the HTTP service-check surface that parks
# **zero** confirmation cards. This is the repository's first genuinely
# card-free sample, so the demo's job is to prove the two things that make
# "zero cards" a fact rather than an accident — the tool is registered at
# `risk_level: read`, and the skill document declares no `risk_class`.
#
# Deterministic legs (always run, no model involved):
#   1. the HTTP surface is enabled, the origin is allowlisted, `http.get` is
#      registered read
#   2. `/healthz` answers in-cluster with all eight keys and the seeded state
#   3. the same reads through `http.get` itself: the fixed projection shape,
#      a bounded header set, the `/api/hello` echo, and a name outside the
#      bounded pattern arriving as a *successful tool result* carrying 422
#   4. the skill is ingested and declares neither `risk_class` nor `web_target`
#
# Optional chat leg (RUN_CHAT_LEG=true): a scripted chat asks the agent to
# check the service's health. The assertion is that the turn parks **no**
# confirmation_request frame — the bottom of the ladder.
#
# Prerequisites: see demo-lib.sh's header. In short: `make deploy`,
# `make deploy-sample-app`, `make deploy-samples`, and an identity-service
# port-forward on 18081 (plus platform-gateway on 18083 for the chat leg).

set -eu

DEMO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
# shellcheck source=../../demo-lib.sh
. "$DEMO_DIR/../../demo-lib.sh"

acme_demo_init "health-check" 4

SKILL_ID="samples/health-check-checkservicehealth"

acme_leg "HTTP surface enabled, origin allowlisted, http.get registered read"

require_runtime_config GATEWAY_HTTP_ENABLED true \
  "deploy with the browser-dev runtime profile, which sets it for the sample suite"
require_allowlisted GATEWAY_HTTP_ALLOW_ORIGINS \
  "the browser-dev profile lists the sample app's origin"
require_tools_registered "http.get:read"

acme_leg "/healthz in-cluster: eight keys and the seeded state"

app_http "$ORIGIN/healthz"
[ "$APP_CODE" = "200" ] || fail "GET /healthz answered $APP_CODE: $APP_BODY"
printf '%s' "$APP_BODY" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
required = ("status", "service", "version", "hostname", "uptime_seconds",
            "started_at", "users_seeded", "store_revision")
missing = [key for key in required if key not in payload]
assert not missing, "health payload is missing %s" % ", ".join(missing)
assert payload["status"] == "ok", "status is %r" % payload["status"]
assert payload["service"] == "acme-admin", "service is %r" % payload["service"]
assert isinstance(payload["uptime_seconds"], (int, float)), \
    "uptime_seconds is %r, not a number" % payload["uptime_seconds"]
assert payload["users_seeded"] == 4, "users_seeded is %r" % payload["users_seeded"]
assert payload["store_revision"] == 0, \
    "store_revision is %r; the demo reseeds first, so 0 is expected" % payload["store_revision"]
print("  ok: /healthz carries all eight keys (service=%s version=%s hostname=%s)" % (
    payload["service"], payload["version"], payload["hostname"]))' \
  || fail "GET /healthz did not carry the asserted payload: $APP_BODY"

acme_leg "the same reads through http.get: projection, headers, echo, 422"

ensure_tokens

invoke_tool http.get "{\"url\":\"$ORIGIN/healthz\"}" health
[ "$HTTP_CODE" = "200" ] || fail "http.get /healthz answered $HTTP_CODE: $GATEWAY_BODY"
printf '%s' "$GATEWAY_BODY" | python3 -c '
import json, sys
data = json.load(sys.stdin)["data"]
# The projection is a fixed key set (SPEC-058 R-1): a skill can rely on it
# without parsing prose, and nothing outside it can leak.
required = {"url", "status", "elapsed_ms", "headers", "content_type",
            "content_length", "truncated", "body"}
missing = required - set(data)
assert not missing, "projection is missing %s" % ", ".join(sorted(missing))
assert data["status"] == 200, "upstream status is %r" % data["status"]
assert data["truncated"] is False, "a health payload must not be truncated"
assert data["content_type"].startswith("application/json"), \
    "content_type is %r" % data["content_type"]
assert isinstance(data["elapsed_ms"], (int, float)), \
    "elapsed_ms is %r, not a number" % data["elapsed_ms"]
# The header set is allowlisted, and the two that would carry a secret or a
# session must never appear.
names = {str(k).lower() for k in (data["headers"] or {})}
for forbidden in ("set-cookie", "authorization"):
    assert forbidden not in names, "projection leaked a %s header" % forbidden
# SPEC-058 R-1 projects an untruncated application/json body *parsed*, so a
# skill reads fields rather than re-decoding a string; a truncated or
# unparseable one falls back to honest text. Assert which shape arrived.
body = data["body"]
assert isinstance(body, dict), \
    "an untruncated application/json body must project parsed, got %s" % type(body).__name__
assert body["store_revision"] == 0 and body["users_seeded"] == 4, \
    "the body http.get returned is not the seeded health payload: %r" % body
print("  ok: http.get projected status=%s content_type=%s elapsed_ms=%s" % (
    data["status"], data["content_type"], data["elapsed_ms"]))
print("       headers projected: %s" % ", ".join(sorted(names)))' \
  || fail "http.get /healthz did not project the expected shape: $GATEWAY_BODY"

invoke_tool http.get "{\"url\":\"$ORIGIN/api/hello?name=luban\"}" hello
[ "$HTTP_CODE" = "200" ] || fail "http.get /api/hello answered $HTTP_CODE: $GATEWAY_BODY"
printf '%s' "$GATEWAY_BODY" | python3 -c '
import json, sys
data = json.load(sys.stdin)["data"]
assert data["status"] == 200, "upstream status is %r" % data["status"]
assert isinstance(data["body"], dict), \
    "an untruncated application/json body must project parsed, got %s" % type(data["body"]).__name__
message = data["body"].get("message")
assert message == "hello, luban!", "message is %r" % message
# The URL is projected back with its secret query masked and every other byte
# intact — here there is no secret, so it must survive verbatim.
assert data["url"].endswith("/api/hello?name=luban"), "projected url is %r" % data["url"]
print("  ok: /api/hello?name=luban echoed %r through http.get" % message)' \
  || fail "http.get /api/hello did not echo as expected: $GATEWAY_BODY"

# A name outside `^[A-Za-z0-9 _.-]{1,64}$` is refused by the app with 422.
# The point of asserting it here is *how* it arrives: an upstream 4xx is a
# successful tool result carrying that status, not a tool error. A skill that
# treated it as a failure would report the app as down.
invoke_tool http.get "{\"url\":\"$ORIGIN/api/hello?name=not%2Fallowed\"}" hello-refused
[ "$HTTP_CODE" = "200" ] \
  || fail "an upstream 422 should still answer 200 at the tool layer, got $HTTP_CODE: $GATEWAY_BODY"
printf '%s' "$GATEWAY_BODY" | python3 -c '
import json, sys
data = json.load(sys.stdin)["data"]
assert data["status"] == 422, "upstream status is %r, expected 422" % data["status"]
assert data["truncated"] is False, "a 422 body must not be truncated"
print("  ok: a name outside the bounded pattern arrived as a tool result with status 422")' \
  || fail "the bounded-name refusal did not arrive as expected: $GATEWAY_BODY"

acme_leg "skill ingested, read-only by declaration"

require_skill health-check CheckServiceHealth.md \
  'title: Check ACME Admin Service Health' \
  'http.get'
require_no_risk_class health-check CheckServiceHealth.md

if [ "${RUN_CHAT_LEG:-}" = "true" ]; then
  echo ""
  echo "==> [CHAT] a read-only turn parks zero cards"

  require_hitl_enabled
  ensure_tokens

  CHAT_SESSION=$(chat_session_new)
  [ -n "$CHAT_SESSION" ] || fail "session creation returned no session_id"

  CHAT_MESSAGE="Check the health of the acme-admin service and tell me what you found. Use skill ${SKILL_ID}. No credentials are needed for the health endpoint."

  STREAM_OUTPUT=$(chat_send "$CHAT_SESSION" "$CHAT_MESSAGE")
  require_zero_cards "$STREAM_OUTPUT" \
    "a read-only http.get turn must park nothing"

  printf '%s' "$STREAM_OUTPUT" | grep -q '"tool_name": *"http.get"\|"tool_name":"http.get"' \
    || fail "the turn never called http.get — did it pick the right skill?"
  ok "the turn called http.get"

  require_card_count "$CHAT_SESSION" 0 \
    "a read-only turn leaves no durable card either"
else
  chat_leg_skipped "a scripted health check asserting zero confirmation cards"
fi

acme_demo_summary \
  "GATEWAY_HTTP_ENABLED=true and $ORIGIN is on GATEWAY_HTTP_ALLOW_ORIGINS" \
  "http.get is registered at risk_level=read, so it cannot park a card" \
  "/healthz carries all eight keys and the reseeded state (revision 0, 4 users)" \
  "http.get projects a fixed key set with an allowlisted header set (no set-cookie, no authorization)" \
  "/api/hello echoes its argument, and a name outside the bounded pattern arrives as a tool result carrying 422" \
  "CheckServiceHealth declares no risk_class and no web_target — read-only by declaration as well as by tier"
