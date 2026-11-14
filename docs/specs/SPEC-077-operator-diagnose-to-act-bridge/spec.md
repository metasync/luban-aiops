# SPEC-077: Operator Diagnose→Act Bridge (Wiring the Delivered `stage_remediation` Behind an Explicit Human Trigger)

## Status

- status: `delivered`
- owner: chi
- created: 2026-11-10
- approved: 2026-11-11 — all nine Open Questions ratified as recommended (`## Open Questions`); per
  the SPEC-066/069/076 pattern the [plan](plan.md) and [tasks](tasks.md) are authored on ratification.
  Approval authorizes implementation to *begin* — **not** to merge, commit/push, deploy, or
  version-bump (each a separate gate).
- delivered: 2026-11-13 as **v0.58.0** — R-1/R-2/R-3/R-5/R-6/R-7 + R-8 implemented as the **UX-agnostic
  operator-initiated diagnose→act bridge** (the `FU-076-b` production trigger): a new agent-service
  `POST /api/v2/remediate` (+ gateway `POST /api/v1/remediate` proxy) gated by a **new** deny-by-default
  `remediate:stage` action (granted `platform-admin`/`operator`), binding `AgentRole.EXECUTOR` for **one**
  `read_only=False` staging turn on the *same* delegated token over `{session_id}::orch::staging`, anchored
  on the **request-carried** completed diagnosis (no fan-out re-run); the executor's toolkit *proposes* the
  single mutating call, which parks as the **existing** SPEC-020/030/031 card with `staged_by_role="executor"`
  for a **distinct human** approver, dispatched only by the signed at-most-one-dispatch worker — **zero new
  mutation-path machinery**, no new wire frame (`agent-stream-event`/`execution-request` byte-unchanged, role
  off the wire), `event_type` enum closed. Only the two stageable profiles (`post-deploy-verify`,
  `k8s-pod-degradation`) stage; the two diagnosis-only profiles + an unknown profile **fail closed** 4xx (R-2).
  Added `PLATFORM_GATEWAY_REMEDIATE_TIMEOUT_SECONDS` (code default `300`s) and carried the v0.57.0 finding
  that the `120`s `PLATFORM_GATEWAY_DIAGNOSE_TIMEOUT_SECONDS` code default is too tight (tracked; the product
  default is unchanged). **R-4 (the portal Stage-remediation button) was DEFERRED post-approval**
  (2026-11-11 operator re-scope) as the named follow-up **`FU-077-agentic-remediation`** (a SPEC-078
  candidate). Released as **v0.58.0** (2026-11-13); a follow-on **v0.58.1** patched the platform-gateway JSON
  proxies to relay an upstream agent-service 4xx (the R-2 fail-closed refusal had been surfacing as a raw
  500). Commit/tag/push remained separate operator gates.
- named follow-up: this spec **is** `FU-076-b`, the operator-initiated diagnose→act bridge that
  [SPEC-076](../SPEC-076-bounded-autonomous-diagnosis/spec.md) (v0.57.0) recorded in its Non-Goals,
  the [delivery roadmap](../../agentic-aiops-platform/delivery-roadmap.md) multi-agent row, and its
  [tasks](../SPEC-076-bounded-autonomous-diagnosis/tasks.md) Delivery Gate as **tracked, not
  dropped**. SPEC-076 delivered the `executor`-scoped `stage_remediation(...)` mechanism
  **unit-proven but unwired** (`run_bounded_diagnosis` never calls it; `POST /api/v2/diagnose` is
  diagnosis-only), so the read-only ceiling held **by construction**. This spec supplies the
  **production trigger** — and only the trigger — that reaches that mechanism.
- release slice: the **multi-agent / bounded-autonomy program** — the first increment *after*
  phase 5 of the phased SPEC series [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md)
  gates ([memo](../../workspace/multi-agent-orchestration-spike.md) §7). Target version
  **v0.58.0** — pinned on approval (2026-11-11); a minor bump over v0.57.0 per the SPEC-070…076 pattern.
