# SPEC-075: Multi-Agent Audit & Attribution (Agent-Role Dimension in the Durable Audit Trail)

## Status

- status: `delivered`
- owner: chi
- created: 2026-11-05
- approved: 2026-11-05 (all seven Open Questions ratified by the operator **exactly as
  recommended** — a new `agent_role` **dimension** on existing events with the `event_type` enum
  left **closed**; the agent-platform emitter seam **wired but inert**; an additive
  `session-evidence` turn field **only**; **no** portal filter and **no** summary facet; an additive
  field **within audit-event v1** (no title bump) with **no new ADR**; unit + contract +
  emitter-parity + reachability/no-diff evidence. See `## Open Questions — resolved`.)
- delivered: 2026-11-05 as **v0.56.0** — R-1…R-6 implemented as an **inert, additive `agent_role` attribution
  dimension** (the optional enum-closed field on `audit-event.schema.json` + the SPEC-025 evidence
  turn, threaded through the `AuditEvent`/`AuditQuery` model, the audit-store column/index/filter,
  the **six**-emitter parity family, and the agent-platform emitter seam wired to SPEC-073's
  `current_agent_role_value()`); byte-identical today because no deployed caller binds a non-`None`
  role. Full agent-platform suite **1716 green** (incl. five new `TestSpec075AuditAttribution`
  guards), audit-service **149**, all-product `make test` **4036**, root `make verify` green
  end-to-end (portal **546**; the SPEC-063 `execution-failure-test` campaign **795 passed, exit 0**
  in 0:38:11). **Released as v0.56.0** — the `CHANGELOG.md` entry is closed into
  `## 0.56.0 — 2026-11-05`; the push remains a separate operator gate.
- release slice: the **multi-agent / bounded-autonomy program** — phase 4 of the phased SPEC
  series [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md) gates
  ([memo](../../workspace/multi-agent-orchestration-spike.md) §7 step 4, §4.3). Delivered as
  **v0.56.0** (2026-11-05), following the SPEC-070/071/072/073/074 minor-bump pattern.
