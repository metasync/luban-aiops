# v0.57.0 — Bounded Autonomous Diagnosis (SPEC-076)

Date: 2026-11-10
Release type: minor (phase 5 of the six-phase bounded read-only multi-agent
orchestration program gated by
[ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md)
`accepted` 2026-11-03 — the first phase that *binds* the SPEC-073/074/075
agent-roles **live** and the first **operator-invoked** multi-agent capability:
one new authenticated read-only endpoint (`POST /api/v2/diagnose` + its gateway
`POST /api/v1/diagnose` proxy), gated by the **existing** `chat` action. **No**
new wire frame — `agent-stream-event.schema.json` and
`execution-request.schema.json` are **byte-unchanged**, and the deployed
**unscoped** single-agent chat path (`/api/v2/chat`, `/chat/stream`) stays
byte-identical. Diagnosis-only: it synthesizes a diagnosis and *proposes*
remediation but ships **no production act trigger** (the diagnose-before-act
ceiling, Decision 2 — autonomous resolve deferred). No agentscope orchestration
surface is constructed (Decision 5).)

## Summary

This release ships
[SPEC-076](../../specs/SPEC-076-bounded-autonomous-diagnosis/spec.md), phase 5 of
the phased multi-agent SPEC series. Phases 2-4 —
[SPEC-073](../../specs/SPEC-073-role-scoped-agent-identity/spec.md) (v0.54.0,
role-scoped agent identity),
[SPEC-074](../../specs/SPEC-074-policy-role-axis/spec.md) (v0.55.0, the policy
role axis), and
[SPEC-075](../../specs/SPEC-075-multi-agent-audit-attribution/spec.md) (v0.56.0,
multi-agent audit attribution) — each landed **inert**: the identity, policy, and
audit machinery for a bounded multi-agent loop existed, but no deployed caller
bound a role. SPEC-076 is the **producer** that first binds them live.

It adds a platform-owned **bounded read-only orchestration loop**
(`services/orchestration.py`): an `orchestrator` fans out read-only
`diagnostician` members over the **same** delegated token, each turn bracketed by
SPEC-073's `agent_role_scope()` and each toolkit narrowed at the existing
`_ensure_toolkit(read_only=True)` seam. The fan-out is bounded by the new
`AGENT_ORCHESTRATION_MAX_STEPS` budget (default `20`) and **fails closed** to a
budget-limited partial diagnosis rather than ever widening to a mutating step.
Given an incident, the loop autonomously gathers read-only evidence and
synthesizes a **diagnosis plus a proposed remediation**, surfaced to the operator
through **existing** stream frames (a normal assistant turn, SPEC-025 evidence
frames, a SPEC-031 card) so the wire contract does not change.

**The honest ceiling (diagnose-before-act, Decision 2).** The loop *diagnoses*;
it does not *act*. A separate `executor`-scoped `stage_remediation(...)`
mechanism is **delivered and unit-proven** — it parks a proposal on the existing
SPEC-020/030/031 HITL card (carrying the SPEC-073 `staged_by_role` provenance)
for a **distinct human** to approve and the signed at-most-one-dispatch worker
(SPEC-037/038/063) to run, and fails closed for a diagnosis-only profile — but it
is **not wired to a production trigger** in phase 5: `run_bounded_diagnosis`
never calls it and `POST /api/v2/diagnose` is diagnosis-only. There is **zero new
mutation-path code** and autonomous *resolve* stays deferred. Turning the staged
proposal into an operator-initiated act is the named follow-up **FU-076-b**, not
shipped here.

**Live vs. ready-but-inert.** The **live** read-only control is in-process:
SPEC-073 toolkit narrowing (a `diagnostician` sees only read-tier tools for its
risk tier and token `roles`) plus the loop's `read_only=True` admission, and the
SPEC-075 audit/evidence `agent_role` dimension **is populated** per participant.
The SPEC-074 **policy axis** (`evaluate()`'s `agent_role` input + a minimal
canonical `agent_roles_any` rule pair) lands **ready-but-inert**: SPEC-073 R-3
keeps the bound role **off every wire field**, so no deployed gateway `evaluate()`
threads a non-`None` role and the rules never match on the live path. The axis
becomes live only through the phase-6 wire contract or a live in-process
policy-evaluation point (**FU-076-c**). Because the role never crosses the wire,
the in-process control is non-spoofable.

## What shipped

- **R-1 — The bounded read-only orchestration loop (`agent-platform`).**
  `services/orchestration.py` drives `run_bounded_diagnosis(...)` — a bounded
  fan-out of read-only `diagnostician` member turns over the existing
  `reply_text(..., read_only=True)` seam, synthesizing as `orchestrator`. The
  orchestrator consumes only member **summaries** (member intermediate steps stay
  out of the leader's context but remain reconstructable via the SPEC-025 evidence
  record). No agentscope `TeamPipeline`/`GoalPipeline`/`A2AAgent` surface is
  constructed (Decision 5); the loop is platform-owned Python over existing kernel
  seams, so the trigger is read-only **by construction**.
