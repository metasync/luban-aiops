#!/bin/sh

# Operations document repository live check (SPEC-039 delivery gate,
# extended for the SPEC-040 handover section and the SPEC-041
# counts-only summary).
#
# Deterministic end-to-end assertions for the operations document
# repository (Phase 1: shift summaries), runnable after `make deploy`:
#   1. control check: a role without documents:create is rejected (403)
#   2. an operator creates a session, then a shift-summary draft citing
#      it (digest + provenance present, state=draft, the digest carries
#      the deterministic handover section — SPEC-040 R-1 — and the
#      record carries the counts-only summary line — SPEC-041 R-4)
#   3. drafts are owner-only: the reader gets a 404 anti-enumeration
#      before the owner publishes, and a 200 with owner attribution after
#   4. publish is one-way: the second publish answers 409
#   5. the reader sees the document in the published scope listing,
#      envelope-only (digest/prose never leak through the listing) and
#      carrying the summary line
#   6. the durable trail carries document_created / document_published
#      and the cross-owner document_read attributed to the reader
#   7. session rename (R-7): owner renames (list/detail reflect it),
#      a foreign caller gets the anti-enumeration 404, and the auditor
#      role — denied session:update — gets 403
#
# Prerequisites:
#   - kubectl context pointed at the dev cluster
#   - a port-forward for the platform-gateway, e.g.:
#       kubectl -n dev-luban-aiops port-forward svc/platform-gateway 18083:8000
#   - a port-forward for the identity broker (token issuance):
#       kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000
#
# Environment overrides:
#   GATEWAY_URL   (default http://localhost:18083)
#   IDENTITY_URL  (default http://localhost:18081)
#   OWNER_USER    (default luban-operator)
#   READER_USER   (default luban-approver)

set -eu

GATEWAY_URL="${GATEWAY_URL:-http://localhost:18083}"
IDENTITY_URL="${IDENTITY_URL:-http://localhost:18081}"
OWNER_USER="${OWNER_USER:-luban-operator}"
READER_USER="${READER_USER:-luban-approver}"
RUN_SUFFIX="$(date +%s)-$$"

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

# HTTP call that keeps the body in $HTTP_BODY and the status in $HTTP_CODE.
http() {
  HTTP_BODY=$(curl -s -o /tmp/documents-body -w "%{http_code}" "$@")
  HTTP_CODE="$HTTP_BODY"
  HTTP_BODY=$(cat /tmp/documents-body)
}

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

echo "==> [1/7] platform tokens for owner, reader, observer, and auditor"
OWNER_TOKEN=$(platform_token "$OWNER_USER" operator ops-operators)
[ -n "$OWNER_TOKEN" ] || fail "broker issued no platform token for $OWNER_USER"
READER_TOKEN=$(platform_token "$READER_USER" approver ops-approvers)
[ -n "$READER_TOKEN" ] || fail "broker issued no platform token for $READER_USER"
OBSERVER_TOKEN=$(platform_token luban-observer read-only-observer ops-observers)
[ -n "$OBSERVER_TOKEN" ] || fail "broker issued no platform token for luban-observer"
AUDITOR_TOKEN=$(platform_token luban-auditor auditor ops-auditors)
[ -n "$AUDITOR_TOKEN" ] || fail "broker issued no platform token for luban-auditor"
echo "tokens issued for $OWNER_USER, $READER_USER, luban-observer, luban-auditor"

echo "==> [2/7] role matrix: observer denied documents:create"
http -X POST "$GATEWAY_URL/api/v1/documents" \
  -H "Authorization: Bearer $OBSERVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"document_type": "shift_summary", "session_ids": ["ses-x"], "label": "denied"}'
[ "$HTTP_CODE" = "403" ] || fail "observer create answered $HTTP_CODE, expected 403"
echo "observer create denied (no documents:create grant)"

echo "==> [3/7] owner creates a session and a shift-summary draft citing it"
http -X POST "$GATEWAY_URL/api/v1/sessions" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" -d '{}'
[ "$HTTP_CODE" = "200" ] || fail "session create answered $HTTP_CODE, expected 200"
SESSION_ID=$(json_field "$HTTP_BODY" session_id)
[ -n "$SESSION_ID" ] || fail "session create returned no session_id"