- related ADRs: [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md)
  (`accepted` 2026-11-03 — the phased series' §4.3 "audit & attribution" leg; **Decision 4**'s
  role-scoped agents must be *attributable* in audit for the four-point gate's point 1 — "audit
  preserved" — to hold once phase 5 binds roles);
  [ADR-0010](../../adr/0010-signed-execution-envelopes-declare-authority-provenance.md)
  (**provenance rides the fact** — the attribution model this spec projects into the durable
  record);
  [ADR-0004](../../adr/0004-broker-mediated-token-delegation.md) (the *one* identity edge — the
  agent-role is an attribution **label** beside the token, never a new principal, claim, or edge).
  **No new ADR is expected**: ADR-0017's §4.3 already names the audit-attribution leg; this spec
  makes it concrete and additive (see OQ-6 on the schema revision).
- extends: [SPEC-013](../SPEC-013-durable-audit-trail/spec.md) (the canonical audit-event
  envelope + the closed `event_type` vocabulary), [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)
  (the **`delegation_mode` sibling dimension** — the exact additive-optional-field precedent this
  spec mirrors), [SPEC-025](../SPEC-025-evidence-persistence-in-transcripts/spec.md) (the `session_evidence`
  turn model), [SPEC-039](../SPEC-039-operations-document-repository/spec.md) /
  [SPEC-022](../SPEC-022-multi-session-operator-workspace/spec.md) (the transcript/session record),
  [SPEC-029](../SPEC-029-skills-usage-audit-trail/spec.md) /
  [SPEC-047](../SPEC-047-audit-summary-drilldown/spec.md) (the audit-vocabulary + query-filter
  extension precedent), [SPEC-054](../SPEC-054-action-approval-and-change-request-card/spec.md) (the
  `approval_kind` **additive-optional-field-when-a-consumer-exists** pattern SPEC-073 named for
  this phase), and [SPEC-073](../SPEC-073-role-scoped-agent-identity/spec.md) (the closed
  agent-role vocabulary + the `staged_by_role` / `current_agent_role_value()` producer seed this
  spec projects) and [SPEC-074](../SPEC-074-policy-role-axis/spec.md) (the policy-axis sibling).

> SDD note: `spec.md` was drafted first and carried **seven Open Questions**, all ratified by the
> operator **2026-11-05** exactly as recommended (see `## Open Questions — resolved`). Approval
> authorizes the [plan](plan.md) / [tasks](tasks.md) — now written and **binding** — and lets
> implementation **begin**. It does **not** authorize a merge, commit/push, deployment, or a version
> bump; those stay separate boundaries, and the standing "review before any merge/deploy"
> constraint governs. This is phase 4 of the series: **bounded autonomous diagnosis** (§5, the loop
> that first *binds* roles and produces live attribution) and the **v2 multi-agent contract**
> (§4.5, any wire framing of the role) are separate later specs and are explicitly out of scope
> here.

## Summary

Land the **agent-role** as an explicit, first-class **attribution dimension in the durable audit
trail** — the §4.3 leg of ADR-0017's phased series that SPEC-073 and SPEC-074 both deliberately
deferred to phase 4. The memo's attribution triple is *which **role** acted, on whose **behalf**,
under which **delegation***. Two legs already exist as top-level audit-event fields: `subject` /
`username` (on whose behalf) and `delegation_mode` (under which delegation, SPEC-070). The missing
leg — **which role acted** — has no field today: SPEC-073's `staged_by_role` provenance is
kernel-internal and ephemeral (`repr=False`, "NEVER persisted to the durable card record … the
wire/audit projection is deferred to phase 4"), and SPEC-074's policy axis understands an
agent-role but projects nothing to audit ("audit — none in phase 3").

Phase 4 adds that leg as an **additive, inert** optional `agent_role` field on the audit-event
envelope — drawn from the closed SPEC-073 vocabulary (`diagnostician`, `orchestrator`,
`executor`), omitted when absent so every event from today's unscoped single-agent path audits
**byte-identically** — and threads it through the same machinery `delegation_mode` already rides:
the `AuditEvent` / `AuditQuery` model, the audit-store column/index/filter/insert, the canonical
fire-and-forget emitter parity family, and the contract-parity tests. Like SPEC-070/073/074, it
ships **inert**: no deployed caller binds a non-`None` `AGENT_ROLE` yet (that producer is phase 5),
so `current_agent_role_value()` returns `None` on every live path and the field is never emitted.
The result is that when phase 5 first binds roles and fans out concurrent members, each member's
audited action is **already attributable to its role** — gate point 1 ("audit preserved") holds by
construction rather than being retro-fitted onto a running loop.

## Motivation

- **The memo requires role attribution in audit, and names it phase 4.** memo §4.3: "Multi-agent
  needs: which **role** acted, on whose **behalf**, under which **delegation** — and member
  activity must be captured even though 'the leader only ever sees the summary' … This likely
  extends the audit vocabulary (a new dimension on existing events, or new event types) and the
  SPEC-025 evidence / SPEC-039 transcript model so a member's tool calls remain reconstructable."
  memo §7 step 4 makes it a discrete SPEC: "multi-agent audit & attribution (§4.3): the
  audit/evidence/transcript extensions, keeping member activity reconstructable."
- **Both prior phases explicitly handed this to phase 4.** SPEC-073 Non-Goals: "Multi-agent audit
  & attribution (memo §4.3) — new audit dimensions/event types so member activity is
  reconstructable, and the SPEC-025 evidence / SPEC-039 transcript extensions. **Phase 4.**" And
  its OQ: "a phase-2 role label has no enforcement consumer yet (policy axis = phase 3, audit
  projection = phase 4). **Phase 4 adds the additive optional field when a real consumer exists,
  following the `approval_kind` pattern.**" SPEC-074 Impact: "**audit** — none in phase 3 (the role
  projection is phase 4)."
- **Attribution must precede the producer, not follow it.** Phase 5 (bounded autonomous diagnosis)
  runs a loop where "the leader never sees the member's intermediate steps" (memo §3.1); a naive
  adoption would put member tool calls **outside** the leader's transcript and the audit trail.
  Gate point 1 ("deny-by-default policy **+ audit** preserved") fails unless the attribution
  dimension exists *before* concurrent members do. Sequencing phase 4 immediately after the policy
  axis is the memo's own order and the safe one: build the record shape while it is still inert,
  then bind roles into it in phase 5.
- **The pattern is already proven twice.** `delegation_mode` (SPEC-070) is the exact precedent — an
  optional top-level audit-event enum dimension, omitted when `None`, with a store column + index,
  an `AuditQuery` filter, emitter parity, and contract-parity tests. Phase 4 adds the sibling
  `agent_role` dimension the same way, so the machinery is mechanical and the risk is bounded.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.
Phase 4 delivers an **inert attribution dimension**: every requirement is provable by
unit/contract/parity tests over the audit model with **no caller binding a non-`None` agent-role**
and **no change to any deployed (unscoped) audit event** — mirroring SPEC-070/073/074's
inert-substrate acceptance.

### R-1: An additive `agent_role` dimension in the audit-event contract

Extend `audit-event.schema.json` with an **optional** top-level `agent_role` string field whose
enum is the closed SPEC-073 vocabulary (`diagnostician`, `orchestrator`, `executor`). **Absent =
not asserted** (the field is omitted, never null, exactly as `delegation_mode` is), so every
existing event serializes byte-identically. The `event_type` enum stays **closed** — phase 4 adds a
*dimension on existing events*, not new event types (OQ-1).

Acceptance criteria:

- The schema declares an optional `agent_role` with the three-value closed enum; `additionalProperties`
  stays `false`; the field is not in `required`.
- A parity guard asserts the audit `agent_role` enum is **exactly** the SPEC-073 agent-role
  vocabulary (single source of truth — the audit dimension cannot drift from the identity/policy
  vocabulary; mirrors the `event_type`/`EventType` lockstep test).
- A contract test asserts the change is additive only (no required key added, no existing field's
  semantics changed, `delegation_mode` untouched).

### R-2: The audit-service model, store, and query dimension

Add `agent_role` to the `AuditEvent` model (an optional field, omitted from the serialized envelope
when `None` — mirroring `delegation_mode`'s `model_serializer` omission), to `AuditQuery` as an
optional filter, and to the audit store: an `ADD COLUMN IF NOT EXISTS agent_role TEXT` migration,
an `idx_audit_agent_role` index, the INSERT/`_ROW_COLUMNS`/row-mapping paths, both the in-memory
and SQL WHERE filters, and the `?agent_role=` query-API parameter (rejecting an out-of-vocabulary
value at the boundary).

Acceptance criteria:

- `AuditEvent.model_json_schema()["properties"]` stays equal to the contract's `properties` (the
  existing property-parity test covers the new field automatically).
- An event emitted without `agent_role` stores and returns with the field **absent** (never null,
  never an empty string); a legacy row read back yields `agent_role is None`.
- `GET /api/v1/audit/events?agent_role=diagnostician` filters to matching events; an invalid value
  is rejected the same way `delegation_mode=invalid` is today.
- The filter composes with the existing `username` / `session_id` / `event_type` / `outcome` /
  `delegation_mode` filters (AND semantics, empty = unconstrained).

### R-3: Emitter parity across the audit-emitting services

Add `agent_role: str | None = None` to the canonical `build_audit_event` signature and
`("agent_role", agent_role)` to the omit-when-`None` field tuple in the fire-and-forget audit
emitter replicated across the emitter services (the `EMITTER_SERVICES` parity family — agent-service,
execution-runtime, identity-service, incident-service, platform-gateway, skills-hub, tool-gateway),
keeping the modules **byte-for-byte identical** under `AuditEmitterParityTest`.

Acceptance criteria:

- The emitter parity test still passes (all replicas byte-identical); the new tuple entry is present
  in every replica.
- An emitter call with no `agent_role` produces a payload **byte-identical** to today's (the field
  is omitted, not nulled) — asserted by the existing "optional identity fields are omitted" test
  extended to `agent_role`.
