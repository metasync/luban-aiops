# SPEC-076 Plan: Bounded Autonomous Diagnosis (The Read-Only Orchestration Loop That First Binds Agent-Roles)

> **BINDING** — approved 2026-11-06. The operator ratified all seven Open Questions in
> [`spec.md`](spec.md) **exactly as recommended**, so the design below (which assumed each OQ's
> recommended resolution) is now binding and the provisional banner is lifted (the SPEC-066/069
> pattern). Design points contingent on an OQ remain tagged `(OQ-n)`. Approval authorizes
> implementation to *begin* — **not** to merge, commit/push, deploy, or version-bump (separate
> gates). OQ-3's deferral is recorded as the named follow-up **`FU-076`** (unattended machine-trigger
> ingestion) — see R-7 and the spec Non-Goals; it is tracked, not dropped.

## Approach

Phase 5 is the **producer** that makes three inert substrates live in a single wiring event. It adds
a **platform-owned bounded read-only orchestration loop** — no agentscope orchestration surface
(ADR-0017 Decision 5) — that drives role-scoped member turns over the *existing* seams rather than
adding a new execution surface:

- the loop reuses `_ensure_toolkit(bearer_token, read_only=True)` (the SPEC-015 automated
  diagnostic-turn toolkit) and `agent_role_scope()` (SPEC-073) to run each `diagnostician` member as
  a bounded read-only turn, and runs the synthesizer as an `orchestrator` (no direct tools);
- the bound role is threaded into both gateway `evaluate()` engines and the canonical
  `policy-default.yaml` gains the minimal `agent_roles_any` rule(s) (SPEC-074 made live, OQ-4);
- each member's audited action and evidence turn carries its `agent_role` (SPEC-075 populated);
- any proposed remediation is *staged* by an `executor` onto the **existing** HITL park +
  signed-dispatch path (SPEC-020/030/031 + SPEC-037/038/063) — zero new mutation machinery;
- everything surfaces through **existing** frames (assistant turn + SPEC-025 evidence + SPEC-031
  card), so `agent-stream-event.schema.json` / `execution-request.schema.json` stay byte-unchanged
  and the multi-agent wire framing stays phase 6 (OQ-5).

The capability is built **once, runbook-agnostic**, and the four operator-named workflows (memo §8
Q5 = all four) are expressed as **declared diagnosis profiles** (trigger + read toolkit families +
proposed-remediation shape), with two wired end-to-end and all four covered by scenario tests
(OQ-7). The work groups into eight stages mirroring R-1…R-8.

## Design Per Requirement

### R-1: The bounded read-only orchestration loop (OQ-1, OQ-2)

- affected files: a new `products/agent-platform/src/agent_service/services/orchestration.py`
  (platform-owned loop, no agentscope pipeline type); the `runtime_kernel.py` turn seams it drives;
  `runtime_settings.py` (the new budget knob).
- chosen approach: a discrete orchestration module runs a **bounded fan-out** of read-only member
  turns over the existing `reply_text(..., read_only=True)` seam, each wrapped in
  `agent_role_scope(AgentRole.DIAGNOSTICIAN)`, with the synthesizer wrapped in
  `agent_role_scope(AgentRole.ORCHESTRATOR)`. The orchestrator consumes only member **summaries**
  (memo §3.1). A new `AGENT_ORCHESTRATION_MAX_STEPS` knob (a deliberate twin of
  `GATEWAY_BROWSER_FLOW_MAX_STEPS`, default `20`, validated `>= 1`) bounds **total member read steps
  per orchestration**; on exhaustion the loop **fails closed** to a budget-limited partial diagnosis.
- alternatives rejected: adopting `TeamPipeline`/`GoalPipeline` (Decision 5 — all fail all four gate
  points as shipped); inlining the fan-out into the single-turn runner (tangles the loop into the
  byte-identical unscoped path and complicates the reachability guard — OQ-1); an unbounded or
  per-member-only budget (loses the total-spend bound that is the safety argument — OQ-2).

### R-2: Role binding via the orchestration frame (OQ-1)

