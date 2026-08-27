# SPEC-039 Tasks: Shift-Summary Artifacts

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## Contract & Policy

- [ ] add `shared/shared-contracts/schemas/shift-summary.schema.json` (artifact shape: digest sections, provenance ids, `prose_status`) (`shared/shared-contracts`)
- [ ] add `shifts:summarize` action with `operator`/`approver`/`platform-admin` grants to the canonical policy bundle and run `make sync-policy` (`shared/shared-contracts/policies`)

## R-1: Deterministic digest assembly

- [ ] implement `build_digest` with own/foreign two-tier coverage and per-source degradation (`products/agent-platform/src/agent_service/services/shift_summary.py`)
- [ ] digest tests: own full-digest, foreign metadata-only gating, provenance ids present, degraded store sections (`products/agent-platform/tests/test_shift_summary_digest.py`)

## R-2: Policy-gated generation API

- [ ] agent route `POST /api/v2/shift-summaries` with bounded input validation and structured rejections (`products/agent-platform/src/agent_service/api/v2/routes.py`)
- [ ] gateway pass-through route behind `enforce_policy("shifts:summarize")` (`products/platform-gateway/src/platform_gateway/api/routes.py`)
- [ ] route tests: happy path, cap-20 session list, unknown-id rejection, schema validation of the response (`products/agent-platform/tests/test_shift_summaries_api.py`)
- [ ] policy-matrix tests for `shifts:summarize` grants/denials (`products/platform-gateway/tests/test_policy_matrix.py`)

## R-3: Durable artifact store

- [ ] `shift_summary_store` memory + Postgres backends, cap 20 per requester, 30-day TTL sweep, idempotent DDL (`products/agent-platform/src/agent_service/services/shift_summary_store.py`)
- [ ] store tests: immutability, cap eviction, TTL sweep, backend parity, list/get/delete ownership 404s (`products/agent-platform/tests/test_shift_summary_store.py`)

## R-4: Optional clearly-labeled prose layer

- [ ] prose generator with digest-only prompt contract, hard timeout, fail-soft `prose_status=failed` (`products/agent-platform/src/agent_service/services/shift_summary_prose.py`)
- [ ] prose tests: prompt receives digest only, timeout/error degrades to digest-only artifact (`products/agent-platform/tests/test_shift_summary_prose.py`)

## R-5: Audit event

- [ ] emit `shift_summary_generated` after persistence with forwarded `x-request-id` (`products/agent-platform/src/agent_service/services/audit_emitter.py` consumers)
- [ ] audit tests: event fields (requester, own/foreign ids, counts, prose status), fire-and-forget non-blocking (`products/agent-platform/tests/test_shift_summaries_api.py`)

## R-6: Portal shift-summaries view

- [ ] Shift summaries nav entry + view: request dialog (own-session picker, explicit foreign-id input), artifact list, digest-first artifact page with labeled collapsed prose panel (`products/operator-portal/web-ui`)
- [ ] manual live-check walkthrough recorded in the delivery log

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified
- [ ] living state docs updated (see spec `Impact` section)
- [ ] `CHANGELOG.md` entry added referencing the spec ID
- [ ] spec index in `docs/specs/README.md` updated
- [ ] spec status set to `delivered`
