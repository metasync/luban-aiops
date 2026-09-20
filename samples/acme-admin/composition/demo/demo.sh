#!/bin/sh

# acme-admin composition demo (SPEC-057 R-8, ladder rung 5 — the runbook).
#
# The story: a `kind: composition` skill that names two skills the suite already
# ships — `password-reset` (a bound browser flow, one `flow` card) and
# `lock-unlock-user` (one `http.post`, one `action` card) — in a declared order,
# and carries **no authority of its own** (ADR-0011). The claim this demo makes
# is the one a composition has to earn: ordering two mutating skills into a
# runbook does not merge their gates. Each sub-skill still parks its own card,
# decided by its own approver, so the runbook's gate count is the **sum** of its
# parts (2), never one card that "covers" the other.
#
# The deterministic legs are all read-only against skills-hub — they never touch
# the app or the gateway, because what a composition *is* is a fact about the
# catalog, not about a mutation:
#   1. the composition document is mounted, and declares no authority of its own
#      (no web_target, no steps, no author risk_class)
#   2. the composition **resolves**: get_skill returns two ordered sub-skills,
#      each enriched with its own title/target, and a **derived** risk_class of
#      `write` (because password-reset is write) the document never declared
#   3. **no nesting**: both sub-skills are leaves (`kind != composition`), and the
#      `samples` source synced the composition with zero rejections — so the
#      resolution pass accepted it rather than dropping it
#   4. the **structural** layer fails closed: an over-cap list, a self-declared
#      risk_class, and a smuggled sequencing key are each rejected by the
#      operator-facing `/skills/validate` pre-flight
#   5. nesting is a **resolution**-layer rejection, not a structural one: the
#      catalog-blind pre-flight passes a nested reference, which is exactly why
#      R-2 splits validation in two (asserted live by leg 3, and negatively by
#      skills-hub's own `test_sync.py`)
#
# Optional chat leg (RUN_CHAT_LEG=true): one session follows the runbook and
# parks **two** durable cards — a `flow` and an `action` — proving the
# multi-binding gate count (2 > any single sub-skill's 1) and that no card claims
# authority over a sub-skill it does not name.
#
# Prerequisites: see demo-lib.sh's header. `make deploy-samples` must have packed
# this composition and both sub-skills into the one `samples` source, so they
# resolve within a single sync cycle.

set -eu

DEMO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
# shellcheck source=../../demo-lib.sh
. "$DEMO_DIR/../../demo-lib.sh"

acme_demo_init "composition" 5

COMPOSITION_LEAF="composition"
COMPOSITION_FILE="RecoverAcmeAccount.md"
COMPOSITION_ID="samples/composition-recoveracmeaccount"
SUB_BROWSER="samples/password-reset-resetacmepassword"
SUB_INFRA="samples/lock-unlock-user-lockunlockuser"
SKILLS_HUB_URL="http://localhost:8000"

# The composition's own recovery target for the opt-in chat leg: `dave` is the
# seed's pre-locked user, so "reset the password, then unlock" is a real
# recovery of a locked-out account rather than a no-op against an active one.
TARGET_USER="${TARGET_USER:-dave}"
NEW_PASSWORD="${NEW_PASSWORD:-TempPass-2026!}"

# --- skills-hub read-only plumbing (this demo carries its own, the way the
# --- skill-graduation demo carries its own app-access helpers: the other four
# --- rungs only ever `cat` a mounted document, so demo-lib.sh has no API client)

# resolve_query_secret — the /skills query credential, the same one skills-demo.sh
# pulls: the tool-gateway entry of SKILLS_QUERY_CLIENTS. Never printed.
resolve_query_secret() {
  clients=$(kubectl -n "$NAMESPACE" get secret skills-hub-runtime-secrets \
    -o jsonpath='{.data.SKILLS_QUERY_CLIENTS}' | base64 -d) \
    || fail "could not read SKILLS_QUERY_CLIENTS from skills-hub-runtime-secrets"
  SKILLS_QUERY_SECRET=$(printf '%s' "$clients" | tr ',' '\n' \
    | grep '^tool-gateway=' | cut -d= -f2-)
  [ -n "$SKILLS_QUERY_SECRET" ] \
    || fail "no tool-gateway entry in SKILLS_QUERY_CLIENTS (run sync-skills-secrets.sh)"
}

