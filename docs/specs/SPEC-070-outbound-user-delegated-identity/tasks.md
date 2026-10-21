# SPEC-070 Tasks: Outbound User-Delegated Execution Identity (Tool-Gateway Substrate)

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

> **Approved (amended) — 2026-10-18; OQ-7 ratified 2026-10-19.** Redirect-based direction is
> ratified; ADR-0016 is accepted and ADR-0015 superseded. OQ-7 (detailed first-use contract)
> is **ratified** — the pre-runtime gate is closed; OQ-3 (target profile) is the sole open
> (pre-live) gate. No R-1–R-6 runtime task is complete. The attached kickoff plan is not
> edited. Commit/push, deployment, live tests, and release are separate.

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
- [ ] **OQ-3:** obtain intended AAP release/patch and MCP build plus Keycloak/SSO facts;
      pin explicit endpoints, client auth, callback, PKCE S256, scopes, target account
      linkage, refresh issuance/rotation/revocation, token lifetimes, and group/RBAC lifecycle.
- [x] **OQ-7:** complete and ratify exact API/stream/owner-state/browser-binding contracts,
      credential configuration fields, audit-query impact, and safe stop/continue semantics
      against the existing signed-execution path. No callback may dispatch a tool. **Drafted
      (proposed) 2026-10-18** in
      [oq7-first-use-handoff-contract.md](oq7-first-use-handoff-contract.md): bounded-stop (not
      park) signal via a reserved `TARGET_AUTHORIZATION_REQUIRED` code + additive
      `authorization_required` tool-result object and stream v13 frame; owner-scoped
      single-use `challenge_id`/`start_token`/`state`; portal + internal routes; replica-safe
      transaction store; new-turn continue that re-passes policy/HITL/signed-execution/claim;
      top-level `delegation_mode` audit field. **Ratified 2026-10-19** — the pre-runtime gate
      is closed and R-1..R-6 may begin against it; the two flagged TTL/PKCE values stay
      **[OQ-3]-gated** pins until the deployment facts arrive.
- [x] Obtain revised spec/ADR approval before runtime work — **done 2026-10-18:** operator
      approved the amended spec; ADR-0016 accepted and ADR-0015 marked `superseded by
      ADR-0016` (status/link only, accepted body preserved). Approval authorized the OQ-7
      design, which was **ratified 2026-10-19** — R-1..R-6 implementation may now begin
      against the contract; runtime code that depends on the OQ-3 facts stays gated.
- [ ] Obtain separate authorization and an actual target environment for live token/RBAC tests.

**Build sequence after approval:** R-1 → R-6 store foundation → R-2/R-3 → R-4 → R-6
provisioning/live proof, with R-5 failure-first tests at every step.

## R-1: Credential Configuration

- [ ] Add `oauth2_authorization_code` validation/projection with the ratified fields; preserve
      existing scheme/default parsing and browser credential behavior (R-1a–c).
- [ ] Reject unsupported/incomplete/untrusted config with safe warnings and zero network calls;
      enforce delegated generation invalidation on change/removal without changing machine sets.

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
- [ ] Pin/test local cache delays, target revocation, account disable, and group removal;
      separate SSO logout from target grant revocation (R-3e).

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

## R-6 Completion: Provisioning and Operational Proof

- [ ] Wire file-mounted target/client config plus least-privilege database/key mounts and
      network access; keep delegation disabled until provisioned; pass `make overlays` (R-6c).
- [ ] Update existing operator/configuration/troubleshooting guides for registration, first-use,
      renewal, recovery, key rotation, revocation/offboarding, rollback, and SSO limits (R-6d).
- [ ] With separate authorization, prove actual AAP two-user RBAC, first-use/reauthorization,
      no-prompt renewal, account/group changes, restart, and configuration removal (R-6e).

## Acceptance-to-Test Matrix

All entries are **planned / not run**. Replace each planned obligation with concrete test
paths/names and results before delivery; do not count this matrix as execution evidence.

| Criteria | Planned asserting coverage | Primary boundary |
| --- | --- | --- |
| R-1a, R-1b, R-1c | Parser/projection regression; unsupported fields/trust/scopes; zero network calls | tool-gateway |
| R-2a | Two users/two targets; cache expiry, scope/generation isolation, single-flight | HTTP + MCP + Postgres |
| R-2b, R-2e | Missing grant/user; malformed response; refresh success/denial; transient-error distinction; zero target sessions | tool-gateway |
| R-2c | First-use redirect only for needed target; no settings/manual tokens; no loop on cancellation | gateway + portal |
| R-2d | Owner return/status; cancellation; current-policy continue; no callback dispatch, consumed-claim reuse, or unknown-write retry | agent + portal + signed execution |
| R-3a | State/code replay, CSRF, PKCE, mix-up, browser/session substitution, open redirect | gateway callbacks |
| R-3b, R-3c | Wrong target account; immutable linkage; ID-token validation when used; platform/target allow/deny | gateway + actual target |
| R-3d | Allowed-but-unrelated origin, HTTP redirect, MCP destination, token-endpoint redirect | HTTP + MCP |
| R-3e | Group removal, account disable, grant revoke, logout distinction, bounded cache delay | local + actual target |
| R-4a, R-4b, R-4c | Verified mode/account; failed enrollment; durable audit filter round-trip; signed correlation; overflow | gateway + audit |
| R-5a, R-5b | Ciphertext-only refresh; memory-only access; opaque-secret injection; callback/access-log/JS/referrer exclusions | gateway + portal + telemetry |
| R-5c, R-5d | Every fallback spy remains zero; key/store/provider/callback failure opens no target session | HTTP + MCP + callback |
| R-6a, R-6b | Real-Postgres owner/target substitution, concurrent rotation/revoke, lost response, restart/key rotation | independent processes + Postgres |
| R-6c, R-6d | Overlay rendering; disabled-until-configured; exercised setup/revocation/recovery/rollback procedures | GitOps + operator guides |
| R-6e | Authorized actual-target two-user first-use/renewal/RBAC/lifecycle campaign; mocks explicitly insufficient | live AAP/MCP |

## Delivery Gate

- [ ] Gate 0 approval recorded; all criteria mapped to actual asserting tests and passed;
      every changed contract tested in its consumers; live target evidence recorded.
- [ ] Root `make verify` passes, including secret vocabulary, overlays, portal tests/build,
      policy, dashboards, version checks, and disposable execution-failure campaign.
- [ ] Existing-scheme regressions and every no-fallback/no-disclosure test pass.
- [x] ADR-0016 accepted/indexed and ADR-0015 supersession recorded (2026-10-18).
- [ ] Living state docs updated to implemented behavior, not planned capability; SPEC-069's
      delivered dev record preserved and its production dependency status updated accurately.
- [ ] Release bookkeeping and `VERSION` changes only with separate authorization; no
      `delivered` status while acceptance or authorized live proof is pending.

> **Forward path.** SPEC-070 is the production-identity dependency SPEC-069 R-1 names; the
> Layer-2 runbook-typed-tools fast-follow (number assigned at its own drafting) also relies
> on it for user-delegated action attribution. SPEC-069's read-only **dev** slice does not
> block on SPEC-070 — it validates against a self-hosted server's own auth.
