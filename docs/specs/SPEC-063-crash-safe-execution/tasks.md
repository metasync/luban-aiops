# SPEC-063: Implementation Tasks and Proof Gates

Task states: `[ ]` pending, `[x]` done. Implementation explicitly authorized after plan approval. S0–S5 previously passed T-37 (**791 passed, 2 deselected, exit 0**); separately authorized S6 passed all five corrected F-35 paths with independent reconciliation and cleanup. Those historical proofs remain retained. **Delivered 2026-09-26 as 0.43.0:** after the candidate's first root verification (V1) failed with **85 failed, 695 passed, 2 deselected, 12 errors** under a wedged local Docker daemon, the retained attempts V1–V6 plus an operator-authorized OrbStack engine restart led to a clean full root `make verify` on **V7 (campaign 791 passed, 2 deselected, exit 0)** with every product/portal/policy/version/secret gate green and clean disposable teardown. See [closure evidence](#delivery-closure-evidence); no failed run is relabeled or replaced by an earlier pass. The scenario map records actual asserting nodes/driver paths. Follow the frozen [plan](plan.md) and living [failure matrix](failure-test-matrix.md).

## S0 / R-8: Establish the Failure Harness First

- [x] T-01 Create disposable Compose/process harness, isolated Postgres 16, independent target/gateway counters, and cleanup ownership guards (`products/execution-runtime/tests/failure/support/`; R-8a).
- [x] T-02 Add acknowledged barriers B0–B5, real process kill/restart, agent and gateway fault proxies, bounded watchdogs, and commit-ack-loss versus rollback injection (R-8a).
- [x] T-03 Add scenario manifest F-01–F-36, evidence/JUnit output, schedule seeds, and prerequisite/zero-test/missing-scenario failures (`shared/platform-ops/e2e/execution-failure-test.sh`; R-8c).
- [x] T-04 Prove negative controls are detected: duplicate dispatch, takeover, false no-effect classification, replay-based secret release. Test-only wiring must be absent from production control surfaces (R-8a).
- [x] T-05 Wire planned `make execution-failure-test`; demonstrate red tests against the unsafe behavior before claiming ledger success (R-8a/R-8c).

### S0 executed evidence (2026-09-23)

- `uv run --offline --frozen --project products/execution-runtime python products/execution-runtime/tests/failure/run.py --stage harness`: **33 passed**, two baseline-red nodes intentionally deselected. Asserting nodes are in `tests/failure/test_harness_contract.py`; manifest/JUnit: `.workspaces/spec063-evidence/20260923T144055Z-1dd61561885e/`.
- `--stage baseline-red`: **two expected assertion failures**, retained at `.workspaces/spec063-evidence/20260923T143847Z-03316177c046/`. Two actual worker PIDs dispatched the same envelope: gateway=2, accepted=2, effects=2. The real agent evidence middleware released one held-delivery frame from a replay-shaped success. These are local fixture reproductions, not production incidents.
- Real Postgres **16.14**, image digest `postgres@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777`; Docker 29.4.0, Compose 5.1.2, uv 0.8.14, Python 3.12.9. Baseline HEAD `bd756e961e6ebe097f32427e2919bc46e82383aa`, dirty working tree.
- Commit wrapper and wire proxy independently prove committed-but-unacknowledged rows; rollback yields zero rows from a fresh observer process. Negative controls reject duplicate dispatch, takeover, false no-effect certainty, and replay release. B0–B5 barrier machinery is proven; production hook integration follows with the ledger.
- `make -C products/execution-runtime test`: **73 passed**. `make execution-failure-test`: **fails as required** on missing F-01–F-34 coverage; full campaign and F-35 acceptance are not delivered. The target is also required by `make verify`.
- Earlier harness failures remain in evidence directories `20260923T143614Z-84887df67ad7` and `20260923T143756Z-987713dc3d36`: Docker internal-network port publication and truncated-response forwarding were corrected before the final harness run. Disposable resources were removed after each run with ownership checks; no shared service or target was used.

## S1 / R-1, R-2, R-6: Contracts and Durable Admission

- [x] T-06 Add v3 execution request and observation/recovery/handoff-response schemas; preserve legacy request/receipt validation for reads only (`shared/shared-contracts/schemas/`; R-6c).
- [x] T-07 Implement additive transactional migration, schema/constraint verification, both unique identities, append-only observations, bounded overflow/conflict state, and no session-delete cascade (`shared/shared-contracts/sql/execution-ledger-v1.sql`; R-1a/R-1b/R-7a).
- [x] T-08 Implement immutable intent registration and action/flow signing with run/epoch/expiry identity; failed preparation cannot send (`agent-platform` signing/recovery/kernel modules; R-1a/R-4a/R-6b).
- [x] T-09 Implement worker burn-on-claim transaction and single-use local permit; lost commit acknowledgment gives no permit (`execution-runtime/services/execution_ledger.py`; R-1a/R-1c).
- [x] T-10 Replace single-flight authority and raw-result duplicate cache with bounded durable metadata lookup; changed-content/reminted-ID conflicts cannot change the original row (R-1b/R-3c).
- [x] T-11 Add disabled-by-default admission, separate epoch, actual-backend readiness 503, independent liveness, and no deployed memory executor (`app.py`, config and health routes; R-2a).
- [x] T-12 Add real-Postgres two-process constraint races, startup/DB/schema failures, expiry bounds, registration failure, and commit-ambiguity tests; fake drivers remain supplemental (R-1/R-2/R-7a).

## S2 / R-3: Worker Outcomes and Late Evidence

- [x] T-13 Separate executor transport uncertainty from validated tool reports; disable HTTP retries/redirect replay and validate result/tool/correlation shape (R-3a).
- [x] T-14 Persist signed worker observations/receipt before original-result response; bounded same-bytes metadata retry/read-after-ambiguous-commit only (R-2b/R-2c/R-3b).
- [x] T-15 Implement deterministic recovery reducer, deadline projection, unavailable/not-found distinction, idempotent observations, conflict retention, and reserved observation capacity (R-3b/R-3d/R-6a).
- [x] T-16 Validate original response variant/schema/signatures/IDs/digest at the agent; distinguish status-only replay and malformed/forged responses (`execution_worker_client.py`; R-3c).
- [x] T-17 Replace v3 caller timeout receipt closure with attributed observations; preserve late results and keep legacy/read-tier handling separate (`runtime_kernel.py`; R-3b).
- [x] T-18 Complete crash tests B1–B5, reply loss on both HTTP legs, receipt write/ack loss, deadline, and late/conflicting receipt tests (R-2/R-3).

