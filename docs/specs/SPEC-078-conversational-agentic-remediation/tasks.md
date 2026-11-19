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

- [x] Add an opt-in **remediation-intent flag** (+ `profile`) to `AgentChatRequest` in
      `products/agent-platform/src/agent_service/schemas/v2.py` — `model_config =
      ConfigDict(extra="forbid")`, **no** `agent_role`; defaults off so the unscoped path is unchanged
- [x] Branch the chat turn (`api/v2/routes.py` `chat` L346 + the `GET /api/v2/chat/stream` SSE path L591)
      on the flag: when set **and** the caller holds `remediate:stage`, drive
      `run_conversational_remediation(...)`; otherwise the unscoped `reply_text` / `TurnStreamer` path
- [x] Add `run_conversational_remediation(...)` in `services/orchestration.py` composing the **delivered**
      `run_bounded_diagnosis(...)` + `stage_remediation(...)` **verbatim**; the route binds **no** role
      and the body carries none (the composition binds `orchestrator`/`diagnostician`/`executor`
      in-process)
- [x] Stream the diagnosis narrative through the **existing** `TurnStreamer` (`kernel_streaming.py`) and
      park the single proposal through the **existing** `ConfirmationCoordinator`
      (`kernel_confirmations.py`) → the existing SPEC-031 card + approval inbox (no new frame/view)
- [x] Tests: a remediation-intent turn produces a streamed diagnosis narrative and parks **one** proposed
      mutating call as a card carrying `staged_by_role="executor"`; a non-remediation turn is
      **byte-identical** to today (no role bound, no orchestration frame); the route itself dispatches
      **nothing**

## R-2: Team-proposal composition reusing delivered machinery (zero new mutation path)

- [x] Compose the delivered `run_bounded_diagnosis(...)` (bounded by `AGENT_ORCHESTRATION_MAX_STEPS`,
      failing closed to a partial diagnosis) + `stage_remediation(...)` (**one** `read_only=False` turn on
      `{session_id}::orch::staging`, *same* delegated token) **unchanged**
- [x] Preserve the SPEC-030 self-approval block + the `executor`→**distinct-human**-approver
      disjointness; the signed at-most-one-dispatch worker (SPEC-037/038/063) alone executes
- [x] Fail closed on a diagnosis-only profile (`remediation_shape is None`) or an unknown profile —
      **never** open an executor turn
- [x] Tests: a guard asserts no `TeamPipeline`/`GoalPipeline`/`A2AAgent` (or any agentscope orchestration
      surface) is constructed on the path (mirrors SPEC-076 R-1); the stager can never be the approver; a
      diagnosis-only profile fails closed and opens no executor turn (mirrors SPEC-077 R-2)

## R-3: The in-process role-axis policy check goes live (`FU-076-c`) (OQ-5)

- [x] Add an in-process `agent_roles_any` evaluation point at the **executor-staging seam** in
      `orchestration.py`, reading the bound role via `current_agent_role_value()` (`agent_role.py`) —
      *complementary to* (not replacing) the tool-gateway `evaluate()`; the role **never crosses a wire
      field** (SPEC-073 R-3)
- [x] Add the canonical rule expectation to `policy-scenarios.yaml`: an `executor` may stage the profile's
      mutating tool while a `diagnostician`/`orchestrator` may not; keep `policy-default.yaml`
      **byte-unchanged** unless a rule must be canonical (OQ-5)
- [x] **Condition (R-3):** if implementation grounding finds the axis cannot fire without a wire change,
      revert R-3 to **deferred** (record in the Delivery Gate) rather than break the role-off-the-wire
      invariant
- [x] Tests: the in-process rule is evaluated + enforced at the staging seam with the role never crossing
      a wire field; `make validate-policy` + `validate-policy-scenarios` (both engines) stay green; a
      byte-freeze assertion confirms `agent-stream-event`/`execution-request` unchanged and no
      `agent_role` on any wire field

## R-4: Audit attribution (the conversational flow is reconstructable)

- [x] Verify (**no new code**) the fan-out turns audit the SPEC-075 `agent_role` `orchestrator` /
      `diagnostician` and the staging turn audits `executor`; the parked card carries the SPEC-073
      `staged_by_role="executor"` provenance; **no** new `event_type` (the enum stays **closed** — the
      gateway reuses `chat_completed`)
- [x] Tests: the fan-out + staging turns emit audit events carrying the correct `agent_role`; the
      diagnose→propose→approve→execute chain is reconstructable and attributable to the same human +
      delegated token; the six-emitter parity family + contract-parity tests stay green

