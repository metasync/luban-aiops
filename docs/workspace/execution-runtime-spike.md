# Spike: Isolated Execution Worker and Signed Execution Requests (SPEC-037 candidate)

Status: spike complete — Phase 1 promoted to SPEC-037 (delivered in v0.19.0); Phase 2 promoted to SPEC-038 (drafted 2026-08-27)
Date: 2026-08-26
Roadmap home: delivery-roadmap R4 "Approval-Gated Bounded Actions" — "isolated execution worker" and "signed execution requests" are the two R4 deliverables not yet implemented
Verified against: approval and execution path at 0.18.1 (SPEC-020/021/030/031 as delivered)

## 1. Question

SPEC-020 through SPEC-036 delivered the full approval *decision* machinery:
park/resume confirmation bridging, tiered `require_approval` policy
semantics, a durable inbox with persistent cards, live decision sync, and
turn-anchored transcripts. But the approved action itself still executes
**in-process in agent-service**: the resumed turn feeds the confirmed
`tool_call` back through the kernel middleware chain and invokes the
tool-gateway inline under the confirmer's delegated token. The R4 roadmap
names two deliverables this leaves unmet — an *isolated execution worker*
and *signed execution requests*. What is the smallest decision-complete
slice that closes R4 without rebuilding any delivered substrate, and what
is the right phase boundary?

## 2. Findings — verified current state

- **Execution is coupled to the agent reply stream.**
  `RuntimeKernel.resume_confirmation` feeds a `UserConfirmResultEvent`
  back to the parked agent; approved calls traverse the permission chain
  again with `ToolCallState.ALLOWED` (short-circuited, never re-ASKed)
  and run inside the resumed SSE stream. A tool failure interrupts the
  resumed turn; there is no durable "execution request" artifact — only
  the confirmation record (decision, decider, timestamps) and the
  tool-gateway's own `tool_invoked` audit event.
- **Identity rides delegation, not a worker principal.** The confirmer's
  bearer token is set on `DELEGATED_TOKEN` for the resumed stream; the
  tool-gateway evaluates `tools:mutate` admission and policy on that
  delegated identity. There is no service-level execution identity today.
- **The decision side is already durable and attributed.** SPEC-031
  confirmation records live on the shared Postgres posture with
  decider attribution, structured `409 already_resolved` races, and a
  claim-before-stream invariant (one parked batch can never be resumed
  twice). That record is the natural anchor for an execution request.
- **`products/execution-runtime/` is a placeholder README.** Its boundary
  statement already fixes the invariants: it receives signed execution
  requests, never decides whether an action is allowed, and must never
  bypass policy or approval controls.
- **The approval-queue remainder was deliberately deferred.** The
  SPEC-030 spike memo parked "full approval queue + policy-center
  service" as the R5-shaped remainder (option C). This spike must not
  reopen that scope: no queue semantics, no tiers beyond SPEC-030, no
  change windows.
- **Audit has the correlation substrate.** `tool_invoked` events carry
  forwarded `x-request-id`; the `confirmation` audit dimension was
  reserved by the SPEC-020 spike memo. An execution request/receipt pair
  can correlate `confirmation_decided` → execution → `tool_invoked`
  without a new audit dimension.

## 3. Options weighed

| Option | Shape | Cost | Verdict |
|---|---|---|---|
| A. Sign-and-record only (no new service) | On resume of an approved mutating batch, construct a signed execution request (tool, canonicalized args digest, confirm_id, decider, session) before invoking; after the call, persist a signed receipt (status, outcome digest, timestamps). Requests/receipts live on the shared Postgres posture beside confirmation records; new `execution_requested` / `execution_completed` audit events. Execution still in-process | Small | **Phase 1 — recommended.** Delivers the "signed execution requests" R4 line verifiably (approval-to-execution binding is auditable and tamper-evident) with zero new deployment surface |
| B. Isolated worker service now | A plus: new `execution-runtime` deployment; agent-service hands the approved request to the worker over an authenticated internal API; the worker performs the tool-gateway call and writes the receipt; the resume stream awaits the result before continuing | Medium-large | **Phase 2 — the eventual target.** Real process isolation, bounded blast radius, independent resource limits. Cost now: streaming contract surgery (resume must block on worker completion), worker identity and delegation forwarding, crash/idempotency handling |
| C. Full async execution queue | Durable queue, webhook-style completion, agent picks up results on a later turn, retries and schedules | Large | Rejected for R4 — this is the SPEC-030 memo's deferred approval-queue remainder re-entering through the back door; breaks the current "approve → watch it happen" operator experience |

## 4. Recommended shape (SPEC-037 candidate, phased)

### 4.1 Phase 1 — signed execution requests and receipts (Option A)

- **Signing scheme.** HMAC-SHA256 over a canonical request envelope
  (`tool_name`, SHA-256 of canonical-JSON args, `confirm_id`,
  `session_id`, `decider_user_id`, `request_id`, timestamp) with a
  platform key provisioned by a `sync-execution-signing-secret.sh`
  script in the deploy chain (same posture as the delegation and audit
  secrets). Asymmetric (Ed25519) signing is rejected for now: there is
  no multi-party verification need, and HMAC keeps verification
  symmetric with the single trust domain. Revisit if receipts ever need
  verification by a party that must not hold the signing key.
