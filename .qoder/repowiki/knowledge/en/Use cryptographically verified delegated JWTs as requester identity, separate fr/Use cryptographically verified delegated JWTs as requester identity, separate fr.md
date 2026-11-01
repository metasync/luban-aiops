---
kind: design
name: Use cryptographically verified delegated JWTs as requester identity, separate from approver bearer
source: session
category: adr
---

# Use cryptographically verified delegated JWTs as requester identity, separate from approver bearer

_Source: coding plans from commit period b4148f4 → c4214cf — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
User-delegated targets need to preserve the original requester's ownership over the target grant even when another user approves the action. Unsigned headers, model arguments, usernames, emails, or session identifiers cannot serve as trusted identity.

## Decision drivers
- non-repudiable human provenance
- cross-user approval must not switch target account
- separation of requester vs approver authority

## Considered options
- **Typed requester context backed by a signed delegated JWT with issuer/audience/signature/expiry/subject checks** — pros: cryptographically verifiable; survives park/re-park; never persisted in session state, confirmations, execution rows, evidence, or logs
- **Derive requester from unsigned header / username / email / session ID** _(rejected)_ — pros: simpler transport; cons: forgeable; cross-user approval would impersonate the approver; no cryptographic proof of delegation

## Decision
Add a typed non-model requester context using a cryptographically verified inbound delegated JWT (trusted issuer namespace, audience, signature, expiration, nonempty subject, expected human delegation provenance). Bind new delegated-capable sessions to immutable requester namespace/sub in backend metadata; preserve requester identity at park/re-park via memory-only token holding. Existing machine-credential envelopes retain current behavior; delegated-target mutations require the four bounded envelope fields `requester_namespace`, `requester_sub`, `decider_namespace`, `decider_sub`.

## Consequences
The worker verifies both requester and approver bearers and matches them to signed identities plus existing owner/decider/session/call bindings. A missing/expired requester bearer requires a fresh turn rather than impersonation fallback. Legacy unbound sessions must start a new verified session before using delegated targets. Internal execution uses `/api/v2/tools/invoke-delegated` callable only by the exact execution-runtime workload identity.