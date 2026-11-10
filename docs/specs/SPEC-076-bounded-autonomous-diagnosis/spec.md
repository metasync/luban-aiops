# SPEC-076: Bounded Autonomous Diagnosis (The Read-Only Orchestration Loop That First Binds Agent-Roles)

## Status

- status: `approved`
- owner: chi
- created: 2026-11-06
- approved: 2026-11-06 (all seven Open Questions ratified by the operator **exactly as
  recommended**: a new platform-owned `services/orchestration.py` bounded fan-out over the existing
  `read_only=True` seam (OQ-1); a new `AGENT_ORCHESTRATION_MAX_STEPS` budget, default `20`,
  per-orchestration total, failing closed to a partial diagnosis (OQ-2); an **operator-invoked**
  trigger, unattended machine-trigger ingestion deferred to the named follow-up **FU-076** (OQ-3);
  the **minimal** canonical `agent_roles_any` rule(s), tool-family axis deferred (OQ-4); **no new
  frame** — the diagnosis surfaces through existing assistant/evidence/card frames (OQ-5); scenario
  tests for all four runbooks plus a gated live-cluster read-only check (OQ-6); the capability built
  once with four declared profiles, two wired end-to-end (OQ-7). See `## Open Questions — resolved`.)
- release slice: the **multi-agent / bounded-autonomy program** — phase 5 of the phased SPEC
  series [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md) gates
  ([memo](../../workspace/multi-agent-orchestration-spike.md) §7 step 5, §5). Target version
  **v0.57.0** (a minor bump over v0.56.0, per the SPEC-070/071/072/073/074/075 pattern), pinned on
  approval 2026-11-06.
- related ADRs: [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md)
  (`accepted` 2026-11-03 — **Decision 1** the bounded read-only orchestration loop, **Decision 2**
  the diagnose-before-act autonomy ceiling, and **Decision 4** role-scoped agents on the same
  delegated token; this spec is the first to *bind* those roles and to admit the loop);
  [ADR-0011](../../adr/0011-composition-carries-no-authority.md) (**amended by ADR-0017 at
  Decision 3 only** — this spec is the controlled relaxation: a bounded loop admitted **only**
  where every step is read-only; composition still carries no mutation authority);
  [ADR-0004](../../adr/0004-broker-mediated-token-delegation.md) (the *one* identity edge,
  preserved across the fan-out — a member acts as the same human with a narrowed toolkit);
  [ADR-0007](../../adr/0007-browser-flow-single-hitl-gate.md) (one HITL gate per mutating flow —
  the `executor`→human-approver invariant);
  [ADR-0010](../../adr/0010-signed-execution-envelopes-declare-authority-provenance.md)
  (provenance rides the signed fact) and
  [ADR-0013](../../adr/0013-durable-single-use-execution-claims.md) (durable single-use dispatch
  claims) — both stay authoritative on the mutation path. **No new ADR is expected**: ADR-0017
  already fixed the control-flow model, the autonomy ceiling, and the identity model; this spec
  makes Decision 1 concrete (see OQ-1 on the loop mechanism and OQ-5 on the contract boundary).
