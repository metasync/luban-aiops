# SPEC-063: Implementation Plan

## Status and Approach

- Scope approved by the operator on 2026-09-23; this is the requested implementation plan, not authorization to deploy or inject live faults.
- Baseline: v0.42.0. Runtime implementation and every failure scenario remain pending.
- Companions: [spec](spec.md), [failure matrix](failure-test-matrix.md), [tasks](tasks.md), [ADR-0013](../../adr/0013-durable-single-use-execution-claims.md).
- Build the deterministic failure harness first. Deliver contracts, durable admission, honest outcomes, run stopping, and recovery as one coordinated protocol cutover. Do not enable a partially upgraded mutation path.
- Keep the existing synchronous worker, Postgres service, policy/HITL, and secret-delivery boundary. There is no queue, takeover, automatic tool retry, or exactly-once target guarantee.

## Grounded Integration Points

Paths below are repository-relative. New files named later are planned, not present implementation.

| Concern | Existing integration point | Required change |
|---|---|---|
| Worker admission | `products/execution-runtime/src/execution_runtime/api/routes/handoff.py`, `services/single_flight.py` | Replace cache-owned permission with a committed, single-use claim. A cache may never authorize or return a secret-bearing duplicate result. |
| Worker output | `services/executor.py`, `services/execution_records.py` in execution-runtime | Distinguish local transport uncertainty from a validated gateway report; completion becomes durable before an authoritative response. |
| Lifecycle | execution-runtime `app.py`, `core/config.py`, `core/metrics.py`, health routes | Actual-backend readiness, admission disable, bounded drain, no fallback executor. |
| Signing | agent-platform `services/execution_signing.py`, `runtime_kernel.py` | Version/expiry/run identity in both action and flow builders; preserve canonical digests. |
| Invocation | agent-platform `tools/gateway_tools.py`, `services/execution_worker_client.py` | Gate before handoff and return typed original-result versus metadata-only outcomes. |
| Permission/evidence | agent-platform `services/kernel_middleware.py` | Check stop before the `ALLOWED` short-circuit; do not use plain tool success as a secret-release permit. |
| Durable recovery | agent-platform `services/execution_records.py`, `api/v2/routes.py`, `schemas/v2.py` | Read the new ledger independently of legacy presentation rows; replace exception-to-empty-history behavior. |
| Derived facts | agent-platform `services/shift_summary.py`, `services/incident_report.py`, authoring-trace consumers | Preserve unknown, conflict, unavailable, and late reports without claiming independent target verification. |
| Portal | `products/operator-portal/web-ui/app/src/api/sessions.ts`, `chat/ChatView.tsx`, `chat/usePendingDecisionPoll.ts`, `stream/models.ts`, `stream/decoder.ts` | Owner recovery display, decided-card refresh, vocabulary parity, no retry or secret replay. |
| Gateway | tool-gateway `api/routes/tools.py` and its invocation models/audit details | Forward original request header and execution correlation only; no new authority. |
| Operations | root `Makefile`, `shared/platform-ops/gitops/`, affected guides | Required disposable failure target and mutation-disabled migration/restore procedure. |

## Design Per Requirement

### R-1: Durable Admission and Duplicate Prevention

#### Tables and ownership

Use the existing sessions Postgres database, with new tables unrelated to session cascade deletion. The canonical migration is planned at `shared/shared-contracts/sql/execution-ledger-v1.sql`; the migration runner lives in execution-runtime. Runtime processes validate the schema version/constraints and never create or repair it implicitly.

| Table | Keys and immutable data | Mutable data / authority |
|---|---|---|
| `execution_runs` | `run_id` UUID primary key, `session_id`, `owner_user_id`, server-generated start time | Monotonic `stopped_at`, bounded stop reason; never reset a stopped run. Agent creates the run; agent/worker can stop it. |
| `execution_intents` | `execution_id` UUID primary key; unique `(confirm_id, call_id)`; complete signed v3 request metadata, canonical request digest, original request ID, registration time | None. Agent registers before sending; worker requires an exact registered match. This is preparation, not dispatch permission. |
| `execution_dispatch_claims` | `execution_id` primary key/FK to intent; unique `(confirm_id, call_id)`; request digest, random claim-owner UUID, DB `claimed_at`, `observe_by`, `retain_until` | None. Only the worker claim transaction creates the row; no executable/reset/lease field. |
| `execution_observations` | observation UUID primary key; execution ID/FK to intent; signed closed metadata, content digest, DB insertion sequence/time | Append-only. Agent writes only agent observations; worker writes only worker observations. |
| `execution_observation_state` | execution ID primary key/FK to intent | Bounded counters, reserved-slot occupancy, monotonic integrity/overflow flags, first conflicting digest; updated atomically with observations, never used to grant a dispatch permit. |
| `execution_protocol_state` | singleton schema version and deployment admission epoch UUID | Migrator creates it disabled; operational enable is explicit and requires matching process configuration. |

