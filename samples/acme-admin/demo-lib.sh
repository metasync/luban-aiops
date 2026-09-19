#!/bin/sh

# Shared plumbing for the acme-admin demo scripts (SPEC-059 R-8).
#
# Sourced, never executed:
#
#     . "$(dirname "$0")/../../demo-lib.sh"
#     acme_demo_init "health-check"
#
# These demos are one suite against one application: they share a reseed step,
# one credential arrangement, one allowlisted origin and a ladder of card counts
# that only means something read together, so the plumbing lives here once. The
# four ladder rungs source it, and so does the migrated adhoc-password-reset
# demo SPEC-060 folded into this category. skill-graduation is the exception —
# its demo is standalone, because it drives an author/graduate/replay flow rather
# than a ladder rung, and carries its own in-cluster app-access helpers.
#
# Every helper follows the house rule the other demos established: an
# assertion that cannot be made deterministically is not made at all, and a
# leg that depends on a model choosing the right tools is opt-in behind
# RUN_CHAT_LEG=true.
#
# In-cluster HTTP runs from the tool-gateway pod (`app_http`), for two
# reasons that both matter: that container already ships curl (it has no
# python3 on PATH, so a `kubectl run` probe would need an image pull *and*
# could not parse JSON in-pod), and it is the exact pod the sample's
# NetworkPolicy admits — so a passing probe also proves the policy.
#
# Prerequisites for every demo in this suite:
#   - kubectl context pointed at the dev cluster
#   - `make deploy` with the browser-dev + mutating-dev runtime profiles
#   - `make deploy-sample-app` (builds, applies and asserts acme-admin)
#   - `make deploy-samples` (packs the four skill documents into the
#     skills-hub `samples` source)
#   - a port-forward for the identity broker (token issuance):
#       kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000
#   - for the chat legs additionally a port-forward for the platform-gateway:
#       kubectl -n dev-luban-aiops port-forward svc/platform-gateway 18083:8000
#
# Environment overrides:
#   NAMESPACE        (default dev-luban-aiops)
#   IDENTITY_URL     (default http://localhost:18081)
#   GATEWAY_URL      (default http://localhost:18083, chat legs)
#   TEST_USER        (default luban-operator)
#   APPROVER_USER    (default luban-approver, chat legs: tier_2 decider)
#   RUN_CHAT_LEG     (unset: deterministic legs only)
#   CROSS_TARGET     (default carol, demo-suite.sh cross-skill leg only)

NAMESPACE="${NAMESPACE:-dev-luban-aiops}"
IDENTITY_URL="${IDENTITY_URL:-http://localhost:18081}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:18083}"
TEST_USER="${TEST_USER:-luban-operator}"
APPROVER_USER="${APPROVER_USER:-luban-approver}"

# The origin both surfaces share: the browser connector's allowlist entry and
# the HTTP connector's are the same string (SPEC-059 R-5), so one demo can
# cross between them. Overridable only so the app-facing helpers can be pointed
# at a locally running acme-admin (see POD_CURL_IMPL below) — the allowlist and
# credential-set legs still need the real in-cluster value.
ORIGIN="${ORIGIN:-http://acme-admin:8080}"
CREDENTIAL_SET="${CREDENTIAL_SET:-acme-admin}"
SECRET_NAME="${SECRET_NAME:-acme-admin-credentials}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
DEMO_RESET_HEADER="X-Luban-Demo-Reset"
RUN_SUFFIX="$(date +%s)-$$"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

ok() {
  echo "  ok: $1"
}

# --- banner -------------------------------------------------------------

