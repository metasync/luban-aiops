---
kind: design
name: Enforce one HITL gate per mutating browser flow via session-scoped flow authority
source: session
category: adr
---

# Enforce one HITL gate per mutating browser flow via session-scoped flow authority

_Source: coding plans from commit period c66ad9a → 7eee39a — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
SPEC-049 R-4 promised that a single approval unlocks the bound flow's interactions for that session, but the kernel parked every write-tier `web.*` tool call as its own approval card. A live password-reset demo exposed this: each mutating browser action triggered a separate card because `GatewayPermissionMiddleware.on_check_permission` had zero flow/session memory and always ASKed for non-allow-listed writes.

## Decision drivers
- realize SPEC-049 R-4 one-gate-per-flow invariant
- keep browser write tools off the auto-allow list to preserve the fail-closed signed-execution invariant (SPEC-037/038)
- bound blast radius with TTL and gateway deviation guards (origin/risk_class/step budget)

## Considered options
- **Auto-allow write-tier browser tools in DEFAULT_AUTO_ALLOWED_TOOLS** _(rejected)_ — pros: simplest path to no extra cards; cons: breaks the SPEC-037/038 fail-closed signed-execution invariant; any future write tool would execute without operator consent
- **Per-action approval cards (status quo / skill-authoring discipline)** _(rejected)_ — pros: no platform change; cons: violates the one-gate invariant; already regressed in production; fragile reliance on skill authors writing exactly one write action
- **Session-scoped flow authority with kernel-auto-signed envelopes** — pros: honors R-4 letter and intent; each unlocked execution is still individually signed/persisted/audited/receipted; bounded by TTL + gateway guard; hot path unchanged when no approval; cons: trust-model change spanning agent-platform, tool-gateway, and samples; requires new SPEC-051 and ADR-0007

## Decision
Implement SPEC-051: after approving the first browser-write card, record a `FlowApproval` (session_id, confirm_id, owner_user_id, decider_user_id, approved_at) in an in-memory `FLOW_APPROVALS` store with a configurable TTL (`AGENT_BROWSER_FLOW_APPROVAL_TTL`). On subsequent `web.*` write calls within that session, `GatewayPermissionMiddleware` uses a `flow_signer` callback to build and inject a fresh SPEC-037 envelope under the approving card's authority, returning ALLOW instead of ASK. Non-browser writes (`k8s.*`) are unaffected. The static auto-allow list stays unchanged — this is runtime session authority, not an allow-list entry.

## Consequences
One operator card per mutating browser flow; subsequent declared steps execute without further cards. Blast radius is bounded by the TTL-bounded session authority plus the existing gateway deviation guard (origin/risk_class/step budget). If a flow exceeds its step budget, the gateway denies it (`BROWSER_FLOW_EXHAUSTED`) rather than re-parking — a minor deviation from R-4's 'escalates to ASK' letter that fails safe. `web.evaluate` is included in flow-unlock and remains subject to pre-execution mutation guard. The hot path is provably inert for turns without a flow approval.