## R-5: Contract boundary — existing frames only, single-voice projection

- [x] Keep the intent flag `extra="forbid"` with **no** `agent_role`; ride **existing** frames only
      (`AgentChatResponse`, the assistant turn, the SPEC-025 evidence turn, the SPEC-031 card,
      `execution-request.schema.json`)
- [x] Narrate member (`diagnostician`) activity into the **one** session stream (single-voice projection)
      + attribute in audit — **not** a new multi-agent frame
- [x] Contract tests: `agent-stream-event.schema.json` + `execution-request.schema.json`
      **byte-unchanged**; no `agent_role` on any wire field; no agentscope type leaks through the
      platform-owned v2 contract (gate point 4); the phase-6 v2 contract is **not** a prerequisite

## R-6: The autonomy gradient is recorded as binding (ceiling fixed; R2/R3 deferred)

- [x] Record the gradient + ceiling in the spec + `authorization-matrix.md`: **R1** delivered; ceiling =
      **every mutation human-approved**; **R2** a named fast-follow (N *individually*-gated proposals,
      ADR-0011); **R3** deferred behind the ADR-0017 Decision-2 trigger
- [x] Tests: no path dispatches a mutation without a distinct-human approval; autonomous resolve is absent

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

- [x] Scenario tests: a remediation-intent turn parks **one** proposal; a non-remediation turn is
      **byte-identical**; a diagnosis-only profile **fails closed**; the in-process role-axis rule fires
- [x] Add `e2e/conversational-remediation-livecheck.sh` (mirroring `e2e/remediation-livecheck.sh`) + a
      `make conversational-remediation-livecheck` target: the **gated billable** leg drives one authorized
      conversational remediation and asserts the proposal **parks** with **zero** `execution_requested`
      dispatch and **no** HITL auto-approval; the **mocked-I/O** leg is collected by `make test` so it
      cannot be skipped silently
- [x] Record the SPEC-018 four-point-gate mapping (audit live-attributed; identity on the one token; park
      + distinct-human approval is the mutation ceiling; no new frame on the v2 contract)
- [x] Docs: `authorization-matrix.md` (the conversational entry + the now-live in-process role axis),
      `configuration-reference.md` (any new knob), `delivery-roadmap.md` (**`FU-077-agentic-remediation`**
      + **`FU-076-c`** closed; **R2** recorded as the fast-follow), `docs/specs/README.md` index (this
      row), `CHANGELOG.md`
- [x] Root `make verify` green across every leg

## Post-delivery parking correction (operator-authorized 2026-11-19)

The first paid check did not establish positive parking: its success assertion only
proved completion and absence of dispatch. The blocking executor path bypassed the
HITL event handler, and its virtual staging session could not be opened by the
approval API. The original delivery evidence above does not prove this integration.

- [x] Add failure-first coverage using the real kernel/confirmation coordinator and SDK events.
      Both blocking/SSE real-SDK cases failed on missing owner-session park before the fix.
      Script negative cases also reproduced false success for missing cards, decisions, and cleanup failure.
- [x] Route executor staging through existing HITL handling, on the owning chat session;
      keep diagnostic member memory isolated and prevent reuse of prior flow approval.
      The card is visible through the pending API; another turn is blocked while pending;
      real-SDK denial resumes the same agent without dispatch. SSE emits the existing card
      instead of a misleading message_end. This corrects the historical derived-staging-session design.
- [x] Require a durable pending card before live-check cleanup, plus zero execution and decisions;
      add negative cases for missing, unrelated, resolved, empty, wrong-owner, and read-only cards.
      Audit pagination is bounded/fail-closed; cleanup failures cannot print success. The paid fixture
      is an explicit approval-only rehearsal against existing scratch-restart-demo, not a fabricated outage.
- [x] Run affected test suites and record the results here.
      Agent-platform: **1,910 passed**; platform-gateway: **536 passed**;
      focused composition/HITL/middleware set: **280 passed**; live-check scenarios: **16 passed**.
      L3 security review returned no findings. These are targeted correction results, not a new full make verify run.