- affected files: `services/orchestration.py`, `runtime_kernel.py` (the `agent_role_scope()`
  brackets around orchestrator/diagnostician/executor turns), and the SPEC-073/074/075
  reachability-guard tests.
- chosen approach: the orchestration frame is the **only** new role-binder. It sets `AGENT_ROLE`
  per participant via `agent_role_scope()` (process-local, not snapshotted — SPEC-073 OQ-2), so
  `current_agent_role_value()` returns non-`None` on the orchestration path and `None` everywhere
  else. The three reachability guards are updated from "no caller binds a role" to "only the
  orchestration frame binds a role."
- alternatives rejected: persisting the role in the SPEC-017 snapshot (SPEC-073 OQ-2 rejected this —
  a park/resume re-derives it per turn); binding a role on the chat/triage/documents paths (would
  break the byte-identical unscoped guarantee and the reachability guard).

### R-3: Same-token identity preservation across the fan-out

- affected files: `services/orchestration.py` (token hand-off to members), the broker-exchange guard
  test.
- chosen approach: the orchestrator passes its **own** delegated `bearer_token` to every member
  turn; no member mints or requests a second broker token. The `REQUESTER_IDENTITY`/`DECIDER_IDENTITY`
  `VerifiedHuman` contextvars are preserved across each hop (the same bracket the single-turn path
  already sets). The role stays process-local — never a claim, header, or wire field.
- alternatives rejected: per-role broker identities (Decision 4 — rejected; materially more identity
  machinery for no read-only gain); carrying the role on the delegated token (SPEC-073 R-3 forbids
  it; the contract framing is phase 6).

### R-4: Diagnose-before-act — mutations park on HITL + signed dispatch

- affected files: `services/orchestration.py` (the propose-remediation hand-off), the `executor`
  staging path (reuses the SPEC-020/030/031 park + SPEC-037/038/063 dispatch).
- chosen approach: the read-only loop never dispatches a mutation. When the diagnosis proposes a
  remediation, an `executor`-scoped step *stages* it onto the **existing** confirmation-card path,
  carrying the SPEC-073 R-4 `staged_by_role` provenance; a **distinct human** approves and the signed
  at-most-one-dispatch worker executes. The SPEC-030 self-approval block fires unchanged (the
  executor acts *as the same human requester*). **Zero new mutation-path code** beyond the staging
  hand-off — no new gate, worker, claim type, or schema. Autonomous resolve stays deferred
  (Decision 2).
- alternatives rejected: an autonomous resolve loop (Decision 2 — explicitly deferred); a
  role-specific approval path (would contradict ADR-0007's one-gate-per-mutating-flow and the
  `executor`→human invariant).

### R-5: Live policy enforcement + the canonical agent-role rule (OQ-4)

- affected files: `products/platform-gateway/src/*/services/policy_engine.py` +
  `products/tool-gateway/src/*/services/policy_engine.py` (thread `agent_role` on the orchestration
  path — the SPEC-074 input already exists), `shared/shared-contracts/policies/policy-default.yaml`
  (+ its three byte-identical replicas via `make sync-policy`), `policy-scenarios.yaml`.
- chosen approach: thread the participant's bound `agent_role` into `evaluate()` on the
  orchestration path, landing the **minimal** canonical `agent_roles_any` rule(s) the four runbooks
  need (a `diagnostician` read posture, an `executor`→`require_approval` encoding). Keep the axis
  **action-based**; **defer the tool-name/family axis** unless a runbook demonstrably needs
  same-tool-different-role divergence (OQ-4). The axis stays subtractive-only + fail-closed.
- alternatives rejected: adding a tool-name/family match dimension now (a larger axis with no proven
  need — toolkit narrowing already restricts what each role sees); leaving policy inert (SPEC-074
  OQ-1 explicitly deferred live enforcement to phase 5, "when a producer exists").

### R-6: Live attribution — the audit/evidence record populated

- affected files: the orchestration path's audit-emitter calls (already thread
  `current_agent_role_value()` per SPEC-075 OQ-2) and the SPEC-025 evidence persistence (already
  carries the additive `agent_role` per SPEC-075 R-4). **No schema change.**
