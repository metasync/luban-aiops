# SPEC-078 Plan: Conversational Agentic Remediation (composing the delivered diagnosis loop + staging trigger into a human-requested, team-proposed, human-approved flow)

> **BINDING** — approved 2026-11-18. The operator ratified all seven Open Questions in
> [`spec.md`](spec.md) **exactly as recommended**, so the design below (which assumed each OQ's
> recommended resolution) is now binding and the provisional banner is lifted (the SPEC-066/069/076/077
> pattern). Design points contingent on an OQ remain tagged `(OQ-n)`. Approval authorizes
> implementation to *begin* — **not** to merge, commit/push, deploy, or version-bump (separate gates).
> This increment is a **composition + entry** change over already-delivered, already-unit-proven
> machinery: **zero new mutation-path machinery**, role **off every wire field** (SPEC-073 R-3),
> `agent-stream-event`/`execution-request` **byte-unchanged**, and the **unscoped single-agent chat
> path byte-identical**. Two siblings stay deferred and are **not** pulled in here: **`FU-076`**
> (unattended machine-trigger ingestion) and **R2** multi-step remediation plans (a named fast-follow
> after R1); **R3** autonomous resolve stays deferred behind the ADR-0017 Decision-2 revisit trigger.
> **`FU-076-c`** (the live in-process role axis) **is** folded into v1 (R-3).

## Approach

SPEC-078 wires the two delivered halves of the bounded-autonomy program into **one conversational
chat-turn flow**. Phase 5 (v0.57.0) shipped the platform-owned bounded read-only diagnosis loop
(`run_bounded_diagnosis(...)` in `services/orchestration.py` — an `orchestrator` fanning out read-only
`diagnostician` members, bounded by `AGENT_ORCHESTRATION_MAX_STEPS`, failing closed to a partial
diagnosis); SPEC-077 (v0.58.0) shipped the `executor` staging trigger (`stage_remediation(...)` in the
same module). Both are reachable **only** through dedicated operator-initiated endpoints
(`POST /api/v2/diagnose`, `POST /api/v2/remediate`); nothing drives *diagnose → propose → stage* from
**within a chat turn**. This spec adds that entry and nothing else on the mutation path:

- an **explicit remediation-intent flag** on the chat request (OQ-1/OQ-2 — deterministic + auditable,
  **not** a model-selected tool), gated by the **reused** deny-by-default `remediate:stage` action
  (OQ-3), so a normal chat turn never silently widens into a mutation-adjacent flow;
- a **conversational composition** that calls the delivered `run_bounded_diagnosis(...)` then
  `stage_remediation(...)` **verbatim**, streaming the diagnosis narrative through the **existing**
  `TurnStreamer` seam and parking the single proposed mutating call through the **existing**
  `ConfirmationCoordinator` seam → the existing SPEC-020/030/031 card + approval inbox;
- the **in-process** role-axis check that finally makes the SPEC-074 `agent_roles_any` axis fire
  (`FU-076-c` / R-3, OQ-5) at the executor-staging seam, with the role never crossing a wire field;
- everything surfaces through **existing** frames (`AgentChatResponse`, the assistant turn, the SPEC-025
  evidence turn, the SPEC-031 card, `execution-request.schema.json`), single-voice projected, so both
  stream/execution schemas stay **byte-unchanged** and the phase-6 v2 multi-agent contract is **not** a
  prerequisite.

A turn without the intent flag runs the unscoped single-agent path (`reply_text` / `TurnStreamer`)
**byte-identically**. A diagnosis-only profile (`remediation_shape is None`) or an unknown profile
**fails closed** and never opens an executor turn (mirrors SPEC-077 R-2). The staged proposal **always**
parks for a **distinct human** approver; the signed at-most-one-dispatch worker (SPEC-037/038/063) alone
dispatches, and the SPEC-030 self-approval block fires unchanged. The work groups into seven stages
mirroring R-1…R-7.

## Design Per Requirement