- related ADRs: [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md)
  (**Decision 2** the diagnose-before-act autonomy ceiling — this spec is the *act* half, admitted
  only as an operator-initiated, HITL-parked proposal, never autonomous resolve; **Decision 4**
  role-scoped agents on the same delegated token — this spec binds the `executor` role in production);
  [ADR-0007](../../adr/0007-browser-flow-single-hitl-gate.md) (one HITL gate per mutating flow — the
  `executor`→**distinct-human**-approver invariant is the load-bearing control here);
  [ADR-0010](../../adr/0010-signed-execution-envelopes-declare-authority-provenance.md) (provenance
  rides the signed fact — `staged_by_role="executor"`) and
  [ADR-0013](../../adr/0013-durable-single-use-execution-claims.md) (durable single-use dispatch
  claims) — both stay authoritative and **unchanged** on the mutation path. **No new ADR is
  expected**: ADR-0017 Decision 2 already fixed the autonomy ceiling and the `executor`→human-approver
  model; this spec makes the *act* trigger concrete without relaxing any invariant (see OQ-6 on the
  policy-axis boundary and OQ-1 on the trigger shape).
- extends: [SPEC-076](../SPEC-076-bounded-autonomous-diagnosis/spec.md) (the delivered
  `stage_remediation(...)` mechanism + the `DiagnosisProfile.remediation_shape` split this trigger
  wires), [SPEC-073](../SPEC-073-role-scoped-agent-identity/spec.md) (the `executor` role +
  `agent_role_scope()` + `staged_by_role` provenance this binds in production),
  [SPEC-020](../SPEC-020-hitl-confirmation-bridging/spec.md) /
  [SPEC-030](../SPEC-030-require-approval-policy-semantics/spec.md) /
  [SPEC-031](../SPEC-031-approval-inbox-persistent-confirmation/spec.md) (the existing HITL park,
  self-approval block, and persistent approval inbox the staged proposal rides — **zero new
  mutation-path machinery**), [SPEC-037](../SPEC-037-signed-execution-requests/spec.md) /
  [SPEC-038](../SPEC-038-isolated-execution-worker/spec.md) /
  [SPEC-063](../SPEC-063-crash-safe-execution/spec.md) (the signed at-most-one-dispatch worker that
  alone dispatches an approved proposal), [SPEC-075](../SPEC-075-multi-agent-audit-attribution/spec.md)
  (the `agent_role` audit dimension the executor staging turn **populates**), and
  [SPEC-004](../SPEC-004-policy-enforcement/spec.md) (the deny-by-default policy engine that gates the
  new trigger action). Reconciles with [SPEC-074](../SPEC-074-policy-role-axis/spec.md) (the
  `agent_roles_any` axis stays **ready-but-inert** on this path — see OQ-6; making it live is
  `FU-076-c`, not this spec).

## Problem

