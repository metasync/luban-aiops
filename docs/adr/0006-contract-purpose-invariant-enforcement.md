# ADR-0006: Contract Purpose Restated — Invariant Enforcement, Not Framework Swappability

## Status

`accepted`

- date: 2026-08-19
- deciders: workspace maintainers
- related specs: SPEC-018 (kernel middleware alignment), ADR-0002, ADR-0003

## Context

ADR-0003 established the platform-owned agent-service contract and framed
its primary value as bounded framework swappability: if the kernel is
ever replaced (for example with `LangGraph`), the swap would be a
single-adapter change.

Post-SPEC-017 experience shows that framing was a weak premise:

- agentic frameworks differ most exactly where their value lives —
  interaction model, human-in-the-loop primitives, streaming semantics,
  state, and tool orchestration. A portable agent contract over those
  surfaces is leaky by nature; a real swap rewrites the integration layer
  regardless of how the contract is shaped.
- treating swappability as the design goal pushed the contract toward a
  minimal, frozen surface and the kernel integration toward hand-rolled
  interception (tool subclassing, per-request toolkit rebuilds, mid-flight
  toolkit mutation) instead of deep exploitation of supported surfaces.
  That is precisely the pattern SPEC-018 now remediates.
- the recurring friction is domain-level, not framework-level: every
  agentic kernel assumes a human on the line (permission ASK gates,
  confirmation events, interactive channels). In a headless enterprise
  deployment, the platform must answer in code every question the kernel
  would ask a human. That problem recurs identically under any framework,
  so it is the platform's to solve once, not a capability to inherit.

## Decision

The platform-owned agent-service contract exists to enforce platform
invariants — identity, deny-by-default policy, audit, structured
evidence, delegated-token carriage — around whichever kernel is adopted.
The kernel behind the boundary should be exploited deeply through its
supported surfaces (middleware, out-of-the-box components), subject to
the adoption gate defined in SPEC-018. Swappability is accepted as a
side effect of the boundary, not a design goal.

## Alternatives Considered

- remove the boundary and expose the kernel's native interaction surfaces
  (channels, HITL prompts) directly — rejected: dismantles the single
  identity/policy/audit edge; the human-interaction problem still has to
  be solved against enterprise auth and audit requirements
- keep ADR-0003's swappability framing unchanged — rejected: misleads
  future specs toward lowest-common-denominator design and continued
  under-exploitation of the kernel
- supersede ADR-0003 entirely — rejected: the contract decision itself
  remains correct and in force; only its stated rationale is restated

## Consequences

- ADR-0003's decision stands; this record restates its purpose and
  governs how future specs interpret the boundary
- the v2 contract may deliberately grow rich: interaction semantics
  (confirmation frames, interruption, steering) are legitimate contract
  extensions when the product needs them, not violations of the boundary
- kernel exploitation follows SPEC-018's four-point adoption gate:
  deny-by-default policy + audit preserved, identity via delegated token
  only, read-only posture, no framework types past the contract
- human-in-the-loop becomes a first-class platform feature to build once
  through the contract; framework-native channels are never surfaced
  directly
- follow-up: HITL confirmation bridging (kernel confirmation events →
  v2 contract frames → operator-portal approve/deny → answer returned)
  is recorded as future scope in SPEC-018 and must be delivered before
  any write/mutating tool ships