- Implement worker storage in a new `services/execution_ledger.py`; add an agent-side `services/execution_recovery.py` for registration, agent observations, run stopping, and reads. Do not import one product's runtime package into another. Shared schemas/SQL plus parity tests define the contract.
- Intent includes owner/decider, session/run, tool, approval kind, argument digest, request signature, signed times, and protocol version. These are the existing signed metadata plus new protocol fields, never arguments or credentials. `request_digest` is the existing canonical SHA-256 over the entire signed request, including its signature; signers and both readers use the same input.
- Enforce UUIDs where generated by Luban; bound other IDs to 256 characters, tool names to 128, SHA/HMAC hex to 64. New code rejects invalid bounded fields before logging. Add SQL checks for version, digest form, timestamp ordering, and lifetime; validate closed observation JSON in both writers and with database shape/size checks.
- Preserve original identity on every conflict. A new execution ID for the same confirmation/call is a conflict even with equivalent arguments. One execution ID with different signed bytes is a conflict. No upsert updates identity.
- Registration commit must be acknowledged before handoff. A registration error stops the local run and sends nothing. Registration is idempotent for identical bytes; it cannot re-authorize a claim. Register only mutation intents, inside the serialized invocation lane before handoff; builders can sign a batch without registering unscheduled calls. Read-tier approved calls retain their existing direct gateway path.

#### Claim transaction

1. Authenticate the handoff; validate the complete v3 schema, HMAC, argument digest, delegated credential presence, and configured gateway before reaching admission.
2. Begin a bounded Postgres transaction; lock the run row. Require exact registered intent/owner/run identity. Look up both unique identities: an existing identical claim returns metadata only, even for a stopped run or expired request. A differing intent/claim returns an identity conflict. Neither returns a dispatch permit, and status retrieval does not require admission to be enabled.
3. For a new claim require matching admission epoch, enabled durable admission, and a non-stopped run. Every earlier dispatched intent must have an accepted original response before a new call can dispatch; an unresolved earlier intent/claim, including a recorded result without agent acceptance, prevents continuation. Order intents by DB insertion sequence, not caller timestamps.
4. For an absent claim, evaluate `clock_timestamp()` after lock acquisition: `requested_at <= db_now < expires_at`, `0 < expires_at - requested_at <= 900 seconds`. Insert the claim with `observe_by = claimed_at + 120 seconds` and `retain_until >= expires_at + 30 days`; insert the signed worker claim observation in the same transaction.
5. Commit with `synchronous_commit=on` and require Postgres durability settings (`fsync` and `full_page_writes`) enabled in the supported environment. Return an in-process, nonserializable dispatch permit only after commit acknowledgment. A connection/commit exception returns no permit, even if a later read finds the row. No retry of the claim-to-send operation.
6. The owner passes the permit once to the final send gate described under R-4. Consume the permit before initiating the HTTP request. Cancellation, timeout, failed send, shutdown, or cache removal cannot recreate it.

Use `INSERT ... ON CONFLICT DO NOTHING` plus explicit reads of both keys, not exception-driven blind retries or check-then-insert without constraints. Use READ COMMITTED with unique constraints and row locking; transaction failures fail closed. Cap connection/statement/lock waits at two seconds for admission and status operations. Do not hold a claim transaction open over a network call.

`single_flight.py` is removed from the handoff authority path. Duplicates perform one bounded durable read and return immediately; they do not join an unbounded future, reconstruct output, or reuse a cached secret-bearing response.

Tests: F-01–F-08, F-28–F-30, including a real two-process unique-key race and negative controls that deliberately bypass the claim.

### R-2: Fail-Closed Persistence and Health

- Production admission is Postgres-only. Memory stores remain dependency-injected test doubles; environment selection of memory never enables the deployed worker's handoff path.
- Add `EXECUTION_ADMISSION_ENABLED=false` by default, plus `EXECUTION_ADMISSION_EPOCH` supplied separately from the database. Agent receives the matching epoch/configuration; all new requests sign the epoch. Missing/mismatched epoch or disabled admission refuses first dispatch.
- A configured but unavailable backend is represented by an unavailable durable store, not a memory replacement. Health can stay alive while initialization/probe retries bounded metadata operations. No tool runs as a probe.
- `/health/live` remains process-local. `/health/ready` returns 503 when admission is disabled, Postgres/schema/epoch is unhealthy, or credentials/gateway configuration are missing. Return configured backend, actual backend, schema/protocol readiness, and admission enabled state, without DSNs or secrets.
- Add a bounded independent recovery-read path in the agent. A ledger outage yields `availability: unavailable`; historical data may be labeled historical/stale but is not substituted for a successful current lookup.
- Receipt persistence is mandatory for `original_result`. One initial metadata write plus at most two retries within five seconds is allowed, retaining the same signed bytes/observation ID. Read after ambiguous commit before retrying. The tool itself is never called again.
- Failure to establish persisted completion returns `outcome_unknown` with `durability: unconfirmed`; a transient tool report may be represented only by safe enum metadata. Do not return raw transient output to the model, release a secret, or mark authoring success.
- The worker may finish a previously committed attempt during DB loss; it must retain the consumed right and report uncertainty if it cannot persist its result. No DB recovery action replays work.