skills_hub_curl() {
  kubectl -n "$NAMESPACE" exec -i deployment/skills-hub -- curl "$@"
}

# skills_get_skill <id> — echoes the full record (get_skill projects a
# composition's sub-skills; a non-composition is returned verbatim).
skills_get_skill() {
  skills_hub_curl -fsS -u "tool-gateway:$SKILLS_QUERY_SECRET" \
    "$SKILLS_HUB_URL/api/v1/skills/$1" </dev/null
}

# skills_status — the per-source sync report (unauthenticated, as in skills-demo).
skills_status() {
  skills_hub_curl -fsS "$SKILLS_HUB_URL/api/v1/skills/status" </dev/null
}

# skills_validate <document> — POSTs one candidate to the operator pre-flight and
# echoes {"valid": .., "reason": ..}. The body travels on stdin, never in argv.
skills_validate() {
  payload=$(printf '%s' "$1" | python3 -c \
    'import json, sys; print(json.dumps({"document": sys.stdin.read()}))')
  printf '%s' "$payload" | skills_hub_curl -fsS \
    -u "tool-gateway:$SKILLS_QUERY_SECRET" \
    -H 'Content-Type: application/json' -d @- \
    "$SKILLS_HUB_URL/api/v1/skills/validate"
}

# compose_doc <extra-frontmatter> <sub_skill-item-line>... — builds a candidate
# composition document (probe) so the validate legs never hand-write YAML.
compose_doc() {
  python3 -c '
import sys
extra = [line for line in sys.argv[1].split("\n") if line]
lines = ["---", "title: Composition probe", "description: probe document",
         "kind: composition"] + extra + ["sub_skills:"] + list(sys.argv[2:])
lines += ["---", "", "Probe body."]
sys.stdout.write("\n".join(lines))' "$@"
}

# require_no_frontmatter_key <key> — the mounted composition must not declare it.
require_no_frontmatter_key() {
  body=$(kubectl -n "$NAMESPACE" exec deployment/skills-hub -- \
    cat "/skills/samples/$COMPOSITION_LEAF-$COMPOSITION_FILE")
  frontmatter=$(printf '%s' "$body" \
    | awk 'NR==1 && $0!="---"{exit} NR>1{if($0=="---") exit; print}')
  if printf '%s' "$frontmatter" | grep -q "^$1:"; then
    fail "the composition declares '$1'; a composition carries no authority of its own"
  fi
}

kubectl -n "$NAMESPACE" get deployment skills-hub >/dev/null 2>&1 \
  || fail "no skills-hub deployment in namespace '$NAMESPACE'; run 'make deploy'"
resolve_query_secret

acme_leg "the composition is mounted and declares no authority of its own"

require_skill "$COMPOSITION_LEAF" "$COMPOSITION_FILE" \
  'title: Recover a Locked-Out ACME Admin Account' \
  'kind: composition' \
  "$SUB_BROWSER" \
  "$SUB_INFRA"
# A composition names sub-skills; it binds no flow, replays no steps, and authors
# no risk_class (SPEC-057 R-1/R-2). All three are rejected on a composition, so
# the runbook cannot claim a scope its sub-skills do not already have.
require_no_frontmatter_key web_target
require_no_frontmatter_key steps
require_no_frontmatter_key risk_class
ok "the composition declares no web_target, no steps and no author risk_class"

acme_leg "the composition resolves: two ordered sub-skills, derived risk_class write"

COMPOSITION_JSON=$(skills_get_skill "$COMPOSITION_ID") \
  || fail "get_skill on $COMPOSITION_ID failed — is it mounted and both sub-skills published? (run 'make deploy-samples')"