- **Binding invariant.** An execution request is only constructable when
  a claimable pending confirmation exists; the request embeds the
  `confirm_id` and the args digest is computed from the *parked* tool
  call, so the signed envelope proves the executed arguments are the
  ones the approver saw. Any drift between parked args and attempted
  args fails signature verification and audits as
  `execution_rejected` (reason `args_digest_mismatch`).
- **Receipts.** After the tool-gateway call returns, a receipt records
  status (`succeeded` / `failed` / `timeout`), an outcome digest, and
  the correlating `x-request-id`; written best-effort-durable (a write
  failure degrades audit completeness, never the chat stream — same
  posture as SPEC-031 claim-time resolution writes).
- **Contracts.** Additive `execution-request.schema.json` and
  `execution-receipt.schema.json` in shared-contracts; additive
  `execution_requested` / `execution_completed` / `execution_rejected`
  audit event types via the canonical fire-and-forget emitter.
- **Portal.** Read-only execution-request detail on the decided
  confirmation card (args digest match, receipt status) — additive,
  no new view.

### 4.2 Phase 2 — isolated worker (Option B, separate spec)

- New `execution-runtime` product: Python service on the shared base-uv
  image, its own deployment in the dev-k8s overlay, no direct portal or
  LLM exposure.
- Handoff: agent-service `POST`s the signed request over an
  internal API authenticated by service identity (SPEC-008 posture);
  the worker verifies the signature, performs the tool-gateway call with
  the forwarded delegated token, writes the receipt, and returns the
  outcome. The resume stream awaits the worker call (blocking, bounded
  timeout) so the operator still watches the result arrive in the same
  turn.
- Idempotency: request_id-keyed single-flight in the worker; a crash
  after execution but before receipt lands is reconciled by the
  tool-gateway's own invocation audit (documented recovery query, not
  automatic retry — re-execution of a mutating action is never automatic).

## 5. Open questions for the spec

- Q-1: does the worker need its own service identity for the internal
  handoff API, or does mTLS-free cluster-local trust (SPEC-008's current
  posture) suffice for the first slice?
  Resolved by SPEC-038 R-2: the worker holds its own static, scope-limited
  handoff credential (SPEC-008 R-3 posture — no user authority, K8s Secret
  provisioned by the deploy chain); unauthenticated cluster-local trust was
  rejected, projected workload identity stays the cross-service upgrade path.
- Q-2: exact resume-stream timeout when awaiting Phase-2 worker
  completion — reuse the HITL timeout value or introduce a dedicated
  execution timeout knob?
  Resolved by SPEC-038 R-4: a dedicated `AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS`
  knob (default 60s) — the HITL timeout governs parked-confirmation
  answerability, an unrelated concern.
- Q-3: should receipts be retrievable through the approvals inbox API
  (decider-visible) or stay on the session-detail surface (owner-visible)
  — the exposure decision parallels SPEC-030 Q-1.
  Resolved by SPEC-037 R-6: receipts stay owner-visible on the session
  surface; the approver inbox stays decision-metadata-only.

## 6. Promotion recommendation

Promote to a SPEC-037 draft (Phase 1 scope only) once the operator signs
off on the phased shape. Phase 2 gets its own spec number after Phase 1
is live-verified, keeping each release one vertical slice per the roadmap
principles. This memo satisfies the memo-first promotion rule. Operator
sign-off was given 2026-08-27; SPEC-037 drafting proceeds on Phase 1 scope.

Promotion gate satisfied 2026-08-27: Phase 1 (SPEC-037) was delivered in
v0.19.0 and live-verified on the `mutating-dev` profile (signed receipt on
the approved card, correlated `execution_requested` / `execution_completed`
audit chain). Phase 2 was promoted the same day to
`SPEC-038-isolated-execution-worker` (`docs/specs/SPEC-038-isolated-execution-worker/`),
which inherits §4.2's shape — the signed envelope contract verbatim, the
authenticated internal handoff, the blocking bounded-timeout resume await,
and `request_id`-keyed single-flight with no automatic re-execution — and
resolves Q-1 and Q-2 in its R-2 and R-4.

## 7. Relationship to the big-small LLM collaboration pattern (clarification)

The execution runtime is unrelated to the big-small model collaboration
pattern introduced by SPEC-028 — the two live on different layers. The
big-small pattern decides *who thinks*: a small team-hosted model for
pre-triage and redaction, the flagship model for tool-heavy agent turns
(inference layer). The execution runtime decides *how the platform acts*
after the decision is made (action layer) and never involves an LLM. The
only indirect connection: as weaker edge models increasingly propose or
pre-filter actions upstream, the invariant that nothing executes except
via an approved, signed execution request becomes more valuable — the
approval chain, not the worker, is what makes weaker-model proposals
safe.
