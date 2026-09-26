# SPEC-063: Failure-Test Matrix

- status: `delivered — 0.43.0; V7 full root make verify green (campaign 791 passed, 2 deselected, exit 0); historical T-37 791 and corrected F-35 five paths; V1/V3/V5/V6 daemon-instability runs retained`
- companions: [approved spec](spec.md), [frozen implementation plan](plan.md), [tasks and actual asserting tests](tasks.md)
- baseline: static inspection of v0.42.0, 2026-09-23
- scope: failure-first implementation and local disposable verification authorized;
  isolated live acceptance separately authorized on 2026-09-25 in `spec063-acceptance`.
  Shared development/production faults remain unauthorized. Plan and ADR-0013 remain frozen.

## Proof Model

A passing receipt or a plausible assistant response is not proof of a single
mutation. Every scenario checks the relevant independent counters and facts:

1. Durable dispatch claims keyed by execution ID and approved-call identity.
2. Worker-to-gateway HTTP attempts, counted outside the worker under test.
3. Target-side accepted requests and committed effects, counted separately.
4. Durable observations/receipts, fetched through a fresh process after restart.
5. Owner-visible state, agent continuation, and secret-delivery availability.

The deterministic target increments a counter on **every** mutation. It must not
hide a duplicate by implementing an idempotent set-state operation or by sharing
the worker's in-memory state. The gateway/target and their counters survive worker
termination. The acme-admin leg uses revision deltas and independent state reads;
its state must not be reseeded or its process restarted between before/after reads.

Use deterministic barriers, not timing-only sleeps, at these boundaries:

| Barrier | Injection point |
|---|---|
| B0 | Before claim transaction |
| B1 | Claim committed, before the worker can send |
| B2 | Gateway has accepted the request, before target mutation |
| B3 | Target mutation committed, before gateway response |
| B4 | Worker received a result, before receipt transaction |
| B5 | Receipt committed, before handoff response reaches the agent |

A lost commit acknowledgment is injected separately from a rolled-back transaction.
Process crashes must use genuinely separate worker processes against real Postgres;
reconstructing an in-memory registry inside a unit test is supporting coverage only.
A fault proxy may discard replies without discarding the request. It may never
retry a mutation on behalf of the test client.

## Scenario Matrix

Rows F-01–F-34 and F-36 have been executed green both as development-stage/harness
targeted proofs and, subsequently, together as the single gated full deterministic
campaign (T-37): **791 passed, 2 deselected (the two `baseline_red` controls), exit 0**,
with 20× schedule seeds on the repeated/race rows and all 60 `commit_wire` proxy
variants passing. The actual asserting node IDs and evidence locations are recorded
in the [tasks](tasks.md) scenario-to-test map. F-35 was separately authorized and
its corrected five-path live campaign passed; the earlier held-secret harness
failure remains retained. Expected counts below are verified assertions, not
claims about the current release or overall delivery completion.