# acme_demo_init <sample-name> <total-legs>
#
# Prints the suite banner and resolves the one secret every leg needs. Fails
# loudly, naming the command that fixes it, when the app or its credential has
# not been provisioned — a demo that silently skips its subject proves
# nothing, which is the failure mode ADR-0008 records.
acme_demo_init() {
  ACME_SAMPLE="$1"
  ACME_LEGS="$2"
  ACME_LEG=0

  echo "=============================================================="
  echo " acme-admin demo: $ACME_SAMPLE (SPEC-059)"
  echo " namespace=$NAMESPACE origin=$ORIGIN"
  echo "=============================================================="

  command -v kubectl >/dev/null 2>&1 || fail "kubectl not found on PATH"
  command -v python3 >/dev/null 2>&1 || fail "python3 not found on PATH (used to parse JSON assertions)"

  kubectl -n "$NAMESPACE" get deployment acme-admin >/dev/null 2>&1 \
    || fail "no acme-admin deployment in namespace '$NAMESPACE'; run 'make deploy-sample-app'"

  ACME_ADMIN_PASSWORD=$(kubectl -n "$NAMESPACE" get secret "$SECRET_NAME" \
    -o go-template="{{index .data \"ACME_ADMIN_PASSWORD\" | base64decode}}" 2>/dev/null) \
    || fail "secret '$SECRET_NAME' has no ACME_ADMIN_PASSWORD key"
  [ -n "$ACME_ADMIN_PASSWORD" ] \
    || fail "ACME_ADMIN_PASSWORD is empty; run shared/platform-ops/gitops/sync-browser-credentials.sh"
  # Never echoed. The value reaches the app through a curl config file on
  # stdin (`app_http_authed`), so it never appears in a process listing.
  ok "admin credential resolved from secret/$SECRET_NAME (not printed)"

  reseed_demo
}

# acme_leg <description> — prints the next numbered leg header.
acme_leg() {
  ACME_LEG=$((ACME_LEG + 1))
  echo ""
  echo "==> [$ACME_LEG/$ACME_LEGS] $1"
}

# --- the transport -------------------------------------------------------

# Every app- and gateway-facing call in this suite goes through `pod_curl`, the
# one place a transport is named. It defaults to a `kubectl exec` into the
# tool-gateway container — the pod the sample's NetworkPolicy admits, and one
# that already ships curl (it has no python3 on PATH, so a `kubectl run` probe
# would need an image pull *and* could not parse JSON in-pod).
#
# Overriding POD_CURL_IMPL is how a contributor exercises these legs against a
# locally running acme-admin without a cluster:
#
#     POD_CURL_IMPL=local_curl ORIGIN=http://127.0.0.1:8099 sh demo.sh
#
# where `local_curl() { curl "$@"; }`. Only the app-facing legs survive that
# (the gateway and skills-hub legs still need the cluster), which is why the
# override is a debugging aid and not a supported mode.
POD_CURL_IMPL="${POD_CURL_IMPL:-kubectl_pod_curl}"
BODY_FILE="${BODY_FILE:-/tmp/acme-body}"

kubectl_pod_curl() {
  kubectl -n "$NAMESPACE" exec -i deployment/tool-gateway -c tool-gateway -- curl "$@"
}

kubectl_pod_cat() {
  kubectl -n "$NAMESPACE" exec -i deployment/tool-gateway -c tool-gateway -- cat "$@"
}

pod_curl() {
  "$POD_CURL_IMPL" "$@"
}

pod_cat() {
  "${POD_CAT_IMPL:-kubectl_pod_cat}" "$@"
}

# --- in-cluster HTTP against the app ------------------------------------

# app_http <curl args...>
#
# Sets APP_CODE (the HTTP status) and APP_BODY (the response body). No
# credentials; use app_http_authed for the admin routes.
app_http() {
  APP_CODE=$(pod_curl -sS -o "$BODY_FILE" -w '%{http_code}' "$@" </dev/null) \
    || fail "in-cluster call to the app did not complete: $*"
  APP_BODY=$(pod_cat "$BODY_FILE")
}

# app_http_authed <curl args...> — same, with HTTP Basic from the synced secret.
app_http_authed() {
  APP_CODE=$(printf 'user = "%s:%s"\n' "$ADMIN_USERNAME" "$ACME_ADMIN_PASSWORD" | \
    pod_curl -sS -K - -o "$BODY_FILE" -w '%{http_code}' "$@") \
    || fail "authenticated in-cluster call to the app did not complete: $*"
  APP_BODY=$(pod_cat "$BODY_FILE")
}

