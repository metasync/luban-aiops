# SPEC-037: Signed Execution Requests and Receipts

## Status

- status: `approved`
- owner: luban-platform-team
- created: 2026-08-27
- release slice: R4 — Approval-Gated Bounded Actions (closing slice)
- related ADRs: none (spike memo: `docs/workspace/execution-runtime-spike.md`, Phase 1)

## Summary

Approved mutating actions gain a tamper-evident execution record: when a
parked confirmation is resumed with approval, agent-service constructs a
signed execution request per approved tool call — an HMAC-SHA256 envelope
over the tool name, a digest of the *parked* arguments, the confirm id,
the decider, and the session — verifies the executed arguments against
that digest at invocation time, and persists a signed execution receipt
with the outcome. Execution still happens in-process (the isolated worker
is Phase 2, own spec); this slice closes the R4 "signed execution
requests" deliverable and makes the approval-to-execution binding
auditable.

## Motivation

- **The decision side is durable; the execution side is not.** SPEC-031
  records who decided what and when, and the tool-gateway emits
  `tool_invoked` per call — but nothing today proves the executed
  arguments are the ones the approver saw on the confirmation card. The
  binding is reconstructive (chat transcript + invocation logs), not
  cryptographic.
- **The R4 roadmap names this deliverable.** "Signed execution requests"
  is one of the two R4 lines still unimplemented (the isolated worker is
  the other). The spike memo verified the current path executes
  in-process under the confirmer's delegated token and recommends this
  sign-and-record slice as Phase 1 — operator sign-off was given
  2026-08-27.
- **Weaker models upstream raise the bar.** As the SPEC-028 big-small
  pattern matures, smaller edge models will propose or pre-filter
  actions; the invariant that nothing executes except via an approved,
  signed request is what keeps those proposals safe. Laying the signed
  envelope now means the future isolated worker inherits a proven
  contract instead of inventing one.

## Requirements

Each requirement is stable once the spec is `approved` and carries
testable acceptance signals.

### R-1: Execution request and receipt contracts

Two additive schemas land in `shared/shared-contracts/schemas/`:
`execution-request.schema.json` (v1) — `execution_id`, `confirm_id`,
`call_id`, `session_id`, `owner_user_id`, `decider_user_id`,
`tool_name`, `args_digest` (SHA-256 hex of canonical-JSON arguments),
`requested_at`, `signature`; and `execution-receipt.schema.json` (v1) —
`execution_id`, `status` (`succeeded` / `failed` / `timeout`),
`outcome_digest`, `request_id` (the correlating `x-request-id`),
`completed_at`, `signature`. Canonicalization is defined once (sorted
keys, no insignificant whitespace) and shared by both sides.

Acceptance signals:

- Both schemas validate under the shared-contracts validator; a
  canonicalization helper is unit-tested for key-order and whitespace
  stability (same input ⇒ same digest, reordered input ⇒ same digest,
  changed value ⇒ different digest).

### R-2: Signed requests at resume, fail-closed on missing key

When a claimed confirmation resumes with `approve`, agent-service
constructs one signed execution request per approved tool call before
any invocation happens. Signatures are HMAC-SHA256 over the canonical
envelope with a platform key provisioned by a new
`sync-execution-signing-secret.sh` in the deploy chain (same posture as
the delegation and audit secrets) and surfaced to agent-service as
`AGENT_EXECUTION_SIGNING_KEY`. If the key is absent, mutating resumes
fail closed: the resumed stream reports the execution as rejected and
audits `execution_rejected` (reason `signing_unavailable`) — a missing
key never silently degrades to unsigned execution. Denials construct no
request.

Acceptance signals:

- Resume-path tests: an approved batch produces one signed request per
  call with the parked arguments' digest; a denial produces none; with
  the key unset the mutating resume rejects before invoking and the
  rejection is audited.
- Deploy chain: `deploy.sh` invokes the new sync script; the dev-k8s
  overlay provisions the secret (skippable via
  `SKIP_EXECUTION_SIGNING_SECRET=true` for CI, matching the existing
  `SKIP_*_SECRETS` pattern).

### R-3: Argument-digest verification at invocation

At the gateway-invocation boundary, mutating tool calls carry their
execution request (state-local, set at resume); the invoked arguments'
digest is recomputed and compared against the signed envelope before the
tool-gateway call goes out. A mismatch audits `execution_rejected`
(reason `args_digest_mismatch`) and blocks the invocation — the kernel's
ALLOWED state alone never suffices for a mutating call. Read-only tools
are untouched (no envelope, no check).