| ID | Requirement criteria | Scenario / injected fault | Required assertion |
|---|---|---|---|
| F-01 | R-1a, R-3c, R-4a | Valid action request; no faults | One claim, one gateway attempt, one target effect, validated durable worker receipt; identity, arguments digest, and original correlation agree. |
| F-02 | R-1a, R-4a, R-6b | Missing handoff/signing credentials; invalid caller/signature/schema; changed arguments | Zero gateway attempts and target effects; structured pre-dispatch refusal; no forged claim or authority. Parameterize every refusal. |
| F-03 | R-1b | Concurrent identical handoffs within one process and across two processes | Exactly one gateway attempt/effect; duplicate waits are bounded and end in current metadata, not another invocation. |
| F-04 | R-1b, R-6b | Reuse execution ID with changed tool/args/owner/decider/provenance/expiry; remint ID for same confirmation/call | Collision rejected; original immutable identity and claim unchanged; zero additional gateway attempts. |
| F-05 | R-1b, R-1c, R-3c, R-6a | Successful call; evict all local cache entries; restart worker; repeat handoff | Durable metadata replay only; total attempt/effect count stays one; no fabricated original output, secret handle, or automatic dependent write. |
| F-06 | R-1a, R-2a, R-2b | Postgres unavailable at startup/B0; wrong backend; missing schema/failed constraint | Zero dispatches; no memory fallback; readiness non-success with actual backend; liveness independent. Each failure is tested independently. |
| F-07 | R-1a, R-1c, R-2b | Claim commit succeeds but acknowledgment is lost | Ambiguous owner sends nothing; a later process sees the consumed claim and never takes over. Target count remains zero; UI may remain unknown. |
| F-08 | R-1c, R-3d | Crash at B1 | No target effect; claim survives; restart/replay sends nothing; unknown becomes visible within 120 seconds. No false certainty that the target never ran based only on the claim. |
| F-09 | R-1c, R-3a, R-4b | Pause owner at B1 beyond the observation deadline, then resume it | No second owner or retry; late original attempt can still occur; timeout is not treated as cancellation; dependent mutations remain stopped. |
| F-10 | R-1c, R-3a, R-3d | Crash at B2, then release the gateway/target | Gateway/target may finish once; restarted worker never re-dispatches; absent result is unknown, not rejected. |
| F-11 | R-2b, R-3a, R-4b | Commit target at B3, drop gateway reply | Target effect equals one; worker reports unknown and preserves claim; no blind tool retry, native fallback, or next mutating step. |
| F-12 | R-2b, R-2c, R-3a | Postgres fails at B4, including a lost receipt-commit acknowledgment | Already observed target effect is not undone; no durably-complete claim without a verified persisted receipt; restore DB and verify no redispatch. If receipt actually committed, recover it by read. |
| F-13 | R-3b, R-3c, R-5a | Lose handoff reply at B5 or terminate agent after B5 | One durable result remains; session reload recovers it through a fresh process; caller wait expiry cannot overwrite it; no tool re-execution. |
| F-14 | R-3b, R-5a | Agent wait expires first; worker later records result | Both timeout observation and later signed receipt remain; current state becomes result-recorded; original turn/card anchoring preserved. |
| F-15 | R-3a, R-3c | Timeout/read disconnect, malformed JSON, wrong result shape, forged receipt, wrong execution ID or outcome digest | Potential-send cases report uncertainty and block continuation; none masquerades as pre-send rejection or verified success. |
| F-16 | R-3a, R-5d | Gateway HTTP error; valid tool failure after partial target effect; `http.post` tool success with upstream 500 | HTTP/tool/business outcomes remain distinct; failure never proves no effect; handover and agent-facing facts require verification. |
| F-17 | R-3b, R-6c | Duplicate identical receipt, then conflicting signed result | Identical observation is idempotent; conflicting result preserved as an integrity conflict; no silent last-writer-wins success or new dispatch. |
| F-18 | R-2c, R-5a | Status read fails while ledger DB is unavailable | Owner sees status unavailable, not zero executions or success from a fallback memory store; normal read-only tool routing is unchanged. |
| F-19 | R-4a | Deny approval; let pending approval expire; lose valid browser-flow authority | Denial/approval expiry produces zero gateway attempts; stale flow authority produces zero target mutations, including when refusal occurs at the gateway after worker dispatch. No flow widening or held-secret reveal. Cover action and flow cases separately. |
| F-20 | R-4a, R-4b | Duplicate a flow-auto-signed call, then deliver an unknown result before later writes | Duplicate consumes no second browser step; later automatic writes/batch continuation cannot dispatch; no additional card or ID used to evade the stop. |
| F-21 | R-4b, R-5d | Agent restart after unknown outcome; resume run with stale ALLOWED/flow state | Durable uncertainty survives process loss and blocks automatic mutation continuation; read-only investigation is still governed normally. |
| F-22 | R-4b | Two calls already in flight when one becomes unknown | Report both attempts independently; no assertion that the other was canceled; calls not yet dispatched are blocked before send. |
| F-23 | R-4c, R-6a | Generated password held across unknown outcome, failed receipt write, metadata replay, and late success | No Copy-password release or email send triggered by these paths; original handoff expires safely; no secret/handle in new evidence. Happy-path delivery still occurs only under existing approved-success conditions. |
| F-24 | R-5a, R-6b | Owner reload, foreign owner, decider inbox, forged execution ID | Owner gets bounded history/current facts; foreign owner denied; inbox remains decision-only; possession of an ID never authorizes access or execution. |
| F-25 | R-5b, R-5c | Correlation chain with a duplicate request and audit sink outage | Original header request ID reaches gateway; execution ID remains correlation-only; duplicate request ID does not overwrite original; ledger survives audit loss; missing audit is inconclusive. |
| F-26 | R-5d, R-6c | New shift-summary/incident digest and authoring projections with unknown/late/conflicting outcomes | Uncertainty is preserved, not dropped or counted as definitive failure/success; old published artifacts unchanged; no unsupported successful authoring origin. |
| F-27 | R-6a | Canary secrets in args, result strings, malformed response, exception text and URL; oversized metadata | No canary, token, plaintext argument, delivery handle, or snapshot in ledger/history/log/audit/card; bounded closed projection; canonical signing inputs unmodified. |
| F-28 | R-7a | Signed deadline boundaries, future timestamp, oversized lifetime, expired/legacy request | Database-time bounds enforced exactly; missing expiry or version refused; expiry does not cancel a previously claimed attempt; zero new attempts for expired calls. |
| F-29 | R-1b, R-7a | Delete session, run presentation sweeps and local cache eviction, replay a still-valid request | Dispatch ledger protection survives all three; replay never sends again; deleting a session does not resurrect authority. |
| F-30 | R-7a | Advance clock through ledger retention and remove eligible old rows | Expired signed replay remains rejected without recreating a claim; retention cannot reset the execution right. Test approved-call ID remint refusal within the validity horizon. |
| F-31 | R-6c, R-7b | Migrate legacy records containing success, timeout, and open requests | Existing signed bytes remain readable; no invented claim/outcome certainty; old executable protocol refused at cutover. |
| F-32 | R-7b, R-7c | Mutation-disabled cutover; two new-version workers overlap; graceful drain and abrupt termination | No mixed-version mutation window; duplicate protection holds through overlap; bounded shutdown does not release claims or claim to cancel remote work. |
| F-33 | R-7b | Attempt binary downgrade or restore a pre-claim DB snapshot | Mutation admission remains disabled pending recovery/cutover checks; no silent return to process-local execution. Document the lost-evidence limit and required expiry wait. |
| F-34 | R-7c | Store failure, duplicate storm, conflict, unknown-age transition, receipt-write failure | Health and bounded-cardinality metrics distinguish these conditions; no secret/user/execution-ID labels; no extra executions caused by monitoring. |
| F-35 | R-5c, R-8b | Approved isolated acme-admin normal, denied/expired, and interrupted journeys | Independent revision/state reads establish actual target effects; approval/receipt/card/replay evidence agrees where known and explicitly differs where uncertain; no unapproved sample reseed or target restart. |
| F-36 | R-8a, R-8c | Run harness without real-Postgres/process prerequisites; map every criterion | Required integration target fails with actionable setup error, never silently skips; actual asserting test names and evidence are recorded before delivery. |

