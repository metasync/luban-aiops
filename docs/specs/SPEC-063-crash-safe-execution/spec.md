# SPEC-063: Crash-Safe Execution and Outcome Reconciliation

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-23
- approved: 2026-09-23 by the workspace operator
- delivered: 2026-09-26 as 0.43.0 (full root `make verify` green; see below)
- release slice: R5 — operational reliability; delivered
- release version: 0.43.0; original/S6 evidence baseline v0.42.0
- related ADRs: ADR-0008 (delivery traceability), ADR-0010 (signed authority
  provenance), ADR-0011 (composition carries no authority), ADR-0012 (secret
  delivery), [ADR-0013](../../adr/0013-durable-single-use-execution-claims.md)
  (accepted durable single-use dispatch authority)
- lineage: extends SPEC-037/038; preserves SPEC-051/054 approval semantics and
  SPEC-062 plus v0.42.0 secret-delivery safeguards
- authorization: implementation and local failure-first verification were separately
  authorized after scope/plan approval. Isolated S6 in `spec063-acceptance` was separately
  authorized, executed, reconciled, and removed. The operator then authorized local
  documentation/version/verification closure, and separately authorized an OrbStack
  engine restart to recover a wedged local Docker daemon blocking the final campaign.
  No commit, push, shared deployment, or repeat live acceptance is authorized.