- chosen approach: because SPEC-075 already wired the emitter seam and the evidence-turn field, a
  bound role flows into the audit events and evidence turns **automatically** — phase 5 only needs to
  bind the role (R-2). Each member read, the orchestrator synthesis, and any executor-staged
  proposal is attributed. The `event_type` enum stays closed.
- alternatives rejected: new audit event types for orchestration (SPEC-075 OQ-1 kept the enum
  closed — attribution is a dimension, not a type); deferring attribution to phase 6 (gate point 1
  must hold *by construction* when the loop runs — the whole reason phase 4 preceded phase 5).

### R-7: The four runbook profiles + the trigger boundary (OQ-3, OQ-7)

- affected files: `services/orchestration.py` (the diagnosis-profile shape), a runbook/profile
  declaration (config or module constant), the operator-invoked entry point (portal/chat) **only if**
  OQ-3 lands it, and scenario/e2e tests per runbook.
- chosen approach: build the capability **runbook-agnostic** and express each of the four workflows
  as a **declared diagnosis profile** — trigger + read toolkit families + proposed-remediation shape:
  (a) ServiceNow-incident, (b) observability-alert, (c) post-deploy-verify, (d) k8s-pod-degradation.
  The `diagnostician` toolkit is the **union** of the four runbooks' read-tier families (narrowed per
  token `roles`). Wire **(a)** and **(d)** end-to-end (the dev cluster + SPEC-067 mock can exercise
  them); cover **all four** by scenario tests. Per OQ-3, the phase-5 trigger is **operator-invoked**
  (or anchored on an existing incident record); unattended machine-trigger ingestion is deferred to
  the **named follow-up `FU-076`** (recorded in the delivery-roadmap multi-agent row + the tasks
  Delivery Gate; a future spec, not dropped scope).
- alternatives rejected: hardcoding one runbook into the loop (speculative — the memo §8 Q5 wants the
  split driven by real runbooks; the operator named all four); wiring all four live (larger than the
  environment can prove — OQ-7); building unattended webhook/alert ingestion now (a materially larger
  surface with its own storm/dedup safety questions — OQ-3).

### R-8: Four-point-gate parity, the no-new-frame boundary, and documentation (OQ-5, OQ-6)

- affected files: contract-parity tests (assert `agent-stream-event.schema.json` /
  `execution-request.schema.json` byte-unchanged), the four-point-gate mapping note, and the living
  docs (`identity-and-authorization-design.md`, `authorization-matrix.md`,
  `configuration-reference.md`, the roadmap row, `CHANGELOG.md`).
- chosen approach: record the gate mapping (point 1 audit **live/strengthened**; point 2 identity on
  the one token; point 3 read-only posture enforced by toolkit narrowing + loop admission; point 4 no
  agentscope type on the contract — the loop is platform-owned and surfaces through existing frames).
  Add the `AGENT_ORCHESTRATION_MAX_STEPS` knob (and any trigger knob) to `configuration-reference.md`.
- alternatives rejected: adding an orchestration-status/member SSE frame now (Decision 6 defers the
  contract change to phase 6 — OQ-5); skipping the live-cluster check (unit tests alone cannot prove
  the loop runs bounded + read-only end-to-end — OQ-6).

## Sequencing And Dependencies

1. **Stage 1 — the loop + budget (R-1)** — depends on nothing new; the platform-owned bounded
   read-only fan-out over the existing `read_only=True` seam + the `AGENT_ORCHESTRATION_MAX_STEPS`
   knob. The control-flow anchor.
2. **Stage 2 — role binding (R-2)** — depends on Stage 1; the `agent_role_scope()` brackets + the
   updated reachability guards. Makes SPEC-073 live.
3. **Stage 3 — identity preservation (R-3)** — depends on Stage 2; the same-token hand-off + the
   single-broker-exchange guard across the fan-out.
4. **Stage 4 — live policy (R-5, OQ-4)** — depends on Stage 2; thread `agent_role` into `evaluate()`
   + the minimal canonical rule (synced across four replicas). Makes SPEC-074 live.
