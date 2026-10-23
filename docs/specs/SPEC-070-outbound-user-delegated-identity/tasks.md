# SPEC-070 Tasks: Outbound User-Delegated Execution Identity (Tool-Gateway Substrate)

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

> **Approved; delivery boundary amended 2026-10-23.** ADR-0016 remains accepted and OQ-7
> ratified. Development acceptance covers R-1–R-6d without a real AAP dependency. OQ-3 and
> former acceptance criterion R-6e are tracked under **DI-070** below: mandatory before
> production target enablement, not a development-delivery or version-bump gate. No runtime
> task is complete. The attached kickoff plan and accepted ADR bodies are unchanged.
> This documentation commit is for operator review before code; other handoff gates remain.

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

- [ ] Add tool-result authorization-required signal, stream v13 with all consumer surfaces,
      and audit delegation-mode contract/query parity; preserve existing callers and keep
      runtime delegation inert until configured (R-2b/c, R-4b).
- [ ] Define route/request/response shapes and transaction-store Protocol/record fields with
      pinned TTL defaults; do not expose a usable authorization flow before trust/custody
      and policy checks are implemented. Test schema/consumer parity and safe omission.

## R-1: Credential Configuration

- [ ] Pin provider-independent parser field names/types, then add `oauth2_authorization_code`
      validation/projection under the R-1 capability contract; preserve existing scheme/default
      parsing and browser credential behavior (R-1a–c).
- [ ] Reject unsupported/incomplete/untrusted config with safe warnings and zero network calls;
      enforce delegated generation invalidation on change/removal without changing machine sets.
- [ ] Test optional endpoints absent/present/invalid; absent renewal is explicitly unsupported,
      absent provider revocation still revokes locally, and absent verifiable target identity
      blocks authorization. No guessed endpoint, degraded identity check, or fallback.

## R-6 Foundation: Encrypted Postgres Custody

- [ ] Implement gateway-owned tables/role, versioned authenticated encryption, owner/target
      binding, separately mounted keys, and product dependency/frozen lockfile (R-6a).
- [ ] Implement single-use authorization transactions and cross-process credential generation,
      refresh rotation, local revocation, and cache invalidation; fail closed on store/key failure.
- [ ] Prove real-Postgres concurrency, ciphertext substitution denial, key rotation, crash/restart,
      lost provider refresh response/commit, and no revoked-record resurrection (R-6b).

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
- [ ] Implement any ratified audit filter/schema change and asserting durable query test;
      a configured mode label alone cannot mark successful delegation (R-4a–c).

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

Development entries R-1a–R-6d are **planned / not run**. Replace each obligation with concrete
test paths/names and results before delivery; this matrix is not execution evidence. Tests
must exercise real Luban enforcement against deterministic OAuth and per-user target fixtures,
not canned shared-bearer success. DI-070 separately tracks actual AAP evidence.

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
