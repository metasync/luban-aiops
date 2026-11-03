# ADR-0017: Bounded Read-Only Multi-Agent Orchestration; Composition Keeps No Mutation Authority

## Status

`accepted`

- date: 2026-11-01
- accepted: 2026-11-03
- deciders: workspace operator — the three load-bearing decisions (control-flow **option b**
  bounded read-only loop; **diagnose-before-act** autonomy ceiling with autonomous resolve
  deferred; role-scoped agents on the **same delegated token, narrowed per role**) were
  ratified 2026-11-01. **Accepted 2026-11-03** on the operator's review pass, mirroring
  SPEC-071's draft→approved flow. Acceptance ratifies the architecture and unblocks drafting
  the phased SPEC series ([memo](../workspace/multi-agent-orchestration-spike.md) §7),
  beginning with role-scoped identity & authority (§4.1); it authorizes no runtime code,
  deployment, commit/push, version bump, or SPEC number on its own — the operator separately
  directed opening that first spec (SPEC-073).
- related specs: the phased series the [memo](../workspace/multi-agent-orchestration-spike.md)
  §7 sketches (not yet numbered) — role-scoped identity & authority, policy role axis,
  multi-agent audit & attribution, bounded autonomous diagnosis, v2 multi-agent contract;
  reconciles with [SPEC-064](../specs/SPEC-064-agentscope-compression-and-goal-pipeline/spec.md)
  (the `GoalPipeline` reopen trigger this meets), SPEC-057, SPEC-020/030/031 (HITL),
  SPEC-037/038/063 (signed at-most-one-dispatch), and SPEC-018 (the four-point adoption gate).
- **extends and amends [ADR-0011](0011-composition-carries-no-authority.md), Decision 3 only** —
  ADR-0011 stays `accepted` and its body is unchanged (per the ADR immutability rule). Reconciles
  with ADR-0002/0003/0004/0007/0010/0013/0015/0016, which all stay in force.
- evidence: [multi-agent-orchestration-spike.md](../workspace/multi-agent-orchestration-spike.md)
  (2026-11-01) — scored `TeamPipeline`, `A2AAgent`, and `GoalPipeline` against SPEC-018's
  four-point gate from static inspection of the locked agentscope 2.0.11 install at v0.51.1.

## Context

The operator named a multi-agent / segregation-of-duty / bounded-autonomy need — autonomous
detect→troubleshoot→resolve and incident-driven diagnose→resolve, with **role-scoped agents of
different system access rather than one super-agent**. That need is exactly the reopen trigger
SPEC-064 R-1 recorded for `GoalPipeline` ("a concrete autonomous-remediation product need"), so
it is now live.

agentscope 2.0.11 ships orchestration surfaces (`TeamPipeline`, `A2AAgent`, `pipeline.GoalPipeline`),
but the memo scores all three as failing **all four** gate points as shipped, and each embodies
the interpreter ADR-0011 rejected. The blocker is ADR-0011 **Decision 3** — "No control flow. No
branch, loop, conditional or early exit — sequencing and validation only." Its rationale is that
"an interpreter needs loops, and a loop defeats `GATEWAY_BROWSER_FLOW_MAX_STEPS`, currently the
only bound on an unlocked flow." That rationale is about **mutating** flows: the platform has no
admissible control-flow model for autonomous multi-step *read-only* diagnosis. What needs
deciding is therefore not whether to adopt a surface, but what control flow the platform itself
admits, and under what autonomy ceiling and identity model.

## Decision

Admit a **bounded platform orchestration loop for read-only diagnosis only**, under a
**diagnose-before-act** ceiling, with **role-scoped agents on the same delegated token narrowed
per role** — while composition continues to carry **no mutation authority**.

1. **Bounded read-only orchestration loop (control-flow option b).** An orchestrator may fan out
   read-only sub-agents (observability, k8s, ServiceNow, log reads) and synthesize a diagnosis
   **autonomously, with no human in the loop**, because a read cannot cause harm and every read
   still rides the tool-gateway's deny-by-default policy, redaction, evidence, and audit. The loop
   is **bounded** by an iteration/step budget mirroring the `GATEWAY_BROWSER_FLOW_MAX_STEPS`
   discipline — this is the controlled relaxation of ADR-0011 Decision 3, and it applies **only**
   where every step is read-only.
2. **Diagnose-before-act autonomy ceiling.** Every mutation (write / execute / remediate) parks on
   the existing HITL confirmation (SPEC-020/030/031) and, once approved, dispatches through the
   signed at-most-one-dispatch worker (SPEC-037/038/063). **No agent may approve another agent's
   mutation** — the approver stays a distinct human (ADR-0007's one-HITL-gate-per-mutating-flow;
   identity design principle 5). **Autonomous resolve** (closing the loop without a human
   approver) is **explicitly deferred** to a later, evidence-backed trust-model decision.