- The emitter accepts an `agent_role` and, when non-`None`, includes it; the value is never
  validated/coerced at the emitter (the audit-service model + schema own the vocabulary).

### R-4: Evidence / transcript attribution (scoped per OQ-3)

Make a member's activity **reconstructable and attributed** in the durable session record, per memo
§4.3's "the SPEC-025 evidence / SPEC-039 transcript model so a member's tool calls remain
reconstructable": an additive optional `agent_role` on the `session-evidence` turn (and, per OQ-3,
the transcript turn) so a replayed evidence group declares which role produced it. **Scope is
governed by OQ-3** — the recommended slice lands the additive evidence-turn field only where it is
inert and cheap, and defers any heavier transcript re-modelling to phase 5/6 when concurrent
members actually produce multi-role turns.

Acceptance criteria:

- `session-evidence.schema.json` (and the `evidence_turns` item in `agent-session.schema.json`)
  gains an optional `agent_role`; a turn stored without it is byte-identical to today.
- An evidence turn with an `agent_role` renders/replays with that attribution; a legacy turn (no
  field) replays exactly as before (no empty artifact).
- If OQ-3 defers the transcript-turn projection, the deferral and its trigger (phase 5's concurrent
  members) are recorded explicitly and no transcript field changes.

### R-5: Inertness, four-point-gate parity, and the producer seam

