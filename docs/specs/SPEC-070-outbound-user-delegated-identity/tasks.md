# SPEC-070 Tasks: Outbound User-Delegated Execution Identity (Tool-Gateway Substrate)

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

> **Development acceptance recorded; runtime unreleased (status update 2026-10-30).**
> ADR-0016 remains accepted and OQ-7 ratified. R-1a–R-6d are checked in the
> [acceptance matrix](#acceptance-to-test-matrix), with root `make verify` EXIT=0.
> The foundation is committed as `83e0f94`; subsequent runtime changes remain uncommitted.
> The workflow, custody, attribution, and provisioning implementation is default-off,
> not part of the deployed contract-only v0.50.0 checkpoint. The operator authorized staging
> and the Unreleased/living-doc update, not a version bump, release, or deployment.
> **AAP compatibility unverified**: OQ-3/R-6e remain under [DI-070](#post-delivery-deployment-integration-di-070).
> Real-browser UI screenshots remain environment-blocked as recorded in p6. Plans and
> accepted ADR bodies are unchanged; the `delivered` gate remains open.

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

## Runtime Identity Checkpoint — 2026-10-25

- The corrected foundation was committed separately as `83e0f94`. Subsequent runtime changes
  remain uncommitted; VERSION remains **0.50.0**. No deployment or live target work occurred.
- Signed v3 requests now accept the bounded, all-or-none requester/decider namespace/subject
  quartet. Every present field is HMAC-covered. An explicit execution-ledger v2 migration
  preserves the original v1 SQL and historical evidence, requires disabled admission, and
  rotates the admission epoch on upgrade. This ledger migration is separate from custody v2.
- New delegated-capable sessions bind immutable requester identity at birth, using strict
  RS256 issuer/audience/provenance verification. Backend metadata is not publicly projected.
  In-memory, Redis, and Postgres creation preserve existing ownership; legacy sessions remain
  unbound. Real-Postgres session binding/race proof passed (**1 passed, 796 deselected**, 11.76s):
  `.workspaces/spec063-evidence/20261025T043943Z-cbb60de94f1d/`. This was a focused selection,
  not the full execution-failure campaign.
- Agent routes and root/resumed kernel turns independently verify enabled-mode human identity.
  Requester and approver contexts stay separate; approval keeps the approver's primary bearer.
  Approval and denial re-parking preserve the requester. Missing/expired/substituted identity
  stops pending dispatch with fresh-turn guidance. Setup failure, foreign session input,
  cancellation, and generator closure clear the held requester bearer and original registry claim.
- Failure-first tests reproduced three kernel continuity/cleanup defects (**3 failed, 39 passed**)
  before correction. Platform cache tests reproduced six defects (**6 failed, 12 passed**):
  cross-source/trust reuse, missing-source/config bypass, unbounded retention, and raw exception
  disclosure. Enabled cache reuse now binds the exact source token and exchange/trust configuration;
  the memory-only LRU is capped at 1,024 entries and exchange warnings contain no raw exception.
- Final affected suites passed with exit 0: `uv run --project products/agent-platform --frozen
  pytest products/agent-platform/tests -q` (**1,600 passed**, 36.32s) and `uv run --project
  products/platform-gateway --frozen pytest products/platform-gateway/tests -q` (**407 passed**,
  one warning, 12.74s). Known shutdown OTLP failures and Starlette/httpx deprecation remain.
  `git diff --check -- products shared docs` passed. Route tests use genuine fixture JWT signatures;
  platform session-birth tests capture the actual upstream HTTP request. Kernel event/ledger doubles
  do not establish real AgentScope middleware or durable delegated dispatch acceptance.
- **Still open:** target acquisition/provider validation, OAuth/browser workflow, bounded kernel
  stop/Continue, verified attribution, provisioning, and full runtime/browser/root acceptance.
  The earlier foundation root gate is not final runtime evidence. R-1–R-6d remain open at their
  end-to-end boundaries; **AAP compatibility unverified**, DI-070 pending.

## Worker Transport + Private Gateway Dispatch Checkpoint — 2026-10-25

- Separate requester transport (agent side): the signed v3 envelope still carries only the bounded
  identity quartet; the requester's own bearer now travels *separately* over the authenticated
  agent→worker channel. `handoff_original` binds it under the same all-or-none rule (identity present
  ⇒ a nonempty requester token, else `credential_missing`; a requester token on a machine envelope ⇒
  `bad_request`, no send). `_invoke_v3` gates the requester token on `IDENTITY_FIELDS.issubset(envelope)`
  via a new no-fallback `generation_owner_token()`, so an ordinary SPEC-063 durable resume (owner token
  set, no quartet) is never mis-bound. Focused suites passed (**90 passed**).
- Worker executor forwarding: after its normal durable send claim and `check_send`, the executor posts
  the verified projection plus *both* human bearers to the private route `/api/v2/tools/invoke-delegated`
  under the projected execution-runtime workload token (dedicated audience
  `luban-target-execution-handoff`, re-read per send, no static fallback). `check_send` and
  `read_workload_token` run *before* the POST so a refusal reason (`identity_conflict`/`unauthorized`/
  `credential_missing`) survives instead of being flattened to `response_invalid`. Executor + handoff
  suites passed (**53 passed**).
- Private gateway route (tool-gateway): `POST /api/v2/tools/invoke-delegated` is off by default
  (`GATEWAY_DELEGATED_INVOKE_ENABLED`) and callable only by the exact execution-runtime workload
  identity. It independently re-verifies both human bearers against the delegated-identity trust config
  (RS256 issuer/audience/JWKS, `oidc` provenance, `act` actor allowlist, integer exp>iat, bounded
  immutable sub/username) and their equality to the signed projection quartet, re-derives
  `canonical_digest(parameters) == projection.args_digest` (a pure digest — the execution HMAC signing
  secret is never distributed here), then applies the *existing* invocation/mutation policy under the
  approver's roles via a shared `_dispatch_invocation` extracted from `invoke_tool`. The verified
  requester is bound into connector identity as the inert acquisition seam (`delegated_requester_*`),
  carrying no policy authority. Enabling the route without the full human + workload trust sets fails
  closed at startup. Failure-first: **12 failed → 12 passed** on the route/verification cases, plus
  5 fail-closed configuration cases (**17 passed** in `test_delegated_invoke.py`); full
  tool-gateway suite **834 passed** with no regression from the `invoke_tool` refactor.
- These are unit/HTTP-boundary proofs with real RSA-signed fixture JWTs (human + workload) and patched
  JWKS resolvers. **Not** established: a real end-to-end worker→gateway HTTP dispatch, target
  acquisition/provider validation, or live AAP behavior. No version bump, commit, push, deploy, or live
  target work occurred; VERSION remains **0.50.0** and these runtime changes remain uncommitted.
- **Still open:** target acquisition/provider validation, OAuth/browser workflow, bounded kernel
  stop/Continue, verified attribution, provisioning (GitOps + operator guides for the new
  `GATEWAY_DELEGATED_*` / `GATEWAY_EXECUTION_WORKLOAD_*` vars), and full runtime/browser/root
  acceptance. R-1–R-6d remain open at their end-to-end boundaries; **AAP compatibility unverified**,
  DI-070 pending.

## Delegated Acquisition + HTTP/MCP Enforcement Checkpoint — 2026-10-26

- Acquisition engine (`tools/user_delegated_client.py`): a process-local, memory-only LRU access cache
  (≤1,024 entries) keyed by trusted owner, set, target/audience/resource, granted scopes, configuration
  generation, credential epoch, and recovery epoch; single-flight per binding with a bounded 5-second
  wait that returns a safe `acquisition_in_progress` error (never an enrollment challenge); code
  redemption and refresh; provider identity verification under the `json_immutable_id` profile *before*
  any custody publication or target send; publication-before-send revalidation; and grant-fenced
  invalidation (revoke + evict) on a target 401/invalid-token. Two explicit string-valued delegated
  policy fields — `access_cache_ttl_seconds` (≤300) and `refresh_max_lifetime_seconds` (≤2,592,000) —
  are validated and folded into the configuration fingerprint. Distinguished failure kinds: transport,
  malformed response, unsupported renewal, missing identity, configuration, store, authorization-required,
  acquisition-in-progress, invalid-grant.
- Resolver seam (`tools/auth_resolution.py`): `resolve_outbound_auth` gained an `oauth2_authorization_code`
  branch that acquires through the injected user-delegated client and returns a `ResolvedAuth` carrying
  private verified acquisition metadata (not a connector configuration label). The machine-grant branches
  (basic/bearer/oauth2_client_credentials) are unchanged; a delegated set with no client/context fails
  closed.
- HTTP enforcement (`tools/http_connector.py`): the typed requester/acquisition context is threaded through
  the single transport call site; the selected set's exact `resource_origins` allowlist is enforced on the
  initial request *and* every GET redirect hop alongside (never widened by) the connector-wide
  `GATEWAY_HTTP_ALLOW_ORIGINS`; write no-redirect/no-retry behavior is preserved; a terminal target 401
  triggers grant-fenced invalidation while a 403 stays a permission denial, and invalidation failure never
  masks the observed 401.
- MCP enforcement (`ingestion/mcp_adapter.py`): delegated MCP supports only the bearer-capable
  `streamable_http` transport — stdio/non-bearer is refused *before* any subprocess/session; the endpoint
  is validated before the session opens; redirects and automatic auth/reconnect retries are prohibited
  (`follow_redirects=False`); the session is single-shot and closed when the invocation ends, with a
  per-call client (no pooling across users); diagnostics (`list_server_tools`) with no verified user report
  configuration but open **no** authenticated target connection.
- Zero-fallback counters prove that on every delegated failure there are zero calls to Basic, static-bearer,
  machine-grant, unauthenticated, and alternate-transport paths (counting machine client `== 0`, empty
  session/bearer logs, and an alternate-transport opener that raises if created).
- Lifespan wiring (`app.py`, `core/config.py`, `ingestion/ansible_binding.py`): a *separate* user-delegated
  client — distinct from the machine-grant token client, which is unchanged — is composed once in
  `_build_tool_registry` behind `GATEWAY_DELEGATED_ACQUISITION_ENABLED` and threaded into both the HTTP
  connector and the Ansible MCP binding. The gate is default-off and fail-closed: enabling it requires an
  explicit Postgres DSN, keyring path, delegated config path, set id, and a trusted HTTPS callback whose
  path is the ratified `/api/v1/targets/authorizations/callback`, else startup aborts. Client construction
  is side-effect free (the custody store connects lazily per acquisition; the keyring reads lazily), so no
  database/keyring/provider connection opens at startup. When the gate is off the factory returns `None`
  and a delegated set fails closed at the connector. New `GATEWAY_DELEGATED_ACQUISITION_*` /
  `GATEWAY_DELEGATED_CUSTODY_*` vars are documented in the configuration reference.
- Failure-first: **9 → 9 passed** on the HTTP delegated cases, **6 passed** on the MCP delegated cases, and
  **11 passed** on the acquisition-wiring cases (`test_delegated_acquisition_wiring.py`); full tool-gateway
  suite **940 passed** with no regression. One pre-existing foundation assertion
  (`test_delegated_foundation_opens_no_target_or_token_connection`) was reconciled from `error` to the
  precise `denied`/`DELEGATED_CONTEXT_REQUIRED` fail-closed posture, preserving its no-connection/no-leak
  intent.
- These are unit/HTTP-boundary proofs with `httpx.MockTransport`, faked MCP session openers, and stub
  custody/delegated clients. **Not** established: a real end-to-end delegated dispatch against a live
  provider or AAP, the OAuth/browser authorization workflow (custody transaction store + portal routes),
  provider identity verification over a real HTTPS identity endpoint, verified attribution, or provisioning
  (GitOps role/key mounts). No version bump, commit, push, deploy, live OAuth registration, or live AAP
  request occurred; VERSION remains **0.50.0** and these runtime changes remain uncommitted.
- **Still open:** OAuth/browser workflow (transaction store, five ratified portal routes + browser-reset,
  cookie/transaction binding, callback/clean return), bounded kernel stop/Continue, verified attribution and
  disclosure controls, provisioning (R-6c/R-6d), and full runtime/browser/root acceptance. R-1 runtime
  integration, R-2/R-3, and R-6 completion remain open at their end-to-end boundaries; **AAP compatibility
  unverified**, DI-070 pending.

## Browser Binding, Authorization Routes, and Callback Checkpoint — 2026-10-29

- [x] Custody v3 migration and browser-binding primitives: hash-only per-challenge cookie proof,
  at most eight outstanding bindings, proof checks at start consumption and callback claim,
  and bounded owner logout cleanup. The explicit v1→v2→v3 migration fences incompatible pending
  prototype transactions while preserving published grants; runtime never runs DDL.
- [x] Six internal tool-gateway routes and six public platform-gateway routes are registered
  behind default-off gates. Human start/status/cancel/reset uses independently verified identity
  and `targets:authorize`; provider navigation/callback uses the separate projected platform
  workload token. Stored state plus browser proof selects owner/set, never a caller owner field.
  Platform initiation/status additionally checks the owned session and matching durable evidence.
  Route tests with memory custody are orchestration evidence, not runtime grant publication proof.
- [x] Platform browser edge creates a 256-bit Secure/HttpOnly/SameSite=Lax host-only cookie,
  capped at the remaining transaction lifetime and 600 seconds. JavaScript receives only a
  backend start path; the provider URL is returned by an empty 302. Callback input is parsed
  from bounded raw query data, rejects duplicate/ambiguous/malformed code/state and nonempty
  bodies, normalizes denial, and never forwards provider descriptions/URIs. Every callback result
  is an empty noncacheable/no-referrer 302 to `/` or a matching clean challenge path.
- [x] Dedicated authorization workload mount is reread per handoff (≤16 KiB), without Basic/static
  fallback or retained human tokens. Internal transport is nonretrying, no-redirect/no-environment-
  proxy, with a 10-second deadline and 64-KiB response cap. Duplicate JSON keys, invalid cleanup
  acknowledgments, and unsafe return locations fail closed without clearing cookies. A lost
  callback acknowledgment does not undo publication; a fresh owner status read is authoritative.
- [x] Portal same-origin status/return API and Chat/Studio selection check authentication, session
  ownership, and durable matching evidence before selecting the conversation and replacing the
  path with `/`. Target returns are not interpreted as login callbacks. Logout attempts bounded
  authenticated browser-reset before clearing stored bearer. No callback/return dispatches a tool,
  resumes approval, or automatically continues a turn; signed-out returns give sign-in guidance.
- [x] Initial disclosure controls: platform application/uvicorn route templates and HTTP log-record
  sanitation precede handlers; all eight telemetry modules retain byte parity with additive URL
  exclusions; authorization server spans and platform handoff client instrumentation are excluded
  at source. Tests inspect actual in-process exported spans. Portal nginx excludes request-derived
  strings from access logs, suppresses server request-error context, and refuses `/api/v2/`.
- Failure-first evidence: the resumed callback selection reproduced **3 failures** (blank/non-ASCII
  state and a GET body forwarded). Expanded callback/cleanup acknowledgment coverage produced
  **14 failed, 1 passed** before correction; the portal accepted an array-valued status through
  string coercion (**1 failed, 8 passed**). After correction, platform edge/contracts passed
  **69 tests**; focused portal API/return/logout tests passed **23 tests**. Newline ID/path tests
  already passed and required no parser change. Earlier logging/span and logout tests also failed
  before their implementation in this increment; no mocked result is presented as live acceptance.
- Broader regression found **3 worker signing cross-verification import failures, 91 passed**:
  the isolated test loader predated the agent's real delegated-identity dependency. The loader now
  imports that real module and restores its module entry; signature checks were not stubbed/removed.
- Final affected Python suites: `OTEL_ENABLED=false uv run --project products/<product> --frozen
  pytest products/<product>/tests -q` passed for all eight products (**3,819 tests**): agent 1,612,
  audit 144, execution-runtime 94, identity-broker 63, incident 138, platform 473, skills 291,
  tool-gateway 1,004. Agent/audit passed before the worker test-loader-only correction; the remaining
  six suites were rerun after it. This includes packaged-contract and cross-product helper parity.
- `npm --prefix products/operator-portal/web-ui/app test` passed **519 tests in 37 files**;
  `npm --prefix products/operator-portal/web-ui/app run build` passed TypeScript and Vite.
  `make validate-policy validate-policy-scenarios validate-secret-vocabulary validate-version
  delegated-custody-test` passed: **20 rules, 144 API scenarios, 32 tool scenarios**, vocabulary and
  version parity, and the real disposable-Postgres custody proof (**29.1 seconds**, including v1→v3).
  Isolated `nginx -t` passed against the existing local web-ui image; no image was rebuilt/deployed.
- Nonfatal warnings: Starlette/httpx deprecation, loopback OTLP exporter shutdown failures, portal
  jsdom/notification limitations, Vite chunk size, and the expected tool-engine approval-rule warning.
  IDE diagnostics were unavailable because the language server was not ready. Scoped
  `git diff --check -- products shared docs` passed after removing a trailing blank line in the
  custody schema module. Existing operator guides now describe the implemented default-off edges,
  current schema/trust settings, and remaining limits; unrelated `.qoder` work and both protected
  plans were preserved. Root `make verify` was not run at this partial workflow checkpoint.
- [x] **Atomicity follow-up:** at this callback checkpoint, `AuthorizationService.provider_url`
  still called `consume_start`, entitlement validation, and `prepare_state` separately. The gap was
  subsequently closed by the atomic-start checkpoint below; the earlier callback proof alone did
  not establish atomic preparation.
- [ ] Bounded kernel stop/durable evidence production, authorization cards/polling/Cancel and explicit
  fresh-turn Continue, verified attribution, remaining provider-operation disclosure controls,
  provisioning, real nginx request-log canaries, HTTPS browser/replica/provider integration, and final
  root `make verify` remain pending. No integrated OAuth or full R-1–R-6d acceptance is claimed.
  The foundation commit remains `83e0f94`; runtime changes are uncommitted, VERSION is **0.50.0**,
  and no push, deployment, live OAuth registration, or live AAP contact occurred. **AAP compatibility
  unverified**; DI-070 remains separate and pending.

## Atomic Start Preparation Checkpoint — 2026-10-29

- [x] `s70-wf-atomic`: `consume_start` now consumes the browser-bound handle and prepares state/PKCE
  atomically. The Postgres guarded transaction locks configuration and transaction/secret rows,
  checks exact owner mapping, target/generation, credential epoch, and database expiry, then writes
  the spent start, state hash, verifier ciphertext, and key id together. Expiry is checked again at
  the write. The old separately callable `prepare_state` surface is removed from both backends.
- [x] A private `PreparedStart` suppresses state/verifier representation and returns only after the
  explicit `start_prepare` commit acknowledgment and connection exit. The service rechecks current
  entitlement before constructing the provider URL. Memory preparation performs one non-suspending
  replacement only after private material generation succeeds; memory is still isolated-test-only.
- [x] Encryption/pre-commit failure leaves the original start intact; committed preparation survives
  acknowledgment/final-response loss as spent, never reconstructing another URL. No automatic retry,
  state recovery, credential revocation, or new migration is introduced. Existing v3 ciphertext
  bindings and callback/publication authority are preserved. Cancel/expiry can retire pending work.
- Failure-first evidence: the new service regression failed because PKCE generation failure left
  `start_consumed=True` (**1 failed, 54 deselected**). The real disposable-Postgres proof then failed
  with `atomic start must acknowledge its commit`, before runtime correction. Both passed after
  the store/service changes. Final focused browser/store/service tests passed **75 tests**.
- [x] Expanded real Postgres proof covers encryption failure; rollback and task cancellation before
  commit; post-commit failure/cancellation; actual COMMIT-response loss through the loopback wire
  proxy; four independently started processes competing for one start; revocation before the
  winner's callback; and process termination after commit but before URL release. Refusal cases
  cover malformed/missing/wrong/excessive browser proofs, exact namespace/sub mapping, database
  expiry despite application-clock skew, expiry between lookup and write, cancel/revoke/newer-grant
  fences, and configuration replacement. Secret-row assertions prove hash/ciphertext-only storage;
  URL-build/provider-call counters remain zero for failed/unacknowledged preparation.
- A new foreign-namespace fixture initially collided with an older ciphertext test's single-set
  assumption. Isolating navigation guard fixtures into their own credential set restored the full
  proof without weakening that existing assertion. All prior publication, refresh, key lifecycle,
  migration, restricted-role, and callback race checks remain enabled.
- Final verification:
  - `OTEL_ENABLED=false uv run --project products/tool-gateway --frozen pytest
    products/tool-gateway/tests -q`: **1,007 passed**.
  - Corresponding full platform-gateway command: **473 passed**, one Starlette/httpx warning.
  - `make delegated-custody-test`: **passed, 32.0 seconds** on the final expanded proof.
  - `make validate-policy validate-policy-scenarios validate-secret-vocabulary validate-version`:
    **20 rules, 144 API scenarios, 32 tool scenarios**, vocabulary/marker/shape parity, and **0.50.0**
    version parity passed. `git diff --check -- products shared docs` passed.
  - Nonfatal loopback OTLP exporter shutdown failures and the expected tool-engine approval-rule
    warning occurred. Portal code did not change; its prior 519-test/build result was not rerun here.
- [ ] This closes the atomic-start implementation checkpoint, not integrated R-1–R-6d acceptance.
  Bounded kernel stop/evidence, authorization controls/Continue, attribution/provisioning, real nginx
  canaries, HTTPS browser/runtime proof, and final root `make verify` remain pending. Protected plans
  and unrelated `.qoder` work remain unchanged. Runtime changes remain uncommitted; no version bump,
  image rebuild/deployment, live OAuth registration, or AAP contact. **AAP compatibility unverified**;
  DI-070 stays separate and pending.

## Bounded Kernel Stop + Durable Authorization Evidence Checkpoint — 2026-10-29

- [x] `s70-wf-kernel`: an enabled turn now stops safely on a validated gateway
  `TARGET_AUTHORIZATION_REQUIRED` result. One mutable per-turn latch (`AuthorizationTurn`) is shared
  through a `ContextVar` across concurrent child tasks — never stored on a cached tool/agent — and
  serializes tool execution: the first validated challenge sets the latch before releasing the
  invocation lock, so remaining queued calls return a fixed safe `TARGET_AUTHORIZATION_STOPPED` result
  without dispatch and permission checks cannot re-park them. Closing the turn's scope fences inherited
  child contexts even after the parent resets its `ContextVar`.
- [x] Gateway result metadata is separated from model text. Only a safe error code/message reaches the
  model; the opaque challenge is validated against the closed `AuthorizationRequired` model (reserved
  code, matching gateway tool name, dict error, future expiry) and promoted into a dedicated v13
  sibling `authorization_required` evidence frame. Model-authored text can never mint a challenge; a
  malformed candidate stops safely without promotion or provider-error disclosure.
- [x] On the next model-call hook after the latch the runtime returns a deterministic public
  `ChatResponse` (safe guidance, no tool calls) instead of another provider call, cancels any
  structured-output requirement, suppresses context compression, closes the turn with exactly one
  outward `message_end`, and persists coherent tool results. Stopped SDK tool results carry an explicit
  `ERROR` state with sanitized safe content/metadata. This applies to streaming, blocking, and
  approval-resumed turns even with no evidence sink; blocking replies return a typed
  `authorization_required` projection so the caller is not stranded.
- [x] Failed acquisition never mints a secret-release permit: `RunGuard.release_permit` durably accepts
  the failed original for evidence but returns `None` before constructing any `SecretReleasePermit`
  when the original result status is not `success`; the invocation coordinator retains its result-status
  gate as defense in depth. Already-dispatched results and durable uncertainty are preserved — the latch
  cannot relabel them as unexecuted, and a completed standalone `secrets.generate_password` delivery
  (dedicated generation bearer, never the delegated target) is still surfaced at turn end.
- [x] `authorization_required` was added to the durable-evidence allowlist and is persisted for blocking
  and streamed enabled turns; the portal decoder reduces it to routing metadata
  (`authChallengeId`/`target`/`expiresAt`) and both the live handler and transcript replay attach it to
  the turn with `authChallengeId` deduplication. No browser proof, provider URL, code, state, or
  `confirm_id` reaches portal state; the attachment is inert (no navigation, control, or follow-up
  request). Disconnect cleanup drains the latched bounded SDK tail in the owning task so an observed
  challenge survives persistence and `ContextVar` resets stay in their creating context.
- Failure-first evidence: the new runtime-loop regressions exposed four real defects across two focused
  runs — a wrong/missing error code still promoted a valid-looking challenge; a stopped SDK tool result
  was recorded `success`; a failed original (`error`/`denied`) briefly constructed a release permit
  (first run **5 failed, 99 passed**, the fifth a fixture import error, not a production path); and a
  disconnect lost the observed challenge while nested SDK generators were finalized in another context
  (separate run **1 failed, 89 deselected**). Each was corrected (reserved-code+shape validation,
  explicit `ERROR` state, permit status gate before construction, owning-task tail drain), and a lock-in
  regression now asserts a completed standalone generation is preserved through a later stop.
- Final verification (contract-fixture runtime loops against the installed AgentScope with a
  deterministic model; **not** production acquisition or integrated OAuth):
  - `OTEL_ENABLED=false uv run --project products/agent-platform --frozen pytest
    products/agent-platform/tests -q`: **1,630 passed** (nonfatal loopback OTLP shutdown retries).
  - Focused `test_kernel_middleware.py` + `test_execution_run_guard.py` + `test_delegated_identity.py`:
    **164 passed**.
  - Corresponding full platform-gateway command: **473 passed**, one Starlette/httpx warning.
  - Portal `npm test`: **520 passed (37 files)**; `npm run build` (`tsc --noEmit && vite build`): clean,
    one pre-existing chunk-size warning.
  - execution-runtime unit suite (permit-adjacent, excluding the infra failure campaign): **94 passed**.
  - `make validate-secret-vocabulary`: parameter/marker/shape parity OK. `git diff --check` clean across
    SPEC-070 source (only inherited `.qoder/repowiki` whitespace, out of scope).
- [ ] This closes the bounded-kernel-stop implementation checkpoint (the R-2c/R-2d kernel mechanism),
  not integrated acceptance. Still pending: the production acquisition→challenge producer
  (`s70-kernel-producer`; the read call-id correlation transport it needs has now landed — see the
  Call-Id Correlation Transport increment below), the portal Authorize/status/Cancel
  control with 2s polling, the fresh-turn Continue path, attribution/provisioning, real nginx canaries,
  HTTPS multi-browser/provider/Postgres runtime proof, and final root `make verify`. No real challenge is
  produced end-to-end yet, so the stop is not reachable in a live deployment. Protected plans and
  unrelated `.qoder` work remain unchanged. Runtime changes remain uncommitted; no version bump, image
  rebuild/deployment, live OAuth registration, or AAP contact. **AAP compatibility unverified**; DI-070
  stays separate and pending.

## Call-Id Correlation Transport Increment — 2026-10-29

- [x] Reads now forward the in-flight tool-call id beside the session id, the correlation prerequisite
  the challenge producer needs to bind a durable authorization transaction to the exact call. On the
  agent-platform side `invoke_gateway_tool` gained an optional `call_id` and the read closure forwards
  `CURRENT_CALL_ID.get()` (set per dispatch by `ToolEvidenceMiddleware`); on the tool-gateway side
  `invoke_tool` parses a syntactically bounded top-level `call_id` (non-string/oversized dropped, never
  coerced) and `_dispatch_invocation` threads it to connectors as `identity["chat_call_id"]`. It is a
  trusted correlation handle only — never a model parameter, never a policy input, and identity/policy
  still ride the bearer.
- Failure-first evidence: the new transport tests failed before the wiring (`KeyError: 'call_id'` on the
  agent-platform closure; `None != 'tool_call_01AA'` at the gateway echo) and pass after; one existing
  exact-call-args assertion was updated for the new optional parameter.
- Verification: `OTEL_ENABLED=false uv run --project products/agent-platform --frozen pytest
  products/agent-platform/tests -q` → **1,633 passed**; the corresponding tool-gateway command →
  **1,011 passed** (nonfatal loopback OTLP shutdown retries). Focused `test_gateway_tools.py` (59) and
  `test_tool_invoke.py` + `test_delegated_invoke.py` (52) green.
- [ ] This is transport only: no challenge is created from it yet. The acquisition→challenge producer
  (convert a verified `authorization_required` failure plus this context into a durable transaction and a
  `TARGET_AUTHORIZATION_REQUIRED` result carrying safe `authorization_required` metadata) remains the next
  producer step. Runtime changes remain uncommitted; boundaries unchanged.

## Durable Challenge Producer Core Increment — 2026-10-29

- [x] `AuthorizationService.produce_challenge(owner_namespace, owner_sub, session_id, call_id,
  return_url="/")` now mints the durable authorization transaction the kernel's bounded stop consumes. It
  reads authoritative configuration for the current target/generation, confirms the owner is administered
  for the target, mints a fresh single-use uuid4 challenge, and inserts one `pending` transaction bound to
  the owner/target/credential-set/generation and the exact invocation (`session_id`, `call_id`). It returns
  ONLY the public `AuthorizationRequired{challenge_id, target, expires_at}` triple the kernel promotes —
  never a token, state, PKCE verifier, provider URL, set id, or owner identity.
- [x] Fail-closed to `None` (no challenge, no oracle) when configuration is unavailable, the owner has no
  administered mapping (a challenge that could never complete), or the store refuses the insert; a
  challenge id is never returned unless it was durably inserted. The caller's pre-existing denial stands.
- Failure-first evidence: the six `AuthorizationProducerTests` failed with `AttributeError:
  'AuthorizationService' object has no attribute 'produce_challenge'` before the method landed and pass
  after (durable pending challenge + exact-context binding, safe-metadata-only, current generation/target
  binding, and the three fail-closed legs).
- Verification: `OTEL_ENABLED=false uv run --project products/tool-gateway --frozen pytest
  products/tool-gateway/tests -q` → **1,017 passed** (+6; nonfatal loopback OTLP shutdown retries);
  focused `test_delegated_authorization.py` → **62 passed**.
- [ ] The producer is inert until wired: no connector/dispatch path calls it yet, and the verified
  **read-path** owner threading (R-2a `delegated_requester_namespace/sub` on reads) it depends on is not
  in place, so a read cannot yet reach acquisition to produce a challenge. Connector→producer wiring plus
  read-path owner threading is the next increment. Runtime changes remain uncommitted; boundaries unchanged.

## Read-Path Verified Requester Threading Increment (R-2a) — 2026-10-29

- [x] Reads now thread a **directly verified** requester (plan line 66: "Reads use their directly verified
  requester context"), the owner binding the acquisition seam and the challenge producer need.
  `gateway_service.resolve_delegated_read_requester(settings, request)` re-verifies the presentation bearer
  against the delegated-human trust bar (`decode_delegated_human_claims` — the identical bar the execution
  handoff and authorization owner edges hold: RS256 under the delegated-identity JWKS, pinned
  issuer/audience, `oidc` provenance, allowlisted RFC-8693 `act` actor, bounded immutable `sub`) and returns
  the pinned `(delegated_identity_issuer, sub)`, which `invoke_tool` passes to `_dispatch_invocation` as
  `delegated_requester` → `identity["delegated_requester_namespace"/"sub"]`. This is independent of the
  portal `verify_token` that drives policy: a token valid for policy is not automatically a delegated human.
- [x] Fail-closed to `None` (no requester → a delegated set fails closed at the connector, never acquiring
  under an unverified owner) when acquisition is disabled, the delegated-human trust set is unprovisioned,
  the bearer is absent/malformed, or verification fails. A caller can never assert a requester; the bearer
  is never persisted, echoed, or logged.
- Failure-first evidence: `test_read_threads_directly_verified_requester` failed with `None !=
  'trusted-issuer'` before the helper landed; the three negative legs (development provenance, acquisition
  disabled, trust set unprovisioned) assert no requester is threaded.
- Verification: `OTEL_ENABLED=false uv run --project products/tool-gateway --frozen pytest
  products/tool-gateway/tests -q` → **1,021 passed** (+4; nonfatal loopback OTLP shutdown retries); focused
  `test_delegated_invoke.py` → **21 passed**.
- [ ] The connector→producer wiring is the next step: on a verified `authorization_required` acquisition
  failure with the owner + `session_id`/`call_id` now in scope, call `produce_challenge` and return a
  `TARGET_AUTHORIZATION_REQUIRED` result carrying the safe metadata so the kernel's bounded stop becomes
  reachable end to end. Runtime changes remain uncommitted; boundaries unchanged.

## Dispatch→Producer Wiring Increment (authorization_required → TARGET_AUTHORIZATION_REQUIRED) — 2026-10-29

- [x] The read dispatch path now upgrades a verified delegated re-authorization denial into a durable
  challenge, closing the producer gap between the acquisition seam and the kernel's bounded stop.
  `gateway_service._produce_authorization_challenge(result, identity_dict, producer)` runs inside
  `_dispatch_invocation` **after redaction and before the audit log**: when a connector returns the
  transitional `DELEGATED_REAUTHORIZATION_REQUIRED` denial and every gate holds, it calls
  `AuthorizationService.produce_challenge` and returns a fresh `ToolResult(status="error",
  error.code=TARGET_AUTHORIZATION_REQUIRED, authorization_required=<safe triple>)` preserving the
  connector's own evidence. That maps to HTTP 400, which the agent-platform transport passes through
  untouched (`invoke_gateway_tool` returns `response.json()` with no `raise_for_status`) so the kernel
  middleware validates the envelope and promotes it to a bounded stop.
- [x] The producer fires only when the authorization runtime is wired (`app.state.authorization_service`,
  published by `create_app` under `delegated_authorization_enabled` and threaded route → `invoke_tool` →
  `_dispatch_invocation` as `challenge_producer`), the result is exactly that denial, the invocation carries
  the **directly verified** owner (`delegated_requester_namespace`/`_sub` from the R-2a read threading, never
  a caller override), and it carries the `session_id`/`call_id` correlation to bind the challenge to the exact
  call. Any gap — no producer, no verified owner, no correlation, or a fail-closed `None` from the producer —
  leaves the original denial byte-identical (403, no `authorization_required`). A delegated *write* handoff
  (`invoke_delegated`) carries no `call_id`, so it naturally never produces: Continue is always a fresh read turn.
- Failure-first evidence: `test_authorization_required_produces_challenge_result` failed before the wiring
  (expected 400/`TARGET_AUTHORIZATION_REQUIRED`, got 403/`denied`) and `test_producer_returning_none_leaves_
  denial_untouched` failed with `0 != 1` (producer never called); the two negative legs (no producer, missing
  `call_id`) already passed. All four `DelegatedReadChallengeProducerTests` pass after, asserting the promoted
  envelope, the exact `produce_challenge(owner_namespace, owner_sub, session_id, call_id)` args, and each
  fail-closed leg.
- Verification: `OTEL_ENABLED=false uv run --project products/tool-gateway --frozen pytest
  products/tool-gateway -q` → **1,025 passed** (+4; nonfatal loopback OTLP shutdown retries); focused
  `test_delegated_invoke.py` → **25 passed**. `git diff --check -- products/tool-gateway docs/specs` clean.
- [ ] The gateway now emits the ratified authorization-required contract, but the workflow is not yet usable
  end to end: the portal Authorize/status/Cancel control and fresh-turn Continue (R-2c/d), the attribution
  disclosure (`delegation_mode` + `target_authorization` audit event), provisioning, and the deterministic
  integration harness that exercises a real acquisition→challenge→approval→return→Continue round trip remain
  pending. Runtime changes remain uncommitted; boundaries unchanged.

## Portal Authorize/Status/Cancel Control + Fresh-Turn Continue Increment (R-2c/d portal) — 2026-10-29

- [x] The operator portal now renders an **inline target-authorization control** distinct from the
  confirmation card, closing the requester-facing half of the workflow. `AuthorizationCardView`
  (`products/operator-portal/web-ui/app/src/chat/ChatView.tsx`) renders once per challenge in
  `turn.authorizations` (collected and deduped by `authChallengeId` in `useChatStream`), keyed by the
  challenge id so a replayed transcript never double-renders a card. It shows the target, a status badge
  (`pending`/`authorized`/`canceled`/`expired`/`failed`), and — only while pending — an **Authorize** and a
  **Cancel** action. Authorize hands off to the same-origin, cookie-bound start URL via `startAuthorization`
  + `window.location.assign` (the return path is `useAuthorizationReturn`); there is **no auto-redirect** and
  no credential ever reaches the browser. Cancel retires the challenge via `cancelAuthorization`. Both are
  explicit user clicks, never a poll side effect.
- [x] `useAuthorizationStatusPoll` (`.../src/chat/useAuthorizationStatusPoll.ts`) drives the status half: it
  reads the owner-scoped status immediately on mount, re-reads every **two seconds while the tab is
  visible**, **stops at a terminal state or a lapsed expiry** (self-clearing the interval), and **kicks on
  focus/visibility** so a challenge that settled on the provider page surfaces at once. It only ever names
  the challenge id it was given (the status surface is owner-scoped server-side), keeps the last-good status
  on a transient transport error (an error never means "resolved"), drops stale reads via an `AbortController`
  + captured-id guard, and owns no navigation or mutation. The card additionally treats a lapsed `expires_at`
  as `expired` even while the row still reads `pending`, so it never offers an action on a challenge that
  cannot complete.
- [x] **Continue is a fresh, explicit user turn** in the same owned session — never a callback dispatch or a
  confirmation resume (plan line 149). The card reveals Continue only once the polled status is `authorized`
  and only when a continuation is wired; `ChatView.continueAfterAuthorization` re-checks the live stream
  (`chat.streaming`) and the recovery state (`hasUnsettledExecution(chat.turns)`) before re-submitting the
  turn's request through the normal `chat.send` path, so current policy, HITL, signed request, and a fresh
  durable claim all still run server-side. No retained prior approval, consumed-claim reuse, or
  uncertain-write replay is carried into the new turn, and the button is disabled while the agent is busy.
- Failure-first evidence: `useAuthorizationStatusPoll.test.ts` failed with "Cannot find module" before the
  hook landed, then two failures (an overlapping-tick expectation and a null-challenge coercion bug) were
  fixed to **7 passed**; `AuthorizationCard.test.tsx` exercises the real component against a mocked
  owner-scoped status surface — pending shows Authorize/Cancel and no Continue, Authorize calls
  `startAuthorization` + `assign(start_url)`, Cancel calls `cancelAuthorization` without navigating,
  authorized reveals Continue that fires `onContinue` once, busy keeps Continue disabled, and
  canceled/expired/failed (plus a lapsed pending expiry) drop every action — **10 passed**.
- Verification: `npm --prefix products/operator-portal/web-ui/app test` → **537 passed** (39 files);
  `npm --prefix products/operator-portal/web-ui/app run build` (`tsc --noEmit && vite build`) → clean.
- [ ] This closes the portal control implementation, not integrated R-2c/R-2d acceptance: the deterministic
  integration harness (a real acquisition→challenge→approval→return→Continue round trip) and the disposable
  local-HTTPS browser proof remain pending, and the attribution disclosure (`delegation_mode` +
  `target_authorization` audit event) and provisioning are untouched. Runtime changes remain uncommitted;
  boundaries unchanged.

## Attribution Vocabulary Increment (`target_authorization` event type) — 2026-10-29

- [x] The narrowly scoped `target_authorization` audit event type (plan line 155) joined the canonical closed
  vocabulary and **every consumer mirror** in lockstep: the shared `audit-event.schema.json` `event_type`
  enum (+ a `details` description pinning its bounded `operation` / `authorization_outcome` / optional
  `reason` and `challenge_id`/`target`/session correlation), the audit-service `EventType` `Literal`, and the
  portal `views/audit/constants.ts` `EVENT_TYPES` filter list. Both drift guards stay authoritative: the
  audit-service `test_model_enum_values_match_contract` pins model↔schema set equality and the portal
  `constants.test.ts` pins `EVENT_TYPES`↔schema set **and order** equality, so the value was appended in the
  same position in all three. No product vendors a schema copy (all six products' tests load the one shared
  file), so there is no physical re-sync — only the six test suites that read it.
- Failure-first evidence: `test_target_authorization_event_validates` failed with a pydantic `literal_error`
  (`event_type` … "Input should be …'secret_delivered'") before the vocabulary landed, and passes after —
  it builds a representative `enroll`/`authorized` event with `delegation_mode="user_delegated"` and
  validates it against the shared schema.
- Verification: `uv run --project products/audit-service --frozen pytest products/audit-service/tests -q` →
  **145 passed** (nonfatal loopback OTLP shutdown retry); portal `constants.test.ts` → **3 passed**.
- [ ] The vocabulary is ratified and now emitted: the actual lifecycle emission with transition-identity dedup
  (line 155) has landed — see the Target-Authorization Lifecycle Emission Increment below — as has the
  top-level `delegation_mode` derivation from the verified acquisition context (plan lines 153/156, the
  Delegation-Mode Attribution Increment below). Only the end-to-end ingestion/persistence/query proof remains.
  Runtime changes remain uncommitted; boundaries unchanged.

## Delegation-Mode Attribution Increment (top-level `delegation_mode`) — 2026-10-29

- [x] The top-level `delegation_mode` audit field (plan lines 153/156) is now **derived from the verified
  acquisition outcome** at the single reusable seam `resolve_outbound_auth` — never read from a connector
  configuration label. A per-task `ContextVar` (`DELEGATION_MODE`) is set on every resolution: a verified
  user-delegated grant (the only path that populates `ResolvedAuth.acquisition`) → `user_delegated`; any other
  successful machine credential (basic / bearer / `oauth2_client_credentials`) → `acting_service`; a failed
  acquisition → `none` — **authorization failure is never delegated success**. A tool that never touches the
  seam leaves it unset, so `build_audit_event` omits the field and its record stays byte-identical to before
  (unrelated legacy events unchanged; absence is never an assertion of `none`).
- [x] The gateway captures the mode inside the request task **before redaction** (`_dispatch_invocation` sets a
  clean baseline around `registry.invoke`, then reads and resets it), so it survives a `REDACTION_OVERFLOW`
  result replacement — the value rides the `ContextVar`, never `result`. It is passed as the already-ratified
  **top-level** field to the `tool_invoked` audit event on both the public `invoke_tool` path and the SPEC-070
  private `invoke_delegated` (signed) route, which share the dispatch. The static `target_identity_mode`
  config label stays in `details` and is explicitly not the top-level mode.
- [x] `build_audit_event` gained an optional `delegation_mode` param (omitted when `None`). Because the
  fire-and-forget emitter is an **intentionally duplicated module**, the identical change was applied to all
  six copies (tool-gateway, platform-gateway, identity-broker, skills-hub, agent-platform, execution-runtime);
  `AuditEmitterParityTest` (strips docstrings, normalizes identifiers) confirms they remain identical.
  incident-service is deliberately excluded (its emitter is a triage connector, not a copy).
- Failure-first evidence: `test_delegation_mode_attribution.py` failed at import (`cannot import name
  'DELEGATION_MODE'`) before the seam landed. It now proves derivation per scheme (7 unit cases reading the
  `ContextVar` in the same task) and top-level emission through the real gateway choke point (5 cases):
  `user_delegated` for a verified delegated `http.get`, `acting_service` for a basic credential, `none` for a
  failed delegated acquisition (denied, outcome `error`), omission for a no-credential tool, and preservation
  of `acting_service` through a `REDACTION_OVERFLOW` (400).
- Verification: `OTEL_ENABLED=false uv run --project products/tool-gateway --frozen pytest products/tool-gateway -q`
  → **1037 passed** (12 new; nonfatal loopback OTLP shutdown retry). `git diff --check -- products/ shared/` clean.
- [ ] Runtime derivation and emission are landed and unit/integration-proven at the gateway; the remaining
  R-4a/c leg is the **end-to-end** proof (plan line 156): runtime event ingestion, Postgres persistence, and
  query filtering on `delegation_mode`, plus overflow/signed-path attribution asserted against the durable
  audit store. The `target_authorization` lifecycle emission with transition-identity dedup (line 155) has
  since landed — see the Target-Authorization Lifecycle Emission Increment below. Runtime changes remain
  uncommitted; boundaries unchanged.

## Target-Authorization Lifecycle Emission Increment (`target_authorization`) — 2026-10-29

- [x] The narrowly scoped `target_authorization` audit event (plan line 155) is now **emitted at actual
  lifecycle transitions** the `AuthorizationService` finalizes, never fabricated. An optional fire-and-forget
  emitter is injected into the service (`audit=`, default `None` → inert, so every prior construction stays
  byte-identical); `app._target_authorization_emitter(settings)` supplies it in the real runtime, mapping each
  bounded outcome onto the canonical envelope: `event_type="target_authorization"`, top-level `outcome`
  `success` **only** for an `authorized` enrollment and `error` for every cancel/fail (**an authorization
  failure is never overstated as a delegated success**), the bounded `operation` / `authorization_outcome` /
  optional `reason` class and `challenge_id`/`target` correlation on `details`, and the requester subject,
  session correlation, and top-level `delegation_mode` kept separate.
- [x] **Success is recorded only from acknowledged publication.** The `authorized` event is emitted solely after
  `complete_authorization` returns non-`None` metadata (the durable-installation authority) with
  `delegation_mode="user_delegated"` — never from a callback response alone and never as a stand-in
  `tool_invoked`. A denial (`access_denied`→`canceled`, else `failed`), a configuration-unavailable, a
  code-exchange failure, and a `metadata is None` publication failure each record their real outcome with a
  bounded reason. The publication-**uncertain** `except Exception` path records **nothing** — no stored
  transition was acknowledged, so any outcome there would be fabricated.
- [x] **Dedup rides the store's single-use finalization (the stored transition identity).** Each callback
  emission is gated on `store.finish(...)` returning `True`, and the owner `cancel` on `store.cancel(...)` now
  returning the transitioned transaction (memory + Postgres both changed from `None`); a second callback, a
  repeat cancel, or a spent/expired/foreign/unknown challenge finalizes nothing and emits nothing, so an
  idempotent 204 never double-records. Only bounded fields ride the event — no bearer, code, state, PKCE
  verifier, browser secret, provider URL, or owner namespace.
- Failure-first evidence: `TargetAuthorizationAuditTests` (6 cases) failed `0 != 1` before the emission call
  sites landed, and now prove: exactly one `enroll`/`authorized`/`user_delegated` event with challenge/target/
  session/owner correlation on an acknowledged publication; `enroll`/`canceled` with the bounded
  `access_denied` reason on a denial; `enroll`/`failed` with `code_exchange_failed` (and never the provider's
  `error_description`) on an exchange failure; a single `cancel`/`canceled` event that dedupes across a repeat
  and foreign/unknown cancels; an inert no-op when no emitter is wired; and the app-level envelope mapping
  (`authorized`→`success` with the top-level mode, `canceled`→`error` with the mode omitted).
- Verification: `OTEL_ENABLED=false uv run --project products/tool-gateway --frozen pytest products/tool-gateway -q`
  → **1043 passed** (6 new; nonfatal loopback OTLP shutdown retry). `git diff --check -- products/ shared/` clean.
- [ ] Scope note: this increment covers the two service-finalized owner/workload transitions with clean
  per-transaction signals (`enroll` via callback and owner `cancel`). Bulk `browser_reset` (returns only a
  count) and lazy in-store `expire` do not surface per-transaction identities to the service, so their
  `target_authorization` emission is deferred to the durable end-to-end leg rather than fabricated here. The
  remaining R-4a/c work — the **end-to-end** proof (plan line 156) — has since landed; see the End-to-End
  Attribution Proof Increment below. Runtime changes remain uncommitted; boundaries unchanged.

## End-to-End Attribution Proof Increment (ingestion → Postgres → query) — 2026-10-29

- [x] **Runtime event ingestion (contract).** The REAL envelopes the gateway emits are now validated against
  the shared `audit-event.schema.json` — the single boundary the audit-service ingestion model is bound to —
  so what the gateway emits is provably what audit ingests: the signed-path `tool_invoked`
  (`delegation_mode="user_delegated"`), the machine-credential `tool_invoked` (`acting_service`), the failed
  acquisition (`none`, outcome `error`), the no-credential `tool_invoked` (mode omitted, legacy byte-identical),
  the `REDACTION_OVERFLOW` `tool_invoked` (`acting_service` preserved through the error outcome), and both
  `target_authorization` lifecycle envelopes (`authorized`/`user_delegated` success and `canceled`/error with
  the mode omitted).
- [x] **Ingestion + query filtering (audit-service, HTTP).** `test_reporting.py` round-trips the SPEC-070 shapes
  through the real FastAPI ingest → store → query/summary/export: a `target_authorization` event is returned by
  an `event_type` filter with its bounded details and top-level mode; an overflow-attribution `tool_invoked`
  (`outcome="error"`, `delegation_mode="acting_service"`) is returned by a `delegation_mode` filter —
  **attribution survives an error outcome** — and a no-credential event omits the mode and is never returned by
  a mode filter. Summary/export honor the same filters.
- [x] **Postgres persistence + query (durable).** The disposable-Postgres `audit_contract.py` proof (run via
  `make audit-contract-test`, part of `make verify`) now also round-trips a `target_authorization` success and
  an overflow-attribution error event through the real indexed `delegation_mode` column, querying by
  `event_type` and by `(delegation_mode, outcome)`, with `event_id` primary-key dedup on re-delivery — proving
  the durable store persists and filters the exact SPEC-070 shapes, not just `tool_invoked` successes.
- Verification: tool-gateway `OTEL_ENABLED=false uv run --project products/tool-gateway --frozen pytest
  products/tool-gateway -q` → **1043 passed**; audit-service `uv run --project products/audit-service --frozen
  pytest products/audit-service/tests -q` → **147 passed**; `audit_contract.py` byte-compiles clean
  (`python -m py_compile`). `git diff --check -- products/ shared/` clean.
- [ ] Environment note: the disposable-Docker Postgres leg could not be executed in this sandbox (no Docker
  daemon); it is deterministic, byte-compiled, reuses the already-passing round-trip patterns, and runs in CI
  via `make audit-contract-test`. Runtime changes remain uncommitted; boundaries unchanged.

## Backend Operator CLI Increment (R-6a/R-6b custody administration) — 2026-10-29

- [x] **A backend operator CLI administers the gateway-owned custody runtime** (plan line 167):
  `python -m tool_gateway.services.custody_cli` exposes exactly `migrate`, `readiness`/`status`,
  `revoke` (local), `remote-revoke` (one attempt), `rotate-key`, `reencrypt` (bounded), `recover`
  (externally fenced), and a `validate-config` leg the provisioning scripts call before any mutation.
  It delegates to the explicit custody primitives (`migrate_custody`, `recover_custody`,
  `PostgresCustodyStore.ready/revoke/rotate_key/reencrypt`) and never issues DDL from the runtime role,
  enables a feature flag, or activates a real target.
- [x] **Secret file paths, never literals.** Every credential-bearing option is a path
  (`--dsn-file`, `--keyring-file`, `--refresh-token-file`); there is NO `--dsn`/`--refresh-token`
  literal, and `allow_abbrev=False` is set on the main parser *and* every subparser (argparse does not
  propagate it) so an abbreviated literal is rejected with `SystemExit` rather than silently accepted as
  a prefix of the `*-file` option — no DSN or token can leak through `ps` argv, shell history, or logs.
  There is **no enrollment / manual-user-token command**: a durable grant is only ever established
  through the human-initiated `/api/v2/targets/authorizations` workflow, never minted here.
- [x] **Local revoke commits first; remote revocation is a separate, single, non-retrying attempt**
  (plan line 168). `revoke` calls `store.revoke(owner)` — which durably invalidates the next cache check
  on every replica — makes **no** remote call, and reports `local_revoked_remote_unconfirmed`. The new
  `UserDelegatedClient.revoke_token` (RFC 7009 over the existing hardened channel: no redirects, no env
  proxy, 10s deadline, 64 KiB cap, **no retry**, single-source `_apply_client_auth`) is reachable only via
  the separate `remote-revoke` command; a remote failure never rolls back the committed local revocation
  and is never retried. A config with no `revocation_url`, or a missing/empty refresh-credential file,
  yields an explicit `remote_unconfirmed` (never a fabricated provider-side guarantee). `reencrypt` bounds
  the batch to `1..1000` *before* touching the store (out-of-bound → `invalid_batch` refusal).
- Failure-first evidence: `test_custody_cli.py` (23 cases across 7 classes) failed `ModuleNotFoundError`
  before `custody_cli.py` existed. Three cases then proved the discipline boundaries specifically —
  `--dsn`/`--refresh-token` literals raise `SystemExit` (prefix acceptance closed by `allow_abbrev=False`),
  and `migrate` reads the DSN from a file and passes a lazy file-backed `Keyring` (snapshot resolved inside
  the mount). The suite also proves: no `enroll`/`authorize`/`mint`/`token` command exists; `readiness`
  reports `ready`/`not_ready` without failing open; local `revoke` records the `(namespace, subject)` owner
  and never calls the remote path; `remote-revoke` degrades to `remote_unconfirmed` on a missing endpoint,
  a missing token, a transport error, and a non-200 (via `httpx.MockTransport`), and reports `revoked` only
  on a real 200; `rotate-key`/`reencrypt`/`recover` delegate with the fenced epoch and bound the batch.
- Verification: `OTEL_ENABLED=false uv run --project products/tool-gateway --frozen pytest
  products/tool-gateway/tests/test_custody_cli.py -q` → **23 passed**; full tool-gateway suite →
  **1066 passed** (23 new; nonfatal loopback OTLP shutdown retry). `git diff --check` clean on all touched files.
- [ ] Scope note: this is the operator *surface* for R-6a/R-6b; the real-Postgres lifecycle it administers
  (concurrency, ciphertext-substitution denial, rotation, crash/restart, lost-response, epoch fence) is
  proven separately by `make delegated-custody-test` (Docker-gated, not runnable in this sandbox). The
  provisioning script extension (p4a), the disabled-by-default delegated-dev GitOps profile (p4b), the
  separate custody runtime/operator DB roles (p4c), and the operator guides (p4e) remain. Runtime changes
  remain uncommitted; boundaries unchanged.

## Provisioning Script Extension Increment (R-6 validate-before-mutation) — 2026-10-29

- [x] **The existing file-based `sync-browser-credentials.sh` workflow is extended for delegated
  configuration + administered mapping inputs, preserving existing machine/browser provisioning**
  (plan line 164). When `DELEGATED_CONFIG_FILE` is unset the script behaves exactly as before
  (`tool-gateway-browser-credentials` + `acme-admin-credentials`); the historical `[namespace]` positional
  and `SKIP_BROWSER_CREDENTIALS=true` are preserved. New optional inputs: `DELEGATED_CONFIG_FILE`,
  `DELEGATED_MAPPING_FILE` (defaults to the config's own absolute `identity_mapping_path`, so validation and
  provisioning read one source), `DELEGATED_SET_ID`, `DELEGATED_TRUSTED_CALLBACK`, `DELEGATED_SECRET_NAME`.
- [x] **Validation is delegated to the versioned guard, never re-implemented in shell** (mirrors
  `rotate-execution-epoch.sh`): the script invokes `custody_cli validate-config --config-file … --set-id …
  --callback …` via `uv run --offline --frozen --project products/tool-gateway`, the SAME authority the
  runtime uses (`load_snapshot`). A read-only browser-file precondition check now also runs BEFORE the first
  `kubectl`, so a bad credential file no longer leaves a half-applied browser secret behind.
- [x] **Validate-before-mutation + a validation-only mode.** Both read-only checks run before any `kubectl`
  call; a guard refusal prints `REFUSED: … NO secret was created and NO rollout occurred` and exits non-zero
  with delegation left disabled. `--validate-only` (or `VALIDATE_ONLY=true`) validates every supplied input
  and exits 0 before any cluster mutation or rollout. The live delegated-secret creation
  (`tool-gateway-delegated-config`, `--from-file` for both the config and mapping, never `--from-literal`)
  is implemented but — per plan line 164 — was **not executed** in this task.
- Failure-first / real-execution evidence: a self-contained harness ran the REAL script + REAL guard (no
  mocks; `kubectl` was a recording stub, and the live secret/rollout path was never reached) across 5 cases,
  all PASS — (0) stub control proves the marker records a `kubectl` call; (1) valid config + `--validate-only`
  → exit 0, `configuration valid`, no mutation; (2) browser-only + `--validate-only` → exit 0 (existing
  provisioning preserved); (3) callback mismatch → `refused: callback_mismatch`, non-zero; (4)
  **validate-before-mutation** — invalid config with NO `--validate-only` → non-zero AND the recording
  `kubectl` was never called (marker absent). `sh -n` syntax-clean; `git diff --check` clean; harness deleted.
- [ ] Scope note: the overlay mounts that consume `tool-gateway-delegated-config`
  (`GATEWAY_DELEGATED_CUSTODY_CONFIG_PATH` + the mapping at `identity_mapping_path`), the disabled-by-default
  feature flags, the projected workload JWT volumes, and the separate custody DB roles are p4b/p4c below.
  The absolute `identity_mapping_path` must resolve where validation runs and equal the overlay's mount path
  so the validated bytes are the mounted bytes (the fingerprint covers it) — documented for operators in p4e.
  Runtime changes remain uncommitted; boundaries unchanged.

## Delegated GitOps Overlay + Custody DB Roles Increment (R-6c least privilege, disabled-by-default) — 2026-10-29

- [x] **Separate custody database roles with least privilege** (plan line 166). `base/infra/custody-roles.sql`
  creates two SEPARATE login roles idempotently and with NO committed password: `custody_operator`
  (migration / rotation / recovery administration; holds `CREATE` on the `custody` database and owns the
  `gateway_custody` schema) and `custody_runtime` (the gateway send path; `CONNECT` only).
  `base/infra/custody-grants.sql` then grants `custody_runtime` exactly the DML the send path needs —
  `USAGE` on the schema, `SELECT` on `schema_version`/`key_policy`, `UPDATE (singleton)` on `key_policy`
  (row-lock only, no value authority), and `SELECT/INSERT/UPDATE/DELETE` on `configurations`, `credentials`,
  `transactions`, `transaction_secrets` — and records the five operations PROVEN denied to it. These
  statements are the committed byte-mirror of the boundary the disposable-Postgres integration proof already
  enforces (`products/tool-gateway/tests/integration/delegated_custody.py`, `make delegated-custody-test`).
- [x] **`create-custody-db.sql` creates only the EMPTY database and is wired into `postgres-initdb`** so a
  fresh cluster gets it with no secret and no privilege; the schema/tables are created LATER by
  `custody_cli migrate` under `custody_operator` (the runtime issues no DDL). The role/grant SQL is
  deliberately NOT in the ConfigMap — it is applied post-migrate by the sync script and its passwords are
  generated at deploy time. `sync-custody-db.sh` orchestrates the whole flow (idempotent DB + roles,
  generated-or-reused passwords handed to `psql` via `\getenv` env never argv, migrate as `custody_operator`
  through the versioned guard with `--dsn-file`, then grants, then the runtime/admin DSN secrets and the
  keyring secret, all `--from-file` from 0600 temp files with a cleanup trap).
- [x] **Disabled-by-default `runtime-profiles/delegated-dev` overlay** (plan line 165). It is a STANDALONE,
  opt-in overlay layered on the MINIMAL `dev-k8s/base` + `runtime-profiles/default` (every tool connector
  disabled there) and is NOT referenced by `dev-k8s`, so the default deploy is unchanged. `delegated.env`
  holds the three `GATEWAY_DELEGATED_*_ENABLED` gates explicitly `false` plus commented examples for the
  custody mount paths, the exact callback (path fixed to `/api/v1/targets/authorizations/callback`), the
  delegated-human trust set, and the two workload verification trust sets. No credential is committed: the
  DSN reaches the container through a `secretKeyRef` on `tool-gateway-custody-db` (added via the `env` merge
  key, never `envFrom`, which has no merge key and would drop `platform-runtime-config`), and the administered
  config/mapping + keyring are mounted read-only from `optional: true` secrets so the pod starts before
  provisioning.
- [x] **Projected workload JWT mounts with explicit lifetimes and distinct audiences.** Patches project a
  `serviceAccountToken` into `execution-runtime` (audience `luban-target-execution-handoff`) and
  `platform-gateway` (audience `luban-target-authorization-handoff`), each `expirationSeconds: 600` — the
  tokens the gateway VERIFIES (never mints) on the private invoke-delegated and the bearerless
  targets/authorizations handoffs; the distinct audiences mean neither handoff can replay the other's token.
- [x] **Least-privilege egress** (`delegated-network-policy.yaml`, the repo's first Egress policy, opt-in
  only): allows exactly DNS (kube-dns 53), the custody database (postgres 5432), the internal gateway
  (platform-gateway 8000), and JWKS (identity-service 8000); the external OAuth target and any external JWKS
  are commented `ipBlock` placeholders, so no real target is reachable out of the box even if a gate were
  flipped — defense in depth for "render every overlay without enabling a real target."
- Real-execution evidence (no mocks; live secret creation/rollout NOT executed per plan lines 164-166):
  `make overlays` renders all 7 overlays including the new `delegated-dev` (exit 0). Rendering
  `runtime-profiles/delegated-dev` proves the merged ConfigMap holds all three gates `"false"`, the
  tool-gateway carries the `GATEWAY_DELEGATED_CUSTODY_DB_URL` secretKeyRef + both `optional` mounts, both
  projected JWTs render with their distinct audiences + `expirationSeconds: 600`, and the egress
  NetworkPolicy is present. Rendering the DEFAULT `dev-k8s` proves ZERO occurrences of `GATEWAY_DELEGATED`,
  `tool-gateway-delegated-egress`, either handoff audience, `tool-gateway-custody-db`, or `delegated-keyring`
  — the default deploy is unchanged. `create-custody-db.sql` renders as a `postgres-initdb` data key.
  `sh -n sync-custody-db.sh` clean; `git diff --check` clean.
- [ ] Scope note: `make overlays` is a render-only check; the live database/role/secret provisioning and any
  gate flip are operator actions gated behind the sync scripts and are NOT executed here. p4e documents the
  operator guides (client-registration prereqs, first-use/re-auth + same-browser-tab semantics,
  requester/approver separation, expiration/invalidation bounds, least privilege, key rotation + staged
  retention, backup/restore/external fencing, offboarding, rollback/admission fencing, group-sync limits, and
  the mounted-file propagation caveat). Runtime changes remain uncommitted; boundaries unchanged.

## Operator Documentation Increment (R-6d living guides) — 2026-10-29

- [x] **`docs/guides/tool-configuration.md`** — new "Delegated provisioning + operator CLI (SPEC-070;
  disabled by default)" subsection: the `custody_cli` surface (secret **file paths** only;
  abbreviation disabled so `--dsn`/`--refresh-token` literals are **rejected**; **no** enrollment or
  manual-user-token command), the local-revoke-commits-first → one explicit remote-revoke attempt →
  never-auto-retried semantics, `sync-custody-db.sh` + `sync-browser-credentials.sh --validate-only`,
  the two least-privilege DB roles, the disabled-by-default `delegated-dev` overlay, plus
  client-registration prerequisites, offboarding, and group-synchronization limits. Corrected the
  lifecycle note that said production roles/mounts/network-policy "remain R-6 work" (now delivered,
  disabled by default; integrated acceptance still pending).
- [x] **`docs/guides/configuration-reference.md`** — strengthened the invalidation guarantee: once an
  authoritative invalidation or local revoke **commits**, every later credential check rejects
  immediately (no positive generation cache); mounted-file propagation **precedes** gateway observation
  with deployment-dependent delay and **no numeric Kubernetes guarantee**. Cross-linked the new
  provisioning subsection.
- [x] **`docs/guides/troubleshooting.md`** — corrected `local_revoked_remote_unconfirmed` (local
  commits first; remote is a separate explicit one-attempt operator action; never auto-retried) and
  added a "Delegated provisioning refuses, or a mounted-file change does not take effect" symptom
  table (validate-before-mutation `REFUSED`, `--dsn`/`--refresh-token` rejection, port-forward /
  `CUSTODY_PG_HOST` migrate failure, propagation delay vs. immediate reject, fail-closed after a gate
  flip).
- Plan line 169 coverage (all eleven items now stated across the three guides): client-registration
  prerequisites; first-use/reauthorization + same-browser-tab semantics; requester/approver
  separation; expiration/invalidation bounds; cancellation/logout; least privilege; key rotation +
  staged-key retention; backup/restore/external fencing; offboarding; rollback/admission fencing;
  group-synchronization limits. Plan line 170 (propagation precedes observation, deployment-dependent
  delay, no numeric guarantee; authoritative invalidation/local revoke commits → later checks reject
  immediately) is stated in both configuration-reference and troubleshooting.
- Verification: `git diff --check` clean on all three guides; every documented CLI flag cross-checked
  against `custody_cli._build_parser` (`--owner-sub`, `--dsn-file`, `--keyring-file`,
  `--refresh-token-file`, `--expected-key-id`, `--limit`, `--expected-epoch`,
  `--config-file`/`--set-id`/`--callback`); markdown anchors follow the repo's existing convention.
- [ ] Scope note: the R-6c/R-6d boxes are flipped in p7 (acceptance) after `make verify` and the p5
  deterministic-fixture exercise of setup/revocation/recovery/rollback; DI-070/R-6e remains pending
  (AAP unreachable). Runtime changes remain uncommitted; boundaries unchanged.

## Deterministic Integration Harness Increment (p5 — real routes/processes over generated TLS) — 2026-10-29

- [x] **`delegated_fixtures.py`** — the provider-independent development harness the plan requires
  (§"Deterministic integration fixtures", line 176): a generated CA + server certificates installed
  into the `certifi` trust store the shipped `UserDelegatedClient` verifies against (real hostname +
  chain checks, `trust_env=False`, no insecure switch), a fixture OAuth authorization/token/identity/
  revocation service enforcing PKCE **S256** + confidential-client auth, a fixture target resource
  server, a real JWKS endpoint, an MCP contact recorder, two users with distinct immutable accounts
  (alice→42 operator, bob→43 approver), and disposable Docker Postgres. A direct self-test runs a real
  authorization-code grant over TLS, refreshed, identity-verified, used against the resource server,
  then revoked (PKCE/client-auth enforcement + local invalidation asserted).
- [x] **`delegated_runtime.py`** (`make delegated-runtime-test`) — the *real* tool-gateway composed
  from env (no overrides/fakes/JWKS patching) against the fixtures: read-path invoke → fail-closed
  acquisition → durable challenge producer → the six authorization routes enroll via a real
  browser-simulated grant over TLS → the delegated send (invoke-delegated → http.get) refreshes and
  calls the real resource server (200). Plus the route-level fail-closed matrix (dedicated workload
  audiences, no-oracle 404s, single-use handles, callback replay, cancel/browser-reset), the MCP
  adapter failing closed pre-session, and the **cross-user approval matrix** (plan line 181):
  requester alice / approver bob reaches the target as **alice's account 42, never bob's 43** (line
  50), with policy/attribution riding bob; wrong requester bearer, altered signed identity, expired
  owner token, foreign session, stale envelope, wrong workload audience/subject, and a direct
  requester override on the ordinary read path all fail closed at **zero dispatch** (line 66: the
  override is ignored, the challenge binds to the verified caller). **EXIT=0.**
- [x] **`delegated_multiproc.py`** (`make delegated-multiproc-test`) — independently started `uvicorn`
  gateway processes against shared custody: cross-replica callback/refresh + cold cache (S1), restart
  durability (S2), revocation dominating warm replicas (S3), and configuration removal failing closed
  (S4), each asserting real network call counts/recipients. **EXIT=0, S1–S4 PASS.**
- [x] **`delegated_custody.py`** (`make delegated-custody-test`, pre-existing) — store-level boundaries
  (key rotation, wrong/removed keys, recovery epochs, account changes, expiry/delay bounds,
  ambiguous/lost-commit) against shared Postgres with independent processes, barriers, fake clocks, and
  a real COMMIT-acknowledgment wire proxy.
- [x] **p5f gate** — `delegated-runtime-test` + `delegated-multiproc-test` added to the Makefile and
  wired **unconditionally** into root `verify` alongside `delegated-custody-test` (plan line 192: no
  optional skip). Harness logs quieted via a shared `quiet_logs()` (app/httpx/httpx2/httpcore/uvicorn →
  WARNING) so the mandatory gate output stays readable; the unreferenced scratch `_dockerfree_check.py`
  was removed. `make -n verify` confirms all delegated harnesses in-chain.

## Browser Edge Proof Increment (p6 — real platform-gateway edge over generated TLS) — 2026-10-29

- [x] **`delegated_edge.py`** (`make delegated-edge-test`, wired into root `verify`) — the layer only the
  **platform-gateway browser edge** (`/api/v1/targets/authorizations`) adds, proven against a *real*
  `uvicorn` platform-gateway process composed from env and served over **generated TLS** (its own CA +
  server certificate), pointed at a *real* tool-gateway process over the fixture OAuth/JWKS/Postgres
  stack — no mocks, no in-process ASGI shortcut, no dependency overrides. Driven with **real cookie jars
  over the wire** (plan line 186):
  - **E1 Authorize** — navigation 302s to the real fixture provider over TLS; `no-store` family; **empty
    body** (provider material never reaches the SPA-visible response); the edge builds the URL but only
    the browser contacts the provider (authorize count asserted).
  - **E2 authorized return** — callback 302s to the server-chosen `/authorizations/return/<cid>`, the
    binding cookie is cleared (`Secure`, `Max-Age=0`), body empty, and **no code/state/cookie/handle is
    reflected** into any response body or header; backend status is genuinely `authorized`.
  - **E3 different browser without the cookie fails** — a cookieless browser is bare-redirected to `/`
    with **no provider contact**, and the single-use handle is **not consumed**: the cookie-holding
    browser still authorizes it (the cookie, not the handle, is the binding proof).
  - **E4 same-browser tabs work** — one cookie jar carrying two concurrent challenges resolves both.
  - **E5 cookie expiry/logout invalidates pending work** — a stale/cleared binding (secret mismatch) and
    a logged-out (cookieless) browser both fail closed with no provider contact.
  - **E6 canceled** (provider denial) and **E7 failed/expired** (spent-state replay) — bounded,
    non-authorized redirects; the provider `error_description` is **never reflected**; a spent state is a
    safe `/` outcome that never re-authorizes.
  - **E8 real edge logs** — the captured platform-gateway process log templates the navigation path
    (`/start/{start_token}`), omits httpx/httpcore diagnostics, and a full canary scan finds **zero**
    leakage of any code, state, cookie secret, handle, or provider URL. **EXIT=0.**
- [x] Callback/start response bodies and headers verified over real TLS throughout (bare 302s,
  `no-store`/`no-cache`/`no-referrer`, `Secure`+`Max-Age=0` cookie clearing), satisfying "verify
  callback/start response bodies and headers and inspect actual edge logs" (line 186) on a real process,
  not caplog alone.
- [ ] **Browser-UI screenshot matrix — environment-blocked, recorded honestly.** The real-browser half of
  line 186 ("once available … screenshots of Authorize, canceled/failed/expired, authorized return, and
  Continue") cannot run in this environment: the fixtures pin the provider callback to
  `https://portal.test/...` (a reserved `.test` host that does **not** resolve — confirmed `gaierror`),
  so a real browser cannot complete the provider→callback round trip without a `/etc/hosts` override
  (sudo, outside the workspace, not authorized) plus installing the generated CA into the browser trust
  store. The portal is an nginx/Docker SPA proxying to `platform-gateway:8000`, built for the deployed
  cluster. Consistent with the plan's conditional wording and the existing precedent (line 148:
  "screenshot capture was unavailable" → rendered-DOM inspection), the browser-binding invariants are
  proven deterministically at the HTTP boundary the browser actually drives (`delegated_edge.py`), and
  the portal card's five states + fresh-turn Continue are covered by the rendered-DOM Vitest suite
  (`AuthorizationCard.test.tsx`, run by `make portal-test` inside `verify`). No screenshot evidence is
  claimed; this limitation is recorded alongside DI-070/AAP.

## R-1: Credential Configuration

- [x] Pin provider-independent parser field names/types and `oauth2_authorization_code`
      validation/projection; preserve existing scheme/default parsing and browser credential
      behavior (R-1a–c foundation; parser and connector regressions above).
- [x] Reject unsupported/incomplete/untrusted config with safe warnings and zero network calls;
      prove delegated generation invalidation on change/removal without changing machine sets.
- [x] Test optional endpoints absent/present/invalid in parser/custody primitives: absent renewal
      is explicitly unsupported, absent provider revocation still permits local revoke, and
      missing identity evidence blocks installation. No guessed endpoint or fallback.
- [x] Exercise these capabilities through actual delegated acquisition and provider identity
      verification with deterministic OAuth/target fixtures (R-1 runtime integration with R-2/R-3).
      _Proven: the `delegated_fixtures.py` self-test runs a real authorization-code grant over generated
      TLS — refresh, `/whoami` immutable-account identity verification, resource call, PKCE-S256 +
      confidential-client enforcement, and revocation — and `delegated_runtime.py` exercises the same
      capabilities through the composed tool-gateway's real acquisition seam. `make verify` EXIT=0._

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
- [x] Integrate custody into actual provider acquisition/callback/cache behavior and exercise
      the complete lifecycle against deterministic OAuth/target fixtures (R-2/R-3 and R-6 completion).
      _Proven: `delegated_runtime.py` (enroll→publish→refresh→send against real Postgres custody),
      `delegated_multiproc.py` (cross-replica callback/refresh, cold cache, restart durability,
      revocation-dominates-warm-replicas, configuration removal), and `delegated_custody.py` (key
      rotation, recovery epochs, lost/ambiguous commit). All three are mandatory `make verify` gates;
      EXIT=0._

## R-2: Acquisition and First-Use Workflow

- [x] Thread verified identity through HTTP and existing MCP calls into the resolver; add a
      separate user-delegated client, not changes to the machine-grant client (R-2a–b).
      _The separate `UserDelegatedClient` is wired into the HTTP/MCP seam (machine-grant client unchanged);
      the write path threads the projection-matched requester and the read path now threads a directly
      verified requester (see the R-2a increment above), both reaching the resolver as the acquisition owner._
- [x] Implement generation-bound cache, bounded expiry, single-flight, safe token-response
      validation, and supported refresh behavior (R-2a/e).
      _Proven: `delegated_multiproc.py` (cold cache + cross-replica refresh S1, restart durability S2),
      `delegated_custody.py` (expiry/delay bounds, generation/epoch fences), and `delegated_runtime.py`
      (safe token-response validation + supported refresh through the real acquisition seam). `make verify` EXIT=0._
- [x] Implement the ratified gateway/agent/portal authorization-required contract and minimal
      workflow feedback; first-use redirect only for the needed target, no settings UI (R-2c).
      _Gateway-side contract emission landed: a verified read now returns the reserved
      `TARGET_AUTHORIZATION_REQUIRED` result carrying the safe `authorization_required` triple the kernel
      promotes (see the Dispatch→Producer Wiring increment above). The kernel bounded stop + closed
      `authorization_required` sibling frame and the portal inline Authorize/status/Cancel control with
      fresh-turn Continue also landed (see the Bounded Kernel Stop and Portal Control increments above);
      integrated first-use/no-loop acceptance is now proven by `delegated_edge.py` (E1 first-use Authorize,
      E2 authorized return) + `delegated_runtime.py`, with the portal card's five states and fresh-turn
      Continue covered by rendered-DOM Vitest (`AuthorizationCard.test.tsx`); the real-browser screenshot
      half stays environment-blocked (see the p6 checkpoint). `make verify` EXIT=0._
- [x] Implement owner-only status/return, cancellation/expiry, and bounded stop/continue;
      completion never dispatches/replays a write or bypasses approval/claims (R-2d).
      _Bounded kernel stop + durable evidence mechanism landed, and the gateway now produces the durable
      challenge + `TARGET_AUTHORIZATION_REQUIRED` result on a verified read (see the 2026-10-29 checkpoints
      above). The portal now renders owner-scoped status (2s poll), Authorize/Cancel, and a fresh-turn
      Continue that re-checks stream + recovery state before re-submitting (see the Portal Control increment
      above); owner-only status/return and cancellation/expiry were already backend-enforced, and integrated
      no-replay/no-bypass acceptance is now proven by `delegated_runtime.py` (callback replay, single-use
      handles, cancel, fail-closed cross-user matrix at zero dispatch) and `delegated_edge.py` (E3 handle not
      consumed by a cookieless browser, E7 spent state never re-authorizes). `make verify` EXIT=0._
- [x] Test first-use, later no-prompt renewal, HTTP/MCP isolation, absent user/grant, transient
      failure versus reauthorization, cancellation, duplicate/expired state, and safe continuation.
      _Proven across `delegated_runtime.py` (first-use challenge, HTTP + MCP-stdio isolation, absent
      user/grant no-oracle 404s, cross-user fail-closed matrix, cancellation, callback/state replay),
      `delegated_multiproc.py` (later no-prompt renewal + transient-vs-reauthorization on cold/warm cache),
      and `delegated_edge.py` (E6 canceled, E7 duplicate/expired spent state, safe continuation). `make verify` EXIT=0._

## R-3: Trust and Callback Security

- [x] Implement exact HTTPS callback/endpoint validation, state + PKCE S256, initiating
      browser/user binding, single-use replay protection, and safe return locations (R-3a).
      _Proven: `delegated_fixtures.py` enforces PKCE **S256** + confidential-client auth and an exact
      `redirect_uri`/callback match; `delegated_edge.py` proves initiating-browser binding over real cookie
      jars (E3 cookieless browser fails without consuming the single-use handle, E5 expiry/logout invalidates
      pending work) and safe return locations (E2 server-chosen `/authorizations/return/<cid>`, E6/E7 bounded
      non-authorized redirects); `delegated_runtime.py` proves single-use state/handle replay protection at the
      callback. Actual-target callback verification is retained under DI-070. `make verify` EXIT=0._
- [x] Verify target immutable account identity against trusted linkage; reject wrong-account
      login, bad issuer/audience/nonce, and username/email-only linking (R-3b).
      _Proven: `delegated_fixtures.py` `/whoami` returns an immutable account id the client verifies against the
      trusted linkage (rejecting username/email-only linking); `delegated_runtime.py`'s cross-user matrix rejects an
      altered signed identity, a wrong workload audience/subject, and an expired owner token at zero dispatch, and
      binds the acquisition to the verified caller's account (requester alice→42, never approver bob→43).
      Actual-target identity/linkage verification against the real provider is retained under DI-070 (R-3b). `make verify` EXIT=0._
- [x] Enforce separate Luban policy/target RBAC and destination-bound HTTP/MCP credentials;
      prove no leakage to another allowed origin or redirected token endpoint (R-3c/d).
      _Proven: `delegated_runtime.py` keeps the delegated credential destination-bound (a wrong requester bearer or a
      direct requester override on the ordinary read path fails closed at zero dispatch; policy/attribution ride the
      verified approver), and its HTTP + MCP-stdio paths are separately exercised; `delegated_edge.py` proves no
      provider material reaches the SPA-visible response body/headers (E1/E2 empty bodies, `no-store`/`no-referrer`)
      and a full canary scan of the real edge logs finds zero leakage of any code/state/cookie/handle/provider URL.
      Actual-target RBAC/allow-deny verification is retained under DI-070 (R-3c). `make verify` EXIT=0._
- [x] Pin/test local cache delays and handling of target revocation, account disable, and
      group removal with deterministic target fixtures; separate SSO logout from target
      grant revocation (R-3e). Actual provider propagation measurements belong to DI-070.
      _Proven: `delegated_custody.py` pins the local cache delay/expiry bounds and asserts revocation + no
      revoked-epoch resurrection; `delegated_multiproc.py` S3 proves revocation dominates warm replicas and S4
      proves configuration removal fails closed; `delegated_edge.py` E5 proves a cleared/expired browser binding
      (logout) invalidates pending work independently of the backend grant, separating SSO-logout from target
      grant revocation. Actual-target propagation/cache-delay measurements remain DI-070 (R-3e). `make verify` EXIT=0._

## R-4: Verified and Queryable Attribution

- [x] Record human, service actor, verified target identity, mode, signed correlation, and
      safe authorization/acquisition failure classes; preserve redaction-overflow attribution.
      _Proven: the audit-service suite plus the end-to-end attribution proof (runtime ingestion → Postgres
      persistence → query filtering) record the human, service actor, verified target identity, derived
      `delegation_mode`, and signed correlation, and preserve attribution across `REDACTION_OVERFLOW` (the mode is
      captured before redaction); safe authorization/acquisition failure classes are asserted by the fail-closed
      matrix in `delegated_runtime.py`. `make verify` EXIT=0._
- [x] Implement the ratified audit schema/filter change and asserting durable query proof
      (R-4b contract/persistence groundwork; v0.50.0 evidence above).
- [x] Emit and test verified delegation attribution end to end; a configured mode label
      alone cannot mark successful delegation (R-4a/c and runtime R-4b integration).
      _The top-level `delegation_mode` is now derived from the verified acquisition outcome at the shared
      resolver and emitted on both the public and the signed delegated `tool_invoked` paths, captured before
      redaction so it survives `REDACTION_OVERFLOW` (see the Delegation-Mode Attribution Increment above); the
      static `target_identity_mode` config label remains distinct and stays in `details`. The narrowly scoped
      `target_authorization` lifecycle event is now emitted at actual enroll/cancel transitions with
      transition-identity dedup and success only from acknowledged publication (see the Target-Authorization
      Lifecycle Emission Increment above), and the end-to-end leg (runtime ingestion → Postgres persistence →
      query filtering, incl. overflow/signed-path attribution) is now proven (see the End-to-End Attribution
      Proof Increment above). The p7 acceptance gate (`make verify`) has now passed (EXIT=0), so the R-4a/c box
      is flipped on that real-execution evidence — a configured mode label alone still cannot mark success._

## R-5: Failure-First Security Invariants

- [x] Prove target access tokens memory-only and refresh tokens ciphertext-only; callback
      code/state handled backend-only and omitted from JS/logs/referrers (R-5a).
      _Proven: `delegated_custody.py` denies ciphertext substitution and never exposes a plaintext refresh token at
      rest (access tokens are held memory-only, never persisted); `delegated_edge.py` proves the callback code/state
      are handled backend-only and omitted from the SPA-visible response (`no-store`, empty bodies, `no-referrer`) and
      from the real edge logs (E8 templated navigation path + zero-canary leak). `make verify` EXIT=0._
- [x] Inject opaque test secrets into URLs, headers, responses, errors, logs, traces, results,
      evidence, and audit; repair uncovered representations; pass secret-vocabulary gate (R-5b).
      _Proven: `delegated_edge.py` injects opaque canaries (code/state/cookie-secret/handle/provider-URL/denial
      description) and scans every response body, header, and the real edge process log, finding zero leakage; the
      tool-gateway suite injects opaque secrets across results/evidence/audit, and the root `validate-secret-vocabulary`
      gate passes inside `make verify`. `make verify` EXIT=0._
- [x] Spy on Basic/bearer/machine/unauthenticated/alternate-transport paths, including MCP
      diagnostics/stdio; failed delegated acquisition invokes none (R-5c).
      _Proven: `delegated_runtime.py` spies every fallback transport (Basic/bearer/machine/unauthenticated and the
      MCP-stdio diagnostics path) and asserts a failed or unenrolled delegated acquisition invokes **none** of them —
      the cross-user matrix and no-oracle 404s all fail closed at zero dispatch, with the MCP adapter refusing
      pre-session. `make verify` EXIT=0._
- [x] Assert failure-first callback/identity/key/store/token endpoint/malformed-response tests
      open no target session and never grant execution authority (R-5d).
      _Proven: failure-first tests across `delegated_runtime.py` (callback replay/denial, identity mismatch, token
      endpoint + malformed response), `delegated_custody.py` (key/store failure fails closed), and
      `delegated_multiproc.py` (configuration removal S4) each assert **no** target session is opened and **no**
      execution authority is granted (zero dispatch, no resource-server contact). `make verify` EXIT=0._

## R-6 Completion: Provisioning and Operator Documentation

- [x] Wire file-mounted target/client config plus least-privilege database/key mounts and
      network access; keep delegation disabled until provisioned; pass `make overlays` (R-6c).
      _Proven: the disabled-by-default delegated-dev overlay mounts file-based target/client config, the custody DSN,
      and the keyring, projects dedicated workload JWTs, pins the exact callback, and applies least-privilege egress;
      infra SQL splits a custody runtime DML role from an operator admin role with least-privilege grants. Delegation
      stays disabled until provisioned, and `make overlays` renders every overlay cleanly inside `make verify`. EXIT=0._
- [x] Update existing operator/configuration/troubleshooting guides for registration, first-use,
      renewal, recovery, key rotation, revocation/offboarding, rollback, and SSO limits (R-6d).
      _Done: the configuration/tool/troubleshooting and SPEC-070 operator guides were updated for registration,
      first-use, renewal, recovery, key rotation, revocation/offboarding, rollback, and SSO limits, alongside the
      backend operator CLI (migrate/readiness/local-revoke/remote-revoke-attempt/rotate/re-encrypt/recover) with
      secret-file-path args and no enrollment path. DI-070/AAP is documented as pending with no compatibility claim._
- [x] Exercise setup, disconnect, recovery, and rollback against deterministic OAuth/target
      fixtures and real Postgres. Document DI-070 as pending, with no AAP compatibility claim.
      _Proven: setup/enroll (`delegated_runtime.py` browser-simulated grant → real Postgres publication), disconnect
      (`delegated_multiproc.py` S4 configuration removal fails closed), recovery/rollback (`delegated_custody.py`
      recovery epochs, key rotation, ambiguous/lost-commit) all run against deterministic OAuth/target fixtures and
      real Docker Postgres. DI-070 is documented as pending/environment-blocked with no AAP compatibility claim (see
      the Post-Delivery Deployment Integration section and the p6 browser-UI limitation). `make verify` EXIT=0._

## Acceptance-to-Test Matrix

Full development acceptance **R-1a–R-6d PASSED** (2026-10-29) on real-execution evidence: root
`make verify` EXIT=0 with every product suite, the portal Vitest + build, overlays/secret-vocabulary/
policy/dashboard/version gates, the disposable execution-failure campaign (795 passed), and all four
mandatory delegated harnesses. The "Asserting coverage" column below is now realized by concrete
paths — not planned shapes:

- `products/tool-gateway/tests/integration/delegated_fixtures.py` — generated-CA TLS + fixture OAuth
  (PKCE **S256** + confidential-client auth), `/whoami` immutable-account identity, resource server,
  JWKS, MCP recorder, 2 users/2 accounts, disposable Postgres; self-test runs a real grant→refresh→
  identity-verify→resource-call→revoke (realizes R-1a–c, R-3a/b identity linkage).
- `products/tool-gateway/tests/integration/delegated_runtime.py` (`make delegated-runtime-test`) — the
  real composed tool-gateway over the fixtures: read→fail-closed acquisition→durable challenge→six
  routes enroll→delegated send (200); route-level fail-closed matrix + MCP-stdio pre-session refusal +
  cross-user approval matrix at zero dispatch (realizes R-2a/b/e, R-2c/d, R-3b/c/d, R-4, R-5c/d).
- `products/tool-gateway/tests/integration/delegated_multiproc.py` (`make delegated-multiproc-test`) —
  independent `uvicorn` processes over shared custody: cross-replica callback/refresh + cold cache (S1),
  restart durability (S2), revocation-dominates-warm-replicas (S3), configuration removal (S4)
  (realizes R-2a/e renewal + transient-vs-reauth, R-3e, R-5d).
- `products/tool-gateway/tests/integration/delegated_edge.py` (`make delegated-edge-test`) — the real
  platform-gateway browser edge over generated TLS vs a real tool-gateway process, driven by real cookie
  jars: E1 Authorize, E2 authorized return, E3 different-browser-no-cookie fails without consuming the
  handle, E4 same-browser tabs, E5 expiry/logout invalidates, E6 canceled, E7 failed/expired replay,
  E8 secret-safe real edge logs (realizes R-2c/d, R-3a, R-3e logout distinction, R-5a/b).
- `products/tool-gateway/tests/integration/delegated_custody.py` (`make delegated-custody-test`) — store
  boundaries: key rotation, wrong/removed keys, recovery epochs, account changes, expiry/delay bounds,
  ambiguous/lost-commit, ciphertext-substitution denial, no revoked-epoch resurrection (realizes R-3e,
  R-5a, R-6a/b).
- Portal `AuthorizationCard.test.tsx` (rendered-DOM Vitest, `make portal-test`) covers the card's five
  states + fresh-turn Continue; audit-service suite + the end-to-end attribution proof cover R-4a/b/c.

Two obligations are explicitly **not** closed here and remain honestly recorded: **DI-070/R-6e** (actual
AAP/target verification of R-3b/c/e — AAP unreachable) and the **real-browser UI screenshot matrix**
(environment-blocked: the fixtures pin the callback to the unresolvable reserved `.test` host; see the p6
checkpoint). Neither is a development-acceptance criterion. Integration coverage exercises real Luban
enforcement against deterministic OAuth and per-user target fixtures, never canned shared-bearer success.

**Evidence scope clarification (2026-10-30):** the implemented target-identity profile is
`json_immutable_id` via a configured HTTPS identity endpoint, not an ID-token profile; no
issuer/audience/nonce ID-token verification is claimed. Runtime fixtures prove HTTP success
and MCP acquisition failure boundaries, not successful real-AAP MCP delegation. The edge
harness inspects platform-gateway process logs, not nginx logs; actual nginx request-log
inspection remains outstanding as recorded in [troubleshooting](../../guides/troubleshooting.md).

| Criteria | Asserting coverage (realized) | Primary boundary |
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

- [x] Gate 0 and 2026-10-23 amendment recorded; all development criteria R-1a–R-6d mapped
      to actual asserting tests and passed; every changed contract tested in its consumers.
      DI-070 is explicitly outside this development gate, not represented as passed.
      _R-1a–R-6d are each mapped to concrete asserting paths in the Acceptance-to-Test Matrix above and pass
      under root `make verify` (EXIT=0, 2026-10-29). The changed contracts (`target_authorization` vocabulary in
      all three mirrors + audit schema/filter) are tested in their consumers (audit-service suite, portal
      `AuthorizationCard.test.tsx`, end-to-end attribution proof). DI-070/R-6e and the real-browser UI screenshot
      matrix remain open/environment-blocked and are **not** represented as passed._
- [x] Root `make verify` passes, including secret vocabulary, overlays, portal tests/build,
      policy, dashboards, version checks, and disposable execution-failure campaign.
      _Ran 2026-10-29: VERIFY_EXIT=0. Every product suite (agent-platform 1633, tool-gateway 1066,
      platform-gateway 473, skills-hub 291, audit-service 147, incident-service 138, execution-runtime 94,
      identity-broker 63, shared validators), `validate-secret-vocabulary`, `overlays`, portal Vitest (537+44) +
      build, policy (144 api / 32 tools) + scenarios, dashboards, version, and the execution-failure campaign
      (795 passed, 2 deselected; campaign duration 28:17) all green, plus the four mandatory delegated
      harnesses. Nonfatal output includes Starlette deprecations, a Vite chunk-size notice, jsdom
      pseudo-element and Ant Design X environment notices, and expected fail-closed warnings._
- [x] Existing-scheme regressions and every no-fallback/no-disclosure test pass.
      _Existing-scheme/default parser + connector + machine-grant regressions pass unchanged (tool-gateway 1066,
      platform-gateway 473); the no-fallback spies (`delegated_runtime.py` fallback-transport/MCP-stdio zero-invoke,
      cross-user zero-dispatch matrix) and no-disclosure tests (`delegated_edge.py` canary scan, secret-vocabulary
      gate) all pass under `make verify` EXIT=0._
- [x] ADR-0016 accepted/indexed and ADR-0015 supersession recorded (2026-10-18).
- [x] Living state docs updated to implemented behavior, not planned capability; SPEC-069's
      delivered dev record preserved and its production dependency status updated accurately.
      _Completed 2026-10-30 under explicit staging/documentation authorization: [Unreleased notes](../../../CHANGELOG.md#unreleased),
      SPEC-070 status/index, delivery roadmap, identity design, tool-gateway README, and operator/configuration/
      troubleshooting guides now distinguish implemented runtime from contract-only v0.50.0.
      SPEC-069's [dated dependency update](../SPEC-069-ansible-read-tier-mcp-ingestion-pilot/tasks.md#production-dependency-status-update--2026-10-30)
      and spec changelog reconcile its production dependency without rewriting delivered v0.48.0 requirements
      or dev evidence. Runtime remains unreleased/default-off; `VERSION` stays `0.50.0` and status stays
      `in-progress`. DI-070/AAP, browser screenshots, and actual nginx log-inspection limits remain disclosed.
      No commit, release, or deployment is authorized by this documentation gate._
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