### R-1: A conversational remediation entry (OQ-1, OQ-2)

- affected files: `products/agent-platform/src/agent_service/schemas/v2.py` (an opt-in
  remediation-intent flag + `profile` on `AgentChatRequest`, `extra="forbid"`, **no** `agent_role`);
  `products/agent-platform/src/agent_service/api/v2/routes.py` (the `chat` handler at L346 and the
  `GET /api/v2/chat/stream` SSE path at L591 branch on the flag);
  `products/agent-platform/src/agent_service/services/orchestration.py` (a new
  `run_conversational_remediation(...)` composing the delivered `run_bounded_diagnosis(...)` +
  `stage_remediation(...)`); `products/agent-platform/src/agent_service/services/kernel_streaming.py`
  (`TurnStreamer` — the streamed narrative) and `.../kernel_confirmations.py` (`ConfirmationCoordinator`
  — the park); and the platform-gateway chat proxy + `agent_client` (mirroring the `/diagnose` +
  `/remediate` proxies).
- chosen approach: the portal sets an explicit remediation-intent flag (OQ-1/OQ-2) on a chat turn. When
  it is set **and** the caller holds `remediate:stage`, the turn drives
  `run_conversational_remediation(...)` in-process: the `orchestrator` runs the delivered bounded
  read-only diagnosis loop, synthesizes a diagnosis + a *proposed* remediation, and the `executor`
  stages it via the delivered `stage_remediation(...)` — the narrative streaming through `TurnStreamer`
  and the proposal parking through `ConfirmationCoordinator`. The route binds **no** role itself (the
  composition binds `orchestrator`/`diagnostician`/`executor` in-process) and the body carries none.
  When the flag is absent, `reply_text` / `TurnStreamer` run the unscoped single-agent path
  byte-identically (R-1 acceptance).
- alternatives rejected: a **model-selected tool** the orchestrator calls (OQ-1 — non-deterministic
  intent classification, harder to gate behind a dedicated deny-by-default action, and it risks silently
  widening a normal turn into a mutation-adjacent flow); a **new portal view / diagnosis card /
  Stage-remediation button** (explicitly rejected by the operator's direction — the entry is
  conversational; SPEC-077 R-4 was deferred for exactly this reason).

### R-2: Team-proposal composition reusing delivered machinery (zero new mutation path)

- affected files: `services/orchestration.py` (compose `run_bounded_diagnosis(...)` +
  `stage_remediation(...)` **unchanged**); a guard test asserting no agentscope orchestration surface is
  constructed on the path (mirroring the SPEC-076 R-1 guard).
- chosen approach: the team **proposes; a human disposes.** `run_conversational_remediation(...)` calls
  the delivered functions verbatim — the read-only fan-out stays bounded by
  `AGENT_ORCHESTRATION_MAX_STEPS` and fails closed to a partial diagnosis; the executor staging turn
  stays **one** `read_only=False` turn on `{session_id}::orch::staging` over the *same* delegated token.
  The proposal parks on the existing HITL card; the SPEC-030 self-approval block and the
  `executor`→**distinct-human**-approver disjointness are unchanged; the signed at-most-one-dispatch
  worker alone executes. A diagnosis-only profile (`remediation_shape is None`) fails closed and never
  opens an executor turn. **No** new gate, worker, claim type, dispatch path, or schema.
- alternatives rejected: constructing a `TeamPipeline`/`GoalPipeline`/`A2AAgent` (ADR-0017 Decision 5 —
  no agentscope orchestration surface); re-running the fan-out at staging time (a second billable
  fan-out that could diverge from what the operator read); a **composite** approval for a multi-step
  plan (ADR-0011 — a composition carries no authority; R2 is a fast-follow and stays N
  *individually*-gated proposals).

### R-3: The in-process role-axis policy check goes live (`FU-076-c`) (OQ-5)

