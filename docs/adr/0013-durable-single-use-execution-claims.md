# ADR-0013: Durable Single-Use Claims Own Approved Execution Dispatch

## Status

`accepted`

- date: 2026-09-23
- accepted: 2026-09-23
- deciders: workspace operator, through explicit SPEC-063 scope approval
- related specs: [SPEC-063](../specs/SPEC-063-crash-safe-execution/spec.md); extends SPEC-037/038, preserves SPEC-051/054 and SPEC-062
- lineage: ADR-0010 (signed authority provenance), ADR-0011 (composition carries no authority), ADR-0012 (secret delivery), ADR-0008 (delivery evidence)
- scope: records the approved architectural trade-off; implementation details remain in the requested [plan](../specs/SPEC-063-crash-safe-execution/plan.md). Acceptance is not a claim of shipped behavior or authorization for live disruption/deployment.

## Context

Static inspection of v0.42.0 found that execution-runtime suppresses duplicate
handoffs with an in-process registry. Its execution-record store may fall back
to memory, and receipt persistence follows the gateway call on a best-effort
basis. The caller can write a timeout receipt before the worker obtains a result;
first-write-wins presentation storage then retains the timeout.

These are verified implementation boundaries, not reproduced incidents. A worker
restart or overlapping process cannot consult another process's registry. A
missing receipt, transport error, or missing audit event cannot establish that
an external target did nothing. A target mutation and its local receipt cannot
be committed in one transaction across arbitrary browser, HTTP, and infrastructure
tools.

The operator approved a reliability slice prioritizing failure/crash proofs,
durable admission, explicit uncertainty, and no automatic mutation retry. The
platform remains human-led: recovery does not create new approval authority.

## Decision

A committed Postgres single-use claim, bound to both execution identity and the
approved call, owns the right to make at most one worker dispatch attempt. A
consumed or ambiguously committed claim is never reassigned or automatically
retried; recovery is read-only evidence collection, not replay.

1. **Durable admission is mandatory.** Verify the authenticated handoff, complete
   signed request, argument digest, authority provenance, and signed deadline
   before consuming the claim. Only a process that received its commit
   acknowledgment may dispatch. Postgres failure cannot enable memory-backed
   mutation execution. Process-local coordination is never the authority.
2. **Identity binds the approval.** Protect both `execution_id` and
   `(confirm_id, call_id)` with immutable signed-content digests. A reminted ID
   cannot execute the same approved call again. Distinct calls under a valid
   flow remain distinct, individually bound executions.
3. **Availability is deliberately sacrificed in ambiguous windows.** A crash
   between claim and send can leave an unexecuted call permanently consumed.
   Timeouts, restarts, clock expiry, and shutdown do not prove cancellation or
   release that right. No lease takeover, tool retry, or native fallback is added.
4. **Observations are distinct from target truth.** Caller wait expiry is not a
   terminal worker receipt. Retain late validated results and conflicting
   observations. A tool report—even a successful report—is not independent
   verification of the target's business state. Uncertainty becomes visible no
   later than 120 seconds after claim without a background executor.
5. **Uncertainty stops continuation.** Enforce run stopping before additional
   automatic mutations, including resumed approved batches and flow signing.
   Late results and metadata-only duplicate responses do not restart a run or
   release held secret deliveries. Read-only investigation keeps existing gates;
   any fresh mutation keeps existing policy/HITL and requires accounting for
   possibly still-running work.
6. **Validity bounds cleanup.** New executable envelopes carry protocol version
   and signed expiry with a first-dispatch lifetime at most 900 seconds.
   Postgres time enforces the boundary with no expiry grace. Retain protection
   and bounded evidence at least 30 days after expiry, independently of session
   deletion. After cleanup, an expired envelope still cannot obtain a claim.
7. **Recovery does not persist replayable secrets.** Store signed metadata,
   digests, claim ownership, bounded observations, and receipts—not raw arguments,
   tokens, passwords, delivery handles, full outputs, or snapshots. Duplicates
   return status metadata, never reconstructed original output. Owner visibility
   does not extend the approver inbox's access.
8. **Cutover is coordinated and mutation-disabled.** Refuse legacy executable
   requests while retaining historical receipt bytes. Stop old execution-capable
   processes and account for unresolved work before enabling matching consumers.
   Downgrades and database restores keep mutations disabled until recovery checks
   and old request validity windows are satisfied. An old binary or missing
   ledger snapshot is not a safe executable rollback.
9. **Prove the boundary with failures.** Real Postgres and independent processes,
   deterministic crash barriers, independently counted gateway/target effects,
   and negative controls are required. Mock-only tests and model prose do not
   establish dispatch safety. Live sample acceptance supplements these proofs
   under separately approved environment/action scope.

## Alternatives Considered

- **Keep process-local single-flight and best-effort receipts** — rejected as an
  authority boundary: neither persists dispatch ownership across process loss.
- **Use a durable receipt alone as an idempotency check** — rejected: the target
  may act before a receipt exists; absence is not permission to execute again.
- **Expiring leases, automatic retries, or queue takeover** — rejected for this
  slice: an expired owner may still act, and arbitrary targets provide no common
  idempotency/fencing contract. A queue would not solve that ambiguity.
- **Exactly-once business transactions across tools** — not promised: connector
  internals and remote target transactions are outside the local database commit.
- **Persist raw request/result payloads for restart replay** — rejected: creates
  a durable secret-bearing replay surface and does not establish remote outcome.
- **Use audit delivery as the execution oracle** — rejected: the current sink is
  asynchronous and unavailable events do not establish no execution. A durable
  audit outbox remains a separate candidate.
- **Rolling mixed-version mutation-enabled deployment** — rejected: a legacy
  worker can bypass the new ledger. One desired replica alone is not a proof.

## Consequences

- Approved-call duplicate protection survives supported worker restarts and
  new-version overlap; independent evidence explains lost/late responses.
- Postgres availability and the enforced protocol become mutation dependencies.
  Some safe-but-unexecuted calls require human investigation and fresh approval.
- At-most-one worker dispatch is narrower than exactly-once target effect. Remote
  work can continue after local timeout, process loss, or a stopped run.
- Retained safety metadata can outlive a deleted session; user-visible history
  deletion cannot be used to reset execution permission.
- Protocol, recovery consumers, run stopping, and secret-release interlocks must
  ship together. Release/restore procedures become part of the safety boundary.
- This decision does not authorize MCP, execution scaling/queues, a complete
  backup system, automatic compensation, or a cross-session semantic deduplicator.
