# SPEC-029: Technical Plan

## Approach

Replicate the platform's canonical fire-and-forget audit emitter into
skills-hub (fifth member of the identifier-normalized emitter family),
extend the closed audit vocabulary additively, and emit at the three
points where usage/catalog facts are known: search response, retrieval
response, sync-cycle completion. No new query surface — the SPEC-013
audit API and its `event_type` filter serve the analytics.

## Key decisions

- **Emit at skills-hub, not (only) at the caller.** tool-gateway's
  `tool_invoked` events see tool names, not skill outcomes, and only
  agent traffic. skills-hub sees every consumer and the actual skill ids
  returned. User attribution is recovered by joining on `request_id`
  (R-3) instead of forwarding user identity into skills-hub.
- **Exact copy of the canonical emitter.** The module is byte-identical
  to tool-gateway's `audit_emitter.py` modulo `skills_hub`/`SkillsSettings`
  identifiers, so it joins `AuditEmitterParityTest` (M1 drift guard) and
  future fixes propagate mechanically. Requires `record_audit_emit` in
  `skills_hub/core/metrics.py` (same name as the family expects).
- **Route emission after the store call, before the response return** —
  the emitter never raises and spawns a daemon thread, so response
  latency is unaffected; the authenticated `client_id` (already returned
  by `authenticate_caller`) becomes `actor`; routes start capturing that
  return value.
- **Sync emission inside `sync_once`'s existing success/error arms**,
  reusing the `SourceStatus` fields and the token-scrubbed error message
  it already computes. `sync_once` "never raises" stays true: emission is
  fire-and-forget.
- **Contract extension is additive** (three enum values + details docs).
  The audit-service `EventType` Literal is the only consumer-side model;
  `test_contracts.py` already asserts model ↔ schema enum equality, so
  drift is impossible.

## Touch points

| Area | File | Change |
| --- | --- | --- |
| Contract | `shared/shared-contracts/schemas/audit-event.schema.json` | +3 enum values, details docs |
| audit-service | `src/audit_service/schemas/audit.py` | +3 Literal values |
| audit-service | `tests/test_routes.py` | skills-event round-trip test |
| skills-hub | `src/skills_hub/services/audit_emitter.py` | new (canonical copy) |
| skills-hub | `src/skills_hub/core/config.py` | `SKILLS_AUDIT_*` settings |
| skills-hub | `src/skills_hub/core/metrics.py` | `record_audit_emit` |
| skills-hub | `src/skills_hub/api/routes/skills.py` | emit in search/get |
| skills-hub | `src/skills_hub/services/sync.py` | emit in `sync_once` |
| skills-hub | `tests/` | emitter/route/sync/config tests |
| tool-gateway | `src/tool_gateway/services/gateway_service.py` | `request_id` in identity dict |
| tool-gateway | `src/tool_gateway/tools/skills_connector.py` | forward `x-request-id` |
| tool-gateway | `tests/test_module_parity.py` | skills-hub joins emitter family |
| gitops | `sync-audit-secrets.sh`, `dev-k8s/base/skills-hub/*` | ingest registration + env |
| docs | `configuration-reference.md`, READMEs, CHANGELOG | living-doc updates |

## Test strategy

- skills-hub `tests/test_audit_emitter.py` mirrors tool-gateway's:
  contract-schema validation of built envelopes, no-op gating (no thread
  when URL unset), delivery ok/4xx/transport-error paths against a fake
  `httpx.Client`.
- Route tests assert emission payloads (search details, retrieval hit and
  not-found miss, list NOT emitting) by patching `emit_audit_event`.
- Sync test asserts one event per cycle with status fields on the success
  and failure arms.
- tool-gateway tests assert `request_id` lands in the identity dict and
  the skills connector sends the `x-request-id` header.
- Parity guard proves the emitter copy cannot drift.