# app_http_redirect <curl args...> — an unauthenticated call that also captures
# where a redirect points. A 302's answer lives in its `Location` header and its
# body is empty (`content-length: 0`), so grepping the body for the target — the
# obvious thing to write — always fails on a correctly behaving app. Same header
# dump idiom as app_sign_in below; sets APP_CODE and APP_REDIRECT.
app_http_redirect() {
  raw=$(pod_curl -sS -D - -o /dev/null -w 'HTTPCODE:%{http_code}' "$@" </dev/null) \
    || fail "in-cluster call to the app did not complete: $*"
  APP_CODE=$(printf '%s' "$raw" | sed -n 's/^HTTPCODE://p')
  APP_REDIRECT=$(printf '%s\n' "$raw" | grep -i '^location:' \
    | sed 's/^[Ll]ocation: *//; s/\r$//' | head -n1)
}

# --- the human surface's session -----------------------------------------

# app_sign_in — logs into the console the way the browser skill does (a POST
# to /admin/login with the admin credential) and keeps the session cookie in
# ACME_SESSION_COOKIE.
#
# The password goes into the request body and the cookie comes back in a
# header, and both travel through a curl config file on stdin rather than
# argv: `ps` inside the pod must not be able to read either. The cookie is an
# opaque session token for a throwaway in-memory store, but the habit is the
# point of a tutorial.
#
# `-K -` is what makes curl read that config file; without it curl never looks
# at stdin, the POST goes out with an empty body, and the app answers 422 for a
# missing field — which reads like a bad credential and is not one.
app_sign_in() {
  escaped=$(printf '%s' "$ACME_ADMIN_PASSWORD" | sed 's/\\/\\\\/g; s/"/\\"/g')
  raw=$(printf 'header = "Content-Type: application/json"\ndata = "{\\"username\\":\\"%s\\",\\"password\\":\\"%s\\"}"\n' \
      "$ADMIN_USERNAME" "$escaped" | \
    pod_curl -sS -K - -D - -o "$BODY_FILE" -w 'HTTPCODE:%{http_code}' -X POST "$ORIGIN/admin/login") \
    || fail "POST /admin/login did not complete"
  code=$(printf '%s' "$raw" | sed -n 's/^HTTPCODE://p')
  if [ "$code" != "200" ]; then
    # Name what the app said. A 422 means the body never arrived; a 401 means
    # it did and the credential is wrong — different fixes, same status line
    # otherwise.
    fail "POST /admin/login answered $code with the synced admin credential: $(pod_cat "$BODY_FILE")"
  fi
  ACME_SESSION_COOKIE=$(printf '%s\n' "$raw" | grep -i '^set-cookie:' \
    | sed 's/^[Ss]et-[Cc]ookie: *//; s/;.*$//' | head -n1)
  [ -n "$ACME_SESSION_COOKIE" ] || fail "POST /admin/login set no session cookie"
  ok "signed into the console over the human surface (session cookie held, not printed)"
}

# app_http_session <curl args...> — an in-cluster call carrying that cookie.
app_http_session() {
  APP_CODE=$(printf 'header = "Cookie: %s"\n' "$ACME_SESSION_COOKIE" | \
    pod_curl -sS -K - -o "$BODY_FILE" -w '%{http_code}' "$@") \
    || fail "session in-cluster call to the app did not complete: $*"
  APP_BODY=$(pod_cat "$BODY_FILE")
}

# app_post_session <path> <json-body> — a POST carrying both the cookie and a
# JSON body. The body is escaped for curl's config parser and travels on stdin,
# so no value the demo posts is ever visible in a process listing.
app_post_session() {
  escaped=$(printf '%s' "$2" | sed 's/\\/\\\\/g; s/"/\\"/g')
  APP_CODE=$(printf 'header = "Cookie: %s"\nheader = "Content-Type: application/json"\ndata = "%s"\n' \
      "$ACME_SESSION_COOKIE" "$escaped" | \
    pod_curl -sS -K - -o "$BODY_FILE" -w '%{http_code}' -X POST "$ORIGIN$1") \
    || fail "session POST $1 did not complete"
  APP_BODY=$(pod_cat "$BODY_FILE")
}

