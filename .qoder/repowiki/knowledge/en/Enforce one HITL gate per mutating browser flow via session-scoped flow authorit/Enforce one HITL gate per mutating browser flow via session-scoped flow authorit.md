---
kind: design
name: Enforce one HITL gate per mutating browser flow via session-scoped flow authority
source: session
category: adr
---

# Enforce one HITL gate per mutating browser flow via session-scoped flow authority

_Source: coding plans from commit period 123c4b6 → e252f12 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
SPEC-049 R-4 promises that a single approval unlocks the bound flow's interactions for that session, but `GatewayPermissionMiddleware.on_check_permission` parks every non-allow-listed write tool independently with zero flow/session memory. The password-reset demo exposed this as multiple cards because the skill/README/WALKTHROUGH and the target pages contradicted each other on which action is the write.

## Decision drivers
- realize SPEC-049 R-4/D-3 one-gate-per-flow invariant
- fail-closed signed-execution model (SPEC-037/038)
- keep browser writes out of the static auto-allow list
- bounded blast radius via TTL + gateway origin/risk_class/step budget

## Considered options
- **Auto-allow list browser write tools** _(rejected)_ — pros: simplest code change; cons: breaks the SPEC-037/038 fail-closed signed-execution invariant; no operator consent
- **Per-action approval cards (status quo)** _(rejected)_ — pros: no platform changes; cons: violates the one-gate invariant; already regressed in production
- **Skill-authoring-only discipline (one write per skill)** _(rejected)_ — pros: zero runtime cost; cons: fragile, unenforced status quo that silently regressed
- **Session-scoped flow authority with kernel-auto-signed envelopes** — pros: honors R-4 exactly once per flow; each unlocked execution still individually signed/persisted/audited/receipted; bounded by TTL and gateway deviation guard; cons: adds in-memory `FlowApprovalStore`, signing path in middleware/kernel, and a TTL knob; hot-path must stay inert without an approval

## Decision
Implement a platform-side flow-unlock: after approving the first browser-write card, record a session-scoped `FlowApproval` (session_id, confirm_id, owner_user_id, decider_user_id, approved_at) in an in-memory store; subsequent `web.*` write calls in that session are ALLOWED and auto-signed under the approving card's authority via a new `build_flow_request` envelope reused from `sign_envelope`. Non-browser writes (`k8s.*`) are unaffected. A configurable `AGENT_BROWSER_FLOW_APPROVAL_TTL` (default 900 s, 0 disables to pre-fix posture) bounds stale approvals. Browser write tools never join any auto-allow list.

## Consequences
The agent-platform kernel now carries per-session trust state; the hot path remains behavior-preserving when no approval exists. Staleness is bounded by TTL and the gateway's origin/risk_class/step-budget guard. Step-budget exhaustion still fails closed (gateway denies rather than re-parks). The password-reset sample is reconciled so login stays read-tier and the single destructive 'Confirm reset' click is the only card. Delivery traceability is enforced via ADR-0008 (every R-x maps to automated tests; shipped samples exercised under `make verify`).