Tests: F-06, F-07, F-12, F-18, F-34. Test committed-but-unacknowledged writes separately from transactions that actually rolled back.

### R-3: Honest Outcomes, Observations, and Response Validation

#### Shared wire contracts

| Planned contract change | Exact direction |
|---|---|
| `execution-request.schema.json` v3 | Closed v3 branch with required `protocol_version: 3`, `expires_at`, `run_id`, `admission_epoch`, and explicit `approval_kind`, plus all existing fields. Historical legacy branch remains valid for reading only; the executable worker explicitly selects v3. |
| `execution-observation.schema.json` (new) | Version 1 signed, closed observation envelope described below. |
| `execution-recovery.schema.json` (new) | Current projection plus bounded observation page, availability, replay marker, integrity/verification flags. |
| `execution-handoff-response.schema.json` (new) | Discriminated response variants: `original_result`, `status_only`, `refused`, `unavailable`; never infer a variant from HTTP status alone. |
| `execution-receipt.schema.json` | Preserve the current receipt schema/signature/canonical bytes. Worker receipts are wrapped/referenced by new observations; no rewriting historical timeout receipts. |
| `agent-session.schema.json`, `agent-stream-event.schema.json`, `session-evidence.schema.json` | Add optional closed recovery metadata to execution rows/tool-result frames and top-level execution availability to session detail. Preserve old rows/frames. No new SSE event type is necessary. |

The new observation signs every field except `signature`, using the existing canonicalization and HMAC scheme. Required fields: `observation_version: 1`, UUID `observation_id`, `execution_id`, `run_id`, `request_digest`, `source` (`agent` or `worker`), `kind`, `observed_at`, original `attempt_request_id`, current `request_id`, bounded `reason_code`, and signature. A `worker_result` additionally carries the unchanged signed receipt, its canonical digest, claim-owner ID, and safe tool-status metadata. Other kinds cannot carry a receipt or arbitrary data.

Kinds are `claim_committed`, `wait_expired`, `transport_uncertain`, `pre_dispatch_refused`, `worker_result`, `result_persistence_unconfirmed`, `response_accepted`, `run_stopped`, and `duplicate_seen`. HMAC attribution remains the existing mutually trusted service-key model, not cryptographic nonrepudiation between services sharing a key. No new policy action or audit event type is introduced.

| Source | Allowed observation kinds |
|---|---|
| `agent` | `wait_expired`, `transport_uncertain`, `pre_dispatch_refused`, `response_accepted`, `run_stopped` |
| `worker` | `claim_committed`, `transport_uncertain`, `pre_dispatch_refused`, `worker_result`, `result_persistence_unconfirmed`, `run_stopped`, `duplicate_seen` |

Closed `reason_code` vocabulary: `none`, `unauthorized`, `bad_request`, `signing_unavailable`, `signature_invalid`, `args_digest_mismatch`, `request_missing`, `identity_conflict`, `protocol_unsupported`, `request_expired`, `request_not_yet_valid`, `lifetime_invalid`, `admission_disabled`, `epoch_mismatch`, `store_unavailable`, `schema_invalid`, `claim_commit_unconfirmed`, `gateway_not_configured`, `credential_missing`, `wait_expired`, `transport_error`, `response_invalid`, `receipt_unconfirmed`, `run_stopped`, `predecessor_unresolved`, `send_lock_unavailable`, `shutdown`, `integrity_conflict`, and `metadata_replay`. Gateway free-text/error strings never extend this enum.

