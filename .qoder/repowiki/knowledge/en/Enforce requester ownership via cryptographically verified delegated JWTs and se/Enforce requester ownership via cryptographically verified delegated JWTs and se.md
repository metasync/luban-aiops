---
kind: design
name: Enforce requester ownership via cryptographically verified delegated JWTs and separate execution/workload JWTs
source: session
category: adr
---

# Enforce requester ownership via cryptographically verified delegated JWTs and separate execution/workload JWTs

_Source: coding plans from commit period 199331f → 83e0f94 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
User-delegated target mutations must prove who initiated the request and who approved it, without letting the approver impersonate the original requester or leaking human tokens into persisted execution records.

## Decision drivers
- requester identity provenance
- separation of authentication and authorization
- no persisted human tokens
- worker trust boundary

## Considered options
- **Pass the requester's bearer token in the execution envelope and verify it at the worker** _(rejected)_ — pros: simple transport; cons: human bearer would be persisted in execution rows; worker would need access to the human auth material
- **Signed execution envelope carrying bounded `requester_namespace`/`requester_sub`/`decider_namespace`/`decider_sub` fields, with the actual human bearers passed separately over an authenticated agent-to-worker channel** — pros: only hashes and identities persist; worker verifies both bearers against the signed projection before dispatch; workload JWT pins the sender; cons: adds envelope fields, migration, and a new internal `/api/v2/tools/invoke-delegated` route

## Decision
Human delegation uses a cryptographically verified inbound JWT whose issuer, audience, signature, expiration, subject, and expected human delegation provenance are checked; the namespace/sub becomes the immutable requester context bound to the session. The signed execution envelope carries optional bounded string fields `requester_namespace`, `requester_sub`, `decider_namespace`, `decider_sub`. Tool-gateway exposes `POST /api/v2/tools/invoke-delegated` callable only by the exact execution-runtime workload identity (audience `luban-target-execution-handoff`). The worker forwards its verified execution projection plus the requester and approver bearers over this authenticated channel; tool-gateway independently verifies the human bearers and matches them to the signed identities before applying invocation/mutation policy.

## Consequences
Requester ownership is provable and survives redaction, but human bearer tokens are never persisted. Ordinary public invocation and diagnostic routes cannot accept a caller-supplied requester override. The worker remains the single non-retrying dispatch owner; tool-gateway trusts the authenticated worker's execution verification but does not receive the execution HMAC signing secret.