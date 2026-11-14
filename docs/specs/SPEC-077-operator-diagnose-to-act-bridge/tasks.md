# SPEC-077 Tasks: Operator Diagnose→Act Bridge (Wiring the Delivered `stage_remediation` Behind an Explicit Human Trigger)

> **BINDING** — approved 2026-11-11. The operator ratified all nine Open Questions in
> [`spec.md`](spec.md) **exactly as recommended**, so the tasks below are now **binding** and the
> provisional banner is lifted (the SPEC-066/069/076 pattern). Task states: `[ ]` pending, `[x]` done.
> Keep tasks small and tied to requirement IDs. This increment supplies **only the production trigger**
> that reaches the delivered-but-unwired `stage_remediation(...)` — **zero new mutation-path machinery**.
> The sibling follow-ups **`FU-076`** (unattended machine-trigger ingestion) and **`FU-076-c`** (a live
> SPEC-074 policy axis where R-3 keeps the role off the wire — OQ-6) stay **deferred** and are tracked in
> the Delivery Gate so they are not silently pulled in or dropped.

## R-1: The operator-initiated staging trigger (OQ-1, OQ-2)

- [x] Add `RemediateRequest` to `schemas/v2.py` — `{profile, goal, diagnosis, session_id?, model?}`,
      `model_config = ConfigDict(extra="forbid")`, **no** `agent_role`; `goal`/`diagnosis` `min_length=1`
      (fail-closed if absent/empty) — mirroring the delivered `AgentDiagnoseRequest` posture
- [x] Add `POST /api/v2/remediate` in `api/v2/routes.py`, mirroring the `diagnose` handler:
      `_verified_requester` → `ensure_session` → `_reject_if_parked` → `_resolve_model` → `get_profile`
- [x] Call the **delivered** `stage_remediation(kernel, profile=…, goal=…, diagnosis=…, session_id=…,
      user_name=…, bearer_token=…, model_id=…)` **unchanged**; the `goal` + `diagnosis` come from the
      request (OQ-2 request-carried — the synthesis the portal already received from `/diagnose`)
- [x] Return through the **existing** `AgentChatResponse` (the parked confirmation rides the existing
      SPEC-031 card frame — no new response frame); the route binds no role and dispatches nothing
- [x] Tests: a staging request for `post-deploy-verify` / `k8s-pod-degradation` binds `AgentRole.EXECUTOR`
      for exactly one `read_only=False` turn on `{session_id}::orch::staging`; the proposed mutating call
      **parks** as a card carrying `staged_by_role="executor"`; the route itself dispatches **nothing**

## R-2: Fail-closed on a diagnosis-only or unknown profile

