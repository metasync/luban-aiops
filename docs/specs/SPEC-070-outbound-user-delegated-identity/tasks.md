# SPEC-070 Tasks: Outbound User-Delegated Execution Identity (Tool-Gateway Substrate)

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

> **In progress; contract-only v0.50.0 release approved 2026-10-23.** ADR-0016 remains accepted and OQ-7
> ratified. Development acceptance covers R-1–R-6d without a real AAP dependency. OQ-3 and
> former acceptance criterion R-6e are tracked under **DI-070** below: mandatory before
> production target enablement, not a development-delivery or version-bump gate. The additive
> contract increment is released; the internal R-1/R-6 foundation is implemented and verified
> as recorded below. OAuth workflow and production provisioning remain open. The attached
> kickoff/foundation plans and accepted ADR bodies are unchanged. No usable authorization flow
> or full SPEC-070 delivery is claimed; other handoff gates remain.

## Historical Stage 0 — 2026-10-12

- [x] Selected target-issued authorization-code, no outbound broker mint, and per-user
      credential custody; accepted/indexed ADR-0015 and approved the original scaffold.
- [x] Recorded AAP documentation research. **Correction, 2026-10-18:** this was not a live
      deployment fact. PKCE not enforced in 2.6 does not mean unsupported; no universal
      token-exchange impossibility follows from absent discovery/documentation.
- [x] Recorded Keycloak + AWX as an early dev suggestion. **Correction, 2026-10-18:** it
      cannot stand in for actual AAP credential/RBAC compatibility proof without equivalence.
- [x] Retained the original v0.49.0 planning target; no version bump or runtime delivery.

## Reopened Gate 0 — Redirect-Based Reconciliation

- [x] Record zero-redirect no-go and the later operator-approved change to first-use and
      reauthorization redirects without credential settings, manual tokens, or CLI enrollment.