3. **Composition keeps no mutation authority (ADR-0011 amended at Decision 3 only).** ADR-0011
   Decisions 1, 2, 4, and 6 stay in force: a composition carries no authority of its own; each
   mutating sub-skill keeps its own gate; a composition is not a transaction (no rollback); and a
   declared order is guidance, not enforcement, on the mutation path. The relaxation here is
   confined to admitting a bounded **read-only** loop; it grants no composite-level mutation gate.
4. **Role-scoped agents on the same delegated token, narrowed per role — not a super-agent, not
   per-role broker identities.** Authority is narrowed per role at the **toolkit + policy** layer;
   each role's actions are attributed in audit. Roles: **`diagnostician`** (read-only toolkit; may
   run autonomously; may not propose mutations), **`planner`/`orchestrator`** (decomposes an
   incident, delegates to read-only roles, synthesizes a diagnosis and a *proposed* remediation;
   holds no mutation authority itself), and **`executor`** (may *stage* a mutation as a
   confirmation card, but a **human** approves and the isolated worker dispatches; it cannot
   self-approve). This is segregation of duty *within* the existing gate model, preserving the
   single gateway-forwarded delegated-token identity edge (gate point 2).
5. **No agentscope orchestration surface is adopted as shipped; A2A stays parked.** The platform
   builds its own bounded orchestration under this ADR rather than wiring `TeamPipeline` /
   `GoalPipeline` (an ungoverned second edge). **A2A external federation is parked** — no `a2a`
   extra is installed and no concrete federation use case is named; it is revisited only behind an
   outbound-identity decision (ADR-0015/0016) if a real peer-to-peer need arises, and then only
   ever as a read-only consultant.
6. **The v2 contract change is additive, versioned, and last.** Any multi-agent stream/schema
   extension (member attribution, orchestration status) is additive, versioned, and specified only
   **after** the identity / policy / audit / orchestration semantics are fixed by the downstream
   SPECs. This ADR changes no contract; `agent-stream-event.schema.json` is untouched.

## Alternatives Considered

- **Control-flow option a — model-driven delegation only, no platform loop** — considered and not
  selected: closest to today and the smallest substrate change, but the model must drive every step
  via tool calls with no bounded platform orchestration, which under-delivers the named autonomous
  detect→troubleshoot value. The operator chose the bounded read-only loop.
- **Control-flow option c — a general orchestration engine / interpreter** — rejected: the largest
  substrate change, hardest to govern under the four-point gate, and precisely the "interpreter
  executing the composition" ADR-0011 rejected; a general engine admits unbounded **mutating** loops.
- **Adopt `TeamPipeline` / `GoalPipeline` as shipped** — rejected: all fail all four gate points
  (`TeamAssign` is `is_read_only=False`; the leader sees only member summaries; per-participant HITL
  parking is not the platform's gate; `GoalPipeline`'s executor-until-verifier loop is autonomous
  multi-step execution outside the governed dispatch path).
- **Distinct broker-mediated identity per role** — rejected for this phase: stronger segregation but
  materially more identity machinery; the same-token-narrowed model preserves the single identity
  edge and is sufficient for read-only diagnosis. Revisit only if a role needs an independent credential.
- **Autonomous resolve in phase 1** — rejected: a self-approving mutation loop is a separate
  trust-model change requiring its own gate and evidence; deferred until bounded diagnosis is proven.

## Consequences

- **Unblocks the multi-agent program as a planning go.** This ADR is the gate for everything
  downstream; on acceptance, the phased SPEC series (memo §7) can be drafted in order — (2)
  role-scoped identity & authority, (3) policy role axis, (4) multi-agent audit & attribution,
  (5) bounded autonomous diagnosis, (6) v2 multi-agent contract — each still passing the four-point
  gate on its own terms.
- **The governed mutation path is unchanged.** Because only Decision 3's read-only case is relaxed,
  SPEC-037/038/063 dispatch, SPEC-020/030/031 HITL, ADR-0007's one-gate-per-mutating-flow, and
  ADR-0010/0013 provenance/durable-claim invariants all remain authoritative.
- **Accepted trade-off — new machinery.** A bounded read-only loop needs its own iteration/step
  budget and a per-role toolkit + policy narrowing mechanism; these are the downstream SPECs'
  subject and are not free.
- **Accepted trade-off — unattended read spend.** Read-only autonomy consumes model/tool budget with
  no human in the loop; the step bound and the read-only posture are the safety argument, and each
  read still rides policy / redaction / evidence / audit.
- **Deferred with named triggers.** Autonomous resolve — revisited only after bounded read-only
  diagnosis is proven in production. A2A federation — revisited only on a named use case plus an
  outbound-identity decision.
- **Open for the first bounded-autonomy SPEC, not this ADR.** The **first concrete incident
  workflow** (memo §8 Q5) that drives the role/toolkit split from a real runbook rather than a
  speculative one is named when SPEC (5) is drafted; this ADR fixes the control-flow *model*, not
  the first workflow.
- No runtime change, deployment, commit/push, version bump, or SPEC number for the downstream series
  is authorized by writing this proposal.