The recovery object requires `recovery_version: 1`, `availability` (`available`/`unavailable`/`not_found`), nullable `state` (the four SPEC-063 dispatch states), execution/confirmation/call/session/run IDs when known, original `attempt_request_id`, `request_digest`, signed request/expiry times, nullable claim/deadline times, DB `as_of`, `replay`, `run_stopped`, `integrity_conflict`, `target_verification_required`, nullable `receipt`, `observations`, `observations_truncated`, and nullable `next_observation_cursor`. Only registered-but-unclaimed rows carry `preparation_state: registered` with null dispatch state before their uncertainty deadline. Unavailable/not-found states have null dispatch state/receipt and no purported current observations. The closed handoff wrapper also carries `protocol_version: 3`, `kind`, incoming `request_id`, nullable recovery, and `durability` (`confirmed`/`unconfirmed`/`not_applicable`); only `original_result` can carry raw `result`, only `refused` carries the closed refusal code. Historical payloads remain on their legacy branch.

- Identical observation IDs/bytes are idempotent. Different bytes for the same ID are refused and set a durable integrity-conflict marker; retain the candidate's bounded digest/reason rather than overwrite. Commit the conflict marker before returning the refusal; do not roll it back by throwing the rejection inside the transaction. Different valid worker-result observations for one execution are retained and compared.
- Same receipt bytes, including timestamp/signature, count as the same final result. Retrying a metadata write never rebuilds the receipt with a new completion timestamp.
- Cap ordinary observations to 64 per execution and each serialized envelope to 8 KiB. Reserve space for the claim, first worker result, timeout, stop, acceptance, and first conflicting result; duplicate storms cannot exhaust those slots. Further duplicates/conflicts update bounded counters and a permanent overflow/conflict flag, not unbounded JSON. Expose the bounded/truncated fact.

#### Deterministic projection

Priority is: unavailable read → `availability: unavailable` with no asserted current state; verified conflicting worker results → `outcome_unknown` plus `integrity_conflict`; one verified durable worker result → `result_recorded`; uncertainty observation or elapsed `observe_by` → `outcome_unknown`; consumed claim → `dispatch_claimed`; positively evidenced refusal with no consumed claim → `not_dispatched`. A registered intent without a result/claim is pending handoff, not proof of no effect; after its bounded wait it is unknown. A missing row is `not_found`, never `not_dispatched`. Scope `not_dispatched` to the positively refused submission: a refusal of altered/unauthenticated bytes cannot label the registered original call. For a registered original refusal, atomically stop its run and verify no claim before exposing that state, so a delayed original handoff cannot later obtain permission. If that durable refusal cannot be established, show uncertainty instead.

The 120-second claim deadline is computed on every durable read, so restart recovery needs no scheduler. Also bound registered-but-unclaimed uncertainty at 120 seconds after registration. Store `observe_by`; expose `as_of` using DB time. Readiness/metrics may refresh projections but never create execution work.

A late worker result changes current state without deleting a caller timeout. Once any stop condition occurred, late completion never clears the run stop. `target_verification_required` stays true for recorded tool reports; this slice has no generic independent-target-verification attestation.

#### Handoff response and agent behavior

- `original_result` is 200 only for the original owner response after acknowledged receipt persistence: v3 protocol, execution/request digest, original request ID, signed worker observation/receipt, current recovery metadata, and the original result in transit. Map a validated gateway `success` to receipt `succeeded`, validated gateway error code `TIMEOUT` to receipt `timeout`, and other validated error/denied reports to `failed`; these record tool reports, not proof about target effects.
- `status_only` is 200 for a completed duplicate, 202 for pending/unknown; `replay: true`, recovery metadata only, no `result` field. A GET recovery read is never an original response.
- `refused` uses 400/401/403/409/410 as appropriate and a bounded reason. Invalid unauthenticated input never gets a trusted attributed observation. Claim collisions describe the rejected incoming request, not a claim that the original call did nothing.
- `unavailable` uses 503 with no false execution conclusion. An agent may know its own missing local config prevented a send; after any possible send, an arbitrary 4xx/5xx, broken body, canceled task, or connection error is uncertainty unless a validated durable record resolves it.
- The agent verifies schema/variant, both signatures, request digest, execution/run/epoch identity, original request ID, tool name, receipt status consistency, and `canonical_digest(original_result) == receipt.outcome_digest`. Do this before redaction changes a display copy. A copied receipt for a different execution cannot close this call.
- Executor transport errors/timeouts/non-tool HTTP responses are typed uncertainty, not synthetic gateway reports. A schema-valid tool failure is a recorded tool report, even if it followed a partial effect. An `http.post` success envelope with upstream HTTP 500 remains that fact, not business success.
- Replace the v3 branch of the kernel's caller-authored receipt closure with observation handling; keep legacy/read-tier presentation behavior explicitly separate. Never sign a terminal worker result from a timeout frame.

Tests: F-09–F-18 and F-27; corruption tests cover every binding field and both directions of canonicalization/signature parity.

### R-4: Run Stop and Secret-Delivery Interlocks

#### Durable run identity