printf '%s' "$COMPOSITION_JSON" | python3 -c '
import json, sys
composition, browser, infra = sys.argv[1], sys.argv[2], sys.argv[3]
data = json.load(sys.stdin)
assert data.get("kind") == "composition", "kind is %r" % data.get("kind")
# The derived display risk_class: write because a resolved sub-skill is write.
# The document declares none, so this value was computed and persisted at sync.
assert data.get("risk_class") == "write", \
    "derived risk_class is %r, expected write" % data.get("risk_class")
# A composition binds nothing of its own.
assert "web_target" not in data and "steps" not in data, \
    "the composition record carries a web_target or steps"
subs = data.get("sub_skills") or []
ids = [s.get("skill_id") for s in subs]
assert ids == [browser, infra], "sub_skills are %r, expected [%s, %s] in order" % (
    ids, browser, infra)
# Resolution enriched each item with its own title; the browser sub-skill also
# carries its declared target, the infra one does not (it opens no browser).
assert all(s.get("resolved_title") for s in subs), \
    "a sub-skill did not resolve to a title: %r" % subs
assert subs[0].get("resolved_web_target"), \
    "the browser sub-skill carries no resolved_web_target: %r" % subs[0]
assert not subs[1].get("resolved_web_target"), \
    "the infra sub-skill unexpectedly carries a resolved_web_target: %r" % subs[1]
print("  ok: %s resolved -> risk_class=write (derived), 2 sub-skills in order" % composition)
print("       [0] %s  target=%s" % (subs[0]["skill_id"], subs[0]["resolved_web_target"]))
print("       [1] %s  (infra, no target)" % subs[1]["skill_id"])' \
  "$COMPOSITION_ID" "$SUB_BROWSER" "$SUB_INFRA" \
  || fail "the composition did not resolve as expected: $COMPOSITION_JSON"

acme_leg "no nesting: both sub-skills are leaves and the samples source accepted it"

# The no-nesting rule (R-2) is why the composition above resolved instead of
# being dropped: neither sub-skill is itself a composition. Assert it live.
for sub in "$SUB_BROWSER" "$SUB_INFRA"; do
  sub_json=$(skills_get_skill "$sub") \
    || fail "get_skill on sub-skill $sub failed"
  printf '%s' "$sub_json" | python3 -c '
import json, sys
data = json.load(sys.stdin)
assert data.get("kind") != "composition", \
    "%s is itself a composition — nesting is not allowed in Phase 1" % sys.argv[1]
print("  ok: %s is a leaf (kind=%r), not a composition" % (
    sys.argv[1], data.get("kind") or "knowledge"))' "$sub" \
    || fail "a sub-skill of the composition is itself a composition"
done

# …and the resolution pass really accepted the composition: the samples source
# synced with no error and dropped nothing named for this runbook.
STATUS_JSON=$(skills_status) || fail "the skills-hub status endpoint did not answer"
printf '%s' "$STATUS_JSON" | python3 -c '
import json, sys
leaf_file = sys.argv[1]
# /skills/status reports an object {store_backend, sync_interval_seconds, sources: [...]};
# iterate the sources list, not the top-level object keys.
sources = json.load(sys.stdin).get("sources") or []
samples = next((s for s in sources if s.get("source_id") == "samples"), None)
assert samples is not None, "the status report carries no samples source"
assert samples.get("last_error") in (None, "null"), \
    "the samples source reports a sync error: %r" % samples.get("last_error")
dropped = [r for r in (samples.get("rejections") or [])
           if leaf_file in (r.get("path") or "")]
assert not dropped, "the composition was rejected at sync: %r" % dropped
print("  ok: the samples source synced clean (accepted=%s, no rejection named %s)" % (
    samples.get("accepted"), leaf_file))' "$COMPOSITION_FILE" \
  || fail "the samples source did not cleanly accept the composition: $STATUS_JSON"

acme_leg "the structural pre-flight fails closed: cap, author risk_class, control flow"