http -X POST "$GATEWAY_URL/api/v1/documents" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"document_type\": \"shift_summary\", \"session_ids\": [\"$SESSION_ID\"], \"label\": \"live check $RUN_SUFFIX\", \"include_prose\": false}"
# include_prose stays pinned off here: the live check asserts the
# deterministic digest surface; the narrative path is fail-soft but
# latency-bound (model call), and the portal walkthrough covers it.
[ "$HTTP_CODE" = "201" ] || fail "document create answered $HTTP_CODE: $HTTP_BODY"
DOCUMENT_ID=$(json_field "$HTTP_BODY" document_id)
[ -n "$DOCUMENT_ID" ] || fail "document create returned no document_id"
[ "$(json_field "$HTTP_BODY" state)" = "draft" ] || fail "new document is not a draft"
[ "$(json_field "$HTTP_BODY" owner_user_id)" = "$OWNER_USER" ] \
  || fail "new document owner is not $OWNER_USER"
[ "$(json_field "$HTTP_BODY" provenance.sessions.0.session_id)" = "$SESSION_ID" ] \
  || fail "provenance does not anchor the cited session"
# SPEC-040 R-1: the digest tells the shift story deterministically.
[ "$(json_field "$HTTP_BODY" digest.handover.covered_session_count)" = "1" ] \
  || fail "digest carries no handover section with covered_session_count=1"
[ "$(json_field "$HTTP_BODY" digest.handover.own_session_count)" = "1" ] \
  || fail "handover section lost the own-session count"
[ "$(json_field "$HTTP_BODY" digest.handover.quiet)" = "True" ] \
  || fail "a fresh session should report an honest quiet shift"
# SPEC-041 R-4: the counts-only summary is computed at creation.
[ "$(json_field "$HTTP_BODY" summary)" = "Quiet shift — no recorded decisions or executions." ] \
  || fail "created document carries no quiet summary line"
echo "draft $DOCUMENT_ID created citing session $SESSION_ID (handover section + summary present)"

echo "==> [4/7] drafts are owner-only until publish; publish is one-way"
http "$GATEWAY_URL/api/v1/documents/$DOCUMENT_ID" \
  -H "Authorization: Bearer $READER_TOKEN"
[ "$HTTP_CODE" = "404" ] || fail "reader saw the draft: $HTTP_CODE, expected 404"
echo "reader gets the anti-enumeration 404 while the document is a draft"

http -X POST "$GATEWAY_URL/api/v1/documents/$DOCUMENT_ID/publish" \
  -H "Authorization: Bearer $OWNER_TOKEN"
[ "$HTTP_CODE" = "200" ] || fail "publish answered $HTTP_CODE: $HTTP_BODY"
[ "$(json_field "$HTTP_BODY" state)" = "published" ] || fail "publish did not flip state"

http -X POST "$GATEWAY_URL/api/v1/documents/$DOCUMENT_ID/publish" \
  -H "Authorization: Bearer $OWNER_TOKEN"
[ "$HTTP_CODE" = "409" ] || fail "re-publish answered $HTTP_CODE, expected 409"
echo "published; re-publish answers 409"

http "$GATEWAY_URL/api/v1/documents/$DOCUMENT_ID" \
  -H "Authorization: Bearer $READER_TOKEN"
[ "$HTTP_CODE" = "200" ] || fail "reader fetch after publish answered $HTTP_CODE"
[ "$(json_field "$HTTP_BODY" owner_user_id)" = "$OWNER_USER" ] \
  || fail "reader view lost the owner attribution"
http "$GATEWAY_URL/api/v1/documents?scope=published" \
  -H "Authorization: Bearer $READER_TOKEN"
[ "$HTTP_CODE" = "200" ] || fail "published listing answered $HTTP_CODE"
printf '%s' "$HTTP_BODY" | grep -q "$DOCUMENT_ID" \
  || fail "published listing does not contain $DOCUMENT_ID"
printf '%s' "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin).get('documents', [])
assert rows, 'published listing is empty'
for row in rows:
    assert 'digest' not in row and 'prose' not in row, row.get('document_id')