- **R-2 — Role binding via the orchestration frame.** The frame brackets
  orchestrator/diagnostician/executor turns in `agent_role_scope()`, keeping the
  role **process-local** (never in the SPEC-017 snapshot, never a JWT
  claim/header/wire field); a park/resume re-derives it per turn. The in-process
  SPEC-073 R-5 guard and the SPEC-075 R-5 audit-attribution guard move from "no
  caller binds a role" to "**only** the orchestration frame binds a role".
- **R-3 — Same-token identity preservation.** Every member runs on the **same**
  delegated token as the orchestrator — no new principal, claim, credential, or
  identity edge is minted, so the loop cannot widen what the human token already
  permits. The bound role crosses no wire field (the SPEC-073 R-3 invariant); the
  **gateway** SPEC-074 R-5 guard (`test_no_deployed_caller_threads_a_non_none_agent_role`)
  is unchanged and still passes with zero offenders.
- **R-4 — Diagnose-before-act.** The loop produces a diagnosis + a **proposed**
  remediation; `stage_remediation(...)` is delivered and unit-proven but **not**
  wired to any production trigger (the Decision 2 ceiling). A proposed remediation
  reaches reality only through the existing HITL approval + signed
  execution-request path, and **no mutation dispatches without a distinct human**
  approver (the SPEC-030 self-approval block fires unchanged).
- **R-5 — Policy enforcement + the canonical agent-role rule (OQ-4).** Both gateway
  `evaluate()` engines **accept** an `agent_role` axis (subtractive-only,
  fail-closed — unit-proven), and `policy-default.yaml` gains the minimal
  `deny-diagnostician-tools-mutate` + `require-approval-executor-tools-mutate`
  rules, synced byte-identically across all four replicas. They land **inert in
  deployment** (see Summary); the live read-only control is the in-process
  narrowing + `read_only=True` admission.
- **R-6 — Live attribution.** The SPEC-075 `agent_role` audit/evidence dimension
  binds a real non-`None` role on the orchestration path for the first time, so a
  member's read-only tool calls are attributable to *which role acted* beside *on
  whose behalf* (SPEC-013) and *under which delegation* (SPEC-070).
- **R-7 — Four runbook profiles + the trigger boundary (OQ-3, OQ-7).**
  `services/runbooks.py` expresses each of the operator's four named first
  workflows as pure data (trigger + read-tier families + proposed remediation
  shape): `servicenow-incident` and `observability-alert` are diagnosis-only;
  `post-deploy-verify` (rollback) and `k8s-pod-degradation` (remediation) can stage
  a proposal. The declared read families are **documentation of intent** — a
  `diagnostician_read_families()` union with **no production caller**; the live
  toolkit is narrowed by **risk tier + token `roles`** (SPEC-073 R-2), not selected
  by runbook family, so adding a runbook does not by itself widen any member's
  tools. The trigger is **operator-invoked**; unattended machine-trigger ingestion
  is **FU-076**.
- **R-8 — Four-point-gate parity + the no-new-frame boundary + docs.**
  `tests/test_contract_parity.py` records the SPEC-018 four-point-gate mapping and
  asserts the boundary: both frozen schemas carry no multi-agent vocabulary, the
  stream-event frame enum is unchanged, the `execution-request` replicas stay
  byte-identical, and the diagnose response validates against the existing chat
  frame. The unscoped turn stays byte-identical (no-diff).

## Changed

- **New knob (`agent-platform`, `platform-gateway`).** `AGENT_ORCHESTRATION_MAX_STEPS`
  (default `20`, validated `>= 1`) bounds **total member read steps per
  orchestration** (OQ-2) — a deliberate twin of `GATEWAY_BROWSER_FLOW_MAX_STEPS` /
  `AGENT_SKILL_GRADUATION_MAX_STEPS`; composed with the per-turn
  `AGENTSCOPE_MAX_ITERS` it gives a two-level bound. The gateway diagnose proxy
  carries a longer `PLATFORM_GATEWAY_DIAGNOSE_TIMEOUT_SECONDS` budget (default
  `120`). Both are documented in the
  [configuration reference](../../guides/configuration-reference.md).
- **Gated live-cluster read-only check (`platform-ops`, `agent-platform`).**
  `e2e/diagnosis-livecheck.sh` (`--local` mocked / `--live` gated) proves the two
  routes are deployed, drives the three live-wired runbooks read-only, and asserts
  the point-1 `chat_completed` attribution lands with **zero** `execution_requested`
  events (point-3 read-only); wired into `make diagnosis-livecheck` + `make e2e`.
