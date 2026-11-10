# SPEC-076 Tasks: Bounded Autonomous Diagnosis (The Read-Only Orchestration Loop That First Binds Agent-Roles)

> **BINDING** — approved 2026-11-06. The operator ratified all seven Open Questions in
> [`spec.md`](spec.md) **exactly as recommended**, so the tasks below are now **binding** and the
> provisional banner is lifted (the SPEC-066/069 pattern). Task states: `[ ]` pending, `[x]` done.
> Keep tasks small and tied to requirement IDs. Phase 5 is the **first phase with live runtime
> behavior** — it binds the roles SPEC-073/074/075 landed inert, so its acceptance includes an actual
> bounded read-only orchestration run (OQ-6), while the deployed **unscoped** single-agent path stays
> byte-identical. OQ-3's deferral is the named follow-up **`FU-076`** (unattended machine-trigger
> ingestion), tracked in the Delivery Gate below so it is not skipped.

## R-1: A bounded read-only orchestration loop (OQ-1, OQ-2)

- [x] Add a platform-owned orchestration module (`services/orchestration.py`) that drives a bounded
      fan-out of read-only member turns over the existing `reply_text(..., read_only=True)` seam —
      **no** agentscope `TeamPipeline`/`GoalPipeline`/`A2AAgent` type constructed (ADR-0017 Decision 5)
- [x] Add the `AGENT_ORCHESTRATION_MAX_STEPS` knob (`runtime_settings.py`), a deliberate twin of
      `GATEWAY_BROWSER_FLOW_MAX_STEPS` (default `20`, validated `>= 1`), bounding **total member read
      steps per orchestration** (OQ-2)
- [x] Fail closed on budget exhaustion: stop and synthesize a **budget-limited partial diagnosis**;
      never widen to a mutating step to "finish"
- [x] The orchestrator consumes only member **summaries** (memo §3.1); member intermediate steps stay
      out of the leader's context but reconstructable via R-6
- [x] Tests: the loop terminates at the budget and marks the result budget-limited; a mutating member
      step is refused inside the loop; a guard asserts no agentscope orchestration type is constructed

## R-2: Role binding via the orchestration frame (OQ-1)

- [x] Bind `AGENT_ROLE` per participant via SPEC-073's `agent_role_scope()`: `orchestrator` for the
      synthesizer (empty gateway toolkit — it delegates), `diagnostician` for each read member,
      `executor` for a staging step
- [x] Keep the role **process-local** (not in the SPEC-017 snapshot); a park/resume re-derives it per
      turn from the orchestration frame (SPEC-073 OQ-2)
- [x] Update the **in-process** SPEC-073 R-5 guard (`test_only_the_orchestration_frame_binds_a_role`)
      and the SPEC-075 R-5 audit-attribution guard from "no caller binds a role" to "**only the
      orchestration frame binds a role**"; the **gateway** SPEC-074 R-5 guard
      (`test_no_deployed_caller_threads_a_non_none_agent_role`) is **unchanged** and still passes with
      zero offenders (R-3 keeps the role off the wire)
- [x] Tests: `current_agent_role()` is correct per participant and `None` on the unscoped path; the
      unscoped single-agent turn (`/api/v2/chat`, `/chat/stream`) is **byte-identical** (no-diff)

## R-3: Same-token identity preservation across the fan-out

- [x] The orchestrator passes its **own** delegated `bearer_token` to every member; no member mints or
      requests a second broker token; preserve `REQUESTER_IDENTITY`/`DECIDER_IDENTITY` across each hop
- [x] Keep the role off every wire surface — no JWT claim, no forwarded header, no
      `agent-stream-event`/`execution-request` field (SPEC-073 R-3)
- [x] Tests: **exactly one** broker exchange per user across a multi-member fan-out (fail if invoked
      twice); the requester `VerifiedHuman` is unchanged before/within/after the fan-out

## R-4: Diagnose-before-act — mutations park on HITL + signed dispatch