## Test Layers and Execution Authority

| Layer | Purpose | Required before delivery | Authorized now? |
|---|---|---|---|
| Unit and contract tests | Validation, projections, state rules, signatures, expiry bounds | Yes | Authorized and exercised; results in tasks. |
| Real-Postgres multiprocess harness | Claims, constraint races, commit ambiguity, crashes, independent target counts | Yes | Authorized; full deterministic campaign green. |
| Cross-product deterministic integration | Agent/worker/gateway behavior, flow stop, masking, receipt/status handling | Yes | Authorized; asserting nodes and results in tasks. |
| Portal and digest tests | Owner scope, history, unavailable state, late results, derived evidence | Yes | Authorized automated tests; not live browser acceptance. |
| Isolated acme-admin acceptance | Deterministic live product seams and independent target verification | Yes, under an explicitly approved test environment/action list | Separately authorized in spec063-acceptance; corrected five-path campaign green, first failure retained; isolated resources removed. |
| Shared development or production faults | Disrupt existing users/services | Not required by this spec | Not authorized. |

The [implementation plan](plan.md) records required commands, disposable
infrastructure, fault mechanisms, and stage gates; [tasks](tasks.md) maps all
36 rows and 26 criteria to planned implementation and asserting-test targets.
Required real-database tests belong to an explicit verification target with a
prerequisite check; they may not be represented by a passing mock-only test suite.
No LLM is needed for the deterministic failure proofs. A live conversational check
is supplementary evidence and cannot replace the counters and invariant tests.

