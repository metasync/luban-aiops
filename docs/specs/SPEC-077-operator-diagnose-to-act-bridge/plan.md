# SPEC-077 Plan: Operator Diagnose→Act Bridge (Wiring the Delivered `stage_remediation` Behind an Explicit Human Trigger)

> **BINDING** — approved 2026-11-11. The operator ratified all nine Open Questions in
> [`spec.md`](spec.md) **exactly as recommended**, so the design below (which assumed each OQ's
> recommended resolution) is now binding and the provisional banner is lifted (the SPEC-066/069/076
> pattern). Design points contingent on an OQ remain tagged `(OQ-n)`. Approval authorizes
> implementation to *begin* — **not** to merge, commit/push, deploy, or version-bump (separate gates).
> This increment supplies **only the production trigger** that reaches the delivered-but-unwired
> `stage_remediation(...)`; **zero new mutation-path machinery** is added. Two sibling follow-ups stay
> deferred and are **not** pulled in here: **`FU-076`** (unattended machine-trigger ingestion) and
> **`FU-076-c`** (making the SPEC-074 policy axis live where R-3 keeps the role off the wire — OQ-6).

## Approach

SPEC-077 is a **thin trigger** over an already-delivered, already-unit-proven mechanism. Phase 5
(v0.57.0) shipped `stage_remediation(...)` — it binds `AgentRole.EXECUTOR`, runs **one**
`read_only=False` turn on `{session_id}::orch::staging`, and lets the executor's full toolkit *propose*
the single mutating call, which the kernel parks on the **existing** SPEC-020/030/031 confirmation card
with `staged_by_role="executor"`. Nothing calls it in production. This spec adds the caller and nothing
else on the mutation path:

- a new agent-service `POST /api/v2/remediate` that mirrors the delivered `/api/v2/diagnose` handler
  shape and calls `stage_remediation(...)` for a **stageable** profile, anchored on the
  **request-carried** completed diagnosis (OQ-2) — no re-run of the bounded fan-out, no new persistence;
- a gateway `POST /api/v1/remediate` proxy mirroring `/api/v1/diagnose`, gated by a **new**
  deny-by-default `remediate:stage` action (OQ-3) and carrying its own proxy budget (OQ-7);
- a portal **Stage remediation** affordance on the completed diagnosis card, visible only for a
  stageable profile **and** a role holding the action (OQ-4), reusing the existing card + approval
  inbox for park/resume — no new UX surface;
- everything surfaces through **existing** frames (`AgentChatResponse`, the SPEC-031 card,
  `execution-request.schema.json`), so both stream/execution schemas stay **byte-unchanged** and no
  `agent_role` crosses a wire field (SPEC-073 R-3 — OQ-6 keeps the SPEC-074 axis ready-but-inert).

A diagnosis-only profile (`remediation_shape is None`) or an unknown profile **fails closed** (4xx) at
the trigger and never opens an executor turn (R-2). The staged proposal **always** parks for a
**distinct human** approver; the signed at-most-one-dispatch worker (SPEC-037/038/063) alone dispatches,
and the SPEC-030 self-approval block fires unchanged. The work groups into eight stages mirroring
R-1…R-8.

## Design Per Requirement

### R-1: The operator-initiated staging trigger (OQ-1, OQ-2)

- affected files: `products/agent-platform/src/agent_service/api/v2/routes.py` (a new `remediate`
  handler mirroring `diagnose`), `products/agent-platform/src/agent_service/schemas/v2.py` (a new
  `RemediateRequest`), `products/agent-platform/src/agent_service/services/orchestration.py` (calls the
  **delivered** `stage_remediation(...)` — unchanged), and the platform-gateway proxy
  (`products/platform-gateway/src/platform_gateway/api/.../diagnose` route + `agent_client`).