Acceptance signals:

- Invocation-path tests: matching arguments pass verification and the
  call proceeds; a mutated argument set is blocked and audited with the
  mismatch reason; read-only invocations never consult the envelope.

### R-4: Durable execution records beside confirmation records

A new execution record store persists requests and receipts on the same
Postgres posture as SPEC-031 confirmation records (memory backend for
tests), keyed by `confirm_id` + `call_id`. Writes are best-effort-durable
— a store failure degrades audit completeness, never the chat stream
(same posture as SPEC-031 claim-time resolution writes). Records follow
the confirmation records' retention: TTL-scoped startup sweep, no
unbounded growth. The session-detail surface gains an additive
`executions` array per confirmation (owner-scoped, like the cards
themselves) carrying request/receipt status and the digest-match result.

Acceptance signals:

- Store tests (memory + Postgres): request persists at resume, receipt
  lands after the tool result, a store failure raises no exception into
  the stream, expired rows are swept at startup.
- Session-detail route test: decided confirmations carry their
  execution entries; pending ones carry none.

### R-5: Execution audit events

Three additive `event_type` values extend `audit-event.schema.json` —
`execution_requested` (envelope metadata), `execution_completed`
(status, duration, request correlation), `execution_rejected` (reason) —
emitted through the canonical fire-and-forget emitter with `confirm_id`
and forwarded `x-request-id`, so the trail correlates
`confirmation_decided` → `execution_requested` → `tool_invoked` →
`execution_completed` without a new audit dimension. The schema's
details description documents the three payloads.

Acceptance signals:

- Emission tests: an approved-and-executed mutating call emits requested
  then completed with matching `confirm_id`; a rejected call emits only
  `execution_rejected` with its reason; the schema validator accepts all
  three payloads.

### R-6: Receipt visibility on decided confirmation cards

The portal renders execution status read-only on decided confirmation
cards in the owner transcript: a receipt badge (succeeded / failed /
timeout) and the argument-digest match result, no new view and no new
interaction. Live undecided cards and the approver inbox are unchanged —
receipts are owner-visible through the session surface (the memo's Q-3,
resolved: the approver's surface stays decision-metadata-only, keeping
SPEC-030 Q-1's exposure posture).

Acceptance signals:

- Component tests: a decided card with a receipt renders the badge and
  digest-match state; a decided card without a receipt (legacy row)
  renders as today; inbox entries are unchanged.

## Non-Goals

- The isolated `execution-runtime` worker — Phase 2 of the spike memo,
  own spec after this slice is live-verified.
- Async execution queues, retries, schedules — rejected in the spike;
  re-execution of a mutating action is never automatic.
- Receipt exposure through the approvals inbox API — the approver
  surface stays metadata-only (Q-3 resolution above).
- Any change to approval tiers, policy semantics, pending-record
  behavior, or the HITL timeout — SPEC-030/031 surfaces are untouched.
- Asymmetric (Ed25519) signing — rejected in the spike for a single
  trust domain; revisit only if a non-key-holding verifier appears.

## Impact

- products touched: `products/agent-platform` (execution signing,
  verification, record store, resume path, session detail),
  `products/operator-portal` (decided-card receipt badge),
  `shared/platform-ops/gitops` (signing-secret sync script and deploy
  wiring)
- contracts touched: `execution-request.schema.json` (new, v1),
  `execution-receipt.schema.json` (new, v1), `audit-event.schema.json`
  (additive enum values + details description)
- identity / policy / audit / execution safety impact: strictly tighter
  — approved executions gain a tamper-evident binding and a fail-closed
  signing requirement; no grant is widened, no approval surface changes
- living state docs to update on delivery: approval-and-hitl guide,
  configuration-reference (new knob and secret), CHANGELOG,
  delivery-roadmap, spec index

## Open Questions

None — the memo's Q-1 and Q-2 belong to the Phase-2 worker spec; Q-3 is
resolved in R-6. All resolvable at draft; must stay empty before
approval.

## Changelog

- 2026-08-27: approved by the operator with no changes to the drafted
  requirements; implementation proceeds in a fresh session.
- 2026-08-27: created as `draft` from the execution-runtime spike memo
  (Phase 1) after operator sign-off on the phased shape.
