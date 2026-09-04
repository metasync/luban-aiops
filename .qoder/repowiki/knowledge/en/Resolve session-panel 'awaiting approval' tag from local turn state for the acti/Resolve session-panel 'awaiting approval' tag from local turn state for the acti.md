---
kind: design
name: Resolve session-panel 'awaiting approval' tag from local turn state for the active session
source: session
category: adr
---

# Resolve session-panel 'awaiting approval' tag from local turn state for the active session

_Source: coding plans from commit period b4f66c1 → c66ad9a — records intent at planning time; the implementation may lag or differ._

## Context
During SPEC-050 live testing, the session panel kept showing 'awaiting approval' until the backend's `CONFIRMATION_REGISTRY.resolve()` fired in the `finally` block of the resumed stream — i.e., after the agent finished. Operators saw the tag linger even after they had already approved.

## Decision drivers
- immediate visual feedback after operator decision
- no backend change required
- avoid flicker on non-active sessions

## Considered options
- **Move `resolve()` earlier in the backend lifecycle** _(rejected)_ — pros: Single source of truth stays on the server; cons: Risks resolving before the agent has actually consumed the decision; requires backend changes and careful ordering
- **Derive the tag from local turn state for the active session only** — pros: Instant UI response; no backend change; non-active sessions keep using the backend flag; cons: Introduces a small client-side override that must not affect other sessions

## Decision
In `ChatView.tsx`, hide the 'awaiting approval' tag for the active session when local turn state shows no pending confirmation turns (`localDecisionApplied`), while leaving the backend-driven `pending_confirmation` flag intact for non-active sessions. Add a settling indicator between approval and the agent's reply to fill the gap left by the settle-window poll.

## Consequences
The session list becomes responsive to operator actions without waiting for backend reconciliation. Non-active sessions still reflect the authoritative backend state, so this is a strictly local optimization for the active conversation.