Phase 5 shipped a bounded read-only diagnosis an operator can invoke
(`POST /api/v2/diagnose`), and it shipped — unit-proven but deliberately unwired — the
`executor`-scoped `stage_remediation(...)` mechanism that turns a diagnosis into a **proposed**
mutating action parked on the existing HITL confirmation card. Today the operator can therefore
*ask the platform to diagnose* a degraded pod or a failed post-deploy verification, read a bounded
synthesis, and then must leave the portal to act on it: there is **no production trigger** that
reaches `stage_remediation`. Two of the four declared runbooks
(`post-deploy-verify` → *"roll the deployment back to the last known-good revision"*;
`k8s-pod-degradation` → *"restart or reschedule the degraded pod, or roll back the offending config
change"*) declare a `remediation_shape` and are meant to be stageable; the mechanism exists and is
proven, but nothing calls it.

The gap is intentional (the diagnose-before-act ceiling, ADR-0017 Decision 2), and closing it is
**mutation-adjacent**, so it deserves its own evidence-backed increment rather than being folded into
the read-only delivery: a distinct portal entry, a distinct deny-by-default policy action, park/resume
UX that reuses the existing confirmation card and approval inbox, and a live-check that proves the
staged proposal **parks and never auto-dispatches**.

## Approach (ratified resolution)

Add an **operator-initiated staging trigger** — a new agent-service `POST /api/v2/remediate` (+ a
gateway `POST /api/v1/remediate` proxy) gated by a **new** deny-by-default action — that calls the
**delivered** `stage_remediation(...)` exactly as unit-proven: it binds `AgentRole.EXECUTOR`, runs
**one** `read_only=False` staging turn over the *same* delegated token, and lets the executor's full
toolkit (SPEC-073 R-2 `_narrow_for_role`) *propose* the single mutating call, which the kernel parks
as the **existing** SPEC-020/030/031 confirmation card labelled `staged_by_role="executor"`. A
**distinct human** approver resumes it through the existing approval inbox; the signed
at-most-one-dispatch worker (SPEC-037/038/063) alone dispatches. **Zero new mutation-path code**: no
new gate, worker, claim type, dispatch path, or wire frame. A diagnosis-only profile
(`remediation_shape is None`) **fails closed** at the trigger (4xx) and never opens an executor turn.

The trigger is **anchored on a completed diagnosis** (OQ-2, ratified **request-carried**): the operator
stages from a diagnosis they have already run and read — the `RemediateRequest` carries the `goal` +
`diagnosis` text the portal already received from `/diagnose` — so the bridge does **not** re-run the
bounded fan-out and adds **no** new persistence. The role stays **process-local** (SPEC-073 R-3 — off
every wire field), so the SPEC-074 policy axis stays **ready-but-inert** on this path (OQ-6) and the
live control remains in-process toolkit narrowing plus the HITL park.

## Requirements

### R-1: The operator-initiated staging trigger (wires `stage_remediation`)

A new agent-service `POST /api/v2/remediate` calls the delivered `stage_remediation(...)` for a
**stageable** profile anchored on the request-carried completed diagnosis (`goal` + `diagnosis`, OQ-2),
and returns through the **existing** `AgentChatResponse` (the parked confirmation surfaces through the
existing SPEC-031 card frame — no new response frame). The gateway exposes `POST /api/v1/remediate` as
a proxy mirroring the `/api/v1/diagnose` proxy shape (delegated token, longer proxy budget — R-7).

- **Acceptance:** a staging request for `post-deploy-verify` / `k8s-pod-degradation` invokes
  `stage_remediation` with `AgentRole.EXECUTOR` bound for exactly one `read_only=False` turn over
  `{session_id}::orch::staging` on the same delegated token; the turn's proposed mutating call is
  **parked** as a confirmation card carrying `staged_by_role="executor"`; the route itself dispatches
  **nothing**.

### R-2: Fail-closed on a diagnosis-only or unknown profile

A staging request for a profile with `remediation_shape is None` (`servicenow-incident`,
`observability-alert`) or an unknown profile name is refused **4xx** and never opens an executor turn
— the trigger must not widen a read-only runbook into a mutation to "finish" it.

- **Acceptance:** `remediate(servicenow-incident)` and `remediate(observability-alert)` return 4xx
  with no `stage_remediation` call and no executor turn (mirrors the delivered `ValueError` fail-closed
  path, surfaced as an HTTP refusal); an unknown profile returns 4xx (never coerced).

### R-3: A new deny-by-default policy action gates the trigger

The staging trigger is gated by a **new** action (`remediate:stage`, ratified; OQ-3) in both gateway
`evaluate()` engines, `PROTECTED_ACTIONS`, all policy-bundle mirrors, and `policy-scenarios.yaml` —
**not** the existing `chat` action, because staging is mutation-adjacent and deserves its own
deny-by-default gate. Granted to `platform-admin` and `operator`; denied to `developer`,
`read-only-observer`, and `auditor`. The `executor`→**distinct-human**-approver disjointness
(SPEC-074) and the SPEC-030 self-approval block are preserved unchanged.

- **Acceptance:** `validate-policy` + `validate-policy-scenarios` (both engines) green with the new
  action; a token without `remediate:stage` is denied (403) at the gateway; the approver of a staged
  proposal can never be the stager (self-approval blocked).

### R-4: Portal entry + park/resume UX (reuses the existing card and inbox)

> **DEFERRED 2026-11-11 (operator re-scope, post-approval).** Implementation grounding found the
> ratified premise false: the operator portal has **no** "completed diagnosis" surface — SPEC-076
> shipped the diagnose flow **backend-only** (the portal was last touched by SPEC-072 / v0.53.0; there
> is no diagnosis card and no `/api/v1/diagnose` client). So there is no card to attach a **Stage
> remediation** button to, and the plan's "cheap because it reuses the card" cost assumption is void.
> The operator's product direction is an **agentic / multi-agent** remediation model — human-requested,
> carried out by an agent team, surfacing through conversation or graduated autonomy rather than a
> discrete button — which supersedes the button-on-a-card UX and would make building it throwaway.
> R-4 is therefore **deferred**, not dropped, and recorded as the named follow-up
> **`FU-077-agentic-remediation`** (a SPEC-078 candidate: conversational/agentic entry, multi-agent
> remediation team, an autonomy gradient, the ADR-0017 Decision-2 revisit, and the `FU-076-c` policy
> axis going live). The backend trigger (R-1/R-2/R-3/R-5/R-6/R-7) is **UX-agnostic** and ships in
> v0.58.0 regardless — it is the prerequisite for any entry shape (button, chat message, or machine
> trigger). The original ratified R-4 text is retained below for the record.

The operator portal gains a **Stage remediation** affordance on a completed diagnosis, visible **only**
for a stageable profile **and** only to a role holding `remediate:stage`. Invoking it calls
`POST /api/v1/remediate`; the resulting parked proposal appears through the **existing** SPEC-031
confirmation card and approval-inbox flow (no new card type, no new resume path).

- **Acceptance:** the affordance is absent for diagnosis-only profiles and for roles without the
  action; a staged proposal is visible to a distinct approver in the existing inbox and resumes
  through the existing signed-dispatch path; portal unit suite (Vitest) + typechecked build green.

### R-5: Audit attribution (the executor turn is attributable)

The staging turn audits with the SPEC-075 `agent_role="executor"` dimension (already populated by the
delivered mechanism) and the parked card carries the SPEC-073 `staged_by_role="executor"` provenance.
The diagnose→act bridge is reconstructable from the durable trail: the read-only diagnosis
(`chat_completed`, role `orchestrator`/`diagnostician`) and the staged proposal (role `executor`) are
both attributable to the same human + delegated token. The `event_type` enum stays **closed** (OQ-5
ratified: no new event type).

- **Acceptance:** an executor staging turn emits an audit event carrying `agent_role="executor"`; the
  six-emitter parity family and contract-parity tests stay green; no new event type is added.

### R-6: Contract boundary — existing frames only, role off the wire

The staged proposal rides **existing** frames (`AgentChatResponse`, the SPEC-031 confirmation card,
`execution-request.schema.json`). `agent-stream-event.schema.json` and `execution-request.schema.json`
stay **byte-unchanged**; no `agent_role` crosses any wire field (SPEC-073 R-3). The **v2 multi-agent
wire contract** stays phase 6, out of scope here.

- **Acceptance:** a byte-freeze assertion on both schemas; the inbound `RemediateRequest` carries no
  `agent_role` and is `extra="forbid"` (a smuggled role is refused 4xx).

### R-7: Proxy timeout budget for the staging turn (carries the v0.57.0 finding)

The gateway `POST /api/v1/remediate` proxy carries a budget adequate for **one executor model turn
against a real remote provider**. This spec **carries the v0.57.0 live-check finding**: the observed
live bounded diagnosis took ~140s, exceeding the `120`s `PLATFORM_GATEWAY_DIAGNOSE_TIMEOUT_SECONDS`
**code default** (the dev overlay now sets `300`s); a single staging turn is shorter than a full fan-out
but is still a real provider call. The remediate proxy budget is set accordingly (ratified: a dedicated
`PLATFORM_GATEWAY_REMEDIATE_TIMEOUT_SECONDS`, **code default `300`s**, OQ-7), and the too-tight `120`s
diagnose **code default** is recorded as a follow-up finding for the operator (raised in dev, not
silently changed in product code by this spec).

- **Acceptance:** the remediate proxy does not `ReadTimeout` on a legitimate live staging turn; the
  configuration reference documents the new knob and its default; the `120`s code-default finding is
  recorded in the delivery roadmap / tasks (tracked, not dropped).

### R-8: Evidence — the four-point gate + a gated live-check + docs

Scenario tests cover all four runbooks at the trigger: the two stageable profiles **park** a proposal
(never dispatch), the two diagnosis-only profiles **fail closed**. A gated live-cluster check
(mirroring `diagnosis-livecheck.sh`) drives one **authorized, billable** staging turn and asserts the
proposal **parks** with **zero** `execution_requested` dispatch and **no** HITL auto-approval; the
mocked-I/O leg is collected by `make test` so the check cannot be skipped silently. The SPEC-018
four-point-gate mapping is recorded. Living docs are reconciled: the authorization matrix (the new
action + the executor→human invariant), the configuration reference (R-7 knob), the delivery roadmap
(FU-076-b closed; the `120`s finding), the spec index (this row → `delivered`), and `CHANGELOG.md`.

- **Acceptance:** scenario tests green for all four profiles; the gated live-check asserts park + zero
  dispatch; `make verify` green across every leg; docs reconciled.

## Non-Goals

- **Autonomous resolve / auto-dispatch.** The staged proposal **always** parks on HITL for a distinct
  human; nothing here dispatches without approval, and the SPEC-030 self-approval block is unchanged.
  Autonomous resolve stays deferred (ADR-0017 Decision 2 ceiling).
- **Unattended machine-trigger ingestion** (webhook/alert auto-fire, dedup, storm control) — that is
  `FU-076`, a separate future spec; this trigger is **operator-initiated** only.
- **Making the SPEC-074 policy axis live** (threading a non-`None` `agent_role` into a deployed gateway
  `evaluate()`) — that is `FU-076-c`. On this path the role stays off the wire (SPEC-073 R-3), so the
  axis stays ready-but-inert and the live control is in-process toolkit narrowing + the HITL park (OQ-6).
- **The phase-6 v2 multi-agent wire contract.** Existing frames only (R-6).
- **New mutation-path machinery** — no new gate, worker, claim type, dispatch path, or schema
  (the delivered mechanism + the existing SPEC-020/030/031/037/038/063 path are reused verbatim).
- **New runbooks or widening `remediation_shape`.** The two stageable profiles ship as declared;
  diagnosis-only profiles stay diagnosis-only.
- **Re-running the diagnosis on staging** (OQ-2 ratified anchoring on the request-carried completed
  diagnosis, not a fresh fan-out).
- **A portal Stage-remediation affordance (R-4) and the agentic / multi-agent remediation model.**
  R-4 is **deferred** (2026-11-11 operator re-scope): the portal has no completed-diagnosis surface
  (SPEC-076 shipped backend-only), and the operator's direction is an agentic/multi-agent remediation
  — human-requested, agent-team-carried, surfacing through conversation or graduated autonomy rather
  than a button on a card. Captured as the named follow-up **`FU-077-agentic-remediation`** (a SPEC-078
  candidate, joining `FU-076` and `FU-076-c`); v0.58.0 ships the **UX-agnostic backend trigger** only.

## Open Questions

> **Ratified 2026-11-11** — all nine resolved as recommended (each `**Ratified:**` below is binding);
> `status` is now `approved` and the [plan](plan.md)/[tasks](tasks.md) are authored. Recommendations
> followed the SPEC-066/069/076 pattern.

- **OQ-1 — Trigger shape.** A dedicated `POST /api/v2/remediate` endpoint (+ gateway proxy), **or** an
  `act`/`stage` flag on the existing `/diagnose`, **or** a chat-driven tool? **Ratified: a dedicated
  endpoint** — it cleanly separates the read-only diagnosis from the mutation-adjacent staging, carries
  its own policy action (R-3) and its own proxy budget (R-7), and keeps `/diagnose` diagnosis-only (so
  the phase-5 read-only ceiling statement stays literally true).
- **OQ-2 — How the staging turn obtains the diagnosis.** Re-run the bounded fan-out, **or** anchor on the
  already-completed diagnosis (persisted on the session / passed in the request)? **Ratified: anchor
  on the completed diagnosis** — the operator stages from a diagnosis they have run and read; re-running
  is a second billable fan-out and could diverge from what the operator approved. **Ratified resolution:
  request-carried** — the `RemediateRequest` carries the `goal` + `diagnosis` text the portal already
  received from `/diagnose` (`extra="forbid"`, fail-closed 4xx if absent/empty); zero new persistence,
  and the distinct-human HITL approval of the concrete proposed call is the integrity backstop (the
  staged-from diagnosis rides the executor turn's audit record).
- **OQ-3 — Policy action name + grant set.** New `remediate:stage` (or `diagnose:act`), granted to
  `platform-admin` + `operator`, denied to `developer`/`read-only-observer`/`auditor`? **Ratified: a
  new `remediate:stage` action** with that grant set — staging is mutation-adjacent and must not ride the
  broad `chat` action.
- **OQ-4 — Portal entry placement + visibility.** A **Stage remediation** button on the completed
  diagnosis card, visible only for a stageable profile + a role holding the action? **Ratified: yes**,
  reusing the existing SPEC-031 card + inbox for park/resume (no new UX surface).
  **Superseded 2026-11-11 (post-approval operator re-scope):** the ratified premise — a pre-existing
  completed-diagnosis card — is false (the portal has no diagnosis surface; SPEC-076 was backend-only),
  and the operator's agentic/multi-agent direction supersedes the button-on-a-card UX. R-4 is
  **deferred** as `FU-077-agentic-remediation` (a SPEC-078 candidate); see the R-4 deferral note and
  Non-Goals. The backend trigger ships UX-agnostic in v0.58.0.
- **OQ-5 — Audit event type.** Does the bridge need a new `event_type`, or is the executor staging turn
  fully attributable on existing events (SPEC-075 `agent_role` dimension + the parked-card provenance)?
  **Ratified: no new event type** — the `agent_role="executor"` dimension plus the existing
  `chat_completed`/execution-request events make the bridge reconstructable; the enum stays closed.
- **OQ-6 — Does the SPEC-074 policy axis go live on this path?** The executor role is bound in-process
  during staging, but SPEC-073 R-3 keeps it off the wire, so a deployed gateway `evaluate()` still sees
  `None`. **Ratified: the axis stays ready-but-inert here** (making it live in-process is `FU-076-c`);
  the live control on this path is in-process toolkit narrowing (the executor gets the full toolkit,
  `read_only=False`) **plus** the HITL park + distinct-human approval — which is the actual ceiling.
- **OQ-7 — The remediate proxy budget + the carried `120`s finding.** A dedicated
  `PLATFORM_GATEWAY_REMEDIATE_TIMEOUT_SECONDS` (proposed default mirroring the raised diagnose value),
  and separately record the too-tight `120`s **diagnose code default** as a follow-up finding?
  **Ratified: yes to both** — set the dedicated `PLATFORM_GATEWAY_REMEDIATE_TIMEOUT_SECONDS` code default
  to `300`s (mirroring the raised dev diagnose value), and log the `120`s code-default finding for a
  future product decision (this spec raises the dev overlay, not the product default).
- **OQ-8 — Runbook scope.** Only the two stageable profiles (`post-deploy-verify`,
  `k8s-pod-degradation`); the two diagnosis-only profiles fail closed (R-2)? **Ratified: yes.**
- **OQ-9 — Evidence depth.** A gated billable live-check that stages one proposal and asserts park +
  zero dispatch + no auto-approval, mirroring `diagnosis-livecheck.sh`, plus scenario tests for all four
  profiles and the four-point-gate mapping? **Ratified: yes** (the mocked leg collected by
  `make test`; the live leg an explicit operator step).

## Carried findings (from v0.57.0 delivery)

- **The `120`s `PLATFORM_GATEWAY_DIAGNOSE_TIMEOUT_SECONDS` code default is too tight for a real slow
  provider.** Observed live: agent-service completed a bounded read-only diagnosis with **HTTP 200 in
  ~140s** while the gateway proxy `ReadTimeout`'d at `120`s and returned 500. The dev overlay now sets
  `300`s (commit `a7b3ba6a`); the **code default** is unchanged and recorded here (and in R-7/OQ-7) as a
  follow-up for a future product decision, since the correct default needs real provider-latency data.

## Changelog

- 2026-11-10 — drafted as `FU-076-b` (SPEC-077) with nine Open Questions; not yet approved.
- 2026-11-11 — all nine Open Questions ratified as recommended (OQ-2 → request-carried anchor;
  OQ-7 → `PLATFORM_GATEWAY_REMEDIATE_TIMEOUT_SECONDS` code default `300`s + the `120`s diagnose
  code-default finding logged); `status: draft → approved`; target **v0.58.0** pinned; `plan.md` +
  `tasks.md` authored.
- 2026-11-11 (post-approval re-scope) — **R-4 deferred** by the operator. Implementation grounding
  found the portal has no completed-diagnosis surface (SPEC-076 shipped the diagnose flow
  backend-only; the portal was last touched by SPEC-072 / v0.53.0), so the ratified "button on the
  diagnosis card" premise is void; the operator's direction is an **agentic / multi-agent**
  remediation model (human-requested, agent-team-carried, conversational or graduated-autonomy)
  rather than a discrete button. R-4 + the agentic model are recorded as the named follow-up
  **`FU-077-agentic-remediation`** (a SPEC-078 candidate). v0.58.0 ships the **UX-agnostic backend
  trigger** (R-1/R-2/R-3/R-5/R-6/R-7) + evidence (R-8); the portal affordance is deferred, not
  dropped. OQ-4 annotated **superseded**; Non-Goals + `plan.md`/`tasks.md` updated additively.
- 2026-11-13 — **delivered as v0.58.0** — R-1/R-2/R-3/R-5/R-6/R-7 + R-8 implemented and verified (R-4
  deferred as `FU-077-agentic-remediation`). The operator-initiated diagnose→act bridge wired the
  delivered-but-unwired `executor` `stage_remediation(...)` behind a new agent-service
  `POST /api/v2/remediate` + gateway `POST /api/v1/remediate` proxy, gated by a **new** deny-by-default
  `remediate:stage` action (granted `platform-admin`/`operator`, denied `developer`/`read-only-observer`/
  `auditor`, synced byte-identically across all four policy replicas + `PROTECTED_ACTIONS` + both gateway
  `evaluate()` engines). One `read_only=False` executor staging turn rides the *same* delegated token over
  `{session_id}::orch::staging`, anchored on the request-carried completed diagnosis (no fan-out re-run),
  parking the proposed mutating call as the existing SPEC-020/030/031 card with `staged_by_role="executor"`
  for a **distinct human** (SPEC-030 self-approval block unchanged), dispatched only by the signed
  at-most-one-dispatch worker. The two stageable profiles park; the two diagnosis-only profiles + an unknown
  profile fail closed 4xx. `agent_role="executor"` audited with **no new** `event_type` (enum closed; the
  gateway reuses `chat_completed`); role off the wire, `agent-stream-event`/`execution-request`
  byte-unchanged (SPEC-074 axis stays ready-but-inert, `FU-076-c` unchanged). Added
  `PLATFORM_GATEWAY_REMEDIATE_TIMEOUT_SECONDS` (code default `300`s) and logged the too-tight `120`s
  `PLATFORM_GATEWAY_DIAGNOSE_TIMEOUT_SECONDS` code-default finding (dev overlay `300`s via `a7b3ba6a`; the
  product default is unchanged). Evidence: the four-profile trigger scenario tests, the gated
  `remediation-livecheck.sh` (the billable leg drives one authorized staging turn and asserts park + **zero**
  `execution_requested` + no HITL auto-approval; the mocked leg is collected by `make test`), and the recorded
  SPEC-018 four-point-gate mapping (full agent-platform suite **1793**, platform-gateway **510**, root
  `make verify` green across every leg). Released as **v0.58.0** (2026-11-13); commit/tag/push remained
  separate operator gates.
- 2026-11-14 — **v0.58.1** follow-on patch (not a SPEC-077 scope change): the platform-gateway JSON proxies
  (`chat`/`diagnose`/`remediate`) now **relay** an upstream agent-service 4xx (e.g. the R-2 fail-closed 422)
  as-is with its extracted `detail` instead of letting an unhandled `httpx.HTTPStatusError` surface a raw
  **500**; 5xx/transport errors map to a structured **502**. This makes the R-2 diagnosis-only refusal
  observable end-to-end through the gateway (previously masked as a 500). Released as **v0.58.1**.
