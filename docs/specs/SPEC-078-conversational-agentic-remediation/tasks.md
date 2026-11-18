# SPEC-078 Tasks: Conversational Agentic Remediation (composing the delivered diagnosis loop + staging trigger into a human-requested, team-proposed, human-approved flow)

> **BINDING** — approved 2026-11-18. The operator ratified all seven Open Questions in
> [`spec.md`](spec.md) **exactly as recommended**, so the tasks below are now **binding** and the
> provisional banner is lifted (the SPEC-066/069/076/077 pattern). Task states: `[ ]` pending, `[x]`
> done. Keep tasks small and tied to requirement IDs. This increment is a **composition + entry** change
> over delivered machinery — **zero new mutation-path machinery**, role **off every wire field**
> (SPEC-073 R-3), `agent-stream-event`/`execution-request` **byte-unchanged**, and the **unscoped
> single-agent chat path byte-identical**. The siblings **`FU-076`** (unattended machine-trigger
> ingestion) and **R2** (multi-step remediation plans) stay **deferred** and are tracked in the Delivery
> Gate so they are not silently pulled in or dropped; **R3** (autonomous resolve) stays deferred behind
> the ADR-0017 Decision-2 trigger; **`FU-076-c`** *is* folded into v1 (R-3).

## R-1: A conversational remediation entry (OQ-1, OQ-2)

- [ ] Add an opt-in **remediation-intent flag** (+ `profile`) to `AgentChatRequest` in
      `products/agent-platform/src/agent_service/schemas/v2.py` — `model_config =
      ConfigDict(extra="forbid")`, **no** `agent_role`; defaults off so the unscoped path is unchanged
- [ ] Branch the chat turn (`api/v2/routes.py` `chat` L346 + the `GET /api/v2/chat/stream` SSE path L591)
      on the flag: when set **and** the caller holds `remediate:stage`, drive
      `run_conversational_remediation(...)`; otherwise the unscoped `reply_text` / `TurnStreamer` path
- [ ] Add `run_conversational_remediation(...)` in `services/orchestration.py` composing the **delivered**
      `run_bounded_diagnosis(...)` + `stage_remediation(...)` **verbatim**; the route binds **no** role
      and the body carries none (the composition binds `orchestrator`/`diagnostician`/`executor`
      in-process)
- [ ] Stream the diagnosis narrative through the **existing** `TurnStreamer` (`kernel_streaming.py`) and
      park the single proposal through the **existing** `ConfirmationCoordinator`
      (`kernel_confirmations.py`) → the existing SPEC-031 card + approval inbox (no new frame/view)
- [ ] Tests: a remediation-intent turn produces a streamed diagnosis narrative and parks **one** proposed
      mutating call as a card carrying `staged_by_role="executor"`; a non-remediation turn is
      **byte-identical** to today (no role bound, no orchestration frame); the route itself dispatches
      **nothing**

## R-2: Team-proposal composition reusing delivered machinery (zero new mutation path)

- [ ] Compose the delivered `run_bounded_diagnosis(...)` (bounded by `AGENT_ORCHESTRATION_MAX_STEPS`,
      failing closed to a partial diagnosis) + `stage_remediation(...)` (**one** `read_only=False` turn on
      `{session_id}::orch::staging`, *same* delegated token) **unchanged**
- [ ] Preserve the SPEC-030 self-approval block + the `executor`→**distinct-human**-approver
      disjointness; the signed at-most-one-dispatch worker (SPEC-037/038/063) alone executes
- [ ] Fail closed on a diagnosis-only profile (`remediation_shape is None`) or an unknown profile —
      **never** open an executor turn
- [ ] Tests: a guard asserts no `TeamPipeline`/`GoalPipeline`/`A2AAgent` (or any agentscope orchestration
      surface) is constructed on the path (mirrors SPEC-076 R-1); the stager can never be the approver; a
      diagnosis-only profile fails closed and opens no executor turn (mirrors SPEC-077 R-2)

## R-3: The in-process role-axis policy check goes live (`FU-076-c`) (OQ-5)

- [ ] Add an in-process `agent_roles_any` evaluation point at the **executor-staging seam** in
      `orchestration.py`, reading the bound role via `current_agent_role_value()` (`agent_role.py`) —
      *complementary to* (not replacing) the tool-gateway `evaluate()`; the role **never crosses a wire
      field** (SPEC-073 R-3)
- [ ] Add the canonical rule expectation to `policy-scenarios.yaml`: an `executor` may stage the profile's
      mutating tool while a `diagnostician`/`orchestrator` may not; keep `policy-default.yaml`
      **byte-unchanged** unless a rule must be canonical (OQ-5)
- [ ] **Condition (R-3):** if implementation grounding finds the axis cannot fire without a wire change,
      revert R-3 to **deferred** (record in the Delivery Gate) rather than break the role-off-the-wire
      invariant
- [ ] Tests: the in-process rule is evaluated + enforced at the staging seam with the role never crossing
      a wire field; `make validate-policy` + `validate-policy-scenarios` (both engines) stay green; a
      byte-freeze assertion confirms `agent-stream-event`/`execution-request` unchanged and no
      `agent_role` on any wire field

## R-4: Audit attribution (the conversational flow is reconstructable)

- [ ] Verify (**no new code**) the fan-out turns audit the SPEC-075 `agent_role` `orchestrator` /
      `diagnostician` and the staging turn audits `executor`; the parked card carries the SPEC-073
      `staged_by_role="executor"` provenance; **no** new `event_type` (the enum stays **closed** — the
      gateway reuses `chat_completed`)
- [ ] Tests: the fan-out + staging turns emit audit events carrying the correct `agent_role`; the
      diagnose→propose→approve→execute chain is reconstructable and attributable to the same human +
      delegated token; the six-emitter parity family + contract-parity tests stay green

