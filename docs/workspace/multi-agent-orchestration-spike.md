# Spike: Multi-Agent Orchestration & Bounded Autonomy — Architecture Exploration

Status: exploration / framing only (2026-11-01). This memo records the operator's
named multi-agent need, scores the three candidate agentscope surfaces
(`TeamPipeline`, `A2AAgent`, `GoalPipeline`) against SPEC-018's four-point
adoption gate, and lays out the architecture dimensions and a proposed ADR → SPEC
path. It authorizes **no** runtime change, **no** ADR, **no** SPEC number, and
**no** implementation. All three surfaces remain **kept out** until a superseding
ADR is accepted.
Date: 2026-11-01
Roadmap home: [Exploration Backlog](../agentic-aiops-platform/delivery-roadmap.md#exploration-backlog) — the "Multi-agent orchestration & bounded autonomy" row
Audit home: [agentscope-utilization-audit.md §2](agentscope-utilization-audit.md) — the `TeamPipeline`, `A2AAgent`, and `pipeline`/`GoalPipeline` rows
Reopens: the `GoalPipeline` reopen condition recorded in [SPEC-064 R-1 §3.4](agentscope-compression-goal-pipeline-spike.md)
Evidence baseline: repository at 0.51.1 (`c4214cf`); static inspection of the locked
agentscope 2.0.11 install
(`products/agent-platform/.venv/lib/python3.12/site-packages/agentscope/`) —
`pipeline/_team_pipeline.py`, `pipeline/_goal_pipeline.py`, `agent/_a2a_agent.py`,
`state/_a2a_state.py`. No agent was run, no pipeline was executed, the `a2a` extra
is **not** installed, and nothing was deployed.

## 1. Question and framing

> Luban today is a single kernel agent per session plus gateway-forwarded tools.
> The operator has named a concrete forward need: move toward **multi-agent
> orchestration** for autonomous *detect → troubleshoot → resolve* and for
> incident-driven *diagnose → resolve*, under **segregation of duty** — several
> role-scoped agents holding *different* access to *different* systems, not one
> super-agent that can reach everything. Intra-Luban orchestration and federation
> with external agent systems (A2A) are both in scope. What does this require, and
> do the agentscope surfaces fit?

This is exactly the reopen trigger SPEC-064 R-1 §3.4 recorded for `GoalPipeline` —
"a concrete autonomous-remediation product need." The need is now named, so the
question is legitimately reopened. The finding, however, is that the need is real
and worth pursuing **but is a substrate change, not a feature**: it cannot be met
by wiring an agentscope pipeline, because (a) every candidate surface fails the
four-point gate as shipped (§3), and (b) the platform's governing decision
(ADR-0011) explicitly forbids the control flow those surfaces embody and already
classified an executing orchestration interpreter as "a substrate change rather
than a feature." The correct next step is therefore an **architecture decision**
(a superseding ADR), then a phased SPEC series — not a library adoption.

Recommendation summary:

- **Do not adopt `TeamPipeline`, `A2AAgent`, or `GoalPipeline` now.** All three
  remain kept out (§3.4).
- **Pursue the need as a bounded-autonomy program** scoped to *diagnose-before-act*:
  agents may orchestrate **read-only** diagnosis autonomously, while **every
  mutation stays behind the existing HITL gate and the signed at-most-one-dispatch
  path** (SPEC-020/030/031/037/038/063). Autonomous *resolve* — mutation with no
  human approver — is a separate, later trust-model decision (§5).
- **Open a superseding ADR to ADR-0011** deciding whether and where platform-side
  control flow is admissible, reconciled with ADR-0002/0003/0004/0007/0010/0013/
  0015/0016 (§7).
- **Treat the five architecture dimensions in §4 as the "additional preparation"**
  the operator anticipated: each is a prerequisite that must be decided before any
  orchestration SPEC can be decision-complete.

The four gate points (SPEC-018), restated: (1) deny-by-default policy + audit
preserved, tool-gateway the only execution surface; (2) identity carried only by
the gateway-forwarded delegated token; (3) read-only operational posture; (4) no
agentscope types leak through the platform-owned v2 contract.

## 2. Why this is a substrate change, not a feature

ADR-0011 ("a composition carries no authority; each sub-skill keeps its own gate")
is the pivot. Its Decision 3 is **"No control flow"** — the platform provides no
interpreter, no branch/loop/conditional, no early exit; a composition is *grounded
guidance the model reads*, not a program the platform executes (Decision 6,
"guidance, not enforcement"). Its Alternatives Considered explicitly rejects "an
interpreter executing the composition," noting an interpreter needs loops and that
"no interpreter substrate exists today, so this is a **substrate change rather than
a feature**."

Every multi-agent surface below is, mechanically, that rejected interpreter: a
platform-owned loop that sequences agents, routes results, and retries. Adopting
one does not add a capability *within* the current architecture — it replaces the
"no control flow" invariant with an orchestration engine. That is why the change
must be decided at the ADR tier (which can supersede ADR-0011 with a recorded
rationale), not slipped in as a middleware or a spec requirement.

Two further invariants make this more than a kernel change:

- **One governed execution path.** SPEC-037/038/063 (and ADR-0010/0013) give the
  platform exactly one dispatched-mutation path: a signed envelope, a durable
  single-use claim, at-most-one dispatch, no automatic retry. A multi-agent loop
  that "keeps going until the goal is verified" is a second, autonomous driver
  beside that path.
- **One identity edge.** ADR-0004 + SPEC-070/ADR-0015/0016 carry identity as a
  gateway-forwarded, per-user delegated token. "Different roles, different system
  access" (§6) means *per-agent* authority — several distinct identity/toolkit
  surfaces where the gate assumes one.

## 3. Candidate surfaces — evidence and gate scoring

### 3.1 `TeamPipeline` (leader → concurrent members)

`TeamPipeline(leader: Agent, members: list[TeamMember], reset_members=True)`
(`pipeline/_team_pipeline.py`). A `TeamMember` is "an existing agent plus the
description the leader reads to decide when to assign a task to it." The leader is
given one external tool, `TeamAssign` (`is_external_tool=True`,
`is_concurrency_safe=True`, **`is_read_only=False`**), whose input is
`{member: <enum of member names>, prompt: <the complete task>}`. Per the class
docstring:

- "the pipeline runs that member **in its own context** and feeds its final reply
  back as the tool result, so the leader **only ever sees the summary, never the
  member's intermediate steps**";
- "Members assigned in the same round **run concurrently**"; "Members do not talk
  to each other; a member's result always returns to the leader";
- "**HITL works per participant**: a member that needs user confirmation parks like
  any agent, **its request is streamed out unchanged**, and the result … is routed
  to it by `reply_id`. Meanwhile the leader stays parked on the assignment."

Two consequences for Luban are immediate. (a) *Audit:* if the leader "never sees
the member's intermediate steps," a naive adoption would put the member's tool
calls **outside the leader's transcript** — they must instead land in the same
governed evidence/audit records (SPEC-025 `session_evidence`, SPEC-039 transcript,
the closed `event_type` enum) attributed to the member role. (b) *Contract:* "HITL
works per participant … streamed out unchanged" means **multiple agents can park
and emit concurrently**, while the v2 SSE contract and
`agent-stream-event.schema.json` model **one agent's turn**.

### 3.2 `A2AAgent` (federation with a remote peer)

`A2AAgent(agent_card, *, client=None, state=None)` (`agent/_a2a_agent.py`) is
"a stateful **client-side adapter** for an A2A 1.0 agent" that "intentionally
provides Agent-like interaction methods **without inheriting `Agent`**." A local
`Agent` "owns a model, toolkit, state, and reasoning loop; this adapter
**delegates those concerns to the remote A2A server** and owns only the remote
conversation (`context_id`) and the Task the next message continues (`task_id`)."
It requires the `a2a` extra (`pip install 'agentscope[a2a]'`) — **not installed** —
and builds a streaming `JSONRPC`/`HTTP+JSON` client from the peer's `AgentCard`.
A remote Task may be `TASK_STATE_AUTH_REQUIRED`.

The governance problem is structural: because the remote peer owns its own model,
**toolkit**, state, and reasoning loop, Luban **cannot enforce the four-point gate
on it** — tool-gateway-only execution, delegated-token identity, and the read-only
posture are all properties of *Luban's* kernel, and a remote agent is outside that
boundary. `AUTH_REQUIRED` also implies an **outbound** trust/authorization edge to
a third-party agent, beside (not inside) SPEC-070/ADR-0015/0016.

### 3.3 `GoalPipeline` (executor-until-verifier)

Unchanged from the SPEC-064 R-1 assessment: `GoalPipeline(executor, verifier,
max_iters=10, max_retries=3)` runs two full `Agent` instances in a `while True`
retry/feedback loop until the verifier passes
(`pipeline/_goal_pipeline.py`; see [SPEC-064 R-1 §3](agentscope-compression-goal-pipeline-spike.md)).
It is the purest form of the ADR-0011-rejected interpreter. This memo does not
re-score it; it records that the reopen trigger is now met and that the reopen
belongs to the ADR decision in §7, not to a wiring change.

### 3.4 Gate scoring (all three surfaces, as shipped)

| Gate point | `TeamPipeline` | `A2AAgent` | `GoalPipeline` |
|---|---|---|---|
| 1. Policy + audit; tool-gateway the only execution surface | **Fail** — a platform-owned leader loop is a second orchestration edge; `TeamAssign` is `is_read_only=False`; member tool calls fall outside the leader's transcript unless re-attributed into SPEC-025/039 | **Fail** — the remote peer's toolkit is not the tool-gateway; Luban cannot apply deny-by-default policy to a server it does not own | **Fail** — autonomous retry loop is a second orchestration edge (SPEC-064 R-1) |
| 2. Identity via the delegated token only | **Fail** — leader + N members = N+1 identity/toolkit surfaces; per-role authority has no mapped edge today | **Fail** — a remote peer needs its own outbound auth (`AUTH_REQUIRED`), a new trust edge beside SPEC-070 | **Fail (unmapped)** — executor + verifier expand the identity/toolkit surface |
| 3. Read-only / bounded-autonomy posture | **Fail** — concurrent autonomous members are materially more autonomous than operator-driven, one-turn-at-a-time HITL | **Fail** — the remote peer's posture is unknown and unenforceable | **Fail** — an executor that autonomously retries toward a goal |
| 4. No agentscope types through the v2 contract | **Fail** — per-participant parking/streaming means several agents emit at once vs the single-turn v2 frame | **Fail** — remote Parts become `TextBlock`/`DataBlock` and a remote Task lifecycle the v2 contract does not model | **Fail** — interleaved executor+verifier event stream vs the single-turn v2 frame |

All three fail all four points **as shipped**. None has a governed platform caller
today. This is a keep-out, not a "configure it differently" — the gaps are
architectural (§4), not knobs.

## 4. The five architecture dimensions (the "additional preparation")

The operator's instinct that "we might need additional preparation and development"
is correct and concrete. These five dimensions are the preparation; each must be
decided (mostly at the ADR tier) before an orchestration SPEC is decision-complete.

### 4.1 Identity & authority — segregation of duty

Today: one kernel agent per session, a per-token cached gateway toolkit, identity
read from the `DELEGATED_TOKEN` contextvar at call time (ADR-0004; SPEC-070 /
ADR-0015/0016 for outbound). Segregation of duty requires **role-scoped agents**,
each with its **own** toolkit subset and its **own** authority — e.g. a
`diagnostician` (read-only across observability/k8s/ServiceNow), an
`executor` (may *propose* mutations, never self-approve), an `approver`-facing
surface. The design must answer: does each role ride the *same* delegated user
token with a narrowed scope, or a distinct broker-mediated identity (ADR-0004)?
How is "on whose behalf" preserved end-to-end when a leader delegates to a member?
The [identity design](../agentic-aiops-platform/identity-and-authorization-design.md)
principles (a human owner; a *distinct* human approver) and ADR-0010 (an envelope
declares its authority provenance) are the constraints any answer must satisfy.

### 4.2 Policy — a new agent-role dimension

The tool-gateway's deny-by-default policy decides per (identity, tool, arguments).
Multi-agent adds an **agent-role** dimension: the same tool may be allowed for the
`diagnostician` and denied for a `summarizer`, and a mutation proposed by an
`executor` must still require a *human* approver (never another agent). This must
land in the [authorization matrix](../agentic-aiops-platform/authorization-matrix.md)
and the policy-center model as an explicit role axis, not as per-agent ad-hoc rules.

### 4.3 Audit & attribution

The audit `event_type` enum is **closed** (22 values) and every event is attributed
to one session/actor. Multi-agent needs: which **role** acted, on whose **behalf**,
under which **delegation** — and member activity must be captured even though "the
leader only ever sees the summary" (§3.1). This likely extends the audit vocabulary
(a new dimension on existing events, or new event types) and the SPEC-025 evidence
/ SPEC-039 transcript model so a member's tool calls remain reconstructable.

### 4.4 Orchestration / control flow

The pivotal decision: **is any platform-side control flow admissible, and if so
what kind?** Options range from (a) keep ADR-0011 as-is and express "orchestration"
only as *model-driven* delegation the platform never sequences (the leader agent
choosing to call a sub-agent tool, exactly as it calls any tool — the closest fit
to today's architecture); to (b) admit a **bounded** platform loop for *read-only*
diagnosis only; to (c) admit a general orchestration engine (superseding ADR-0011
wholesale). This memo recommends starting at (a)/(b) (§5, §7). Whatever is chosen,
it must reconcile with SPEC-057 (composition carries no authority) and must not
create a second mutation driver beside SPEC-037/038/063.

### 4.5 The v2 contract — multi-agent framing

The v2 SSE contract and `agent-stream-event.schema.json` model one agent's turn and
one parked confirmation. Concurrent, per-participant parking (§3.1) needs either a
**single-voice** projection (the platform serializes member activity into the one
session stream, attributing each frame to a role) or a genuine multi-agent frame
model. Gate point 4 forbids leaking agentscope types either way; the
`agent-stream-event.schema.json` byte-stability invariant means any change is an
additive, versioned contract decision, not an in-place edit.

## 5. Bounded autonomy: diagnose-before-act

The safest first increment — and the one that matches the platform's existing
"diagnose before act" posture — is to let agents orchestrate **autonomously only
where they are read-only**, and to keep **every mutation** on the existing governed
path:

- **Autonomous (read-only):** detect/triage/diagnose — an orchestrator may fan out
  read-only sub-agents (query observability, k8s, ServiceNow, logs) and synthesize
  a diagnosis with no human in the loop, because a read cannot cause harm and each
  read still rides the tool-gateway's policy/redaction/evidence/audit.
- **Gated (any mutation):** every write/execute/remediate step **parks** on the
  existing HITL confirmation (SPEC-020/030/031) and, once approved, dispatches
  through the signed at-most-one-dispatch worker (SPEC-037/038/063). No agent may
  approve another agent's mutation — the approver stays a distinct human
  (identity design principle 5; ADR-0007's one-HITL-gate-per-mutating-flow).
- **Deferred (autonomous resolve):** closing the loop *without* a human approver is
  a **separate trust-model decision** to revisit only after bounded diagnosis is
  proven in production. It is explicitly **out of scope** for the first phase.

This framing lets the program deliver the operator's detect→troubleshoot→*propose*
value immediately while leaving the contentious autonomy question (self-approving
resolve) for a later, evidence-backed decision.

## 6. A segregation-of-duty model sketch

Concretely, the "different roles, different access" goal maps to role-scoped agents
over the *same* governed gateway, not to separate super-agents:

- **`diagnostician`** — read-only toolkit (observability/k8s/ServiceNow/log reads);
  may run autonomously; may not propose mutations.
- **`planner`/`orchestrator`** — decomposes an incident, delegates to read-only
  roles, synthesizes a diagnosis and a *proposed* remediation; holds no mutation
  authority itself.
- **`executor`** — may *stage* a mutation as a confirmation card, but the card must
  be approved by a **human** and dispatched by the isolated worker; the executor
  cannot self-approve.
- **external peer (A2A)** — only ever as a *read-only* consultant behind an
  outbound-identity decision, if a concrete federation use case is ever named.

Authority is narrowed per role at the **toolkit + policy** layer (§4.1/§4.2); each
role's actions are attributed in audit (§4.3). This is segregation of duty *within*
the existing gate model — the opposite of one super-agent holding every credential.

## 7. Proposed path: superseding ADR → phased SPEC series

1. **ADR (supersedes/extends ADR-0011):** decide the admissible control-flow model
   (§4.4), reconciled with ADR-0002/0003/0004/0007/0010/0013/0015/0016. This is the
   gating artifact; nothing downstream is decision-complete without it.
2. **SPEC — role-scoped identity & authority (§4.1):** how per-role agents carry
   narrowed authority on the delegated-token/broker model, with ADR-0010 provenance.
3. **SPEC — policy role axis (§4.2):** the agent-role dimension in the authorization
   matrix / policy-center.
4. **SPEC — multi-agent audit & attribution (§4.3):** the audit/evidence/transcript
   extensions, keeping member activity reconstructable.
5. **SPEC — bounded autonomous diagnosis (§5):** the read-only orchestration
   increment, mutations still on the SPEC-037/038/063 path.
6. **SPEC — v2 multi-agent contract (§4.5):** the additive, versioned stream/schema
   change, only once 1–5 fix the semantics.

Each SPEC still passes the four-point gate on its own terms; the ADR is what makes
gate point 1/3 satisfiable for orchestration at all.

## 8. Open questions for the operator

1. **Control-flow appetite (§4.4):** start at model-driven delegation only (option
   a — closest to today), or admit a bounded platform loop for read-only diagnosis
   (option b)? Option c (a general engine) is not recommended first.
2. **Autonomy ceiling (§5):** confirm the first phase is *diagnose-before-act* with
   every mutation human-approved, and autonomous resolve is explicitly deferred.
3. **Identity model (§4.1):** role-scoped agents on the *same* delegated user token
   with narrowed scope, or distinct broker-mediated identities per role?
4. **A2A scope (§3.2):** is external federation a near-term need, or should A2A stay
   parked until an intra-Luban multi-agent phase is proven? (No `a2a` extra is
   installed today.)
5. **First concrete incident workflow:** which single detect→troubleshoot→propose
   scenario should the first bounded-autonomy SPEC target, so the role/toolkit
   split is driven by a real runbook rather than a speculative one?

## 9. Go/no-go and next decision

- **`TeamPipeline` / `A2AAgent` / `GoalPipeline`: no-go / keep out** as shipped —
  all fail all four gate points (§3.4) and embody the ADR-0011-rejected interpreter
  (§2). No code, no wiring.
- **The multi-agent/bounded-autonomy program: go for *planning*** — the need is
  legitimate and now named (the SPEC-064 R-1 reopen trigger is met), so the correct
  next step is to open the §7 ADR, not to adopt a surface.
- **This memo is documentation-only.** It does not flip any audit row to "adopt,"
  change product code, open an ADR, assign a SPEC number, or authorize deployment.
  The operator decides whether to open the superseding ADR (§7 step 1); that ADR is
  the gate for everything downstream.

## Changelog

- 2026-11-01: initial exploration. Framed the operator's named multi-agent /
  segregation-of-duty / bounded-autonomy need as the SPEC-064 R-1 `GoalPipeline`
  reopen trigger; scored `TeamPipeline`, `A2AAgent`, and `GoalPipeline` against
  SPEC-018's four-point gate (all fail as shipped) from static inspection of the
  locked agentscope 2.0.11 install at 0.51.1 (`c4214cf`); laid out the five
  architecture dimensions, the diagnose-before-act scoping, a segregation-of-duty
  model sketch, and a superseding-ADR → phased-SPEC path. Assessment only: no
  runtime change, no ADR opened, no SPEC number, no implementation, no deployment.
