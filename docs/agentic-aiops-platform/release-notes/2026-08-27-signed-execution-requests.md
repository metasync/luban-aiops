# v0.19.0 — Signed Execution Requests and Receipts (SPEC-037)

Date: 2026-08-27
Release type: minor (additive contracts, audit enum values, and session
surface; no approval, policy, or HITL semantics change)

## Summary

v0.19.0 delivers Phase 1 of the execution-runtime spike
(`docs/workspace/execution-runtime-spike.md`): approved mutating calls
gain a tamper-evident execution chain. When a parked confirmation
resumes with approval, agent-service signs an HMAC-SHA256 execution
request over the parked arguments' digest before any invocation; the
invocation boundary recomputes the digest and blocks any mismatch;
durable execution records and signed receipts close each executed call,
and the audit trail correlates `confirmation_decided` →
`execution_requested` → `tool_invoked` → `execution_completed`. The
portal renders a read-only receipt badge on decided confirmation cards.
Execution still happens in-process under the confirmer's delegated
token — the isolated `execution-runtime` worker remains Phase 2 with
its own spec after this slice is live-verified.

## What Changed

### Execution request and receipt contracts (R-1)

- Two additive schemas land in `shared/shared-contracts/schemas/`:
  `execution-request.schema.json` (v1) and
  `execution-receipt.schema.json` (v1), plus a shared canonicalization
  helper (sorted keys, no insignificant whitespace) so both sides
  digest identical argument sets regardless of key order.

### Signed requests at resume, fail-closed (R-2)

- An approved resume constructs one signed request per approved tool
  call before any invocation; signatures are HMAC-SHA256 over the
  canonical envelope with `AGENT_EXECUTION_SIGNING_KEY`. A missing key
  fails closed: the resumed stream reports the execution as rejected
  and audits `execution_rejected` (`signing_unavailable`) — never a
  silent unsigned execution. Denials construct no request.

### Argument-digest verification at invocation (R-3)

- At the gateway-invocation boundary, mutating calls recompute the
  invoked arguments' digest against the signed envelope before the
  tool-gateway call goes out. A mismatch audits `execution_rejected`
  (`args_digest_mismatch`), marks the record `rejected`, and blocks the
  invocation; read-only tools never consult the envelope.

### Durable execution records (R-4)

- A new execution record store persists requests and receipts on the
  SPEC-031 Postgres posture (memory backend for tests), keyed
  `(confirm_id, call_id)`, following the confirmation records'
  retention. Writes are best-effort-durable — a store failure degrades
  audit completeness, never the chat stream. Session detail gains an
  additive owner-scoped `executions` array per decided confirmation;
  receipts close only `status='requested'` rows.

### Execution audit events (R-5)

- `audit-event.schema.json` gains three additive `event_type` values —
  `execution_requested`, `execution_completed`, `execution_rejected` —
  emitted through the canonical fire-and-forget emitter with
  `confirm_id` and forwarded `x-request-id`, so the durable trail
  correlates the full approval-to-execution chain without a new audit
  dimension.

### Portal receipt badge (R-6)

- Decided confirmation cards in the owner transcript render a
  read-only execution receipt: status tag (requested / succeeded /
  failed / timeout / rejected), tool name, and a digest-match note.
  Live undecided cards and the approver inbox are unchanged — the
  inbox stays decision-metadata-only.

### Deploy chain

- `sync-execution-signing-secret.sh` provisions the
  `execution-signing-secret` (generate → reuse ladder, skippable via
  `SKIP_EXECUTION_SIGNING_SECRET=true`), wired into `deploy.sh`; the
  agent-service deployment reads `AGENT_EXECUTION_SIGNING_KEY` through
  an optional `secretKeyRef` so an absent secret fails closed
  app-side. `sync-audit-secrets.sh` registers agent-service in
  `AUDIT_INGEST_CLIENTS` and upserts
  `AGENT_AUDIT_CLIENT_SECRET` into the agent-platform runtime-profile
  secrets (preserving the LLM keys), and the agent-platform
  runtime config carries the audit service URL and client id.

## Validation

- Agent-platform suite 527 passed (contracts, canonicalization,
  signing/verification, resume-path signing/denial/fail-closed/receipt/
  rejection/timeout, record store both backends, session-detail
  attachment, audit emission); portal suite 164/164 (vitest) +
  `tsc --noEmit` clean.
- `make verify` green: version lockstep 0.19.0, three kustomize
  overlays, policy validation.
- Live check: `mutating-demo.sh` HITL leg on the `mutating-dev`
  profile — parked `risk_level=write` call, tier_2 approval, signed
  receipt on the approved card (`digest_match` true, signature and
  outcome digest present), and the correlated `execution_requested` /
  `execution_completed` events for the same `confirm_id` on the
  durable trail.