## R-5: Contract boundary — existing frames only, single-voice projection

- [ ] Keep the intent flag `extra="forbid"` with **no** `agent_role`; ride **existing** frames only
      (`AgentChatResponse`, the assistant turn, the SPEC-025 evidence turn, the SPEC-031 card,
      `execution-request.schema.json`)
- [ ] Narrate member (`diagnostician`) activity into the **one** session stream (single-voice projection)
      + attribute in audit — **not** a new multi-agent frame
- [ ] Contract tests: `agent-stream-event.schema.json` + `execution-request.schema.json`
      **byte-unchanged**; no `agent_role` on any wire field; no agentscope type leaks through the
      platform-owned v2 contract (gate point 4); the phase-6 v2 contract is **not** a prerequisite

## R-6: The autonomy gradient is recorded as binding (ceiling fixed; R2/R3 deferred)

- [ ] Record the gradient + ceiling in the spec + `authorization-matrix.md`: **R1** delivered; ceiling =
      **every mutation human-approved**; **R2** a named fast-follow (N *individually*-gated proposals,
      ADR-0011); **R3** deferred behind the ADR-0017 Decision-2 trigger
- [ ] Tests: no path dispatches a mutation without a distinct-human approval; autonomous resolve is absent

## R-7: Evidence — the four-point gate + a gated live-check + docs (OQ-6)

> **SPEC-018 four-point-gate mapping (recorded 2026-11-18).** The conversational flow re-affirms the
> four-point gate: **1 — audit live-attributed:** the fan-out + staging turns audit the SPEC-075
> `agent_role` dimension and park the SPEC-073 `staged_by_role` provenance; **no** new `event_type` (the
> enum stays closed). **2 — identity on the one token:** the flow rides the *same* gateway-forwarded
> delegated bearer token across the fan-out + staging; the route binds no role and mints nothing.
> **3 — park + distinct-human approval is the mutation ceiling:** the executor **proposes** one mutating
> call → **parks** on HITL → a **distinct** human approves; the SPEC-030 self-approval block is unchanged
> and nothing auto-dispatches. **4 — no new frame on the v2 contract:** the intent flag is
> `extra="forbid"` and carries **no** `agent_role`; the response rides existing frames and
> `agent-stream-event`/`execution-request` stay **byte-unchanged**.

- [ ] Scenario tests: a remediation-intent turn parks **one** proposal; a non-remediation turn is
      **byte-identical**; a diagnosis-only profile **fails closed**; the in-process role-axis rule fires
- [ ] Add `e2e/conversational-remediation-livecheck.sh` (mirroring `e2e/remediation-livecheck.sh`) + a
      `make conversational-remediation-livecheck` target: the **gated billable** leg drives one authorized
      conversational remediation and asserts the proposal **parks** with **zero** `execution_requested`
      dispatch and **no** HITL auto-approval; the **mocked-I/O** leg is collected by `make test` so it
      cannot be skipped silently
- [ ] Record the SPEC-018 four-point-gate mapping (audit live-attributed; identity on the one token; park
      + distinct-human approval is the mutation ceiling; no new frame on the v2 contract)
- [ ] Docs: `authorization-matrix.md` (the conversational entry + the now-live in-process role axis),
      `configuration-reference.md` (any new knob), `delivery-roadmap.md` (**`FU-077-agentic-remediation`**
      + **`FU-076-c`** closed; **R2** recorded as the fast-follow), `docs/specs/README.md` index (this
      row), `CHANGELOG.md`
- [ ] Root `make verify` green across every leg

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified (R-1…R-7); **R-3 reverts to deferred** (recorded, not
      forced) if the in-process axis cannot fire without a wire change
- [ ] all seven Open Questions ratified by the operator **exactly as recommended** (2026-11-18); the
      `plan.md` / `tasks.md` PROVISIONAL banners lifted (binding)
- [ ] **`FU-076`** (unattended machine-trigger ingestion) remains a **deferred named follow-up** in the
      roadmap + spec Non-Goals — **not** pulled in, **not** dropped; SPEC-078 stays **human-requested**
- [ ] **R2** (multi-step remediation plans) is recorded as a **named fast-follow after R1** (operator
      2026-11-18) — **not** in v1; when built it stays N *individually*-gated proposals (ADR-0011), never
      a composite approval or an automatic multi-dispatch
- [ ] **R3** (autonomous resolve) remains **deferred** behind the ADR-0017 Decision-2 revisit trigger
      (production-proven bounded diagnosis + a new trust-model ADR); the staged proposal **always** parks
      for a distinct human and the SPEC-030 self-approval block is unchanged
- [ ] **`FU-076-c`** is folded into v1 as the R-3 in-process role axis (role off the wire); the **phase-6
      v2 multi-agent contract** stays open and is **not** a prerequisite
- [ ] living docs updated; `CHANGELOG.md` entry added referencing SPEC-078
- [ ] spec index in `docs/specs/README.md` updated; spec status set to `delivered` (done at the release
      gate — the `delivered` flip is version-stamped `as v0.60.0`)
- [ ] version bump to **v0.60.0** (`VERSION` + products + portal lockstep, proven by `validate-version`)
      at the release gate
- [ ] confirm: the unscoped single-agent chat path is **byte-identical** and `/api/v2/diagnose` +
      `/api/v2/remediate` are unchanged; `remediate:stage` is deny-by-default and **reused** (no new
      action); a staged proposal **always** parks for a **distinct human** and nothing dispatches without
      approval (self-approval block fires); both stream/execution schemas are byte-unchanged; no
      `agent_role` crosses a wire field; autonomous resolve remains deferred