The dimension is **inert** on every deployed path: no caller binds a non-`None` `AGENT_ROLE`, so
every live audit event is byte-identical and gate point 1 ("audit preserved") is **strengthened,
never relaxed**. Per OQ-2, phase 4 may wire the *seam* — the agent-platform emitter threading
`current_agent_role_value()` (SPEC-073) into its events — which is byte-identical today because
`AGENT_ROLE` defaults to `None` on the unscoped single-agent path.

Acceptance criteria:

- Reachability guard: no code path reachable from a deployed emitter passes a non-`None`
  `agent_role` in phase 4 (the SPEC-073 R-5 / SPEC-074 R-5 reachability guard, audit-side). If OQ-2
  wires the seam, the guard proves the seam's source (`current_agent_role_value()`) is `None` on
  every deployed turn.
- No-diff test: the full audit-service suite (and every emitter's suite) passes unchanged with the
  dimension present but unexercised; a captured unscoped event is byte-identical before/after.
- Gate mapping is recorded: point 1 (audit) strengthened; points 2 (identity — the role stays a
  label beside the one delegated token, no new principal/claim/edge), 3 (read-only posture), and 4
  (no agentscope types through the v2 contract — the field is a plain string enum) unchanged.
- Root `make verify` green (incl. `validate-version`, the audit-contract target, and the emitter
  parity check).

### R-6: Documentation and contract reconciliation

Document the attribution triple as complete in the living docs and reconcile the audit contract
surfaces: the authorization-matrix attribution note (the agent-role now appears in audit, beside
`delegation_mode`), the identity-and-authorization-design phase-boundary note (phase 4 landed), and
the audit-vocabulary/summary surface per OQ-5.

Acceptance criteria:

- The authorization matrix / audit documentation states that an audited event may carry an
  `agent_role` attribution (which role acted) beside `subject`/`username` (on whose behalf) and
  `delegation_mode` (under which delegation), completing the memo §4.3 triple, and that the
  dimension narrows nothing (it is descriptive attribution, not an authorization input — the
  authorization axis is SPEC-074).
- The schema revision is recorded per OQ-6; the summary/export surface is reconciled per OQ-5
  (additive facet, or explicitly unchanged with the reason recorded).
- Both docs cross-reference SPEC-073 (vocabulary), SPEC-070 (`delegation_mode` sibling), and
  ADR-0017 §4.3.

## Non-Goals

- **Binding a role at a live caller / running an orchestration loop.** No diagnosis or
  orchestration loop binds a non-`None` `AGENT_ROLE` in phase 4. The producer is **phase 5**
  (bounded autonomous diagnosis). Phase 4 is the inert attribution dimension only.
- **Crossing the process boundary with the role on the wire.** The agent-role stays out of every
  JWT claim, forwarded header, and `agent-stream-event` / `execution-request` field in phase 4
  (SPEC-073's invariant). The v2 multi-agent **contract** framing of the role is **phase 6**; this
  spec touches the **audit/evidence record**, not the streaming contract.
- **New audit event types.** The `event_type` enum stays closed (23 values). Attribution is a
  *dimension on existing events*, not new vocabulary (OQ-1) — mirroring `delegation_mode`.
- **Any authorization decision keyed on `agent_role`.** The audit dimension is **descriptive**
  (what acted); the **prescriptive** axis (what a role may do) is SPEC-074's policy engine. Phase 4
  adds no enforcement and changes no decision.
- **A portal audit filter/column for `agent_role`.** `delegation_mode` has no portal filter today;
  phase 4 mirrors that and defers any portal rendering until there is data and a consumer (OQ-4).
- **Re-modelling the transcript for concurrent multi-agent turns.** The single-turn transcript /
  v2 SSE frame stays as-is; the multi-agent event stream (several agents emitting at once) is
  phase 6 (memo §3.1(b), §4.5). Phase 4 only adds an optional attribution field where OQ-3 allows.

## Impact

- products touched: `products/audit-service` (`schemas/audit.py` — `AuditEvent` + `AuditQuery` +
  the `AgentRole` literal; `services/audit_store.py` — column/index/filter/insert/row; the query /
  reporting API route — `?agent_role=`), and the canonical `audit_emitter.py` replicated across the
  **six emitter services** (`products/{agent-platform,execution-runtime,identity-broker,platform-gateway,skills-hub,tool-gateway}`)
  — signature + field tuple only, parity-enforced. Per OQ-2, `products/agent-platform` may also
  thread `current_agent_role_value()` (SPEC-073) into its emitter (the inert seam). Per OQ-3,
  `products/agent-platform` evidence persistence (`session_evidence`). **No** portal, gateway
  policy, identity-broker mint, or execution-runtime dispatch change (the policy axis is SPEC-074;
  the toolkit is SPEC-073; the wire contract is phase 6). Documentation:
  `docs/agentic-aiops-platform/authorization-matrix.md`,
  `docs/agentic-aiops-platform/identity-and-authorization-design.md` (phase-boundary note).
- contracts touched: `shared/shared-contracts/schemas/audit-event.schema.json` (additive optional
  `agent_role`; versioning per OQ-6); `shared/shared-contracts/schemas/session-evidence.schema.json`
  and the `evidence_turns` item in `agent-session.schema.json` **only if** OQ-3 lands the
  evidence/transcript field; `shared/shared-contracts/schemas/audit-summary.schema.json` **only if**
  OQ-5 adds a summary facet. `agent-stream-event.schema.json` and `execution-request.schema.json`
  stay **byte-unchanged** (SPEC-073's invariant; the contract field is phase 6).
- identity / policy / audit / execution safety impact: **audit** — adds an inert, descriptive
  `agent_role` attribution dimension to the durable record, completing the memo §4.3 triple; the
  `event_type` enum stays closed; an unscoped event is byte-identical. **identity** — none (the role
  stays a label beside the one delegated token; no new principal, claim, or edge — ADR-0004).
  **policy** — none (the authorization axis is SPEC-074; this is descriptive, not prescriptive).
  **execution safety** — unchanged: the governed mutation path (SPEC-037/038/063) and the
  `executor`→human-approver invariant (SPEC-074 R-3) are untouched; attribution never authorizes.
- living state docs to update on delivery: `docs/specs/README.md` (index row),
  `docs/agentic-aiops-platform/delivery-roadmap.md` (the multi-agent program row, phase 4),
  `CHANGELOG.md`, and the phase-boundary note in `identity-and-authorization-design.md`.

## Open Questions — resolved

All seven Open Questions were ratified by the operator **2026-11-05** exactly as recommended (the
SPEC-072/073/074 pattern). Each resolution is binding on the [plan](plan.md) / [tasks](tasks.md).

- **OQ-1 — Attribution shape: a new dimension on existing events, or new event types?**
  **RESOLVED: a new `agent_role` dimension on existing events; the `event_type` enum stays
  closed.** Attribution is orthogonal to event type (any event can be role-attributed), a new
  dimension mirrors the `delegation_mode` precedent exactly, and adding types to a closed enum
  ripples through every emitter, the portal drift guard, and the parity tests for no gain. This is
  the memo's first-listed option ("a new dimension on existing events").
- **OQ-2 — Producer wiring: thread the SPEC-073 seam now, or pure schema/store substrate?**
  **RESOLVED: wire the agent-platform emitter seam** to thread `current_agent_role_value()`
  (SPEC-073) into its audit events, closing the loop SPEC-073 explicitly deferred ("phase 4 adds the
  additive optional field when a real consumer exists"). It is **byte-identical today** because
  `AGENT_ROLE` defaults to `None` on every deployed unscoped turn, so the field is omitted; but the
  projection path then exists end-to-end, and phase 5's job becomes purely "bind a role," not "bind
  a role *and* wire attribution." The alternative (pure substrate, wiring deferred to phase 5) is
  smaller but leaves SPEC-073's seed unconnected and re-opens the emitter in phase 5.
- **OQ-3 — Evidence/transcript scope: how much of §4.3's "reconstructable" lands in phase 4?**
  **RESOLVED: the additive optional `agent_role` on the `session-evidence` turn only; defer any
  transcript re-modelling to phase 5/6.** The evidence-turn field is cheap, inert, and makes a
  persisted tool-evidence group self-attributing; the concurrent-multi-agent transcript (several
  roles emitting into one session's turn stream) is a phase-6 contract concern (memo §3.1(b)) with no
  producer until phase 5. Landing only the evidence field keeps phase 4 tight while satisfying
  §4.3's "member tool calls remain reconstructable" for the durable record.
- **OQ-4 — Portal projection: an audit filter/column for `agent_role`?**
  **RESOLVED: no portal change in phase 4.** `delegation_mode` — the sibling dimension — has no
  portal filter today, and projecting an always-absent field adds a consumerless UI surface
  (mirrors SPEC-074 OQ-5's "add the field when a real consumer exists"). Defer portal rendering to
  phase 5+, when bound roles produce data worth filtering.
- **OQ-5 — Summary / export facet: does `agent_role` become an aggregate dimension?**
  **RESOLVED: not in phase 4; record the deferral.** `delegation_mode` is available as a summary
  window, but adding an `agent_role` facet to `audit-summary.schema.json` / the bounded CSV export
  before any event carries the field is a consumerless surface. Revisit at phase 5 with real data;
  keep the query-API **filter** (R-2) since it is the same additive machinery as `delegation_mode`.
- **OQ-6 — Schema version / ADR: does `audit-event.schema.json` bump, and is a new ADR needed?**
  **RESOLVED: an additive optional field within the existing audit-event version (no title
  bump), and no new ADR.** SPEC-070 added `delegation_mode` the same way — an optional top-level
  field, `additionalProperties: false`, title unchanged — so this is a contract decision within the
  spec, not an architecture decision. ADR-0017's §4.3 already authorizes the audit-attribution leg
  and ADR-0010 already fixes "provenance rides the fact."
- **OQ-7 — Acceptance evidence: what proves phase 4?**
  **RESOLVED: unit + contract + emitter-parity + a reachability/no-diff guard, green `make
  verify`; no live/browser evidence.** Mirrors SPEC-073 OQ-5 / SPEC-074 OQ-7. The reachability guard
  (R-5) proves no deployed emitter threads a non-`None` `agent_role`; the no-diff test proves an
  unscoped event is byte-identical; the contract-parity + enum-lockstep tests prove the model,
  schema, and SPEC-073 vocabulary stay in lockstep.

## Changelog

- 2026-11-05: created as `draft` with seven Open Questions; phase 4 of the ADR-0017 series,
  realizing the audit-&-attribution leg (memo §4.3, §7 step 4) that SPEC-073 (v0.54.0) and
  SPEC-074 (v0.55.0) both deferred to this phase. Adds the `agent_role` attribution dimension as
  the sibling of SPEC-070's `delegation_mode`, completing the memo's *role / behalf / delegation*
  triple; ships inert (no producer binds a role until phase 5).
- 2026-11-05: **approved** — all seven Open Questions ratified by the operator exactly as
  recommended; [plan](plan.md) / [tasks](tasks.md) written and now binding; implementation
  authorized to *begin* (not to merge, commit/push, deploy, or version-bump).
- 2026-11-05: **delivered** — R-1…R-6 implemented as an inert, additive `agent_role` attribution
  dimension (the audit-event contract dimension + enum-lockstep guard; the audit-service
  model/store/query/`window_echo`; the **six**-emitter parity family — correcting the draft's
  "seven", `incident-service` being a distinct triage `AuditConnector` with no `build_audit_event`
  that never carried `delegation_mode` and is not an `AuditEmitterParityTest.EMITTERS` member;
  evidence-turn attribution; the inert agent-platform producer seam; and the living-docs sweep).
  Root `make verify` green end-to-end (agent-platform **1716** incl. five new
  `TestSpec075AuditAttribution` guards, audit-service **149**, all-product `make test` **4036**,
  portal **546**, the SPEC-063 `execution-failure-test` campaign **795 passed, exit 0** in 0:38:11);
  phase-4 inertness confirmed (no deployed emitter threads a non-`None` `agent_role`; every unscoped
  audit event and evidence turn byte-identical; the `event_type` enum closed;
  `agent-stream-event`/`execution-request` byte-unchanged). **Discovered doc-gap (out of scope,
  recorded as a follow-up):** `docs/guides/servicenow-integration.md` §5.5 "Audit attribution" lists
  the `audit_events` columns but is stale — it omits `delegation_mode` (a pre-existing SPEC-070 gap)
  and now `agent_role`; left untouched here because SPEC-075 does not own that guide. Released as
  **v0.56.0** (2026-11-05); the push remains a separate operator gate.
