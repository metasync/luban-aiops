# SPEC-070: Outbound User-Delegated Execution Identity (Tool-Gateway Substrate)

## Status

- status: `approved` — amended redirect-based direction ratified 2026-10-18; the OQ-7
  detailed handoff contract was **ratified 2026-10-19**, closing the pre-runtime design
  gate. R-1..R-6 implementation may now begin against that contract. Approval + ratification
  do not authorize runtime code that depends on the still-open OQ-3 deployment facts (which
  pin the contract's **[OQ-3]** TTL/PKCE values), live target tests, deployment, commit/push,
  or a version bump.
- owner: luban-platform-team
- created: 2026-10-12
- current decision: first-use target OAuth authorization redirects are allowed; no manual
  credential entry, enrollment command, or credential-settings UI. Later acquisition uses
  server-to-server renewal; revoked/expired grants may require another authorization.
- remaining gates: **OQ-7** (detailed cross-product handoff contract) is **ratified
  2026-10-19** — the pre-runtime design gate is closed and R-1..R-6 may begin against it.
  **OQ-3** (exact AAP release/MCP build, client/PKCE/renewal/lifecycle profile, identity
  binding) is now the sole open gate — a pre-live gate supplied by the operator/admin, which
  also pins the contract's two **[OQ-3]** value/fact items (numeric TTLs, PKCE enforcement).
  See the [compatibility update](compatibility-report.md#redirect-based-reassessment-2026-10-18).
- superseding ADR: [ADR-0016](../../adr/0016-just-in-time-outbound-oauth-authorization.md)
  (**accepted** 2026-10-18) records the first-use workflow and encrypted Postgres custody.
  [ADR-0015](../../adr/0015-outbound-user-delegated-identity-via-per-user-oauth.md) is now
  `superseded by ADR-0016`; its accepted body is unchanged.
- release slice: **R6-enabling substrate** — the *user-delegated* form of the outbound
  External Execution Identity that the MCP-ingestion pilots need for production
  attribution. Extracted from
  [SPEC-069](../SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) OQ-4 so it can
  be shaped independently of any single pilot's live-system gate, mirroring how
  [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) was extracted
  from [SPEC-067](../SPEC-067-servicenow-mcp-ingestion-pilot/spec.md) R-1. SPEC-069's
  read-only **dev** slice is **not** blocked on this spec (it validates against a
  self-hosted server's own auth); only the **production** user-delegated path depends on
  it (see the [delivery roadmap](../../agentic-aiops-platform/delivery-roadmap.md#r6-external-system-integration-via-mcp-ingestion)).
- target version: **v0.50.0** — re-slotted from v0.49.0 at SPEC-067's 2026-10-20
  approval (SPEC-067 took the v0.49.0 slot as R6's next slice); still a retained
  planning target from the 2026-10-12 approval, not a delivery commitment while OQ-3
  remains open (OQ-7 was ratified 2026-10-19). SPEC-068 shipped at v0.47.0; SPEC-069's
  read-only **dev** slice shipped at v0.48.0 without this substrate; SPEC-067 targets
  v0.49.0. The `VERSION` file remains unchanged; release/version changes require
  separate approval.
- related ADRs: [ADR-0016](../../adr/0016-just-in-time-outbound-oauth-authorization.md)
  (**accepted** 2026-10-18, supersedes [ADR-0015](../../adr/0015-outbound-user-delegated-identity-via-per-user-oauth.md)).
  This spec establishes the platform's **first outbound
  user-delegated identity** — carrying a human subject's identity and authority across the
  platform boundary to an external system that enforces its own RBAC on that user. That is
  a **trust-model change** of the same weight as
  [ADR-0004](../../adr/0004-broker-mediated-token-delegation.md), which established
  *inbound/internal* delegation, so — unlike SPEC-068's **target-issued, user-less**
  `client_credentials` shape — it is **not** ADR-free. ADR-0015 recorded the resolved
  decision (retained by ADR-0016): **per-user OAuth 2.x authorization-code, resolved
  connector-locally** against
  the target's own token endpoint (a **target-issued, user-bound** token), with **no
  identity-broker mint** (OQ-2) and a new **user-scoped credential store** as the
  principal new trust surface. It reuses ADR-0004's inbound `sub` (which supplies the user
  subject used to look up that user's refresh token) without changing it.
- lineage: extracted from
  [SPEC-069](../SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) OQ-4 (operator
  direction 2026-10-11: keep **user-delegated identity all the way to the targets** as the
  safest AI-governance default, so the agent never acts toward a target on its own
  service identity). Anticipated by
  [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) Non-Goals (which
  deferred every scheme beyond `basic`/`bearer`/`oauth2_client_credentials`, and named
  the inbound machine-consumer plane as still-parked) and by the
  [identity model](../../agentic-aiops-platform/identity-and-authorization-design.md)
  §Service Identity Model / §External Execution Identity (Principle 2 "the human actor
  must remain attributable", Principle 3 "identity must flow end to end", Principle 5
  "service identity and human identity are different"). **Extends SPEC-068 additively** —
  the same `credential_set` mechanism
  ([SPEC-049 R-5](../SPEC-049-browser-web-check-tools/spec.md)) and the same outbound
  auth-resolution seam
  ([SPEC-058](../SPEC-058-http-service-check-tools/spec.md)'s `http_connector`, generalized
  by SPEC-068 R-3), extended to carry a user subject.

> **Approval history and current authorization.** The full scaffold was approved
> on 2026-10-12 with ADR-0015's target-issued authorization-code mechanism. On 2026-10-18
> a stricter zero-additional-redirect requirement reached a documented Gate 0 no-go on
> available evidence. The operator subsequently agreed to first-use authorization redirects
> without credential settings, and on 2026-10-18 ratified the amended direction: ADR-0016
> is **accepted**, ADR-0015 is **superseded**, and this spec is **approved**. Approval
> authorized the OQ-7 detailed-contract design, which was subsequently **ratified
> 2026-10-19** — closing the pre-runtime gate so R-1..R-6 implementation may begin against
> it. Live target work still waits for the OQ-3 deployment facts (which also pin the
> contract's **[OQ-3]** TTL/PKCE values). The dated changelog preserves the original
> approval; the attached kickoff plan is not edited.

## Summary

Extend the tool-gateway's outbound credential model so a connector can act **as the
requesting user** at an external target — not merely as a platform service account.
SPEC-068 shipped the outbound plane but only with a **machine** grant
(`oauth2_client_credentials`), which carries **no user subject**; an external system such
as Red Hat AAP (whose MCP server uses "dual-layer auth inheriting user RBAC") would see a
shared service identity, losing per-user attribution and letting the agent act with the
service account's full authority regardless of which operator asked. SPEC-070 adds a
**user-delegated** credential form and threads the requesting user's subject (already
present inbound via the ADR-0004 delegated token) into outbound credential acquisition, so
the target-issued token is **bound to the user** and the target enforces **its own** RBAC.
The change is **additive and target-agnostic**: every existing SPEC-068 scheme is
byte-for-byte unchanged, and the concrete grant mechanism — resolved by OQ-1 to
**per-user OAuth 2.x authorization-code** (connector-local, target-issued; ADR-0015) —
extends the same `credential_set` seam rather than replacing it.

## Motivation

- **The operator's AI-governance directive makes this the safest default.** SPEC-069 OQ-4
  resolved (2026-10-11) that user-delegated identity should run "all the way to the
  targets … to avoid the agent performing inappropriate decisions on its own identity."
  A shared service account at the target is exactly the confused-deputy risk
  [ADR-0004](../../adr/0004-broker-mediated-token-delegation.md) was written to prevent
  *internally*; SPEC-070 is its outbound-to-external-target analogue.
- **SPEC-068 deliberately stopped short of this.** Its outbound token is
  `client_credentials` — a machine grant with no user subject — and its Non-Goals deferred
  "OAuth2 authorization-code" and any user-delegated form "until a named target requires
  one." AAP is that named target: its MCP server inherits the requesting user's RBAC, so
  a production Ansible integration that cannot carry the user would either (a) act with a
  service account's blanket authority or (b) not enforce per-user scope at the target at
  all. Both contradict Principles 2/3/5 of the identity model.
- **Why a standalone substrate rather than a SPEC-069 requirement.** The capability is
  reusable across all three R6 ingestion pilots (ServiceNow → Ansible → Windows) and is
  independent of any one target's live gate. Bundling a cross-cutting identity/trust change
  into a read-only pilot would inflate it and stall the shared seam behind one pilot's
  timeline — the same reasoning that produced the
  [SPEC-068 ← SPEC-067 extraction](../SPEC-068-outbound-execution-credential-schemes/spec.md).
  SPEC-069 dev-validates against a self-hosted server's own auth meanwhile, so its
  read-only slice ships without waiting on this spec.
- **Why redirect-based OAuth is the selected direction.** AAP 2.6 and 2.7 document
  authorization-code authentication; this avoids relying on a specialized target token
  exchange. It is not a universal compatibility guarantee. The actual deployment's
  client security, renewal, identity mapping, and revocation behavior still need evidence.
- **No settings UI is not zero interaction.** First-use and reauthorization redirects may
  show target login/consent. Existing SSO may remove a password prompt, but not necessarily
  consent. Only targets needed for a user's authorized operation are connected; normal
  Luban login does not enroll the user into every configured target.

## Requirements

The amended direction is **target-issued authorization-code plus server-side renewal**.
The criteria below are the ratified acceptance obligations for this approval; none is
shipped behavior yet, and each maps to a planned (not run) test in the task matrix.

### R-1: User-delegated outbound credential scheme (extends SPEC-068 additively)

Add `oauth2_authorization_code` to the existing named credential-set parser.

Acceptance criteria:

- **R-1a:** Existing `basic`, `bearer`, `oauth2_client_credentials`, and omitted-scheme
  parsing/projection/resolution remain unchanged. No delegated set means no new behavior.
- **R-1b:** Require operator-configured authorization/token endpoints, target identity and
  allowed resource destinations, confidential-client authentication, exact callback URI,
  permitted/requested scopes, PKCE security profile, and store reference. The target's
  verified profile determines renewal/revocation and identity-resolution endpoints. Do not
  require an OIDC discovery endpoint from an OAuth-only provider.
- **R-1c:** Reject incomplete, unsupported, untrusted, or over-scoped configuration before
  token acquisition or target connection. Warnings contain safe failure classes, never
  submitted values. Model/tool arguments cannot select endpoints, trust, or user identity.

### R-2: User-bound acquisition and authorization-required workflow

Thread gateway-verified identity through both HTTP and the existing MCP adapter. Target
code redemption and renewal belong to a separate user-delegated client in tool-gateway;
keep the existing machine-grant client unchanged.

Acceptance criteria:

- **R-2a:** Key lookup/cache by trusted identity namespace and subject, credential set,
  target/audience, scope, and configuration/credential generation. Two users and two
  targets cannot share credentials. Bounded expiry and single-flight apply to acquisition;
  durable rotation is coordinated across processes.
- **R-2b:** Missing/expired/revoked authorization produces a typed authorization-required
  outcome before opening a target session. Missing identity, bad configuration, store
  failure, and transient target failure remain distinct errors, not authorization loops.
- **R-2c:** For an authorized operation needing credentials, the portal explains the target
  authorization and initiates a standard top-level redirect. No settings screen, manual
  token entry, enrollment helper, or enrollment of unrelated targets. Provider login or
  consent may appear. Cancellation/expiry is visible and does not repeatedly redirect.
- **R-2d:** Return the user to the same owned conversation with a verified completion or
  refusal status. OAuth completion never dispatches an operation itself. Continuing a read
  uses fresh authorization checks; a write remains behind existing HITL, signed-request,
  and durable-claim checks. Never replay an already attempted/uncertain write or treat
  OAuth consent as mutation approval. Resume details must be ratified before implementation.
- **R-2e:** Subsequent calls renew server-to-server under the verified target contract.
  Unsupported renewal is reported explicitly; no fabricated refresh token or PAT fallback.
  Target credentials never reach the model, kernel state, transcript, or browser storage.

### R-3: Target trust, callback security, and per-user RBAC

The target must register Luban as a confidential OAuth client and issue credentials for
its own user account. SSO may simplify the provider login but does not replace this grant.

Acceptance criteria:

- **R-3a:** Use HTTPS endpoints and exact registered callback URIs. Bind short-lived,
  single-use state to the initiating authenticated user/browser session, target, scope,
  configuration generation, and approved local return location. Require PKCE S256 in the
  proposed baseline; unverified/unsupported provider behavior blocks that target rather
  than silently disabling PKCE. Reject login CSRF, state/code replay, issuer mix-up,
  wrong-session callbacks, arbitrary return URLs, and verifier mismatch.
- **R-3b:** Link the target's verified immutable account identity to the requesting Luban
  identity using trusted federation evidence or an administrator-controlled mapping. Token
  possession or equal usernames/emails is not sufficient. Reject authorization under a
  different target account; any ID token used for evidence is validated for issuer,
  audience, signature, and nonce. OAuth-only targets need a verified identity endpoint.
- **R-3c:** Luban policy and target RBAC must both allow the operation. Group-to-role mapping
  is configured separately in each system. No target-role synthesis or admin impersonation.
- **R-3d:** Bind credentials to the configured target/resource destinations, including HTTP
  redirects and MCP sessions. Another generally allowlisted origin cannot receive them.
  Token endpoint redirects must not forward client credentials to an untrusted endpoint.
- **R-3e:** Pin access/refresh lifetimes, target revocation, account-disable and group-removal
  behavior, and maximum local cache/config invalidation delays. Test those limits; SSO
  logout or a group-name change is not a guarantee of immediate target-token revocation.

### R-4: End-to-end attribution fidelity

Preserve separate requester `sub`, acting service, target identity, and signed-execution
correlation; derive delegated attribution from verified acquisition context.

Acceptance criteria:

- **R-4a:** Distinguish verified user delegation from machine credentials and from a pending
  or failed authorization. A configured mode label is not proof of success. Record safe
  authorization/renewal/refusal outcomes without credentials or browser transaction secrets.
- **R-4b:** Delegation mode is queryable through the durable audit API, with an asserting
  round-trip/filter test. Include any additive audit schema/filter changes in approval.
- **R-4c:** Attribution survives redaction overflow and signed execution. Risk tiers,
  one-HITL-gate-per-flow, and durable execution safety remain unchanged.

### R-5: Secret handling, fail closed, and no downgrade

Acceptance criteria:

- **R-5a:** Target access tokens stay memory-only; durable refresh tokens exist only as
  authenticated ciphertext in the R-6 store. Client secrets and PKCE verifiers remain
  server-side. Authorization codes necessarily traverse the provider-to-callback browser
  redirect, but are immediately consumed/removed from the URL, never exposed to portal JS,
  referrers, logs, traces, evidence, or transcripts. State/verifiers receive equivalent
  protection; callback responses use no-store and a restrictive referrer policy.
- **R-5b:** Inject identifiable opaque secrets into URLs, headers, errors, token responses,
  results, logs, traces, evidence, and audit. Assert non-disclosure, including edge access
  logs. Existing vocabulary is not assumed sufficient for arbitrary values or OAuth codes.
  Keep `make validate-secret-vocabulary` green; report and fix proven coverage gaps.
- **R-5c:** On any delegated failure, assert zero calls to Basic, bearer, machine-grant,
  unauthenticated, or alternate-transport fallback paths. Cover HTTP, MCP invocation,
  diagnostics, and unsupported stdio/non-bearer paths.
- **R-5d:** Invalid callback, missing identity, unavailable/wrong encryption key, unavailable
  store, timeout, malformed token response, and revoked grant fail closed. No target
  session opens after failed acquisition; cancellation grants no execution authority.

### R-6: Provisioning and durable credential custody

Use gateway-owned tables and a dedicated database role on existing Postgres infrastructure,
with application-level authenticated encryption and separately mounted versioned keys.

Acceptance criteria:

- **R-6a:** Bind encrypted records to trusted owner namespace/subject, target, credential
  set, and configuration generation; retain verified target account identity. Substituting
  ciphertext between owners/targets fails. No plaintext file or machine-credential fallback.
- **R-6b:** Rotation, local revocation, configuration removal, and cache invalidation work
  across replicas. Real disposable-Postgres tests cover concurrency, restart, key rotation,
  revoked-record resurrection, and refresh/revocation races. If the provider rotates a
  refresh token but the response/commit is lost, fail closed into reauthorization; do not
  claim an atomic transaction spanning the provider and Postgres.
- **R-6c:** Reuse `credential-sets.json` and `sync-browser-credentials.sh` for operator
  target/client configuration. Provision database/key mounts and least-privilege network
  access through GitOps; delegated mode stays disabled until configured. No user secrets
  in env literals, Git, or configuration examples; `make overlays` must pass.
- **R-6d:** Document client registration, first-use/reauthorization UX, cancellation, key
  rotation, backup/recovery, local and target revocation, offboarding, rollback, and group
  synchronization limits in existing operator guides. A local disconnect prevents use
  immediately under the documented cache contract; target revocation failure is visible.
- **R-6e:** Separately authorized live proof uses the actual approved AAP/MCP target and two
  users with distinct RBAC: first-use redirects, later renewal without another prompt,
  wrong-account rejection, denied operation, disablement/group removal, restart, and
  configuration removal. Deterministic mocks prove protocol handling, not AAP compatibility.

## Non-Goals

- **The inbound machine-consumer `client_credentials` grant / stable-API productization.**
  Still the parked, trust-model-blocked plane (no human owner/approver; it needs a
  machine-*subject* token the identity-broker cannot mint — see the
  [credential memo](../../workspace/machine-consumer-credential-model-spike.md) §5).
  SPEC-070 is strictly the **outbound user-delegated** plane.
- **New target tools or a new MCP transport.** Reuse SPEC-069's shipped adapter for
  identity threading; no new MCP dependency or connector. ServiceNow and Windows remain
  separate pilots. AAP is the first compatibility profile, not proof of every target.
- **Changing internal ADR-0004 delegation or upstream SSO custody.** No outbound broker
  mint and no forwarding of internal Luban JWTs. The target authorization code supplies
  the outbound credential, so this design does not retain/reuse the Keycloak login token.
- **Authority elevation or role synthesis.** The outbound token never exceeds the user's
  target-side authority; mapping platform roles to target RBAC is the target's job, not a
  platform translation layer.
- **Kubernetes workload identity (SPEC-068's Option C).** It remains the documented
  *upgrade path* for the External Execution Identity, appropriate under cluster-to-cluster
  trust; it is not this spec's mechanism.
- **New write tools or execution approval authority.** Authorization UI is not a HITL
  mutation gate. Risk tiers, one-gate-per-flow, signed execution, and durable claims keep
  their safety semantics; no automatic write retry is introduced.
- **Alternative credential mechanisms.** RFC 8693, OBO, password/implicit grants, PAT/manual
  provisioning, shared-service fallback, and administrator impersonation are excluded from
  this slice. Target SSO may assist login but is not the outbound credential mechanism.

## Impact

- **Tool-gateway:** credential parsing, a separate user-delegated client, HTTP/MCP identity
  threading, authorization transaction/credential storage, account binding, and attribution.
- **Platform-gateway and operator-portal:** authenticated first-use initiation, backend
  callback forwarding, owner-scoped status/return handling, and minimal authorization
  feedback in the existing workflow. No credential-settings screen or target tokens in JS.
- **Agent-platform / shared contracts:** bounded authorization-required signaling and safe
  stop/continue integration are in scope for design. The existing tool-result error object
  admits only `code`/`message`; it is not an existing structured authorization handoff.
  Pin the additive contract, persistence, and resume semantics before approval. Do not claim
  the kernel is untouched until that call-chain design is proven.
- **Audit-service / query contracts:** an additive delegation-mode filter/schema change if
  needed to meet R-4b; record the exact impact in the revised approval checkpoint.
- **Identity-broker:** no planned code or upstream login-custody change. Its existing
  verified internal subject is reused; no new outbound signing authority or identity-token
  claim/audience class. This boundary must remain explicit in the final contract design.
- **Infrastructure:** gateway-owned Postgres tables/role, authenticated encryption/key
  mounts, migrations, and credential/config generation invalidation across replicas.
- **ADR:** [ADR-0016](../../adr/0016-just-in-time-outbound-oauth-authorization.md)
  (**accepted** 2026-10-18) retains ADR-0015's mechanism but replaces provisioning-only
  enrollment, the PAT option, and its blanket no-kernel-change assumption with the scoped
  first-use design. ADR-0015 is now `superseded by ADR-0016`; its accepted body is unchanged.
- **Delivery documentation:** update existing identity, architecture, configuration,
  troubleshooting, tool-gateway, and operator guides only when behavior is implemented.
  Spec/ADR indexes and R6 roadmap reflect this approval now; release/version is unchanged.

## Open Questions

The operator has resolved the UX direction, approved this amended spec, and **ratified the
OQ-7 detailed contract (2026-10-19)** — the pre-runtime design gate is closed; the
deployment facts are not yet supplied. OQ-3 is now the sole open gate — a **pre-live** gate
(deployment facts before target tests/deployment), which also pins the two **[OQ-3]**
value/fact items the ratified contract flags. Live acceptance remains a separately authorized
delivery gate. The [report update](compatibility-report.md#redirect-based-reassessment-2026-10-18)
distinguishes documented support from missing organization-specific evidence.

- **OQ-1 — resolved (direction ratified 2026-10-18):** target authorization-code, first-use
  and reauthorization redirects allowed; no credential settings, manual tokens, or CLI helper.
  Consent is not necessarily once forever. Subsequent renewal is server-to-server.
- **OQ-2 — resolved:** no outbound broker mint, no upstream Keycloak-token custody change,
  and no internal identity-token schema change. Target-issued credentials remain gateway-owned.
- **OQ-3 — deployment facts OPEN (pre-live gate):** exact AAP release/patch and MCP build;
  configured
  confidential-client authentication, callback, PKCE S256 support/enforcement, scopes,
  refresh issuance/rotation/revocation, lifetimes, external-user token setting, target
  identity endpoint/linkage, and group/RBAC lifecycle. AAP 2.6 documents explicit endpoints
  and says PKCE is **not enforced**, not that it is unsupported; 2.7 defaults new apps to
  PKCE but migrates existing apps with it disabled. Neither documents this installation.
  Keycloak's version/SSO mappings matter for login behavior, not for token-exchange features.
- **OQ-4 — storage selection agreed:** existing Postgres, gateway-owned tables/role,
  application-level authenticated encryption, and separately mounted keys. Rotation,
  revocation, transaction custody, and cross-replica invalidation must meet R-6 gates.
- **OQ-5 — validation direction corrected:** deterministic OAuth mocks for protocol tests,
  real disposable Postgres for custody, and actual approved AAP/MCP for live compatibility.
  Keycloak plus AWX is not assumed protocol-equivalent; the deployed shared-bearer mock
  proves neither OAuth nor per-user RBAC.
- **OQ-6 — retained as asserting test obligations:** no elevation, no shared-account
  fallback, no credential leakage, and no mutation replay/bypass after authorization.
- **OQ-7 — cross-product contract RATIFIED 2026-10-19 (pre-runtime gate closed):** the
  detailed contract — initiation/callback/status endpoints, browser-session binding, typed
  authorization-required signaling, owner-only persistence, exact return/continue semantics,
  and audit-query fields — is written in
  [OQ-7: First-Use Authorization Handoff](oq7-first-use-handoff-contract.md), grounded in the
  shipped secret-delivery, HITL, stream-v12, tool-result, gateway-routing, and audit seams.
  The operator **ratified** it on 2026-10-19, closing the pre-runtime design gate: R-1..R-6
  implementation may now begin against the contract. Two items inside it stay **[OQ-3]-gated**
  value/fact pins — numeric TTLs and PKCE enforcement — to be filled when the OQ-3 deployment
  facts arrive; they are not open design decisions and do not hold the gate. These were new
  design decisions beyond the original connector-only assumption, tracked in accepted ADR-0016
  and the plan.

## Changelog

- 2026-10-20 (planning-target re-slot): SPEC-067's approval pinned its target version to
  **v0.49.0** (R6's next slice after SPEC-069's delivered v0.48.0), so this spec's
  retained planning target re-slots **v0.49.0 → v0.50.0** to keep the two R6 tracks on
  distinct minor versions. A **planning-target annotation only** — no delivery
  commitment, no `VERSION` change (still 0.48.0), and no effect on OQ-3 (the sole
  pre-live gate) or on the 2026-10-12 approval's substance. The 2026-10-12 entry below
  keeps its as-written v0.49.0 pin (a historical record, not re-edited).
- 2026-10-19 (OQ-7 ratification): the operator **ratified** the OQ-7 detailed first-use
  handoff contract ([oq7-first-use-handoff-contract.md](oq7-first-use-handoff-contract.md)),
  closing the pre-runtime design gate — R-1..R-6 implementation may now begin against it.
  The contract's status banner flipped PROPOSED → RATIFIED; the spec/plan/tasks/index/roadmap/
  compatibility surfaces were reconciled to name OQ-7 ratified and OQ-3 as the sole open
  gate. Items §13.1–13.2 (numeric TTLs, PKCE enforcement) remain **[OQ-3]-gated** value/fact
  pins; OQ-3 stays the pre-live gate. Ratification authorizes no runtime code that depends on
  OQ-3, no live target test, deployment, commit/push, or version bump.
- 2026-10-18 (OQ-7 draft): authored the detailed cross-product first-use authorization
  handoff contract ([oq7-first-use-handoff-contract.md](oq7-first-use-handoff-contract.md))
  from the shipped call chain, marked **proposed / pre-runtime gate**. It pins the typed
  authorization-required signal, stream v13 projection, owner-scoped single-use handles,
  portal + internal routes, replica-safe transaction persistence, bounded-stop/new-turn
  continue semantics, and a top-level `delegation_mode` audit field, and enumerates every
  additive contract surface. OQ-7 remains open pending operator ratification and the OQ-3
  values it flags; no runtime code, live target test, deployment, commit/push, or version
  bump is authorized by this entry.
- 2026-10-18 (ratification): operator approved the amended redirect-based direction.
  ADR-0016 moved `proposed` → `accepted`; ADR-0015 → `superseded by ADR-0016` (accepted body
  unchanged); this spec `draft` → `approved`; ADR/spec indexes and the R6 roadmap reconciled.
  Approval authorizes the OQ-7 detailed-contract design and decision-complete implementation
  to begin. OQ-7 remains a pre-runtime gate and OQ-3 a pre-live gate; no runtime code,
  live target test, deployment, commit/push, or version bump is authorized by this entry.
- 2026-10-18: operator agreed to first-use/reauthorization redirects without credential
  settings or manual enrollment, following the zero-redirect Gate 0 no-go. Reopened as
  `draft` for the amended approval checkpoint; retained target-issued authorization-code
  and no outbound broker mint, selected encrypted gateway-owned Postgres, and expanded
  scope to portal/platform-gateway authorization handling and safe agent workflow signaling.
  Added R-1a–R-6e traceable criteria, corrected the in-memory-token/refresh-persistence
  contradiction, removed stale broker/PAT alternatives from this slice, and separated
  documentation support from deployment proof. Proposed ADR-0016; ADR-0015 and the attached
  kickoff plan remain unchanged. Production versions/security/renewal facts and detailed
  cross-product contract ratification still gate runtime work; no release/version change.
- 2026-10-12: created as `draft`; full scaffold (`spec.md` + `plan.md` + `tasks.md`)
  authored together per the SPEC-064..069 precedent. Extracted from
  [SPEC-069](../SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) OQ-4 (operator
  direction 2026-10-11: user-delegated identity all the way to the targets). Records the
  trust-model finding that an **ADR-0015 is expected** (the platform's first outbound
  user-delegated identity) but **not drafted** because its decision turns on OQ-1
  (mechanism) and OQ-2 (broker-minting). **OQ-1 and OQ-2 block `approved`**; the spec is
  not decision-complete. Extends SPEC-068 additively; no implementation, commit/push,
  deployment, or version bump authorized.
- 2026-10-12: **approved** (operator). OQ-1 resolved to **(c) per-user OAuth 2.x
  authorization-code, connector-local**; OQ-2 to **no identity-broker mint**; OQ-3 answered
  by research (Red Hat AAP's MCP server accepts per-user auth-code / PATs and inherits user
  RBAC, with no OIDC discovery / token-exchange / OBO in 2.6).
  [ADR-0015](../../adr/0015-outbound-user-delegated-identity-via-per-user-oauth.md) drafted
  and **accepted**; target version pinned to **v0.49.0**. R-1 fields, the R-3 trust
  contract, and R-6/OQ-4 (the user-scoped credential store) are pinned to the chosen
  mechanism and **in scope**; `identity-token.schema.json` is **unchanged** and the
  identity-broker is **not** touched. Requirements body, Non-Goals, Impact, and Open
  Questions updated from mechanism-agnostic to mechanism-specific. Per the SPEC-066/069
  precedent, approval **authorizes implementation to begin**; commit/push, deployment, and
  any version bump remain separate boundaries **not** granted here.