- chosen approach: `POST /api/v2/remediate` validates the requester/session exactly as `/diagnose`
  does (`_verified_requester`, `ensure_session`, `_reject_if_parked`, `_resolve_model`), resolves the
  profile via `get_profile(body.profile)`, and calls `stage_remediation(kernel, profile=..., goal=...,
  diagnosis=..., session_id=..., user_name=..., bearer_token=..., model_id=...)`. The `goal` + `diagnosis`
  come **from the request** (OQ-2 request-carried): the portal passes back the synthesis it already
  received from `/diagnose`. The handler returns the reply through the **existing** `AgentChatResponse`;
  the parked confirmation rides the existing SPEC-031 card frame. `stage_remediation` binds `EXECUTOR`
  internally — the route binds no role and the body carries none (R-6).
- alternatives rejected: an `act`/`stage` flag on `/diagnose` (OQ-1 — blurs the read-only ceiling); a
  chat-driven tool (hardest to gate behind a dedicated deny-by-default action + deterministic park);
  re-running the bounded fan-out at staging time (OQ-2 — a second billable fan-out that could diverge
  from what the operator read and approved).

### R-2: Fail-closed on a diagnosis-only or unknown profile

- affected files: the `remediate` handler in `routes.py`; the HTTP mapping of `stage_remediation`'s
  delivered `ValueError` (`remediation_shape is None`) to a 4xx refusal.
- chosen approach: an unknown profile is refused **422** (mirroring `/diagnose`'s existing
  `unknown diagnosis profile` guard) *before* any executor turn; a profile whose `remediation_shape is
  None` (`servicenow-incident`, `observability-alert`) is refused **4xx** by pre-checking
  `profile.remediation_shape` in the handler (and/or mapping the delivered `ValueError`), so **no**
  executor turn is opened. The trigger must never widen a read-only runbook into a mutation.
- alternatives rejected: coercing an unknown/diagnosis-only profile to a wider runbook; opening the
  executor turn and letting it fail mid-turn (wastes a model call and risks a partial proposal).

### R-3: A new deny-by-default policy action gates the trigger (OQ-3)

- affected files: `shared/shared-contracts/policies/policy-default.yaml` (canonical) **+ its three
  byte-identical replicas** (`products/tool-gateway/.../policies/policy-default.yaml`,
  `products/platform-gateway/.../policies/policy-default.yaml`,
  `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`) synced via `make sync-policy`;
  `policy-scenarios.yaml`; the `PROTECTED_ACTIONS` set + the action vocabulary in **both** gateway
  `evaluate()` engines.
- chosen approach: add a **new** action `remediate:stage`, deny-by-default, granted to `platform-admin`
  + `operator`, denied to `developer`, `read-only-observer`, and `auditor`. The gateway
  `POST /api/v1/remediate` proxy evaluates it (a token without it is denied **403**). The
  `executor`→**distinct-human**-approver disjointness (SPEC-074) and the SPEC-030 self-approval block
  are preserved unchanged. `make validate-policy` + `validate-policy-scenarios` (both engines) must stay
  green with the new action, and the four bundle replicas stay byte-identical.
- alternatives rejected: reusing the broad `chat` action (staging is mutation-adjacent and deserves its
  own deny-by-default gate); naming it `diagnose:act` (OQ-3 — "act" overstates a trigger that only
  stages/parks and never dispatches).

### R-4: Portal entry + park/resume UX (OQ-4)

> **DEFERRED 2026-11-11 (operator re-scope, post-approval).** The "affected files" premise below is
> false: the operator portal has **no** diagnosis card component and no `/api/v1/diagnose` client —
> SPEC-076 shipped the diagnose flow **backend-only** (the portal was last touched by SPEC-072 /
> v0.53.0). The operator's direction is an **agentic / multi-agent** remediation (conversational or
> graduated-autonomy, not a button on a card), so building this UX would be throwaway. R-4 is deferred
> as **`FU-077-agentic-remediation`** (a SPEC-078 candidate); Stage 6 is **cancelled** for v0.58.0.
> The backend trigger (Stages 1–5) is UX-agnostic and ships regardless. Original text retained below.