- **Living docs.** The
  [identity-and-authorization design](../identity-and-authorization-design.md)
  records phase 5 delivered (the loop is live); the
  [authorization matrix](../authorization-matrix.md) gains an "Agent-Role Binding
  (SPEC-076, phase 5) — live in-process, policy axis ready-but-inert" section; and
  the [delivery-roadmap](../delivery-roadmap.md) multi-agent row records phase 5 +
  `FU-076`. The [specs index](../../specs/README.md) row moves to `delivered` and
  [CHANGELOG.md](../../../CHANGELOG.md) gains the 0.57.0 entry.
- **Doc-accuracy corrections (pre-ship review).** A pre-ship code & doc review
  returned **CHANGES-REQUESTED** and was remediated before release: four
  documentation-accuracy Majors corrected (the SPEC-074 axis is **ready-but-inert**,
  not live-on-the-wire; `stage_remediation` is delivered-unwired with **no
  production trigger**; the `diagnostician` toolkit is narrowed by risk tier +
  token roles, not runbook family; and the phase count/wording), two real defects
  fixed (the `diagnosis-livecheck` `execution_requested` query now keys on the
  session-id prefix, and `forget_session` reclaims the `::orch::*` derived
  orchestration agents so they no longer leak), plus five minors and six nits
  (including an `extra="forbid"` guard, a sha256 byte-freeze assertion, an
  `incident_id` `max_length`, and stale phase-2/3 docstrings).
- **Follow-ups recorded (not skipped).** `FU-076` (unattended machine-trigger
  ingestion — webhook/alert auto-fire, dedup, storm control), `FU-076-b` (the
  operator-initiated diagnose→act bridge that would wire the delivered
  `stage_remediation`), and `FU-076-c` (a live in-process policy-evaluation point
  for the SPEC-074 axis). **Phase 6** (the v2 multi-agent wire contract) remains
  open.

## Verification

- Full agent-platform suite **1774 passed** — including the new
  `test_orchestration.py` (the bounded loop, budget-limited fail-closed, all four
  runbook profiles driven read-only with no human approving any read, two of them
  driven end-to-end, and the executor-stages-never-dispatches proof),
  `test_diagnose_route.py`, `test_contract_parity.py` (8), and
  `test_diagnosis_livecheck.py` (6); platform-gateway **503 passed** (the diagnose
  proxy + route inventory).
- Root `make verify` green across all sixteen legs — the all-product `test`
  suites, overlays, dashboards, policy, policy-scenarios, version, secret-vocabulary,
  password-policy, secret-delivery-demo, portal (**546 passed**), the audit-contract
  Postgres round-trip, and the four delegated custody/runtime/multiproc/edge proofs
  over real docker + TLS — including the long-running SPEC-063
  `execution-failure-test` campaign run to completion: **795 passed, 2 deselected,
  exit 0** in 0:38:20 (evidence
  `.workspaces/spec063-evidence/20261108T111345Z-9c8f362be386`).
- After the pre-ship remediation, the affected suites were re-verified green:
  agent-platform **1774**, platform-gateway **503**, tool-gateway **1085**,
  `diagnosis-livecheck` **6**, `validate-policy` **23**, and policy-scenarios
  **156 + 35**.
- Phase-5 boundary confirmed: the unscoped single-agent path binds no role and is
  byte-identical, the only reachable role-binder is the orchestration frame,
  `agent-stream-event`/`execution-request` stay byte-unchanged, no mutation
  dispatches without a **distinct human** approver, and autonomous resolve remains
  deferred.
- `make validate-version` green at **0.57.0** across the eight products and the
  portal. An L3 deep security review of the delivery returned **no findings**.

## Posture

Read-only and **diagnose-before-act**. The loop can gather evidence and propose a
remediation but ships **no production act trigger** — every mutation still parks on
human-in-the-loop approval and dispatches over a signed execution request, and the
executor's `stage_remediation` is delivered inert. The deployed unscoped
single-agent chat path is **byte-identical** to v0.56.0, no wire frame changed, no
new principal/claim/credential/identity edge is minted, and no agentscope
orchestration surface is introduced (Decision 5). The SPEC-074 policy axis is
**ready-but-inert** on the wire (SPEC-073 R-3 keeps the role off every field); the
live read-only control is in-process toolkit narrowing + the loop's `read_only=True`
admission, which is non-spoofable because the role never crosses the wire.
Activating the staged remediation behind an operator diagnose→act bridge
(**FU-076-b**), a live in-process policy-evaluation point (**FU-076-c**),
unattended machine-trigger ingestion (**FU-076**), and the phase-6 v2 multi-agent
wire contract all remain **separate, future** work. Commit/tag/push and deployment
remain separate gates.
