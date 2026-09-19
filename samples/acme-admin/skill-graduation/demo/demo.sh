#!/bin/sh

# Skill-graduation tutorial demo (SPEC-055 develop-as-you-go sample).
#
# Deterministic end-to-end assertions for the develop-as-you-go graduation
# path, runnable after `make deploy` and `make deploy-samples`.
#
# This sample ships NO skill document, and that is the point: the skill is
# the artifact the demo produces. It walks the whole SPEC-055 story on the
# same acme-admin console the other two browser samples use —
#
#   ACT 1  author    an operator works ad hoc against a DECLARED target with
#                    no skill bound, so every write parks its own per-action
#                    card (SPEC-054 R-2) and each approved, signed mutation is
#                    captured into the session's authoring trace (R-2)
#   ACT 2  graduate  the trace is re-validated against the declared target and
#                    rendered into an executable-flow draft (R-4) — no model
#                    call, no step nobody approved
#   ACT 3  merge     a human merges the draft into the team's skills repo; the
#                    demo does the mechanical half (install into the `samples`
#                    source) and asserts the ingested skill carries the v2
#                    `kind` + `steps` columns (R-3)
#   ACT 4  replay    the graduated flow binds and the SAME mutations now cost
#                    ONE gate instead of N (R-5 / SPEC-051)
#
# The contrast between act 1 and act 4 is the whole value proposition: N
# approvals to do the work the first time, one approval every time after.
#
# SPEC-060 moved this sample off the static browser-check-target mock onto the
# stateful acme-admin app, so acts 1 and 4 now end by proving the resets they
# drove actually landed in the store (`/api/users/{alice,bob}` password_changed_at
# + a revision that moves again between the two acts) rather than pointing at a
# page that only echoes its own query string. The store is reseeded to a known
# baseline before act 1 so that proof starts from revision 0.
#
# Deterministic legs (always run, no model and no cluster mutation beyond
# two throwaway sessions):
#   1. browser connector enabled, HITL bridging active, SPEC-055 knobs sane
#   2. acme-admin console pages served by the acme-admin app
#   3. acme-admin credential set loaded on the tool-gateway
#   4. fifteen web.* tools in discovery with correct risk tiers
#   5. a declared target is first-wins, is reported as the scope in force
#      rather than echoed, and is stripped of any query, fragment or
#      embedded credential before it is stored
#   6. graduation posture: an observer is denied both routes, and a session
#      with no captured mutation is refused rather than exported
#
# Optional chat legs (RUN_CHAT_LEG=true) run acts 1-4. They depend on the
# model choosing the right tools, so they are opt-in like the other demos'
# chat legs; the live dev-k8s exercise of them rides the spec's Delivery
# Gate browser live check (ADR-0008).
#
# Prerequisites:
#   - kubectl context pointed at the dev cluster
#   - `make deploy` completed (browser connector enabled) and
#     `make deploy-sample-app` completed (the acme-admin app the acts drive),
#     with the acme-admin credential set synced
#   - `make deploy-samples` completed (creates the `skills-samples`
#     ConfigMap act 3 merges into; this sample contributes no file to it)
#   - a port-forward for the identity broker (token issuance):
#       kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000
#   - a port-forward for the platform-gateway:
#       kubectl -n dev-luban-aiops port-forward svc/platform-gateway 18083:8000
#     Unlike the other two acme-admin browser samples, this one is NOT
#     chat-leg-only: legs 5 and 6 declare targets and attempt graduations over
#     the gateway, so the deterministic run needs it too.
#
# Environment overrides:
#   NAMESPACE             (default dev-luban-aiops)
#   IDENTITY_URL          (default http://localhost:18081)
#   GATEWAY_URL           (default http://localhost:18083; legs 5-6 and acts
#                          1-4, i.e. every leg that is not a kubectl exec)
#   TEST_USER             (default luban-operator)
#   APPROVER_USER         (default luban-approver, chat leg decider)
#   OBSERVER_USER         (default luban-observer, leg 6 denial)
#   TARGET_USER_A         (default alice)
#   TARGET_USER_B         (default bob)
#   NEW_PASSWORD          (default TempPass-2026!)
#   SESSION_TITLE         (default "Batch Password Reset (Graduation Demo)")
#   KEEP_GRADUATED_SKILL  (default empty: act 3's install is removed again on
#                          exit; set to true to leave it in the cluster)

set -eu

NAMESPACE="${NAMESPACE:-dev-luban-aiops}"
IDENTITY_URL="${IDENTITY_URL:-http://localhost:18081}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:18083}"
TEST_USER="${TEST_USER:-luban-operator}"
APPROVER_USER="${APPROVER_USER:-luban-approver}"
OBSERVER_USER="${OBSERVER_USER:-luban-observer}"
TARGET_USER_A="${TARGET_USER_A:-alice}"
TARGET_USER_B="${TARGET_USER_B:-bob}"
NEW_PASSWORD="${NEW_PASSWORD:-TempPass-2026!}"
SESSION_TITLE="${SESSION_TITLE:-Batch Password Reset (Graduation Demo)}"

# The sample's leaf name is also the ConfigMap key prefix act 3 merges under,
# matching deploy-samples.sh's `<sample-leaf>-<file>.md` convention.
SAMPLE_LEAF="skill-graduation"
# The develop-as-you-go target: declared up front, before anything is
# captured, so it is an authorization scope and not a post-hoc claim.
ADMIN_TARGET="http://acme-admin:8080/admin/"
# The same app's in-cluster origin, used by the store-verification legs the
# SPEC-060 move adds. `APP_ORIGIN/admin/` is ADMIN_TARGET; the split keeps the
# declared scope a literal (it is asserted verbatim against the graduated
# web_target) while the verification legs build /api and /internal paths off
# APP_ORIGIN. The store reads are HTTP-Basic authed with the synced admin
# credential, resolved lazily in the chat leg and never printed.
APP_ORIGIN="http://acme-admin:8080"
APP_CREDENTIAL_SECRET="acme-admin-credentials"
CONFIGMAP="skills-samples"

WORK=$(mktemp -d)
BODY_FILE="$WORK/body"
SCRATCH_SESSIONS=""
GRADUATED_KEY=""
# Set in leg 4; the trap can fire before it, and under `set -u` an unbound
# expansion inside the cleanup would mask the failure that triggered it.
OPERATOR_PLATFORM_TOKEN=""

