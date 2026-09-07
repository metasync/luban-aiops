---
kind: design
name: Enforce one HITL gate per mutating browser flow via session-scoped flow authority
source: session
category: adr
---

# Enforce one HITL gate per mutating browser flow via session-scoped flow authority

_Source: coding plans from commit period 33e6a7f → 123c4b6 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
SPEC-049 R-4 promised that one approval unlocks the bound flow's interactions for that session, but the kernel parked every write-tier tool call independently, so the password-reset demo produced multiple cards. The existing behavior relied on fragile skill-authoring discipline and had silently regressed.

## Decision drivers
- realize SPEC-049 R-4 one-gate-per-flow promise
- fail-closed signed-execution invariant (SPEC-037/038)
- bounded blast radius per session
- no change to gateway deviation guard

## Considered options
- **Auto-allow list browser write tools** _(rejected)_ — pros: simplest code path; cons: breaks the fail-closed signed-execution invariant; removes operator consent for writes
- **Per-action approval cards (status quo)** _(rejected)_ — pros: minimal platform change; cons: violates the one-gate invariant; caused the observed multi-card defect
- **Skill-authoring-only discipline** _(rejected)_ — pros: no platform code; cons: already proven fragile and unenforced — it is what regressed
- **Session-scoped flow authority with auto-signed envelopes** — pros: honors R-4 exactly once per flow; each unlocked write still individually signed/persisted/audited/receipted; bounded by TTL + gateway origin/risk_class/step budget; cons: trust-model change spanning agent-platform, tool-gateway, and samples; requires new in-memory store and signing plumbing

## Decision
Implement a per-process `FlowApprovalStore` keyed by `session_id` with a configurable TTL (`AGENT_BROWSER_FLOW_APPROVAL_TTL`). On approving a card containing a browser write, record the authority; subsequent `web.*` write calls in that session are ALLOWed and auto-signed under the approving card's `confirm_id`/`decider` via a new `build_flow_request` envelope. Browser write tools remain excluded from the static auto-allow list; the gateway deviation guard remains the enforcement boundary.

## Consequences
Realizes SPEC-049 R-4: one operator card per mutating browser flow. Session-scoped blast radius is bounded by TTL and the gateway origin/risk_class/step-budget guards. A session rebounding to a different write-class flow after an approval could auto-sign that flow's first write (documented boundary). Step-budget exhaustion now fails closed at the gateway rather than re-parking. No new audit event or contract schema is introduced.