# --- the deterministic reseed every demo starts from ---------------------

# reseed_demo
#
# Two assertions in one, because the pair is the point (SPEC-059 R-1):
#   1. a POST *without* the header is refused 403 DEMO_RESET_HEADER_REQUIRED —
#      and `http.post` ships no `headers` parameter at all, so the agent
#      cannot reach this endpoint even though its origin is allowlisted;
#   2. a POST *with* it restores the exact seed.
reseed_demo() {
  app_http -X POST "$ORIGIN/internal/reset-demo"
  [ "$APP_CODE" = "403" ] \
    || fail "headerless POST /internal/reset-demo answered $APP_CODE, expected 403"
  printf '%s' "$APP_BODY" | grep -q 'DEMO_RESET_HEADER_REQUIRED' \
    || fail "headerless reset-demo did not name the missing header: $APP_BODY"

  app_http -X POST -H "$DEMO_RESET_HEADER: 1" "$ORIGIN/internal/reset-demo"
  [ "$APP_CODE" = "200" ] \
    || fail "POST /internal/reset-demo answered $APP_CODE: $APP_BODY"
  printf '%s' "$APP_BODY" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("status") == "reseeded", "status is %r" % payload.get("status")
assert payload.get("store_revision") == payload.get("seed_revision") == 0, \
    "reseed left store_revision=%r seed_revision=%r" % (
        payload.get("store_revision"), payload.get("seed_revision"))
assert payload.get("users_seeded") == 4, "users_seeded is %r" % payload.get("users_seeded")
assert payload.get("users") == ["alice", "bob", "carol", "dave"], \
    "seed users are %r" % payload.get("users")' \
    || fail "reset-demo did not restore the deterministic seed: $APP_BODY"
  ok "store reseeded (revision 0, 4 users); the header gate refuses a headerless POST"
}

# --- runtime configuration ----------------------------------------------

# runtime_config <KEY> — echoes the platform-runtime-config value, empty if unset.
runtime_config() {
  kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
    -o jsonpath="{.data.$1}"
}

# require_runtime_config <KEY> <expected> <fix hint>
require_runtime_config() {
  value=$(runtime_config "$1")
  [ "${value:-}" = "$2" ] \
    || fail "$1 is '${value:-<unset>}', expected '$2' ($3)"
  ok "$1=$2"
}

# require_allowlisted <KEY> <hint> — the shared origin must be listed.
require_allowlisted() {
  value=$(runtime_config "$1")
  case ",$value," in
    *",$ORIGIN,"*) ok "$1 lists $ORIGIN" ;;
    *) fail "$1 does not list $ORIGIN (got '${value:-<empty>}'); $2" ;;
  esac
}

# --- credential sets -----------------------------------------------------

# require_credential_set — the acme-admin entry must be mounted in the
# gateway's credential-set file, with the admin username and a non-empty
# password. Both surfaces resolve it by name: `web.fill_credential` and
# `http.get`/`http.post`'s `credential_set`.
require_credential_set() {
  sets_path=$(runtime_config GATEWAY_BROWSER_CREDENTIAL_SETS)
  [ -n "$sets_path" ] || sets_path="/etc/luban/browser-credentials/credential-sets.json"
  CRED_JSON=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -c tool-gateway -- \
    cat "$sets_path") || fail "could not read $sets_path from the tool-gateway pod"
  printf '%s' "$CRED_JSON" | python3 -c '
import json, sys
name = sys.argv[1]
sets = json.load(sys.stdin)
entry = sets.get(name)
assert isinstance(entry, dict), "credential set %r is missing" % name
assert entry.get("username") == "admin", \
    "%s username is %r, expected admin" % (name, entry.get("username"))
assert entry.get("password"), "%s password is empty" % name' "$CREDENTIAL_SET" \
    || fail "the '$CREDENTIAL_SET' credential set is not loaded correctly (run sync-browser-credentials.sh)"
  ok "credential set '$CREDENTIAL_SET' loaded (username=admin, password present)"
}

# --- tool discovery and direct invocation --------------------------------

