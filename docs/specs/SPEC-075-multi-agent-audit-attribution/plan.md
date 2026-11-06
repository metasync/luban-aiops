# SPEC-075 Plan: Multi-Agent Audit & Attribution (Agent-Role Dimension in the Durable Audit Trail)

> **BINDING** — approved 2026-11-05. The operator ratified all seven Open Questions in
> [`spec.md`](spec.md) **exactly as recommended**, so the resolutions assumed below are binding:
> a new `agent_role` **dimension** on existing events (the `event_type` enum stays closed); the
> agent-platform emitter seam **wired but inert**; an additive `session-evidence` turn field
> **only**; **no** portal filter and **no** summary facet; an additive field **within audit-event
> v1** (no title bump) with **no new ADR**; unit + contract + emitter-parity + reachability/no-diff
> evidence. Implementation is authorized to *begin* — not to merge, commit/push, deploy, or
> version-bump (separate gates).

## Approach

Phase 4 adds the second top-level **attribution dimension** to the audit-event envelope, beside the
`delegation_mode` SPEC-070 added: an optional `agent_role` answering *which role acted*, drawn from
the closed SPEC-073 vocabulary and **omitted when absent** so every event from today's unscoped
single-agent path audits byte-identically. The change is **additive and inert**, and it is
deliberately a *clone of the `delegation_mode` mechanism* — the same schema field shape, the same
model + serializer omission, the same store column/index/filter, the same query-API parameter, and
the same emitter-parity tuple — so the machinery is mechanical and the risk is bounded by two
precedents (SPEC-070's dimension, SPEC-073/074's inert discipline). Per OQ-2 the agent-platform
emitter seam is wired to SPEC-073's `current_agent_role_value()`, which returns `None` on every
deployed turn, so the projection path exists end-to-end while remaining byte-identical. The work
groups into six stages mirroring R-1…R-6.

## Design Per Requirement

### R-1: Additive `agent_role` dimension in `audit-event.schema.json`

