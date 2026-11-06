# SPEC-075 Tasks: Multi-Agent Audit & Attribution (Agent-Role Dimension in the Durable Audit Trail)

> **BINDING** — approved 2026-11-05; all seven Open Questions in [`spec.md`](spec.md) ratified by
> the operator exactly as recommended, provisional banner lifted.
> Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs. Phase 4 is
> an **inert attribution dimension** — every task is provable by unit/contract/parity tests with no
> deployed caller binding a non-`None` agent-role and no change to any unscoped audit event. The
> mechanism is a deliberate clone of SPEC-070's `delegation_mode` dimension.

## R-1: Additive `agent_role` dimension in the audit-event contract

- [x] Add an optional top-level `agent_role` string property to `audit-event.schema.json`,
      `enum`-closed to `diagnostician`/`orchestrator`/`executor`, **not** in `required`,
      `additionalProperties` still `false`, title stays "(v1)" (OQ-6), with a description mirroring
      `delegation_mode`'s omission semantics (`shared/shared-contracts/schemas/audit-event.schema.json`)
- [x] Enum-parity guard: the audit `agent_role` enum is **exactly** the SPEC-073 agent-role
      vocabulary (single source of truth — the attribution dimension cannot drift from the
      identity/policy vocabulary)
- [x] Contract test: the change is additive only (no required key added, no existing field's
      semantics changed, `delegation_mode` untouched)

## R-2: Audit-service model, store, and query dimension

- [x] Add `AgentRole = Literal["diagnostician","orchestrator","executor"]`,
      `AuditEvent.agent_role: AgentRole | None = None`, and
      `AuditQuery.agent_role: AgentRole | None = None`; extend the `model_serializer` to pop
      `agent_role` when `None` (mirror `_omit_unknown_delegation`)
      (`products/audit-service/src/audit_service/schemas/audit.py`)
- [x] Store DDL + write path: `ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS agent_role TEXT;`
      + `CREATE INDEX IF NOT EXISTS idx_audit_agent_role ON audit_events (agent_role);`; add
      `agent_role` to the INSERT columns/values, `_ROW_COLUMNS`, the row→model mapping, and the JSON
      insert path (`products/audit-service/src/audit_service/services/audit_store.py`)
- [x] Store filters: the in-memory filter and the SQL WHERE clause for `agent_role` (compose with
      the existing `username`/`session_id`/`event_type`/`outcome`/`delegation_mode` filters; empty =
      unconstrained) (`.../audit_store.py`)
- [x] Query API: accept `?agent_role=` and reject an out-of-vocabulary value exactly as
      `delegation_mode=invalid` is rejected today (the audit query/reporting route)
- [x] Tests: an event without `agent_role` stores/returns with the field **absent** (never null); a
      legacy row reads back `agent_role is None`; `?agent_role=diagnostician` filters; an invalid
      value is rejected; the model↔contract property-parity test covers the new field
      (`products/audit-service/tests/`)

## R-3: Emitter parity across the six audit-emitting services

> **Implementation correction (2026-11-05).** The draft named *seven* services including
> `incident-service`; the parity family is **six**. `incident-service`'s `audit_emitter.py` is a
> triage `AuditConnector._build_event` with no `build_audit_event` and it never carried
> `delegation_mode`, so it is not an `AuditEmitterParityTest.EMITTERS` member and stays untouched
> (confirmed against `products/tool-gateway/tests/test_module_parity.py`).

- [x] Add `agent_role: str | None = None` to `build_audit_event` and `("agent_role", agent_role)` to
      the omit-when-`None` tuple (beside `("delegation_mode", delegation_mode)`) in the canonical
      emitter, replicated **byte-for-byte** across all six services
      (`products/{agent-platform,execution-runtime,identity-broker,platform-gateway,skills-hub,tool-gateway}/src/*/services/audit_emitter.py`)
- [x] `AuditEmitterParityTest` passes (all replicas byte-identical with the new tuple entry); the
      "optional identity fields are omitted" test extended to assert `agent_role` is omitted when
      `None` (byte-identical payload)

## R-4: Evidence-turn attribution (OQ-3 scope)

- [x] Add an optional `agent_role` (enum-closed to the SPEC-073 vocabulary) to the session-evidence
      turn (`shared/shared-contracts/schemas/session-evidence.schema.json`) and the `evidence_turns`
      item in `agent-session.schema.json`; a turn stored without it is byte-identical
- [x] Persist `agent_role` on the evidence turn from the `current_agent_role_value()` seed when a
      turn is scoped; a legacy turn replays with no empty artifact (agent-platform `session_evidence`
      persistence path)
- [x] Record the OQ-3 deferral: the transcript-turn projection and any concurrent-multi-agent
      transcript re-modelling stay **deferred to phase 5/6** (no producer until phase 5; the
      multi-agent stream is a phase-6 contract concern)

## R-5: Inertness, the producer seam, and four-point-gate parity

- [x] Per OQ-2, wire the agent-platform emitter seam to pass `agent_role=current_agent_role_value()`
      (SPEC-073) — byte-identical today because `AGENT_ROLE` defaults to `None` on every deployed
      unscoped turn (agent-platform audit-emitter call sites)
- [x] Reachability guard: no code path reachable from a deployed emitter passes a non-`None`
      `agent_role` (equivalently, `current_agent_role_value()` is `None` on every deployed path) —
      the SPEC-073 R-5 / SPEC-074 R-5 guard, audit-side
- [x] No-diff test: an unscoped audit event captured before/after is byte-identical; the full
      audit-service suite and every emitter suite pass unchanged with the dimension present but
      unexercised
- [x] Record the four-point-gate mapping (point 1 audit **strengthened**; points 2 identity / 3
      read-only posture / 4 no agentscope types on the v2 contract unchanged)
- [x] Root `make verify` green (incl. the audit-contract target, `AuditEmitterParityTest`,
      `validate-version`)

## R-6: Documentation and contract reconciliation

- [x] Document the completed attribution triple — `agent_role` (which role acted) beside
      `subject`/`username` (on whose behalf) and `delegation_mode` (under which delegation) — in the
      authorization matrix; state the dimension is **descriptive** and narrows nothing (the
      prescriptive axis is SPEC-074) (`docs/agentic-aiops-platform/authorization-matrix.md`)
- [x] Update the phase-boundary note to record phase 4 delivered
      (`docs/agentic-aiops-platform/identity-and-authorization-design.md`)
- [x] Record the OQ-4 (no portal filter — `delegation_mode` has none), OQ-5 (no summary facet —
      consumerless until data exists), and OQ-6 (additive field within audit-event v1, no new ADR)
      decisions; confirm `agent-stream-event.schema.json` and `execution-request.schema.json` stay
      byte-unchanged

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified (R-1…R-6)
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing SPEC-075
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
- [x] confirm no deployed emitter threads a non-`None` `agent_role`, every unscoped audit event is
      byte-identical, the `event_type` enum is unchanged (closed), and no contract field beyond the
      additive `agent_role` dimension (audit-event + session-evidence) changed (phase-4 inertness)