# ensure_tokens — issues a dev platform token for the operator and exchanges it
# for a tool-gateway-audience token, plus a platform token for the approver
# identity the chat legs need (SPEC-030 R-4: the requester cannot decide their
# own mutating call).
ensure_tokens() {
  if [ -n "${OPERATOR_TOKEN:-}" ]; then
    return 0
  fi

  clients=$(kubectl -n "$NAMESPACE" get secret identity-service-runtime-secrets \
    -o jsonpath='{.data.IDENTITY_SERVICE_CLIENTS}' | base64 -d)
  client_entry=$(printf '%s' "$clients" | tr ',' '\n' | grep '^platform-gateway:')
  [ -n "$client_entry" ] || fail "platform-gateway client missing from IDENTITY_SERVICE_CLIENTS"
  CLIENT_SECRET=$(printf '%s' "$client_entry" | cut -d: -f2)

  OPERATOR_PLATFORM_TOKEN=$(platform_token "$TEST_USER" operator ops-operators)
  [ -n "$OPERATOR_PLATFORM_TOKEN" ] || fail "broker issued no platform token for $TEST_USER"
  OPERATOR_TOKEN=$(delegate "$OPERATOR_PLATFORM_TOKEN")
  [ -n "$OPERATOR_TOKEN" ] || fail "no delegated tool-gateway token for $TEST_USER"
  APPROVER_PLATFORM_TOKEN=$(platform_token "$APPROVER_USER" approver ops-approvers)
  [ -n "$APPROVER_PLATFORM_TOKEN" ] || fail "broker issued no platform token for $APPROVER_USER"
  ok "tokens issued: $TEST_USER (operator, delegated) and $APPROVER_USER (approver)"
}

platform_token() {
  response=$(curl -fsS --max-time 30 -X POST "$IDENTITY_URL/api/v1/auth/token" \
    -H "Content-Type: application/json" \
    -d "{\"username\": \"$1\", \"email\": \"$1@luban-aiops.local\", \"roles\": [\"$2\"], \"groups\": [\"$3\"]}") \
    || fail "failed to obtain a platform token for $1 (is the identity-service port-forward up?)"
  printf '%s' "$response" | python3 -c '
import json, sys
print(json.load(sys.stdin).get("access_token", ""))'
}

delegate() {
  response=$(curl -fsS --max-time 30 -X POST "$IDENTITY_URL/api/v1/auth/exchange" \
    -u "platform-gateway:$CLIENT_SECRET" \
    -H "Content-Type: application/json" \
    -d "{\"subject_token\": \"$1\", \"audience\": \"tool-gateway\"}") \
    || fail "delegation exchange failed"
  printf '%s' "$response" | python3 -c '
import json, sys
print(json.load(sys.stdin).get("access_token", ""))'
}

# gateway_http <curl args...> — cluster-side call against tool-gateway itself;
# sets HTTP_CODE and GATEWAY_BODY.
gateway_http() {
  HTTP_CODE=$(pod_curl -sS -o "$BODY_FILE" -w '%{http_code}' "$@" </dev/null) \
    || fail "in-cluster gateway call did not complete"
  GATEWAY_BODY=$(pod_cat "$BODY_FILE")
}

# fetch_discovery — echoes the gateway's tool-discovery document. Needs a
# delegated token, so it calls ensure_tokens itself.
#
# ensure_tokens reports on stdout, and stdout here *is* the return value: an
# `ok: tokens issued …` line captured into the document made every caller's
# JSON parse fail with a bare traceback and a misleading "discovery does not
# carry the expected tools" — on the first call in a demo, which is the one made
# before that demo's own ensure_tokens. The transcript line goes to stderr, so
# the caller still sees it and the captured value is exactly the document.
fetch_discovery() {
  ensure_tokens >&2
  pod_curl -fsS -H "Authorization: Bearer $OPERATOR_TOKEN" \
    http://localhost:8000/api/v2/tools </dev/null
}