5. **Stage 5 — attribution (R-6)** — depends on Stage 2; verify the bound role populates the SPEC-075
   audit/evidence dimension (no schema change). Makes SPEC-075 live.
6. **Stage 6 — diagnose-before-act staging (R-4)** — depends on Stages 2–3; the `executor` staging
   hand-off onto the existing HITL + signed-dispatch path.
7. **Stage 7 — runbook profiles + trigger (R-7, OQ-3/OQ-7)** — depends on Stages 1–6; the four
   declared profiles, two wired end-to-end, the operator-invoked entry.
8. **Stage 8 — gate parity, evidence, docs (R-8, OQ-5/OQ-6)** — depends on all; the contract-parity +
   four-point-gate mapping, the gated live-cluster check, `make verify`, then index / roadmap /
   CHANGELOG on delivery.

## Test Strategy

- unit tests: the bounded loop terminates at `AGENT_ORCHESTRATION_MAX_STEPS` and fails closed to a
  partial diagnosis; a mutating member step is refused inside the loop; the orchestrator toolkit is
  empty of gateway tools; `current_agent_role()` is correct per participant and `None` on the unscoped
  path; the role is not snapshotted (re-derived per turn).
- identity tests: exactly one broker exchange per user across a multi-member fan-out; the requester
  `VerifiedHuman` is unchanged across every hop; no role on any wire field.
- policy tests: an orchestration-path `evaluate()` threads the role; a `diagnostician` cannot reach a
  mutating grant; the canonical bundle change is byte-identical across four replicas; the
  `executor`→human-approver disjointness holds live.
- attribution tests: an orchestration run emits audit events with the correct non-`None` `agent_role`
  per participant; member reads are reconstructable from the evidence record with attribution; an
  unscoped event stays byte-identical.
- mutation-path tests: a proposed remediation parks as a card carrying `staged_by_role`; the
  self-approval block fires; no signed dispatch occurs without an approval; `execution-request`
  byte-unchanged.
- contract tests: `agent-stream-event.schema.json` and `execution-request.schema.json` byte-unchanged
  (no new frame — OQ-5); no schema revision beyond the existing SPEC-074 v3 / SPEC-075 dimensions.
- scenario / e2e: all four runbook profiles covered by mock/fixture-backed end-to-end scenarios; a
  **gated live-cluster** read-only run for the k8s-pod-degradation + observability-alert runbooks and
  the ServiceNow-incident runbook against the SPEC-067 in-cluster mock (OQ-6). No live mutation.
- root `make verify` green (incl. `validate-version`, `validate-policy`, `validate-policy-scenarios`,
  the emitter-parity + contract-parity checks, and the SPEC-063 `execution-failure-test` campaign).

## Rollout And Migration

- deployment or configuration changes: one new knob `AGENT_ORCHESTRATION_MAX_STEPS` (default `20`,
  validated `>= 1`) plus — if OQ-3 lands an operator-invoked entry — any trigger wiring; if OQ-4 lands
  a canonical rule, `policy-default.yaml` + its three replicas change (synced via `make sync-policy`,
  bundle-hash re-provenanced). **No** schema migration (the SPEC-074 policy axis and SPEC-075 audit
  column already exist). The loop is read-only and cannot mutate without the R-4 human gate.
- backward compatibility: the unscoped single-agent chat/triage/documents/skills paths bind no role
  and are byte-identical; a deployment with the orchestration entry unused behaves exactly as v0.56.0.
- rollback approach: revert the orchestration module + the kernel brackets + the policy/trigger
  wiring. Because the substrates (SPEC-073/074/075) are additive and remain inert without the
  orchestration frame, rollback removes the live loop and returns the platform to the v0.56.0
  all-inert posture with no schema or data effect.
- autonomy safety: the read-only posture + the step bound are the safety argument (ADR-0017
  Consequences, "unattended read spend"); every read still rides policy/redaction/evidence/audit, and
  no mutation is possible without a distinct human approver on the existing signed path.