## S3 / R-4: Stop the Run Before Another Mutation or Secret Release

- [x] T-19 Persist root run identity through park/resume, confirmations, flow reuse, and agent-state recovery. Missing restored identity fails closed; stopped runs are never reset (R-4a/R-4b).
- [x] T-20 Add synchronous shared run latch before event yield; durable monotonic stop and unresolved-intent checks survive a failed stop write plus restart (R-4b).
- [x] T-21 Gate before middleware `ALLOWED`, before flow signing, in the mutating closure, at worker claim, and at final send; no new card/ID evades a stopped run (R-4b).
- [x] T-22 Implement bounded per-run final-send mutex and mutation lane, original-response acceptance, DB-loss/lock-loss behavior, and independent already-running-target reporting. Read tools remain governed on their existing path (R-2c/R-4b).
- [x] T-23 Require original verified/durable response permit for held-delivery release; unknown/replay/failed-close/late-result paths discard or expire the hold and never email/reveal it (R-4c).
- [x] T-24 Exercise denied/expired approval, stale flow, duplicate flow step, pending/parallel batch, interrupted agent, re-park, and secret-release race regressions at actual product seams (R-4a/R-4b/R-4c).

## S4 / R-5, R-6: Owner Recovery and All Evidence Consumers

- [x] T-25 Add bounded owner session recovery with cursor paging and explicit availability, independent of legacy confirmation/presentation write success; preserve turn anchoring (`api/v2/routes.py`, session schemas; R-5a).
- [x] T-26 Align platform-gateway's existing session proxy; prove foreign-owner/forged-ID refusal and decision-only approver inbox (R-5a/R-6b).
- [x] T-27 Render current state/history/late/conflict/unavailable in decided cards and add bounded visibility-aware recovery polling; no retry/reset/mark-success/reveal controls (portal chat/API/stream modules; R-5a).
- [x] T-28 Preserve original `x-request-id`, add correlation-only execution header, retain duplicate request IDs, and test audit outage independently of ledger recovery (worker executor/tool-gateway; R-5b).
- [x] T-29 Share uncertainty projection with new shift summaries/incident handovers and authoring decisions; preserve foreign metadata limits and published snapshots (R-5d).
- [x] T-30 Add closed safe projections, secret-canary/oversize tests across DB/log/audit/session/card/artifacts, and schema/vocabulary/canonicalization parity including portal/digest (R-6a/R-6c).
- [x] T-31 Add operator recovery guidance: inspect evidence, account for still-running work, independently verify target, then consider a fresh separately approved action. Missing audit/result is inconclusive (R-5c).

## S5 / R-7, R-8: Operational Failure Proof

- [x] T-32 Implement independent retention sweep preserving run/intent/claim/observation protection through expiry plus 30 days; test session deletion, cache eviction, and replay after cleanup (R-7a).
- [x] T-33 Test additive migration from legacy success/timeout/open rows and interrupted migration; historical signatures and bytes remain unchanged (R-7b).
- [x] T-34 Implement disabled cutover/downgrade/restore wrapper checks, external epoch management, old-process inventory, and old-validity wait runbook; no auto-enable (`shared/platform-ops/gitops/`; R-7b).
- [x] T-35 Add single-replica Recreate posture, bounded graceful drain, overlapping-new-process safety tests, readiness and bounded-cardinality unknown/duplicate/conflict/persistence metrics (R-7c).
- [x] T-36 Wire portal tests/build and the real-Postgres target into `make verify`; retain all existing repository gates; no skip/zero-tests success (R-8c).
- [x] T-37 Run all deterministic F-rows, including 20 schedule iterations for designated races and negative-control detection. Record actual test node IDs and sanitized evidence; do not silently retry failures to green (R-8a/R-8c).

### S1–S5 executed evidence (recorded 2026-09-25)

Backfilled record. Node IDs are confirmed against the actual asserting tests in the scenario-to-test map below; planned names that differed have been replaced. Disposable run logs and manifests persist under `.workspaces/` and `.workspaces/spec063-evidence/`. F-01–F-34 were first proven as **development-stage targeted proofs** and then re-run green together as the single gated **full deterministic campaign sweep (T-37, see the S5 T-37 bullet below)**. F-35 was still pending separate authorization at that point; the later authorized execution is recorded under S6 below.