- [x] Retain target authorization-code/server-side renewal and no new broker signing authority.
- [x] Record selected encrypted Postgres custody and expanded portal/gateway/agent impact.
- [x] Recheck official AAP 2.6/2.7 authorization-code, client, PKCE, and token-lifetime docs;
      preserve evidence limits in the [report](compatibility-report.md#redirect-based-reassessment-2026-10-18).
- [x] Draft revised requirements, plan/test gates, proposed ADR-0016, and index/roadmap state.
- [x] **2026-10-23 scope amendment:** move OQ-3 deployment facts and live-test authorization
      to DI-070 below; neither is a development-delivery gate. This records relocation,
      not completion of the live proof or resolution of the missing AAP facts.
- [x] **OQ-7:** complete and ratify exact API/stream/owner-state/browser-binding contracts,
      audit-query impact, and safe stop/continue semantics
      against the existing signed-execution path. No callback may dispatch a tool. **Drafted
      (proposed) 2026-10-18** in
      [oq7-first-use-handoff-contract.md](oq7-first-use-handoff-contract.md): bounded-stop (not
      park) signal via a reserved `TARGET_AUTHORIZATION_REQUIRED` code + additive
      `authorization_required` tool-result object and stream v13 frame; owner-scoped
      single-use `challenge_id`/`start_token`/`state`; portal + internal routes; replica-safe
      transaction store; new-turn continue that re-passes policy/HITL/signed-execution/claim;
      top-level `delegation_mode` audit field. **Ratified 2026-10-19** — the pre-runtime gate
      is closed. The 2026-10-23 amendment pins local TTL defaults and retains S256;
      actual provider enforcement and lifetime reconciliation are DI-070 checks.
- [x] Obtain revised spec/ADR approval before runtime work — **done 2026-10-18:** operator
      approved the amended spec; ADR-0016 accepted and ADR-0015 marked `superseded by
      ADR-0016` (status/link only, accepted body preserved). Approval authorized the OQ-7
      design, which was **ratified 2026-10-19** — R-1..R-6 implementation may now begin
      against the contract. **Amended 2026-10-23:** provider-independent configuration and
      custody development no longer depend on OQ-3; live work remains under DI-070.
- [x] Record operator approval (2026-10-23) of optional-but-validated endpoint behavior and
      separation of development delivery/version eligibility from AAP deployment integration.

**Build sequence:** documentation-only amendment commit for operator review → additive OQ-7
contract increment → R-1 + R-6 custody foundation increment → R-2/R-3 runtime workflow → R-4
attribution → R-6 provisioning/guides → development delivery. Keep the contract and foundation
increments separately reviewable; R-5 failure-first tests accompany each. DI-070 runs separately
when the real environment and authorization are available, not as a prerequisite to this sequence.

## Additive OQ-7 Contract Increment

- [x] Add tool-result authorization-required signal, stream v13 with all consumer surfaces,
      and audit delegation-mode contract/query parity; preserve existing callers and keep
      runtime delegation inert until configured (R-2b/c, R-4b).
- [x] Define route/request/response shapes and transaction-store Protocol/record fields with
      pinned TTL defaults; do not expose a usable authorization flow before trust/custody
      and policy checks are implemented. Test schema/consumer parity and safe omission.

**Implementation checkpoint — 2026-10-23 (contract increment only):**

- Tool-result serialization accepts closed, error-only metadata under the reserved code;
  legacy callers omit it. Canonical and packaged agent/worker schemas match; the worker
  accepts the reserved error as a failed report without retry. Stream v13 is represented
  in the schema, agent model/allowlist/normalizer, and portal model/decoder. Normalization
  projects only routing metadata; the portal deliberately performs no navigation,
  confirmation, or follow-up request.
- Audit stores persist/filter the optional top-level mode through query, summary, export,
  and gateway proxy. Legacy absence remains absent in responses and NULL in Postgres;
  it does not match explicit `none`. Existing CSV columns are unchanged. The additive
  column/index upgrade is exercised against a literal pre-increment schema.
- Closed public start/status and internal handoff models, strict 60/600-second defaults,
  and the frozen routing record/Protocol are defined. Internal code/state/provider URL
  values redact in ordinary dumps; future authenticated transport must explicitly unwrap
  them. Shape validation supplies no trust, endpoint allowlisting, or execution authority.
- **Not implemented:** transaction factory/backends, single-use start/state claims, encrypted
  PKCE/credential custody, provider URL construction/trust validation, callback handlers,
  acquisition, signal production/promotion and bounded stop, `targets:authorize` policy,
  authorization controls/status polling/Continue, or verified delegation emission. These
  remain R-1/R-6 foundation and R-2–R-5 workflow work; no usable OAuth route is registered.
- Evidence: tool-gateway `tests/test_tool_registry.py` and `tests/test_authorization_contracts.py`;
  agent-platform `tests/test_contract_adapter.py`; portal `stream/__tests__/decoder.test.ts`
  and `useChatStream.test.ts`; audit-service `tests/test_contracts.py`, `test_audit_store.py`,
  and `test_reporting.py`; platform-gateway `tests/test_authorization_contracts.py` and
  `test_audit_proxy.py`; execution-runtime `tests/test_signing.py` and `test_executor.py`.
  Failure-first signal/consumer/filter checks failed before support was added; negative,
  omission, legacy, and no-route checks pass. The first full execution campaign exposed
  stale packaged tool-result schemas (four parity failures; 788 checks passed). Fast
  regressions reproduced both schema drift and worker rejection, then all three passed
  after both packaged copies were corrected. The complete post-fix gate also passed.
- `make audit-contract-test` (also required by root `make verify`) passed against a fresh,
  loopback-bound disposable Postgres: legacy upgrade, idempotent initialization, NULL/none
  separation, committed round-trip through a fresh store, dedupe, combined filters,
  summary/window, and pagination. This is audit persistence evidence, **not** the R-6
  multiprocess custody/concurrency proof.
- Final verification: root `make verify` passed after the packaged-schema correction.
  All eight frozen Python product suites passed (**3,252 tests**, including 82 execution
  unit tests); portal **496 tests** and typechecked production build passed. Overlays,
  dashboards, policy/scenarios, version, secret vocabulary, password policy, secret-delivery
  demo, and disposable audit proof passed. The full execution-failure campaign passed
  **792 tests** (two baseline-red controls deselected by the existing campaign runner;
  no development subset), including the four previously failing parity cases.
  Local campaign evidence: `.workspaces/spec063-evidence/20261023T090319Z-c4c535bb76f7/`
  (`evidence.json` and `junit.xml`); exit 0, no host suspension or live acceptance.
  Scoped `git diff --check` passed, excluding untouched preexisting `.qoder` changes.
- This closes only the contract-increment checkpoint; rerun the full gate after subsequent
  runtime/foundation changes. At this pre-release checkpoint no version bump, commit of the
  increment, push, deployment, or live target validation had occurred. The later release
  authorization below supersedes that handoff state. **AAP compatibility unverified**;
  DI-070 remains pending.

**Release checkpoint — v0.50.0 (operator approved 2026-10-23):**

- Code and documentation review passed with no high-confidence correctness or security
  findings in the 37-file contract increment; unrelated repowiki changes were excluded.
- The operator explicitly selected **v0.50.0 for this contract-only increment**, authorizing
  version bookkeeping, commit/tag/push, image rebuild, and local Kubernetes deployment.
  Full SPEC-070 delivery moves to a later release, not yet selected; foundation/runtime
  tasks below remain open. No live AAP work or production delegation enablement is included.
- Release-version verification: root `make verify` passed again with all product versions
  at **0.50.0**: **3,252 Python tests**, **496 portal tests**, typechecked production build,
  static/overlay/policy/secret checks, and the disposable audit migration proof. The full
  execution-failure campaign passed **792 tests**, with the same two baseline-red controls
  deselected and no development subset; exit 0, no host suspension or live acceptance.
  Release campaign evidence: `.workspaces/spec063-evidence/20261023T150420Z-360617be3111/`
  (`evidence.json` and `junit.xml`). All eight regenerated lockfiles changed only their
  local package version, with no dependency upgrades. This evidence is separate from the
  pre-release implementation proof above; see the [changelog](../../../CHANGELOG.md#0500--2026-10-23).

**Release handoff completed — 2026-10-24:** commit `199331f` and annotated `v0.50.0`
were pushed after the L3 security review reported no issues. All nine platform images were
rebuilt and deployed to `orbstack` / `dev-luban-aiops` using
`0.50.0-dev-k8s-199331f-dirty-20261024004646`. Backend version/readiness, the deployed audit
migration, preserved credentials/SSO, and portal v0.50.0/ready indicators were verified.
Portal evidence was rendered DOM inspection; screenshot capture was unavailable. This
closes the contract-only release workflow, not SPEC-070 or DI-070.

## R-1/R-6 Foundation Increment — Verified; Runtime Integration Pending

The separately approved foundation adds strict delegated configuration, encrypted Postgres
custody, concrete single-use transaction stores, and fencing/recovery proofs. Factories
remain internal and disconnected from OAuth routes and connector acquisition. No release,
deployment, client registration, or live AAP testing is included. Existing machine-scheme
behavior and the v0.50.0 public contracts remain unchanged. Results below must distinguish
library/state-machine proof from the still-pending workflow and production provisioning.

**Pre-amendment foundation verification checkpoint — historical, incomplete:**

- The focused parser, custody, HTTP, browser, MCP, and unchanged authorization-contract
  tests passed (**406 tests**). The full tool-gateway suite passed (**793 tests**);
  shutdown telemetry exporters logged connection failures against the test loopback sink.
- The disposable Postgres proof passed in **17.4 seconds**, including the newly added
  explicit recovery-epoch operation. That run checked uncertainty only after cleanup.
- A subsequent stronger multiprocess proof **failed for both refresh and authorization
  completion**: pause the writer after its database commit but before completion returns,
  read from a separate store, terminate the writer, and read again. The installed grant
  remains usable; process-local blocking and compensating cleanup do not close this window.
  Reproduction: `UV_CACHE_DIR="$PWD/.workspaces/uv-cache" uv run --frozen --project
  products/tool-gateway python products/tool-gateway/tests/integration/delegated_custody.py`
  (one shell command). At that checkpoint both assertions failed; the earlier passing run
  did not establish the stronger completion guarantee. The amended expectations are below.
- The authoritative completion/acknowledgment boundary then required resolution before custody
  could be marked complete. Staged publication needed an explicit decision on survival of a
  lost final application response; this amended the absolute uncertain-completion quarantine
  guarantee, not merely its cleanup implementation.
- No disposable custody containers remained after those runs. Root `make verify`, Makefile
  custody-target integration, remaining fault coverage, and operator-guide handoff were then
  pending. No version, public schema, route, release, or deployment change was made.
  **AAP compatibility unverified**; SPEC-070 and DI-070 remain open.

**Publication amendment — operator approved 2026-10-24:** the operator selected database
publication as authoritative after reviewing the preceding failure. Unusable encrypted staging
is followed by atomic grant/authorization-status publication under fresh generation/epoch/key
checks. Lost provider responses or unacknowledged staging require reauthorization with no replay.
A committed publication may survive loss of its database acknowledgment or final application
response; the uncertain caller releases no token. Cleanup cannot revoke published/newer grants.
This supersedes the blanket uncertain-completion quarantine requirement, not the no-replay or
revocation guarantees. The attached foundation plan and accepted ADR bodies remain untouched.

**Post-amendment implementation/evidence:**

- Strict delegated parser and fresh-file reload, mapping-bound HMAC generations, AES-256-GCM
  keyring/envelopes, schema-version-1 migration, memory/Postgres transactions, start/state
  claims, staged publication, refresh/revoke, key rotation, and explicit recovery are internal
  library primitives. App wiring and public schemas are unchanged; existing schemes retain
  their projection and machine keep-last-good behavior.
- The single-use operation records are fields on locked credential/transaction-secret rows;
  there is no replayable generic payload or separate provider-operation queue. The registry
  uses one row per named set with a target field to prevent target replacement bypassing
  revision ordering; credential bindings additionally include the target and owner namespace.
- `products/tool-gateway/tests/test_delegated_configuration.py` and `test_delegated_custody.py`
  cover parser, crypto, and memory boundaries. HTTP, browser, MCP HTTP/stdio diagnostic,
  credential-set, and unchanged contract/no-route regressions pass. The initial post-amendment
  full tool-gateway suite passed **797 tests** (5.31 seconds). A later 22-case addition covered
  missing fields, ambiguous bracket authorities, and unknown-scheme log safety; its first run
  found supplied values in the legacy unknown-scheme warning (**1 failed, 209 passed**).
  After replacing that warning with a fixed message, the full suite passed **819 tests**
  (5.32 seconds), including all 210 delegated-configuration tests. Shutdown telemetry exporters
  logged nonfatal connection failures against the test loopback sink.
- `make delegated-custody-test` passed (**28.7 seconds**) and is now mandatory in `make verify`.
  Evidence source: `products/tool-gateway/tests/integration/delegated_custody.py`. Real
  Postgres 16, a dedicated non-superuser runtime role, four spawned contenders, repeated
  callback/refresh/revocation races, killed claimants, old-ciphertext restoration, absent
  capabilities, mapping/config fences, keyless revoke, pending-PKCE rotation, and offline
  recovery are asserted. Runtime cannot change key-policy values or migration version.
- Staging/publication boundaries are tested separately for refresh and authorization:
  concurrent reads and process termination before return, injected pre/post-commit errors,
  and a loopback PostgreSQL wire proxy that discards COMMIT acknowledgment before the driver
  sees it. Only published state survives response loss; unpublished candidates cannot renew.
  Intervening cancellation, expiry, revoke, and newer authorization fence publication; old
  cleanup preserves the newer grant. The formerly failing absolute-quarantine expectation
  was replaced explicitly under the approved contract, not reported as fixed unchanged.
- The dump assertion includes live encrypted PKCE material and encrypted refresh credentials;
  secrets/DSNs are never printed or retained as proof artifacts. These are custody/state-machine
  tests, **not** production provider identity verification or R-2/R-3 protocol evidence.
- The first foundation root `make verify` passed, including portal **496 tests** and the
  typechecked production build, disposable audit proof (**2.3 seconds**), custody proof
  (**26.7 seconds**), and the full execution-failure campaign (**792 passed, 2 deselected**,
  1493.04 seconds; existing baseline-red controls excluded, no development subset).
  Campaign evidence: `.workspaces/spec063-evidence/20261024T153130Z-4cd4a3a382d6/`
  (`evidence.json`, `junit.xml`); exit 0, no host suspension or live acceptance. Its tool-gateway
  stage preceded the final 22 tests/logging fix, so it was followed by the final-code rerun below.
- Existing configuration/tool/troubleshooting guides document inert behavior, fields/key format,
  publication, privilege separation, revocation, and externally fenced recovery. Schema proof is
  fresh creation/idempotence, not upgrading an older version-1 prototype. Full runtime integration,
  provisioning, R-4 attribution, R-5 disclosure, and development acceptance remain open.

**Final foundation verification and handoff:**

- Final-code root `make verify` passed: all eight frozen Python product suites (**3,472 tests**,
  including **819 tool-gateway tests**), portal **496 tests** and typechecked production build,
  all six overlays, dashboards, policy/scenarios, version lockstep at **0.50.0**, secret vocabulary,
  password policy, and the local secret-delivery demo. Disposable audit proof passed in
  **2.2 seconds**; the mandatory custody proof passed in **27.6 seconds**.
- The full execution-failure campaign passed **792 tests**, with the same **two baseline-red
  controls deselected** by its existing runner and no development subset (**1542.80 seconds**).
  Evidence: `.workspaces/spec063-evidence/20261024T160153Z-688fed78aa1a/` (`evidence.json`,
  `junit.xml`); exit 0, no host suspension, no live acceptance. Root output is retained locally
  in `.workspaces/spec070-foundation-verify-final.log`. The manifest's `delivery_complete:false`
  is not a test failure or a claim of live acceptance.
- Nonfatal warnings: test-sink OTLP export failures, Starlette/httpx deprecation, portal jsdom/
  notification limitations, and the existing Vite chunk-size warning. Scoped `git diff --check`
  and new-foundation-file trailing-whitespace checks passed. IDE diagnostics were unavailable
  because the language server was not ready; no IDE clean-bill claim is made.
- Disposable custody/audit/execution proof containers were absent after completion. Dependency
  changes are limited to psycopg/psycopg-binary **3.3.6** and its Windows tzdata dependency in
  tool-gateway's frozen lockfile; existing package versions were not upgraded.
- Only this internal foundation checkpoint is complete. No usable OAuth route/acquisition,
  provider identity verification, portal authorization control, production provisioning, version
  bump, commit/push/tag, image rebuild, or deployment was performed. Unrelated `.qoder/repowiki`
  work and the attached plan were preserved. **AAP compatibility unverified**; DI-070 is pending.

**Post-review concurrency correction — foundation re-verified before commit:**

- A code review of the uncommitted foundation, after the passing run above, found **two blocking
  P1 concurrency defects**. The earlier green suite is historical evidence and did **not** close
  them; the foundation was not checkpoint-ready until both were corrected and re-proved.
  - *Defect 1 — epoch reuse after rollback.* Uncertainty cleanup matched only
    binding/generation/epoch/unpublished-status. A claim whose transaction rolled back left the
    epoch unadvanced, so an independent successor could claim the same next epoch; the original
    attempt's late cleanup then revoked the valid successor (refresh) or broadly failed every
    pending owner transaction at the reused epoch (authorization).
  - *Defect 2 — mutable observed generation.* `invalidate_observed` re-read `self._observed`
    after its first await, so a delayed invalidation of generation G1 could invalidate a G2 that
    another coroutine activated on the same store while G1 awaited a connection.
- Correction: unpublished credential operations now carry an immutable random `attempt_id`,
  distinct from the operation/publication capability hash, generated before the claim can suspend
  and carried through claim → staging → publication → cleanup. Refresh keeps one attempt identity;
  authorization completion mints a fresh completion attempt associated with its exact challenge.
  Uncertainty cleanup is a compare-and-set on the full binding, generation, epoch, attempt
  identity, and unpublished status, so it can never revoke an active publication or a successor
  that reused an epoch; refresh cleanup touches no transaction and authorization cleanup fails
  only its own challenge. Process-local uncertainty blocks are attempt-scoped
  (`_blocked: set[(Owner, attempt_id)]`), so resolving one attempt cannot clear another's block.
  Callback-claim uncertainty is a compare-and-set on the stored callback operation, so an
  unacknowledged old claim cannot cancel a successor claim of the same challenge.
  `invalidate_observed` snapshots the observed generation before its first await and compares
  against that immutable local value only. Attempt metadata is cleared on publication, revoke,
  configuration invalidation, recovery, and generation reset.
- Schema fencing ships as an **explicit versioned migration to version 2**, not runtime DDL:
  `custody_schema.SCHEMA_VERSION == 2`, `DDL` creates a fresh v2 schema with `attempt_id` and two
  CHECK invariants (`credentials_attempt_fenced`, `credentials_attempt_cleared`), and
  `UPGRADE_V1_TO_V2` idempotently adds the column, fences legacy unpublished rows that lack
  attempt identity, preserves published active rows, adds the constraints, and bumps the version.
  Runtime `initialize()` rejects any schema whose version is not exactly 2.
- Failure-first regression evidence (deterministic, real Postgres, no timing sleeps):
  `tests/integration/delegated_custody.py` adds `refresh_successor_survives_stale_cleanup`,
  `authorization_successor_survives_stale_cleanup`, `callback_claim_cleanup_is_attempt_scoped`,
  `observed_generation_snapshot_is_immutable`, and `migration_upgrades_v1_and_fences_legacy`.
  Removing the `attempt_id` predicate from cleanup failed the proof at *"stale attempt cleanup
  cannot revoke the successor refresh"*; reverting the observed-generation snapshot failed it at
  *"a delayed G1 invalidation leaves G2 active"*. With both corrections restored the full proof
  passed (**30.6 seconds**). `tests/test_delegated_custody.py` adds three pure-Python regressions
  for attempt-scoped local blocks, the versioned schema/attempt invariants, and the immutable
  refresh-claim attempt identity; the focused file passed **10 tests** and the full tool-gateway
  suite passed **822 tests** (5.08 seconds), with only the known nonfatal test-sink OTLP export
  warnings. **AAP compatibility unverified**; DI-070 remains pending.
- Post-correction root `make verify` passed (exit 0, **29m44s**): all eight frozen Python product
  suites (agent-platform 1539, audit-service 144, execution-runtime 82, identity-broker 61,
  incident-service 138, platform-gateway 398, skills-hub 291, tool-gateway **822**), portal **496
  tests** and the typechecked production build, all overlays/dashboards/policy/scenarios, version
  lockstep at **0.50.0**, secret vocabulary, password policy, and the secret-delivery demo. The
  audit-contract proof passed (**2.1s**), the mandatory custody proof passed (**28.7s**) including
  the new attempt-fencing/callback-CAS/observed-snapshot/v1→v2-migration block, and the full
  execution-failure campaign passed **792 tests, 2 deselected** (**1544.80s**, exit 0). Evidence:
  `.workspaces/spec070-foundation-verify-postcorrect.log` and
  `.workspaces/spec063-evidence/20261024T181017Z-f80b24431add/` (`evidence.json`, `junit.xml`).
  No host suspension and no live acceptance; the manifest's `delivery_complete:false` is not a
  test failure. Nonfatal warnings were limited to the known test-sink OTLP export failures and
  Starlette/httpx deprecation notices.

## R-1: Credential Configuration

- [x] Pin provider-independent parser field names/types and `oauth2_authorization_code`
      validation/projection; preserve existing scheme/default parsing and browser credential
      behavior (R-1a–c foundation; parser and connector regressions above).
- [x] Reject unsupported/incomplete/untrusted config with safe warnings and zero network calls;
      prove delegated generation invalidation on change/removal without changing machine sets.
- [x] Test optional endpoints absent/present/invalid in parser/custody primitives: absent renewal
      is explicitly unsupported, absent provider revocation still permits local revoke, and
      missing identity evidence blocks installation. No guessed endpoint or fallback.
- [ ] Exercise these capabilities through actual delegated acquisition and provider identity
      verification with deterministic OAuth/target fixtures (R-1 runtime integration with R-2/R-3).

## R-6 Foundation: Encrypted Postgres Custody

- [x] Implement gateway-owned schema and isolated proof role, versioned authenticated encryption,
      owner/target binding, per-operation key loading, and product dependency/frozen lockfile
      (R-6a library foundation; production role/key mounts remain below).
- [x] Implement single-use memory/Postgres transactions and cross-process generation/epoch
      fences, staged publication, refresh rotation, local revoke, and cache-check primitives;
      fail closed on store/key failure. No access-token cache/acquisition is wired yet.
- [x] Prove real-Postgres concurrency, ciphertext substitution denial, key rotation, crash/restart,
      simulated lost provider response, actual lost commit acknowledgment, and no revoked-epoch
      resurrection (R-6b foundation under the approved database-publication amendment).
- [ ] Integrate custody into actual provider acquisition/callback/cache behavior and exercise
      the complete lifecycle against deterministic OAuth/target fixtures (R-2/R-3 and R-6 completion).

## R-2: Acquisition and First-Use Workflow

- [ ] Thread verified identity through HTTP and existing MCP calls into the resolver; add a
      separate user-delegated client, not changes to the machine-grant client (R-2a–b).
- [ ] Implement generation-bound cache, bounded expiry, single-flight, safe token-response
      validation, and supported refresh behavior (R-2a/e).
- [ ] Implement the ratified gateway/agent/portal authorization-required contract and minimal
      workflow feedback; first-use redirect only for the needed target, no settings UI (R-2c).
- [ ] Implement owner-only status/return, cancellation/expiry, and bounded stop/continue;
      completion never dispatches/replays a write or bypasses approval/claims (R-2d).
- [ ] Test first-use, later no-prompt renewal, HTTP/MCP isolation, absent user/grant, transient
      failure versus reauthorization, cancellation, duplicate/expired state, and safe continuation.

## R-3: Trust and Callback Security

- [ ] Implement exact HTTPS callback/endpoint validation, state + PKCE S256, initiating
      browser/user binding, single-use replay protection, and safe return locations (R-3a).
- [ ] Verify target immutable account identity against trusted linkage; reject wrong-account
      login, bad issuer/audience/nonce, and username/email-only linking (R-3b).
- [ ] Enforce separate Luban policy/target RBAC and destination-bound HTTP/MCP credentials;
      prove no leakage to another allowed origin or redirected token endpoint (R-3c/d).
- [ ] Pin/test local cache delays and handling of target revocation, account disable, and
      group removal with deterministic target fixtures; separate SSO logout from target
      grant revocation (R-3e). Actual provider propagation measurements belong to DI-070.

## R-4: Verified and Queryable Attribution

- [ ] Record human, service actor, verified target identity, mode, signed correlation, and
      safe authorization/acquisition failure classes; preserve redaction-overflow attribution.
- [x] Implement the ratified audit schema/filter change and asserting durable query proof
      (R-4b contract/persistence groundwork; v0.50.0 evidence above).
- [ ] Emit and test verified delegation attribution end to end; a configured mode label
      alone cannot mark successful delegation (R-4a/c and runtime R-4b integration).

## R-5: Failure-First Security Invariants

- [ ] Prove target access tokens memory-only and refresh tokens ciphertext-only; callback
      code/state handled backend-only and omitted from JS/logs/referrers (R-5a).
- [ ] Inject opaque test secrets into URLs, headers, responses, errors, logs, traces, results,
      evidence, and audit; repair uncovered representations; pass secret-vocabulary gate (R-5b).
- [ ] Spy on Basic/bearer/machine/unauthenticated/alternate-transport paths, including MCP
      diagnostics/stdio; failed delegated acquisition invokes none (R-5c).
- [ ] Assert failure-first callback/identity/key/store/token endpoint/malformed-response tests
      open no target session and never grant execution authority (R-5d).

## R-6 Completion: Provisioning and Operator Documentation

- [ ] Wire file-mounted target/client config plus least-privilege database/key mounts and
      network access; keep delegation disabled until provisioned; pass `make overlays` (R-6c).
- [ ] Update existing operator/configuration/troubleshooting guides for registration, first-use,
      renewal, recovery, key rotation, revocation/offboarding, rollback, and SSO limits (R-6d).
- [ ] Exercise setup, disconnect, recovery, and rollback against deterministic OAuth/target
      fixtures and real Postgres. Document DI-070 as pending, with no AAP compatibility claim.

## Acceptance-to-Test Matrix

Full development acceptance R-1a–R-6d remains **open**. Evidence above covers R-2/R-4 contract
shapes and R-1/R-6 internal configuration/custody primitives, not the full runtime/security
obligations below. Replace each remaining obligation with concrete test paths/names and results
before delivery; this matrix is not execution evidence. Integration tests must exercise real
Luban enforcement against deterministic OAuth and per-user target fixtures, not canned
shared-bearer success. DI-070 separately tracks actual AAP evidence.

| Criteria | Planned asserting coverage | Primary boundary |
| --- | --- | --- |
| R-1a, R-1b, R-1c | Existing scheme/projection regression; optional endpoints absent/present/invalid; unsupported trust/scopes; zero network on rejection | tool-gateway |
| R-2a | Two users/two targets; cache expiry, scope/generation isolation, single-flight | HTTP + MCP + Postgres |
| R-2b, R-2e | Missing grant/user; malformed response; refresh success/denial/unsupported; transient-error distinction; zero resource sessions after failure | tool-gateway + deterministic OAuth |
| R-2c | First-use redirect only for needed target; no settings/manual tokens; no loop on cancellation | gateway + portal |
| R-2d | Owner return/status; cancellation; current-policy continue; no callback dispatch, consumed-claim reuse, or unknown-write retry | agent + portal + signed execution |
| R-3a | State/code replay, CSRF, mandatory S256, TTL boundaries, mix-up, browser/session substitution, open redirect | gateway callbacks + deterministic OAuth |
| R-3b, R-3c | Wrong/missing account evidence; immutable linkage; ID-token validation when used; independent platform/target allow/deny | gateway + deterministic per-user target |
| R-3d | Allowed-but-unrelated origin, HTTP redirect, MCP destination, token-endpoint redirect | HTTP + MCP |
| R-3e | Group-removal/account-disable/revocation response handling, explicit lifetimes, logout distinction, bounded cache delay | local enforcement + deterministic target lifecycle |
| R-4a, R-4b, R-4c | Verified mode/account; failed enrollment; durable audit filter round-trip; signed correlation; overflow | gateway + audit |
| R-5a, R-5b | Ciphertext-only refresh; memory-only access; opaque-secret injection; callback/access-log/JS/referrer exclusions | gateway + portal + telemetry |
| R-5c, R-5d | Every fallback spy remains zero; key/store/provider/callback failure opens no resource session | HTTP + MCP + callback |
| R-6a, R-6b | Real-Postgres owner/target substitution, concurrent rotation/revoke, lost response, restart/key rotation; mandatory local revoke despite missing/failed remote endpoint | independent processes + Postgres |
| R-6c, R-6d | Overlay rendering; disabled-until-configured; exercised setup/revocation/recovery/rollback; pending-integration disclosure | GitOps + operator guides + deterministic target |

## Delivery Gate

These gates apply to eventual full-spec delivery. Passing contract/foundation checkpoints above
does not close runtime acceptance or replace verification after the remaining implementation.

- [ ] Gate 0 and 2026-10-23 amendment recorded; all development criteria R-1a–R-6d mapped
      to actual asserting tests and passed; every changed contract tested in its consumers.
      DI-070 is explicitly outside this development gate, not represented as passed.
- [ ] Root `make verify` passes, including secret vocabulary, overlays, portal tests/build,
      policy, dashboards, version checks, and disposable execution-failure campaign.
- [ ] Existing-scheme regressions and every no-fallback/no-disclosure test pass.
- [x] ADR-0016 accepted/indexed and ADR-0015 supersession recorded (2026-10-18).
- [ ] Living state docs updated to implemented behavior, not planned capability; SPEC-069's
      delivered dev record preserved and its production dependency status updated accurately.
- [ ] Mark `delivered` only after R-1a–R-6d development acceptance passes. Release bookkeeping
      and `VERSION` changes still need separate authorization; pending DI-070 does not block
      either. Release notes and living guides explicitly say **AAP compatibility unverified**
      and link the integration task until its actual evidence is recorded.

## Post-Delivery Deployment Integration (DI-070)

- **Status:** pending / environment-blocked; no live proof run. Not a development acceptance
  criterion and not a condition for SPEC-070 delivery, version eligibility, or later development.
- **Owner:** workspace operator, with the AAP administrator supplying deployment facts and
  approving scoped accounts/configuration. No external task or target resource is created here.
- **Trigger:** reachable intended AAP/MCP environment, two users with distinct RBAC, and separate
  authorization for registration/configuration/token tests. Complete before enabling production
  user-delegated AAP use; authorized validation is limited to the named test target/accounts.
- **Traceability:** carries OQ-3 and former development criterion R-6e, plus actual-target
  verification of R-3b/c/e. These obligations are retained, not checked off by development tests.

| Task | Required actual-target evidence | State |
| --- | --- | --- |
| DI-070a / OQ-3 | AAP release/patch, MCP build, SSO version/mappings, explicit endpoints, confidential client/callback, scopes, external-user eligibility, identity evidence/linkage, refresh/rotation/revocation and lifetimes; no secrets in the record | Pending |
| DI-070b / security profile | Demonstrate enforced S256, wrong/missing verifier refusal, exact callback and immutable-account linkage. Reconcile local 60/600-second defaults with real authorization-session/code limits and consent dwell | Pending |
| DI-070c / R-6e + R-3b/c | Two distinct-RBAC users: first-use and reauthorization, later no-prompt renewal, wrong-account rejection, platform/target denial, and accurate human/service/target audit attribution | Pending |
| DI-070d / R-6e + R-3e | Revocation, account disable/group removal, measured propagation/cache delays, restart, unavailable target, configuration removal, local disconnect despite failed remote revoke, and no fallback/replay | Pending |
| DI-070e / integration closure | Sanitized run evidence tied to exact build/configuration and results; restore validation resources; operator acceptance and explicit production-enable authorization | Pending |

**Known integration risks and stop conditions:**

- PKCE may be unsupported, disabled on a migrated app, or unenforced; block that target until
  verified/configured. No version-based assumption or automatic downgrade.
- Local TTLs may outlast the provider's authorization session/code or be too short for consent;
  reconcile configuration and test expiry. Never extend provider validity or weaken single use.
- Actual refresh issuance/rotation, identity response/linkage, or RBAC/offboarding behavior may
  differ from fixtures. Missing required identity or renewal blocks target qualification;
  absence of provider revocation must be explicitly recorded with the offboarding procedure,
  never represented as successful remote revocation.
- A configuration mismatch may be resolved within the separately authorized integration work.
  A product behavior gap requires a scoped fix/review and, if necessary, a separately approved
  patch or follow-up spec. Do not silently rewrite the delivered spec or claim universal support.

> **Forward path.** SPEC-070 is the production-identity dependency SPEC-069 R-1 names; the
> Layer-2 runbook-typed-tools fast-follow (number assigned at its own drafting) also relies
> on it for user-delegated action attribution. SPEC-069's read-only **dev** slice does not
> block on SPEC-070 — it validates against a self-hosted server's own auth.
