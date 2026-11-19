# SPEC-078: Conversational Agentic Remediation (composing the delivered diagnosis loop + staging trigger into a human-requested, team-proposed, human-approved flow)

## Status

- status: `delivered`
- owner: chi
- created: 2026-11-18
- promoted from: the [agentic-remediation design spike](../../workspace/agentic-remediation-spike.md)
  (the named follow-up **`FU-077-agentic-remediation`** that
  [SPEC-077](../SPEC-077-operator-diagnose-to-act-bridge/spec.md) deferred out of its R-4),
  **reviewed & approved by the operator 2026-11-18**. All five Open Questions SPEC-077 left
  unresolved are settled **as recommended** (memo §3), and the two scope forks are decided:
  **R2 multi-step remediation plans → a named fast-follow after R1** (not in v1), and the
  **`FU-076-c` in-process role axis → folded into v1** (conditioned on staying in-process, role
  off the wire). This spec carries those resolutions as the **ratified design basis**. **Approved
  2026-11-18** — the seven spec-level Open Questions below (entry mechanism, remediation-intent
  detection, policy action, runbook scope, in-process-axis placement, evidence depth, target
  version) were each ratified by the operator **exactly as recommended** (`draft → approved`), and
  the binding [plan](plan.md) / [tasks](tasks.md) are authored (per the SPEC-066/069/076/077
  pattern). Approval authorizes implementation to *begin* — **not** to merge, commit/push, deploy,
  or version-bump (each a separate gate).
- release slice: the **multi-agent / bounded-autonomy program** — the first increment *after*
  [SPEC-077](../SPEC-077-operator-diagnose-to-act-bridge/spec.md) (`FU-076-b`), composing phase 5
  ([SPEC-076](../SPEC-076-bounded-autonomous-diagnosis/spec.md)) and the diagnose→act trigger
  (SPEC-077) into one conversational flow. Target version **v0.60.0** — a **MINOR** bump over
  v0.59.0 (a new operator-facing capability), per the SPEC-070…077 release-train pattern,
  **pinned on approval 2026-11-18**.
- delivered: 2026-11-19 as **v0.60.0** — R-1…R-7 implemented as the **conversational agentic
  remediation** entry (**`FU-077-agentic-remediation`** closed): an opt-in coupled
  `remediation_intent` + `remediation_profile` flag on `AgentChatRequest` / the gateway `ChatRequest`
  (`extra="forbid"`, **no** `agent_role`) **additionally** gated by the **reused** deny-by-default
  `remediate:stage` action, drives `run_conversational_remediation(...)` composing the **delivered**
  SPEC-076 `run_bounded_diagnosis(...)` + SPEC-077 `stage_remediation(...)` **verbatim** — the
  diagnosis narrative streams through the **existing** v0.59.0 `TurnStreamer` and the single proposed
  mutating call parks through the **existing** `ConfirmationCoordinator` → the SPEC-020/030/031 card
  for a **distinct human** (SPEC-030 self-approval block unchanged), dispatched only by the signed
  at-most-one-dispatch worker. **R-3 makes the SPEC-074 `agent_roles_any` axis fire *in-process*** at
  the executor-staging seam (`_enforce_staging_role_axis`; **`FU-076-c` closed**), role still **off
  every wire field**, both gateway rules inert on the wire until phase 6. **Zero new mutation-path
  machinery**; `agent-stream-event`/`execution-request` **byte-unchanged**; `event_type` enum closed
  (the gateway reuses `chat_completed`); the unscoped single-agent chat path **byte-identical**; **no
  new knob** (reuses `PLATFORM_GATEWAY_REMEDIATE_TIMEOUT_SECONDS` + `AGENT_ORCHESTRATION_MAX_STEPS`).
  **R2** (multi-step plans) is a named fast-follow; **R3** (autonomous resolve) + `FU-076` stay
  deferred. Evidence: the conversational-flow scenario + attribution + in-process role-axis tests, the
  gated `conversational-remediation-livecheck.sh` (park + **zero** dispatch + no auto-approval), and
  the recorded SPEC-018 four-point-gate mapping (full agent-platform suite **1899**, platform-gateway
  **536**, root `make verify` green across every leg incl. the SPEC-063 execution-failure campaign
  **795**). Released as **v0.60.0** (2026-11-19); commit/tag/push remained separate operator gates.