- **S1 (T-06–T-12)** — v3 contracts, additive migration, durable admission, burn-on-claim, disabled-by-default admission, real-Postgres races. Asserting nodes in `F/test_admission.py`, `F/test_persistence.py`, `F/test_schema.py` (F-01–F-07). execution-runtime unit suite **77 passed**.
- **S2 (T-13–T-18)** — transport-uncertainty separation, signed observations, recovery reducer, agent response validation, attributed timeout observations, B1–B5 crash tests. Asserting nodes in `F/test_crashes.py`, `F/test_observations.py`, `F/test_cross_product.py` (F-08–F-18). Dev-run logs `.workspaces/spec063-dev-s2cross.log`, `spec063-dev-f13.log`, `spec063-dev-f14.log`, `spec063-dev-f15.log`, `spec063-dev-f16f18.log`.
- **S3 (T-19–T-24)** — run-identity persistence, shared run latch, stop gates at every seam, bounded final-send mutex, permit-gated secret release. Asserting nodes F-19–F-23 in `F/test_cross_product.py`. Dev-run logs `.workspaces/spec063-dev-f19.log`, `spec063-f20.log`, `spec063-dev-f21.log`, `spec063-f22.log`, `spec063-dev-f23.log`; suites `.workspaces/spec063-s3-agent-suite.log`, `spec063-s3-runtime-suite.log`.
- **S4 (T-25–T-31)** — owner recovery API, gateway proxy alignment, portal rendering/polling, correlation-only execution header, shared uncertainty projections, minimization/canary proofs, operator guidance. Asserting nodes F-24–F-27 in `F/test_cross_product.py` and `F/test_minimization.py`. Dev-run log `.workspaces/spec063-f24.log`; gateway `.workspaces/s63-t28-gateway-full.log`, `s63-t28-regression.log`. Exit-gate suites: **agent-platform 1505 passed, execution-runtime 77 passed, operator-portal 494 passed + build, platform-gateway 430 passed, real-Postgres regression green**.
- **S5 partial (T-32, T-33)** — independent bounded `ExecutionLedger.retention_sweep()` (FK-ordered, never touches `execution_runs`, trigger re-checks the 30-day horizon); F-28–F-31 proven. Targeted development-stage harness: **14 passed** (F-29 session_delete/presentation_sweep/cache_eviction, F-30 expired_replay/remint, F-30 retention_boundary ×9) and **4 passed** (F-31 success/timeout/open/interrupted), exit 0. Evidence `.workspaces/spec063-evidence/20260924T174043Z-4ce25efab922/`, `.workspaces/spec063-evidence/20260924T174449Z-294b77e9071a/`.
- **S5 partial (T-34)** — disabled cutover/downgrade/restore guard `execution_runtime.services.execution_cutover` (`plan_cutover`/`restore_interlock`/`rotate_epoch`/`old_validity_wait_seconds`; never auto-enables admission), GitOps wrappers `shared/platform-ops/gitops/execution-cutover.sh` + `rotate-execution-epoch.sh`, and the `docs/guides/execution-cutover-restore.md` runbook (old-process inventory + 960s old-validity wait + lost-evidence/no-universal-rollback limits). F-33 proven: targeted development-stage harness **3 passed** (downgrade/restore/epoch_mismatch), exit 0; runtime unit suite **77 passed**; disposable Postgres torn down (no stranded owner). Evidence `.workspaces/spec063-evidence/20260925T020630Z-328c415abf3f/`, log `.workspaces/spec063-dev-f33.log`.
- **S5 partial (T-35)** — single-replica `Recreate` posture + `terminationGracePeriodSeconds: 45` + `preStop sleep 5` in `execution-runtime-deployment.yaml` (kustomize-rendered clean); SIGTERM→draining lifecycle (`app.py` main-thread signal wrapper flips `draining` and records drain state; `main.py` `timeout_graceful_shutdown=35`; no claim release on drain); agent-platform handoff budget capped at 120s (`runtime_settings.__post_init__`, unit `test_execution_worker_timeout_cap`); fixed-cardinality metrics surface (`core/metrics.py`: duplicate/conflict/store-write-failure counters + admission-available/unresolved-count/unresolved-oldest-DB-age/drain-state gauges; bounded 5s-cached fail-open `ExecutionLedger.metrics_snapshot()`). F-32 proven: `F/test_cutover.py::test_disabled_cutover_overlap_and_bounded_drain` **80 passed** (disabled_cutover/overlap/drain/abrupt × 20 seeds), exit 0. F-34 proven: `F/test_observability.py::test_health_and_metrics_do_not_trigger_work` **5 passed** (store_failure/duplicate_storm/conflict/unknown_age/receipt_failure), exit 0. Runtime unit suite **77 passed**; agent-platform `test_runtime_settings.py` **65 passed**; disposable Postgres torn down (no stranded owner). Evidence `.workspaces/spec063-evidence/20260925T030128Z-25eaa8db9c21/` (F-32), `.workspaces/spec063-evidence/20260925T025803Z-b35d65223fa1/` (F-34); logs `.workspaces/spec063-dev-f32.log`, `.workspaces/spec063-dev-f34.log`.
- **S5 partial (T-36)** — root `make verify` now runs a new `portal-test` target (delegating to `make -C products/operator-portal test` + `web-build`, i.e. `npm --prefix web-ui/app test` and `run build`) immediately before the already-wired `execution-failure-test` real-Postgres target; all existing gates (product tests, overlays, policy/policy-scenarios, version, secret-vocabulary, password-policy, secret-delivery-demo) retained. Proven: `make portal-test` exit 0 — Vitest **494 passed (34 files)** + `tsc --noEmit && vite build` succeeded (5947 modules). No skip/zero-tests green path: `vitest run` on a non-matching filter exits **1** ("No test files found"). `make -n verify` confirms portal test/build precede `execution-failure-test.sh`. Log `.workspaces/spec063-t36-portal.log`.
- **S5 (T-37)** — full deterministic campaign run green as a single gated sweep: `products/execution-runtime/.venv/bin/python products/execution-runtime/tests/failure/run.py --stage campaign` → **791 passed, 2 deselected (the two `baseline_red` controls), exit 0, in 26:06 (1566.94s)**. The coverage gate was satisfied — every F-01…F-34 + F-36 case selected, with 20× schedule seeds on the REPEATED/race rows (F-03/F-07/F-08/F-09/F-12/F-14/F-20/F-22/F-32); all 60 `commit_wire` proxy variants passed. Per-file node counts: test_admission 99, test_agent_storage 74, test_crashes 143, test_cross_product 179, test_cutover 83, test_persistence 120, test_schema 30, test_harness_contract 33, test_retention 13, test_minimization 8, test_observability 5, test_observations 4. Evidence manifest `.workspaces/spec063-evidence/20260925T044507Z-6dac57118401/` (`evidence.json`: stage=campaign, exit_code=0, selected=791, results=791 all `passed`, `delivery_complete=false` because S6 is not authorized; metadata.database `spec063-f52d3ecdf777406eaf746858267cb0b1`, Postgres 16.14, fsync/full_page_writes/synchronous_commit all `on`; `junit.xml`, `prerequisites.json` git_head `bd756e9`); log `.workspaces/spec063-t37-campaign-fg.log`. The gate surfaced and I closed a genuine pre-existing coverage gap: F-05 declared both `cache_eviction` and `restart` but only `restart` was authored — `F/test_crashes.py::test_restart_replay_metadata_only` is now parametrized over both (a freshly launched peer with no process-local cache models eviction), so the campaign selects F-05/cache_eviction. **Run-mode honesty:** the campaign MUST run in the FOREGROUND — the agent's background shell sandbox denies POSIX named semaphores (`sem_open`), which `CommitAckProxy`'s `CONTEXT.Event()` needs, so a background run reported 63 spurious `commit_wire` `PermissionError` failures (not a code regression; foreground probe returns `SEMLOCK_OK` and all 60 pass). `uv run` is bypassed via the venv Python because the sandbox blocks writes to `~/.cache/uv`. Disposable Postgres torn down (no stranded `spec063-*` owner).
- **Historical stage boundary** — S6 was pending after T-37; its subsequent authorization, five-path acceptance, and cleanup are recorded below. `delivery_complete=false` is retained in historical artifacts and is not rewritten during closure.

## S6 / R-8b: Separately Authorized Isolated Acceptance

- [x] T-38 Record explicit environment/action authorization, account/target identity, code/image versions, permitted faults, and independent revision baseline. No implicit shared-cluster scope.
- [x] T-39 Implement and run `make execution-acceptance`: normal, denied/expired, interrupted, owner reload, and held-secret paths against isolated acme-admin. No target restart/reseed between observations.
- [x] T-40 Reconcile target revision/state with claim/attempt/receipt/card history; record unknowns honestly and prove no automatic repeat mutation or late secret release.

### S6 executed evidence (2026-09-25)