- delivery gate: **passed** — the full root `make verify` is green on V7 (campaign 791
  passed, exit 0; all product/portal/policy/version/secret gates and clean teardown);
  see [delivery evidence](tasks.md#delivery-closure-evidence). Earlier daemon-wedge runs
  (V1/V5/V6) and the V4 test-only fixture fix are retained as honest history.

## Summary

Make the approved-mutation path safe to interpret after duplicate handoffs,
process loss, database failure, and lost responses. A durable, single-use dispatch
claim prevents the same approved call from being dispatched again; explicit
uncertainty and retained late observations let operators investigate without
being told that a timeout means the target did nothing.

This is an at-most-one **worker dispatch attempt per approved call**, not an
exactly-once business-effect guarantee. Some failures deliberately sacrifice
execution availability to prevent a possible duplicate mutation.

The frozen [implementation plan](plan.md) records the approved design and
failure-first sequence. The living [failure-test matrix](failure-test-matrix.md)
and [tasks](tasks.md) map all 26 criteria and 36 scenarios to actual asserting
nodes, commands, artifacts, and retained pass/fail results. Historical proof and
S6 acceptance do not override a failed final delivery gate.

## Motivation and Evidence

Static inspection at v0.42.0 established the following historical boundaries;
the drafting exercise itself did not reproduce faults. Subsequent implementation
and failure evidence are recorded in tasks, not retroactively substituted here.

| Historical v0.42.0 boundary | Evidence | Consequence addressed here |
|---|---|---|
| Single-flight is an in-process dictionary with age/count eviction | [single_flight.py](../../../products/execution-runtime/src/execution_runtime/services/single_flight.py) | A restart or another process does not inherit dispatch ownership; cache eviction is not an authorization boundary. |
| The worker calls the gateway before closing the durable record | [handoff.py](../../../products/execution-runtime/src/execution_runtime/api/routes/handoff.py) | A receipt is evidence after execution, not a durable pre-dispatch claim. |
| Store initialization can fall back to memory; receipt writes are best-effort | [worker record store](../../../products/execution-runtime/src/execution_runtime/services/execution_records.py), [agent record store](../../../products/agent-platform/src/agent_service/services/execution_records.py) | Configuring Postgres does not guarantee durable admission. |
| The first receipt wins, including a caller timeout; later completion is logged | [handoff.py](../../../products/execution-runtime/src/execution_runtime/api/routes/handoff.py), [runtime_kernel.py](../../../products/agent-platform/src/agent_service/runtime_kernel.py) | The session record can retain a timeout after the worker obtains a result. |
| Handoff transport errors and malformed responses become worker-unavailable errors | [execution_worker_client.py](../../../products/agent-platform/src/agent_service/services/execution_worker_client.py) | Failures before send and loss of an answer after send need different certainty. |
| The worker puts correlation in JSON while the gateway route reads a header | [executor.py](../../../products/execution-runtime/src/execution_runtime/services/executor.py), [tools route](../../../products/tool-gateway/src/tool_gateway/api/routes/tools.py) | End-to-end correlation must be asserted, not inferred from field names. |
| Audit emission is asynchronous, with logged failures | [audit_emitter.py](../../../products/execution-runtime/src/execution_runtime/services/audit_emitter.py) | Missing audit events do not establish that dispatch or a target effect did not occur. |
| The base deployment sets one replica without an explicit update strategy | [worker deployment](../../../shared/platform-ops/gitops/dev-k8s/base/execution-runtime/execution-runtime-deployment.yaml) | One desired replica is not proof that two processes never overlap during replacement. |

At drafting, the [operator guide](../../guides/approval-and-hitl.md) described double
execution as structurally impossible, broader than the then-current process-local
protection. The living guide now qualifies that claim with the durable boundary;
this does not reopen or rewrite delivered SPEC-037/038.

## Approved Design Decisions

The operator approved these scope decisions on 2026-09-23. They remain the
requirements; implementation proof and delivery status are recorded separately
above and in tasks (delivered 2026-09-26 as 0.43.0 on the V7 full root gate).

### D-1: Durable authority, synchronous execution

Use the existing Postgres state infrastructure for a worker-owned dispatch ledger.
The ledger, not the process-local cache or the agent's presentation record, owns
permission to dispatch. Keep the long-running single worker and bounded synchronous
handoff. No execution queue, retry scheduler, worker pool, or per-action Kubernetes
Job is introduced. In-memory stores remain test doubles, not deployed mutation
admission backends.

### D-2: Burn-on-claim, with no takeover

Atomically commit a unique dispatch claim before the gateway request can be sent.
Only the process that knows its claim commit succeeded may make that one attempt.
A commit whose acknowledgment is lost does not authorize sending. A claimed call
is never reset to executable, leased to another worker, or automatically retried.

A crash after claim but before send can therefore leave a call unexecuted yet
unsafe to retry automatically. This is intentional. A timestamp or expired
heartbeat may change the displayed certainty; neither releases the claim.

Protect both `execution_id` and `(confirm_id, call_id)` so a reminted execution ID
cannot rerun the same approved call. Store an immutable digest of the complete
signed request and its identity fields. A collision with different request
content is rejected, not joined. Fresh calls under an approved browser flow have
distinct call IDs and remain distinct executions.

### D-3: Separate attempt observations from target truth

Retain immutable, attributed observations rather than letting a caller timeout
permanently close the authoritative result. The session projection distinguishes:

| Execution state | Meaning | May this claim dispatch again? |
|---|---|---|
| `not_dispatched` | Positive evidence of rejection before dispatch authority was consumed | No automatic retry; a new attempt requires the existing approval path. |
| `dispatch_claimed` | A durable claim was consumed; the attempt may be running | No. |
| `outcome_unknown` | Dispatch may have happened, but a trustworthy result is unavailable | No. |
| `result_recorded` | The worker durably recorded a validated gateway result and signed receipt | No. |

An absent record is not positive proof of non-execution: a delayed handoff may
still arrive. Failure to read the store is shown as status unavailable, never an
empty successful history. A gateway result is a tool report, not independent
verification of target state. In particular, `http.post` can return a successful
tool envelope containing an upstream HTTP error, and an error can follow a partial
effect. Recovery guidance must preserve these distinctions.

### D-4: Bounded validity and independent retention

New signed requests carry an explicit protocol version and signed `expires_at`.
The approved maximum first-dispatch window is **900 seconds** after `requested_at`,
with no extension on replay or reminting of the same approved call. Both action
and flow signing paths use it. This is a dispatch deadline, not an extension of
HITL or browser-flow authority; all existing authority checks still apply.

Postgres time is the authority at the atomic claim: require
`requested_at <= database_now < expires_at` and a positive lifetime no greater
than 900 seconds. Clock disagreement fails closed rather than widening the
window. No clock-skew grace is added to the expiration boundary. Expiration does
not cancel an attempt that already consumed its claim.

Claims and recovery observations are retained at least **30 days after request
expiry**, independently of session deletion, presentation-store sweeps, cache
eviction, and worker restarts. After that horizon, an expired signed request must
still be rejected before it could create a fresh claim. Ordinary session deletion
can remove user-visible history without releasing dispatch protection.

### D-5: Recovery is read-only in this slice

The existing owner-scoped session surface gains current execution state and its
bounded observation history. Reconciliation means collecting late authoritative
results and supporting an operator's independent target check, not providing a
button to declare success, reset a claim, retry, or approve retrospectively.

A fresh mutation remains a fresh action under existing policy/HITL. Operators must
first account for the prior attempt and any still-running downstream work. An
unknown outcome remains unknown when evidence cannot resolve it. Cross-session
semantic deduplication and machine-verifiable proof that arbitrary external work
has stopped are not claimed.

### D-6: Minimal durable evidence, no durable secret-bearing replay

Persist signed request metadata/digests, dispatch ownership, timestamps, bounded
reason codes, signed receipts, and immutable observation metadata. Do not persist
raw arguments, bearer tokens, passwords, delivery handles, full gateway output,
or browser snapshots in the dispatch ledger. Existing separately governed evidence
stores retain their own redaction and limits.

A duplicate handoff returns recorded execution metadata; it does not reconstruct
a missing original tool result, replay a secret delivery, or masquerade as a fresh
successful tool call. Status-only replay must stop automatic continuation that
requires the unavailable original result.

### D-7: Compatibility through a gated cutover

Historical requests and receipts remain readable and verifiable with their
original meaning. The new worker refuses legacy executable requests lacking the
new version/expiry fields; legacy envelopes must not bypass the new ledger.

The implementation plan must specify a coordinated mutation-disabled cutover:
drain or classify old in-flight work, stop old execution-capable processes, retain
old unresolved evidence, migrate the ledger, deploy matching consumers, and only
then re-enable mutations. A rolling mixed-version mutation window is unsupported.
Rollback must keep mutations disabled unless the retained ledger and protocol
remain enforced; downgrading to the old worker is not a safe mutation rollback.

## Requirements

Each criterion has an identifier for test traceability. These tests were pending at
scope approval, which declared no criterion delivered; the actual asserting nodes are
now mapped in [tasks](tasks.md) and proven by the V7 full root campaign.

### R-1: Durable admission and duplicate prevention

- **R-1a:** After caller authentication, complete envelope validation, signature,
  argument-digest, and deadline verification, atomically consume a durable claim
  before any gateway invocation. Missing configuration or an invalid request
  cannot invoke the gateway. A lost claim-commit acknowledgment also sends nothing.
- **R-1b:** Concurrent duplicates, separate worker processes, restart replays, and
  cache eviction cause at most one worker-to-gateway dispatch for one approved
  call. A duplicate gets bounded status retrieval, never unbounded waiting or a
  new invocation. Changed content or a reminted ID for an existing approved call
  is rejected without modifying its original claim.
- **R-1c:** A consumed claim is never reclaimed, including after cancellation,
  shutdown, expiration, or an execution error. The protected operation is the
  worker dispatch attempt; connector-internal behavior and target transactions
  must not be represented as exactly-once guarantees.

### R-2: Fail-closed persistence without false outcome claims

- **R-2a:** Deployed mutation admission requires the configured, actual Postgres
  backend and a successful claim transaction. Startup failure never silently
  enables a memory-backed executor. Worker readiness returns a non-success HTTP
  status when durable admission is unavailable and reports actual backend state;
  liveness remains independent of database availability.
- **R-2b:** Database loss or schema/constraint failure before claim causes zero
  dispatches. Database loss after claim does not release the claim. A result whose
  durable close fails is not reported as a durably completed execution; the caller
  receives uncertainty plus any safely distinguishable transient observation.
- **R-2c:** Reads and status retrieval cannot silently substitute an empty memory
  store when the durable store is unavailable. Read-only tools are not routed
  through this new mutation gate. Database recovery requires no mutation replay.
  Retrying an idempotent metadata write is permitted; retrying the tool is not.

### R-3: Honest outcomes, late results, and bounded waiting

- **R-3a:** Only positively established pre-dispatch refusals report
  `not_dispatched`. Timeouts, cancellations, transport disconnects, malformed
  responses, and gateway failures after possible send report `outcome_unknown`
  unless a validated durable result already exists. HTTP status alone is not
  execution evidence, and missing audit events cannot prove non-execution.
- **R-3b:** The agent records its wait expiry separately and cannot author a
  terminal worker result from that timeout. A late worker receipt is preserved
  and becomes the current result without erasing the earlier timeout observation.
  Conflicting purported final results remain visible as an integrity conflict
  requiring reconciliation; neither is silently overwritten.
- **R-3c:** The worker response is validated for schema, signed receipt, execution
  identity, and outcome digest before the agent treats it as authoritative.
  Completed duplicates return metadata explicitly marked as replay, without a
  fabricated tool result or repeated downstream continuation.
- **R-3d:** A live claim with no result becomes visibly uncertain by a documented
  bounded observation deadline, at most 120 seconds after claim. This is not a
  cancellation guarantee or lease expiry. The same projection works after a
  restart, without a background executor or heartbeat-based takeover.

### R-4: Preserve approval and secret-handling safety during uncertainty

- **R-4a:** Both individually approved calls and flow-auto-signed browser writes
  use the durable boundary. Missing approval, denial, expiry, altered arguments,
  and invalid authority provenance retain their existing refusals. Duplicate
  delivery does not consume a second browser step or create new approval authority.
- **R-4b:** Unknown outcomes stop automatic mutating continuation for the affected
  run, including already approved batches and browser-flow auto-signing. This must
  be enforced before another call can dispatch, not only by prompt guidance or a
  delayed UI update. Already-dispatched concurrent work is reported separately;
  the platform cannot undo it. Read-only investigation remains available under
  existing gates. Cross-session business-operation deduplication is out of scope.
- **R-4c:** Unknown outcomes, metadata-only replays, and failed durable completion
  do not release held secret deliveries or auto-resume a workflow on late receipt.
  Preserve owner-only, one-time redemption and fail-safe expiry. A password reset
  that may have succeeded while its delivery was lost requires explicit recovery,
  not re-execution or late automatic revelation of the old secret.

### R-5: Owner-visible recovery and evidence correlation

- **R-5a:** Session detail and the decided confirmation card show current execution
  state, the original attempt/approval IDs, observation times, late-result history,
  and whether target verification is still required. Reloading yields the same
  durable facts. Status unavailable is distinct from no executions. The approver
  inbox remains decision-metadata-only; no new cross-owner access is granted.
- **R-5b:** Forward the original `x-request-id` in HTTP headers through agent,
  worker, and gateway. Carry `execution_id` as correlation metadata at the gateway
  and in existing audit details, never as authorization. Retain each duplicate
  request's own correlation without replacing the original attempt identifier.
  Safe execution facts remain recoverable even if the audit sink is offline.
- **R-5c:** The operator runbook requires inspecting the ledger and available
  target evidence, accounting for possibly still-running work, and independently
  verifying target state before considering a fresh mutation. No retry/reset-claim
  control is added. Missing evidence is explicitly inconclusive.
- **R-5d:** Newly generated handover/digest projections and agent-facing recovery
  results preserve uncertainty and late results rather than treating every
  timeout as a final failure or every successful tool envelope as business success.
  Published historical documents remain unchanged. An unavailable or conflicting
  result must not make an authoring step look successfully verified.

### R-6: Identity, evidence minimization, and contract compatibility

- **R-6a:** Persist the minimum fields in D-6 through a closed, bounded projection.
  Secret-shaped test canaries must be absent from the ledger, observations,
  session/card output, logs, and audit details. Request/receipt digests remain
  based on their defined canonical inputs, not rewritten display projections.
- **R-6b:** Preserve user/decider attribution and signed action/flow provenance.
  Status access uses existing owner/service authorization, not possession of an
  execution ID. Forged correlation fields cannot claim or complete another call.
- **R-6c:** Define explicit shared contracts for the versioned dispatch request,
  recovery projection, and signed observations. Preserve legacy receipt bytes;
  do not reinterpret old timeout receipts as proof of no effect. Add vocabulary
  parity tests in every consumer, including the portal and digest paths. No new
  policy action or audit event type is required; existing execution events carry
  bounded details, while the ledger supplies authoritative recovery state.

### R-7: Retention, cutover, and safe operational posture

- **R-7a:** Enforce D-4's signed lifetime and database-clock bounds at first claim.
  Neither session deletion nor any retention/cache sweep may make a still-valid
  request executable again. After ledger retention ends, expiry validation still
  refuses the old request. No compatibility fallback accepts expiry-less requests.
- **R-7b:** Exercise a migration from legacy records without fabricating dispatch
  claims or certainty about historical outcomes. Existing immutable receipts stay
  readable. The cutover and rollback procedure in D-7 is a mandatory delivery gate;
  reverting binaries or restoring an old database snapshot cannot silently reopen
  mutation admission. After a restore, mutations stay disabled until unresolved
  work is accounted for and old request validity windows have elapsed.
- **R-7c:** Keep one desired worker replica and bounded shutdown/drain behavior.
  Correctness must nevertheless hold for overlapping new-version processes.
  Publish admission-store health, duplicate/conflict counts, uncertain-execution
  counts/age, and receipt-persistence failures without secret values or per-user
  metric labels. Do not scale workers or introduce a queue in this slice.

### R-8: Failure-test proof and delivery discipline

- **R-8a:** Implement the companion matrix with deterministic barriers around
  claim, send, target commit, receipt persistence, and response delivery. The
  concurrency/restart tests use real Postgres and independent worker processes;
  fake-store unit tests alone do not establish the invariant. Count gateway
  requests and target effects independently of model prose and receipt status.
- **R-8b:** Add isolated acme-admin acceptance for normal completion, denied/expired
  approval, and interrupted execution after deterministic harness validation.
  Verify account revision/state through an independent read. No resets, disruptive
  restarts, or fault injection on the shared development cluster are authorized by
  this scope approval or planning request. Record the approved environment and
  permitted actions before live use.
- **R-8c:** Before delivery, every criterion maps to actual asserting tests in
  `tasks.md` per ADR-0008, with required integration tests failing rather than
  silently skipping when prerequisites are missing. Run the applicable product,
  contract, portal, and repository verification gates. Update living operator,
  configuration, deployment, and product documentation, and record the architectural
  trade-off in an accepted ADR. Scope approval is not a delivery claim.

## Non-Goals

- MCP exposure, consumption, or tool extraction; MCP remains parked.
- Exactly-once target effects, transactional composition, automatic compensation,
  mutation retries, lease takeover, or replaying lost browser sessions.
- A distributed execution queue, worker pool, scaling campaign, or throughput work.
- A generic target-state reconciler, manual outcome-edit API, new approval roles,
  a retry button, cross-owner raw-session access, or cross-session semantic dedup.
- A platform-wide durable audit outbox or a complete backup/restore implementation;
  these remain subsequent reliability candidates. Restore safety requirements for
  this execution ledger are still in scope.
- Durable storage of raw tool arguments/results or recoverable secret material.
- Hardening direct external callers of tool-gateway into a signed-execution API;
  the guarantee applies to Luban's approved worker path and is not a gateway-wide
  exactly-once claim.

## Impact

- **Products:** execution-runtime (durable claim, observations, response validation,
  readiness); agent-platform (both signing paths, timeout handling, continuation
  guard, session/digest projections); operator-portal (owner recovery display);
  tool-gateway (correlation metadata). Platform-gateway is affected only where the
  existing session proxy/contract tests need alignment, not by new authority.
- **Contracts:** execution-request, agent-session, and explicit signed-observation /
  recovery schemas; execution-receipt semantics remain backward-readable. Stream
  consumers must carry uncertainty without treating it as a successful tool result.
  Exact wire/schema changes are enumerated in the [implementation plan](plan.md).
- **Storage:** a durable ledger independent of the existing presentation-record
  sweep and session deletion; existing Postgres infrastructure, no new database
  service. No bearer tokens or replayable plaintext argument store.
- **Security:** existing identity/policy/HITL and target authorization remain;
  persistence failure tightens mutation admission. Recovery never grants execution.
- **Deployment:** coordinated, mutation-disabled protocol cutover and explicit
  rollback safety. Local 0.43.0 version/manifest changes are delivered; S6's
  separately authorized isolated deployment was removed. No shared rollout is claimed.
- **Living docs at delivery:** execution-runtime and agent-platform READMEs;
  approval/HITL, configuration, portal, and troubleshooting guides; relevant GitOps
  runbooks; roadmap and specs index; release changelog/notes. Qualify process-local
  safety claims; do not rewrite delivered SPEC-037/038.

## Approval Decisions

The operator approved this decision-complete scope on 2026-09-23 and requested the
implementation plan, explicitly prioritizing testing different failure/crash cases.
Approval accepts these trade-offs:

1. Postgres availability is required for new approved mutations; no memory fallback.
2. A consumed claim is never retried or taken over, including the pre-send crash gap.
3. Signed first-dispatch lifetime is capped at 900 seconds; retention is at least
   30 days after expiry; observation uncertainty is visible within 120 seconds.
4. Recovery is owner-visible and read-only; an unknown result stops automatic
   mutation continuation and never releases a held secret.
5. A coordinated mutation-disabled upgrade is required; legacy executable
   envelopes and unsafe downgrade paths are rejected.

## Open Questions

None left implicit at the scope level. The five decisions above are approved.
The [implementation plan](plan.md) specifies SQL constraints and atomic transitions,
signed-observation wire fields, timeout/cancellation integration, continuation-guard
placement, and required failure-test commands. Implementation and historical proof
are recorded in tasks; the root-verification failures and cleanup recorded there were
closed by the V7 full root gate (see Delivery Gate). Any discovery that changes these
requirements returns to scope review.

## Changelog

- 2026-09-26: **Delivered as 0.43.0.** After an operator-authorized OrbStack engine
  restart recovered the wedged local Docker daemon and the ownership-verified cleanup
  settled the stranded disposable owner, a fresh full root `make verify` passed end to
  end (V7): campaign **791 passed, 2 deselected, exit 0**, with all product suites,
  portal test/build, overlays, policy, version, and secret/password gates green and a
  clean teardown. Status flipped `approved` → `delivered`; Delivery Gate closed;
  spec index and roadmap updated; CHANGELOG promoted from candidate to a dated 0.43.0
  release. The V1/V5/V6 daemon-wedge cascades and the V4 test-only fixture fix
  (a SPEC-039 cap test whose hardcoded date aged past the 30-day retention sweep) are
  retained as honest history; no product assertion was weakened and no failed run was
  relabeled. Frozen plan/ADR hashes unchanged. No commit, push, or shared deployment.
- 2026-09-26: Reconciled living documentation, criterion/test provenance, and local
  0.43.0 candidate versions after authorized S6 acceptance/cleanup. Final root
  campaign failed (85 failures, 12 errors) and Docker cleanup is unconfirmed;
  status stays `approved`, not `delivered`. Frozen plan/ADR and historical evidence
  remain unchanged; no commit, push, or shared deployment.

- 2026-09-23: Operator approved the scope and requested a failure/crash-focused
  implementation plan. Added plan/tasks and accepted ADR-0013; requirements and
  bounds unchanged. Planning only; no runtime implementation or live tests run.
- 2026-09-23: Created as `draft` from the operator-approved reliability-spec
  drafting request and static v0.42.0 implementation evidence. Added the companion
  failure-test matrix. No implementation, live tests, or release authorized.
