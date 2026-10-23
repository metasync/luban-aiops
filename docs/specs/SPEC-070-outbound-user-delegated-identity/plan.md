# SPEC-070 Plan: Outbound User-Delegated Execution Identity (Tool-Gateway Substrate)

> **Approved; delivery boundary amended 2026-10-23.** First-use redirects without
> credential settings, accepted [ADR-0016](../../adr/0016-just-in-time-outbound-oauth-authorization.md),
> and the ratified OQ-7 handoff remain the design. Development acceptance (R-1–R-6d) is
> independent of AAP availability; OQ-3/R-6e are the separate
> [DI-070 deployment-integration task](tasks.md#post-delivery-deployment-integration-di-070).
> The attached kickoff plan and accepted ADR bodies remain unchanged. The documentation
> amendment preceded implementation. **Later checkpoint, 2026-10-23:** the additive OQ-7
> contracts are implemented and verified, and the operator approved their contract-only
> **v0.50.0** release. Full SPEC-070 delivery remains open for a later, unselected release;
> OAuth workflow/custody is not enabled. See [checkpoint evidence](tasks.md#additive-oq-7-contract-increment).
> **AAP compatibility unverified**; this technical plan's remaining requirements still apply.

## Approach

Retain target-issued authorization-code and server-side refresh acquisition in tool-gateway.
Keep existing Basic/bearer/machine-grant behavior and internal Luban delegation unchanged.
No upstream Keycloak access-token custody or outbound broker signing authority is added.

The portal offers authorization in the current workflow when an allowed operation first
needs a target grant. It may display target login/consent through a standard redirect,
then returns to the owned conversation. Renewal is server-to-server until reauthorization
is required; normal Luban login does not connect every target. No settings page, token
copying, or enrollment helper is part of the user experience.

## Gate 0 — Development Approval and Integration Boundary

- Spec/ADR direction was approved 2026-10-18, OQ-7 ratified 2026-10-19, and the delivery
  boundary amended by the operator 2026-10-23. Preserve accepted ADR bodies and dated history.
- Implement the provider-independent OAuth contract: confidential client, exact HTTPS
  callback, S256 without downgrade, explicit scopes/destinations, verified immutable account
  linkage, encrypted Postgres custody, and bounded lifecycle handling. Optional endpoint
  behavior is pinned below; missing capability never authorizes a weaker fallback.
- Pin local defaults to 60 seconds for start handles and 600 seconds for transaction/state;
  validate positive bounded lifetimes and fail closed on expiry. These are Luban defaults,
  not measured AAP values; deployment reconciliation belongs to DI-070.
- Keep development evidence (deterministic OAuth/target fixtures, real Postgres, consumer
  contracts, workflow/security tests) separate from deployment evidence in the
  [report](compatibility-report.md#development-delivery-and-deployment-integration-2026-10-23).
- DI-070 records actual AAP/MCP/SSO versions, endpoints, client registration, enforced S256,
  renewal/revocation, account linkage, and RBAC/lifetime measurements. No shared-bearer mock
  can close it. It blocks production target enablement, not the substrate's release.
  Registration, deployment, and live token/account tests still need separate permission.

## First-Use Handoff — Ratified Contract Boundary (OQ-7)

1. Tool-gateway reports a typed authorization-required failure without opening a target
   session. A generic upstream error or model-authored text cannot initiate OAuth.
2. A server-authenticated, owner-scoped workflow record identifies the needed configured
   target and originating conversation. It contains no access token, refresh token, code,
   verifier, or provider authorization URL. Agent-platform must stop boundedly, not loop.
3. Platform-gateway authenticates initiation from the portal and verifies ownership,
   target entitlement, and CSRF protection; tool-gateway owns the OAuth transaction and
   PKCE verifier. Only the backend selects endpoint, scope, callback, and local return path.
4. The backend callback validates single-use state and browser/user binding, redeems the
   code, verifies target account identity, and commits encrypted custody before reporting
   success. Portal JS never handles the code or target tokens. No-store callback handling
   removes query material before returning to the conversation.
5. Owner-authenticated status distinguishes pending, authorized, canceled, expired, and
   failed. A wrong user/tab-session, stale configuration, duplicate callback, or lost
   provider response cannot overwrite another user's credential or resurrect a revoked one.
6. Completion only restores workflow context. A subsequent continue/retry passes current
   policy and existing execution-safety gates; callback/status handlers cannot invoke tools.
   Never automatically replay a write, reuse a consumed claim, or convert an unknown
   outcome to not-dispatched. Cancellation leaves existing approvals/executions unchanged.

**Detailed contract ratified (2026-10-19).** The six items the boundary requires — exact route
methods/paths and schemas, server-side browser-binding lifetime, challenge-to-conversation
persistence, authenticated internal handoff, stream projection/versioning, and continue
semantics against the shipped signed-execution call chain — are specified in
[OQ-7: First-Use Authorization Handoff](oq7-first-use-handoff-contract.md), grounded in the
shipped secret-delivery single-use handles, HITL registry, stream v12, tool-result error
object, gateway confirm routing, and audit attribution seams. The operator **ratified** that
document on 2026-10-19, closing the pre-runtime gate: R-1..R-6 implementation may now begin
against it. The 2026-10-23 amendment pins local TTL defaults and mandatory S256; actual
provider enforcement and deployment lifetime reconciliation remain DI-070 checks. R-1 and
R-6 internals no longer depend on AAP facts. The contract confirms the current tool-result
schema allows only error `code`/`message`, so the handoff is a genuinely new additive
contract, not an implemented feature.

## Design Per Requirement

### R-1: Credential Configuration

- Extend `tools/credential_sets.py` scheme validation and field projection; preserve every
  existing scheme, omitted-scheme behavior, and browser credential consumer.
- Declare target authorization/token endpoints, confidential client auth, callback, scopes,
  target/resource binding, S256, trusted identity-linkage configuration, and store reference.
  The 2026-10-23 amendment removes the requirement to derive parser/custody design from AAP
  deployment facts. These are operator-supplied protocol configuration, not discovered AAP
  defaults. Preserve the existing string-valued credential-set projection and keep the
  delegated scheme's validation separate from existing scheme behavior.
- **Optional endpoint contract:** renewal, revocation, and identity-resolution endpoints
  may be absent. If supplied, each is a non-empty string naming a trusted HTTPS destination;
  reject invalid type, blank value, userinfo, fragment, untrusted origin, and unsupported
  profile before network use. No automatic endpoint discovery, guessed AAP paths, or reuse
  of an unrelated allowlisted origin. A renewal endpoint may explicitly equal the configured
  token endpoint; omission must not silently enable renewal.
- **Missing renewal:** return an explicit unsupported-renewal result; no invented refresh
  token, machine/PAT fallback, or automatic redirect loop. A supported refresh flow must still
  be implemented and tested with deterministic endpoints before development delivery.
- **Missing provider revocation:** local disconnect/revocation, durable generation changes,
  and cross-replica cache invalidation remain mandatory. Report provider revocation as
  unsupported/unconfirmed; never label local removal as remote success. A configured endpoint
  failure remains visible and cannot undo local revocation.
- **Missing identity endpoint:** optional configuration is not optional identity proof. Before
  reporting authorization success or opening a resource session, verify the token's immutable
  target account through the configured trusted evidence path and match its administered
  linkage to the Luban subject. OAuth-only targets without an identity endpoint are unusable;
  an independently validated ID-token evidence path, where supported, must verify signature,
  issuer, audience, and nonce. Neither a mapping alone nor matching names/emails proves the
  token's account. Missing or unsupported evidence blocks authorization, not another redirect.
- Validate before network use. Keep existing machine-set reload semantics; delegated config
  removal/change must invalidate its generation across replicas, not retain stale grants
  indefinitely under keep-last-good configuration behavior.
- **Gate:** R-1a–c parser/projection regressions; malformed/unsupported config; zero network
  calls on rejection; delegated config removal and unreadable-config failure cases.

### R-6 Foundation: Postgres Custody Before Acquisition

- Gateway-owned tables and dedicated database role on existing Postgres. Add a Postgres
  dependency and frozen product lockfile only at implementation; reuse `cryptography`.
- Authenticated encryption binds ciphertext to owner namespace/subject, target, set, and
  configuration generation. Separate versioned key mounts from database credentials/data.
- Persist required refresh tokens encrypted; access tokens memory-only. Persist short-lived
  authorization transaction state server-side, with single-use claims and encrypted PKCE
  verifiers if durable. Do not persist authorization codes.
- Coordinate refresh with row-level locking/generation checks and local revocation across
  processes. A provider rotation and local database commit cannot be one atomic transaction:
  lost/uncertain rotation requires reauthorization, never stale-token resurrection.
- Recheck credential/config generation before serving cache hits; bound and test propagation.
  Store/key unavailability fails closed even if a process still holds a cached token.
- **Gate:** real disposable-Postgres tests for ciphertext-only persistence, owner/target
  substitution, wrong/unavailable keys, concurrent callback/refresh/revoke, crash/restart,
  rotated-token response loss, key rotation, and cache invalidation across processes.

### R-2: User Context, Acquisition, and First-Use Workflow

- Keep `tools/oauth_client.py` machine-grant behavior unchanged. Use a separate
  `tools/user_delegated_client.py`; thread verified identity through `tools/auth_resolution.py`,
  `tools/http_connector.py`, and `ingestion/mcp_adapter.py` from `BaseTool.execute`.
- Cache by identity namespace/subject, set, target/audience, scope, and credential/config
  generation; bound expiry and use single-flight. Validate token response type, expiry,
  scope, and identity against the approved profile. No subject supplied by the model.
- Implement the ratified first-use contract across gateway, agent-platform, and portal.
  Treat invalid/revoked grants as reauthorization-needed; distinguish transient errors to
  prevent repeated consent loops. Success requires committed custody and verified account.
- **Gate:** two-user/two-target isolation; cache/expiry/refresh; no-subject failures; HTTP
  and MCP consumers; first-use, later no-prompt renewal, canceled/expired authorization,
  return-to-conversation, forged challenge, duplicate callback, and safe continuation.

### R-3: Trust, Browser Transaction, and RBAC

- Register a confidential OAuth client at the target; backend-only client authentication.
  Require explicit HTTPS endpoints/callback, state + PKCE S256, account identity evidence,
  target destinations/scopes, and separate platform/target group mappings.
- Initiation and status are authenticated/owner-scoped; callback uses a single-use browser
  binding and state. A callback must not trust an arbitrary subject/query parameter or
  require the browser to send an internal bearer token on a top-level redirect.
- Reject wrong-account linking, mix-up, state/verifier replay, arbitrary return locations,
  untrusted redirect destinations, wrong audience/scope, and absent target entitlement.
  Restrict callback logging/referrers/caching before exercising the flow.
- **Gate:** state/code/PKCE/CSRF and session/account substitution tests; redirect leakage;
  denied users; account disable/group removal; local versus target revocation propagation.
  No unsupported-PKCE or service-credential fallback; exceptions need a separate decision.

### R-4: Verified and Queryable Attribution

- Reuse connector attribution hooks and `services/gateway_service.py`; retain human `sub`,
  actor, target system/account, and signed correlation. Delegation mode comes from verified
  acquisition, not a configuration label. Failed enrollment is not a successful delegated call.
- Implement the top-level delegation-mode field and durable audit query/filter/schema changes
  ratified in OQ-7 §10/§13.4; preserve existing event types and non-delegated callers.
- **Gate:** signed-path integration, two-user attribution, redaction overflow, durable audit
  round-trip/filter assertions, and safe authorization/renewal/revocation failure reporting.

### R-5: Failure-First Security Tests Throughout

- Write negative tests before happy paths: invalid callbacks, revoked grants, missing user,
  failed store/decryption, timeout, malformed tokens, and lost rotation response.
- Spy on every machine/basic/bearer/unauthenticated branch, including MCP diagnostics and
  stdio. Failed delegated acquisition opens no target connection and invokes no fallback.
- Inject recognizable opaque access/refresh tokens, codes, state, verifiers, and client
  secrets into response/error/log paths. Assert exclusion from portal JS/storage, kernel,
  transcript, evidence, audit, traces, ingress/access logs, and referrers. Only the necessary
  provider-to-backend code/state redirect is allowed; scrub it before rendering any UI.
- **Gate:** no fallback/disclosure assertions and `make validate-secret-vocabulary`;
  repair proven masking/omission gaps instead of presuming substring rules suffice.

### R-6 Completion: Provisioning and Operator Proof

- Reuse file-mounted `credential-sets.json`/`sync-browser-credentials.sh` for target/client
  config; add gateway Postgres/key provisioning and least-privilege network access.
- Keep disabled until configured. No per-user provisioning script/settings UI. Provide
  operator revocation/offboarding and recovery procedures, not manual target-token entry.
- **Development gate:** `make overlays`, existing-guide updates, real custody tests, and
  exercised setup/revocation/recovery/rollback procedures using deterministic OAuth/target
  fixtures. CI makes no live external call. A static shared-bearer mock cannot replace the
  user-delegated protocol, account-binding, lifecycle, and denial tests.
- **Integration gate (DI-070):** separately authorized two-user AAP proof of first-use,
  renewal, denial, revocation/group changes, restart, unavailable target, and config removal.
  Required before production target enablement, not before development delivery. No mock
  or documentation research satisfies this target-specific proof.

## Sequencing And Dependencies

1. **Documentation amendment:** commit the approved 2026-10-23 scope change separately for
   operator review before runtime code. Preserve the ADR bodies and historical approvals.
2. **Additive OQ-7 contract increment:** tool-result signal, stream v13 consumer lockstep,
   audit mode/query contract, route shapes, and transaction-store Protocol/record fields.
   Test parity; no usable delegated flow until trust, custody, and policy checks exist.
3. **R-1 + R-6 foundation increment:** provider-independent configuration/capability behavior
   and encrypted custody, reviewed separately from the contract increment. Failure-first
   parser tests and real Postgres callback/rotation/revocation tests remain mandatory.
4. **R-2/R-3 acquisition + first-use workflow + trust** across HTTP/MCP, gateways, agent, portal.
5. **R-4 verified audit attribution and queryability** exercised end to end.
6. **R-6 provisioning/guide completion** with deterministic protocol/target fixtures and real
   custody proof. No live AAP dependency in the development acceptance matrix.
7. **Development delivery:** R-1–R-6d acceptance traceability and root `make verify`;
   release notes disclose DI-070 pending / AAP compatibility unverified. Commit/push,
   deployment, version bump, and release remain separately authorized.
8. **DI-070 deployment integration:** OQ-3 profile and actual AAP two-user proof when the
   environment and separate authorization arrive; mandatory before production target
   enablement, but not a prerequisite to step 7 or subsequent development.

R-5 negative tests accompany every stage. SPEC-069's delivered dev slice remains unaffected;
its production user-delegated path still depends on this undelivered substrate.

## Test Strategy

- Map every development criterion R-1a–R-6d to actual asserting tests before delivery; the
  [task matrix](tasks.md#acceptance-to-test-matrix) lists planned coverage, not test passes.
  R-6e is relocated to DI-070, not waived or represented as a passed mock test.
- Protocol unit/integration tests use deterministic fake OAuth endpoints; they do not prove
  AAP support. Custody tests use real disposable Postgres and independent processes.
- Contract tests cover every consumer of changed API/stream/audit schemas. Portal tests
  cover first-use/return/cancel/expiry without settings UI or credential exposure.
- Focused suite: `make -C products/tool-gateway test`; also test platform-gateway,
  agent-platform, audit-service, and portal as their contracts change. Identity-broker
  regression tests prove the normal SSO path remains unchanged.
- Full gate: root `make verify`, including product/portal, overlay, policy, dashboard,
  version, secret-vocabulary, and disposable execution-failure checks. Unit tests alone
  cannot replace it. Separately authorized AAP live tests remain explicitly pending under
  DI-070 and are not a dependency of this gate.

## Rollout And Migration

- Development delivery does not enable or certify a production AAP target. Keep it disabled
  until DI-070 supplies its verified profile and actual two-user proof. Authorized integration
  testing may provision only its scoped validation target; it is not general production rollout.
- New tables, key/database mounts, callback routes, browser-binding controls, and safe
  access-log configuration must exist before enabling a delegated set. No product upgrade
  or target registration is assumed authorized by this document.
- Existing credential schemes/browser fill remain unchanged. New delegation is inert until
  provisioned. Target tokens never change the internal identity-token contract.
- Disable/remove the delegated configuration, invalidate generations/transactions/caches
  across replicas, and block outbound use before rollback. Local invalidation does not
  equal provider revocation; report and retry provider revocation through the reviewed
  operator procedure. Never restore revoked credentials from an old backup or key version.
- Database/key migration and recovery need their own tested procedure; do not describe this
  as migration-free just because the internal JWT schema is unchanged.

## Revision History

- 2026-10-23: operator approved separating development delivery/version eligibility from
  AAP readiness. R-1–R-6d retain asserting tests and real-Postgres custody proof; OQ-3/R-6e
  move to DI-070 before production target enablement. Pinned optional-but-validated endpoint
  behavior and local 60/600-second TTL defaults, retaining mandatory account proof/S256 and
  no fallback/replay. Sequenced a documentation commit for review, then separately reviewable
  contract and foundation increments. No runtime work or release claim; earlier entries intact.
- 2026-10-12: original scaffold approved around provisioning-time per-user consent and
  ADR-0015; no runtime implementation recorded.
- 2026-10-18: revised draft for operator-agreed first-use redirects/no settings UI, encrypted
  Postgres, expanded product scope, and failure-first gates. Target profile and detailed
  handoff contract still pending; no runtime, deployment, commit, or release claim.
- 2026-10-18 (ratification): operator approved the amended direction; ADR-0016 accepted and
  ADR-0015 superseded, spec `draft` → `approved`. OQ-7 handoff contract is the next
  deliverable and a pre-runtime gate; OQ-3 target facts remain a pre-live gate. No runtime
  code, deployment, commit/push, or version bump authorized by this approval.
- 2026-10-18 (OQ-7 draft): authored the detailed first-use authorization handoff contract
  ([oq7-first-use-handoff-contract.md](oq7-first-use-handoff-contract.md)) from the shipped
  call chain, marked **proposed / pre-runtime gate**. Enumerated the additive shared-contract,
  product, and audit surfaces and the failure-first negative tests; left TTL/PKCE values
  flagged **[OQ-3]**. Documentation only — no runtime change, no OQ-7 ratification, and no
  commit/push, deployment, or version bump.
- 2026-10-19 (OQ-7 ratification): the operator **ratified** the OQ-7 detailed first-use
  handoff contract, closing the pre-runtime design gate — R-1..R-6 implementation may now
  begin against it. The banner, Gate 0, the contract-boundary section, and Sequencing step 1
  were reconciled; the contract's two **[OQ-3]** value/fact items (numeric TTLs, PKCE
  enforcement) stay pinned to the still-open OQ-3 pre-live gate. Documentation only — no
  runtime change, commit/push, deployment, or version bump.