- affected files: a new in-process role-axis evaluation point at the executor-staging seam in
  `services/orchestration.py` (reading the bound role via
  `products/agent-platform/src/agent_service/services/agent_role.py`'s `current_agent_role_value()`);
  the canonical rule expectation in `policy-scenarios.yaml`; the **existing** `agent_roles_any` axis in
  `shared/shared-contracts/policies/policy-rule.schema.json` (v3 — unchanged); and
  `policy-default.yaml` (**byte-unchanged** unless a rule must be canonical, OQ-5). **Neither** gateway
  `evaluate()` engine is changed.
- chosen approach: at the staging seam the kernel — which already knows the bound role from the
  `AGENT_ROLE` contextvar — evaluates the `agent_roles_any` axis **in-process**, *complementary to* (not
  replacing) the tool-gateway's deny-by-default `evaluate()`. The first canonical rule asserts an
  `executor` may stage the profile's mutating tool while a `diagnostician`/`orchestrator` may not, proven
  via `policy-scenarios.yaml`. The role stays **off every wire field** (SPEC-073 R-3 preserved); no
  contract field is added and no deployed gateway `evaluate()` is changed. **Condition (R-3):** if
  implementation grounding finds the axis cannot fire without a wire change, R-3 reverts to **deferred**
  (recorded in the Delivery Gate, not forced) rather than breaking the role-off-the-wire invariant.
- alternatives rejected: threading the bound role to a gateway `evaluate()` (would put the role on the
  wire, breaking SPEC-073 R-3); deferring the axis to the phase-6 v2 contract (the single-voice
  projection means phase 6 is **not** a prerequisite).

### R-4: Audit attribution (the conversational flow is reconstructable)

- affected files: **none new** — the delivered loop + `stage_remediation(...)` already audit with the
  SPEC-075 `agent_role` dimension and park with the SPEC-073 `staged_by_role` provenance. This stage only
  **verifies** it end-to-end on the conversational path.
- chosen approach: the read-only fan-out turns audit `agent_role="orchestrator"`/`"diagnostician"`; the
  staging turn audits `agent_role="executor"`; the parked card carries `staged_by_role="executor"`. The
  diagnose→propose→approve→execute chain is reconstructable from the durable trail and attributable to
  the same human + delegated token. The `event_type` enum stays **closed** (the gateway reuses
  `chat_completed`); the six-emitter parity family + contract-parity tests stay green.
- alternatives rejected: adding a new `remediation_staged` event type (widens the closed enum across all
  six emitters and duplicates what `agent_role="executor"` already conveys).

### R-5: Contract boundary — existing frames only, single-voice projection

- affected files: `schemas/v2.py` (the intent flag is `extra="forbid"` and carries **no** `agent_role`),
  and the contract-parity tests that byte-freeze `agent-stream-event.schema.json` +
  `execution-request.schema.json`.
- chosen approach: the flow rides **existing** frames only (the assistant turn, the SPEC-025 evidence
  turn, the SPEC-031 confirmation card, `execution-request.schema.json`). Member (`diagnostician`)
  activity is narrated into the **one** session stream (single-voice projection) and attributed in audit
  — **not** surfaced as a new multi-agent frame. Both stream/execution schemas stay **byte-unchanged**;
  no `agent_role` crosses any wire field; the phase-6 v2 multi-agent contract stays out of scope.
- alternatives rejected: adding an `agent_role` request/response field (SPEC-073 R-3 forbids it; the
  contract framing is phase 6); a new multi-agent stream frame (phase 6, not a prerequisite).

### R-6: The autonomy gradient is recorded as binding (ceiling fixed; R2/R3 deferred)

- affected files: `docs/agentic-aiops-platform/authorization-matrix.md` (the conversational entry + the
  now-live in-process role axis) and this spec; **no** dispatch-path change.
- chosen approach: the **ceiling is "every mutation is human-approved."** SPEC-078 v1 delivers **R1**
  (conversational diagnose→propose→stage). **R2** (multi-step remediation plans) is a **named
  fast-follow after R1** and, when built, stays N *individually*-gated proposals (ADR-0011 — never a
  composite approval, never an automatic multi-dispatch). **R3** (autonomous resolve) stays **deferred**
  behind the ADR-0017 Decision-2 revisit trigger (production-proven bounded diagnosis + a new
  trust-model ADR). No path dispatches a mutation without a distinct-human approval.
- alternatives rejected: autonomous resolve / auto-dispatch (R3 — the Decision-2 ceiling is unchanged and
  its revisit trigger is **not** met); pulling R2 multi-step plans into v1 (operator decision 2026-11-18:
  a named fast-follow).

### R-7: Evidence — the four-point gate + a gated live-check + docs (OQ-6)

- affected files: scenario tests (`products/agent-platform/tests/test_orchestration.py` + a new
  conversational-flow test); a new `e2e/conversational-remediation-livecheck.sh` (mirroring
  `e2e/remediation-livecheck.sh`) + a `make conversational-remediation-livecheck` target; the
  four-point-gate mapping note; and the living docs (`authorization-matrix.md`,
  `configuration-reference.md`, the `delivery-roadmap.md` multi-agent row, `docs/specs/README.md` index,
  `CHANGELOG.md`).
- chosen approach: scenario tests assert a remediation-intent turn parks **one** proposal, a
  non-remediation turn is **byte-identical**, a diagnosis-only profile **fails closed**, and the
  in-process role-axis rule fires. A **gated live-cluster** check drives one authorized, billable
  conversational remediation and asserts the proposal **parks** with **zero** `execution_requested`
  dispatch and **no** HITL auto-approval; the mocked-I/O leg is collected by `make test` so it cannot be
  skipped silently, and the live leg is an explicit operator step. The SPEC-018 four-point-gate mapping
  is recorded. Living docs are reconciled and `make verify` is green across every leg.
- alternatives rejected: unit tests alone (cannot prove the park + zero-dispatch end-to-end on a live
  cluster); an ungated always-live check (would incur cost on every `make test`).

## Sequencing And Dependencies

1. **Stage 1 — contract + intent flag (R-1, R-5)** — the opt-in remediation-intent flag on
   `AgentChatRequest` (`extra="forbid"`, no `agent_role`) and the byte-identical guard proving the
   unscoped single-agent path is unchanged when the flag is absent. Depends on nothing new; the safe
   foundation.
2. **Stage 2 — the conversational composition (R-1, R-2)** — `run_conversational_remediation(...)`
   composing the delivered `run_bounded_diagnosis(...)` + `stage_remediation(...)` verbatim, streamed via
   `TurnStreamer` and parked via `ConfirmationCoordinator`, failing closed on a diagnosis-only/unknown
   profile. Depends on Stage 1.
3. **Stage 3 — the gateway entry + policy gate (R-1, R-5)** — the platform-gateway chat proxy carries the
   intent flag and evaluates the **reused** `remediate:stage` action (OQ-3) deny-by-default (a token
   without it is denied **403** and the turn stays unscoped). Depends on Stage 2.
4. **Stage 4 — the in-process role axis (R-3, `FU-076-c`, OQ-5)** — the in-process `agent_roles_any`
   check at the executor-staging seam + the canonical rule in `policy-scenarios.yaml`; role off the wire.
   Depends on Stage 2. Reverts to deferred if it cannot fire without a wire change.
5. **Stage 5 — attribution verification (R-4)** — confirm the conversational fan-out + staging turns
   audit the correct `agent_role` and park `staged_by_role="executor"`; six-emitter parity stays green.
   Depends on Stage 2.
6. **Stage 6 — evidence (R-7, OQ-6)** — scenario tests, the gated `conversational-remediation-livecheck.sh`
   (park + zero dispatch + no auto-approval), and the four-point-gate mapping. Depends on Stages 1–5.
7. **Stage 7 — docs + verify (R-6, R-7)** — reconcile the authorization matrix, configuration reference,
   roadmap (`FU-077-agentic-remediation` + `FU-076-c` closed; R2 recorded as the fast-follow), index, and
   CHANGELOG; `make verify` green. Depends on all.

## Test Strategy

- unit tests: a remediation-intent chat turn composes `run_bounded_diagnosis(...)` +
  `stage_remediation(...)` and parks **one** proposal carrying `staged_by_role="executor"`; a
  non-remediation turn is **byte-identical** (no role bound, no orchestration frame); a diagnosis-only
  profile and an unknown profile fail closed with **no** executor turn; an `AgentChatRequest` with a
  smuggled `agent_role`/unknown field is refused (`extra="forbid"`); `AGENT_ORCHESTRATION_MAX_STEPS`
  still bounds the fan-out and fails closed to a partial diagnosis.
- policy tests: the in-process `agent_roles_any` rule (an `executor` may stage; a
  `diagnostician`/`orchestrator` may not) is enforced at the staging seam with the role never crossing a
  wire field; `make validate-policy` + `validate-policy-scenarios` (both engines) green; the four bundle
  replicas stay byte-identical; the self-approval block + the `executor`→**distinct-human** disjointness
  hold.
- contract tests: `agent-stream-event.schema.json` and `execution-request.schema.json` **byte-unchanged**;
  no `agent_role` on any wire field; a guard test asserts no `TeamPipeline`/`GoalPipeline`/`A2AAgent` is
  constructed on the path.
- attribution tests: the fan-out + staging turns emit audit events carrying the correct `agent_role`; the
  six-emitter parity family + contract-parity tests stay green; no new `event_type` is added.
- scenario / e2e: a **gated live-cluster** check drives one authorized conversational remediation and
  asserts park + **zero** `execution_requested` + **no** HITL auto-approval (mocked leg collected by
  `make test`; live leg an explicit operator step).
- root `make verify` green (incl. `validate-version`, `validate-policy`, `validate-policy-scenarios`, the
  emitter-parity + contract-parity checks, `portal-test`, and the SPEC-063 `execution-failure-test`
  campaign).

## Rollout And Migration

- deployment or configuration changes: **no new knob expected** — the flow reuses
  `AGENT_ORCHESTRATION_MAX_STEPS` and the existing `PLATFORM_GATEWAY_*_TIMEOUT_SECONDS` budgets; if the
  conversational proxy needs its own budget it mirrors the diagnose/remediate knob and is documented in
  `configuration-reference.md`. **No** schema migration (the SPEC-073 roles, SPEC-074 policy axis,
  SPEC-075 audit dimension, and the entire SPEC-020/030/031/037/038/063 mutation path already exist and
  are reused verbatim). `policy-default.yaml` stays **byte-unchanged** unless a canonical role-axis rule
  must ship (OQ-5); `remediate:stage` already exists (SPEC-077) — **no new action**.
- backward compatibility: the remediation-intent flag is **opt-in and defaults off**, so a deployment that
  never sets it behaves exactly as v0.59.0 — the unscoped single-agent chat path is **byte-identical**,
  and `/api/v2/diagnose` + `/api/v2/remediate` are unchanged. The in-process role-axis check is
  complementary to the gateway `evaluate()` and fails closed.
- rollback approach: remove the intent-flag branch + `run_conversational_remediation(...)` + the
  in-process role-axis check. Because the mutation path is entirely reused, rollback returns the platform
  to the v0.59.0 posture (dedicated `/diagnose` + `/remediate` only) with no schema or data effect.
- autonomy safety: the staged proposal **always** parks on HITL for a **distinct human**; nothing
  dispatches without approval and the SPEC-030 self-approval block is unchanged (ADR-0017 Decision-2
  ceiling; ADR-0007 one-gate-per-mutating-flow). Autonomous resolve stays deferred (R3); multi-step plans
  (R2) are a named fast-follow and stay N *individually*-gated proposals (ADR-0011).
