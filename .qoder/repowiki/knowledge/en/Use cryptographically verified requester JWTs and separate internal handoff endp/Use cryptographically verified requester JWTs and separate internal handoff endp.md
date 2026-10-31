---
kind: design
name: Use cryptographically verified requester JWTs and separate internal handoff endpoints for delegated execution
source: session
category: adr
---

# Use cryptographically verified requester JWTs and separate internal handoff endpoints for delegated execution

_Source: coding plans from commit period 83e0f94 → e41007f — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
User-delegated targets must preserve the original requester's identity across approval, worker dispatch, and tool invocation without leaking bearer tokens into persisted envelopes or allowing ordinary routes to override caller identity.

## Decision drivers
- identity integrity across service boundaries
- separation of signed envelope vs. authenticated transport
- no persistence of human bearer tokens

## Considered options
- **Typed requester context via inbound delegated JWT plus separate `/api/v2/tools/invoke-delegated` endpoint** — pros: verifies issuer/audience/signature/expiration/subject; keeps requester bearer memory-only; worker remains single non-retrying dispatch owner; HMAC signing secret stays out of tool-gateway; cons: adds new internal route, workload JWT audiences, and execution-ledger migration
- **Reuse existing `DELEGATED_TOKEN` globally or pass requester token inside the signed envelope** — pros: less plumbing; cons: mixes authentication with signed payload; risks impersonation if ordinary routes accept overrides; persists human bearer

## Decision
Require a cryptographically verified inbound delegated JWT carrying `requester_namespace`/`requester_sub` (and matching decider fields) as optional all-or-none envelope fields, and pass the requester bearer separately in the authenticated agent-to-worker request. Tool-gateway exposes an internal `/api/v2/tools/invoke-delegated` endpoint callable only by the exact execution-runtime workload identity, which independently verifies both human bearers against the projection before applying policy and target acquisition.

## Consequences
Execution ledger gets a versioned migration; historical v1 rows remain immutable. Ordinary public/diagnostic routes cannot accept requester overrides. The worker is the sole non-retrying dispatch owner and does not distribute the HMAC signing secret to tool-gateway. Session metadata binds to immutable requester namespace/sub for new delegated-capable sessions.