The server creates `run_id` for the human-started root turn; parked approval, resumed batches, flow authority, and automatic sub-skill continuation inherit it. Persist the reference with confirmation and agent state before signing. Flow authority retains its originating run across later turns while reused. A restore/resume missing that identity fails closed; never mint a replacement for restored `ALLOWED` calls. UUIDs are internal metadata, never model arguments.

An explicitly new human request after a stop can start a new run only through the existing approval path, with stale flow authority cleared and the unresolved-prior-attempt warning preserved. This is not an automated retry, a reset of the old run, or proof the old target stopped. No extra confirmation alone inside the stopped run can clear it.

#### Enforcement order and concurrency

1. A shared in-process run latch is set synchronously at the invocation boundary on uncertainty, invalid original response, metadata replay with unavailable output, or failed durable completion—before yielding any result/event to the kernel.
2. Append the attributed agent observation and set the durable run stop before returning control when persistence is available. On DB or stop-lock failure, keep the local latch set and return only a blocked/uncertain result; future mutation checks fail closed. Prepared intents and unresolved claims survive restart even if the stop write failed; no subsequent call can treat that gap as a clean run.
3. Consult the stop in permission middleware **before** the `ALLOWED` shortcut, in the flow signer, in the actual mutating tool closure, in worker claim admission, and at the worker's final send boundary. Read-tier closures stay on their current path and normal policy gates.
4. Order final sends and durable stops using a Postgres session advisory mutex keyed by `run_id`, on a dedicated bounded connection. Acquire it before the final current-state check; hold it through the bounded gateway exchange. A run-stop writer takes the same mutex. Lock failure gives no send. Claimed calls waiting for this mutex recheck all stop/predecessor evidence before attempting HTTP, including absence of an accepted original response for an earlier intent. They are not a persisted queue and cannot be taken over; a two-second acquisition timeout burns their claim without dispatch and stops continuation. Worker stop/result metadata is committed before releasing the mutex. Agent stop persistence may time out while an already-dispatched exchange holds it; the local latch and unaccepted-predecessor rule remain closed until the idempotent stop write lands. Use a stable signed 64-bit SHA-256-derived lock key; a hash collision only serializes unrelated runs. Connection loss never restores a permit or authorizes a second sender.
5. Current-version worker HTTP exchanges within a run are therefore serialized at this final boundary. Different runs remain independent. Claiming can overlap, but no second send bypasses an established stop. The final gate is the dispatch-start linearization point; work already past it can still finish remotely. DB locks are not target-side fencing, and process suspension/network loss cannot be advertised as remote cancellation.
6. Agent calls normally serialize the mutation lane per run as well, before registering/sending the next call, and persist `response_accepted` only after validating the original response. Acceptance binds the exact receipt digest and is permitted only for a currently non-conflicting result and non-stopped run. Failure to persist acceptance gives no continuation or secret-release permit. A durable worker result with no agent acceptance cannot automatically drive a dependent write after agent restart. Metadata-only recovery stops that continuation; stop reasons never disappear when a late receipt or delayed acceptance arrives.

A worker's own elapsed observation deadline does not revoke its consumed claim or prove it stopped. An original paused owner may still send when resumed if no explicit stop or unresolved predecessor bars it; no other owner can. Test both a paused original that later proceeds and one refused by an explicit run stop.

F-22 must also exercise two already-running downstream operations: the target can acknowledge asynchronous operation A while its effect is still pending, then accept B whose response is lost. Record A and B independently and block C; do not claim that serial HTTP exchanges made remote operations serial or canceled A. Include defensive projection tests with multiple already-claimed/unresolved calls in one run.

#### Secret-release permit

Change `ToolEvidenceMiddleware` so held-delivery release requires a typed in-process permit from the **original**, validated, durably recorded successful response plus a non-stopped run; a tool frame's `status: success` and membership in `EXECUTION_REQUESTS` are insufficient. The permit is consumed once and never persisted or reconstructed from status. Check the shared run latch again immediately before emission.

On uncertainty/metadata replay/persistence failure, discard held handles through the existing owner-scoped best-effort discard path and preserve expiry fallback. Do not expose handles in recovery observations. Late success is display-only. Email remains a separate governed write and must pass the same stop gate. Keep standalone generation, existing one-time redemption, and ordinary successful gated delivery behavior intact.

Tests: F-19–F-23; include stale `ALLOWED`, flow provenance, resumed parallel batches, a failed stop write plus restart, lost original response after durable success, and secret-release race at the actual middleware seam.

### R-5: Owner Recovery, Correlation, and Derived Evidence