# require_tools_registered <name:risk> ... — asserts discovery carries each
# named tool at the expected tier. Registration is the gate: a write-tier tool
# that is not registered cannot be called at all, and a read-tier one parks
# nothing.
require_tools_registered() {
  discovery=$(fetch_discovery) || fail "tool discovery failed"
  printf '%s' "$discovery" | python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    document = json.loads(raw)
except ValueError:
    # Name the actual response rather than leaving a traceback: a demo that
    # cannot say what it got sends the operator looking in the wrong place.
    raise SystemExit("tool discovery did not return JSON; first 200 characters: %r" % raw[:200])
tools = {t["name"]: t for t in document}
for spec in sys.argv[1:]:
    name, _, risk = spec.partition(":")
    tool = tools.get(name)
    assert tool is not None, "%s missing from discovery (is its connector enabled?)" % name
    assert tool.get("risk_level") == risk, \
        "%s risk_level is %r, expected %s" % (name, tool.get("risk_level"), risk)
    print("  ok: %s registered with risk_level=%s" % (name, risk))' "$@" \
    || fail "discovery does not carry the expected tools at the expected risk tiers"
}

# invoke_tool <tool_name> <parameters-json> <label>
#
# Calls the gateway's invoke endpoint directly — no model involved — and sets
# HTTP_CODE / GATEWAY_BODY. This is how the demos assert tool-level behaviour
# deterministically: the projection shape, the allowlist refusal, and the
# secret-bearing-URL refusal are all properties of the gateway, not of a
# model's choices.
invoke_tool() {
  gateway_http -X POST http://localhost:8000/api/v2/tools/invoke \
    -H "Authorization: Bearer $OPERATOR_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"$1\",\"parameters\":$2,\"request_id\":\"acme-$3-$RUN_SUFFIX\"}"
}

# json_field <json> <dotted.path>
json_field() {
  printf '%s' "$1" | python3 -c '
import json, sys
value = json.load(sys.stdin)
for key in sys.argv[1].split("."):
    value = value.get(key) if isinstance(value, dict) else None
print(value if value is not None else "")' "$2"
}

# --- skill ingestion -----------------------------------------------------

# require_skill <sample-leaf> <File.md> <grep-pattern> ...
#
# The skills-hub mounts the packed `skills-samples` ConfigMap read-only at
# /skills/samples, one key per document named `<sample-leaf>-<File.md>`.
require_skill() {
  leaf="$1"; file="$2"; shift 2
  mounted="/skills/samples/$leaf-$file"
  body=$(kubectl -n "$NAMESPACE" exec deployment/skills-hub -- cat "$mounted" 2>/dev/null) \
    || fail "skill document $mounted is not in skills-hub (run 'make deploy-samples')"
  for pattern in "$@"; do
    printf '%s' "$body" | grep -q "$pattern" \
      || fail "$leaf-$file does not carry '$pattern'"
  done
  ok "skill $leaf-$file ingested ($*)"
}

# require_no_risk_class <sample-leaf> <File.md>
#
# The read-only half of the ladder is only honest if the frontmatter really
# omits `risk_class`: that omission is what makes the skill park nothing.
require_no_risk_class() {
  leaf="$1"; file="$2"
  body=$(kubectl -n "$NAMESPACE" exec deployment/skills-hub -- \
    cat "/skills/samples/$leaf-$file" 2>/dev/null) \
    || fail "skill document $leaf-$file is not in skills-hub (run 'make deploy-samples')"
  frontmatter=$(printf '%s' "$body" | awk 'NR==1 && $0!="---"{exit} NR>1{if($0=="---") exit; print}')
  # `if`, not `grep -q ... && fail ...`: under `set -e` a failed grep at the
  # head of an `&&` list ends the script, which would invert the assertion.
  if printf '%s' "$frontmatter" | grep -q '^risk_class:'; then
    fail "$leaf-$file declares risk_class; a read-only sample must not"
  fi
  if [ "$leaf" = "health-check" ] && printf '%s' "$frontmatter" | grep -q '^web_target:'; then
    fail "$leaf-$file declares web_target; an http-only skill must not"
  fi
  ok "$leaf-$file declares no risk_class (read-only: parks nothing)"
}

# --- chat legs (opt-in) --------------------------------------------------

