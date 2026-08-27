# SPEC-039 Plan: Operations Document Repository (Phase 1: Shift Summaries)

## Approach

Build the substrate vertically in agent-platform (typed document store
→ assembler → routes), then the gateway pass-through and policy
actions, then the portal Documents view and the two session add-ons.
The substrate is type-agnostic from day one — `document_type` rides
every record and the API shape — so the `incident_report` slice adds
an assembler and a rendering template, not a new store or surface.
The trusted digest is pure data assembly over existing stores; the
only new runtime dependency is the optional prose generation behind a
digest-only prompt contract. Everything degrades: unreadable stores
mark their digest section `unavailable`, failed prose yields a
digest-only document.

## Design Per Requirement

### R-1: The typed document substrate

- affected files: `products/agent-platform/src/agent_service/services/operation_documents.py`
  (store, new), Postgres DDL beside the confirmation/execution record
  tables, settings reuse `AGENT_STATE_STORE_BACKEND`/`AGENT_STATE_DB_URL`
- chosen approach: one `OperationDocumentStore` interface with memory
  + Postgres backends mirroring `confirmation_records`: immutable
  rows keyed by `document_id`, owner index, `state` column, cap 20
  per owner with oldest-eviction, 30-day TTL sweep on startup and
  access. New documents reuse the existing state-store knobs — no new
  configuration surface.
- alternatives rejected: a generic key-value blob store (loses
  typed querying/caps) and a separate product service (the source
  records live in agent-platform; extraction stays parked behind a
  recorded trigger).

### R-2: Role-based access matrix (no per-document ACLs)

- affected files: `shared/shared-contracts/policies/policy-default.yaml`,
  gateway pass-through routes, agent-service list/get filters
- chosen approach: `documents:create` (create/publish/delete own)
  and `documents:read` (list/get) granted to `operator`, `approver`,
  `platform-admin` in the default bundle; `make sync-policy` to
  consumers. The agent layer enforces the visibility matrix (drafts
  owner-only; published to all readers) exactly once at the store
  query boundary.
- alternatives rejected: per-document grant records (burden on the
  requester — the operating model this spec exists to avoid) and
  role-specific visibility per document (unneeded; the matrix is
  type-level and uniform in Phase 1).

### R-3: Shift summary assembly

- affected files: `products/agent-platform/src/agent_service/services/shift_summary.py`
  (new), consuming `session_store`, `confirmation_records`,
  `execution_records`, `evidence_store`
- chosen approach: `build_digest(requester_user_id, session_ids,
  can_view_foreign)` resolves ownership per session and branches into
  full digest (own) or metadata-level digest (foreign, gated by the
  caller's `approvals:list` flag passed from the route). Facts are
  copied verbatim; every entry carries source record ids.
- alternatives rejected: digest-on-read (documents must be immutable
  snapshots) and foreign coverage from titles/transcripts (violates
  the metadata-only posture).

### R-4: Optional clearly-labeled prose layer

- affected files: `products/agent-platform/src/agent_service/services/document_prose.py`
  (new, type-agnostic: takes the digest JSON of any document type)
- chosen approach: bounded digest-only prompt ("recap these facts for
  a teammate; state only what the facts contain"), the runtime's
  default model client with a hard timeout, attach with
  `prose_status=included`; any failure sets `prose_status=failed`
  and the document ships digest-only.
- alternatives rejected: feeding transcripts (defeats the fabrication
  posture) and per-document model selection (no demand).

### R-5: Audit events

- affected files: reuse the canonical fire-and-forget emitter (parity
  family); new event types `document_created`, `document_published`,
  `document_read`
- chosen approach: emit after the corresponding store operation
  succeeds; `document_read` fires only for cross-owner reads of
  published documents; forward `x-request-id` per SPEC-029.
- alternatives rejected: auditing own reads/deletes/renames — no
  cross-user surface is being policed there.

### R-6: Portal Documents view

- affected files: `products/operator-portal/web-ui/` (new Documents
  view beside Approvals)
- chosen approach: creation dialog (own-session picker, explicit
  foreign-id input, label, prose toggle), Mine / Published list with
  type badges and Publish action, digest-first document page with
  owner attribution and collapsed labeled prose panel; reuse the antd
  dark-theme custom properties and existing fetch/error patterns.
- alternatives rejected: embedding documents under Approvals
  (different mental model; Approvals stays decision-centric).

### R-7 (add-on): Session rename

- affected files: `products/agent-platform/src/agent_service/api/v2/routes.py`
  (`PATCH /sessions/{id}/title`), `session_store` update-title
  method on both backends, gateway pass-through behind
  `session:update`, portal inline rename
- chosen approach: owner-only, 1–80 char trimmed title, 404 for
  foreign/unknown ids; supersedes the SPEC-022 server-minted set-once
  title (the minted title remains the default until renamed).
- alternatives rejected: full session metadata editing (only the
  title has a demonstrated need).

### R-8 (add-on): Session id reveal and copy

- affected files: `products/operator-portal/web-ui/` session list
  items and open-session header only
- chosen approach: truncated id with full value on hover +
  `navigator.clipboard` copy action with visible confirmation; the id
  already rides the existing session surfaces, so this is portal-only.

## Sequencing And Dependencies

1. Contracts first — `operation-document.schema.json` + the three
   policy actions in the canonical bundle (`make sync-policy`) —
   depends on nothing
2. Document store (R-1) with unit tests — depends on 1
3. Shift-summary assembler (R-3) with unit tests — depends on 2
4. Agent routes + audit emission (R-2 backend, R-5) — depends on 2, 3
5. Prose layer (R-4) — depends on 3
6. Gateway pass-through + policy-matrix tests (R-2) — depends on 1, 4
7. Portal Documents view (R-6) — depends on 6
8. Session rename end to end (R-7) — depends on 1 (policy action)
9. Session id copy (R-8) — depends on nothing
10. Docs, version, delivery bookkeeping — depends on all

## Test Strategy

- unit tests: store caps/TTL/sweep/lifecycle and backend parity;
  digest assembly (own vs foreign tiers, degraded stores); prose
  prompt contract (digest-only input) and fail-soft degradation;
  visibility matrix at the store query boundary (drafts owner-only)
- contract tests: document responses validate against
  `operation-document.schema.json`; policy-matrix tests cover
  `documents:create`/`documents:read`/`session:update`
  grants/denials in platform-gateway
- integration / overlay validation: `make verify` (all suites,
  overlays, policy validation, version lockstep); delivery-gate live
  check creates a draft, publishes it, reads it as a second operator
  (cross-owner `document_read` audited), and exercises rename + id
  copy in the portal

## Rollout And Migration

- deployment: no new services; agent-platform and platform-gateway
  images plus the portal static bundle; policy bundle re-synced; no
  new secrets
- backward compatibility: purely additive surface (new routes, new
  schema, new actions); session list/detail shapes unchanged except
  title semantics (a renamed title simply replaces the minted one)
- rollback: drop the three policy actions (instant denial) and revert
  the images; the `operation_documents` table stays inert