- affected files: the operator-portal diagnosis card component (the completed-diagnosis view), its API
  client (a `POST /api/v1/remediate` call), and the permission/role gating used to decide visibility
  (the same capability check the portal already applies to gated affordances).
- chosen approach: a **Stage remediation** button on the completed diagnosis card, rendered **only**
  when the profile is stageable (`post-deploy-verify` / `k8s-pod-degradation`) **and** the signed-in
  role holds `remediate:stage`. Clicking it passes the diagnosis's `goal` + `diagnosis` text (already in
  the portal from the `/diagnose` response) to `POST /api/v1/remediate`. The resulting parked proposal
  appears through the **existing** SPEC-031 confirmation card + approval-inbox flow — no new card type,
  no new resume path. Portal unit suite (Vitest) + typechecked production build must stay green.
- alternatives rejected: a separate Remediate view/page (a new UX surface duplicating the card/inbox
  flow); shipping API-only with no portal entry (OQ-4 — R-4 wants the operator-facing affordance, and it
  is cheap because it reuses the card).

### R-5: Audit attribution (OQ-5)

- affected files: **none new** — the delivered `stage_remediation(...)` already audits the executor turn
  with the SPEC-075 `agent_role="executor"` dimension and parks the card with the SPEC-073
  `staged_by_role="executor"` provenance. This stage only **verifies** it end-to-end on the wired path.
- chosen approach: the executor staging turn emits an audit event carrying `agent_role="executor"`; the
  read-only diagnosis (`chat_completed`, role `orchestrator`/`diagnostician`) and the staged proposal
  (role `executor`) are both attributable to the same human + delegated token, so the diagnose→act bridge
  is reconstructable from the durable trail. The `event_type` enum stays **closed** (OQ-5); the
  six-emitter parity family + contract-parity tests stay green.
- alternatives rejected: adding a new `remediation_staged` event type (OQ-5 — widens the closed enum
  across all six emitters and duplicates what `agent_role="executor"` already conveys).

### R-6: Contract boundary — existing frames only, role off the wire

- affected files: `schemas/v2.py` (the new `RemediateRequest` is `extra="forbid"` and carries **no**
  `agent_role`), and the contract-parity tests that byte-freeze `agent-stream-event.schema.json` +
  `execution-request.schema.json`.
- chosen approach: the staged proposal rides **existing** frames (`AgentChatResponse`, the SPEC-031
  confirmation card, `execution-request.schema.json`). Both stream/execution schemas stay
  **byte-unchanged**; no `agent_role` crosses any wire field (SPEC-073 R-3). The inbound
  `RemediateRequest` mirrors the delivered `AgentDiagnoseRequest` posture: `model_config =
  ConfigDict(extra="forbid")`, so a smuggled role or misspelt key is refused **4xx**. The phase-6 v2
  multi-agent wire contract stays out of scope.
- alternatives rejected: adding an `agent_role` request/response field (SPEC-073 R-3 forbids it; the
  contract framing is phase 6); a new `RemediateResponse` frame (the parked card already surfaces
  through the existing `AgentChatResponse` + SPEC-031 frame).

### R-7: Proxy timeout budget for the staging turn (carries the v0.57.0 finding) (OQ-7)

- affected files: `products/platform-gateway/src/platform_gateway/core/config.py` (a new
  `PLATFORM_GATEWAY_REMEDIATE_TIMEOUT_SECONDS`, mirroring the existing
  `PLATFORM_GATEWAY_DIAGNOSE_TIMEOUT_SECONDS`), the gateway's agent client (the `remediate` proxy call
  uses the new budget), `docs/agentic-aiops-platform/configuration-reference.md` (document the knob +
  default), and — optionally — the dev-k8s overlay fragment for platform-gateway env.
