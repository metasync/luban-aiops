---
kind: design
name: Enforce one HITL gate per mutating browser flow via session-scoped flow authority
source: session
category: adr
---

# Enforce one HITL gate per mutating browser flow via session-scoped flow authority

_Source: coding plans from commit period e252f12 → 6359eeb — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
SPEC-049 R-4 promised that a single approval unlocks the bound flow's interactions for that session, but the kernel parked every write-tier browser tool independently, producing multiple approval cards. The demo also contradicted the intended single-gate design by auto-submitting both login and reset, forcing the model to improvise extra writes.

## Decision drivers
- realize SPEC-049 R-4 one-gate-per-flow invariant
- fail-closed signed-execution model (SPEC-037/038)
- bounded blast radius per session
- no change to gateway deviation guards

## Considered options
- **Auto-allow list browser write tools** _(rejected)_ — pros: simplest code path; cons: breaks the fail-closed signed-execution invariant; removes operator consent
- **Per-action approval cards (status quo)** _(rejected)_ — pros: no platform changes; cons: violates the one-gate invariant; observed defect produces multiple cards
- **Skill-authoring-only discipline** _(rejected)_ — pros: zero platform cost; cons: fragile, unenforced, already regressed in live demo
- **Session-scoped flow authority with kernel-auto-signed envelopes** — pros: realizes R-4; keeps each execution individually signed/persisted/audited/receipted; bounded by TTL + gateway origin/risk_class/step budget; no static allow-list change; cons: requires new `FlowApprovalStore`, signing helper, middleware branch, and runtime arming plumbing

## Decision
Implement platform-side flow-unlock: after approving the first browser-write card, record a session-scoped `FlowApproval` (TTL-bounded); subsequent `web.*` write calls in that session are ALLOWED and auto-signed under the approving card's authority via a new `build_flow_request` envelope injected into `EXECUTION_REQUESTS`. Browser write tools never join the static auto-allow list. Non-browser writes (`k8s.*`) are unaffected.

## Consequences
Realizes SPEC-049 R-4/D-3; adds `services/flow_approvals.py`, `execution_signing.build_flow_request`, a `flow_signer` branch in `GatewayPermissionMiddleware`, and arming logic in `runtime_kernel.resume_confirmation` / `stream_events`. Session-scoped blast radius is bounded by `AGENT_BROWSER_FLOW_APPROVAL_TTL` (default 900s) and the existing gateway deviation guard. A minor deviation: step-budget exhaustion denies unlocked writes instead of re-parking them (fail-closed). No new audit event or policy action types are introduced.