# chat_session_new — echoes a fresh session id owned by the operator.
chat_session_new() {
  response=$(curl -fsS --max-time 30 -X POST \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    -H "Content-Type: application/json" -d '{}' \
    "$GATEWAY_URL/api/v1/sessions") || fail "session creation failed"
  printf '%s' "$response" | python3 -c '
import json, sys
print(json.load(sys.stdin).get("session_id", ""))'
}

# chat_send <session_id> <message> — streams one turn and echoes the raw SSE.
chat_send() {
  encoded=$(python3 -c '
import sys, urllib.parse
print(urllib.parse.quote(sys.argv[1]))' "$2")
  curl -fsS --max-time 300 -N \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    "$GATEWAY_URL/api/v1/chat/stream?session_id=$1&message=$encoded" \
    || fail "chat stream request failed"
}

# chat_confirm <session_id> <confirm_id> <decision> — echoes the resume stream.
chat_confirm() {
  curl -fsS --max-time 300 -X POST \
    -H "Authorization: Bearer $APPROVER_PLATFORM_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$1\", \"confirm_id\": \"$2\", \"decision\": \"$3\"}" \
    "$GATEWAY_URL/api/v1/chat/confirm" || fail "the $3 call failed"
}

# count_cards <sse-text> — echoes how many confirmation_request frames it carries.
count_cards() {
  printf '%s' "$1" | python3 -c '
import json, sys
count = 0
for line in sys.stdin:
    line = line.strip()
    if not line.startswith("data:"):
        continue
    try:
        frame = json.loads(line[5:].strip())
    except ValueError:
        continue
    if frame.get("type") == "confirmation_request":
        count += 1
print(count)'
}

# first_card_field <sse-text> <dotted.path> — echoes a field off the first card.
first_card_field() {
  printf '%s' "$1" | python3 -c '
import json, sys
path = sys.argv[1].split(".")
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
    value = frame
    for key in path:
        if isinstance(value, list):
            value = value[int(key)] if len(value) > int(key) else None
        else:
            value = value.get(key) if isinstance(value, dict) else None
    print(value if value is not None else "")
    break' "$2"
}

# require_zero_cards <sse-text> <what it means>
#
# The bottom of the ladder. A read-only turn that parks a card is not a
# read-only turn, so this is a real assertion and not a formality.
require_zero_cards() {
  cards=$(count_cards "$1")
  [ "$cards" = "0" ] \
    || fail "the turn parked $cards confirmation card(s); $2"
  ok "no confirmation card parked ($2)"
}

# require_card_count <session_id> <expected> <what it means>
#
# Counts the *durable* cards on the session, which is the number an operator
# would have had to decide — not the number of frames one curl happened to
# capture before the stream ended.
require_card_count() {
  detail=$(curl -fsS --max-time 30 \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    "$GATEWAY_URL/api/v1/sessions/$1") || fail "session detail fetch failed"
  printf '%s' "$detail" | python3 -c '
import json, sys
expected = int(sys.argv[1])
why = sys.argv[2]
detail = json.load(sys.stdin)
cards = detail.get("confirmations") or []
assert len(cards) == expected, \
    "session carries %d confirmation card(s), expected %d (%s)" % (len(cards), expected, why)
kinds = sorted({(c.get("approval_kind") or "?") for c in cards})
print("  ok: %d card(s) on the session, kind(s) %s (%s)" % (len(cards), ", ".join(kinds), why))' \
    "$2" "$3" || fail "the session's durable card count did not match"
}

# require_card_shape <sse-text> <expected-approval-kind> <expected-tools>
#
# Asserts SPEC-054's discriminator on the parked frame itself: `action` for one
# gated call, `flow` for a bound browser flow — plus that the card names a tool
# an approver is being asked to authorise, at write tier.
#
# <expected-tools> is a comma-separated allowlist, because a flow card should be
# asserted on the *tier* and not on one tool name: the model may drive the same
# gated step with web.click or web.evaluate, and a demo that keys on one of them
# flakes on a correct run. Leaves the frame's confirm_id in CARD_CONFIRM_ID.
require_card_shape() {
  shape_out=$(printf '%s' "$1" | python3 -c '
import json, sys
want_kind = sys.argv[1]
want_tools = [name for name in sys.argv[2].split(",") if name]
frame = None
for line in sys.stdin:
    line = line.strip()
    if not line.startswith("data:"):
        continue
    try:
        candidate = json.loads(line[5:].strip())
    except ValueError:
        continue
    if candidate.get("type") == "confirmation_request":
        frame = candidate
        break
assert frame is not None, "no confirmation_request frame (did the model reach a write-tier call?)"
assert frame.get("approval_kind") == want_kind, \
    "approval_kind is %r, expected %r" % (frame.get("approval_kind"), want_kind)
calls = frame.get("pending_calls") or []
names = sorted({c.get("tool_name", "?") for c in calls})
call = next((c for c in calls if c.get("tool_name") in want_tools), None)
assert call is not None, \
    "no %s pending call on the card (pending: %s)" % (
        "/".join(want_tools), ", ".join(names) or "none")
assert call.get("risk_level") == "write", \
    "%s risk_level is %r, expected write" % (call.get("tool_name"), call.get("risk_level"))
summary = (call.get("change_request") or {}).get("summary") or ""
print("  ok: one %s card on %s (risk_level=write)" % (want_kind, call.get("tool_name")))
if summary:
    print("       change_request.summary: %s" % summary)
print(frame.get("confirm_id", ""))' "$2" "$3") \
    || fail "the parked card did not carry the expected $2/$3 shape"
  # The last line is the confirm_id; everything above it is the assertion's
  # own reporting.
  CARD_CONFIRM_ID=$(printf '%s\n' "$shape_out" | tail -n1)
  printf '%s\n' "$shape_out" | sed '$d'
  [ -n "$CARD_CONFIRM_ID" ] || fail "the parked card carried no confirm_id"
}

# The write-tier browser interactions a bound flow may gate on. Asserted as a
# set, never as one name — see require_card_shape.
WRITE_TIER_WEB_TOOLS="web.click,web.type,web.select,web.press_key,web.upload_file,web.evaluate"

# require_no_plaintext_in_cards <sse-text> <secret>
#
# The card is what a second identity reads in their approvals inbox, so a
# one-time value reaching it is a leak with a named recipient. This asserts the
# frames themselves rather than the whole stream: what the model writes in its
# own reply prose is masked by a different seam (SPEC-049 R-5's transcript and
# live-stream redaction), and conflating the two makes the failure message
# useless.
require_no_plaintext_in_cards() {
  printf '%s' "$1" | python3 -c '
import json, sys
secret = sys.argv[1]
checked = 0
for line in sys.stdin:
    line = line.strip()
    if not line.startswith("data:"):
        continue
    try:
        frame = json.loads(line[5:].strip())
    except ValueError:
        continue
    if frame.get("type") not in ("confirmation_request", "confirmation_result"):
        continue
    checked += 1
    assert secret not in json.dumps(frame), \
        "a confirmation frame carries the one-time value in the clear"
assert checked, "no confirmation frame was checked"
print("  ok: %d confirmation frame(s) carry no plaintext one-time value" % checked)' \
    "$2" || fail "a confirmation frame leaked the one-time value"
}

# require_hitl_enabled — the chat legs cannot run with bridging disabled.
require_hitl_enabled() {
  timeout=$(runtime_config AGENT_HITL_CONFIRM_TIMEOUT)
  [ "${timeout:-600}" != "0" ] \
    || fail "AGENT_HITL_CONFIRM_TIMEOUT=0 disables HITL bridging; the chat leg cannot run"
  ok "HITL bridging active (timeout=${timeout:-600}s)"
}

# chat_leg_skipped <reason>
chat_leg_skipped() {
  echo ""
  echo "==> [CHAT] skipped (RUN_CHAT_LEG unset; opt-in: $1)"
}

# acme_demo_summary <line> ... — the printed proof every demo ends with.
acme_demo_summary() {
  echo ""
  echo "--------------------------------------------------------------"
  echo "acme-admin '$ACME_SAMPLE' demo passed. It proved:"
  for line in "$@"; do
    echo "  - $line"
  done
  echo "--------------------------------------------------------------"
}