- extends: [SPEC-073](../SPEC-073-role-scoped-agent-identity/spec.md) (the closed agent-role
  vocabulary + the `AGENT_ROLE` contextvar + `agent_role_scope()` + the `_narrow_for_role`
  toolkit seam this spec's orchestration frame **binds**),
  [SPEC-074](../SPEC-074-policy-role-axis/spec.md) (the `agent_roles_any` policy axis + the
  `evaluate(agent_role=…)` input this spec makes **live**),
  [SPEC-075](../SPEC-075-multi-agent-audit-attribution/spec.md) (the `agent_role` audit +
  evidence-turn dimension this spec **populates**),
  [SPEC-018](../SPEC-018-kernel-middleware-alignment/spec.md) (the four-point adoption gate this
  loop must satisfy on its own terms),
  [SPEC-007](../SPEC-007-tool-execution-framework/spec.md) (the read-tier tool seam the
  `diagnostician` toolkit reuses), [SPEC-015](../SPEC-015-incident-triage-and-collaboration/spec.md)
  (the existing `read_only=True` automated diagnostic-turn path the loop generalizes),
  and the governed mutation path [SPEC-020](../SPEC-020-hitl-confirmation-bridging/spec.md) /
  [SPEC-030](../SPEC-030-require-approval-policy-semantics/spec.md) /
  [SPEC-031](../SPEC-031-approval-inbox-persistent-confirmation/spec.md) (HITL) and
  [SPEC-037](../SPEC-037-signed-execution-requests/spec.md) /
  [SPEC-038](../SPEC-038-isolated-execution-worker/spec.md) /
  [SPEC-063](../SPEC-063-crash-safe-execution/spec.md) (signed at-most-one dispatch). Reconciles
  with [SPEC-064](../SPEC-064-agentscope-compression-and-goal-pipeline/spec.md) (the `GoalPipeline`
  reopen trigger this meets) and the read-tier ingestion pilots
  [SPEC-067](../SPEC-067-servicenow-mcp-ingestion-pilot/spec.md) (ServiceNow) /
  [SPEC-069](../SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) (the diagnostician's
  external read toolkit).

> SDD note: `spec.md` was drafted first and carried **seven Open Questions** that blocked
> `approved`; the operator ratified all seven **exactly as recommended on 2026-11-06** (see
> `## Open Questions — resolved`), so the resolutions are now binding on the [plan](plan.md) /
> [tasks](tasks.md) (their **provisional** banners lifted to binding) and implementation may
> **begin** — approval does **not** authorize a merge, commit/push, deployment, or a version bump;
> those stay separate boundaries, and the standing "review before any merge/deploy" constraint
> governs. This is phase 5
> of the series: the **v2 multi-agent contract** (§4.5, any additive/versioned wire framing of member
> attribution or orchestration status) is a separate later spec (phase 6) and is explicitly out of
> scope here — per OQ-5 phase 5 surfaces the diagnosis through **existing** frames. **Autonomous
> resolve** (closing the loop without a human approver) is deferred by ADR-0017 Decision 2 and is a
> Non-Goal.

## Summary

Build the **bounded read-only orchestration loop** — the §5 leg of ADR-0017's phased series and the
**producer** that first *binds* the agent-roles SPEC-073, SPEC-074, and SPEC-075 each landed
**inert**. Phases 2–4 built the substrate (a closed role vocabulary + toolkit narrowing, a policy
role axis, and an audit/evidence attribution dimension) with **no deployed caller binding a
non-`None` role**; phase 5 wires that caller. An **`orchestrator`** decomposes a diagnosis goal and
fans out read-only **`diagnostician`** sub-agents over the *same* governed gateway (observability,
Kubernetes, ServiceNow, log reads), then synthesizes a diagnosis and a ***proposed*** remediation
**autonomously, with no human in the loop** — because a read cannot cause harm and every read still
rides the tool-gateway's deny-by-default policy, redaction, evidence, and audit. The loop is
**bounded** by an explicit iteration/step budget mirroring the `GATEWAY_BROWSER_FLOW_MAX_STEPS`
discipline; this is the **controlled relaxation of ADR-0011 Decision 3**, and it applies **only**
where every step is read-only. The autonomy ceiling is **diagnose-before-act**: any mutation the
diagnosis proposes is *staged* by an `executor` as an existing HITL confirmation card that a
**distinct human** approves and the signed at-most-one-dispatch worker executes — no agent approves
another agent's mutation, and **autonomous resolve stays deferred**.

The operator named **all four** candidate first-workflows (memo §8 Q5), so the loop is built once as
a runbook-agnostic capability and **validated against the union of four real runbooks** —
ServiceNow-incident, observability-alert, post-deploy-verify, and Kubernetes-pod-degradation — which
is what drives the role/toolkit split from real runbooks rather than a speculative one. Because
phase 4 landed the attribution record *before* the loop, gate point 1 ("audit preserved") holds **by
construction**: each member's action is already attributable to its role the moment the fan-out
runs, even though "the leader only ever sees the summary" (memo §3.1).

## Motivation

- **ADR-0017 Decision 1 admits the loop; phases 2–4 only built its inert substrate.** Decision 1
  fixed the *model* — "an orchestrator may fan out read-only sub-agents … and synthesize a diagnosis
  autonomously, with no human in the loop … bounded by an iteration/step budget" — but left the
  *mechanism* to this spec (memo §7 step 5: "bounded autonomous diagnosis (§5): the read-only
  orchestration increment, mutations still on the SPEC-037/038/063 path"). Nothing downstream
  (phase 6's contract) is decision-complete until the loop exists and the roles are bound.
- **Three delivered substrates are inert and waiting for exactly this producer.** SPEC-073's
  `agent_role.py` docstring states "the bounded read-only orchestration loop that actually binds
  roles is phase 5"; SPEC-074 OQ-1/OQ-4 deferred *live enforcement* and the *canonical rule* to
  "phase 5, when a producer exists"; SPEC-074 OQ-3 deferred the tool-family axis to "phase 5 when a
  real diagnosis loop names the first concrete tool families — memo §8 Q5"; SPEC-075 ships its
  attribution dimension byte-identical "until phase 5 binds roles." Phase 5 is the single wiring
  event that makes all three live.
- **The seam already half-exists — this is a generalization, not a new execution surface.**
  `_ensure_toolkit(bearer_token, read_only=True)` already builds a per-token **read-only** gateway
  toolkit for "automated diagnostic turns such as incident triage" (SPEC-015); `agent_role_scope()`
  already binds a role for a turn; `_narrow_for_role` already restricts a toolkit per role. Phase 5
  adds the **orchestration frame** that drives a bounded fan-out of role-scoped read-only turns over
  these existing seams — no second gateway, no second identity edge, no agentscope orchestration
  surface (ADR-0017 Decision 5 keeps `TeamPipeline`/`GoalPipeline`/`A2AAgent` out).
- **Attribution preceded the producer on purpose.** Phase 4 was sequenced immediately before phase 5
  so the durable record shape exists while still inert; a naive loop adopted without it would put
  member tool calls outside the leader's transcript and fail gate point 1. Phase 5 therefore
  *populates* an existing dimension rather than retro-fitting one onto a running loop.
- **Why now.** v0.56.0 closed out phase 4 (delivered, tagged, pushed). The operator directed opening
  phase 5 and named all four first-workflows. Sequencing bounded diagnosis before the contract
  change is the memo's own order (§7): phase 6 frames the wire only after phases 2–5 fix the
  semantics.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.
Phase 5 is the **first phase with live runtime behavior**, so — unlike the inert phases 2–4 — its
acceptance includes an actual bounded read-only orchestration run (the evidence bar is OQ-6). Every
requirement preserves the four-point gate (SPEC-018) and the diagnose-before-act ceiling; the
deployed **unscoped single-agent chat path stays byte-identical** (no role is bound outside an
orchestration frame).

### R-1: A bounded read-only orchestration loop (ADR-0017 Decision 1)

Introduce a **platform-owned** orchestrator that decomposes a diagnosis goal into a bounded fan-out
of read-only member turns and synthesizes a diagnosis, **without adopting any agentscope
orchestration surface** (Decision 5). The loop is admitted **only** where every step is read-only; it
is **bounded** by an explicit iteration/step budget (a new knob mirroring
`GATEWAY_BROWSER_FLOW_MAX_STEPS`'s discipline — OQ-2) and **fails closed** on exhaustion (it stops
and reports a best-effort/partial diagnosis; it never widens to a mutating step to "finish"). The
orchestrator sees each member's **summary**, not its intermediate steps (memo §3.1); member activity
is nonetheless reconstructable via R-6.

Acceptance criteria:

- The loop terminates at the configured budget; a test asserts a goal that would exceed the budget
  stops at the bound and yields a partial diagnosis marked as budget-limited (never an unbounded
  loop, never a silent mutation).
- No `TeamPipeline` / `GoalPipeline` / `A2AAgent` (or any agentscope orchestration/pipeline) type is
  constructed anywhere on the orchestration path; a guard test asserts the loop is platform-owned
  (gate point 4 / Decision 5).
- A member step that would mutate is **not** executed inside the loop — it is refused or handed to
  the R-4 park path; the loop's read-only admission is asserted (a mutating tool is not in a
  `diagnostician` toolkit, R-2 + SPEC-073 R-2).
- The unscoped single-agent turn (`/api/v2/chat`, `/chat/stream`) binds no role and is
  **byte-identical** to today; a no-diff test asserts the orchestration frame is the *only* new
  role-binder.

### R-2: Role binding via the orchestration frame (the producer that activates SPEC-073)

The orchestration frame binds `AGENT_ROLE` per participant through SPEC-073's `agent_role_scope()`:
the orchestrator turn runs as **`orchestrator`** (no direct gateway tools — it delegates), each
read-only member runs as **`diagnostician`** (read-level toolkit via `_narrow_for_role` /
`_filter_read_only`), and a proposed remediation is staged by an **`executor`**. This is the **first
deployed caller to bind a non-`None` role**, so `current_agent_role_value()` becomes non-`None` on
the orchestration path and the SPEC-073/074/075 reachability guards change from "no caller binds a
role" to "**only the orchestration frame binds a role**."

Acceptance criteria:

- Within an orchestration, `current_agent_role()` returns the correct role per participant
  (`orchestrator` for the synthesizer, `diagnostician` for each read member, `executor` for a
  staging step); an `orchestrator` context's gateway toolkit is empty (it delegates, never invokes).
- The role binds as process-local context only (SPEC-073 OQ-2): it is **not** part of the SPEC-017
  resumable snapshot, and a park/resume **re-derives** it per turn from the orchestration frame
  rather than persisting a stale role.
- The SPEC-073 R-5 / SPEC-074 R-5 / SPEC-075 R-5 reachability guards are updated and still pass:
  the only reachable non-`None` role-binder is the orchestration frame; no other deployed path
  (chat, triage, documents, skills) binds a role.

### R-3: Same-token identity preservation across the fan-out (ADR-0004, SPEC-073 R-3)

Every member rides the **same** gateway-forwarded delegated token the orchestrator holds: no
per-role broker mint, no second identity edge, no additional signing authority. The human
requester's `VerifiedHuman` identity (SPEC-070 `REQUESTER_IDENTITY`) is **preserved end-to-end**
across every delegation hop — a member acts *as the same human* with a narrowed toolkit, never as a
distinct principal. The role stays process-local (never a JWT claim, forwarded header, or wire
field).

Acceptance criteria:

- A multi-member orchestration performs **exactly one** broker exchange per user for the whole
  fan-out; a test fails if the broker is invoked more than once (SPEC-073 R-3's guard, extended to a
  multi-member loop).
- The requester `VerifiedHuman` (namespace/subject) is unchanged across every hop; a test asserts
  identity equality before, within, and after the fan-out.
- No `agent_role` appears as a JWT claim, a header forwarded to the gateway, or any
  `agent-stream-event` / `execution-request` wire field (SPEC-073's invariant; the contract framing
  is phase 6).

### R-4: Diagnose-before-act — every mutation parks on HITL + signed dispatch (Decision 2)

The loop is read-only. When the synthesized diagnosis proposes a remediation, an **`executor`**-scoped
agent may ***stage*** it as an existing HITL confirmation card (SPEC-020/030/031) carrying the
SPEC-073 R-4 `staged_by_role` provenance; a **distinct human** approves and the signed
at-most-one-dispatch worker (SPEC-037/038/063) executes it. **No agent may approve another agent's
mutation**; the executor cannot self-approve and the SPEC-030 self-approval block still fires.
**Autonomous resolve is explicitly deferred** (Decision 2) — phase 5 never closes the loop without a
human approver.

Acceptance criteria:

- A proposed remediation produces a parked confirmation card carrying the staging `executor` role; a
  `diagnostician` or `orchestrator` context **cannot** stage a mutation at all (no mutating tool in
  its toolkit, R-2), asserted by a test.
- The staged mutation dispatches **only** through the existing signed path with a human decider
  distinct from the requester; the self-approval block fires for a role-staged mutation;
  `execution-request.schema.json` is byte-unchanged (no new field, gate, worker, or claim type).
- The read-only loop **never** dispatches a mutation: an orchestration that reaches a
  propose-remediation step parks and returns control to the human; a test asserts no signed dispatch
  occurs without an approval event.

> **Delivery resolution (v0.57.0).** Phase 5 delivers and unit-proves the `executor`-scoped
> `stage_remediation(...)` **mechanism** — it binds `executor` (`read_only=False`), parks a proposal on
> the existing SPEC-020/030/031 HITL card carrying `staged_by_role="executor"`, fails closed for a
> diagnosis-only profile, and upholds the self-approval block + distinct-human requirement. It wires
> **no production trigger**: `run_bounded_diagnosis` never calls it and `POST /api/v2/diagnose` is
> diagnosis-only. Phase 5 therefore ships the read-only loop, the R-4 ceiling holds **by
> construction** (the live trigger cannot reach a mutation), and the operator-initiated diagnose→act
> bridge that would call `stage_remediation` is the named follow-up **`FU-076-b`** (recorded in
> Non-Goals + the roadmap). The staging acceptance above is met at **unit** scope and activated in
> production by `FU-076-b`.

### R-5: Live policy enforcement + the canonical agent-role rule (activates SPEC-074)

Phase 5 is "when a producer exists" (SPEC-074 OQ-1/OQ-4): thread the bound `agent_role` into **both**
gateway `evaluate()` engines on the orchestration path, and land the canonical
`policy-default.yaml` `agent_roles_any` rule(s) the four runbooks need — keeping the change minimal
and synced across all four bundle replicas (`make sync-policy`). Per SPEC-074 OQ-3, decide whether
the four runbooks' concrete tool families require a **tool-name/family** match dimension or whether
the existing action axis (`tools:invoke`/`tools:mutate`) **plus** SPEC-073 toolkit narrowing already
suffice (OQ-4). The axis stays **subtractive-only** and **fail-closed**: a `diagnostician` can never
reach a mutating grant, and an agent-role-scoped rule never matches an unscoped call.

Acceptance criteria:

- An orchestration-path policy evaluation threads the participant's `agent_role`; a `diagnostician`
  read is allowed by the (tier + role) evaluation and a mutating grant is unreachable for it.
- The canonical bundle change (if OQ-4 lands one) is byte-identical across all four replicas;
  `make validate-policy` / `validate-policy-scenarios` / the bundle-parity check are green.
- The `executor`→**human**-approver disjointness invariant (SPEC-074 R-3) holds on the live path: no
  agent-role ever appears as an approver decider.

> **Delivery resolution (v0.57.0) — reconciles R-5 with R-3 via OQ-4.** The `agent_role` **axis** and
> the two minimal canonical `agent_roles_any` rules (`deny-diagnostician-tools-mutate`,
> `require-approval-executor-tools-mutate`) are landed in `policy-default.yaml` (synced byte-identically
> across all four replicas, `make validate-policy`/`validate-policy-scenarios` green) and their engine
> semantics are **unit-proven** (subtractive-only, fail-closed; an unscoped call and a role the rules do
> not name evaluate byte-identically to the pre-axis baseline). Per **OQ-4** — ratified: "SPEC-073
> toolkit narrowing already restricts *what each role sees* … the policy axis likely stays action-based"
> — the existing action axis **plus** in-process SPEC-073 narrowing **suffice** as the live read-only
> control. Because **R-3 keeps the bound role off every wire field**, no deployed gateway caller threads
> a non-`None` `agent_role`, so the canonical rules stay **ready-but-inert** on the live path. The
> orchestration-path threading acceptance above is therefore met **at the engine layer** (proven by
> test), not by a deployed wire thread; the axis goes live in deployment only via the phase-6 wire
> contract or a deliberately-designed in-process evaluation point (**`FU-076-c`**, recorded in
> Non-Goals + the roadmap). R-5 and R-3 are reconciled by OQ-4, not contradicted.

### R-6: Live attribution — the audit/evidence record populated (activates SPEC-075)

With roles bound, SPEC-075's `agent_role` dimension is **populated**: each member's audited action
and each SPEC-025 evidence turn carries its role, so member activity is reconstructable even though
the orchestrator sees only summaries (memo §3.1/§4.3). The orchestrator's synthesized diagnosis is
attributable to the `orchestrator` role; a staged remediation to the `executor`. **No new audit
event type** — the `event_type` enum stays closed (SPEC-075 R-1); phase 5 fills the existing
dimension.

Acceptance criteria:

- An orchestration run produces audit events whose `agent_role` is non-`None` and correct per
  participant; a query `?agent_role=diagnostician` returns the member reads.
- A member's tool calls are reconstructable from the durable evidence record with role attribution;
  the orchestrator's synthesis and any executor-staged proposal carry their roles.
- An **unscoped** (non-orchestration) event remains byte-identical (no `agent_role`) — the dimension
  is populated only where a role is actually bound.

### R-7: The four concrete runbooks (memo §8 Q5 = all four) + the trigger/autonomy boundary

Express the bounded-diagnosis capability against **four real detect→troubleshoot→propose runbooks**,
each declaring its trigger, its read-only `diagnostician` toolkit families, and its
proposed-remediation shape: **(a)** ServiceNow-incident → diagnosis (SPEC-067 read tools +
observability + k8s + recent changes), **(b)** observability-alert → correlated diagnosis
(metrics/traces/logs/k8s), **(c)** post-deploy health verify → propose rollback (k8s rollout status
+ error-rate metrics + logs), **(d)** Kubernetes pod-degradation triage → root cause + proposed
remediation (pod events + container logs + config/secret diffs + node health). Per OQ-3/OQ-7, decide
the phase-5 **trigger boundary** (operator-invoked diagnosis vs. unattended machine ingestion) and
how many runbooks are wired end-to-end vs. specified-and-scenario-tested.

Acceptance criteria:

- The role/toolkit split is derived from the **union** of the four runbooks (each runbook's read
  families are named, and the `diagnostician` toolkit is the union of read-tier families, narrowed
  per token `roles`).
- Each runbook is covered by an end-to-end scenario test (mock/fixture-backed for CI); at least the
  runbook(s) the dev cluster can actually exercise are wired live per OQ-6 (k8s/observability, and
  ServiceNow against the SPEC-067 in-cluster mock Table-API).
- The trigger boundary is explicit: an autonomous read-only diagnosis runs with **no human approving
  any read**, and the trigger cannot cause a mutation without the R-4 gate.

### R-8: Four-point-gate parity, the no-new-frame contract boundary, and documentation

Re-affirm SPEC-018's four-point gate for the new control flow and keep the contract untouched (OQ-5):
**(1)** deny-by-default policy **+ audit** preserved (audit now *live*-attributed — R-6; the R-5
policy axis lands ready-but-inert — see its resolution note); **(2)**
identity carried only by the one gateway-forwarded delegated token (R-3); **(3)** the read-only
posture enforced by toolkit narrowing + the loop's read-only admission (R-1/R-2); **(4)** no
agentscope type leaks through the v2 contract — the loop is platform-owned and the diagnosis
surfaces through **existing** frames (a normal assistant turn for the synthesis, existing SPEC-025
evidence frames with role attribution for member reads, an existing SPEC-031 confirmation card for
the proposal), so `agent-stream-event.schema.json` and `execution-request.schema.json` stay
**byte-unchanged** and the multi-agent wire framing remains phase 6.

Acceptance criteria:

- The gate mapping is recorded; a contract test asserts `agent-stream-event.schema.json` and
  `execution-request.schema.json` are byte-unchanged (the multi-agent frame is phase 6, Decision 6).
- Root `make verify` is green (incl. `validate-version`, `validate-policy`, the emitter-parity and
  contract-parity checks, and the SPEC-063 `execution-failure-test` campaign).
- Living docs updated: `identity-and-authorization-design.md` (phase-5 boundary note — the loop is
  live), `authorization-matrix.md` (the agent-role binding: live in-process, policy axis
  ready-but-inert), `configuration-reference.md` (the new orchestration-budget knob + any trigger
  knob), the roadmap multi-agent row (phase 5), and `CHANGELOG.md`.

## Non-Goals

- **Autonomous resolve** — a self-approving mutation loop that closes without a human approver.
  Explicitly deferred by ADR-0017 Decision 2 to a later, evidence-backed trust-model decision.
- **The v2 multi-agent contract** (memo §4.5) — any additive/versioned stream or schema framing for
  member attribution or orchestration status. **Phase 6**, and only after phases 2–5 fix the
  semantics; per OQ-5 phase 5 surfaces the diagnosis through existing frames and changes no contract
  schema.
- **Adopting `TeamPipeline` / `GoalPipeline` / `A2AAgent` as shipped** — kept out by ADR-0017
  Decision 5 (all fail all four gate points as shipped; the platform builds its own bounded loop).
- **A2A external federation** — parked by Decision 5 (revisit only on a named use case plus an
  outbound-identity decision, and then only as a read-only consultant).
- **Per-role broker identities** — rejected by Decision 4 (revisit only if a role ever needs an
  independent credential); the same-token-narrowed model is sufficient for read-only diagnosis.
- **Any widening of the governed mutation path** — the SPEC-037/038/063 signed at-most-one dispatch,
  the SPEC-020/030/031 HITL gate, ADR-0007's one-gate-per-mutating-flow, and the ADR-0010/0013
  provenance/durable-claim invariants all remain authoritative and unchanged.
- **New audit event types or a new attribution dimension** — the SPEC-075 `agent_role` dimension is
  *populated*, not extended; the `event_type` enum stays closed.
- **Unattended machine-trigger ingestion** (webhook/alert auto-fire, dedup, storm control) — resolved
  by OQ-3 as **deferred to a named follow-up, `FU-076`**, recorded in the [delivery
  roadmap](../../agentic-aiops-platform/delivery-roadmap.md) multi-agent program row and as a
  [tasks](tasks.md) Delivery-Gate item so it is **not skipped**. Phase 5 lands the operator-invoked
  entry plus the autonomous read-only loop; `FU-076` (a future spec, not dropped scope) adds the
  unattended machine trigger with its own alert-storm / dedup / backpressure safety design.
- **The operator-initiated diagnose→act bridge (`FU-076-b`)** — the production trigger that would call
  the delivered `executor`-scoped `stage_remediation(...)` mechanism (R-4). Phase 5 ships the mechanism
  **unit-proven but unwired** (`run_bounded_diagnosis` never calls it; `POST /api/v2/diagnose` is
  diagnosis-only), so the read-only ceiling holds by construction. Wiring the mutation-adjacent
  diagnose→act bridge is a distinct, evidence-backed increment (its own portal entry, park/resume UX,
  and HITL routing), recorded in the [delivery roadmap](../../agentic-aiops-platform/delivery-roadmap.md)
  and [tasks](tasks.md) so it is **not skipped** — not dropped scope.
- **A live in-process policy-evaluation point for the agent-role axis (`FU-076-c`)** — the deliberate
  design that would make the SPEC-074 `agent_roles_any` rules fire **in-process** (where R-3 keeps the
  role) rather than across the wire. Phase 5 lands the axis + canonical rules **ready-but-inert**
  (engine-proven; no deployed caller threads a role, R-3), with in-process SPEC-073 toolkit narrowing as
  the live read-only control per OQ-4. Making the policy axis itself live — either via the phase-6 wire
  contract or a new in-process evaluation seam — is recorded in the
  [delivery roadmap](../../agentic-aiops-platform/delivery-roadmap.md) and [tasks](tasks.md) so it is
  **not skipped** — not dropped scope.

## Impact

- products touched: `products/agent-platform` primarily — a new platform-owned orchestration module
  (the bounded read-only fan-out loop, OQ-1), the `runtime_kernel` turn seams that bind
  `agent_role_scope()` around orchestrator/diagnostician/executor turns, the existing
  `read_only=True` diagnostic-turn path it generalizes, and the `executor` staging path (which reuses
  the SPEC-020/030/031 park + SPEC-037/038/063 dispatch). `products/platform-gateway` +
  `products/tool-gateway` — add the `agent_role` axis to `evaluate()` (unit-proven; **ready-but-inert**
  in deployment because R-3 keeps the role off the wire — see the R-5 resolution note); the canonical
  `policy-default.yaml` (+ its three byte-identical replicas) gains the minimal `agent_roles_any` rule
  pair OQ-4 ratified. Portal — a minimal operator-invoked "diagnose" entry **only if** OQ-3 lands it.
  `products/audit-service` — **no schema change** (the SPEC-075 dimension is populated, not
  extended). **No** identity-broker, execution-runtime, or skills-hub behavior change.
- contracts touched: **none** if OQ-5 holds — `agent-stream-event.schema.json` and
  `execution-request.schema.json` stay **byte-unchanged** (the multi-agent frame is phase 6);
  `shared/shared-contracts/policies/policy-default.yaml` (+ replicas) **only if** OQ-4 lands a
  canonical rule; `policy-scenarios.yaml` gains orchestration-path expectations. **No** new schema
  revision (the SPEC-074 v3 policy-rule axis and the SPEC-075 audit dimension already exist).
- identity / policy / audit / execution safety impact: **identity** — the one delegated token is
  preserved across the fan-out; no new principal, edge, claim, or broker mint (R-3). **policy** — the
  SPEC-074 agent-role axis + canonical rules land **ready-but-inert** (engine semantics unit-proven; no
  deployed caller threads a role per R-3, and OQ-4 resolves in-process SPEC-073 narrowing as the live
  read-only control); subtractive-only and fail-closed preserved. **audit** — the SPEC-075 dimension is
  **populated**; member activity is reconstructable and role-attributed; the `event_type` enum stays
  closed. **execution safety** —
  the loop is the controlled ADR-0011 Decision 3 relaxation: bounded and **read-only-only**; every
  mutation still parks on HITL and dispatches through the signed worker with a **distinct human**
  approver; autonomous resolve stays deferred.
- living state docs to update on delivery: `docs/specs/README.md` (index row → `delivered`),
  `docs/agentic-aiops-platform/delivery-roadmap.md` (the multi-agent program row, phase 5),
  `docs/agentic-aiops-platform/identity-and-authorization-design.md` (phase-5 boundary note),
  `docs/agentic-aiops-platform/authorization-matrix.md` (agent-role binding — live in-process, policy
  axis ready-but-inert),
  `docs/guides/configuration-reference.md` (the new orchestration-budget + any trigger knob), and
  `CHANGELOG.md`.

## Open Questions — resolved

All seven Open Questions were ratified by the operator **2026-11-06 exactly as recommended** (the
SPEC-073/074/075 pattern). Each resolution below is binding on the [plan](plan.md) /
[tasks](tasks.md); their provisional banners are lifted. **OQ-3 additionally records a named
follow-up, `FU-076` (unattended machine-trigger ingestion), tracked in the delivery roadmap and the
tasks Delivery Gate so it is not skipped.**

- **OQ-1 — Loop mechanism: where does the bounded orchestration live and how is it driven?**
  Options: **(a)** a new platform-owned orchestration module in `agent-platform` (e.g.
  `services/orchestration.py`) that drives bounded member turns over the existing
  `reply_text(read_only=True)` diagnostic-turn seam, binding roles via `agent_role_scope()`; **(b)**
  extend the kernel's turn runner inline with fan-out logic; **(c)** adopt an agentscope surface
  (rejected by Decision 5). Sub-question: **sequential vs. concurrent** fan-out (memo §3.1's "the
  leader only ever sees the summary").
  **RESOLVED (ratified as recommended 2026-11-06): (a)** — a discrete platform-owned module over the existing read-only seam, with
  **bounded fan-out** (sequentially, or limited-concurrency under the same step budget) where the
  orchestrator consumes only member summaries. Decision 5 forbids adopting `TeamPipeline`/
  `GoalPipeline`; (b) would tangle the loop into the single-turn runner and complicate the
  byte-identical-unscoped-path guarantee. A discrete module keeps the four-point-gate mapping and the
  reachability guard localizable.
- **OQ-2 — The step/iteration budget: knob, default, scope, and exhaustion behavior.** What bounds
  the loop, its default, whether it is per-orchestration or per-member, and what happens on
  exhaustion.
  **RESOLVED (ratified as recommended 2026-11-06):** a new `AGENT_ORCHESTRATION_MAX_STEPS` knob — a **deliberate twin** of the
  tool-gateway's `GATEWAY_BROWSER_FLOW_MAX_STEPS` (default `20`) and validated `>= 1` at startup like
  `AGENT_SKILL_GRADUATION_MAX_STEPS` — bounding **total member read steps per orchestration**
  (not per member), so the fan-out cannot grow unbounded regardless of member count. On exhaustion
  the loop **fails closed to a partial diagnosis** (it stops, synthesizes best-effort from the
  summaries gathered, and marks the result budget-limited); it never widens to a mutating step. A
  per-orchestration cap plus the existing per-turn `AGENTSCOPE_MAX_ITERS` gives a two-level bound
  (per member turn × total steps).
- **OQ-3 — Trigger model / autonomy boundary: what starts an autonomous diagnosis in phase 5?**
  Options: **(a)** operator-invoked only ("diagnose this incident/alert/deploy/pod" from the portal or
  chat) — the read-only loop then runs autonomously; **(b)** unattended machine triggers (ServiceNow
  webhook, observability alert auto-fire) with no human at all; **(c)** both.
  **RESOLVED (ratified as recommended 2026-11-06): (a) for phase 5** — an operator-invoked (or existing-incident-record-anchored)
  entry point plus the autonomous read-only loop, **deferring unattended machine-trigger ingestion**
  (webhook/alert auto-fire, dedup, storm control) to a named follow-up. Rationale: the platform is
  operator-portal-driven today; inbound machine ingestion is a materially larger surface with its own
  safety questions (alert storms, dedup, backpressure); and the read-only autonomy ceiling is already
  the safety argument, so "no human in the loop" is preserved for the *diagnosis* while a human (or an
  existing inbound incident) initiates it. All four runbooks are still built and validated — they
  differ in the *diagnosis* they run, and each can be initiated by an operator forwarding its trigger
  in phase 5.
  **Named follow-up recorded (operator instruction 2026-11-06, "recorded and do not skip"): `FU-076`
  — unattended machine-trigger ingestion** (ServiceNow webhook, observability alert auto-fire, and
  the dedup / storm-control / backpressure safety design they require). `FU-076` is logged in the
  [delivery roadmap](../../agentic-aiops-platform/delivery-roadmap.md) multi-agent program row and as
  an explicit [tasks](tasks.md) Delivery-Gate checkbox; it is a future spec, not dropped scope.
- **OQ-4 — Live policy: does phase 5 land canonical `agent_roles_any` rule(s), and a tool-family
  axis?** SPEC-074 OQ-3/OQ-4 deferred the tool-name/family axis and the canonical rule to phase 5.
  Options: land minimal canonical role-scoped rules + keep the action-based axis; or add a
  tool-name/family match dimension.
  **RESOLVED (ratified as recommended 2026-11-06):** land the **minimal** canonical `agent_roles_any` rule(s) the four runbooks need
  (a `diagnostician` read posture and an `executor`→`require_approval` encoding), synced across all
  four replicas, and **defer the tool-name/family axis** unless a runbook demonstrably needs
  same-tool-different-role divergence (memo §4.2's example). SPEC-073 toolkit narrowing already
  restricts *what each role sees*, and the shipped bundle is action-based, so the policy axis likely
  stays action-based; adding a tool-family dimension would be a larger axis for no proven need. The
  concrete tool families each runbook names (OQ-7) are the evidence that decides this.
- **OQ-5 — Contract boundary: does phase 5 need any stream/schema change, or does the diagnosis
  surface through existing frames?** ADR-0017 Decision 6 puts the contract change last (phase 6), but
  the operator must *see* the multi-member diagnosis.
  **RESOLVED (ratified as recommended 2026-11-06): no new frame in phase 5.** Surface the orchestrator's synthesized diagnosis as a
  **normal assistant turn**; member reads ride the **existing SPEC-025 evidence frames** with SPEC-075
  role attribution; the proposed remediation rides the **existing SPEC-031 confirmation card**. This
  keeps `agent-stream-event.schema.json` byte-unchanged, honors Decision 6 (the multi-agent wire
  framing is phase 6), and still gives the operator a legible diagnosis + attributable member
  activity + an approvable proposal. A dedicated orchestration-status/member frame is a phase-6
  additive/versioned concern.
- **OQ-6 — Acceptance evidence: what proves phase 5?** This is the first phase with live behavior
  (SPEC-073 OQ-5: "live evidence becomes relevant at phase 5").
  **RESOLVED (ratified as recommended 2026-11-06):** deterministic **mock/fixture-backed end-to-end scenario tests for all four
  runbooks** in CI, **plus a gated live-cluster check** for at least the runbook(s) the dev cluster
  can actually exercise read-only — Kubernetes pod-degradation and observability-alert against the
  live cluster, and ServiceNow-incident against the SPEC-067 in-cluster mock Table-API — mirroring
  the SPEC-065 R-4 / SPEC-067 / SPEC-069 gated live-check pattern and the SPEC-070 "development
  acceptance separated from live integration" discipline. The live check proves the loop actually
  runs **bounded** and **read-only** end-to-end (the four-point gate's point 3), which unit tests
  alone cannot. No live *mutation* is exercised (the proposal only parks).
- **OQ-7 — Scope of the four runbooks: all four fully wired, or capability-once + profiles?** The
  operator chose "all above," but four full live wirings is large.
  **RESOLVED (ratified as recommended 2026-11-06):** build the **runbook-agnostic capability once** (loop + role binding + budget +
  live policy + attribution), express **each of the four runbooks as a declared diagnosis profile**
  (trigger + read toolkit families + proposed-remediation shape), **wire end-to-end the two the
  environment can prove** (Kubernetes pod-degradation and ServiceNow-incident, per OQ-6), and cover
  **all four by scenario tests**. This honors "all four" — every runbook is first-class, specified,
  and tested — while bounding live-wiring effort to what the dev cluster + SPEC-067 mock can actually
  exercise, and keeping the capability generic enough that wiring the other two is a profile, not a
  new loop.

## Changelog

- 2026-11-06: created as `draft` with seven Open Questions; phase 5 of the ADR-0017 series,
  realizing the bounded-autonomous-diagnosis leg (memo §5, §7 step 5) — the **producer** that first
  binds the agent-roles SPEC-073 (v0.54.0), SPEC-074 (v0.55.0), and SPEC-075 (v0.56.0) each landed
  inert. Opened on the operator's direction after v0.56.0 was delivered, tagged, and pushed; the
  operator named **all four** candidate first-workflows (memo §8 Q5), so the loop is built once as a
  runbook-agnostic capability and validated against the union of four real runbooks
  (ServiceNow-incident, observability-alert, post-deploy-verify, Kubernetes-pod-degradation). Seven
  Open Questions block `approved`; the [plan](plan.md) / [tasks](tasks.md) are authored
  **provisional** and become binding on approval. Approval will authorize implementation to *begin* —
  not to merge, commit/push, deploy, or version-bump (separate gates).
- 2026-11-06: **approved** — the operator ratified all seven Open Questions **exactly as
  recommended** (option A). Status `draft` → `approved`; target version pinned **v0.57.0**; the
  [plan](plan.md) / [tasks](tasks.md) provisional banners lifted to **binding**. Per the operator's
  instruction ("recorded and do not skip"), OQ-3's deferral of unattended machine-trigger ingestion
  is recorded as the **named follow-up `FU-076`** in the Non-Goals, the delivery-roadmap multi-agent
  row, and the tasks Delivery Gate. Approval authorizes implementation to *begin* — **not** to merge,
  commit/push, deploy, or version-bump (separate gates).