- Extend the existing owner-checked session detail rather than exposing a worker API to the portal. Add `execution_recovery_availability` (`available`/`unavailable`) and optional recovery objects on execution rows, including flow calls sharing a confirmation. Fetch ledger facts independently of whether a legacy presentation write succeeded.
- Paginate recovery through the existing session detail query: optional opaque execution cursor and page size (default 50, maximum 100); each execution includes up to 20 observations and an opaque continuation cursor. Cursors bind session, owner, and keyset position. An optional execution filter selects an observation page only after the session owner check. Keep original turn/card anchoring; never place results into the approver inbox.
- Foreign/nonexistent session remains the existing anti-enumeration refusal. An execution ID, request header, or decider identity does not bypass ownership. A deleted session has no portal recovery access even though its protective ledger is retained.
- Add owner-facing labels for claimed, unknown, recorded tool report, late report, conflict, and unavailable. Show times, IDs, replay/missing-output explanation, history truncation, and independent-verification guidance. No retry, reset, mark-success, or reveal-old-password button.
- Extend decided-card polling to unsettled executions: refresh every two seconds while visible for at most 120 seconds per observation window; then show refresh guidance. Resume one refresh on visibility/reload. Stop on teardown/session change; never background-poll another owner's session. A late durable result remains readable later even after polling ends.
- Send `x-request-id` as a header on agent→worker→gateway with the original attempt ID; forward a bounded `x-execution-id` header for gateway audit correlation. Duplicate handoffs have their own HTTP request ID in their observation but never replace the original. These headers grant no rights.
- Existing execution audit event types carry a bounded state/reason/observation ID. Audit failure never erases the ledger or substitutes for an outcome oracle; do not add an outbox in this slice.
- Share one recovery reducer across session and newly generated digest/incident/handover projections. Keep legacy counts separate from new `tool_reports`, `uncertain`, `conflicting`, and `unavailable` facts. Preserve the existing metadata-only foreign digest allowlist; no observation history/owner details leak into foreign coverage. Do not modify already published document snapshots.
- Authoring projections only accept the normal verified original result for successful origin observations. Unknown, unverified, replay-only, and conflicting state cannot confer successful verification or usable replay output.

Tests: F-13/F-14, F-18, F-24–F-27. Test pagination, permission checks before lookup, stale polling responses, and API outage without hiding historical facts.

### R-6: Minimization and Contract Parity

- Close every new object (`additionalProperties: false`) and reject oversized fields before durable writes. Store enum reasons rather than exception strings, URLs, parameter summaries, browser snapshots, recipient values, or connector payloads.
- Original gateway output is permitted only in the original in-memory response path and its existing governed redacted projections; the ledger contains only its canonical digest/receipt and allowlisted status facts. Raw arguments and delegated tokens remain in transit/in memory only.
- Normalize invalid correlation headers to a generated safe ID; do not log an untrusted header verbatim. After identity validation, UUIDs/digests may be logged; no per-identity metric labels.
- Worker runtime needs JSON Schema validation: add `jsonschema` to its runtime dependencies and re-lock that product when implemented. Bind every consumer's enums, optional recovery fields, signature vectors, and closed projections to shared contracts through tests. Add portal fixture/vocabulary tests and digest parity tests, not just backend schema tests.
- Keep historical receipt JSON unchanged. Legacy executable requests are never accepted by the v3 worker, even if their signature verifies. Do not infer authority from the new run or correlation fields.

Tests: F-02/F-04, F-15/F-17, F-24/F-26/F-27/F-31. Scan ledger snapshots, logs, audit payloads, session/card render, and failure-harness artifacts for unique secret canaries without printing canary values into the report.

### R-7: Retention, Migration, Cutover, and Operations

- Retain claims, intents, run stops, and reserved recovery observations until at least 30 days after the latest dependent request expiry. No session FK cascade. Only a dedicated bounded sweep may remove eligible ledger data; never reuse the presentation store's requested-at sweep. Run records outlive all dependent claims/intents.
- Validate signed expiry even when a row has been swept. A replay cannot obtain a new validity window by changing its ID under the same approved-call identity. A new approval is a different action, not a replay mechanism.
- Legacy presentation rows are read in place, labeled legacy/unproven-dispatch as appropriate; migration creates no synthetic claims and never upgrades an old timeout to no-effect certainty. New facts are not written into the old first-write-wins row as an authority source.
- Keep one desired worker replica; set `Recreate` for the cutover posture. Still prove new-version process overlap safety. On SIGTERM refuse new handoffs, mark unready, allow existing work a 35-second drain within a 45-second pod grace period, then terminate without releasing any claim. Gateway timeout defaults to 30 seconds and must be at most 30 for this slice; agent handoff defaults to 60 and is capped at 120.
- Bound readiness/metrics DB reads. Publish actual admission availability, duplicate/conflict totals, unresolved count and oldest age, write failures, and drain state. Metric labels are fixed status/reason enums only. Unknown-age calculation uses DB time; observation does not reset a deadline.