- **Scope/build/cutover:** [authorization](s6-acceptance-authorization.md); context `orbstack`, namespace `spec063-acceptance`, UID `ed54bf8a-a31d-499f-9112-7b556cf85fc6`, target `spec063-accept`, distinct operator/approver. Product/sample tag `0.42.0-spec063-bd756e9-dirty-20260925-s6` from dirty HEAD `bd756e961e6ebe097f32427e2919bc46e82383aa`. Namespace-local Postgres/Redis and fresh credentials; no shared secret files, ingress, or Keycloak reconciliation. Migration started with admission disabled, followed by explicit DB/config enable at UUID epoch `01960c63-0001-4000-8000-000000000001`; worker readiness and agent admission verified. Initial deployment verification incorrectly waited on deliberately disabled readiness; corrected to liveness. Partial cutover was inspected and completed without repeating migration or restarting the target.
- **First campaign — retained failure:** `.workspaces/spec063-evidence/s6-20260925T151650Z-f3f94c6b06/` (`evidence.json`, `junit.xml`): four paths passed; held-secret failed at `secret_redemption`. Target revision advanced **0→4**, wire attempts/completions **0→4**. The harness fetched the reset handle as the wrong owner before its legitimate owner: both existing buffer backends intentionally burn a handle on that probe. The exact function reproduced the same failure locally. No product security semantics were changed; failed evidence was not overwritten or relabeled.
- **Harness correction/local proof:** separate generation-only handle for the destructive wrong-owner control; correct owner redeems the reset password once; status/value checks have distinct sanitized failures; all handles discarded in `finally`. `samples/acme-admin/app/tests/test_execution_acceptance.py::test_held_secret_uses_distinct_owner_and_destructive_probe_handles` first failed on the old harness and now passes; `::test_held_secret_detects_redemption_failures` covers wrong-owner leak, replay leak, HTTP failure and wrong value; `::test_reconciliation_preserves_failed_campaign_and_rejects_drift` covers unchanged failure artifacts and target/wire/claim drift. Sample suite **168 passed, 2 warnings**; tool-gateway `tests/test_secret_delivery.py` **17 passed, 1 warning**.
- **Disclosed corrected campaign — all five passed:** `make execution-acceptance` with the explicit scope, same images/namespace/target, new independently approved calls; `.workspaces/spec063-evidence/s6-20260925T154521Z-31a1b25bd7/` (`evidence.json`, `junit.xml`, driver SHA-256 inventory), exit 0. Driver: `samples/acme-admin/execution_acceptance_live.py::run_campaign`; product-seam probe: `execution_acceptance_probe.py`. This is deterministic live product-seam acceptance, **not a portal/browser or conversational acceptance run**.

| Corrected F-35 path | Target revision | Claims / new wire attempts | Observed result |
|---|---|---|---|
| normal | 4→5 | 1 / 1 | Unlock, durable succeeded receipt and original response acceptance. |
| denied-expired | 5→5 | 0 / 0 | Expired authority refused; target unchanged. Recovery remains conservatively unknown, not false no-effect certainty. |
| interrupted | 5→6 | 1 / 1 | Lock occurred before worker death; no receipt, unknown/stopped recovery, replay caused no new dispatch. |
| owner-reload | 6→7 | 1 / 1 | Unlock, durable worker result but withheld agent acceptance; metadata-only owner recovery, stopped run, replay caused no new dispatch. |
| held-secret | 7→8 | 1 / 1 | Password timestamp changed, lock state unchanged; one release frame, owner redemption once, second permit refused, replay release=0; separate wrong-owner control burned. |

- **Independent reconciliation:** `execution_acceptance_setup.py --stage reconcile` retained `.workspaces/spec063-evidence/s6-reconciliation-ed54bf8a-a31d-499f-9112-7b556cf85fc6.json`: **10 intents, 8 claims, 8 wire attempts/completions, target revision 0→8** across both campaigns. Same target hostname/start time and witness boot ID throughout; alice/bob/carol/dave unchanged. Original artifact hashes retained. Read-only ledger lookup also recovered the failed held-secret execution `ebe99842-45f8-4d2f-a339-cfb556e2572e`: one claim, succeeded receipt, original response accepted; this does not convert its failed redemption assertion into a pass. Unknown paths remain unknown; post-replay stopped state is retained separately from pre-replay facts.
- **Cleanup:** `execution_acceptance_setup.py --stage teardown` completed with ownership checks. Namespace and dedicated ClusterRole/ClusterRoleBinding removed; metadata baselines for deployments/ConfigMaps/Secrets/HTTPRoutes in `dev-luban-aiops` and `gateway`, local shared GitOps env-file hashes, frozen plan and ADR hashes all match the pre-deployment baseline (`protected_unchanged=true`). Archive: `.workspaces/spec063-evidence/s6-setup-ed54bf8a-a31d-499f-9112-7b556cf85fc6.json`. Keycloak change inventory is empty: no realm/client/user/settings were created or modified, so no Keycloak cleanup was needed. Isolated image tags and ignored local workspace/evidence are retained. Follow-up cluster reads confirmed namespace/RBAC absence, no PV with a claim in the acceptance namespace, and node Ready.
- **Authorization provenance:** the authorization file is retained byte-for-byte as the pre-execution scope artifact (SHA-256 `24776fe0b0dccfb4611d0cf2e95d6fbe76a850d144c3f24aa1136c9a58ec0f7a`). Its prospective deployment commands/tag and “not yet executed” wording are historical, not current status: the actual execution used `execution_acceptance_setup.py`, fresh namespace-only credentials, the tag above, and isolated identity-service token issuance without Keycloak or stock deployment/reconciliation scripts. Current results and cleanup are recorded here.
- **Delivery boundary:** acceptance is proven; release versioning, complete root verification/living-document reconciliation, and the remaining Delivery Gate are not claimed complete. `delivery_complete=false` remains in every evidence record. No commit, push, registry push, or shared deployment change.

## Delivery Closure Evidence

The operator authorized remaining local delivery work after S6. Candidate version is
**0.43.0**, at dirty HEAD `bd756e961e6ebe097f32427e2919bc46e82383aa`; no commit, tag,
push, registry push, shared deployment, or new acceptance campaign was performed.
Historical S6 images remain 0.42.0; their provenance and `delivery_complete=false`
fields are unchanged.

### V1 — root verification: failed, retained

Command: `make verify > .workspaces/spec063-close-verify-1.log 2>&1`.
Product suites and non-campaign gates passed before the required failure campaign:

| Gate | Observed result in V1 |
|---|---|
| agent-platform | 1506 passed |
| audit-service | 139 passed |
| execution-runtime | 78 passed, including the new cutover shell regression |
| identity-broker | 60 passed |
| incident-service | 137 passed |
| platform-gateway | 393 passed |
| skills-hub | 230 passed |
| tool-gateway | 430 passed |
| overlays | Four rendered successfully |
| policy/schema/scenarios | 19 rules; API 144 scenarios / 93 granted pairs; tools 26 scenarios / 16 granted pairs |
| version | All product/portal versions agree at 0.43.0 |
| secret vocabulary / password policy | Passed |
| local secret-delivery demo | Agent 10, tool-gateway 28, platform-gateway 66, portal 43 passed |
| full portal / production build | 494 passed in 34 files; TypeScript/Vite build succeeded |
| real-Postgres campaign | **85 failed, 695 passed, 2 baseline-red deselected, 12 errors; exit 1** |

The root target failed at `execution-failure-test`; it is not a pass. Manifest/JUnit
and prerequisites are retained at
`.workspaces/spec063-evidence/20260925T164648Z-950adb785d82/` (Postgres 16.14,
initial fsync/full_page_writes/synchronous_commit all on). The first failure was
`F/test_crashes.py::test_suspended_owner_is_not_canceled_or_replaced[13-explicit_stop]`
at fixture registration with a Postgres connection timeout. Later failures include
more DB connection timeouts, a missing B4 acknowledgment, and four sanitized
agent-probe failures. These remain unresolved, not asserted to be harmless flakes.
Teardown also failed because Docker exceeded its watchdog. A subsequent bounded
15-second `docker ps` for owner `2d239b8e8148413bacdb5c00f0eaa6b5` timed out;
Docker context reports `orbstack`. The daemon's underlying failure is not established.