mine = [row for row in rows if row.get('document_id') == sys.argv[1]]
assert mine, 'listing lost the created document'
assert 'Quiet shift' in (mine[0].get('summary') or ''), mine[0].get('summary')
" "$DOCUMENT_ID" || fail "published listing leaked digest/prose content or lost the summary"
echo "reader reads the published document with owner attribution; listing is envelope-only with the summary line"

echo "==> [5/7] document audit on the durable trail"
sleep 2  # audit emission is fire-and-forget; give the sink a beat
audit_has() {
  http "$GATEWAY_URL/api/v1/audit/events?event_type=$1&limit=50" \
    -H "Authorization: Bearer $AUDITOR_TOKEN"
  [ "$HTTP_CODE" = "200" ] || fail "audit query ($1) answered $HTTP_CODE"
  printf '%s' "$HTTP_BODY" | grep -q "$2"
}
audit_has document_created "$DOCUMENT_ID" \
  || fail "document_created for $DOCUMENT_ID missing from the durable trail"
audit_has document_published "$DOCUMENT_ID" \
  || fail "document_published for $DOCUMENT_ID missing from the durable trail"
http "$GATEWAY_URL/api/v1/audit/events?event_type=document_read&username=$READER_USER&limit=50" \
  -H "Authorization: Bearer $AUDITOR_TOKEN"
[ "$HTTP_CODE" = "200" ] || fail "audit query (document_read) answered $HTTP_CODE"
printf '%s' "$HTTP_BODY" | grep -q "$DOCUMENT_ID" \
  || fail "cross-owner document_read for $READER_USER missing from the durable trail"
echo "document_created, document_published, and cross-owner document_read are durable"

echo "==> [6/7] session rename (R-7): owner renames, foreign 404, auditor 403"
NEW_TITLE="renamed by live check $RUN_SUFFIX"
http -X PATCH "$GATEWAY_URL/api/v1/sessions/$SESSION_ID/title" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"title\": \"$NEW_TITLE\"}"
[ "$HTTP_CODE" = "200" ] || fail "owner rename answered $HTTP_CODE: $HTTP_BODY"
http "$GATEWAY_URL/api/v1/sessions/$SESSION_ID" \
  -H "Authorization: Bearer $OWNER_TOKEN"
[ "$(json_field "$HTTP_BODY" title)" = "$NEW_TITLE" ] \
  || fail "session detail does not reflect the new title"
http -X PATCH "$GATEWAY_URL/api/v1/sessions/$SESSION_ID/title" \
  -H "Authorization: Bearer $READER_TOKEN" \
  -H "Content-Type: application/json" -d '{"title": "not allowed"}'
[ "$HTTP_CODE" = "404" ] || fail "foreign rename answered $HTTP_CODE, expected 404"
http -X PATCH "$GATEWAY_URL/api/v1/sessions/$SESSION_ID/title" \
  -H "Authorization: Bearer $AUDITOR_TOKEN" \
  -H "Content-Type: application/json" -d '{"title": "not allowed"}'
[ "$HTTP_CODE" = "403" ] || fail "auditor rename answered $HTTP_CODE, expected 403"
echo "owner rename reflected; foreign caller 404; auditor 403"

echo "==> [7/7] cleanup: owner deletes the session"
http -X DELETE "$GATEWAY_URL/api/v1/sessions/$SESSION_ID" \
  -H "Authorization: Bearer $OWNER_TOKEN"
[ "$HTTP_CODE" = "200" ] || fail "session cleanup answered $HTTP_CODE"
echo "session $SESSION_ID deleted (the published document stays immutable)"

echo ""
echo "Operations document repository live check passed:"
echo "  - role matrix enforced (observer 403 on documents:create)"
echo "  - draft created with digest + provenance anchor + handover section + summary line"
echo "  - drafts owner-only (404) until publish; published readable by role"
echo "  - listing is envelope-only with the counts-only summary; full content flows the audited fetch"
echo "  - publish is one-way (409 on re-publish)"
echo "  - document_created / document_published / cross-owner document_read durable"
echo "  - session rename owner-only with anti-enumeration and role denial"