#### Coordinated upgrade procedure (future execution, not run now)

1. Record approved environment/action scope and evidence version. Disable writes at the existing gateway mutation gate, disable new agent mutation admission, and refuse new worker handoffs. Keep investigative reads available.
2. Inventory old in-flight attempts and held deliveries. Drain within the existing budget; classify lost/ambiguous work as unresolved. Stop all old execution-capable agent/worker processes; do not infer downstream cancellation from pod termination. Preserve old receipts and unresolved evidence.
3. Run the additive schema migration transaction with admission disabled. Verify constraints, permissions, expiry query, empty/current epoch state, and rollback-on-migration-failure using the same checks as the harness.
4. Deploy matching agent/worker/portal/gateway versions with admission still disabled. Provision a new admission epoch independently of the DB and rotate the internal handoff credential so an old process cannot enter the new worker. Preserve receipt verification material; do not rotate away the only key needed for historical verification.
5. Validate process/image inventory, schema/read paths, absence of old executable consumers, read-only recovery, and the recorded failure-test evidence. Re-enable only after explicit operational approval and the required unresolved-work accounting; run the authorized isolated acceptance journey.

#### Rollback and restore boundary

A binary rollback first disables gateway mutations and stops the worker; old binaries cannot be trusted to honor a new flag. The deployment wrapper refuses a mutation-enabled version downgrade and requires an explicit disabled recovery mode. Do not automatically enable during deploy/startup.

A DB restore is also a disabled recovery operation: retain evidence outside the restored snapshot, stop possible old senders, rotate the epoch/handoff credential, wait out every previously issued request's maximum 900-second window measured from the last possible issuer shutdown (and account for clock disagreement), and investigate possibly running downstream work. Only then can fresh, separately approved actions be considered. A same-era snapshot cannot be detected reliably by a flag stored inside that snapshot: the operational interlock and external epoch rotation are mandatory. Arbitrary out-of-band restores or direct old-binary deployment cannot be made safe by this ledger alone. F-33 must test the supported wrapper refusal and a restored database against mismatched external epoch; never claim universal rollback detection.

Tests: F-28–F-34, with retention boundary, stopped-run retention, session deletion, migration interruption, drain, epoch mismatch, and process-overlap assertions.

### R-8: Failure-First Proof Harness

#### Harness layout and isolation

Create `products/execution-runtime/tests/failure/` with `conftest.py`, `support/` process/barrier/proxy/target helpers, and the asserting test modules named in [tasks](tasks.md). Add a root `execution-failure-test` target calling `shared/platform-ops/e2e/execution-failure-test.sh` (new). This is a disposable local integration harness, not the cluster-facing `make e2e` target.

- Require Docker, Compose v2, uv, and available product environments. Use a uniquely named Compose project, Postgres 16 (matching the deployed major), a separate target/counter process, a gateway fault proxy, and at least two independent worker processes. Record resolved image digest/server version; never use a shared DB URL or implicit kube context.
- Bind control endpoints to loopback/the disposable network only. Use generated test credentials, ephemeral ports/volumes, and an explicit ownership label. Cleanup touches only resources created by that harness instance; preserve sanitized evidence on failure. No production fault endpoints or runtime environment switches enable test barriers.
- Worker `create_app`/ledger/executor seams accept injectable no-op lifecycle hooks. The test-only launcher supplies barriers B0/B1/B4/B5; gateway/target helpers supply B2/B3. The production image must not include a callable test-control route. The actual production claim/executor code runs unpatched in the positive proof.
- Pin worker HTTP transport to no retries and no redirects, with a wall-clock gateway exchange cap of 30 seconds in addition to per-operation HTTP timeouts. Forbid generic client/proxy retry middleware on mutation calls; a failed metadata operation may retry only within its separate bounded budget.
- The target persists accepted-request count, effect count, and append-only operation IDs independently of the worker. Each mutation increments a counter even when its desired value repeats. A separate gateway/proxy counter records inbound attempts; read these from outside the worker. Target state survives worker/agent death.
- Use parent-controlled barriers and explicit acknowledgments. Kill the worker/agent OS process at the selected boundary and assert a new PID after restart; do not substitute a Python exception for a process crash. Have bounded waits/watchdogs and report the exact barrier on failure.
- For claim/receipt commit ambiguity, a test connection wrapper calls the real Postgres commit and then raises before returning acknowledgment. Pair that with a database TCP proxy test that drops the commit response, and independently observe committed rows from a fresh connection. Rollback tests fail before commit; label the two cases distinctly.
- Test proxy faults independently on agent↔worker and worker↔gateway legs: dropped response after request delivery, disconnect during read/write, malformed/truncated bodies, delayed headers, bounded HTTP error responses. Proxies have no retry behavior.
- Use injected DB-clock expressions only in the test store adapter for retention/deadline tests; never adjust the host/shared DB clock. Also test the production `clock_timestamp()` path with requests straddling real DB-time boundaries and the exact inequality in unit/SQL parity tests.
- Cross-product legs launch the real agent/worker/gateway application code with deterministic scripted tool decisions (no LLM/network model dependency), existing delegated-auth fixtures, and disposable browser/secret-delivery dependencies. Do not mock away policy/HITL or the middleware release seam in those legs.

