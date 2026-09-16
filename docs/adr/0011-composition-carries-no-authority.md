# ADR-0011: A Composition Carries No Authority; Each Sub-Skill Keeps Its Own Gate

## Status

`accepted`

- date: 2026-09-16
- accepted: 2026-09-16
- deciders: workspace maintainers
- related specs: SPEC-057 (multi-target composition — roadmap row 346 blocks its
  promotion on this decision), SPEC-056 (Studio — confirmed skills stay
  single-target, `spec.md:403-404`), SPEC-055 (develop-as-you-go graduation —
  R-4 blast-radius re-validation is single-target by construction), SPEC-054
  (action-level approval — R-2 governs the unbound and infra per-action legs),
  SPEC-051 (browser flow HITL gate — the identity guard this relies on);
  **extends ADR-0007, which stays `accepted` and unedited**
- evidence: `docs/workspace/composition-trust-model-spike.md` (2026-09-16)

## Context

Skills are single-target: SPEC-055 R-4 re-validates every step's observed
origin against the one target declared *before* mutating, so a multi-target
operation trace cannot graduate. Multi-target *workflows* therefore need a
composition construct sequencing single-target skills, and roadmap row 346
blocks its promotion on one question — does a composite need its own gate, or
does each sub-skill keep its own?

The platform already answers it, though not in those words:

- `FlowContext.identity()` returns `(skill_id, origin)`
  (`flow_approvals.py:102-104`), and `FLOW_CONTEXTS` is keyed by `session_id`,
  so a session holds exactly one flow context.
- ADR-0007's Decision admits subsequent write-tier browser calls "only while
  the session remains bound to that same flow — a rebind to a different flow
  re-parks".
- `flow_approvals.py:16-21` names that re-park as the mechanism which
  **eliminates** the ADR-0007 cross-flow trade-off rather than merely bounding
  it.

A composite navigating into its next sub-skill therefore re-parks with no
composition-aware code. There is also no interpreter to sequence anything:
`FlowState` declares no `kind` and no `steps`, `steps[].expect` is a
display/replay aid and never a security input, and the deviation guard reads
the origin allowlist, declared `risk_class` and step budget only — never
element semantics.

What needs deciding is therefore not whether per-sub-skill gating works, but
whether to add composite-level authority on top of it, and what a composition
may contain.

## Decision

1. **A composition carries no authority of its own.** Each referenced sub-skill
   keeps its own gate: browser legs get one gate per binding through the
   existing identity guard, infra legs park per-action under SPEC-054 R-2. Gate
   count equals the number of distinct assessable decisions a run encounters —
   never one per composite.
2. **A composition is a declarative, ordered list of sub-skill references**,
   validated at ingestion: every reference resolves to a published skill that
   is single-target and declares its target, and no sub-skill appears twice.
3. **No control flow.** No branch, loop, conditional or early exit — sequencing
   and validation only.
4. **A composition is not a transaction.** There is no rollback. On partial
   failure the agent reports where it stopped and does not continue; re-entry
   starts from a named step, with the completed prefix derived from existing
   `execution_records` signed receipts rather than from new composite state.
5. **Mixed browser+infra composites are allowed**; neither leg depends on the
   other's gate semantics.
6. A composition's declared order is **guidance, not enforcement** — the same
   standing `steps[].expect` has. Enforcement remains with the gateway
   deviation guard and the identity guard.

## Alternatives Considered

- **composite-level gate** (one approval covering the whole runbook) — rejected:
  requires a multi-identity authority store, which is precisely the cross-flow
  posture ADR-0007 closed, so it is a regression against an accepted decision
  rather than a neutral alternative; one card cannot present N sub-skills'
  worth of assessable content; and SPEC-055 R-4 cannot re-validate a
  multi-target unit.
- **prose-only runbook** with no structured list — rejected: nothing to validate
  at ingestion, no way to check that a named sub-skill exists, is published and
  is single-target, and no basis for re-entry from a named step.
- **an interpreter executing the composition** — rejected: an interpreter needs
  loops, and a loop defeats `GATEWAY_BROWSER_FLOW_MAX_STEPS`, currently the only
  bound on an unlocked flow; no interpreter substrate exists today, so this is a
  substrate change rather than a feature.
- **generalizing browser flow binding to infra** so composite infra legs
  collapse to one gate — rejected: infra arguments are self-describing
  (`k8s.delete_pod` names its pod and namespace), so binding would replace N
  assessable cards with one carrying strictly less information. This also
  reframes roadmap row 347, whose premise is the wrong fix.

## Consequences

- Composition needs **no new enforcement machinery**: the identity guard
  supplies the gate boundaries for free, and ADR-0007's invariant is
  strengthened rather than traded away.
- The per-sub-skill signed receipts already in `execution_records` give the
  audit trail and the re-entry substrate without a new store.
- **Accepted trade-off — no composite-wide write bound.** The step budget is
  per bound flow, so N sub-skills bring N budgets and a long runbook has no
  total bound. This is the one real hole the decision leaves. It is deferred to
  SPEC-057 (memo OQ-1) rather than decided here, with the recommendation to
  bound it at ingestion via sub-skill count, consistent with Decision 3's
  no-control-flow stance; a kernel-side composite counter is the alternative.
- **Accepted trade-off — N gates for an N-step runbook** is a real operator
  cost. Collapsing them would reduce what the operator can assess, so the cost
  is accepted. If gate volume becomes the binding constraint, the fix is tool
  granularity (a tool matching the operator's decision unit), not gate
  collapsing.
- Follow-up work: draft **SPEC-057** scoped to Phase 1 (the composition
  construct, its ingestion validation, and per-step re-entry), with Phase 2
  (the "Continue in Studio" spawn bridge and assisted trace-extraction)
  deferred behind it; **rewrite roadmap row 347** from flow-binding
  generalization to infra tool granularity, keeping its existing promotion
  trigger; and record the sample-suite coverage hole that leaves `web.select`
  and `web.upload_file` undemonstrable (memo OQ-4).
