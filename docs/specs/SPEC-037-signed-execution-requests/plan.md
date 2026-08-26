# SPEC-037 Implementation Plan

One service does the work (agent-platform), with additive contracts,
one deploy-chain script, and one portal badge. Execution keeps running
in-process — Phase 2's isolated worker is out of scope. The signing
envelope is built where the decision and the parked arguments are both
in hand (the resume path), verified where the invocation goes out (the
gateway tool boundary), and persisted beside the confirmation records.

## R-1 execution request and receipt contracts

- `shared/shared-contracts/schemas/execution-request.schema.json` and
  `execution-receipt.schema.json` (new, v1) — fields per spec R-1;
  `signature` is the HMAC-SHA256 hex over the canonical envelope
  excluding itself.
- Canonicalization helper lives in agent-platform
  (`services/execution_signing.py`): `json.dumps(obj, sort_keys=True,
  separators=(",", ":"))` then SHA-256 — pinned by unit tests for
  key-order, whitespace, and value-change stability.

## R-2 signed requests at resume

- New module `services/execution_signing.py`:
  - `sign_request(envelope, key) -> str` / `verify_request(envelope,
    signature, key) -> bool` (HMAC-SHA256, constant-time compare);
  - `build_requests(pending, decider_user_id, key) -> list[
    ExecutionRequest]` — one per parked tool call, `args_digest`
    computed from the *parked* arguments, `execution_id` a fresh UUID.
- `runtime_settings.py`: new `execution_signing_key` sourced from
  `AGENT_EXECUTION_SIGNING_KEY` (per-service `AGENT_` prefix).
- `runtime_kernel.resume_confirmation`: after the claim, on `approve`
  — build and persist the requests, then set a state-local
  `ContextVar` (`EXECUTION_REQUESTS` mapping `call_id` → request) for
  the duration of the resumed stream; on missing key, yield the
  `confirmation_result` frame as approved but reject execution: the
  resumed reply reports the rejection, `execution_rejected`
  (`signing_unavailable`) is audited, and no tool call goes out.
  Denials construct nothing.

## R-3 argument-digest verification at invocation

- `tools/gateway_tools.py` (`_make_tool_fn` / `tool_fn`): for mutating
  tools (`is_read_only` False), read `EXECUTION_REQUESTS` for the
  current `call_id`; recompute the invoked arguments' digest and
  compare with the signed envelope. Match → proceed; mismatch → raise
  a structured tool error, audit `execution_rejected`
  (`args_digest_mismatch`), never call the gateway. Read-only tools
  skip the check entirely. Absent envelope on a mutating call (e.g. a
  path that bypassed resume) also rejects — fail closed.

## R-4 durable execution records

- New module `services/execution_records.py`, mirroring
  `confirmation_records.py` structure: `ExecutionRecordStore` protocol
  with memory + Postgres backends, `build_execution_record_store()`
  factory, module-level `EXECUTION_RECORD_STORE`, same
  `AGENT_STATE_STORE_BACKEND` / `AGENT_STATE_DB_URL` posture and a
  dedicated `execution_records` table (in-place creation on first use,
  same migration posture as the confirmation table).
- Write points: requests at resume (best-effort — a failure logs and
  continues, matching the SPEC-031 claim-time write posture), receipts
  after the tool result lands in `runtime_kernel`'s resumed-stream
  frame handling (status mapped from the tool result, `request_id`
  from the stream's request id).
- Retention: TTL-scoped startup sweep reusing the confirmation
  records' sweep shape (30-day window).
- Session detail: `api/v2/routes.py` session-detail assembly gains an
  additive `executions` array under each confirmation entry (owner
  scope already enforced by the existing route).

## R-5 execution audit events

- `audit-event.schema.json`: three additive `event_type` enum values
  (`execution_requested`, `execution_completed`, `execution_rejected`)
  plus details-description text documenting each payload.
- Emission through the existing fire-and-forget emitter (the
  parity-guard family): `execution_requested` at request persistence,
  `execution_completed` at receipt write (status, duration_ms,
  `request_id`), `execution_rejected` at any rejection path (reason).
  All carry `confirm_id`; `x-request-id` forwards as today.

## R-6 receipt visibility on decided cards

- Session-detail `executions` entries ride the existing session-detail
  fetch; `useChatStream` / transcript seeding maps them onto decided
  confirmation cards (`status`, `digest_match`).
- Confirmation card component: read-only receipt badge (succeeded /
  failed / timeout) plus digest-match state; absent receipt (legacy
  decided rows) renders exactly as today. No inbox changes.

## Deploy chain

- New `shared/platform-ops/gitops/sync-execution-signing-secret.sh` —
  generates or reuses a signing key, writes the
  `execution-signing-secret` Secret, honors
  `SKIP_EXECUTION_SIGNING_SECRET=true` for CI; wired into
  `dev-k8s/deploy.sh` beside the other sync scripts; the agent-service
  deployment gains `AGENT_EXECUTION_SIGNING_KEY` from the Secret.

## Sequencing And Dependencies

1. Contracts + canonicalization + signing module (R-1, R-2 core) —
   depends on nothing
2. Resume-path wiring + rejection posture (R-2) — depends on 1
3. Invocation verification (R-3) — depends on 1
4. Record store + session detail (R-4) — depends on 1; parallel with 3
5. Audit events (R-5) — depends on 2/3 write points
6. Portal badge (R-6) — depends on 4
7. Deploy chain + live check — depends on all

## Test Strategy

- unit tests (`products/agent-platform/tests/`): canonicalization
  stability; sign/verify round-trip and tamper rejection; request
  build from parked calls; resume-path approval/denial/missing-key
  matrix; invocation digest match/mismatch/absent-envelope/read-only
  skip; record store memory + Postgres parity, best-effort write
  failures, startup sweep; session-detail executions assembly
- contract tests: both new schemas validate; audit schema accepts the
  three new payloads; `make validate-policy` unaffected
- portal: vitest component tests for the receipt badge states
- integration / overlay validation: `make overlays` renders the
  agent-service env addition; live check on dev-k8s runs the mutating
  demo (`mutating-demo.sh` on the `mutating-dev` profile) and confirms
  requests/receipts land, the audit chain correlates, and the card
  shows the receipt

## Rollout And Migration

- deployment changes: new Secret + env on agent-service via the deploy
  chain; overlays re-render
- backward compatibility: additive everywhere — legacy decided cards
  (no execution rows) render unchanged; read-only flows untouched;
  denial flows untouched
- fail-closed posture: an unprovisioned key blocks mutating execution
  (by design); rollback restores the pre-spec behavior by removing the
  env var only if the signing requirement is feature-flagged off — the
  spec ships without such a flag, so rollback means redeploying the
  previous image