cleanup() {
  # Act 3's install is a demo artifact, not a shipped skill: leaving a
  # write-class executable flow in the cluster after a demo would outlive the
  # run that produced it and be indistinguishable from a merged one.
  if [ -n "$GRADUATED_KEY" ] && [ "${KEEP_GRADUATED_SKILL:-}" != "true" ]; then
    echo "==> [CLEANUP] removing the graduated skill ($GRADUATED_KEY) from '$CONFIGMAP'"
    if kubectl -n "$NAMESPACE" patch configmap "$CONFIGMAP" --type=merge \
        -p "{\"data\":{\"$GRADUATED_KEY\":null}}" >/dev/null 2>&1; then
      kubectl -n "$NAMESPACE" rollout restart "deployment/skills-hub" >/dev/null 2>&1 || true
      kubectl -n "$NAMESPACE" rollout status "deployment/skills-hub" --timeout=180s \
        >/dev/null 2>&1 || true
      echo "graduated skill removed; skills-hub re-ingested without it"
    else
      echo "WARNING: could not remove '$GRADUATED_KEY' from '$CONFIGMAP'; remove it with:" >&2
      echo "  kubectl -n $NAMESPACE patch configmap $CONFIGMAP --type=merge -p '{\"data\":{\"$GRADUATED_KEY\":null}}'" >&2
    fi
  fi
  # The two throwaway sessions legs 5 and 6 create teach nothing once the
  # legs have passed; the authoring and replay sessions are deliberately kept
  # so an operator can read them in the portal.
  if [ -n "$OPERATOR_PLATFORM_TOKEN" ]; then
    for sid in $SCRATCH_SESSIONS; do
      curl -s --max-time 15 -o /dev/null -X DELETE \
        -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
        "$GATEWAY_URL/api/v1/sessions/$sid" 2>/dev/null || true
    done
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

json_field() {
  printf '%s' "$1" | python3 -c "
import json, sys
payload = json.load(sys.stdin)
value = payload
for key in sys.argv[1].split('.'):
    if isinstance(value, dict):
        value = value.get(key)
    elif isinstance(value, list):
        try:
            value = value[int(key)]
        except (ValueError, IndexError):
            value = None
    else:
        value = None
print(value if value is not None else '')" "$2"
}

# HTTP call that keeps the status in $HTTP_CODE and the body in $HTTP_BODY.
# No -f: legs 5 and 6 assert on 403 and 409 bodies, which are the answer
# rather than a failure to get one. But curl's OWN exit status is guarded,
# because a transport failure (nothing listening, DNS, --max-time) is not an
# answer at all — under `set -e` the bare assignment would abort the script
# with no message, right after a leg header, and the likeliest cause is the
# one this sample newly has: legs 5-6 need the gateway port-forward that the
# two sibling demos only need for their chat legs. The message names the
# remedy and never $@ — the arguments carry a live bearer token.
http() {
  HTTP_CODE=$(curl -s --max-time 60 -o "$BODY_FILE" -w "%{http_code}" "$@") \
    || fail "curl could not reach the platform-gateway at $GATEWAY_URL — is 'port-forward svc/platform-gateway 18083:8000' still up? (legs 5-6 and acts 1-4 all need it, not just the chat legs)"
  HTTP_BODY=$(cat "$BODY_FILE")
}

# --- in-cluster app access (SPEC-060 store verification) -----------------
#
# The acts drive resets through the browser; these helpers read the same store
# back over the app's JSON API to prove the mutations landed. They mirror
# deploy.sh's transport exactly: `kubectl exec` into the real tool-gateway
# container (which ships curl and is the pod the app's NetworkPolicy admits)
# and talk to the app over in-cluster DNS. The acme-admin image is a minimal
# uv/python runtime with no curl, so probing from inside it is not an option.
# The admin password crosses on stdin as a curl config file, never in argv, so
# it is not visible in a process listing on either side of the exec.
APP_ADMIN_PASSWORD=""

# app_probe <curl args...> — an unauthenticated in-cluster call; echoes
# "<body>\n<http_code>".
app_probe() {
  kubectl -n "$NAMESPACE" exec -i deployment/tool-gateway -c tool-gateway -- \
    curl -sS -w '\n%{http_code}' "$@" </dev/null
}

# app_probe_authed <path> — an HTTP-Basic GET against the app's JSON API.
app_probe_authed() {
  [ -n "$APP_ADMIN_PASSWORD" ] \
    || fail "the admin credential was not resolved before an authed app read"
  printf 'user = "admin:%s"\n' "$APP_ADMIN_PASSWORD" | \
    kubectl -n "$NAMESPACE" exec -i deployment/tool-gateway -c tool-gateway -- \
    curl -sS -K - -w '\n%{http_code}' "$APP_ORIGIN$1"
}

app_resolve_admin_password() {
  APP_ADMIN_PASSWORD=$(kubectl -n "$NAMESPACE" get secret "$APP_CREDENTIAL_SECRET" \
    -o go-template='{{index .data "ACME_ADMIN_PASSWORD" | base64decode}}' 2>/dev/null) \
    || fail "secret '$APP_CREDENTIAL_SECRET' has no ACME_ADMIN_PASSWORD key"
  [ -n "$APP_ADMIN_PASSWORD" ] \
    || fail "ACME_ADMIN_PASSWORD is empty; run shared/platform-ops/gitops/sync-browser-credentials.sh"
}

# app_sign_in — log into the console over the human surface the way the browser
# skill does, keeping the opaque session cookie in APP_SESSION_COOKIE. The
# password travels in a curl config on stdin, never in argv.
APP_SESSION_COOKIE=""
app_sign_in() {
  escaped=$(printf '%s' "$APP_ADMIN_PASSWORD" | sed 's/\\/\\\\/g; s/"/\\"/g')
  raw=$(printf 'header = "Content-Type: application/json"\ndata = "{\\"username\\":\\"admin\\",\\"password\\":\\"%s\\"}"\n' "$escaped" | \
    kubectl -n "$NAMESPACE" exec -i deployment/tool-gateway -c tool-gateway -- \
    curl -sS -K - -D - -o /dev/null -w 'HTTPCODE:%{http_code}' -X POST "$APP_ORIGIN/admin/login")
  code=$(printf '%s' "$raw" | sed -n 's/^HTTPCODE://p')
  [ "$code" = "200" ] \
    || fail "POST /admin/login answered $code with the synced admin credential"
  APP_SESSION_COOKIE=$(printf '%s\n' "$raw" | grep -i '^set-cookie:' \
    | sed 's/^[Ss]et-[Cc]ookie: *//; s/;.*$//' | head -n1)
  [ -n "$APP_SESSION_COOKIE" ] || fail "POST /admin/login set no session cookie"
}

# app_probe_session <path> — a GET carrying the console session cookie, for the
# session-gated admin pages; echoes "<body>\n<http_code>".
app_probe_session() {
  printf 'header = "Cookie: %s"\n' "$APP_SESSION_COOKIE" | \
    kubectl -n "$NAMESPACE" exec -i deployment/tool-gateway -c tool-gateway -- \
    curl -sS -K - -w '\n%{http_code}' "$APP_ORIGIN$1"
}

# app_reseed — restore the deterministic seed (revision 0) so act 1 starts from
# a known baseline. Header-gated: `http.post` ships no headers parameter, so the
# agent cannot reach this endpoint even though its origin is allowlisted.
app_reseed() {
  raw=$(app_probe -X POST -H "X-Luban-Demo-Reset: 1" "$APP_ORIGIN/internal/reset-demo")
  code=$(printf '%s' "$raw" | tail -n1)
  body=$(printf '%s' "$raw" | sed '$d')
  [ "$code" = "200" ] || fail "POST /internal/reset-demo answered $code: $body"
  printf '%s' "$body" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("status") == "reseeded", "status is %r" % payload.get("status")
assert payload.get("store_revision") == payload.get("seed_revision") == 0, \
    "reseed left store_revision=%r seed_revision=%r" % (
        payload.get("store_revision"), payload.get("seed_revision"))' \
    || fail "reset-demo did not restore the deterministic seed: $body"
  echo "store reseeded to revision 0 before act 1 (a known baseline for the store proof)"
}

# app_store_revision — echoes the whole-store revision, so act 4 can prove it
# moved again on top of act 1's resets.
app_store_revision() {
  raw=$(app_probe_authed "/api/users")
  code=$(printf '%s' "$raw" | tail -n1)
  body=$(printf '%s' "$raw" | sed '$d')
  [ "$code" = "200" ] || fail "GET /api/users answered $code: $body"
  printf '%s' "$body" | python3 -c '
import json, sys
print(json.load(sys.stdin).get("store_revision", ""))'
}

# app_verify_both_resets <label> — both target users must carry a recorded
# password_changed_at and a bumped revision, proving the resets landed in the
# store and not merely on a page that echoes its own query string.
app_verify_both_resets() {
  label="$1"
  for u in "$TARGET_USER_A" "$TARGET_USER_B"; do
    raw=$(app_probe_authed "/api/users/$u")
    code=$(printf '%s' "$raw" | tail -n1)
    body=$(printf '%s' "$raw" | sed '$d')
    [ "$code" = "200" ] || fail "$label: GET /api/users/$u answered $code: $body"
    printf '%s' "$body" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("password_changed_at"), \
    "no password_changed_at recorded for %s" % payload.get("username")
assert payload.get("revision", 0) >= 1, \
    "revision is %r for %s; the approved reset did not move it" % (
        payload.get("revision"), payload.get("username"))
print("  ok: %s carries password_changed_at %s at revision %s" % (
    payload.get("username"), payload.get("password_changed_at"), payload.get("revision")))' \
      || fail "$label: the store does not reflect the reset for $u"
  done
}

echo "==> [1/6] prerequisites: browser connector, HITL bridging, SPEC-055 knobs"

BROWSER_ENABLED=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o jsonpath='{.data.GATEWAY_BROWSER_ENABLED}')
[ "${BROWSER_ENABLED:-}" = "true" ] \
  || fail "GATEWAY_BROWSER_ENABLED is not true ($BROWSER_ENABLED); run 'make deploy' with the browser-dev profile"
echo "browser connector enabled"