- affected files: `shared/shared-contracts/schemas/audit-event.schema.json`.
- chosen approach: add an optional top-level `agent_role` property — `{"type":"string","enum":
  ["diagnostician","orchestrator","executor"]}` — with a description mirroring `delegation_mode`'s
  ("SPEC-075: which agent-role acted, from the closed SPEC-073 vocabulary; omitted when absent, and
  absence is not an assertion"). Leave it out of `required`; keep `additionalProperties: false`;
  leave the title at "(v1)" per OQ-6 (SPEC-070 added `delegation_mode` the same way). A parity guard
  pins the enum to the SPEC-073 agent-role vocabulary (single source of truth).
- alternatives rejected: new `event_type` values (the enum is closed and additive types ripple
  through every emitter, the portal drift guard, and the parity tests for no gain — OQ-1); a
  free-form `string` (loses the closed-vocabulary guarantee SPEC-073 R-1 established); a v2 title
  bump (the `delegation_mode` precedent is an additive field within v1 — OQ-6).

### R-2: Audit-service model, store, and query dimension

- affected files: `products/audit-service/src/audit_service/schemas/audit.py`,
  `products/audit-service/src/audit_service/services/audit_store.py`, and the query/reporting API
  route that parses `AuditQuery` filters.
- chosen approach: add `AgentRole = Literal["diagnostician","orchestrator","executor"]`;
  `AuditEvent.agent_role: AgentRole | None = None` and `AuditQuery.agent_role: AgentRole | None =
  None`; extend the `model_serializer` omission so `agent_role` is popped when `None` (mirroring
  `_omit_unknown_delegation`). In the store: `ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS
  agent_role TEXT;` + `CREATE INDEX IF NOT EXISTS idx_audit_agent_role ON audit_events
  (agent_role);`, add `agent_role` to the INSERT columns/values, `_ROW_COLUMNS`, the row→model
  mapping, the JSON insert path, the in-memory filter (`if filters.agent_role and event.agent_role
  != filters.agent_role: return False`), and the SQL WHERE (`if filters.agent_role:
  where.append("agent_role = %(agent_role)s")`). The route accepts `?agent_role=` and rejects an
  out-of-vocabulary value exactly as `delegation_mode=invalid` is rejected today.
- alternatives rejected: carrying `agent_role` inside `details` JSONB (not a first-class indexed
  column, so not filterable the way `delegation_mode` is — inconsistent); a new event type (OQ-1).

### R-3: Emitter parity across the audit-emitting services

> **Implementation correction (2026-11-05).** This stage named *seven* emitter replicas including
> `incident-service`; implementation verified the parity family is **six**. `incident-service`'s
> `audit_emitter.py` is a triage `AuditConnector._build_event` with no `build_audit_event`, and it
> never carried `delegation_mode`, so it is not an `AuditEmitterParityTest.EMITTERS` member and is
> correctly left untouched (confirmed against `products/tool-gateway/tests/test_module_parity.py`).

- affected files: the canonical `services/audit_emitter.py` replicated byte-for-byte across the
  **six** emitter services — `products/agent-platform` (`agent_service`), `execution-runtime`
  (`execution_runtime`), `identity-broker` (`identity_service`), `platform-gateway`
  (`platform_gateway`), `skills-hub` (`skills_hub`), `tool-gateway` (`tool_gateway`).
- chosen approach: add `agent_role: str | None = None` to the `build_audit_event` signature and
  `("agent_role", agent_role)` to the omit-when-`None` field tuple (right beside
  `("delegation_mode", delegation_mode)`), keeping every replica byte-for-byte identical so
  `AuditEmitterParityTest` still passes. The emitter never validates or coerces the value — the
  audit-service model + schema own the vocabulary.
- alternatives rejected: emitting `agent_role` from agent-platform only (breaks the byte-identical
  parity family); validating at the emitter (duplicates the schema/model vocabulary guard).

### R-4: Evidence-turn attribution (OQ-3 scope)

- affected files: `shared/shared-contracts/schemas/session-evidence.schema.json`, the
  `evidence_turns` item in `shared/shared-contracts/schemas/agent-session.schema.json`, and the
  agent-platform `session_evidence` persistence path.
- chosen approach: add an optional `agent_role` (enum-closed to the SPEC-073 vocabulary) to the
  session-evidence turn, omitted when absent so a legacy turn is byte-identical and replays with no
  empty artifact; persist it from the same `current_agent_role_value()` seed when a turn is scoped.
  Per OQ-3 the transcript-turn projection and any concurrent-multi-agent transcript re-modelling are
  **deferred to phase 5/6** (no producer until phase 5; the multi-agent stream is a phase-6 contract
  concern) — the deferral and its trigger are recorded in the spec and the design note.
- alternatives rejected: landing a transcript-turn field now (consumerless until phase 5 — OQ-3);
  re-modelling the single-turn transcript for concurrent members (phase 6, memo §3.1(b)).

### R-5: Inertness, the producer seam, and four-point-gate parity

- affected files: the agent-platform audit-emitter call sites (thread `current_agent_role_value()`),
  a new reachability-guard test, and no-diff tests.
- chosen approach: per OQ-2, wire the agent-platform emitter seam to pass
  `agent_role=current_agent_role_value()` (SPEC-073) — byte-identical today because `AGENT_ROLE`
  defaults to `None` on the unscoped single-agent path. A reachability guard asserts no code path
  reachable from a deployed emitter passes a non-`None` `agent_role` (equivalently, that
  `current_agent_role_value()` is `None` on every deployed turn — the SPEC-073 R-5 / SPEC-074 R-5
  guard, audit-side). A no-diff test captures an unscoped event before/after and asserts it is
  byte-identical. The four-point-gate mapping is recorded: point 1 (audit) **strengthened**; points
  2 (identity — the role stays a label beside the one delegated token, no new principal/claim/edge),
  3 (read-only posture), and 4 (no agentscope types through the v2 contract — a plain string enum)
  unchanged.
- alternatives rejected: leaving the seam unwired (pure substrate — re-opens the emitter in phase 5
  and leaves SPEC-073's seed unconnected — OQ-2); a live end-to-end attribution test (no producer
  binds a role until phase 5).

### R-6: Documentation and contract reconciliation

- affected files: `docs/agentic-aiops-platform/authorization-matrix.md`,
  `docs/agentic-aiops-platform/identity-and-authorization-design.md` (phase-boundary note), and the
  audit-vocabulary documentation. **No** portal (`constants.ts` / `AuditView.tsx`) and **no**
  `audit-summary.schema.json` change.
- chosen approach: document the attribution triple as complete — an audited event may carry
  `agent_role` (which role acted) beside `subject`/`username` (on whose behalf) and `delegation_mode`
  (under which delegation) — and state that the dimension is **descriptive**, narrowing nothing (the
  prescriptive axis is SPEC-074). Record the additive-within-v1 revision (OQ-6), and record the
  OQ-4 (no portal filter — `delegation_mode` has none) and OQ-5 (no summary facet — consumerless
  until data exists) deferrals with their reasons. Confirm `agent-stream-event.schema.json` and
  `execution-request.schema.json` stay byte-unchanged.
- alternatives rejected: a portal filter/column now (a consumerless UI surface — OQ-4); a summary
  facet now (OQ-5).

## Sequencing And Dependencies

1. **Stage 1 — contract (R-1)** — depends on nothing; the additive `agent_role` field + the
   enum-parity guard are the contract anchor.
2. **Stage 2 — audit-service model/store/query (R-2)** — depends on Stage 1; lands the model field +
   serializer omission, the store column/index/filters, and the query-API parameter.
3. **Stage 3 — emitter parity (R-3)** — depends on Stage 1; adds the field tuple to all six
   byte-identical emitter replicas.
4. **Stage 4 — producer seam (R-5, OQ-2)** — depends on Stages 2–3; wires agent-platform's
   `current_agent_role_value()` into its emitter (inert — `None` on every deployed turn).
5. **Stage 5 — evidence-turn attribution (R-4, OQ-3)** — depends on Stage 1; the additive
   session-evidence field, transcript projection deferred.
6. **Stage 6 — inertness guards (R-5)** — depends on Stages 3–4; the reachability + no-diff guards
   and the four-point-gate mapping.
7. **Stage 7 — documentation (R-6)** — depends on Stages 1–2; the matrix + design phase-boundary
   note + the OQ-4/OQ-5/OQ-6 deferral records.
8. **Stage 8 — verify + reconcile** — depends on all; `make verify` (incl. the audit-contract target,
   `AuditEmitterParityTest`, `validate-version`), then index / roadmap / CHANGELOG on delivery.

## Test Strategy

- unit tests: `AuditEvent` with and without `agent_role` (the field is omitted, never null, when
  `None`); `AuditQuery.agent_role` filtering; the store round-trip (column, in-memory + SQL filters,
  row→model mapping); the query API `?agent_role=` including out-of-vocabulary rejection.
- contract tests: the `audit-event.schema.json` diff is additive only; the existing model↔contract
  property-parity test covers the new field; an enum-lockstep guard asserts the audit `agent_role`
  enum equals the SPEC-073 vocabulary; `session-evidence.schema.json` additive;
  `agent-stream-event.schema.json` and `execution-request.schema.json` byte-unchanged.
- parity tests: `AuditEmitterParityTest` (all six replicas byte-identical with the new tuple
  entry); the "optional identity fields are omitted" test extended to `agent_role`.
- guard tests: the reachability scan (no deployed emitter threads a non-`None` `agent_role`;
  `current_agent_role_value()` is `None` on every deployed path) and the no-diff capture (an unscoped
  event is byte-identical before/after).
- integration / overlay validation: the audit-service integration contract extended with an
  `agent_role` round-trip (stored, filtered, returned verbatim); root `make verify` green.

## Rollout And Migration

- deployment or configuration changes: the additive `ALTER TABLE … ADD COLUMN IF NOT EXISTS
  agent_role TEXT` migration runs idempotently in the audit-store DDL (exactly like
  `delegation_mode`); **no** env var or feature flag is added, and the dimension is inert (no
  producer binds a role). A pod restart picks up the new code and the migration; no event changes.
- backward compatibility: legacy rows read back `agent_role is None`; an event emitted without the
  field is byte-identical to today; the schema field is additive-optional, so nothing that validated
  before fails now.
- rollback approach: revert the schema/model/store/emitter/doc commits. The `ADD COLUMN IF NOT
  EXISTS` is idempotent and a leftover nullable column is harmless (the `delegation_mode` column is
  retained the same way), so rollback has no runtime effect beyond removing the inert capability.