#### Mandatory assertions and repetitions

Every F-row records claim count, gateway attempt count, target accepted/effect count, original/replay request IDs, durable observations from a fresh process, owner recovery, continuation count, and secret-release count where applicable. Counts are checked before and after resuming delayed components; a transient zero before releasing B3 is not proof of no effect.

Run concurrency/race rows F-03/F-07/F-08/F-09/F-12/F-14/F-20/F-22/F-32 at least 20 iterations with recorded deterministic schedule seeds. A later passing rerun does not erase a failure. Negative-control variants in the test-only launcher bypass claim enforcement, permit takeover, misclassify a lost reply, or allow replay-based secret release; the corresponding assertions must fail. Negative controls never become production feature flags.

`execution-failure-test` must fail, not skip, on missing prerequisites, zero selected tests, missing scenario/parameter coverage, failed counter collection, or failed negative-control detection. Default product unit runs may exclude this integration directory explicitly; the repository delivery gate must include the required target, so a unit-only green run cannot deliver SPEC-063.

#### Planned commands and gates

These commands are the implementation's required entry points, **not commands executed during planning**:

```sh
make -C products/execution-runtime test
make -C products/agent-platform test
make -C products/tool-gateway test
make -C products/platform-gateway test
npm --prefix products/operator-portal/web-ui/app test
npm --prefix products/operator-portal/web-ui/app run build
make execution-failure-test
make verify
```

Wire `execution-failure-test` and a portal test/build target into root `make verify` when implemented. Retain existing contract/policy/overlay/version/password/secret-delivery-demo gates. No integration skip toggle is accepted as a release pass. Capture JUnit plus a sanitized JSON evidence manifest beneath an ignored per-run `.workspaces/spec063-evidence/` directory; tasks records durable artifact references and code/image versions at delivery.

F-35 is a separate `make execution-acceptance` entry point, planned in the acme-admin demo suite. It requires an explicitly supplied environment authorization record, target URL/namespace, permitted account/actions, and independent before/after revision reads. It refuses implicit defaults to the shared development cluster. Normal, denied/expired, interrupted, owner reload, and secret-delivery paths must all pass; do not reseed/restart the sample target between observations. Live conversational checks supplement, never replace, deterministic assertions.

## Sequencing and Exit Gates

| Stage | Work and dependencies | Exit gate |
|---|---|---|
| S0 — proof skeleton | No product behavior changes; compose/process/barrier/counter harness, scenario manifest, failing invariant tests, negative controls | Demonstrate that the harness detects a duplicate and distinguishes committed versus rolled-back writes. Missing prerequisites fail loudly. |
| S1 — contracts and storage | S0; v3 schemas, migration, ledger constraints, signing parity, fail-closed health | F-01–F-08/F-28–F-31 storage/contract portions pass against real Postgres. |
| S2 — worker outcomes | S1; consumed permits, no cache authority, real gateway validation, observations, bounded metadata retry/drain | F-09–F-18/F-32 worker portions pass with process death at every B barrier. |
| S3 — run and secret safety | S2; registration, run identity/stop, final send gate, original-response acceptance, release permit | F-19–F-23 and restart/lost-response variants pass at actual invocation and middleware seams. No mutation-enabled deployment before this gate. |
| S4 — recovery consumers | S3; owner session/card, correlation, digest/authoring, redaction | F-24–F-27 and late-result/unavailable portal tests pass; UI and backend contracts agree. |
| S5 — operational proof | S4; retention, migration/rollback/restore/drain tests, metrics, full repetition campaign | F-28–F-34/F-36, all 26 criterion mappings, root verification, and negative controls pass. |
| S6 — authorized acceptance/delivery | S5 plus separate environment/action approval | F-35 independent target evidence; living docs/release traceability complete. No unexecuted row counts as delivered. |

Implementation tasks remain unchecked until their assertions run. Update the matrix with actual node IDs/results as tests land; planned names are not evidence. A discovery requiring weaker guarantees, new authority, secret persistence, or unsafe cutover returns to scope review. Release version remains unassigned until the implementation/delivery phase.