HITL_TIMEOUT=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o jsonpath='{.data.AGENT_HITL_CONFIRM_TIMEOUT}')
[ "${HITL_TIMEOUT:-600}" != "0" ] \
  || fail "AGENT_HITL_CONFIRM_TIMEOUT=0 disables HITL bridging; the chat legs cannot run"
echo "HITL bridging active (timeout=${HITL_TIMEOUT:-600}s)"

# The three SPEC-055 knobs plus the SPEC-051 replay budget they have to agree
# with, read out of the deployed ConfigMap. Each falls back to its own code
# default when the profile leaves it unset — and dev-k8s leaves all four unset
# today (`GATEWAY_BROWSER_FLOW_MAX_STEPS` sits commented out in
# tool-gateway/runtime-config.env) — so what this leg actually earns is the
# *relationship* check below and a nonsense-value check, not the numbers: a
# runtime profile that raised the graduation budget above the replay budget, or
# zeroed the trace cap, would fail acts 1-4 in a way that reads as a model
# problem rather than a configuration one.
kubectl -n "$NAMESPACE" get configmap platform-runtime-config -o json \
  | python3 -c "
import json, sys
data = json.load(sys.stdin).get('data') or {}
def knob(name, default, floor):
    raw = data.get(name)
    value = default if raw in (None, '') else int(raw)
    assert value >= floor, '%s is %d, must be >= %d' % (name, value, floor)
    return value
# Defaults are the code's own (runtime_settings.RuntimeSettings and
# tool-gateway core/config.DEFAULT_BROWSER_FLOW_MAX_STEPS), so an unset knob
# is reported as the value the services will actually use.
trace_cap = knob('AGENT_AUTHORING_TRACE_MAX_STEPS', 100, 1)
idle_days = knob('AGENT_AUTHORING_TRACE_IDLE_DAYS', 180, 0)
budget = knob('AGENT_SKILL_GRADUATION_MAX_STEPS', 20, 1)
replay = knob('GATEWAY_BROWSER_FLOW_MAX_STEPS', 20, 1)
# The two budgets are deliberate twins: a graduation bound above the replay
# budget exports a flow that would die part-way through mutating.
assert budget <= replay, (
    'AGENT_SKILL_GRADUATION_MAX_STEPS (%d) exceeds GATEWAY_BROWSER_FLOW_MAX_STEPS (%d): '
    'graduation would export a flow the gateway refuses part-way through' % (budget, replay))
print('  trace cap=%d, idle GC=%dd, graduation budget=%d, replay budget=%d'
      % (trace_cap, idle_days, budget, replay))" \
  || fail "the SPEC-055 authoring-trace / graduation knobs are not set sanely"
echo "authoring-trace capture and graduation budget configured"

echo "==> [2/6] acme-admin console pages served"

# Probed from inside the tool-gateway pod (which ships curl and is the pod the
# app's NetworkPolicy admits), not the acme-admin pod — its minimal uv/python
# image has no curl. Same transport deploy.sh and demo-lib.sh use.
kubectl -n "$NAMESPACE" exec -i deployment/tool-gateway -c tool-gateway -- \
  curl -fsS "$APP_ORIGIN/admin/" | grep -q 'ACME Admin Console' \
  || fail "acme-admin console login page not served"
echo "console login page served at /admin/"

# Unlike the static mock this sample replaced, the console gates the user list
# and the reset form behind a session (302 to /admin/ when signed out). Sign in
# over the human surface first — exactly what the browser skill does — then
# probe them with the cookie, so "served" means served to an authenticated admin.
app_resolve_admin_password
app_sign_in
app_probe_session "/admin/users/" | sed '$d' | grep -q 'User Management' \
  || fail "admin user list page not served to a signed-in session"
echo "admin user list served at /admin/users/ (session-gated)"

app_probe_session "/admin/users/reset/?user=test" | sed '$d' | grep -q 'Reset Password' \
  || fail "admin reset page not served to a signed-in session"
echo "admin reset form served at /admin/users/reset/ (session-gated)"

echo "==> [3/6] acme-admin credential set loaded"

CRED_JSON=$(kubectl -n "$NAMESPACE" exec deployment/tool-gateway -- \
  cat /etc/luban/browser-credentials/credential-sets.json)
printf '%s' "$CRED_JSON" | python3 -c "
import json, sys
sets = json.load(sys.stdin)
assert 'acme-admin' in sets, 'acme-admin credential set missing'
assert sets['acme-admin'].get('username') == 'admin', \
    'acme-admin username is %r, expected admin' % sets['acme-admin'].get('username')
assert sets['acme-admin'].get('password'), 'acme-admin password is empty'" \
  || fail "acme-admin credential set not loaded correctly"
echo "acme-admin credential set loaded (username=admin, password present)"

echo "==> [4/6] fifteen web.* tools with correct risk tiers"

# Dev platform tokens from the identity broker.
CLIENTS=$(kubectl -n "$NAMESPACE" get secret identity-service-runtime-secrets \
  -o jsonpath='{.data.IDENTITY_SERVICE_CLIENTS}' | base64 -d)
CLIENT_ENTRY=$(printf '%s' "$CLIENTS" | tr ',' '\n' | grep '^platform-gateway:')
[ -n "$CLIENT_ENTRY" ] || fail "platform-gateway client missing from IDENTITY_SERVICE_CLIENTS"
CLIENT_SECRET=$(printf '%s' "$CLIENT_ENTRY" | cut -d: -f2)

platform_token() {
  TOKEN_RESPONSE=$(
    curl -fsS --max-time 30 -X POST "$IDENTITY_URL/api/v1/auth/token" \
      -H "Content-Type: application/json" \
      -d "{\"username\": \"$1\", \"email\": \"$1@luban-aiops.local\", \"roles\": [\"$2\"], \"groups\": [\"$3\"]}"
  ) || fail "failed to obtain a platform token for $1"
  printf '%s' "$TOKEN_RESPONSE" | python3 -c "
import json, sys
print(json.load(sys.stdin).get('access_token', ''))"
}