- [x] The read-only loop never dispatches a mutation; a proposed remediation is *staged* by an
      `executor` onto the **existing** HITL confirmation card (SPEC-020/030/031) carrying the SPEC-073
      R-4 `staged_by_role` provenance
- [x] Reuse the signed at-most-one-dispatch worker (SPEC-037/038/063) with a **distinct human**
      approver; the SPEC-030 self-approval block fires unchanged; **zero new mutation-path code**
      (no new gate, worker, claim type, or schema); autonomous resolve stays **deferred** (Decision 2)
- [x] Tests: a `diagnostician`/`orchestrator` cannot stage a mutation at all; a proposed remediation
      parks as a card with `staged_by_role`; no signed dispatch occurs without an approval event;
      `execution-request.schema.json` byte-unchanged

> **Delivered scope (v0.57.0).** The `executor`-scoped `stage_remediation(...)` **mechanism** is
> delivered + unit-proven; it is **not wired to a production trigger** (`run_bounded_diagnosis` never
> calls it, `POST /api/v2/diagnose` is diagnosis-only), so the R-4 ceiling holds **by construction**.
> The operator-initiated diagnose→act bridge is the named follow-up **`FU-076-b`** (Delivery Gate +
> spec Non-Goals + roadmap), not dropped scope.

## R-5: Live policy enforcement + the canonical agent-role rule (OQ-4)

- [x] Add the `agent_role` axis to **both** gateway `evaluate()` engines (the SPEC-074 input already
      exists) and prove its semantics by unit test; keep the axis **subtractive-only** and
      **fail-closed**. It lands **ready-but-inert** in deployment — R-3 keeps the bound role off every
      wire field, so no deployed caller threads a non-`None` role (see the resolution note below)
- [x] Land the **minimal** canonical `policy-default.yaml` `agent_roles_any` rule(s) the four runbooks
      need (a `diagnostician` read posture, an `executor`→`require_approval` encoding), synced across
      all four replicas (`make sync-policy`); **defer the tool-name/family axis** unless a runbook
      demonstrably needs same-tool-different-role divergence (OQ-4)
- [x] Tests: an `evaluate()` call that threads a role denies a `diagnostician` a mutating grant
      (engine semantics, unit-proven); an unscoped call stays byte-identical to the pre-axis baseline;
      the four bundle replicas stay byte-identical; the `executor`→human-approver disjointness invariant
      holds; `make validate-policy` / `validate-policy-scenarios` green

> **Delivered scope (v0.57.0).** Per **OQ-4**, in-process SPEC-073 toolkit narrowing + the loop's
> `read_only=True` admission are the **live** read-only control; the gateway axis + canonical rules are
> landed **ready-but-inert** (engine-proven, never matching on the live path because R-3 keeps the role
> off the wire). Making the policy axis itself live — the phase-6 wire contract or a new in-process
> evaluation seam — is the named follow-up **`FU-076-c`** (Delivery Gate + spec Non-Goals + roadmap).

## R-6: Live attribution — the audit/evidence record populated

- [x] Verify the bound role flows into the SPEC-075 audit events + SPEC-025 evidence turns
      **automatically** (the emitter seam + evidence field already exist) — **no schema change**; the
      `event_type` enum stays closed
- [x] Tests: an orchestration run emits audit events with the correct non-`None` `agent_role` per
      participant; `?agent_role=diagnostician` returns the member reads; member tool calls are
      reconstructable from the evidence record with attribution; an **unscoped** event stays
      byte-identical (dimension populated only where a role is bound)

## R-7: The four runbook profiles + the trigger boundary (OQ-3, OQ-7)

- [x] Build the capability **runbook-agnostic**; express each of the four workflows as a **declared
      diagnosis profile** (trigger + read toolkit families + proposed-remediation shape):
      (a) ServiceNow-incident, (b) observability-alert, (c) post-deploy-verify, (d) k8s-pod-degradation
