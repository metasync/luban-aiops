# Spike: Agentic / Multi-Agent Remediation (`FU-077-agentic-remediation`) — Design Exploration

Status: exploration / design framing (2026-11-18) — **reviewed & approved by the operator
2026-11-18**. This memo resolves the five Open Questions the operator deferred out of
[SPEC-077](../specs/SPEC-077-operator-diagnose-to-act-bridge/spec.md) as the named follow-up
**`FU-077-agentic-remediation`** (a **SPEC-078 candidate**), and recommends a
decision-complete shape for that spec. The operator approved all five resolutions **as
recommended** and settled the two scope forks (§8): **R2 multi-step plans → a named
fast-follow after R1**, and **`FU-076-c` in-process role axis → folded into v1**. On its own
this memo authorizes **no** runtime change, **no** new ADR, **no** SPEC number, and **no**
implementation; authoring `draft` SPEC-078 is the operator's next gate (§7).
Date: 2026-11-18
Roadmap home: [Exploration Backlog](../agentic-aiops-platform/delivery-roadmap.md#exploration-backlog) — the "Multi-agent orchestration & bounded autonomy" row (the `FU-077-agentic-remediation` / SPEC-078 candidate)
Program gate: [ADR-0017](../adr/0017-bounded-read-only-multi-agent-orchestration.md) (`accepted` 2026-11-03) — **Decision 2** (the diagnose-before-act autonomy ceiling) is the load-bearing constraint this memo tests
Foundational memo: [multi-agent-orchestration-spike.md](multi-agent-orchestration-spike.md) (§5 diagnose-before-act, §6 segregation-of-duty model, §7 the phased series)
Builds on (all delivered): [SPEC-073](../specs/SPEC-073-role-scoped-agent-identity/spec.md) role identity, [SPEC-074](../specs/SPEC-074-policy-role-axis/spec.md) policy role axis, [SPEC-075](../specs/SPEC-075-multi-agent-audit-attribution/spec.md) audit attribution, [SPEC-076](../specs/SPEC-076-bounded-autonomous-diagnosis/spec.md) bounded read-only diagnosis (phase 5), [SPEC-077](../specs/SPEC-077-operator-diagnose-to-act-bridge/spec.md) the operator diagnose→act trigger (`FU-076-b`)
Evidence baseline: repository at **v0.59.0** (`e4779bae`); static reading of the delivered specs, ADR-0017, and the v0.59.0 `AgentKernel` collaborator seams. No agent was run, nothing was deployed, no billable call was made in authoring this memo.

## 1. Question and framing

> SPEC-077 shipped the **UX-agnostic backend trigger** for remediation
> (`POST /api/v2/remediate` → the `executor`-scoped `stage_remediation(...)`), but
> **deferred** the human-facing half (its R-4). The deferral note records the
> operator's product direction verbatim: remediation should be **agentic /
> multi-agent** — *human-requested, carried out by an agent team, surfacing through
> the existing conversational portal surface (no diagnosis card, no discrete button)
> or graduated autonomy* — not a button on a card. That direction is the named
> follow-up `FU-077-agentic-remediation`, and SPEC-077 left its five Open Questions
> explicitly **unresolved**. This memo resolves them.

The five deferred Open Questions (SPEC-077 `tasks.md` Delivery Gate + spec Non-Goals):

1. **Conversational entry vs. card** — how does an operator *request* a remediation,
   and where does it *surface*?
2. **Team-*proposal* vs. team-*execution*** — does the agent team merely propose a
   remediation for a human to approve, or does it execute (autonomous resolve)?
3. **The autonomy gradient** — what rungs exist between "operator clicks stage" and
   "team resolves unattended," and which does the first spec deliver?
4. **The ADR-0017 Decision-2 revisit** — does this spec move the diagnose-before-act
   ceiling, or stay under it?
5. **Making the `FU-076-c` policy axis live** — does the SPEC-074 `agent_roles_any`
   axis finally fire on this path, and if so how (without putting the role on the wire)?

Recommendation summary (each resolved in §3):

- **Conversational entry.** Remediation is requested and surfaced *inside an existing
  chat turn*; the only discrete UI element is the **already-existing** SPEC-031
  confirmation card for the parked mutation. No diagnosis card, no new button.
- **Team-*proposal*, not team-execution.** The team diagnoses (read-only, autonomous)
  and *proposes* one remediation that stages onto the existing HITL card; a **distinct
  human** approves; the existing signed at-most-one-dispatch worker executes.
- **Autonomy gradient: fix the ceiling, deliver the conversational-propose rung (R1).**
  Every mutation stays human-approved; **R2 multi-step plans are a named fast-follow after
  R1** (operator decision), and each step is *individually* gated (ADR-0011: a composition is
  not a transaction).
- **Do NOT revisit ADR-0017 Decision-2.** Its deferral trigger ("after bounded
  read-only diagnosis is proven in production") is not met; autonomous resolve stays
  deferred. **No new ADR** is expected — SPEC-078 composes delivered machinery.
- **Fold `FU-076-c` in as an *in-process* role-axis check — in v1** (operator decision) at
  the staging seam (the role never crosses the wire, so SPEC-073 R-3 holds). This is the
  first flow where role-differentiated policy is meaningful (§3.5).

The net effect: SPEC-078 is a **composition + entry** spec, **not** a mutation-path,
trust-model, or contract change. It wires the delivered SPEC-076 diagnosis loop and the
delivered SPEC-077 staging trigger into one conversational flow, surfaced through the
two collaborator seams v0.59.0 just extracted (`TurnStreamer` for the SSE reply,
`ConfirmationCoordinator` for the park/resume).

## 2. What is already delivered (the foundation SPEC-078 composes)

SPEC-078 should add **no new mutation-path machinery**. Everything below ships today:

- **Roles + in-process narrowing (SPEC-073).** A closed `AgentRole` enum
  (`diagnostician` / `orchestrator` / `executor`), an `AGENT_ROLE` contextvar,
  per-role toolkit narrowing at the `_ensure_toolkit` seam, and kernel-internal
  `staged_by_role` provenance. **R-3 invariant: the role never crosses a wire field.**
- **Policy role axis (SPEC-074).** An additive, **ready-but-inert** `agent_roles_any`
  axis on `policy-rule.schema.json` (v3) and an `agent_role: str | None = None` input on
  **both** gateway `evaluate()` engines, composing conjunctively with the human
  `roles_any` axis; plus the `executor`→**distinct-human**-approver disjointness encoded
  as policy. Inert today because no deployed caller threads a non-`None` role to a gateway
  `evaluate()` — that gap is exactly `FU-076-c` (§3.5).
- **Audit attribution (SPEC-075).** An additive `agent_role` dimension on the durable
  audit envelope and the SPEC-025 evidence turn, enum-closed, omitted when absent; the
  six-emitter parity family populates it from `current_agent_role_value()`.
- **Bounded read-only diagnosis loop (SPEC-076, phase 5).** A platform-owned
  `orchestrator` fans out read-only `diagnostician` members over the same governed
  gateway, bounded by `AGENT_ORCHESTRATION_MAX_STEPS`, **failing closed** to a partial
  diagnosis; it synthesizes a diagnosis + a *proposed* remediation. **No agentscope
  orchestration surface** (`TeamPipeline`/`GoalPipeline`/`A2AAgent` kept out, ADR-0017
  Decision 5). Surfaced through **existing** frames (single-voice projection), so the
  phase-6 v2 contract stayed open. Invoked today by `POST /api/v2/diagnose`.
- **Operator diagnose→act trigger (SPEC-077, `FU-076-b`).** `stage_remediation(...)`
  wired behind `POST /api/v2/remediate` (+ gateway `/api/v1/remediate` proxy), gated by a
  deny-by-default `remediate:stage` action. It binds `AgentRole.EXECUTOR` for **one**
  `read_only=False` staging turn on the derived `{session_id}::orch::staging` session over
  the *same* delegated token, anchored on a **request-carried** completed diagnosis (no
  fan-out re-run); the executor's toolkit *proposes* the single mutating call, which parks
  as the existing SPEC-020/030/031 card with `staged_by_role="executor"`. Two profiles are
  stageable (`post-deploy-verify`, `k8s-pod-degradation`); diagnosis-only profiles fail
  closed 4xx.
- **The governed mutation path (SPEC-020/030/031 + SPEC-037/038/063, ADR-0007/0010/0013).**
  One HITL gate per mutating flow, a self-approval block (the approver is a *distinct*
  human), a signed envelope declaring authority provenance, a durable single-use claim,
  at-most-one dispatch, no automatic retry.
- **The v0.59.0 collaborator seams.** `TurnStreamer` (the SSE streaming turn) and
  `ConfirmationCoordinator` (the HITL park / resume / expire path) are now clean,
  separately-testable collaborators — the two seams a conversational multi-agent
  remediation flow composes through, and the two the v0.59.0 UI→backend e2e just
  verified live (progressive stream + write-tier park → tier-2 approve → signed resume).

**The gap SPEC-078 fills** is narrow and concrete: SPEC-076's loop and SPEC-077's staging
trigger are both reachable **only** through dedicated operator-initiated endpoints
(`/diagnose`, `/remediate`), and the portal has **no** diagnosis or remediation surface at
all (SPEC-076 shipped backend-only; the portal was last touched by SPEC-072 / v0.53.0).
Nothing today drives *diagnose → propose → stage* from **within a conversational chat
turn**. That composition-and-entry wiring is the spec.


## 3. The five Open Questions — recommended resolutions

### 3.1 OQ-1 — Conversational entry vs. card → **conversational entry**

**Recommendation:** the operator requests remediation *in a normal chat turn* ("this pod
is crash-looping — diagnose it and propose a fix"), and the flow surfaces **in that same
conversation**. The **only** discrete UI element is the **already-shipped** SPEC-031
confirmation card for the parked mutation — which is unavoidable (a mutation must park
somewhere a distinct human can approve it) and already exists. **No diagnosis card, no new
button, no new portal view.**

Why this is the right read of the operator's direction:

- The deferral note rejects "a button on a card" and names "the existing conversational
  portal surface." A chat turn *is* that surface; it needs no new portal component.
- It composes the two v0.59.0 seams directly: the streamed reply rides `TurnStreamer`; the
  parked proposal rides `ConfirmationCoordinator` → the existing card + approval inbox. The
  v0.59.0 e2e already proved both live in the portal chat.
- It keeps the SPEC-076 single-voice projection: member (diagnostician) activity is
  narrated into the one session stream and attributed in audit (SPEC-075), **not** surfaced
  as a new multi-agent frame — so the **phase-6 v2 contract stays open** and is *not* a
  prerequisite (mirrors SPEC-076/077 riding existing frames).

**Design consequence (the real net-new):** today the SPEC-076 loop runs only under
`POST /api/v2/diagnose` and staging only under `POST /api/v2/remediate`. Conversational
entry means the **kernel's normal chat reply path** can, on a remediation-intent turn,
drive *diagnose → synthesize → propose → stage* in-process — i.e. the chat turn becomes a
**producer** of the orchestration frame rather than a single unscoped agent turn. This must
be **opt-in and intent-gated** (the unscoped single-agent chat path stays **byte-identical**
when no remediation is requested), and it reuses the delivered loop + staging mechanism
verbatim. Whether the entry is a model-selected tool the orchestrator calls, or an explicit
gateway route the portal calls on a remediation-intent message, is an implementation choice
for the spec's plan — both reach the same wired `stage_remediation`.

### 3.2 OQ-2 — Team-*proposal* vs. team-*execution* → **team-proposal**

**Recommendation:** the team **proposes**; a human **disposes**. The agent team
(`orchestrator` → read-only `diagnostician` fan-out → `executor`) produces *one proposed*
mutating action that stages onto the existing HITL card; a **distinct human** approver
resumes it; the **existing** signed at-most-one-dispatch worker (SPEC-037/038/063) alone
executes. The team never executes autonomously and no agent approves another agent's
mutation (ADR-0007; identity principle 5; SPEC-030 self-approval block — all unchanged).

This is the only option consistent with ADR-0017 Decision 2 as accepted. Team-*execution*
(autonomous resolve) is the Decision-2 revisit (§3.4) and stays **deferred**. Choosing
team-proposal means SPEC-078 adds **zero** new mutation-path machinery — it reuses
SPEC-077's `stage_remediation` exactly as delivered.

### 3.3 OQ-3 — The autonomy gradient → **fix the ceiling; deliver the conversational-propose rung**

The gradient is a *design axis the spec records*, not a ladder it fully ships. Recommended
rungs, from today's floor to the deferred ceiling:

| Rung | Shape | Mutation gate | Status for SPEC-078 |
|---|---|---|---|
| **R0** | Operator-initiated single staging turn (SPEC-077 `/remediate`) | one park, distinct-human approve | delivered (v0.58.0) |
| **R1** | **Conversational diagnose → propose → stage** (this spec) | one park, distinct-human approve | **deliver** |
| **R2** | Multi-step remediation *plan* (an ordered set of proposed mutations) | **each step individually** parked + approved | **named fast-follow after R1** (operator 2026-11-18) |
| **R3** | Autonomous resolve (team executes; no human approver) | none — self-approving loop | **deferred** (Decision-2 revisit, §3.4) |

**Recommendation:** SPEC-078 **delivers R1** and **fixes the ceiling at "every mutation is
human-approved."** R2 is a natural extension but must respect ADR-0011 — *a composition is
not a transaction; each mutating sub-skill keeps its own gate; declared order is guidance,
not enforcement* — so an R2 plan is N individually-parked proposals, **never** one
composite approval and **never** an automatic multi-dispatch. **Operator decision
(2026-11-18): R2 is a named fast-follow after R1 ships — not in v1**, keeping R1 the clean,
minimal, evidence-producing increment. R3 stays deferred.

### 3.4 OQ-4 — The ADR-0017 Decision-2 revisit → **do NOT revisit; stay under the ceiling**

**Recommendation: SPEC-078 does not move the diagnose-before-act ceiling, and no new ADR is
expected.** Decision 2 defers autonomous resolve "to a later, evidence-backed trust-model
decision," and ADR-0017's Consequences fix the revisit trigger: *"Autonomous resolve —
revisited only after bounded read-only diagnosis is proven in production."* That trigger is
**not met**: SPEC-076 (bounded diagnosis) shipped v0.57.0 and SPEC-077 (the trigger)
v0.58.0 only days ago; there is no production evidence base yet, and the dev-cluster e2e is
not "proven in production."

So SPEC-078 stays entirely **within** Decision 2: read-only diagnosis may run autonomously
(the SPEC-076 loop, already admitted by Decision 1), and every mutation parks for a distinct
human (Decision 2, unchanged). This mirrors SPEC-077's own stance ("**No new ADR is
expected**"). The autonomous-resolve trust-model decision (R3) remains a **separate future
ADR amendment + spec**, gated on production evidence — recorded here as the standing
promotion trigger, not opened.

### 3.5 OQ-5 — Making the `FU-076-c` policy axis live → **fold in as an *in-process* role-axis check (in v1)**

**Recommendation: make the SPEC-074 `agent_roles_any` axis fire *in-process* at the
executor-staging seam, and fold `FU-076-c` into SPEC-078 v1** (operator-confirmed
2026-11-18), as a requirement conditioned on staying in-process (role off the wire).

- **Why here.** SPEC-078 is the first flow where **multiple bound roles compose on a
  mutation-adjacent path** (orchestrator/diagnostician read-only, executor proposing a
  write). That is precisely when role-differentiated policy becomes meaningful: "an
  `executor` may stage `k8s.delete_pod`; a `diagnostician` may not" is a real rule rather
  than an inert one.
- **How, without breaking R-3.** The role stays **off every wire field** (SPEC-073 R-3 is
  load-bearing and unchanged). The axis fires at an **in-process** policy-evaluation point
  in the kernel — which already knows the bound role from the `AGENT_ROLE` contextvar —
  *complementary to* (not replacing) the tool-gateway's deny-by-default `evaluate()`. This
  is exactly what `FU-076-c` named: "a live in-process policy-evaluation point that would
  make the SPEC-074 `agent_roles_any` axis fire where R-3 keeps the role."
- **Why it is safe to fold into v1 (operator decision 2026-11-18).** The HITL park +
  in-process toolkit narrowing **already** enforce the ceiling without the axis live
  (SPEC-077 OQ-6 ratified this), so the axis-live check adds *defense-in-depth and
  audit-meaningful role policy*, not the primary control — it cannot weaken the ceiling. The
  condition is that it stays cleanly **in-process** (role off the wire, R-3 preserved): if
  implementation grounding finds it cannot fire without a wire change, it reverts to deferred
  rather than breaking R-3.

## 4. Recommended SPEC-078 shape

**Title (proposed):** *SPEC-078: Conversational Agentic Remediation (composing the
delivered diagnosis loop + staging trigger into a human-requested, team-proposed,
human-approved flow).*

**Delivers (R1):**
- A conversational remediation flow: on a remediation-intent chat turn, the kernel drives
  the **delivered** SPEC-076 bounded read-only diagnosis loop, synthesizes a diagnosis +
  *proposed* remediation, and the **delivered** SPEC-077 `executor` `stage_remediation(...)`
  stages it onto the **existing** HITL card — all surfaced through the existing chat SSE
  stream (`TurnStreamer`) and the existing confirmation card / approval inbox
  (`ConfirmationCoordinator`).
- The autonomy-gradient framing (§3.3) recorded as binding: ceiling = every mutation
  human-approved; R3 autonomous resolve deferred.
- The in-process `agent_roles_any` evaluation point making the SPEC-074 axis live on the
  staging path (`FU-076-c`, **folded into v1**; §3.5) — conditioned on staying in-process
  (role off the wire, R-3 preserved).

**Reuses verbatim (no change):** the SPEC-076 loop + `AGENT_ORCHESTRATION_MAX_STEPS`
budget; SPEC-077 `stage_remediation` + `remediate:stage` action; SPEC-020/030/031 HITL park
+ self-approval block; SPEC-037/038/063 signed at-most-one-dispatch; SPEC-075 audit
attribution; the two stageable profiles.

**Invariants held byte-identical:** the unscoped single-agent chat path (no role bound
outside a remediation flow); `agent_role` off every wire field (SPEC-073 R-3);
`agent-stream-event.schema.json` + `execution-request.schema.json` byte-unchanged (no
phase-6 dependency); the `event_type` enum closed; the deployed gateway `evaluate()`
contract unchanged.

**Likely target version:** a MINOR bump over v0.59.0 (a new operator-facing capability),
per the SPEC-070…077 release-train pattern — pinned only on approval.

## 5. Four-point gate + trust-model check (SPEC-018 / ADR-0017)

| Gate point | SPEC-078 posture |
|---|---|
| 1. Deny-by-default policy + audit; tool-gateway the only execution surface | **Holds** — reads ride the gateway as in SPEC-076; the mutation rides the existing gated path; every role action is attributable (SPEC-075). The in-process axis (§3.5) *adds* a check; it removes none. |
| 2. Identity via the gateway-forwarded delegated token only | **Holds** — the team runs on the *same* delegated token, narrowed per role (ADR-0017 Decision 4); no second identity edge; role off the wire. |
| 3. Read-only / bounded-autonomy posture | **Holds** — autonomy is bounded to *read-only* diagnosis (Decision 1); every mutation parks for a distinct human (Decision 2, unchanged). |
| 4. No agentscope types through the v2 contract | **Holds** — single-voice projection through existing frames; no `TeamPipeline`/`GoalPipeline`/`A2AAgent` (Decision 5); schemas byte-unchanged. |

**Trust model:** unchanged. No agent approves another agent's mutation; the approver is a
distinct human; at-most-one signed dispatch; no automatic retry; no composite transaction.

## 6. Non-Goals (recommended for the spec)

- **Autonomous resolve / auto-dispatch (R3).** Deferred behind the ADR-0017 Decision-2
  revisit trigger (production-proven bounded diagnosis + a new trust-model ADR).
- **Multi-step remediation plans (R2).** A named **fast-follow after R1 ships** (operator
  2026-11-18), not in v1; when built it stays N *individually*-gated proposals (ADR-0011 —
  a composition is not a transaction), never a composite approval or automatic multi-dispatch.
- **Unattended machine-trigger ingestion** (webhook/alert auto-fire, dedup, storm control) —
  that is `FU-076`, a separate future spec; SPEC-078 stays **human-requested**.
- **The phase-6 v2 multi-agent wire contract.** Existing frames only; member attribution
  rides SPEC-075 audit, not a new stream frame.
- **A portal diagnosis card / Stage-remediation button.** Explicitly rejected by the
  operator's direction; the entry is conversational.
- **New mutation-path machinery** — no new gate, worker, claim type, dispatch path, or schema.
- **New runbooks or widening `remediation_shape`** — the two stageable profiles ship as
  declared; diagnosis-only profiles stay diagnosis-only and fail closed.
- **A2A / external federation** — parked by ADR-0017 Decision 5.

## 7. Go / no-go and next decision

- **Go — for a `draft` SPEC-078**, on operator approval. The five deferred OQs are resolved
  with recommendations (§3); the spec composes delivered machinery, holds the four-point
  gate and the Decision-2 ceiling, and needs **no new ADR**. It is decision-complete enough
  to draft.
- **No implementation is authorized by this memo.** Per SDD discipline, promotion to
  `draft` (then the OQ ratification → `approved` → plan/tasks authoring) is the operator's
  call; approval authorizes implementation to *begin*, not to merge, commit/push, deploy, or
  version-bump (each a separate gate).
- **The autonomous-resolve trust-model decision stays closed** until its ADR-0017 trigger is
  met; this memo records the trigger, it does not open it.

## 8. Ratification record — operator review 2026-11-18

The operator reviewed the memo, **approved all five resolutions as recommended**, and settled
the two scope forks:

1. **Entry shape (§3.1):** ✅ **conversational entry** (chat turn → the existing card for the
   park), no diagnosis card / button.
2. **Proposal vs execution (§3.2):** ✅ **team-proposal** — human-approved every mutation;
   autonomous resolve deferred.
3. **Autonomy-gradient scope (§3.3):** ✅ **R2 (multi-step plan) is a named fast-follow after
   R1** — not in v1.
4. **`FU-076-c` (§3.5):** ✅ **folded into v1** as an in-process role-axis check, conditioned
   on staying in-process (role off the wire, R-3 preserved).
5. **No new ADR (§3.4):** ✅ SPEC-078 stays under the Decision-2 ceiling; the
   autonomous-resolve revisit remains gated on production evidence.

With these settled the memo is **decision-complete**; the next gate is authoring `draft`
SPEC-078 (§7).

## Changelog

- 2026-11-18: initial design exploration. Resolved the five `FU-077-agentic-remediation`
  Open Questions deferred out of SPEC-077, against the delivered foundation (ADR-0017;
  SPEC-073/074/075/076/077) at v0.59.0 (`e4779bae`). Recommended: conversational entry;
  team-proposal (not execution); fix the autonomy ceiling at human-approved-every-mutation
  and deliver the conversational-propose rung; **no** ADR-0017 Decision-2 revisit (no new
  ADR); fold `FU-076-c` in as a separable in-process role-axis check. Recorded the
  four-point-gate posture, the byte-identical invariants, non-goals, and the ratification
  asks. Assessment only: no runtime change, no ADR opened, no SPEC number assigned, no
  implementation, no deployment.
- 2026-11-18 (operator review): the operator approved all five resolutions **as recommended**
  and settled the two scope forks — **R2 multi-step plans → a named fast-follow after R1**
  (not in v1); **`FU-076-c` in-process role axis → folded into v1** (conditioned on staying
  in-process, role off the wire). §8 converted from ratification *asks* to a ratification
  *record*; §1/§3.3/§3.5/§4/§6 updated to match. The memo is now decision-complete and ready
  to promote to `draft` SPEC-078. Still assessment only: no SPEC number assigned, no ADR
  opened, no implementation, no deployment.