delegate() {
  EXCHANGE_RESPONSE=$(
    curl -fsS --max-time 30 -X POST "$IDENTITY_URL/api/v1/auth/exchange" \
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

echo "==> [5/6] a declared target is first-wins, reported in force, and scoped"

# A develop-as-you-go session names its target when it opens, before anything
# can have been captured. That ordering is what makes the declaration an
# authorization scope rather than a claim fitted to a trace afterwards, and
# graduation reports it back as `declaration: preceded`.
http -X POST "$GATEWAY_URL/api/v1/sessions" \
  -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"skill_target\": \"$ADMIN_TARGET\"}"
[ "$HTTP_CODE" = "200" ] || fail "session create with a skill_target answered $HTTP_CODE: $HTTP_BODY"
DECLARE_SESSION=$(json_field "$HTTP_BODY" session_id)
[ -n "$DECLARE_SESSION" ] || fail "session create returned no session_id"
SCRATCH_SESSIONS="$SCRATCH_SESSIONS $DECLARE_SESSION"
echo "session opened as a develop-as-you-go one against $ADMIN_TARGET"

# A later, different target cannot move the scope: were it movable, the
# declaration would corroborate nothing, because a session that drifted could
# always be re-scoped to wherever it ended up.
http -X POST "$GATEWAY_URL/api/v1/sessions/$DECLARE_SESSION/skill-target" \
  -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target": "http://elsewhere.example/admin/"}'
[ "$HTTP_CODE" = "200" ] || fail "skill-target re-declaration answered $HTTP_CODE: $HTTP_BODY"
printf '%s' "$HTTP_BODY" | ADMIN_TARGET="$ADMIN_TARGET" python3 -c "
import json, os, sys
body = json.load(sys.stdin)
assert body.get('already_declared') is True, \
    'a second, different target did not report already_declared, got %r' % (body.get('already_declared'),)
assert body.get('target') == os.environ['ADMIN_TARGET'], \
    'the scope moved: in force is %r, expected the first declaration %r' % (
        body.get('target'), os.environ['ADMIN_TARGET'])" \
  || fail "first-wins declaration did not hold"
echo "a different target cannot move the scope (first-wins); the response reports the scope in force"

# Re-declaring the SAME scope reads as success: an operator confirming a
# target they already set is not told they were too late.
http -X POST "$GATEWAY_URL/api/v1/sessions/$DECLARE_SESSION/skill-target" \
  -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"target\": \"$ADMIN_TARGET\"}"
[ "$HTTP_CODE" = "200" ] || fail "same-scope re-declaration answered $HTTP_CODE: $HTTP_BODY"
[ "$(json_field "$HTTP_BODY" already_declared)" = "False" ] \
  || fail "re-declaring the same scope reported already_declared=$(json_field "$HTTP_BODY" already_declared), expected False"
echo "re-declaring the same scope reads as success, not as a missed deadline"

# An address-bar paste is scoped before it is stored: the query and fragment
# are inert at replay, and the userinfo is where a pasted URL carries a
# credential — into a table that outlives every receipt.
PASTED="http://admin:Sup3rSecret@acme-admin:8080/admin/?token=abc123#top"
http -X POST "$GATEWAY_URL/api/v1/sessions" \
  -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"skill_target\": \"$PASTED\"}"
[ "$HTTP_CODE" = "200" ] || fail "session create with a pasted target answered $HTTP_CODE: $HTTP_BODY"
PASTE_SESSION=$(json_field "$HTTP_BODY" session_id)
[ -n "$PASTE_SESSION" ] || fail "pasted-target session create returned no session_id"
SCRATCH_SESSIONS="$SCRATCH_SESSIONS $PASTE_SESSION"
http -X POST "$GATEWAY_URL/api/v1/sessions/$PASTE_SESSION/skill-target" \
  -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target": "http://elsewhere.example/admin/"}'
[ "$HTTP_CODE" = "200" ] || fail "pasted-target read-back answered $HTTP_CODE: $HTTP_BODY"
printf '%s' "$HTTP_BODY" | PASTED="$PASTED" python3 -c "
import json, os, sys
from urllib.parse import urlparse, urlunparse
body = json.load(sys.stdin)
stored = body.get('target') or ''
# The expected scope is re-derived HERE from the pasted address bar instead of
# being compared against ADMIN_TARGET. skill_target_scope keeps scheme, host,
# port and path and drops the userinfo, the query and the fragment, so deriving
# it independently makes the equality an actual proof of the strip; comparing
# against a constant this script also declared would pass on a plain echo and
# prove nothing. That is also why the toxic fragments are not asserted again in
# a loop below — they cannot survive an equality that has already held, and
# naming them twice would read as coverage it is not. They are visible in the
# PASTED literal above, which is where a reader needs them.
pasted = urlparse(os.environ['PASTED'])
expected = urlunparse(pasted._replace(
    netloc=pasted.netloc.rpartition('@')[2], query='', fragment=''))
assert stored == expected, (
    'the stored target is %r, expected the scope %r derived from the pasted '
    'address bar with its userinfo, query and fragment dropped' % (stored, expected))" \
  || fail "a pasted address bar was not scoped down to origin + path"
echo "an address-bar paste is stored as origin + path only (no query, no fragment, no embedded credential)"

echo "==> [6/6] graduation posture: observer denied, an empty trace refused"

OBSERVER_PLATFORM_TOKEN=$(platform_token "$OBSERVER_USER" read-only-observer ops-observers)
[ -n "$OBSERVER_PLATFORM_TOKEN" ] || fail "broker issued no platform token for $OBSERVER_USER"

# session:skill_graduate is a higher trust level than session:skill_draft —
# the artifact declares risk_class: write and a machine-readable replay list —
# so it is separately authorized, and denied to a read-only observer.
http -X POST "$GATEWAY_URL/api/v1/sessions/$DECLARE_SESSION/skill-graduate" \
  -H "Authorization: Bearer $OBSERVER_PLATFORM_TOKEN"
[ "$HTTP_CODE" = "403" ] || fail "observer graduation answered $HTTP_CODE, expected 403"
printf '%s' "$HTTP_BODY" | grep -qi 'denied' \
  || fail "observer graduation was not a policy denial: $HTTP_BODY"
echo "observer denied graduation (no session:skill_graduate grant)"

# The MID-SESSION declare route is part of graduating, not a second
# capability, so it rides the same action and is denied to the same roles.
# Declaring at *birth* (leg 5's `skill_target` on POST /sessions) does not: it
# rides session:create, so any authenticated role may scope their own session
# while only graduating it stays gated. The asymmetry is deliberate — scoping
# your own session authorizes nothing — and it is why this leg tests the
# mid-session route rather than the birth one. The body has to parse for the
# denial to be the answer under test: the request model is resolved before the
# handler runs, so a malformed call would report 422 and never reach policy.
http -X POST "$GATEWAY_URL/api/v1/sessions/$DECLARE_SESSION/skill-target" \
  -H "Authorization: Bearer $OBSERVER_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target": "http://elsewhere.example/admin/"}'
[ "$HTTP_CODE" = "403" ] || fail "observer declaration answered $HTTP_CODE, expected 403"
echo "observer denied target declaration (the same action gates both halves)"

# Nothing to graduate: a flow can only be built from mutating steps a human
# approved while the session ran, so an untouched session is refused rather
# than exported as an empty or synthesized flow. A 503 here instead means the
# agent layer cannot reach skills-hub to validate a draft.
http -X POST "$GATEWAY_URL/api/v1/sessions/$DECLARE_SESSION/skill-graduate" \
  -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN"
[ "$HTTP_CODE" = "409" ] \
  || fail "graduating a session with no captured trace answered $HTTP_CODE, expected 409 (503 would mean skills-hub validation is not configured): $HTTP_BODY"
printf '%s' "$HTTP_BODY" | grep -q 'no captured authoring trace' \
  || fail "the refusal did not name the missing-trace guard: $HTTP_BODY"
echo "a session with no captured mutation is refused, naming the guard"

if [ "${RUN_CHAT_LEG:-}" = "true" ]; then
  echo ""
  echo "==> [ACT 1] author: an ad-hoc batch reset against the declared target"

  # Reseed to a known baseline (revision 0) so the store proof at the end of
  # acts 1 and 4 starts from zero. APP_ADMIN_PASSWORD was already resolved in
  # leg 2; the reseed drops that console session, which is fine — the browser
  # logs in fresh during act 1.
  app_reseed

  APPROVER_PLATFORM_TOKEN=$(platform_token "$APPROVER_USER" approver ops-approvers)
  [ -n "$APPROVER_PLATFORM_TOKEN" ] \
    || fail "broker issued no platform token for $APPROVER_USER"

  http -X POST "$GATEWAY_URL/api/v1/sessions" \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"skill_target\": \"$ADMIN_TARGET\"}"
  [ "$HTTP_CODE" = "200" ] || fail "authoring session create answered $HTTP_CODE: $HTTP_BODY"
  AUTHOR_SESSION=$(json_field "$HTTP_BODY" session_id)
  [ -n "$AUTHOR_SESSION" ] || fail "authoring session create returned no session_id"
  echo "authoring session $AUTHOR_SESSION opened against $ADMIN_TARGET"

  # The title is what the graduated skill is named for, so the demo sets it
  # rather than letting the renderer fall back to "<origin> executable flow".
  http -X PATCH "$GATEWAY_URL/api/v1/sessions/$AUTHOR_SESSION/title" \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"title\": \"$SESSION_TITLE\"}"
  [ "$HTTP_CODE" = "200" ] || fail "session title update answered $HTTP_CODE: $HTTP_BODY"

  # No skill exists yet, so nothing can bind: every write parks its own
  # per-action card. web.type and web.evaluate are excluded on purpose —
  # their value arguments are withheld at capture by name, and a withheld
  # value is an unresolved credential hole that graduation refuses. The
  # reset form pre-fills from the URL, so the only writes are the two
  # 'Confirm reset' clicks — web.fill_credential is read tier, parks no
  # card and never enters the trace, so a credential fill is not a write
  # here even though it touches the page.
  #
  # The prompt must NOT ask the model to click 'Sign in', and that is not
  # stylistic. The target's login page carries a legacy-SSO auto-login timer
  # that fires within 100ms of BOTH credential fields holding a value: it
  # hides the form and navigates to /admin/users/. So a click on that button
  # after two web.fill_credential calls cannot land — the dev-k8s live check
  # of this gate failed with exactly that, `ElementHandle.click: Element is
  # not attached to the DOM`, on the first write of the session. The model
  # recovered (snapshot, re-navigate) and completed both resets, but the
  # failed write stayed in the trace with no observed origin, and R-4
  # refuses to graduate a step whose landing is unverified — correctly, since
  # fabricating an origin would corroborate a mutation that never happened
  # and dropping it would graduate a flow the operator never approved.
  #
  # Both sibling demos already leave that click out — password-reset and
  # adhoc-password-reset were each reconciled to gate on 'Confirm reset' with
  # the login kept read-tier — so this prompt is catching up to a posture the
  # repo already holds, not inventing one. It costs more here than there: the
  # siblings assert a signature, which a failed write still carries, and
  # neither reads the authoring trace, so a click that missed would pass them
  # silently, while act 2 refuses the whole session over it. Act 1's prompt
  # therefore names the mechanism rather than leaving act 2's refusal — which
  # reads as "nothing proves the mutation landed on the declared target" — to
  # be mistaken for a problem with the target declaration.
  AUTHOR_MESSAGE="Working ad hoc in the acme-admin console, reset the password for BOTH '${TARGET_USER_A}' and '${TARGET_USER_B}' to '${NEW_PASSWORD}'. There is no skill for this yet: do NOT pass skill_id to web.navigate, so this session stays UNBOUND and each write parks its own per-action card. Navigate to ${ADMIN_TARGET} and fill BOTH admin credentials with web.fill_credential from the acme-admin credential set — never web.type. Do NOT click the 'Sign in' button: that page's legacy-SSO auto-login submits itself as soon as both fields are filled and replaces the form, so the click would land on a detached element and fail, and a failed write makes this session un-graduable. After the credentials are in, let the page redirect to the user list on its own. Then, for each of the two users, navigate to /admin/users/reset/ with the user and newpw query parameters so the form pre-fills, snapshot, and click the 'Confirm reset' button. Do not use web.type or web.evaluate at all: a typed value is withheld at capture and would make this session un-graduable."

  STREAM=$(curl -fsS --max-time 300 -N \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    "$GATEWAY_URL/api/v1/chat/stream?session_id=$AUTHOR_SESSION&message=$(python3 -c "
import urllib.parse, sys
print(urllib.parse.quote(sys.argv[1]))" "$AUTHOR_MESSAGE")") \
    || fail "authoring chat stream request failed"

  # Approve every per-action card the unbound writes park, in a bounded loop.
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
    assert kind == 'action', \
        'authoring card approval_kind is %r, expected action — nothing is bound yet, so a flow card means the model bound a skill' % (kind,)
    assert not frame.get('flow_summary'), \
        'an authoring card must carry no flow_summary, got %r' % (frame.get('flow_summary'),)
    calls = frame.get('pending_calls') or []
    assert calls, 'authoring card has no pending_calls'
    found_cr = False
    for c in calls:
        cr = c.get('change_request')
        if isinstance(cr, dict) and isinstance(cr.get('summary'), str) and cr.get('summary'):
            found_cr = True
    assert found_cr, 'no pending_call carries a change_request projection'
    print(frame.get('confirm_id', ''))
    break
") || fail "an authoring card is not a per-action change-request card (SPEC-054 R-2 is the authoring posture)"
    [ -n "$CONFIRM_ID" ] || fail "authoring confirmation_request frame carried no confirm_id"
    CARDS=$((CARDS+1))
    echo "  card ${CARDS}: per-action change-request card parked (confirm_id=${CONFIRM_ID}); approving"

    STREAM=$(curl -fsS --max-time 300 -X POST \
      -H "Authorization: Bearer $APPROVER_PLATFORM_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"session_id\": \"$AUTHOR_SESSION\", \"confirm_id\": \"$CONFIRM_ID\", \"decision\": \"approve\"}" \
      "$GATEWAY_URL/api/v1/chat/confirm") || fail "approver approve call failed for authoring card ${CARDS}"
    printf '%s' "$STREAM" | grep -q '"status": *"approved"\|"status":"approved"' \
      || fail "confirmation_result did not report the approval for authoring card ${CARDS}"
  done

  [ "$CARDS" -ge 1 ] \
    || fail "no per-action card parked while authoring (did the model reach an unbound write-tier interaction?)"
  if printf '%s' "$STREAM" | grep -q '"type": *"confirmation_request"\|"type":"confirmation_request"'; then
    fail "more than 8 per-action cards parked while authoring; aborting the bounded approve loop"
  fi
  echo "authored the batch reset behind ${CARDS} per-action card(s), each approved on its own merits"

  # The trace is what graduation reads, so count the durable truth rather
  # than the frames: every approved, signed, write-tier execution is one
  # captured step, and act 2 asserts the two numbers agree exactly.
  http "$GATEWAY_URL/api/v1/sessions/$AUTHOR_SESSION" \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN"
  [ "$HTTP_CODE" = "200" ] || fail "authoring session detail answered $HTTP_CODE: $HTTP_BODY"
  WRITES=$(printf '%s' "$HTTP_BODY" | python3 -c "
import json, sys
detail = json.load(sys.stdin)
assert detail.get('pending_confirmation') is not True, \
    'the authoring session still parks a confirmation after the approve loop completed'
WRITE_TIER = {'web.click', 'web.type', 'web.select', 'web.press_key', 'web.upload_file', 'web.evaluate'}
cards = detail.get('confirmations') or []
assert cards, 'the authoring session persisted no confirmation card'
signed = 0
for idx, card in enumerate(cards):
    assert card.get('approval_kind') == 'action', \
        'durable authoring card %d approval_kind is %r, expected action' % (idx, card.get('approval_kind'))
    assert card.get('status') == 'approved', \
        'durable authoring card %d status is %r, expected approved' % (idx, card.get('status'))
    executions = card.get('executions') or []
    assert executions, 'durable approved authoring card %d carries no execution rows' % idx
    for row in executions:
        assert row.get('tool_name') in WRITE_TIER, \
            'execution row names %r, expected a write-tier web.* tool' % row.get('tool_name')
        # Success, not merely a receipt: a failed or timed-out write is still
        # signed, so the signature check alone would count it — but the kernel
        # records a trace step's observed origin ONLY on a succeeded result, so
        # a failed click leaves that step unverified and act 2 refuses the whole
        # draft with a message about the declared target's origin. Asserting it
        # here names the real cause at the act that produced it.
        assert row.get('status') == 'succeeded', \
            'execution %r did not succeed (status %r) — its trace step carries no observed origin, so act 2 would refuse it as unverified' % (
                row.get('tool_name'), row.get('status'))
        assert row.get('receipt', {}).get('signature'), \
            'execution %r carries no signed receipt' % row.get('tool_name')
        signed += 1
print(signed)") || fail "the authoring session detail lacks approved cards with signed write-tier executions"
  [ "$WRITES" -ge 1 ] || fail "no signed write-tier execution was captured while authoring"
  echo "the authoring session durably holds ${WRITES} succeeded, signed write-tier execution(s)"

  # SPEC-060: prove act 1's approved resets actually landed in the store, and
  # remember the revision so act 4 can show it moved again. This is the fact the
  # static mock could never supply — a page that echoed its own query string
  # proved nothing about state.
  app_verify_both_resets "act 1"
  REV_AFTER_AUTHOR=$(app_store_revision)
  [ -n "$REV_AFTER_AUTHOR" ] || fail "act 1: could not read the store revision after authoring"
  echo "act 1 landed both resets in the store (store revision now ${REV_AFTER_AUTHOR})"

  echo ""
  echo "==> [ACT 2] graduate: the trace becomes an executable-flow draft"

  http -X POST "$GATEWAY_URL/api/v1/sessions/$AUTHOR_SESSION/skill-graduate" \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN"
  [ "$HTTP_CODE" = "200" ] \
    || fail "graduation answered $HTTP_CODE: $HTTP_BODY"
  printf '%s' "$HTTP_BODY" \
    | ADMIN_TARGET="$ADMIN_TARGET" EXPECT_STEPS="$WRITES" SESSION="$AUTHOR_SESSION" \
      NEW_PASSWORD="$NEW_PASSWORD" OUT="$WORK/graduated.md" python3 -c "
import json, os, sys
body = json.load(sys.stdin)

# No model was involved: the draft renders what the session actually did.
assert body.get('mode') == 'graduated', 'mode is %r, expected graduated' % (body.get('mode'),)
assert body.get('validation') == 'passed', \
    'validation is %r, expected passed (skills-hub ingestion accepts the draft as rendered)' % (body.get('validation'),)

# Exactly the approved mutations, no more and no fewer: a step nobody signed
# would be an execution nobody authorized, and a missing one would replay an
# incomplete flow.
#
# The two counts come from different best-effort seams — the trace step is
# appended at the SIGNING seam before the call runs, the execution row is
# closed by the receipt after it — and each swallows its own store failure so
# it can never block the mutation. So this equality assumes both writes landed.
# If it ever fails with the counts off by one, that is a degraded platform
# store rather than a graduation bug, and the message below is accurate about
# which side holds which number.
steps = body.get('step_count')
expected = int(os.environ['EXPECT_STEPS'])
assert steps == expected, \
    'the draft carries %s step(s) but the session holds %d succeeded, signed write-tier execution(s)' % (steps, expected)

# The binding a replay will be held to is the scope declared before the first
# capture, and the draft says which side of it the declaration fell on.
target = body.get('web_target')
assert target == os.environ['ADMIN_TARGET'], \
    'web_target is %r, expected the declared scope %r' % (target, os.environ['ADMIN_TARGET'])
# All three verdicts are legitimate platform answers and nothing gates on them,
# so this is the demo asserting its own premise rather than a guard being
# tested: it declares at birth and then waits on a model round-trip before the
# first approval, which is tens of seconds. postdated would mean the scope was
# fitted to a trace already under way — the thing declaring at birth prevents —
# and indeterminate means both second-precision stamps tied, which that gap
# makes impossible. Either verdict here says the ordering stamp is wrong, not
# that the run was unlucky.
declaration = body.get('declaration')
assert declaration == 'preceded', (
    'declaration is %r, expected preceded — the target was declared when the '
    'session opened, so it is an authorization scope and not a post-hoc claim '
    '(postdated = the scope was fitted to a trace already under way; '
    'indeterminate = the declaration and first capture tied at second precision)'
    % (declaration,))

filename = body.get('suggested_filename') or ''
assert filename.endswith('.md') and len(filename) > 3, \
    'suggested_filename is %r, expected a <slug>.md' % (filename,)

markdown = body.get('markdown') or ''
assert markdown.startswith('---\n'), 'the draft does not open with a YAML frontmatter fence'
end = markdown.find('\n---\n', 4)
assert end > 0, 'the draft never closes its frontmatter fence'
front, body_text = markdown[:end], markdown[end:]

def front_value(key):
    for line in front.splitlines():
        if line.startswith(key + ':'):
            return line[len(key) + 1:].strip()
    return None

assert front_value('kind') == 'executable_flow', \
    'frontmatter kind is %r, expected executable_flow' % (front_value('kind'),)
assert front_value('risk_class') == 'write', \
    'frontmatter risk_class is %r, expected write' % (front_value('risk_class'),)
assert json.loads(front_value('web_target') or 'null') == os.environ['ADMIN_TARGET'], \
    'frontmatter web_target is %r' % (front_value('web_target'),)
assert 'graduated' in (front_value('tags') or ''), \
    'frontmatter tags do not mark the draft as graduated: %r' % (front_value('tags'),)

step_lines = [l for l in front.splitlines() if l.strip().startswith('- tool:')]
assert len(step_lines) == expected, \
    'the frontmatter lists %d step(s), expected %d' % (len(step_lines), expected)
for line in step_lines:
    tool = json.loads(line.split('- tool:', 1)[1].strip())
    assert tool.startswith('web.'), 'a graduated step names %r, expected a browser tool' % (tool,)

# The renderer never invents a decision line: a sentence the trace did not
# say is the composition R-4 forbids, so a replay card shows no flow_intent
# unless a human adds one at merge time.
assert front_value('flow_intent') is None, \
    'the draft synthesized a flow_intent %r — the renderer must not compose one' % (front_value('flow_intent'),)
# Nor a post-condition: the trace records what ran, not what anyone expected.
assert 'expect:' not in front, 'the draft synthesized an expect post-condition'

# The artifact a human merges into a repository carries no secret. The login
# went in by reference and the new password rode a read-tier navigate URL, so
# neither is a captured step — assert that held rather than assume it.
assert os.environ['NEW_PASSWORD'] not in markdown, \
    'the draft carries the new password literal'
# Scoped to the frontmatter, not the whole document: the runbook body names
# the marker in its merge advisory (it warns that graduation refuses a step
# still carrying a credential-reference hole), so a document-wide absence
# check would fail every genuine draft. The frontmatter is the right scope
# twice over — it holds the authoritative replay copy, and it is what
# ingestion scans per step, never the prose.
assert '<credential-reference>' not in front, \
    'a step argument still carries an unresolved credential-reference hole'
# One regression guard, labelled as such rather than passed off as live
# coverage: the pasted userinfo password cannot reach this artifact today
# because it belongs to a DIFFERENT session (leg 5 declares it, never graduates
# it). It stays because a future change that let one session read another
# declaration would leak exactly this — and the two checks above (the
# new-password literal document-wide, and the credential-reference hole in the
# frontmatter) are the ones carrying live weight.
#
# The credential-set-name guard the static-target version of this demo also ran
# is deliberately gone. It asserted 'admin-portal' never appeared in the draft (a
# credential-set name could only arrive through web.fill_credential, which is
# read tier and therefore never captured). After the SPEC-060 move the credential
# set is named 'acme-admin' — the same string as the target host, which the
# graduated web_target legitimately carries — so a substring-absence check on it
# is no longer expressible. The live '<credential-reference>' hole check above
# already covers a captured credential reference, which is what that guard really
# protected.
for needle in ('Sup3rSecret',):
    assert needle not in markdown, 'the draft carries %r' % (needle,)

# Provenance is body content, so a team may keep or strip it on merge.
assert 'mode: graduated' in body_text, 'the draft carries no graduated-mode provenance block'
assert os.environ['SESSION'] in body_text, 'the provenance block does not name the session it came from'

with open(os.environ['OUT'], 'w') as handle:
    handle.write(markdown)
print('  %d step(s), web_target %s, declaration %s, filename %s'
      % (expected, target, body.get('declaration'), filename))
print(filename)" \
    || fail "the graduated draft is not the deterministic executable-flow artifact R-4 promises"
  GRADUATED_FILE=$(printf '%s' "$HTTP_BODY" | python3 -c "
import json, sys
print(json.load(sys.stdin).get('suggested_filename', ''))")
  [ -s "$WORK/graduated.md" ] || fail "the graduated markdown was not written to the work directory"
  [ -n "$GRADUATED_FILE" ] || fail "no suggested_filename to merge under"
  echo "graduated ${WRITES} approved mutation(s) into ${GRADUATED_FILE} — no model call, no invented step"

  echo ""
  echo "==> [ACT 3] merge: the draft installs and ingests as an executable flow"

  # The human half of the merge — reviewing the runbook, replacing the
  # snapshot-relative element refs with durable descriptions, adding the
  # web.fill_credential login step the read-tier capture never recorded, and
  # writing a flow_intent decision line — is what WALKTHROUGH.md covers. The
  # demo does the mechanical half so the replay has something to bind to:
  # the draft goes into the same `samples` ConfigMap deploy-samples.sh owns,
  # under the same `<sample-leaf>-<file>.md` key convention.
  kubectl -n "$NAMESPACE" get configmap "$CONFIGMAP" >/dev/null 2>&1 \
    || fail "the '$CONFIGMAP' ConfigMap is missing; run 'make deploy-samples' first"

  GRADUATED_KEY="$SAMPLE_LEAF-$GRADUATED_FILE"
  python3 -c "
import json, sys
with open(sys.argv[1]) as handle:
    markdown = handle.read()
print(json.dumps({'data': {sys.argv[2]: markdown}}))" \
    "$WORK/graduated.md" "$GRADUATED_KEY" > "$WORK/patch.json" \
    || fail "could not build the ConfigMap patch for the graduated draft"
  kubectl -n "$NAMESPACE" patch configmap "$CONFIGMAP" --type=merge \
    --patch "$(cat "$WORK/patch.json")" >/dev/null \
    || fail "could not merge the graduated draft into '$CONFIGMAP' as '$GRADUATED_KEY'"
  echo "merged the draft into '$CONFIGMAP' as '$GRADUATED_KEY'"

  kubectl -n "$NAMESPACE" rollout restart deployment/skills-hub >/dev/null \
    || fail "could not restart skills-hub to re-ingest the merged draft"
  kubectl -n "$NAMESPACE" rollout status deployment/skills-hub --timeout=180s >/dev/null \
    || fail "skills-hub did not come back after the re-ingest restart"

  SLUG="${GRADUATED_FILE%.md}"
  EXPECTED_ID="samples/$SAMPLE_LEAF-$SLUG"
  # Found by the graduation tag rather than by a predicted id, so the demo
  # reads what ingestion actually produced; the prediction is then asserted
  # against it, which is what keeps the id derivation in deploy-samples.sh
  # and this sample honest about each other.
  #
  # Bounded retry, because `rollout status` reports *readiness* and readiness
  # does not gate on ingestion: skills-hub's lifespan starts each source sync
  # as a background task and /health/ready gates on the store alone, so a pod
  # can be Ready while the postgres-backed store still holds the pre-patch
  # `samples` records. Asserting once here would report "skills-hub did not
  # ingest the merged draft" against a platform that is merely mid-cycle — and
  # cycles are SKILLS_SYNC_INTERVAL_SECONDS (300 in dev-k8s) apart, so a
  # missed first pass does not heal on a demo's timescale.
  ATTEMPTS=0
  INGESTED=false
  while [ "$ATTEMPTS" -lt 40 ]; do
    ATTEMPTS=$((ATTEMPTS+1))
    http "$GATEWAY_URL/api/v1/skills?source=samples&tag=graduated&limit=100" \
      -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN"
    if [ "$HTTP_CODE" = "200" ] && printf '%s' "$HTTP_BODY" | grep -qF "$EXPECTED_ID"; then
      INGESTED=true
      break
    fi
    echo "  waiting for skills-hub to re-ingest the samples source (${ATTEMPTS}/40)"
    sleep 3
  done
  [ "$INGESTED" = "true" ] \
    || fail "skills-hub never re-ingested the merged draft as '$EXPECTED_ID' (last inventory answer: $HTTP_CODE); the source sync runs in the background on a ${ATTEMPTS}-attempt bound, so a slow first cycle is retried but a failing one is not — check 'kubectl logs deployment/skills-hub' for a sync error"
  GRADUATED_SKILL_ID=$(printf '%s' "$HTTP_BODY" | EXPECTED="$EXPECTED_ID" python3 -c "
import json, os, sys
payload = json.load(sys.stdin)
expected = os.environ['EXPECTED']
ids = [s.get('skill_id') for s in (payload.get('skills') or [])]
assert expected in ids, \
    'the merged draft did not ingest as %r; the samples source holds %r' % (expected, ids)
print(expected)") || fail "skills-hub did not ingest the merged draft under the expected id"
  echo "skills-hub ingested the merged draft as $GRADUATED_SKILL_ID"

  # The detail call is retried on the gateway's transport codes only, and for a
  # reason the inventory retry above does not cover: this is the one call the
  # act makes to a service the act itself just restarted, and `rollout status`
  # returning does not mean the Service endpoints have finished propagating.
  # Measured on dev-k8s at 0.36.0, the FIRST detail request after `rollout
  # status` answered 502 "skills hub unavailable" — the gateway's mapping of an
  # httpx transport error, so nothing ever reached skills-hub — on 3 runs out
  # of 3, and the second attempt answered 200 every time, even when the
  # inventory call immediately before it had answered 200 on its first try. So
  # the fragile shape is a single un-retried GET here, not the platform: 502 is
  # the honest answer for a connection the gateway could not complete. A 404
  # ("unknown skill id"), 401 or 403 is a real answer about THIS skill and
  # still fails on the first attempt.
  DETAIL_ATTEMPTS=0
  while :; do
    DETAIL_ATTEMPTS=$((DETAIL_ATTEMPTS+1))
    http "$GATEWAY_URL/api/v1/skills/$GRADUATED_SKILL_ID" \
      -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN"
    if [ "$HTTP_CODE" = "200" ]; then
      break
    fi
    case "$HTTP_CODE" in
      502|503)
        [ "$DETAIL_ATTEMPTS" -lt 20 ] \
          || fail "the graduated skill detail still answered $HTTP_CODE after $DETAIL_ATTEMPTS attempts — a connection the gateway could not complete, not an answer about the skill; check 'kubectl get pods -l app=skills-hub' and the gateway log: $HTTP_BODY"
        echo "  waiting for the skills-hub endpoints to settle (${DETAIL_ATTEMPTS}/20, HTTP $HTTP_CODE)"
        sleep 3
        ;;
      *)
        fail "the graduated skill detail answered $HTTP_CODE: $HTTP_BODY"
        ;;
    esac
  done
  printf '%s' "$HTTP_BODY" | ADMIN_TARGET="$ADMIN_TARGET" EXPECT_STEPS="$WRITES" python3 -c "
import json, os, sys
skill = json.load(sys.stdin)
WRITE_TIER = {'web.click', 'web.type', 'web.select', 'web.press_key', 'web.upload_file', 'web.evaluate'}
# The v2 columns survived the round trip through the real store: a kind
# discriminator and a machine-readable replay list, which a v1 skill has
# neither of and which the whole replay path is built on.
assert skill.get('kind') == 'executable_flow', \
    'ingested kind is %r, expected executable_flow' % (skill.get('kind'),)
assert skill.get('risk_class') == 'write', \
    'ingested risk_class is %r, expected write' % (skill.get('risk_class'),)
assert skill.get('web_target') == os.environ['ADMIN_TARGET'], \
    'ingested web_target is %r, expected %r' % (skill.get('web_target'), os.environ['ADMIN_TARGET'])
steps = skill.get('steps') or []
expected = int(os.environ['EXPECT_STEPS'])
assert len(steps) == expected, \
    'the ingested skill carries %d step(s), expected %d' % (len(steps), expected)
for idx, step in enumerate(steps):
    assert isinstance(step, dict), 'step %d is not an object' % idx
    tool = step.get('tool')
    assert tool in WRITE_TIER, \
        'step %d names %r, expected a write-tier web.* tool' % (idx, tool)
    assert isinstance(step.get('args'), dict), 'step %d carries no args object' % idx
print('  kind=%s risk_class=%s steps=%d web_target=%s'
      % (skill.get('kind'), skill.get('risk_class'), len(steps), skill.get('web_target')))" \
    || fail "the ingested skill does not carry the executable-flow kind, write class and step list"
  echo "the ingested skill is a write-class executable flow with its step list intact"

  echo ""
  echo "==> [ACT 4] replay: the graduated flow collapses to one gate"

  http -X POST "$GATEWAY_URL/api/v1/sessions" \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}'
  [ "$HTTP_CODE" = "200" ] || fail "replay session create answered $HTTP_CODE: $HTTP_BODY"
  REPLAY_SESSION=$(json_field "$HTTP_BODY" session_id)
  [ -n "$REPLAY_SESSION" ] || fail "replay session create returned no session_id"

  # This time the skill exists, so web.navigate(skill_id=…) binds a flow and
  # the same mutations ride one operator decision instead of one each. The
  # no-sign-in-click instruction carries over from act 1 for the same reason,
  # and here it is worth twice as much: act 4 asserts that every write-tier
  # execution under the single gate both succeeded and carries a signed
  # receipt, and a click that fails on the auto-login's already-replaced form
  # is a write the graduated flow never declared.
  REPLAY_MESSAGE="Use skill ${GRADUATED_SKILL_ID} to reset the password for BOTH '${TARGET_USER_A}' and '${TARGET_USER_B}' to '${NEW_PASSWORD}' in the acme-admin console. Bind the flow by passing skill_id to web.navigate. Fill both admin credentials with web.fill_credential from the acme-admin credential set (never web.type) and do NOT click 'Sign in': that page's legacy-SSO auto-login submits itself once both fields are filled, so the click would fail on a detached element and is a write the flow you are replaying never declared. Then pass the new password as the newpw URL parameter on each reset page so the form pre-fills."

  REPLAY_STREAM=$(curl -fsS --max-time 300 -N \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN" \
    "$GATEWAY_URL/api/v1/chat/stream?session_id=$REPLAY_SESSION&message=$(python3 -c "
import urllib.parse, sys
print(urllib.parse.quote(sys.argv[1]))" "$REPLAY_MESSAGE")") \
    || fail "replay chat stream request failed"

  printf '%s' "$REPLAY_STREAM" | grep -q '"type": *"confirmation_request"\|"type":"confirmation_request"' \
    || fail "replaying the graduated flow parked no confirmation card (did the model reach a write-tier interaction?)"
  REPLAY_CONFIRM_ID=$(printf '%s' "$REPLAY_STREAM" | SKILL="$GRADUATED_SKILL_ID" python3 -c "
import json, os, sys
frames = []
for line in sys.stdin:
    line = line.strip()
    if not line.startswith('data:'):
        continue
    try:
        frame = json.loads(line[5:].strip())
    except ValueError:
        continue
    if frame.get('type') == 'confirmation_request':
        frames.append(frame)
assert len(frames) == 1, \
    'the graduated flow parked %d cards before approval, expected exactly one' % len(frames)
frame = frames[0]
assert frame.get('approval_kind') == 'flow', \
    'replay card approval_kind is %r, expected flow' % (frame.get('approval_kind'),)
summary = frame.get('flow_summary') or {}
assert summary.get('skill_id') == os.environ['SKILL'], \
    'the flow headline names %r, expected the graduated skill %r' % (summary.get('skill_id'), os.environ['SKILL'])
assert summary.get('risk_class') == 'write', \
    'the flow headline risk_class is %r, expected write' % (summary.get('risk_class'),)
# One decision about the workflow, not N decisions about N DOM actions.
assert not any((c.get('change_request') for c in (frame.get('pending_calls') or []))), \
    'the flow card carried a per-call change-request projection'
print(frame.get('confirm_id', ''))") \
    || fail "the replay did not collapse to one flow-kind gate headed by the graduated skill"
  [ -n "$REPLAY_CONFIRM_ID" ] || fail "replay confirmation_request frame carried no confirm_id"
  echo "one flow-kind card parked, headed by $GRADUATED_SKILL_ID (confirm_id=${REPLAY_CONFIRM_ID}); approving"

  RESUMED=$(curl -fsS --max-time 300 -X POST \
    -H "Authorization: Bearer $APPROVER_PLATFORM_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$REPLAY_SESSION\", \"confirm_id\": \"$REPLAY_CONFIRM_ID\", \"decision\": \"approve\"}" \
    "$GATEWAY_URL/api/v1/chat/confirm") || fail "approver approve call failed for the replay card"
  printf '%s' "$RESUMED" | grep -q '"status": *"approved"\|"status":"approved"' \
    || fail "confirmation_result did not report the replay approval: $RESUMED"
  if printf '%s' "$RESUMED" | grep -q '"type": *"confirmation_request"\|"type":"confirmation_request"'; then
    fail "the resumed replay parked a SECOND card — a bound flow must collapse to exactly one gate"
  fi
  echo "the resumed replay ran to completion without parking a second gate"

  http "$GATEWAY_URL/api/v1/sessions/$REPLAY_SESSION" \
    -H "Authorization: Bearer $OPERATOR_PLATFORM_TOKEN"
  [ "$HTTP_CODE" = "200" ] || fail "replay session detail answered $HTTP_CODE: $HTTP_BODY"
  printf '%s' "$HTTP_BODY" | python3 -c "
import json, sys
detail = json.load(sys.stdin)
assert detail.get('pending_confirmation') is not True, \
    'the replay session still parks a confirmation after the resume completed'
cards = detail.get('confirmations') or []
assert len(cards) == 1, \
    'expected exactly one confirmation card for the whole replayed flow, got %d' % len(cards)
card = cards[0]
assert card.get('approval_kind') == 'flow', \
    'durable replay card approval_kind is %r, expected flow' % (card.get('approval_kind'),)
assert card.get('status') == 'approved', \
    'durable replay card status is %r, expected approved' % (card.get('status'))
WRITE_TIER = {'web.click', 'web.type', 'web.select', 'web.press_key', 'web.upload_file', 'web.evaluate'}
executions = card.get('executions') or []
assert executions, 'the approved replay card carries no execution rows'
for row in executions:
    assert row.get('tool_name') in WRITE_TIER, \
        'execution row names %r, expected a write-tier web.* tool' % row.get('tool_name')
    # Same reason as act 1: a signed receipt proves the call was authorized,
    # not that it landed, and the claim this act makes is that the SAME
    # mutations replayed — so a failed click must fail here rather than leave
    # the verification URL at the end showing an unreset password.
    assert row.get('status') == 'succeeded', \
        'replayed execution %r did not succeed (status %r) — the flow was approved but the mutation did not land' % (
            row.get('tool_name'), row.get('status'))
    assert row.get('receipt', {}).get('signature'), \
        'execution %r carries no signed receipt' % row.get('tool_name')
print('  %d write-tier execution(s), every one succeeded and signed under the single card' % len(executions))" \
    || fail "the replay session detail lacks the single approved flow card with signed executions"
  echo "every replayed write rode the one approval, landed, and carries a signed receipt"

  # SPEC-060: the replayed flow really mutated the store again — both users carry
  # a fresh password_changed_at and the whole-store revision moved past where act
  # 1 left it. Proving the revision increased (not merely that a timestamp
  # exists) is what distinguishes act 4's replay from act 1's leftover state: the
  # same two resets, driven this time under ONE gate.
  app_verify_both_resets "act 4"
  REV_AFTER_REPLAY=$(app_store_revision)
  [ -n "$REV_AFTER_REPLAY" ] || fail "act 4: could not read the store revision after replay"
  [ "$REV_AFTER_REPLAY" -gt "$REV_AFTER_AUTHOR" ] \
    || fail "act 4: the store revision did not advance past act 1 (${REV_AFTER_REPLAY} <= ${REV_AFTER_AUTHOR}); the replay did not land a fresh mutation"
  echo "act 4 landed both resets again under the one gate (store revision ${REV_AFTER_AUTHOR} -> ${REV_AFTER_REPLAY})"

  echo ""
  echo "==> the contrast this sample exists to show:"
  echo "    authored ad hoc  -> ${CARDS} per-action card(s) for ${WRITES} mutation(s)"
  echo "    replayed as a graduated flow -> 1 card for the same work"
  echo ""
  echo "==> verification (the store is authoritative, not a query-string echo):"
  echo "    port-forward:      kubectl -n $NAMESPACE port-forward svc/acme-admin 8080:8080 &"
  echo "    Console user list: http://localhost:8080/admin/users/  (revision + Last modified for ${TARGET_USER_A}, ${TARGET_USER_B})"
  echo "    JSON store:        http://localhost:8080/api/users/${TARGET_USER_B}  (password_changed_at + revision; HTTP Basic as admin)"
  echo "    Portal session (authoring): open session ${AUTHOR_SESSION} and press 'Graduate as skill'"
  echo "    Portal session (replay):    open session ${REPLAY_SESSION} and read the single flow card"
else
  echo ""
  echo "==> [ACTS 1-4] chat legs skipped (RUN_CHAT_LEG unset; opt-in)"
  echo "    the author -> graduate -> merge -> replay story needs a model;"
  echo "    the deterministic legs above already assert the declaration and"
  echo "    refusal postures that do not."
fi

echo ""
echo "Skill-graduation tutorial demo passed:"
echo "  - browser connector enabled, HITL bridging active, SPEC-055 knobs sane"
echo "  - acme-admin console pages served (login, session-gated users + reset form)"
echo "  - acme-admin credential set loaded"
echo "  - fifteen web.* tools registered with correct risk tiers"
echo "  - a declared target is first-wins, reported in force, and scoped"
echo "  - graduation is separately authorized and refuses an empty trace"
if [ "${RUN_CHAT_LEG:-}" = "true" ]; then
  echo "  - an ad-hoc session of approved mutations graduated into an executable flow"
  echo "  - the merged draft ingested with its kind, risk class and step list"
  echo "  - the graduated flow replayed under one gate, every write landed and signed"
  echo "  - both resets verified in the store after act 1 and again after act 4 (revision advanced)"
fi
