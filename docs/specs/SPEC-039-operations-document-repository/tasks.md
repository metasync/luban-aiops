# SPEC-039 Tasks: Operations Document Repository (Phase 1: Shift Summaries)

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## Contract & Policy

- [ ] add `shared/shared-contracts/schemas/operation-document.schema.json` (envelope: `document_type`, `state`, owner, label, provenance, type payload, `prose_status`) (`shared/shared-contracts`)
- [ ] add `documents:create`, `documents:read`, `session:update` actions with `operator`/`approver`/`platform-admin` grants to the canonical policy bundle and run `make sync-policy` (`shared/shared-contracts/policies`)

## R-1: The typed document substrate

- [ ] `OperationDocumentStore` memory + Postgres backends: immutable rows, draft/published lifecycle, cap 20 per owner with oldest-eviction, 30-day TTL sweep, idempotent DDL (`products/agent-platform/src/agent_service/services/operation_documents.py`)
- [ ] store tests: lifecycle one-way publish, cap eviction, TTL sweep, backend parity, drafts owner-only at the query boundary (`products/agent-platform/tests/test_operation_documents_store.py`)

## R-2: Role-based access matrix

- [ ] agent routes `POST /api/v2/documents`, `GET /api/v2/documents` (mine / published scopes), `GET /api/v2/documents/{id}`, `POST /api/v2/documents/{id}/publish`, `DELETE /api/v2/documents/{id}` with structured rejections (`products/agent-platform/src/agent_service/api/v2/routes.py`)
- [ ] gateway pass-through routes behind `enforce_policy("documents:create"/"documents:read")` (`products/platform-gateway/src/platform_gateway/api/routes.py`)
- [ ] policy-matrix tests for the three new actions' grants/denials (`products/platform-gateway/tests/test_policy_matrix.py`)

## R-3: Shift summary assembly

- [ ] implement `build_digest` with own/foreign two-tier coverage and per-source degradation (`products/agent-platform/src/agent_service/services/shift_summary.py`)
- [ ] digest tests: own full-digest, foreign metadata-only gating, provenance ids present, degraded store sections, bounded input validation (`products/agent-platform/tests/test_shift_summary_digest.py`)

## R-4: Optional clearly-labeled prose layer

- [ ] type-agnostic prose generator with digest-only prompt contract, hard timeout, fail-soft `prose_status=failed` (`products/agent-platform/src/agent_service/services/document_prose.py`)
- [ ] prose tests: prompt receives digest only, timeout/error degrades to digest-only document (`products/agent-platform/tests/test_document_prose.py`)

## R-5: Audit events

- [ ] emit `document_created` / `document_published` after store operations and `document_read` on cross-owner reads, with forwarded `x-request-id` (`products/agent-platform/src/agent_service/services/audit_emitter.py` consumers)
- [ ] audit tests: event fields per type, own reads unaudited, cross-owner reads always audited, fire-and-forget non-blocking (`products/agent-platform/tests/test_operation_documents_api.py`)

## R-6: Portal Documents view

- [ ] Documents nav entry + view: creation dialog (own-session picker, foreign-id input, label, prose toggle), Mine / Published list with type badges and Publish action, digest-first document page with owner attribution and collapsed labeled prose panel (`products/operator-portal/web-ui`)
- [ ] manual live-check walkthrough recorded in the delivery log

## R-7 (add-on): Session rename

- [ ] `PATCH /api/v2/sessions/{session_id}/title` owner-only (1–80 chars, 404 foreign/unknown) + store update-title on both backends (`products/agent-platform`)
- [ ] gateway pass-through behind `enforce_policy("session:update")` (`products/platform-gateway`)
- [ ] rename tests: happy path, bounds, ownership 404s, list/detail reflect the new title (`products/agent-platform/tests/test_session_workspace.py`)
- [ ] portal inline rename in the session panel and session list (`products/operator-portal/web-ui`)

## R-8 (add-on): Session id reveal and copy

- [ ] session id (truncated, full on hover) with clipboard copy + confirmation state on session list items and the open-session header (`products/operator-portal/web-ui`)
- [ ] manual live-check walkthrough recorded in the delivery log

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified
- [ ] living state docs updated (see spec `Impact` section)
- [ ] `CHANGELOG.md` entry added referencing the spec ID
- [ ] spec index in `docs/specs/README.md` updated
- [ ] spec status set to `delivered`
