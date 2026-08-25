# SPEC-031 Plan: Approval Inbox and Persistent Confirmation Cards

## Approach

One durable data model first (R-1), everything else reads it: owner-side
transcript cards (R-2), the approver inbox (R-3), and race-resilient
resolution (R-4) are projections of the same session-scoped confirmation
records; the portal view (R-5) consumes the resulting API surfaces. The
kernel parking mechanism and the gateway tier bridge are untouched except
where they must read/write the new records — SPEC-030 enforcement semantics
stay exactly as delivered.

## Design Per Requirement

### R-1: Durable confirmation lifecycle records

- affected files / modules: new
  `products/agent-platform/src/agent_service/services/confirmation_records.py`,
  `services/hitl_confirmations.py`, `api/v2/routes.py` (park/confirm paths),
  state-store bootstrap
- chosen approach: a `confirmation_records` table in the agent-platform
  Postgres database (same `AGENT_STATE_DB_URL` posture as the SPEC-016/017
  state store and SPEC-025 evidence store — no new infra). Writes: `park`
  inserts the pending record synchronously before the `confirmation_request`
  frame is yielded; `resolve`/`expire` update status + decider + timestamp
  before `confirmation_result` flows. The in-memory `ConfirmationRegistry`
  remains the hot path for the single-flight claim; on startup (and on a
  registry miss) pending records rehydrate from the table so restarts and
  replicas converge. Per-session cap 50, evict oldest; cascade on session
  delete alongside the state snapshot.
- alternatives considered and why rejected: (a) Redis-persisted registry —
  rejected: history queries (inbox) need ordered, bounded, durable reads and
  Redis is reserved for the kernel message bus per SPEC-027; (b) projecting
  from the audit trail — rejected: audit is role-gated, parameter-redacted,
  and owned by audit-service; the inbox needs a first-class low-latency
  read surface.

### R-2: Persistent cards in the owner transcript

- affected files / modules: `api/v2/routes.py` session-detail route,
  `schemas/v2.py`, gateway `sessions.py` relay, portal transcript rendering
- chosen approach: additive `confirmations` field on the session detail
  payload (ordered records from R-1 with status/decider/timestamps and the
  parked-call payload) — the chat-text transcript stays byte-identical. The
  portal merges these into the turn timeline; decided cards render read-only
  with outcome attribution.
- alternatives considered: replaying confirmation frames into the chat-text
  transcript — rejected: couples card state to memory-snapshot fidelity and
  breaks the SPEC-022 transcript contract.

### R-3: Approvals inbox API

- affected files / modules: new agent-platform
  `GET /api/v2/confirmations` (status filter, cross-session, most recent
  first, 30-day history window), new gateway route `GET /api/v1/approvals/inbox`
  (`api/routes/approvals.py`), policy bundle (`approvals:list` action rule),
  agent-client
- chosen approach: the gateway enforces `approvals:list` via
  `enforce_policy`, then relays to agent-platform, which scopes results to
  records whose matched tier's `decided_by_roles` intersect the caller's
  roles (the gateway forwards the caller's roles header as it does today).
  Items are metadata-only: session id + server-minted title, owner username,
  pending calls as parked, status, decider, timestamps — never transcript
  text. The pending-confirmation endpoint already supplies the decision
  surface an inbox item opens into.
- alternatives considered: gateway-side aggregation from audit-service —
  rejected (redaction + query posture, see R-1); granting approvers
  `session:list` cross-user — rejected: violates SPEC-022 owner scoping.

### R-4: Race-resilient resolution semantics

- affected files / modules: `services/hitl_confirmations.py`
  (`ConfirmationAlreadyResolved` carrying decider/decision/decided-at),
  `api/v2/routes.py` confirm route, gateway `chat.py`/`gateway_service.py`
  passthrough mapping, portal decide handler
- chosen approach: the registry keeps its single-flight `claim`; when a
  confirm hits a resolved (or claimed-then-resolved) record, agent-service
  answers `409 already_resolved` with the durable outcome body instead of
  404; the gateway passes that structured body through untouched and the
  portal flips the card to the resolved state. `ConfirmationNotFound` keeps
  its 404 for genuinely unknown ids (anti-enumeration preserved).
- alternatives considered: optimistic retry UX — rejected: exactly-once
  semantics must be visible, not retried.

### R-5: Portal approvals view and persistent cards

- affected files / modules: `web-ui/app/src/views/control/ApprovalsView.tsx`
  (new), nav wiring in `App.tsx`, `api/client.ts`, `chat/ChatView.tsx`
  (persisted card rendering), `useChatStream` card-merge logic
- chosen approach: Approvals nav entry rendered only when the caller holds a
  decider role (reuse `hasAnyRole` + `APPROVAL_DECIDER_ROLES`); the view
  polls the inbox on focus + interval (30s), badges the pending count, lists
  pending-first then history, and reuses `ConfirmationCardView` for the
  decision panel so tier badges and read-only semantics stay identical to
  the owner-side card. Decide calls go through the existing confirm client
  path; `already_resolved` responses merge the outcome into local state.
- alternatives considered: SSE push for inbox updates — rejected (non-goal);
  a separate card component — rejected: two confirmation card UIs would
  drift.

## Sequencing And Dependencies

1. R-1 durable records (store + park/resolve writes + rehydration) — depends on nothing
2. R-4 race-resilient confirm responses — depends on 1
3. R-2 session-detail confirmation surface — depends on 1
4. R-3 inbox endpoint + `approvals:list` bundle rule + `sync-policy` — depends on 1
5. R-5 portal view + persisted owner cards — depends on 2, 3, 4
6. e2e extension + docs — depends on 5

## Test Strategy

- unit tests: confirmation-records store (write order, cap/eviction, session
  cascade, rehydration); registry race paths incl. `already_resolved`;
  session-detail confirmations payload; gateway inbox route (role gating,
  metadata-only shape, passthrough of the 409 body); policy engine test for
  the `approvals:list` rule
- contract tests: confirmation-record shape in shared-contracts validates;
  session-detail schema v8→v9 additive bump stays backward compatible
- integration / overlay validation: `mutating-demo.sh` HITL leg extended —
  after approval, assert (a) the owner session detail carries the decided
  card, (b) the approver inbox lists the item with outcome, (c) a second
  approve attempt returns `already_resolved`; `make verify` gate unchanged

## Rollout And Migration

- schema migration: `confirmation_records` created idempotently by the
  agent-platform startup migration path (same mechanism as the evidence
  store tables); no data migration (no prior records exist)
- bundle change: additive `approvals:list` rule; `make sync-policy` +
  `make validate-policy`; no existing grant is altered
- backward compatibility: session-detail and stream payloads are additive;
  older portals ignore the new fields
- rollback approach: revert images; the table is inert without the new
  code; the additive bundle rule can stay or be removed independently