## Evidence Record for Each Executed Row

When implementation is approved, record:

- spec criterion and matrix ID; asserting test name and command;
- code/image version, schema version, DB version, worker process identities;
- isolated target, authorized action, before-state, fault barrier, and timing;
- claim count, gateway attempt count, target accepted-request count/effect count;
- execution/confirmation/call IDs and original versus duplicate request IDs;
- durable observation sequence, receipt verification, owner projection/reload;
- continuation count and secret-release assertion, without any secret value;
- result: pass / fail / blocked, evidence location, and any remaining uncertainty.

A blocked or unexecuted row is not a pass. Every acceptance criterion must map to
at least one actual asserting test in the eventual `tasks.md`. Requirements that
prove safety need a negative-control check: bypassing the claim, allowing takeover,
or treating a lost response as non-execution must make the relevant test fail.

## Implementation-Plan Test Refinements

These refine execution of existing rows, not their approval criteria or pass status:

- F-02/F-04/F-15/F-27/F-28 are parameter families: every identity, schema,
  signature, transport, size, canary, and deadline variation must assert its own
  dispatch/effect outcome. A single representative case is not completion.
- F-07/F-12 each cover a real commit with lost acknowledgment **and** an actual
  rollback, using an independent DB observer; they are not interchangeable faults.
- F-09 covers the original paused owner resuming after the observation deadline,
  plus an explicit-run-stop variant. A deadline is not cancellation or takeover.
- F-20/F-21 also cover failure to persist a stop, agent restart with stale ALLOWED
  or flow state, registered-but-unclaimed work, and lost original output after a
  durable receipt. None may remint a run automatically to continue mutating.
- F-22 covers two outstanding target operations even though the plan serializes
  new same-run worker HTTP exchanges: target operation A is accepted but still
  active, B loses its response, and C must not dispatch. Include multiple-claim
  recovery fixtures and the final-send/stop ordering race. Do not infer remote
  serialization/cancellation from local HTTP serialization.
- F-23 covers the actual middleware release point and normal successful delivery,
  not merely absence of a handle in a synthetic recovery object.
- F-24/F-26 include paging/observation caps, stale polling response isolation,
  unavailable state, foreign metadata limits, and unchanged published artifacts.
- F-31/F-33 include interrupted migration, mismatched external admission epoch,
  and supported downgrade/restore wrapper refusal. Out-of-band snapshot rollback
  is not automatically detectable from data inside the restored snapshot.
- Repeat F-03/F-07/F-08/F-09/F-12/F-14/F-20/F-22/F-32 at least 20 times with
  recorded schedules. A failure remains evidence; rerunning to green is not proof.
- F-36 requires negative-control detection, complete selected-row coverage,
  independent counters, and failing missing-prerequisite/zero-test behavior.

## Final Root Verification — Passed (V7)

The 0.43.0 candidate's full root `make verify` **passed end to end on V7**
(campaign **791 passed, 2 deselected, exit 0** in 25:29; no `make … Error`; clean
owner-scoped teardown). V7 ran after an operator-authorized OrbStack engine restart
recovered the wedged daemon and the ownership-verified cleanup settled V6's stranded
owner. Artifact `.workspaces/spec063-evidence/20260926T075723Z-dc4d688d8cfc/`; root
log `.workspaces/spec063-close-verify-7.log`. The earlier attempts below are retained
unchanged as the honest daemon-instability path to that pass; none is relabeled or
overwritten:

- **V1** `.workspaces/spec063-close-verify-1.log` /
  `spec063-evidence/20260925T164648Z-950adb785d82/`: campaign **85 failed, 695
  passed, 2 deselected, 12 errors**. First failure a Postgres connection timeout;
  teardown exceeded its Docker watchdog. Owner `2d239b8e-…` later cleaned
  ownership-verified after the daemon was restored.
- **V3** `.workspaces/spec063-close-verify-3.log`: campaign **790 passed, 1 failed**
  — a single load-sensitive `barrier B2 acknowledgment missing` flake at
  `test_kill_after_gateway_acceptance[5-B2]`; the same node re-run in isolation
  passed in 8.05s. Not relabeled as a pass.