- [x] Rebuild the affected local service and rerun one paid check without approving any mutation.
      Local agent-service image: `0.60.0-dev-k8s-6e492758-parking-fix`; rollout succeeded.
      Paid rerun positively proved one pending mutation card on owner session
      `ses-74a83116-201c-47ca-97b8-b68ab2e96e4d`, confirmation
      `f7d29fa8-bb55-47c8-9b2b-7db12dbb65fa`; zero execution/decision events before disposal.
      The script then failed cleanup with HTTP 409 (the correct pending-session deletion guard),
      so this is **not** a clean end-to-end script exit. The same card was subsequently denied
      through the existing API (HTTP 200, durable `denied`); audit records only that intentional
      `deny` for `k8s.delete_pod`, with zero `execution_requested`/`execution_completed` across the
      session family. Session deletion returned 200, and a subsequent lookup returned 404.
      No second remediation scenario was started to retry cleanup.
- [x] Reproduce the cleanup HTTP 409 in the mocked pipeline and correct the harness lifecycle.
      Preserve the application guard; drain the denial stream (or close expiry), verify durable
      denial/expiry and no new pending card, recheck zero execution and only the exact cleanup
      denial, then check deletion. Added expiry/racing-denial and failed/unresolved/reparked/
      approved/dispatched/foreign-decision cases: **24 pipeline scenarios passed**.
      Real-SDK blocking/SSE tests now also prove DELETE 409 while pending and 200 after denial.
- [x] Rerun the complete affected suites and documentation/version checks after the cleanup correction.
      `make -C products/agent-platform test`: **1,918 passed** (including all 24 pipeline scenarios);
      `make -C products/platform-gateway test`: **536 passed**; both exited 0.
      `make docs-check validate-version` and `git diff --check`: **PASS**, version remains 0.60.0.
      Existing deprecation/OTLP shutdown warnings were nonfatal. The rebuilt agent deployment remains
      1/1 Ready, and the two temporary port-forwards were stopped after cleanup.
      Added the correction under `CHANGELOG.md` Unreleased; no release gate was performed.

- [x] Complete the full pre-commit `make verify` gate (2026-11-19): every leg passed.
      The execution-failure campaign finished **795 passed, 2 deselected, exit 0** in **0:45:17**;
      the complete root run finished successfully in **50m33s**, including all product suites,
      baseline portal **546** + build, validation, audit-contract, and delegated integration proofs.
      Campaign evidence: `.workspaces/spec063-evidence/20261119T135649Z-3fb3626b507a`.
      No new live acceptance or paid remediation scenario was performed by this gate.

The operator authorized a separate correction commit on 2026-11-19 before SPEC-079 implementation.
Version bump, tag, and push remain separate, unrequested gates for this correction.

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified (R-1…R-7); **R-3 reverts to deferred** (recorded, not
      forced) if the in-process axis cannot fire without a wire change
- [x] all seven Open Questions ratified by the operator **exactly as recommended** (2026-11-18); the
      `plan.md` / `tasks.md` PROVISIONAL banners lifted (binding)
- [x] **`FU-076`** (unattended machine-trigger ingestion) remains a **deferred named follow-up** in the
      roadmap + spec Non-Goals — **not** pulled in, **not** dropped; SPEC-078 stays **human-requested**
- [x] **R2** (multi-step remediation plans) is recorded as a **named fast-follow after R1** (operator
      2026-11-18) — **not** in v1; when built it stays N *individually*-gated proposals (ADR-0011), never
      a composite approval or an automatic multi-dispatch
- [x] **R3** (autonomous resolve) remains **deferred** behind the ADR-0017 Decision-2 revisit trigger
      (production-proven bounded diagnosis + a new trust-model ADR); the staged proposal **always** parks
      for a distinct human and the SPEC-030 self-approval block is unchanged
- [x] **`FU-076-c`** is folded into v1 as the R-3 in-process role axis (role off the wire); the **phase-6
      v2 multi-agent contract** stays open and is **not** a prerequisite
- [x] living docs updated; `CHANGELOG.md` entry added referencing SPEC-078
- [x] spec index in `docs/specs/README.md` updated; spec status set to `delivered` (done at the release
      gate — the `delivered` flip is version-stamped `as v0.60.0`)
- [x] version bump to **v0.60.0** (`VERSION` + products + portal lockstep, proven by `validate-version`)
      at the release gate
- [x] confirm: the unscoped single-agent chat path is **byte-identical** and `/api/v2/diagnose` +
      `/api/v2/remediate` are unchanged; `remediate:stage` is deny-by-default and **reused** (no new
      action); a staged proposal **always** parks for a **distinct human** and nothing dispatches without
      approval (self-approval block fires); both stream/execution schemas are byte-unchanged; no
      `agent_role` crosses a wire field; autonomous resolve remains deferred
