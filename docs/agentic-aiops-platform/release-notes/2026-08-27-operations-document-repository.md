# v0.21.0 — Operations Document Repository (SPEC-039)

Date: 2026-08-27
Release type: minor (new document capability, three policy actions, and
three audit event types; no approval, HITL, or execution-path change)

## Summary

v0.21.0 opens R5 with the platform's first document-producing capability:
an **operations document repository** where team members generate durable
documents from the platform's own records and colleagues access them **by
role, not by per-document permission grants**. Phase 1 ships the substrate
— typed store, one-way draft→publish lifecycle, role-based access matrix,
provenance anchoring, document audit, portal Documents view — with the
**shift summary** as the first document type: a deterministic digest over
the cited sessions' kernel snapshots, confirmation decisions, execution
receipts, and evidence counts, with two-tier coverage (own sessions full,
foreign sessions metadata-only) and an optional clearly-labeled prose
layer generated from the digest alone. Two session-workspace add-ons
support the sharing workflow: owner session rename and copy-session-id.
Documents are immutable copies anchored to their source record ids —
role-wide visibility never opens a session — and cross-owner reads are
audited.

## What Changed

### The typed document substrate (R-1)

- New `OperationDocumentStore` in agent-service with memory and Postgres
  backends on the existing `AGENT_STATE_STORE_BACKEND` /
  `AGENT_STATE_DB_URL` knobs (idempotent DDL): immutable rows, one-way
  draft→publish lifecycle, cap 20 documents per owner with oldest-draft
  eviction, and a 30-day TTL sweep. Shared contract
  `operation-document.schema.json` defines the envelope (type, state,
  owner, label, provenance, type payload, `prose_status`).

### Role-based access matrix (R-2)

- New deny-by-default policy actions `documents:create` (create, publish,
  delete own documents) and `documents:read` (own drafts + all published),
  granted to `platform-admin`, `approver`, and `operator`; the policy
  matrix tests and the PROTECTED_ACTIONS boundary guard were extended, not
  weakened. No per-document ACL surface exists — publishing is the entire
  access decision.
- Agent routes under `/api/v2/documents` with structured rejections
  (403 coverage, 404 anti-enumeration, 409 double-publish) and gateway
  pass-through under `enforce_policy`; the gateway computes the caller's
  foreign coverage from their own `approvals:list` grant and forwards it
  as a trusted internal header, and agent-service fails closed on
  anything but `allowed`.

### Shift-summary digest (R-3)

- Deterministic `build_digest` over the four durable stores (kernel
  snapshot, `session_evidence`, `confirmation_records`,
  `execution_records`) with per-source degradation: own sessions get full
  coverage; foreign sessions get metadata only — and only when the caller
  holds the approvals inbox grant. Bounded input (≤20 session ids) and a
  provenance block anchoring every cited record id.

### Optional digest-only prose layer (R-4)

- Type-agnostic prose generation whose prompt contract receives the digest
  only — never transcripts. Hard timeout, fail-soft
  `prose_status=failed`, and `not_requested` when the creator opted out;
  the digest always stands alone.

### Document audit (R-5)

- `document_created` / `document_published` after every store mutation and
  `document_read` on cross-owner reads only — own reads stay unaudited.
  Fire-and-forget emission with forwarded `x-request-id`, matching the
  house audit posture. The canonical `audit-event.schema.json` closed
  vocabulary and the audit-service `EventType` lockstep gained the three
  types (the live check caught the missing enum registration before the
  release closed).

### Portal Documents view (R-6)

- New Documents entry in the Control section (document roles only):
  creation dialog with an own-session picker, foreign-id input, label,
  and prose toggle; Mine / Published tabs with type and state badges and
  cross-owner *created by …* attribution; digest-first document page
  where requested prose renders collapsed under the label *AI-generated
  prose (digest-only, may omit facts)* and failed prose renders a warning.

### Session rename (R-7 add-on)

- `PATCH /api/v2/sessions/{session_id}/title` (1–80 characters trimmed,
  owner-only, 404 anti-enumeration) behind the new `session:update`
  action granted everywhere `session:list` is; deliberately unaudited —
  titles are cosmetic. The portal adds inline rename in the session panel
  and the open-session header.

### Session-id reveal and copy (R-8 add-on)

- Portal-only: truncated session ids with the full value on hover and a
  one-click clipboard copy with a visible confirmation state, on every
  session-panel row and the open-session header — the hand-off path for
  citing a colleague's session in a shift summary.

## Verification

- `make verify` green at 0.21.0: all product test suites (gateway 253,
  portal 170 across 18 files, plus agent-service document store / digest /
  prose / API suites), kustomize overlays, policy bundle validation, and
  version lockstep.
- Delivery-gate live check (`shared/platform-ops/e2e/documents-demo.sh`,
  deterministic): role matrix denial, draft digest with provenance
  anchor, drafts owner-only until publish, one-way publish (409),
  cross-owner read with owner attribution, the three document audit
  events on the durable trail, and owner-only rename with 404/403
  posture — all passed. Browser walkthrough additionally verified the
  Documents view, creation dialog, publish, digest detail, session
  rename, and session-id copy confirmation state.