**Cleanup is unconfirmed** for Compose project
`spec063-2d239b8e8148413bacdb5c00f0eaa6b5`. Do not start another campaign until Docker
responds and the harness's ownership-verified `--stage development --cleanup-owner
2d239b8e-8148-413b-acdb-5c00f0eaa6b5` path settles that project. Do not use broad
cleanup or restart OrbStack/shared workloads without separate authorization.
After infrastructure recovery, investigate any remaining assertion failures and
run the full gate with a new log/evidence directory; preserve V1 unchanged.

### V2 — local closure checks: passed

- `make -C samples/acme-admin/app test` (the sample's documented command): **168 passed**;
  log `.workspaces/spec063-close-sample-1.log`. No live target contacted.
- `python3 shared/shared-contracts/scripts/sync_execution_contracts.py`: **exit 0**,
  check-only parity across canonical contracts and both packaged consumers.
- `make validate-version`: **exit 0**, 0.43.0. Eight product manifests/editable lock
  entries/runtime metadata and both package-version constants agree with root VERSION;
  portal uses the root's build-time version. Dependencies were not upgraded.
- `git diff --check` and `sh -n` on both execution operational wrappers: **exit 0**.
- V1 runtime node `tests/test_config.py::CutoverWrapperTests::test_disabled_recovery_requires_verified_empty_sender_inventory`
  passed all nine local subcases: empty/drained success; failed scale/wait/inventory,
  remaining worker/issuer, and unconfirmed-disable refusal. Real decision CLI with
  fake kubectl; no cluster writes. The fix removes swallowed errors and false success.
- Living product READMEs, approval/HITL, configuration, troubleshooting, portal,
  digest, and GitOps guidance reconciled. Initial protocol cutover is mandatory even
  on a semver upgrade; stock deploy does not automate it. Rotation changes the catalog,
  not consumer configuration, and migration never enables admission. F-33 models the
  restored-catalog interlock, not a complete backup/restore drill.
- Frozen repository plan SHA-256 remains
  `3e2799f9c3be3b2b0bb32f94eec99b879fb3209dbd6a9ccadcda996b79aee16a`;
  ADR-0013 remains `d847a8b5fef361daedf480d0b7c959c69439a0aa74bb39bd7c28a2e6b7b322b1`.
  Both match the pre-S6 baseline. S6 authorization hash remains the value recorded above.
- Historical S4 count clarification: its “platform-gateway 430” label is not current
  verification evidence. V1 independently establishes **platform-gateway 393** and
  **tool-gateway 430**; the older log is retained, not silently rewritten.

### V1 stranded-resource cleanup: complete

After the operator restored the local Docker daemon, V1's stranded owner was
settled through the harness's ownership-verified path, not broad cleanup:
`run.py --stage development --cleanup-owner 2d239b8e-8148-413b-acdb-5c00f0eaa6b5`
exit 0, `ownership_verified=true`
(`.workspaces/spec063-evidence/20260926T021533Z-551cfc161b6e/cleanup.json`). A
follow-up owner-scoped `docker ps -a`/`volume ls`/`network ls` returned empty.
This cleanup is not a test pass and does not change V1's failed result.

### V3 — root verification: one barrier flake, retained

`make verify > .workspaces/spec063-close-verify-3.log`. All product/portal/policy/
version/secret gates passed. The real-Postgres campaign reached **790 passed, 1
failed, 2 deselected in 26:29**; the single failure was
`F/test_crashes.py::test_kill_after_gateway_acceptance[5-B2]` — `barrier B2
acknowledgment missing` (the 15s parent `gate.wait` did not observe the spawned
gateway's datagram under load). Re-run in isolation via `--stage development
--select "test_kill_after_gateway_acceptance[5-B2]"`: **1 passed in 8.05s**
(`.workspaces/spec063-evidence/20260926T041149Z-dd3aa2c648d6/`). This is a
load-sensitive harness timing flake, not a product regression; it is not relabeled
as a pass and V3 is retained. A second owner (`27d75f31-...`) stranded by the
tool-timeout-interrupted V2 launch was cleaned the same ownership-verified way
(`.workspaces/spec063-evidence/20260926T024841Z-d5a733c6f369/cleanup.json`).

### V4 — root verification: calendar-rot fixture bug found and fixed, retained

`make verify > .workspaces/spec063-close-verify-4.log`. Failed at the agent-platform
suite: `tests/test_operation_documents.py::TestInMemoryStore::test_cap_evicts_oldest_per_owner`
asserted `18 == 20`. Root cause is a **test-only** date-rot bug unrelated to
SPEC-063: the fixture created documents with a hardcoded `created_at` of
`2026-08-27`, and `InMemoryOperationDocumentStore.create()` opportunistically
sweeps rows older than `RETENTION_DAYS = 30`. Once the wall clock passed
~2026-09-26, two fixture rows aged out before the per-owner cap assertion, so the
cap logic saw 18 live rows. The product retention behavior is correct; the fixture
was wrong. Fixed by stamping `created_at` relative to `datetime.now(timezone.utc)`
(`.workspaces/spec063-close-verify-4.log` retained; the edit touches only
`products/agent-platform/tests/test_operation_documents.py`). Post-fix
`pytest tests/test_operation_documents.py`: **21 passed**.

### V5 — root verification: transient Docker prerequisite timeout, retained

`make verify > .workspaces/spec063-close-verify-5.log`. Every product/portal suite
passed again (agent-platform **1506**, tool-gateway 430, portal 494, etc.). The
campaign exited **2** at its `prerequisites()` Docker probe — `docker unavailable or
exceeded watchdog` — before creating any disposable container, so nothing was
stranded. A subsequent bounded `docker version` returned `29.4.0` in 0.04s, three
times. This is the same daemon instability as V1/V6 surfacing at the prerequisite
gate rather than mid-campaign; it is not a product failure and V5 is retained.

### V6 — root verification: daemon wedge cascade, retained; delivery still blocked

`make verify > .workspaces/spec063-close-verify-6.log` (pid launched detached; not
killed mid-flight). Product/portal suites passed. The campaign started healthy, ran
~22% green, then cascaded: **569 failed, 209 passed, 2 deselected, 14 errors in
29:02**. The first failure is
`F/test_crashes.py::test_kill_after_claim_before_send[5]` (`barrier B1
acknowledgment missing`), immediately followed by
`psycopg.errors.ConnectionTimeout: connection timeout expired` on essentially every
subsequent DB-backed node — the disposable Postgres became unreachable because the
OrbStack daemon wedged under the sustained multiprocess campaign load, the same
mode as V1. A post-run bounded `docker version` **timed out at 15s**, confirming the
wedge. The campaign code is byte-identical to V3's 790/791 run and V5's product
suites were green, so this is daemon instability, not a product regression. V6 is
retained unchanged.

**V6 cleanup** for Compose project `spec063-cad4ee02c59b4f55a7c6269e0cb573e0`
(owner `cad4ee02-c59b-4f55-a7c6-269e0cb573e0`) was settled ownership-verified after
the authorized engine restart, before the V7 run below (no repeat campaign was
started while it was stranded).

**Daemon-instability note (honest).** A clean full `make verify` was not observed on
the first attempts. The local OrbStack daemon intermittently wedged under the
campaign's sustained multiprocess load (V1, V5, V6), with one near-complete run
(V3, 790/791) between them. Recovering a wedged daemon requires an OrbStack engine
restart (`orbctl stop`/`start`), which affects the shared local cluster and its other
workloads; that restart was performed **only after explicit operator authorization**.
No failed run was relabeled, no subset was substituted for the gate, and no product
assertion was weakened to force green. The V4 fixture fix is test-only.

### V7 — root verification: PASSED (delivery gate met)

After the authorized OrbStack engine restart, Docker answered a bounded
`docker version` in 0.27s; V6's stranded owner `cad4ee02-…` was settled through the
ownership-verified `--cleanup-owner` path (exit 0, `ownership_verified=true`,
`.workspaces/spec063-evidence/20260926T075359Z-604a30c2d2a0/cleanup.json`), and a
follow-up owner-scoped inventory returned empty. A fresh full
`make verify > .workspaces/spec063-close-verify-7.log` (launched detached, never
killed mid-flight) then passed **end to end**:

| Gate | V7 result |
|---|---|
| agent-platform | 1506 passed |
| audit-service | 139 passed |
| execution-runtime | 78 passed |
| identity-broker | 60 passed |
| incident-service | 137 passed |
| platform-gateway | 393 passed |
| skills-hub | 230 passed |
| tool-gateway | 430 passed |
| overlays | Four rendered |
| policy schema / scenarios | 19 rules; API 144 scenarios / 93 granted pairs; tools 26 / 16 |
| version | `OK: all product and portal versions match VERSION=0.43.0` |
| password policy | OK (min_length=16, hard_floor=12, classes=4, entropy 64 bits) |
| secret-delivery demo | 10 / 28 / 66 passed |
| portal test + production build | 34 files passed; vite build ✓ 5947 modules |
| **real-Postgres campaign** | **791 passed, 2 deselected, exit 0 in 25:29** |

`SPEC-063 campaign: exit 0`; no `make … Error` anywhere in the log; post-run
owner-scoped Docker inventory is empty (clean teardown). Campaign artifact:
`.workspaces/spec063-evidence/20260926T075723Z-dc4d688d8cfc/` (evidence.json /
junit.xml, `delivery_complete` recorded by the harness). The campaign code is
byte-identical to V3/V5/V6, so V7 reproduces the historical T-37 green result on the
0.43.0 candidate and confirms the V1/V5/V6 cascades were daemon instability, not a
product regression. This is the required full root gate; V1–V6 remain retained as
honest history and are not overwritten.

## Scenario-to-Test Map

Shorthand roots:

- `F/` = `products/execution-runtime/tests/failure/` (new, real-Postgres/process integration).
- `A/` = `products/agent-platform/tests/` (existing test package; new files noted by their planned name).
- `P/` = `products/operator-portal/web-ui/app/src/chat/__tests__/`.
- `F/test_cross_product.py` launches actual product seams with deterministic decisions; unit assertions alone do not satisfy its entries.
- Executed rows record the **actual asserting node IDs** confirmed against the suite; F-35 records the exercised five-path live driver and retained campaign outcomes. Parameterized rows require every case, not one representative success.

| Matrix ID | Actual asserting node(s) — confirmed (dev/harness stage) | Required distinguishing evidence |
|---|---|---|
| F-01 | `F/test_admission.py::test_original_action_dispatches_once` | Claim=1, gateway=1, target=1, validated durable result. |
| F-02 | `F/test_admission.py::test_invalid_handoff_never_dispatches`; `F/test_schema.py::test_action_flow_signing_and_catalog_parity` (provenance); `F/test_schema.py::test_sql_request_shape_constraints_reject_invalid_metadata` (constraint) | Credential/schema/signature/args/provenance parameter set, all target=0. |
| F-03 | `F/test_admission.py::test_duplicate_race_across_processes`; `F/test_admission.py::test_simultaneous_preclaim_unique_key_race` | Same-process and two-PID races; bounded metadata response, one attempt. |
| F-04 | `F/test_admission.py::test_identity_collision_preserves_original` | Each changed identity field and reminted execution ID. |
| F-05 | `F/test_crashes.py::test_restart_replay_metadata_only` (cache_eviction/restart) | New PID, no reconstructed result/handle or dependent call; a fresh peer with empty local cache models eviction. |
| F-06 | `F/test_admission.py::test_admission_without_postgres_never_ready`; `F/test_schema.py::test_database_outage_at_b0_cannot_dispatch` (before_claim); `F/test_schema.py::test_durability_setting_is_checked` (backend); `F/test_schema.py::test_catalog_damage_closes_both_products` (schema/constraint) | Startup/B0/backend/schema/constraint independently fail, live vs ready. |
| F-07 | `F/test_persistence.py::test_claim_commit_ack_loss_never_sends` | Committed row from observer, target=0, no takeover. |
| F-08 | `F/test_crashes.py::test_kill_after_claim_before_send` | Durable claim, target=0, restart unknown by deadline. |
| F-09 | `F/test_crashes.py::test_suspended_owner_is_not_canceled_or_replaced` | Resume original beyond deadline; explicit-stop variant blocks it. |
| F-10 | `F/test_crashes.py::test_kill_after_gateway_acceptance` (kill_B2/kill_B3) | Target may finish once after worker death, unknown after restart. |
| F-11 | `F/test_crashes.py::test_target_commit_with_lost_gateway_reply` | Target=1 despite unknown, no fallback/retry/next write. |
| F-12 | `F/test_persistence.py::test_receipt_write_failure_or_ack_loss`; `F/test_crashes.py::test_kill_after_gateway_acceptance` (kill_B4) | Actual rollback vs committed receipt recovered by read. |
| F-13 | `F/test_cross_product.py::test_agent_death_after_durable_result_recovers_on_reload` (agent_death); `F/test_crashes.py::test_kill_after_gateway_acceptance` (lost_handoff_reply/B5) | Durable result survives B5 loss/agent death without original output. |
| F-14 | `F/test_cross_product.py::test_agent_wait_then_late_worker_result` | Timeout and receipt both retained; original card/turn anchor. |
| F-15 | `F/test_cross_product.py::test_untrusted_worker_reply_blocks_continuation`; `A/test_execution_worker_client.py` | Every malformed/signature/identity/digest/transport variant, no false rejection. |
| F-16 | `F/test_cross_product.py::test_tool_report_is_not_business_success` | Partial effect, HTTP error, tool-success/upstream-500 distinction. |
| F-17 | `F/test_observations.py::test_identical_and_conflicting_final_observations`; `F/test_observations.py::test_duplicate_storm_cannot_exhaust_reserved_facts` (overflow) | Same bytes idempotent; conflicting signed facts retained and flagged. |
| F-18 | `F/test_cross_product.py::test_status_store_outage_is_not_empty_history` | Unavailable on owner reload; normal read path remains available. |
| F-19 | `F/test_cross_product.py::test_denial_expiry_and_stale_flow_authority` | Action/flow refusals and target/dispatch distinction. |
| F-20 | `F/test_cross_product.py::test_flow_duplicate_and_unknown_stop_next_write` | No extra browser step; all stop seams including new-card bypass. |
| F-21 | `F/test_cross_product.py::test_restart_cannot_resume_stopped_run`; `A/test_execution_run_guard.py` | Stale ALLOWED/flow state, failed stop write, unresolved intent, no new run remint. |
| F-22 | `F/test_cross_product.py::test_outstanding_operations_reported_and_next_send_blocked` | A remains active; B unknown; C not sent; no claimed remote cancellation. |
| F-23 | `F/test_cross_product.py::test_secret_release_requires_original_durable_success`; `A/test_secret_delivery_integration.py` | Held handle never released on unknown/replay/late/failed close; normal path intact. |
| F-24 | `F/test_cross_product.py::test_recovery_owner_scope_and_paging`; `P/ExecutionRecovery.test.tsx` | Owner/foreign/inbox/forged-ID, paging limits, stale response rejection. |
| F-25 | `F/test_cross_product.py::test_correlation_survives_duplicate_and_audit_outage` | Header IDs observed outside worker; durable evidence despite sink loss. |
| F-26 | `A/test_shift_summary.py`; `A/test_execution_recovery.py`; `F/test_cross_product.py::test_derived_facts_preserve_uncertainty` | All unknown/late/conflict/unavailable variants, unchanged published artifacts. |
| F-27 | `F/test_minimization.py::test_canaries_absent_from_all_recovery_surfaces`; `F/test_minimization.py::test_minimization_observers_detect_leaks_without_printing_them`; `F/test_minimization.py::test_audit_canary_scanner_observes_before_fixture_filtering` | Closed/oversized data, exception/URL canaries, unchanged canonical digest. |
| F-28 | `F/test_retention.py::test_database_clock_exact_inequality`; `F/test_retention.py::test_production_clock_expiry_after_b0_never_dispatches`; `F/test_retention.py::test_unsupported_lifetime_version_or_epoch_never_sends` | Equality at expiry, future request, >900 lifetime, legacy/version/epoch refusal. |
| F-29 | `F/test_retention.py::test_presentation_loss_never_releases_dispatch_authority` (session_delete/presentation_sweep/cache_eviction) | Still-valid replay remains consumed after all cleanup paths. |
| F-30 | `F/test_retention.py::test_expired_replay_rejected_before_and_after_retention_sweep`; `F/test_retention.py::test_approved_call_id_remint_refused_within_validity_horizon`; `F/test_schema.py::test_sql_immutable_evidence_cannot_be_reused` (retention_boundary) | Zero new claim/attempt after cleanup; protected remint collision. |
| F-31 | `F/test_schema.py::test_legacy_migration_preserves_bytes_without_inventing_claims`; `F/test_schema.py::test_killed_migration_rolls_back_entire_catalog` (interrupted) | Legacy success/timeout/open rows plus failed migration rollback. |
| F-32 | `F/test_cutover.py::test_disabled_cutover_overlap_and_bounded_drain` (disabled_cutover/overlap/drain/abrupt × 20 seeds; **80 passed**) | Admission-disabled cutover worker unready + mints no authority; two overlapping new PIDs dispatch exactly once; SIGTERM drains the in-flight call then terminates without releasing the claim; abrupt SIGKILL retains the claim and a replacement mints no second dispatch. |
| F-33 | `F/test_cutover.py::test_mutation_enabled_downgrade_is_refused_without_disabled_recovery` (downgrade); `F/test_cutover.py::test_restored_snapshot_fails_closed_until_external_epoch_rotated_disabled` (restore); `F/test_cutover.py::test_external_epoch_mismatch_mints_no_dispatch_authority` (epoch_mismatch) | Wrapper/CLI refusal of a mutation-enabled downgrade; restored epoch fails closed then rotation records the new epoch with admission still disabled; bounded 960s expiry-wait; matched-epoch control mints a permit. |
| F-34 | `F/test_observability.py::test_health_and_metrics_do_not_trigger_work` (store_failure/duplicate_storm/conflict/unknown_age/receipt_failure; **5 passed**) | Known bounded reason labels; duplicate counter moves with no identity/session/confirm label; DB-time unknown age grows and observation never resets the deadline; store outage and rolled-back receipt published as write failures while dispatching nothing extra. |
| F-35 | `samples/acme-admin/execution_acceptance_live.py::run_campaign` via `make execution-acceptance` — normal / denied-expired / interrupted / owner-reload / held-secret; `execution_acceptance_probe.py` product seams | Corrected live campaign five passed; first failure preserved; same target process, independent revisions/wire counts, read-only ledger/card reconciliation, isolated cleanup verified. |
| F-36 | `F/test_harness_contract.py::test_missing_prerequisites_fail_without_fallback`; `::test_missing_scenarios_parameters_and_schedules_fail` (coverage gate); `::test_duplicate_and_takeover_negative_controls`; `::test_lost_reply_false_no_effect_control`; `::test_replay_release_negative_control`; `::test_baseline_two_actual_workers_violate_single_dispatch`; `::test_baseline_replayed_success_must_not_release` | No skip/zero-selected/missing-row pass; negative controls fail assertions. |

## Acceptance-Criterion Coverage Register

All **26 criteria** map through their F-rows to the actual asserting nodes above.
For each F-01–F-34/F-36 reference, command/result/artifact provenance is the
**passing V7** full root campaign (791 passed, exit 0,
`.workspaces/spec063-evidence/20260926T075723Z-dc4d688d8cfc/`), which reproduces the
historical T-37 green result on the 0.43.0 candidate; the retained V1/V3/V5/V6 runs
document the daemon-instability path to that pass and are not overwritten. F-35
references use the separately authorized S6 driver, commands, versions, and both
retained runs above; R-5c also uses the reconciled V2 operator guidance. Supplemental
agent/portal nodes use V7's product/portal suites. This is an executed traceability
register, not a collection of planned test names, and with V7 green it closes
delivery.

| Criterion | Implementation tasks | Required matrix proof |
|---|---|---|
| R-1a | T-06–T-12 | F-01/F-02/F-06/F-07 |
| R-1b | T-07/T-09/T-10/T-12/T-32 | F-03/F-04/F-05/F-29 |
| R-1c | T-09/T-18/T-35 | F-05/F-07/F-08/F-09/F-10 |
| R-2a | T-11/T-12/T-35 | F-06 |
| R-2b | T-09/T-14/T-18 | F-06/F-07/F-11/F-12 |
| R-2c | T-14/T-22/T-25 | F-12/F-18 |
| R-3a | T-13/T-16/T-18/T-29 | F-09/F-10/F-11/F-12/F-15/F-16 |
| R-3b | T-14/T-15/T-17/T-18 | F-13/F-14/F-17 |
| R-3c | T-10/T-16/T-18 | F-01/F-05/F-13/F-15 |
| R-3d | T-15/T-18/T-27 | F-08/F-10 |
| R-4a | T-08/T-19/T-24 | F-01/F-02/F-19/F-20 |
| R-4b | T-19–T-22/T-24 | F-09/F-11/F-20/F-21/F-22 |
| R-4c | T-23/T-24 | F-23 |
| R-5a | T-25–T-27 | F-13/F-14/F-18/F-24 |
| R-5b | T-28 | F-25 |
| R-5c | T-31/T-38–T-40 | F-25/F-35 |
| R-5d | T-29/T-30 | F-16/F-21/F-26 |
| R-6a | T-07/T-15/T-23/T-30 | F-05/F-23/F-27 |
| R-6b | T-08/T-26/T-28 | F-02/F-04/F-24 |
| R-6c | T-06/T-30/T-33 | F-17/F-26/F-31 |
| R-7a | T-07/T-12/T-32 | F-28/F-29/F-30 |
| R-7b | T-33/T-34 | F-31/F-32/F-33 |
| R-7c | T-35 | F-32/F-34 |
| R-8a | T-01–T-05/T-37 | All deterministic rows; F-36 validates proof prerequisites. |
| R-8b | T-38–T-40 | F-35 |
| R-8c | T-03/T-36/T-37 and delivery gate | F-36 plus actual full-run evidence. |

## Delivery Gate

- [x] Replace planned names with actual asserting node IDs and record each criterion's test command/result/artifact per ADR-0008; no missing F-row/parameter case or unresolved failed negative control (actual-node map above; V7 campaign JSON/JUnit `.workspaces/spec063-evidence/20260926T075723Z-dc4d688d8cfc/` retains every parameterized node result; F-36 negative controls asserted).
- [x] Required real-Postgres multiprocess failure target passes, including crash-at-every-barrier and repeated schedule campaign; mock-only success does not count (V7: **791 passed, 2 deselected, exit 0**).
- [x] Product, shared-contract, portal test/build, overlay, policy, version, secret-vocabulary/password-policy, sample-local, and root `make verify` gates pass (V7 full `make verify` exit 0; contract check-only parity and sample 168 in V2; all gate results tabulated above).
- [x] Explicitly authorized isolated acme-admin acceptance completed with independent target evidence; no shared-cluster disruptions implied (S6 evidence and cleanup above).
- [x] Cutover and rollback/restore gates rehearsed on disposable infrastructure; document original-claim loss and remote-cancellation limitations (F-32 80 seeds + F-33 downgrade/restore/epoch_mismatch in V7; local shell regression in the execution-runtime suite; limitations documented in the cutover/restore runbook).
- [x] Update living execution-runtime/agent-platform/tool-gateway/operator-portal READMEs and approval/HITL, configuration, troubleshooting, portal, document/digest, and GitOps runbooks; qualify old process-local safety claims without rewriting delivered specs (V2).
- [x] ADR-0013 remains consistent with delivered behavior; accepted scope is not an implementation pass (frozen ADR hash unchanged; delivered behavior matches its at-most-one-dispatch / explicit-unknown / no-takeover guarantees, proven by V7).
- [x] Assign release version in the implementation/delivery phase, update coordinated version/lockfiles and `CHANGELOG.md` with SPEC-063, and record release evidence (0.43.0; `make validate-version` agrees; CHANGELOG promoted from candidate to a dated release; V7 is the release verification evidence).
- [x] Update spec index/roadmap and mark spec `delivered` only after every criterion is proven (spec.md status flipped to `delivered`; docs/specs/README.md and delivery-roadmap.md updated). Commit/push/deploy still require the applicable user authorization — none performed.