- chosen approach: the gateway `POST /api/v1/remediate` proxy carries a dedicated budget with **code
  default `300`s** (OQ-7), ample for one real executor model turn against a remote provider. Separately,
  the too-tight **`120`s `PLATFORM_GATEWAY_DIAGNOSE_TIMEOUT_SECONDS` code default** is recorded as a
  tracked follow-up finding (the dev overlay already sets `300`s via commit `a7b3ba6a`; the **product**
  default is left unchanged pending real provider-latency data — this spec does not silently change it).
- alternatives rejected: reusing the diagnose timeout knob (couples two different workloads' budgets);
  silently raising the `120`s product default (the correct value needs latency data — logged instead).

### R-8: Evidence — the four-point gate + a gated live-check + docs (OQ-8, OQ-9)

- affected files: scenario tests covering all four profiles at the trigger; a new
  `e2e/remediation-livecheck.sh` (mirroring `e2e/diagnosis-livecheck.sh`) + a `make remediation-livecheck`
  target; the four-point-gate mapping note; and the living docs (`authorization-matrix.md`,
  `configuration-reference.md`, the `delivery-roadmap.md` multi-agent row, `docs/specs/README.md` index,
  `CHANGELOG.md`).
- chosen approach: scenario tests assert the two stageable profiles **park** a proposal (never dispatch)
  and the two diagnosis-only profiles **fail closed** (OQ-8). A gated **live-cluster** check drives one
  authorized, billable staging turn and asserts the proposal **parks** with **zero** `execution_requested`
  dispatch and **no** HITL auto-approval; the mocked-I/O leg is collected by `make test` so it cannot be
  skipped silently, and the live leg is an explicit operator step (OQ-9). The SPEC-018 four-point-gate
  mapping is recorded. Living docs are reconciled and `make verify` is green across every leg.
- alternatives rejected: unit tests alone (cannot prove the park + zero-dispatch end-to-end on a live
  cluster); an ungated always-live check (would incur cost on every `make test`).

## Sequencing And Dependencies

1. **Stage 1 — contract + fail-closed guard (R-2, R-6)** — the `RemediateRequest` (`extra="forbid"`, no
   `agent_role`) and the profile validation (unknown → 422; `remediation_shape is None` → 4xx). Depends
   on nothing new; the safe foundation.
2. **Stage 2 — the agent trigger (R-1)** — the `POST /api/v2/remediate` handler wiring the delivered
   `stage_remediation(...)` on the request-carried diagnosis. Depends on Stage 1.
3. **Stage 3 — the policy action (R-3)** — `remediate:stage` in the canonical bundle + three replicas +
   `policy-scenarios.yaml` + `PROTECTED_ACTIONS` + both engines. Independent of Stages 1–2 but required
   before the gateway proxy admits a caller.
4. **Stage 4 — the gateway proxy + budget (R-1, R-7)** — `POST /api/v1/remediate` mirroring
   `/api/v1/diagnose`, gated by `remediate:stage`, with `PLATFORM_GATEWAY_REMEDIATE_TIMEOUT_SECONDS`
   (default `300`). Depends on Stages 2–3.
5. **Stage 5 — attribution verification (R-5)** — confirm the wired executor turn audits
   `agent_role="executor"` and parks `staged_by_role="executor"`; six-emitter parity stays green. Depends
   on Stage 2.
6. **Stage 6 — portal entry (R-4)** — **CANCELLED for v0.58.0** (R-4 deferred 2026-11-11, operator
   re-scope): the portal has no completed-diagnosis surface to attach a button to (SPEC-076 was
   backend-only) and the agentic/multi-agent direction supersedes the button UX. Tracked as
   `FU-077-agentic-remediation` (SPEC-078 candidate). ~~the **Stage remediation** button + profile/role
   visibility gating + the `POST /api/v1/remediate` client call, reusing the existing card/inbox.~~
7. **Stage 7 — evidence (R-8, OQ-8/OQ-9)** — scenario tests for all four profiles, the gated
   `remediation-livecheck.sh` (park + zero dispatch + no auto-approval), the four-point-gate mapping.
   Depends on Stages 1–5 (Stage 6 cancelled).
8. **Stage 8 — docs + verify (R-8)** — reconcile the authorization matrix, configuration reference,
   roadmap, index, and CHANGELOG; `make verify` green. Depends on all.

## Test Strategy

- unit tests: `remediate(post-deploy-verify)` / `remediate(k8s-pod-degradation)` invoke
  `stage_remediation` with `EXECUTOR` bound for exactly one `read_only=False` turn on
  `{session_id}::orch::staging`; the proposal **parks** (never dispatches); `remediate(servicenow-incident)`
  / `remediate(observability-alert)` and an unknown profile return 4xx with **no** executor turn; a
  `RemediateRequest` with a smuggled `agent_role`/unknown field is refused (`extra="forbid"`).
- policy tests: `remediate:stage` is deny-by-default; `platform-admin` + `operator` are granted,
  `developer`/`read-only-observer`/`auditor` denied (403 at the gateway); the four bundle replicas stay
  byte-identical; the self-approval block still fires (the stager can never be the approver);
  `make validate-policy` / `validate-policy-scenarios` (both engines) green.
- contract tests: `agent-stream-event.schema.json` and `execution-request.schema.json` **byte-unchanged**;
  no `agent_role` on any wire field.
- attribution tests: the executor staging turn emits an audit event carrying `agent_role="executor"`; the
  six-emitter parity family + contract-parity tests stay green; no new event type is added.
- portal tests (Vitest): **N/A for v0.58.0** — R-4/Stage 6 deferred (2026-11-11 operator re-scope;
  `FU-077-agentic-remediation`). ~~the **Stage remediation** button is present only for a stageable
  profile **and** a role holding `remediate:stage`, absent otherwise; typechecked production build
  green.~~ The portal is untouched by this increment, so its existing suite + build stay green as-is.
- scenario / e2e: all four profiles covered at the trigger; a **gated live-cluster** check stages one
  proposal and asserts park + **zero** `execution_requested` + **no** HITL auto-approval (mocked leg
  collected by `make test`; live leg an explicit operator step).
- root `make verify` green (incl. `validate-version`, `validate-policy`, `validate-policy-scenarios`, the
  emitter-parity + contract-parity checks, and the SPEC-063 `execution-failure-test` campaign).

## Rollout And Migration

- deployment or configuration changes: one new knob `PLATFORM_GATEWAY_REMEDIATE_TIMEOUT_SECONDS` (code
  default `300`s); one new policy action `remediate:stage` in `policy-default.yaml` + its three replicas
  (synced via `make sync-policy`, bundle-hash re-provenanced) + `policy-scenarios.yaml` + `PROTECTED_ACTIONS`.
  **No** schema migration (the SPEC-074 policy axis, SPEC-075 audit dimension, and the entire
  SPEC-020/030/031/037/038/063 mutation path already exist and are reused verbatim).
- backward compatibility: `remediate:stage` is **deny-by-default**, so a deployment whose bundle has not
  been updated refuses staging (fail-closed) rather than admitting it; `/api/v2/diagnose` and the unscoped
  single-agent chat/triage/documents/skills paths are **unchanged** and byte-identical. A deployment that
  never calls `/remediate` behaves exactly as v0.57.0.
- rollback approach: revert the `remediate` route + gateway proxy + the `remediate:stage` action (there
  is **no** portal button to revert in v0.58.0 — R-4/Stage 6 deferred). Because the mutation path is
  entirely reused and `stage_remediation(...)` returns to unwired, rollback removes only the trigger and
  returns the platform to the v0.57.0 diagnosis-only posture with no schema or data effect.
- autonomy safety: the staged proposal **always** parks on HITL for a **distinct human**; nothing
  dispatches without approval and the SPEC-030 self-approval block is unchanged (ADR-0017 Decision 2
  ceiling; ADR-0007 one-gate-per-mutating-flow). Autonomous resolve stays deferred.