# The operator-facing /skills/validate route is the structural twin of ingestion
# (SPEC-044 R-2). It has no catalog, so it proves exactly the single-document
# facts — and refuses a document that would claim authority a composition lacks.
CAP=$(kubectl -n "$NAMESPACE" exec deployment/skills-hub -- \
  printenv SKILLS_COMPOSITION_MAX_SUB_SKILLS 2>/dev/null || true)
CAP=${CAP:-8}

over_cap=$(python3 -c '
import sys
cap = int(sys.argv[1])
items = ["  - skill_id: samples/cap-probe-%d" % i for i in range(cap + 1)]
sys.stdout.write("\n".join(
    ["---", "title: Over cap", "description: d", "kind: composition",
     "sub_skills:"] + items + ["---", "", "body"]))' "$CAP")
printf '%s' "$(skills_validate "$over_cap")" | python3 -c '
import json, sys
cap = sys.argv[1]
result = json.load(sys.stdin)
assert result.get("valid") is False, "an over-cap composition was accepted: %r" % result
assert ("more than %s sub_skills" % cap) in (result.get("reason") or ""), \
    "unexpected reason: %r" % result.get("reason")
print("  ok: %s+1 sub_skills rejected by the cap (%s): %s" % (
    cap, cap, result.get("reason")))' "$CAP" \
  || fail "the cap leg did not reject an over-cap composition"

authored_risk=$(compose_doc "risk_class: write" "  - skill_id: $SUB_BROWSER")
printf '%s' "$(skills_validate "$authored_risk")" | python3 -c '
import json, sys
result = json.load(sys.stdin)
assert result.get("valid") is False, "a self-declared risk_class was accepted: %r" % result
assert "declares no risk_class" in (result.get("reason") or ""), \
    "unexpected reason: %r" % result.get("reason")
print("  ok: a composition that authors its own risk_class is rejected: %s" % result.get("reason"))' \
  || fail "the pre-flight accepted a composition declaring its own risk_class"

sequenced=$(compose_doc "" "  - skill_id: $SUB_BROWSER" "    on_fail: retry")
printf '%s' "$(skills_validate "$sequenced")" | python3 -c '
import json, sys
result = json.load(sys.stdin)
assert result.get("valid") is False, "a sequencing key was accepted: %r" % result
assert "unknown sub_skill keys" in (result.get("reason") or ""), \
    "unexpected reason: %r" % result.get("reason")
print("  ok: a sub_skill carrying control flow (on_fail) is rejected (R-3): %s" % result.get("reason"))' \
  || fail "the pre-flight accepted a sub_skill carrying a sequencing key"

acme_leg "nesting is a resolution-layer rejection, not a structural one"

# The honest face of "a nested reference is rejected". The structural pre-flight
# is catalog-blind: it can check that a sub_skill id is well-formed, but not that
# the id it names is a leaf. So a candidate that references the composition
# itself PASSES structure and is caught only at resolution (sync's
# _resolve_compositions, which consults the store). This leg demonstrates that
# split rather than pretending one layer does both jobs; leg 3 asserts the rule
# holds for the deployed composition, and skills-hub's test_sync.py asserts the
# negative (a nested reference is dropped into the composition rejection bucket).
nested=$(compose_doc "" "  - skill_id: $COMPOSITION_ID")
printf '%s' "$(skills_validate "$nested")" | python3 -c '
import json, sys
result = json.load(sys.stdin)
assert result.get("valid") is True, \
    "the catalog-blind pre-flight was expected to pass a nested reference: %r" % result
print("  ok: a nested reference passes STRUCTURE (valid=true) — nesting is owned by")
print("       resolution (leg 3 + test_sync.py), which is why R-2 splits the layers")' \
  || fail "the two-layer split did not behave as documented"

if [ "${RUN_CHAT_LEG:-}" = "true" ]; then
  echo ""
  echo "==> [CHAT] one runbook parks two cards: a flow and an action"

  require_runtime_config GATEWAY_BROWSER_ENABLED true "deploy with the browser-dev profile"
  require_runtime_config GATEWAY_MUTATING_TOOLS_ENABLED true "deploy with the mutating-dev profile"
  require_credential_set
  require_hitl_enabled

  reseed_demo
  ensure_tokens

  CHAT_SESSION=$(chat_session_new)
  [ -n "$CHAT_SESSION" ] || fail "session creation returned no session_id"

  CHAT_MESSAGE="Recover the locked-out acme-admin account for '${TARGET_USER}' by following the runbook skill ${COMPOSITION_ID}: first reset the password to '${NEW_PASSWORD}' through the console UI, then unlock the account over the API. Admin credentials are in the ${CREDENTIAL_SET} credential set — do not ask me for a password."

  # Step 1 of the runbook binds the browser flow and parks a `flow` card.
  STREAM_OUTPUT=$(chat_send "$CHAT_SESSION" "$CHAT_MESSAGE")
  require_card_shape "$STREAM_OUTPUT" flow "$WRITE_TIER_WEB_TOOLS"
  FLOW_CONFIRM="$CARD_CONFIRM_ID"
  [ -n "$FLOW_CONFIRM" ] || fail "the parked flow card carried no confirm_id"
  ok "the runbook's first sub-skill parked a flow card (the browser reset)"

  RESUMED=$(chat_confirm "$CHAT_SESSION" "$FLOW_CONFIRM" approve)
  printf '%s' "$RESUMED" | grep -q '"status": *"approved"\|"status":"approved"' \
    || fail "the flow card was not approved: $RESUMED"
  ok "$APPROVER_USER approved the flow card; the reset executed"

  # Step 2 makes the infra write and parks an `action` card — in the resumed turn
  # if the model continued the runbook, otherwise on an explicit nudge. Either
  # way it lands on the SAME session, so the durable count is what matters.
  if [ "$(count_cards "$RESUMED")" = "0" ]; then
    RESUMED=$(chat_send "$CHAT_SESSION" \
      "Now the second step of the runbook ${COMPOSITION_ID}: unlock '${TARGET_USER}' over the API with skill ${SUB_INFRA}. Admin credentials are in the ${CREDENTIAL_SET} credential set.")
  fi
  require_card_shape "$RESUMED" action http.post
  ACTION_CONFIRM="$CARD_CONFIRM_ID"
  [ -n "$ACTION_CONFIRM" ] || fail "the parked action card carried no confirm_id"

  # No card claims authority over a sub-skill it does not name: the action card
  # carries no flow_summary, so the infra write does not inherit the browser
  # flow's blanket approval (ADR-0007 covers one bound flow, not the runbook).
  if [ -n "$(first_card_field "$RESUMED" "flow_summary.skill_id")" ]; then
    fail "the action card carries a flow_summary — it claims the browser sub-skill's authority"
  fi
  ok "the second sub-skill parked an action card carrying no flow authority"

  chat_confirm "$CHAT_SESSION" "$ACTION_CONFIRM" approve >/dev/null \
    || fail "the action card could not be approved"

  # The multi-binding gate count: two mutating sub-skills, two durable cards of
  # two kinds — more than either sub-skill parks alone (one each).
  require_card_count "$CHAT_SESSION" 2 \
    "a two-sub-skill runbook gates once per mutating sub-skill (a flow + an action)"
else
  chat_leg_skipped "a scripted runbook asserting two cards (a flow + an action) on one session"
fi

acme_demo_summary \
  "the composition is mounted and declares no web_target, no steps and no author risk_class" \
  "get_skill resolves it to two ordered sub-skills, each enriched with its own title/target, at a derived risk_class of write" \
  "both sub-skills are leaves and the samples source synced the composition with zero rejections, so resolution accepted it" \
  "the catalog-blind /skills/validate pre-flight rejects an over-cap list, an authored risk_class and a smuggled sequencing key" \
  "a nested reference passes structure and is caught only at resolution — the two-layer split R-2 documents" \
  "(chat leg) one runbook parks two durable cards, a flow and an action, and the action card claims no flow authority"