- [x] Declare each runbook's read-tier families (the `diagnostician_read_families()` union is
      **documentation of intent** with no production caller — a data-integrity check, not a toolkit
      selector); the live `diagnostician` toolkit is narrowed by **risk tier + token `roles`**
      (SPEC-073 R-2), not selected by family; wire **(a)** and **(d)** end-to-end; cover **all four** by
      scenario tests (OQ-7)
- [x] Land the phase-5 trigger as **operator-invoked** (or anchored on an existing incident record);
      record unattended machine-trigger ingestion (webhook/alert auto-fire, dedup, storm control) as
      the **named follow-up `FU-076`** (OQ-3)
- [x] Tests: each runbook profile runs an autonomous read-only diagnosis with **no human approving any
      read**; the trigger cannot cause a mutation without the R-4 gate

## R-8: Four-point-gate parity, the no-new-frame boundary, and documentation (OQ-5, OQ-6)

- [x] Record the four-point-gate mapping (point 1 audit **live**-attributed per R-6, the R-5 policy
      axis landed ready-but-inert; point 2 identity on the one token; point 3 read-only posture
      enforced by toolkit narrowing + loop admission; point 4 no agentscope type on the v2 contract)
- [x] Surface the diagnosis through **existing** frames only — a normal assistant turn (synthesis),
      SPEC-025 evidence frames with role attribution (member reads), a SPEC-031 confirmation card
      (proposal); a contract test asserts `agent-stream-event.schema.json` and
      `execution-request.schema.json` are **byte-unchanged** (the multi-agent frame is phase 6, OQ-5)
- [x] Gated **live-cluster** read-only check for the k8s-pod-degradation + observability-alert
      runbooks and the ServiceNow-incident runbook against the SPEC-067 in-cluster mock; **no live
      mutation** (the proposal only parks) (OQ-6)
- [x] Docs: `identity-and-authorization-design.md` (phase-5 boundary note — the loop is live),
      `authorization-matrix.md` (agent-role binding — live in-process, policy axis ready-but-inert),
      `configuration-reference.md` (the `AGENT_ORCHESTRATION_MAX_STEPS` + any trigger knob), the
      roadmap multi-agent row (phase 5)
- [x] Root `make verify` green (incl. `validate-version`, `validate-policy`, the emitter-parity +
      contract-parity checks, and the SPEC-063 `execution-failure-test` campaign)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified (R-1…R-8)
- [x] all seven Open Questions ratified by the operator **exactly as recommended** (2026-11-06);
      the `plan.md` / `tasks.md` PROVISIONAL banners lifted (binding)
- [x] **`FU-076`** (unattended machine-trigger ingestion — OQ-3's deferral) recorded as a named
      follow-up in the delivery-roadmap multi-agent row + the spec Non-Goals so it is **not skipped**
      (a future spec, not dropped scope)
- [x] **`FU-076-b`** (the operator-initiated diagnose→act bridge that would wire the delivered
      `stage_remediation(...)` executor trigger — R-4) recorded as a named follow-up in the spec
      Non-Goals + roadmap; phase 5 ships the mechanism unit-proven but unwired (diagnosis-only)
- [x] **`FU-076-c`** (a live in-process policy-evaluation point that would make the SPEC-074
      `agent_roles_any` axis fire where R-3 keeps the role — R-5) recorded as a named follow-up in the
      spec Non-Goals + roadmap; phase 5 lands the axis + canonical rules ready-but-inert
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing SPEC-076
- [x] spec index in `docs/specs/README.md` updated; spec status set to `delivered`
      (done at the release gate — the `delivered` flip is version-stamped `as v0.57.0`)
- [x] confirm the unscoped single-agent path binds no role and is byte-identical, the only reachable
      role-binder is the orchestration frame, `agent-stream-event`/`execution-request` are
      byte-unchanged, no mutation dispatches without a distinct human approver, and autonomous resolve
      remains deferred (phase-5 boundary)
