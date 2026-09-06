---
kind: design
name: Enforce one HITL gate per mutating browser flow via session-scoped flow authority
source: session
category: adr
---

# Enforce one HITL gate per mutating browser flow via session-scoped flow authority

_Source: coding plans from commit period 545a4fc → 33e6a7f — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
SPEC-049 R-4 promised that a single approval unlocks the bound flow's interactions for that session, but the kernel parked every write-tier tool call independently. The live password-reset demo exposed this: each mutating call produced its own approval card, contradicting the spec and forcing users to approve multiple times.

## Decision drivers
- spec conformance (one gate per mutating flow)
- fail-closed signed execution invariant
- no change to static auto-allow list policy
- bounded blast radius via TTL

## Considered options
- **Auto-allow write tools in the gateway allow-list** _(rejected)_ — pros: simplest code path; cons: breaks SPEC-037/038 fail-closed signed-execution invariant; removes operator consent entirely
- **Per-action approval cards (status quo)** _(rejected)_ — pros: minimal platform changes; cons: violates the one-gate invariant; already regressed in production; user experience degrades with repeated approvals
- **Skill-authoring-only discipline (rely on authors to emit one action)** _(rejected)_ — pros: zero runtime cost; cons: fragile, unenforced contract that already failed; no way to prevent accidental extra writes
- **Session-scoped flow authority with kernel-auto-signed envelopes** — pros: realizes SPEC-049 R-4; keeps every write individually signed/persisted/audited; preserves non-browser writes unchanged; bounded by TTL and gateway origin/risk/step guards; cons: adds new FlowApprovalStore, signing helper, and middleware branch; requires reconciling demo pages to a single destructive action

## Decision
Implement a platform-side flow-unlock: after approving the first browser-write card, record a session-scoped FlowApproval (with TTL) so subsequent web.* write calls in that session are ALLOWED and auto-signed under the approving card's authority via a new build_flow_request envelope. Non-browser writes remain unaffected; the static auto-allow list stays unchanged.

## Consequences
Each mutating browser flow now has exactly one approval gate. Approvals expire after AGENT_BROWSER_FLOW_APPROVAL_TTL (default 900s). A stale or rebinding session could auto-sign an unexpected flow's first write, but gateway origin/risk-class/step-budget guards still bound execution. Step-budget exhaustion is denied rather than re-parked (fail-closed). No new audit event type or shared-contract schema is introduced.