- related ADRs: [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md)
  (**Decision 2** the diagnose-before-act autonomy ceiling — **unchanged**; **Decision 4**
  role-scoped agents on the same delegated token; **Decision 5** no agentscope orchestration
  surface), [ADR-0007](../../adr/0007-browser-flow-single-hitl-gate.md) (one HITL gate per
  mutating flow — the `executor`→**distinct-human**-approver invariant),
  [ADR-0010](../../adr/0010-signed-execution-envelopes-declare-authority-provenance.md) /
  [ADR-0013](../../adr/0013-durable-single-use-execution-claims.md) (provenance + durable
  single-use dispatch — unchanged), and
  [ADR-0011](../../adr/0011-composition-carries-no-authority.md) (a composition carries no
  authority — so a future multi-step plan is N *individually*-gated proposals, never a
  transaction). **No new ADR is expected**: memo §3.4 confirms SPEC-078 stays **under** the
  Decision-2 ceiling — autonomous resolve is deferred and its revisit trigger ("after bounded
  read-only diagnosis is proven in production") is **not met**.
- extends: [SPEC-076](../SPEC-076-bounded-autonomous-diagnosis/spec.md) (the delivered bounded
  read-only orchestration loop this makes conversational),
  [SPEC-077](../SPEC-077-operator-diagnose-to-act-bridge/spec.md) (the delivered `executor`
  `stage_remediation(...)` + `remediate:stage` action this reaches from a chat turn),
  [SPEC-073](../SPEC-073-role-scoped-agent-identity/spec.md) (roles + the **R-3 role-off-the-wire**
  invariant this preserves), [SPEC-074](../SPEC-074-policy-role-axis/spec.md) (the
  `agent_roles_any` axis this makes **live in-process** = `FU-076-c`),
  [SPEC-075](../SPEC-075-multi-agent-audit-attribution/spec.md) (the `agent_role` audit dimension
  this populates), [SPEC-020](../SPEC-020-hitl-confirmation-bridging/spec.md) /
  [SPEC-030](../SPEC-030-require-approval-policy-semantics/spec.md) /
  [SPEC-031](../SPEC-031-approval-inbox-persistent-confirmation/spec.md) (the existing HITL park,
  self-approval block, and approval inbox the proposal rides), and
  [SPEC-037](../SPEC-037-signed-execution-requests/spec.md) /
  [SPEC-038](../SPEC-038-isolated-execution-worker/spec.md) /
  [SPEC-063](../SPEC-063-crash-safe-execution/spec.md) (the signed at-most-one-dispatch worker that
  alone executes an approved proposal).

## Problem

Phases 2–5 landed the multi-agent substrate and SPEC-077 wired the production staging trigger,
but the two halves are reachable **only** through dedicated operator-initiated endpoints
(`POST /api/v2/diagnose`, `POST /api/v2/remediate`), and the operator portal has **no** diagnosis
or remediation surface at all (SPEC-076 shipped backend-only; the portal was last touched by
SPEC-072 / v0.53.0). Nothing today drives *diagnose → propose → stage* from **within a
conversational chat turn**.

SPEC-077's R-4 (a portal **Stage remediation** button on a completed-diagnosis card) was
**deferred** post-approval because the ratified premise was false (there is no diagnosis card) and
because the operator's product direction supersedes a button-on-a-card: remediation should be
**agentic / multi-agent** — *human-requested, carried out by an agent team, surfacing through the
existing conversational portal surface, or graduated autonomy*. That direction is
`FU-077-agentic-remediation`, and this spec is its promotion. The backend trigger (SPEC-077) is
its **prerequisite** and is already shipped: any entry shape reaches the same wired
`stage_remediation`.

## Approach (ratified design basis — memo §3)

Add a **conversational remediation flow**: on a remediation-intent chat turn, the kernel drives the
**delivered** SPEC-076 bounded read-only diagnosis loop (an `orchestrator` fanning out read-only
`diagnostician` members on the *same* delegated token), synthesizes a diagnosis + a *proposed*
remediation, and the **delivered** SPEC-077 `executor` `stage_remediation(...)` stages that proposal
onto the **existing** HITL confirmation card — all surfaced through the **existing** chat SSE stream
(the v0.59.0 `TurnStreamer` seam) and the **existing** confirmation card / approval inbox (the
v0.59.0 `ConfirmationCoordinator` seam). A **distinct human** approves; the signed
at-most-one-dispatch worker (SPEC-037/038/063) alone executes.

The flow is a **composition + entry** change, **not** a mutation-path, trust-model, or contract
change: it adds **zero** new mutation-path machinery, keeps `agent_role` **off every wire field**
(SPEC-073 R-3), leaves `agent-stream-event.schema.json` and `execution-request.schema.json`
**byte-unchanged** (single-voice projection through existing frames, so the phase-6 v2 contract is
**not** a prerequisite), and holds the autonomy ceiling at **every mutation human-approved**
(ADR-0017 Decision 2, unchanged). It also makes the SPEC-074 `agent_roles_any` policy axis fire
**in-process** at the staging seam (`FU-076-c`), and stays **opt-in / intent-gated** so the deployed
**unscoped single-agent chat path remains byte-identical** when no remediation is requested.

## Requirements

> Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.
> Every requirement preserves SPEC-018's four-point gate, the ADR-0017 Decision-2 ceiling, and the
> byte-identical unscoped-single-agent chat path.

### R-1: A conversational remediation entry (chat turn → diagnose → propose → stage)

A remediation-intent chat turn drives the delivered SPEC-076 diagnosis loop and the delivered
SPEC-077 `stage_remediation(...)` **in-process**, within the kernel's normal reply path, and surfaces
the result through the **existing** chat SSE stream + the **existing** SPEC-031 confirmation card. No
new portal view, no diagnosis card, no discrete button. The entry is **opt-in / intent-gated**: a turn
that does not request remediation binds no role and runs the unscoped single-agent path
**byte-identically**.

- **Acceptance:** a remediation-intent turn produces a streamed diagnosis narrative and parks **one**
  proposed mutating call as a confirmation card carrying `staged_by_role="executor"`; a non-remediation
  turn is byte-identical to today (no role bound, no orchestration frame); the route itself dispatches
  **nothing**.

### R-2: Team-proposal composition reusing delivered machinery (zero new mutation path)

The team **proposes; a human disposes.** The flow composes the delivered SPEC-076 loop (read-only,
bounded by `AGENT_ORCHESTRATION_MAX_STEPS`, failing closed to a partial diagnosis) and the delivered
SPEC-077 `executor` staging turn (`read_only=False`, one turn, `{session_id}::orch::staging`, same
delegated token) **verbatim**. The proposal parks on the existing HITL card; the SPEC-030
self-approval block and the `executor`→**distinct-human**-approver disjointness are unchanged; the
signed at-most-one-dispatch worker alone executes. **No** new gate, worker, claim type, dispatch
path, or schema.

- **Acceptance:** no `TeamPipeline`/`GoalPipeline`/`A2AAgent` (or any agentscope orchestration surface)
  is constructed on the path (a guard test asserts the loop is platform-owned, mirroring SPEC-076 R-1);
  the stager can never be the approver; a diagnosis-only profile (`remediation_shape is None`) fails
  closed and never opens an executor turn (mirrors SPEC-077 R-2).

### R-3: The in-process role-axis policy check goes live (`FU-076-c`)

Make the SPEC-074 `agent_roles_any` axis **fire in-process** at the executor-staging seam — the
kernel, which already knows the bound role from the `AGENT_ROLE` contextvar, evaluates the role axis
**in-process**, *complementary to* (not replacing) the tool-gateway's deny-by-default `evaluate()`.
The role stays **off every wire field** (SPEC-073 R-3 preserved); no contract field is added and no
deployed gateway `evaluate()` is changed. **Condition:** if implementation grounding finds the axis
cannot fire without a wire change, it reverts to deferred rather than breaking R-3.

- **Acceptance:** an in-process role-axis rule (e.g. an `executor` may stage the mutating tool; a
  `diagnostician` may not) is evaluated and enforced at the staging seam with the role never crossing
  a wire field; `validate-policy` + `validate-policy-scenarios` stay green; a byte-freeze assertion
  confirms `agent-stream-event`/`execution-request` unchanged and no `agent_role` on any wire field.

### R-4: Audit attribution (the conversational flow is reconstructable)

Every turn of the conversational flow audits with the SPEC-075 `agent_role` dimension
(`orchestrator`/`diagnostician` for the read-only fan-out, `executor` for the staging turn), and the
parked card carries the SPEC-073 `staged_by_role="executor"` provenance. The diagnose→propose→approve→
execute chain is reconstructable from the durable trail and attributable to the same human +
delegated token. The `event_type` enum stays **closed** (no new event type).

- **Acceptance:** the fan-out and staging turns emit audit events carrying the correct `agent_role`;
  the six-emitter parity family and contract-parity tests stay green; no new `event_type` is added.

### R-5: Contract boundary — existing frames only, single-voice projection

The flow rides **existing** frames only (the assistant turn, the SPEC-025 evidence turn, the SPEC-031
confirmation card, `execution-request.schema.json`). Member (diagnostician) activity is narrated into
the **one** session stream (single-voice projection) and attributed in audit — **not** surfaced as a
new multi-agent frame. `agent-stream-event.schema.json` and `execution-request.schema.json` stay
**byte-unchanged**; the **phase-6 v2 multi-agent contract** is **not** a prerequisite and stays open.

- **Acceptance:** a byte-freeze assertion on both schemas; no agentscope type leaks through the
  platform-owned v2 contract (gate point 4).

### R-6: The autonomy gradient is recorded as binding (ceiling fixed; R2/R3 deferred)

The spec records the autonomy gradient (memo §3.3) as binding: the **ceiling is "every mutation is
human-approved."** SPEC-078 v1 delivers **R1** (conversational diagnose→propose→stage). **R2**
(multi-step remediation plans) is a **named fast-follow after R1** and, when built, stays N
*individually*-gated proposals (ADR-0011 — never a composite approval, never an automatic
multi-dispatch). **R3** (autonomous resolve) stays **deferred** behind the ADR-0017 Decision-2 revisit
trigger.

- **Acceptance:** the gradient + ceiling are stated in the spec and the authorization matrix; no path
  dispatches a mutation without a distinct-human approval; autonomous resolve is absent.

### R-7: Evidence — the four-point gate + a gated live-check + docs

Record the SPEC-018 four-point-gate mapping. Add scenario tests covering the conversational flow
(a remediation-intent turn parks one proposal; a non-remediation turn is byte-identical; a
diagnosis-only profile fails closed) and the in-process role-axis rule. Add a **gated**
live-cluster check mirroring `remediation-livecheck.sh` that drives one **authorized, billable**
conversational remediation and asserts the proposal **parks** with **zero** `execution_requested`
dispatch and **no** HITL auto-approval (the mocked-I/O leg collected by `make test` so it cannot be
skipped silently). Reconcile living docs: the authorization matrix (the conversational entry + the
now-live in-process role axis), the configuration reference (any new knob), the delivery roadmap
(`FU-077-agentic-remediation` / `FU-076-c` closed; R2 recorded as the fast-follow), the spec index
(this row), and `CHANGELOG.md`.

- **Acceptance:** scenario tests green; the gated live-check asserts park + zero dispatch + no
  auto-approval; `make verify` green across every leg; docs reconciled.

## Non-Goals

- **Autonomous resolve / auto-dispatch (R3).** Deferred behind the ADR-0017 Decision-2 revisit trigger
  (production-proven bounded diagnosis + a new trust-model ADR). The staged proposal **always** parks
  for a distinct human; the SPEC-030 self-approval block is unchanged.
- **Multi-step remediation plans (R2).** A named **fast-follow after R1 ships** (operator 2026-11-18),
  not in v1; when built it stays N *individually*-gated proposals (ADR-0011), never a composite
  approval or an automatic multi-dispatch.
- **Unattended machine-trigger ingestion** (webhook/alert auto-fire, dedup, storm control) — that is
  `FU-076`, a separate future spec; SPEC-078 stays **human-requested**.
- **The phase-6 v2 multi-agent wire contract.** Existing frames only (R-5); single-voice projection.
- **A portal diagnosis card / Stage-remediation button.** Explicitly rejected by the operator's
  direction; the entry is conversational (R-1).
- **New mutation-path machinery** — no new gate, worker, claim type, dispatch path, or schema.
- **New runbooks or widening `remediation_shape`.** The two stageable profiles
  (`post-deploy-verify`, `k8s-pod-degradation`) ship as declared; diagnosis-only profiles stay
  diagnosis-only and fail closed.
- **Adopting any agentscope orchestration surface** (`TeamPipeline`/`GoalPipeline`/`A2AAgent`) —
  kept out by ADR-0017 Decision 5.

## Open Questions

> The five **design** questions SPEC-077 deferred are **resolved** in the approved
> [memo](../../workspace/agentic-remediation-spike.md) §3 and recorded as the ratified design basis
> above. The seven **spec-level** questions below were each **ratified by the operator exactly as
> recommended 2026-11-18** (`draft → approved`), on which the binding [plan](plan.md) /
> [tasks](tasks.md) were authored.

- **OQ-1 — Conversational entry mechanism.** Does the kernel reach the flow via a **model-selected
  tool** the orchestrator calls (closest to today's tool-driven turns), or an **explicit gateway
  route / intent flag** the portal sets on a remediation-intent message? **Resolved (ratified 2026-11-18): the explicit
  route/flag** — it keeps remediation-intent determination deterministic and auditable, cleanly
  preserves the byte-identical unscoped-chat path (R-1), and carries the `remediate:stage` policy
  action without relying on model classification. (Memo §3.1 left this to the spec's plan.)
- **OQ-2 — Remediation-intent detection.** How does the platform know a turn requests remediation —
  an explicit operator affordance (a mode/command/intent flag), or model-classified intent?
  **Resolved (ratified 2026-11-18): an explicit affordance** (pairs with OQ-1), so a normal chat turn never silently
  widens into a mutation-adjacent flow.
- **OQ-3 — Policy action.** Does the conversational flow **reuse** the delivered `remediate:stage`
  action (SPEC-077 R-3) for the staging leg, with the read-only diagnosis riding the existing `chat`
  action? **Resolved (ratified 2026-11-18): reuse `remediate:stage`** — no new action; the staging leg is the same
  mutation-adjacent operation SPEC-077 already gates.
- **OQ-4 — Runbook scope for v1.** The same two stageable profiles (`post-deploy-verify`,
  `k8s-pod-degradation`), with the two diagnosis-only profiles failing closed? **Resolved (ratified 2026-11-18): yes** —
  unchanged from SPEC-077; no new runbooks.
- **OQ-5 — In-process role-axis placement + canonical rule (R-3 / `FU-076-c`).** Exactly where does
  the in-process `agent_roles_any` check fire (the staging seam), and what is the first canonical
  rule? **Resolved (ratified 2026-11-18):** fire at the executor-staging seam in the kernel; the canonical rule asserts an
  `executor` may stage the profile's mutating tool while a `diagnostician`/`orchestrator` may not —
  proven via `policy-scenarios.yaml`, with `policy-default.yaml` byte-unchanged unless a rule must be
  canonical.
- **OQ-6 — Evidence depth.** A gated billable live-check mirroring `remediation-livecheck.sh` (park +
  zero dispatch + no auto-approval) plus scenario tests and the four-point-gate mapping?
  **Resolved (ratified 2026-11-18): yes** (the mocked leg collected by `make test`; the live leg an explicit operator step).
- **OQ-7 — Target version.** A MINOR bump over v0.59.0? **Resolved (ratified 2026-11-18): yes** — a new operator-facing
  capability, per the SPEC-070…077 release-train pattern; pinned on approval.

## Changelog

- 2026-11-18 — created as `draft`, promoted from the operator-approved
  [agentic-remediation design spike](../../workspace/agentic-remediation-spike.md)
  (`FU-077-agentic-remediation`). Carries the five memo resolutions as the ratified design basis
  (conversational entry; team-proposal; autonomy ceiling fixed with R2 a fast-follow and R3 deferred;
  no ADR-0017 Decision-2 revisit; `FU-076-c` folded into v1 in-process) and raises seven spec-level
  Open Questions (entry mechanism, intent detection, policy action, runbook scope, in-process-axis
  placement, evidence, target version), each recommended and pending formal ratification. No
  implementation, merge, commit/push, deployment, or version bump authorized by this draft.
- 2026-11-18 — **approved** (`draft → approved`): the operator ratified all seven spec-level Open
  Questions **exactly as recommended** — OQ-1 the explicit gateway route / intent flag (not a
  model-selected tool); OQ-2 an explicit operator affordance (not model-classified intent); OQ-3
  reuse the delivered `remediate:stage` action (no new action); OQ-4 the same two stageable profiles
  (`post-deploy-verify`, `k8s-pod-degradation`), diagnosis-only profiles fail closed; OQ-5 the
  in-process `agent_roles_any` check fires at the executor-staging seam with the canonical
  executor-may-stage / diagnostician-may-not rule; OQ-6 the gated billable live-check (park + zero
  dispatch + no auto-approval) + scenario tests + the four-point-gate mapping; OQ-7 a MINOR bump
  over v0.59.0. Target version pinned **v0.60.0**; the binding [plan](plan.md) / [tasks](tasks.md)
  are authored. Approval authorizes implementation to *begin* — not to merge, commit/push, deploy,
  or version-bump (each a separate gate).
- 2026-11-19 — **delivered as v0.60.0** (`approved → delivered`): R-1…R-7 implemented and verified
  across the seven binding stages — the opt-in coupled `remediation_intent` + `remediation_profile`
  flag on `AgentChatRequest` / the gateway `ChatRequest` (`extra="forbid"`, **no** `agent_role`)
  additionally gated by the **reused** deny-by-default `remediate:stage` action (R-1/R-5);
  `run_conversational_remediation(...)` composing the delivered SPEC-076 `run_bounded_diagnosis(...)`
  + SPEC-077 `stage_remediation(...)` verbatim over the existing `TurnStreamer` + `ConfirmationCoordinator`
  seams (R-2); the in-process SPEC-074 `agent_roles_any` axis firing at the executor-staging seam
  (`_enforce_staging_role_axis`; **`FU-076-c` closed**, role off every wire field) (R-3); one-turn
  audit attribution across the diagnostician/orchestrator/executor span (R-4); and the gated
  `conversational-remediation-livecheck.sh` + scenario tests + four-point-gate mapping (R-6/R-7).
  **`FU-077-agentic-remediation` closed.** Zero new mutation-path machinery; `agent-stream-event` /
  `execution-request` byte-unchanged; the unscoped single-agent chat path byte-identical; **no new
  knob** (reuses `PLATFORM_GATEWAY_REMEDIATE_TIMEOUT_SECONDS` + `AGENT_ORCHESTRATION_MAX_STEPS`).
  Evidence: full agent-platform suite **1899**, platform-gateway **536**, root `make verify` green
  across every leg incl. the SPEC-063 execution-failure campaign **795**. **R2** (multi-step plans)
  is a named fast-follow; **R3** (autonomous resolve) + `FU-076` stay deferred. The `VERSION` bump to
  **v0.60.0** + the spec-index `delivered` flip landed in the release commit; commit/tag/push remained
  separate operator gates.