- **V4** `.workspaces/spec063-close-verify-4.log`: failed in the agent-platform suite
  on a **test-only** calendar-rot fixture (`test_cap_evicts_oldest_per_owner`,
  hardcoded `2026-08-27` aged past the 30-day retention sweep). Fixture fixed to use
  relative timestamps; product behavior was correct and unchanged.
- **V5** `.workspaces/spec063-close-verify-5.log`: all product/portal suites passed;
  campaign exited **2** at its Docker `prerequisites()` probe before creating any
  container (nothing stranded). A bounded `docker version` then answered in 0.04s.
- **V6** `.workspaces/spec063-close-verify-6.log` /
  `spec063-evidence/20260926T045801Z-c0b1f7996c28/`: campaign **569 failed, 209
  passed, 2 deselected, 14 errors**. Ran ~22% green, then the disposable Postgres
  became unreachable — first failure `barrier B1 acknowledgment missing`, then
  `psycopg.errors.ConnectionTimeout` on nearly every DB node. A post-run bounded
  `docker version` timed out at 15s, confirming the daemon wedged under sustained
  multiprocess load. Stranded owner `cad4ee02-c59b-4f55-a7c6-269e0cb573e0`
  (project `spec063-cad4ee02c59b4f55a7c6269e0cb573e0`) was cleaned ownership-verified
  after the authorized engine restart (`.workspaces/spec063-evidence/20260926T075359Z-604a30c2d2a0/cleanup.json`).

The campaign code across V3/V5/V6/V7 is byte-identical, so the V1/V5/V6 cascades were
daemon instability, not a product regression — confirmed by V7 reproducing the
historical T-37 green result once the OrbStack engine was restarted (with explicit
operator authorization, since it affects the shared local cluster) and V6's owner was
settled. All failed evidence stays immutable; the sample's 168 local tests, contract
parity, and every product/portal/static gate passed in V7 too. See
[tasks](tasks.md#delivery-closure-evidence) for exact commands/results, owner IDs,
closure regressions, and the full 26-criterion traceability join.



## F-35 Executed Acceptance and Cleanup

- First campaign `.workspaces/spec063-evidence/s6-20260925T151650Z-f3f94c6b06/`:
  four passed, held-secret failed. The harness burned its positive-control handle
  by probing it as a wrong owner, matching the existing delivery-buffer contract.
  That failed JSON/JUnit remains unchanged.
- Corrected campaign `.workspaces/spec063-evidence/s6-20260925T154521Z-31a1b25bd7/`:
  **five passed**, exit 0. Separate handles prove owner redemption once and
  destructive wrong-owner refusal; product behavior was not weakened. Same
  namespace, image tags, target process, and witness; no target restart/reseed.
- Actual assertions: `samples/acme-admin/execution_acceptance_live.py::run_campaign`
  with `execution_acceptance_probe.py` product seams. Corrected revision deltas:
  **1, 0, 1, 1, 1**; claims and new wire attempts agree. Interrupted work remains
  unknown with a consumed claim; owner reload is metadata-only; replay emits no
  second mutation or secret release. No live portal/conversational claim is made.
- Independent read-only reconciliation retained in
  `.workspaces/spec063-evidence/s6-reconciliation-ed54bf8a-a31d-499f-9112-7b556cf85fc6.json`:
  **10 intents, 8 claims, 8 attempts/completions, target revision 0→8** across both
  campaigns; other users unchanged; original artifact hashes and missing failed-path
  ledger facts preserved without converting the failed campaign to a pass.
- Isolated namespace/RBAC removed; protected shared dev/gateway metadata and local
  configuration/plan/ADR hashes unchanged. Keycloak inventory empty: nothing was
  created or modified there. Cleanup archive:
  `.workspaces/spec063-evidence/s6-setup-ed54bf8a-a31d-499f-9112-7b556cf85fc6.json`.
- Local regression suites: sample **168 passed**, delivery contract **17 passed**.
  See [tasks](tasks.md) for commands, actor/image/epoch scope, and remaining gates.
  Documentation checks alone are not runtime proof; the runtime proof is the V7 full
  root campaign recorded above (791 passed, exit 0), which closes delivery.