- [x] Unknown profile → **422** (mirror `/diagnose`'s `unknown diagnosis profile` guard) **before** any
      executor turn — never coerced to a wider runbook
- [x] `profile.remediation_shape is None` (`servicenow-incident`, `observability-alert`) → **4xx** by
      pre-checking in the handler and/or mapping the delivered `ValueError`; **no** executor turn opened
- [x] Tests: `remediate(servicenow-incident)`, `remediate(observability-alert)`, and an unknown profile
      each return 4xx with **no** `stage_remediation` call and **no** executor turn

## R-3: A new deny-by-default policy action gates the trigger (OQ-3)

- [x] Add the action `remediate:stage` to the canonical `policy-default.yaml` — granted to
      `platform-admin` + `operator`; denied to `developer`, `read-only-observer`, `auditor`
- [x] Sync to the three byte-identical replicas via `make sync-policy`; register in `PROTECTED_ACTIONS` +
      the action vocabulary of **both** gateway `evaluate()` engines
- [x] Add `policy-scenarios.yaml` expectations for the new action (both engines)
- [x] Tests: `make validate-policy` + `validate-policy-scenarios` green; a token without `remediate:stage`
      is denied **403** at the gateway; the four bundle replicas stay byte-identical; the
      `executor`→**distinct-human**-approver disjointness + the SPEC-030 self-approval block hold (the
      stager can never be the approver)

## R-4: Portal entry + park/resume UX (OQ-4) — **DEFERRED 2026-11-11 (operator re-scope)**

> **DEFERRED — not in v0.58.0.** Implementation grounding found the ratified premise false: the
> operator portal has **no** completed-diagnosis surface (SPEC-076 shipped the diagnose flow
> **backend-only**; the portal was last touched by SPEC-072 / v0.53.0 — no diagnosis card, no
> `/api/v1/diagnose` client). The operator's direction is an **agentic / multi-agent** remediation
> (human-requested, agent-team-carried, conversational or graduated-autonomy) rather than a button on a
> card, so building this UX would be throwaway. Tracked as the named follow-up
> **`FU-077-agentic-remediation`** (a SPEC-078 candidate) in the Delivery Gate below + the roadmap +
> spec Non-Goals. The backend trigger (R-1/R-2/R-3/R-5/R-6/R-7) is UX-agnostic and ships regardless.
> Original tasks retained below for the record (left unchecked — deferred, not done).

- [ ] Add a **Stage remediation** button on the completed diagnosis card, rendered **only** for a
      stageable profile (`post-deploy-verify` / `k8s-pod-degradation`) **and** a role holding
      `remediate:stage`; absent for diagnosis-only profiles and unauthorized roles
- [ ] Wire it to `POST /api/v1/remediate` passing the diagnosis's `goal` + `diagnosis` text; the parked
      proposal surfaces through the **existing** SPEC-031 confirmation card + approval-inbox flow (no new
      card type, no new resume path)
- [ ] Tests (Vitest): button visibility by profile + role; a staged proposal is visible to a distinct
      approver in the existing inbox; typechecked production build green

## R-5: Audit attribution (OQ-5)

- [x] Verify (no new code) the wired executor turn audits the SPEC-075 `agent_role="executor"` dimension
      and the parked card carries the SPEC-073 `staged_by_role="executor"` provenance; **no** new
      `event_type` — the enum stays **closed**
- [x] Tests: an executor staging turn emits an audit event carrying `agent_role="executor"`; the
      diagnose→act bridge is reconstructable (diagnosis `chat_completed` role `orchestrator`/`diagnostician`
      + staged proposal role `executor`, same human + delegated token); the six-emitter parity family +
      contract-parity tests stay green

## R-6: Contract boundary — existing frames only, role off the wire

- [x] `RemediateRequest` is `extra="forbid"` and carries **no** `agent_role`; a smuggled role or misspelt
      key is refused **4xx**
- [x] Return via the existing `AgentChatResponse` + the SPEC-031 card + `execution-request.schema.json`;
      add **no** new frame
- [x] Contract tests: `agent-stream-event.schema.json` and `execution-request.schema.json` are
      **byte-unchanged**; no `agent_role` crosses any wire field (SPEC-073 R-3)

## R-7: Proxy timeout budget for the staging turn — carries the v0.57.0 finding (OQ-7)

- [x] Add `PLATFORM_GATEWAY_REMEDIATE_TIMEOUT_SECONDS` (`platform-gateway/core/config.py`, **code default
      `300`s**, mirroring `PLATFORM_GATEWAY_DIAGNOSE_TIMEOUT_SECONDS`); the gateway `POST /api/v1/remediate`
      proxy (mirroring `/api/v1/diagnose`) uses it
- [x] Document the new knob + default in `configuration-reference.md`
- [x] Record the too-tight **`120`s `PLATFORM_GATEWAY_DIAGNOSE_TIMEOUT_SECONDS` code default** as a
      tracked follow-up finding in the delivery roadmap + the Delivery Gate below (the dev overlay already
      sets `300`s via `a7b3ba6a`; the **product** default is left unchanged pending real provider-latency
      data — this spec does **not** silently change it)
- [x] Tests: the remediate proxy does not `ReadTimeout` on a legitimate live staging turn

## R-8: Evidence — the four-point gate + a gated live-check + docs (OQ-8, OQ-9)

> **SPEC-018 four-point-gate mapping (recorded 2026-11-11).** The operator-initiated diagnose→act
> trigger re-affirms the four-point gate for the new control flow:
> **1 — audit live-attributed:** the wired executor staging turn audits the SPEC-075
> `agent_role="executor"` dimension through the delivered `build_audit_event` seam and parks the
> SPEC-073 `staged_by_role="executor"` provenance; **no** new `event_type` — the gateway reuses
> `chat_completed`, so the enum stays **closed** (proven by `TestDiagnoseActBridgeAttribution` +
> livecheck point 1).
> **2 — identity on the one token:** the staging turn rides the *same* gateway-forwarded delegated
> bearer token; the route binds no role and mints nothing (proven by
> `test_staging_rides_the_same_token_and_leaves_no_role_bound` + the single-token live drive).
> **3 — park + distinct-human approval is the mutation ceiling:** the executor **proposes** one
> mutating call → **parks** on HITL → a **distinct** human approves; the SPEC-030 self-approval block
> is unchanged and nothing auto-dispatches (proven by livecheck point 3 — **zero**
> `execution_requested` across the whole session family — + the four-profile scenario tests).
> **4 — no new frame on the v2 contract:** `RemediateRequest` is `extra="forbid"` and carries **no**
> `agent_role`; the response rides the existing `AgentChatResponse` + SPEC-031 card, and
> `agent-stream-event.schema.json` / `execution-request.schema.json` stay **byte-unchanged** with no
> `agent_role` on any wire field (proven by the contract-parity tests + the livecheck no-wire-leak
> assertion).

- [x] Scenario tests for all four profiles at the trigger: the two stageable profiles **park** a proposal
      (never dispatch); the two diagnosis-only profiles **fail closed** (OQ-8)
- [x] Add `e2e/remediation-livecheck.sh` (mirroring `e2e/diagnosis-livecheck.sh`) + a
      `make remediation-livecheck` target: the **gated billable** leg drives one authorized staging turn
      and asserts the proposal **parks** with **zero** `execution_requested` dispatch and **no** HITL
      auto-approval; the **mocked-I/O** leg is collected by `make test` so it cannot be skipped silently
- [x] Record the SPEC-018 four-point-gate mapping (audit live-attributed; identity on the one token;
      park + distinct-human approval is the mutation ceiling; no new frame on the v2 contract)
- [x] Docs: `authorization-matrix.md` (`remediate:stage` + the executor→human invariant),
      `configuration-reference.md` (the R-7 knob), `delivery-roadmap.md` (**FU-076-b closed**; the `120`s
      finding), `docs/specs/README.md` index (this row), `CHANGELOG.md`
- [x] Root `make verify` green across every leg (confirmed 2026-11-11: all legs exit 0 — `make test`
      incl. agent-platform **1793** + platform-gateway **510** + the **8** livecheck scenarios; every
      `validate-*`; `portal-test`; `audit-contract-test`; the four `delegated-*` campaigns; SPEC-063
      `execution-failure-test` **795 passed**)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified (R-1…R-8 **except R-4**, deferred 2026-11-11 by
      operator re-scope — see the R-4 section + the `FU-077-agentic-remediation` follow-up below)
- [x] all nine Open Questions ratified by the operator **exactly as recommended** (2026-11-11); the
      `plan.md` / `tasks.md` PROVISIONAL banners lifted (binding). **OQ-4 superseded** post-approval
      (2026-11-11 operator re-scope) — R-4 deferred as `FU-077-agentic-remediation`; the backend
      trigger (R-1/R-2/R-3/R-5/R-6/R-7) is UX-agnostic and ships in v0.58.0
- [x] **`FU-076`** (unattended machine-trigger ingestion) and **`FU-076-c`** (a live in-process policy
      evaluation point making the SPEC-074 `agent_roles_any` axis fire where R-3 keeps the role — OQ-6)
      remain recorded as **deferred named follow-ups** in the roadmap + spec Non-Goals — **not** pulled
      into this increment, **not** dropped
- [x] **`FU-077-agentic-remediation`** (R-4 deferred 2026-11-11 by operator re-scope) is recorded as a
      **deferred named follow-up** + **SPEC-078 candidate** in the roadmap + spec Non-Goals: an
      **agentic / multi-agent** remediation model — human-requested, carried out by an agent team,
      surfacing through the **existing conversational** portal surface (no diagnosis card, no discrete
      button) or graduated autonomy. Its OQs (conversational entry vs. card; team-*proposal* vs.
      team-*execution*; the autonomy gradient; the **ADR-0017 Decision-2** revisit; making the
      `FU-076-c` policy axis live) are **not** resolved here — **not** pulled into v0.58.0, **not**
      dropped. The v0.58.0 backend trigger is its prerequisite (any entry shape reaches the same wired
      `stage_remediation`)
- [x] the **`120`s** `PLATFORM_GATEWAY_DIAGNOSE_TIMEOUT_SECONDS` **code-default** finding is recorded as a
      tracked follow-up (R-7): dev overlay already `300`s; product default unchanged pending latency data
- [x] living docs updated; `CHANGELOG.md` entry added referencing SPEC-077
- [x] spec index in `docs/specs/README.md` updated; spec status set to `delivered` (done at the release
      gate — the `delivered` flip is version-stamped `as v0.58.0`)
- [x] version bump to **v0.58.0** (`VERSION` + products + portal lockstep, proven by `validate-version`)
      at the release gate
- [x] confirm: `/api/v2/diagnose` is unchanged and the unscoped single-agent path stays byte-identical;
      `remediate:stage` is deny-by-default; a staged proposal **always** parks for a **distinct human**
      and nothing dispatches without approval (self-approval block fires); both stream/execution schemas
      are byte-unchanged; no `agent_role` crosses a wire field; autonomous resolve remains deferred
