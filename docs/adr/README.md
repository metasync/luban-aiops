# Architecture Decision Records

## Purpose

Capture architecturally significant decisions as small, immutable records instead of growing the long-form documents in `docs/agentic-aiops-platform/`.

The existing long-form decision documents remain the founding architecture record:

- `part-1-decision-matrix.md` — framework selection (`AgentScope 2.0`)
- `part-1b-framework-revalidation.md` — 2026-07 framework revalidation (re-affirms `AgentScope 2.0`, records swap triggers)
- `agent-platform-runtime-options.md` — transitional versus native runtime strategy
- `../workspace/python-container-strategy.md` — container base image strategy

New decisions from this point forward are recorded here.

## When To Write An ADR

Write an ADR when a decision:

- constrains future implementation across more than one product
- selects between competing technologies, protocols, or patterns
- changes the trust model, identity flow, or deployment topology
- reverses or supersedes an earlier recorded decision

Do not write an ADR for decisions local to a single spec; record those in the spec's `plan.md`.

## Format And Rules

- files are numbered sequentially: `NNNN-<slug>.md`
- use `template.md` in this directory
- statuses: `proposed`, `accepted`, `superseded by ADR-NNNN`
- an accepted ADR is immutable except for status changes and supersession links
- specs reference the ADRs they depend on in their status header

## Index

| ID | Title | Status |
| --- | --- | --- |
| `ADR-0001` | Adopt spec-driven development with tiered documentation | `accepted` |
| `ADR-0002` | Re-affirm AgentScope 2.0 as the runtime kernel | `accepted` |
| `ADR-0003` | Platform-owned agent-service contract | `accepted` |
| `ADR-0004` | Broker-mediated token delegation for service-to-service calls | `accepted` |
| `ADR-0005` | Extract the platform API edge into a separate `platform-gateway` product | `accepted` |
| `ADR-0006` | Contract purpose restated — invariant enforcement, not framework swappability | `accepted` |
