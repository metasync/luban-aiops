# SPEC-070: Outbound User-Delegated Execution Identity (Tool-Gateway Substrate)

## Status

- status: `draft`
- owner: luban-platform-team
- created: 2026-10-12
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
- target version: **not pinned** — pinned at approval, which is a separate gate not
  crossed by this `draft`.
- related ADRs: **ADR-0015 expected (provisional; not yet drafted).** This spec
  establishes the platform's **first outbound user-delegated identity** — carrying a
  human subject's identity and authority across the platform boundary to an external
  system that enforces its own RBAC on that user. That is a **trust-model change** of the
  same weight as [ADR-0004](../../adr/0004-broker-mediated-token-delegation.md), which
  established *inbound/internal* delegation. It is therefore **not** ADR-free the way
  SPEC-068 was: SPEC-068 acquired a **target-issued, user-less** `client_credentials`
  token connector-locally (no new signing authority, no user subject, no new trust
  behavior — just a new credential *shape*). Every candidate mechanism here instead
  either (i) federates a user assertion outbound, (ii) adds a broker-minted outbound
  token, or (iii) adds a per-user credential store. The ADR's exact decision text turns
  on **OQ-1** (mechanism) and **OQ-2** (whether the identity-broker mints anything new),
  so it is **deliberately not drafted yet** — an ADR records a *decision*, and the
  decision is still open. SPEC-070 stays `draft` until both resolve.
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

> **Approval note (SDD discipline).** The full scaffold (`spec.md` + `plan.md` +
> `tasks.md`) is authored together per the SPEC-064/065/066/067/068/069 same-session
> precedent. **Unlike SPEC-068** (which was target-agnostic *and* decision-complete, with
> no Open Question blocking `approved`), SPEC-070 carries a **central blocking Open
> Question** — OQ-1, the delegation mechanism — plus OQ-2 (the ADR scope it determines).
> It is **not** decision-complete and is **not** approvable as drafted. Drafting it now
> lands the substrate's *shape* and the trust-model finding so SPEC-069 R-1 can name a
> real dependency instead of "a follow-up substrate (number assigned at drafting)";
> **approval is a separate, later gate** that requires the operator to pick the mechanism
> (informed by the OQ-3 AAP Stage-0 fact). No implementation, commit/push, deployment, or
> version bump is authorized by this `draft`.

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
byte-for-byte unchanged, and the concrete grant mechanism (token exchange / OBO / per-user
OAuth / shared-IdP SSO) is the central Open Question, not a drafting assumption.

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
- **Why it is not decision-complete.** The mechanism is a genuine fork with different
  trust-federation, storage, and ADR consequences (OQ-1), and the first production
  target's actual acceptance is a live fact (OQ-3, like SPEC-067 OQ-1 / SPEC-069 OQ-1).
  This spec therefore records the *shape* and the invariants that hold under **any**
  mechanism, and leaves the mechanism to an operator decision rather than guessing one.

## Requirements

Each requirement is written to hold under **any** OQ-1 mechanism; mechanism-specific field
names, grant types, and trust config are pinned only once OQ-1/OQ-2 resolve. Requirements
are stable once the spec is `approved` and will then carry testable acceptance criteria.

### R-1: User-delegated outbound credential scheme (extends SPEC-068 additively)

Add a **user-delegated** scheme to the `credential_sets` vocabulary
(`products/tool-gateway/src/tool_gateway/tools/credential_sets.py`) alongside SPEC-068's
`basic` | `bearer` | `oauth2_client_credentials`, carrying the target-side configuration
needed to obtain a **user-bound** token (e.g. the target's token-exchange/OBO endpoint and
the platform's client credential at that endpoint). The exact scheme name and required
fields are **OQ-1-dependent** and are not fixed here.

Acceptance criteria (mechanism-agnostic):

- Every existing SPEC-068 set (`basic`, `bearer`, `oauth2_client_credentials`, and a set
  with no `scheme` key) parses **byte-for-byte** as it does post-SPEC-068; the user-
  delegated scheme is inert until such a set is provisioned.
- A user-delegated set declares the target endpoint + platform client credential needed
  for the chosen grant; the specific `grant_type`/fields are pinned by OQ-1. An unknown
  scheme, or a set missing its scheme's required fields, is ignored with a
  `LOGGER.warning` and **never** admitted half-formed (reusing SPEC-068 R-1's fail-closed
  parser).
- The scheme is **platform configuration** resolved by name at call time (never
  model-supplied), riding the same file-mounted secret as SPEC-068 R-5.

### R-2: User-subject threading into outbound acquisition

The connector must carry the **requesting user's** subject — already available inbound as
the ADR-0004 delegated token (`sub` = user, `act` = service, `aud` = tool-gateway) — into
the outbound credential acquisition, so the target-issued token is bound to that user
rather than to a shared service account. This extends SPEC-068 R-3's outbound
auth-resolution seam (`products/tool-gateway/src/tool_gateway/tools/auth_resolution.py`)
to accept the request's user-identity context.

Acceptance criteria:

- For a user-delegated set, outbound acquisition uses the **request's** user identity as
  the delegation subject; the resulting target token represents that user, not the
  platform.
- A call whose user subject cannot be resolved **fails closed** with a structured gateway
  error — it **never** silently substitutes a service/machine credential (see R-5's
  no-downgrade invariant).
- The user's authority is **never elevated**: the outbound token can carry at most the
  authority the user holds at the target, mirroring `exchange_service.exchange_token`'s
  invariant that roles are "copied verbatim … the exchange can never grant authority the
  subject token lacks." Role/authority mapping to the target's RBAC is the **target's**
  decision, not the platform's.
- `basic` / `bearer` / `oauth2_client_credentials` resolution is unchanged behind the
  extended seam (no behavior change to SPEC-068's paths).

### R-3: Trust-boundary / federation contract

Define what the external target's authorization server must trust for the delegation to
succeed, and fail closed when that trust is absent. The concrete prerequisite is
**OQ-1/OQ-2-dependent** (a federated platform issuer the target IdP trusts; a per-user
consent/registration at the target; or a shared enterprise IdP per the identity model's
Keycloak + AD stack).

Acceptance criteria:

- The mechanism's trust prerequisite is **explicit configuration** (never auto-negotiated,
  mirroring SPEC-068's explicit `client_auth` variant), so a misconfiguration cannot send
  a user assertion to a target that does not trust it.
- A missing/broken federation or consent fails closed with a structured gateway error —
  never an unauthenticated call and never a fabricated user assertion.
- The platform never asserts a user identity to a target that is not configured to trust
  that assertion; the set of trusted outbound targets is operator-provisioned.

### R-4: End-to-end attribution fidelity

Audit must record both the human subject and the fact that the outbound call was
**user-delegated** (as opposed to service-account), so a target-side action is attributable
end to end (identity model Principles 2/3/5; ADR-0004's separate `sub`/`act` attribution).

Acceptance criteria:

- An outbound user-delegated call produces an audit trail linking the platform user subject
  to the identity used at the target, distinguishable from a SPEC-068 service-account call.
- The delegation **mode** (user-delegated vs service-account) is a queryable audit
  dimension; no token, secret, or credential value surfaces in audit, evidence, a tool
  result, or a log line (reusing SPEC-068 R-4's invariants and SPEC-009 R-1's
  deterministic redaction).
- Attribution survives the existing durable/signed-execution machinery unchanged; SPEC-070
  adds no new HITL surface and does not alter risk tiering or ADR-0007's one-gate-per-flow.

### R-5: Secret-handling, fail-closed, no-fabrication, and **no-downgrade** invariants

Every secret-bearing value SPEC-070 introduces (a user-delegated access/refresh token, any
per-user credential) is provably covered by the platform's redaction, every failure mode
fails closed, and — the governance crux — a failed user delegation **never** falls back to
a service/machine credential.

Acceptance criteria:

- The existing redaction vocabulary already covers the new values (`url_redaction.
  SECRET_QUERY_PARAMS` substring-matches `token`/`secret`/`credential`;
  `redaction._VALUE_PATTERNS` covers the password/secret/token family plus `client_secret`
  and `authorization`); a test drives a user-delegated token through a URL projection, a
  tool result, an evidence field, and audit and asserts it is masked in each.
  `make validate-secret-vocabulary` stays green **without** a new canonical field set (it
  pins redaction vocabularies, not credential field names).
- A user-delegated token is held **in memory only** — never written to disk, a result,
  evidence, audit, or a log line (only the failure *class* and the set **name** are
  logged), matching SPEC-068 R-2's `oauth_client` handling.
- **No-downgrade:** when user-delegated acquisition fails (no resolvable subject, broken
  federation, token-endpoint failure), the connector **fails closed** — it must **never**
  retry with `oauth2_client_credentials`/`basic`/`bearer` as a silent service-account
  fallback. A test asserts the absence of any such fallback path, because a downgrade would
  violate the OQ-4 directive (the agent acting on its own identity).

### R-6: Provisioning, and (OQ-dependent) per-user credential storage

The **target/client** configuration rides SPEC-068 R-5's existing file-mounted
credential-set model (`credential-sets.json` via `sync-browser-credentials.sh`); no new
platform-config secret mechanism. **If** OQ-1 selects per-user OAuth authorization (stored
per-user refresh tokens), a **new user-scoped credential store** is required — a capability
SPEC-068's platform-config store does not provide — and is scoped by OQ-4.

Acceptance criteria:

- The platform-config half reuses SPEC-068 R-5 verbatim: an operator supplies the
  user-delegated set's target/client config through the existing file-mounted secret; never
  inline env, never committed; `make overlays` renders the dev-k8s wiring green; the
  extension is inert until such a set is provisioned.
- The per-user-storage half (consent capture, refresh-token persistence, rotation,
  revocation) is **deferred to OQ-4** and is explicitly out of this substrate's first slice
  unless OQ-1 forces it; if forced, it is its own reviewed capability, not an ad-hoc file.

## Non-Goals

- **The inbound machine-consumer `client_credentials` grant / stable-API productization.**
  Still the parked, trust-model-blocked plane (no human owner/approver; it needs a
  machine-*subject* token the identity-broker cannot mint — see the
  [credential memo](../../workspace/machine-consumer-credential-model-spike.md) §5).
  SPEC-070 is strictly the **outbound user-delegated** plane.
- **Any specific target connector.** ServiceNow is
  [SPEC-067](../SPEC-067-servicenow-mcp-ingestion-pilot/spec.md); Ansible read-tier is
  [SPEC-069](../SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md); Windows is a
  future pilot. SPEC-070 is target-agnostic: it ships no target connector, no MCP
  client/SDK code, and no `mcp` dependency.
- **Changing the internal ADR-0004 delegation.** The broker's inbound `exchange_token`
  (`sub`/`act`/`aud` for service-to-service hops *within* Luban) is untouched. SPEC-070 is
  the separate outbound plane; whether it needs a *new* broker path is OQ-2.
- **Authority elevation or role synthesis.** The outbound token never exceeds the user's
  target-side authority; mapping platform roles to target RBAC is the target's job, not a
  platform translation layer.
- **Kubernetes workload identity (SPEC-068's Option C).** It remains the documented
  *upgrade path* for the External Execution Identity, appropriate under cluster-to-cluster
  trust; it is not this spec's mechanism.
- **Write-tier tools or any new HITL surface.** SPEC-070 changes only outbound auth
  resolution beneath the tier system; risk tiers, one-gate-per-flow (ADR-0007), signed
  execution (SPEC-037), and durable claims (SPEC-063) are untouched.
- **Building the mechanism before OQ-1 resolves it.** This spec records the shape and the
  under-any-mechanism invariants; it does not pre-commit to token exchange vs OBO vs
  per-user OAuth vs shared-IdP SSO.

## Impact

- products touched: `products/tool-gateway` — `tools/credential_sets.py` (additive
  user-delegated scheme), `tools/oauth_client.py` **or** a new `tools/user_delegated_client.py`
  (the grant, per OQ-1), and `tools/auth_resolution.py` (thread the user subject into the
  seam). **Possibly `products/identity-broker`** *if* OQ-2 selects a broker-minted outbound
  token (a new exchange audience/path) — flagged OQ-dependent, not assumed. **No kernel
  change.** New dependency only if OQ-1's mechanism cannot be a plain `httpx` POST (the
  RFC 8693 / OBO grants can; a per-user OAuth consent flow may need more) — pinned at OQ-1.
- contracts touched: the credential-set secret **file shape** (additive scheme).
  **Possibly** `identity-token.schema.json` *if* OQ-2 mints a new outbound audience/claim
  class, and **possibly** a new user-scoped credential secret *if* OQ-4 requires per-user
  storage — both flagged OQ-dependent. No policy-bundle change (no new tools). No
  secret-vocabulary change (existing redaction already covers the new names).
- identity / policy / audit / execution-safety impact: establishes the platform's **first
  outbound user-delegated identity** — a **trust-model change** (ADR-0015 expected). Audit
  gains a delegation-mode dimension (R-4). Fail-closed, no-fabrication, and the new
  **no-downgrade-to-service-account** invariant (R-5) are preserved. The internal ADR-0004
  `sub`/`act` delegation is unaffected.
- ADR: **provisional ADR-0015** expected; scope set by OQ-2 once OQ-1 picks the mechanism.
  Not drafted at this `draft` stage.
- living state docs to update on delivery: the
  [identity model](../../agentic-aiops-platform/identity-and-authorization-design.md)
  §Service Identity Model / §External Execution Identity (record the user-delegated form
  landing), `products/tool-gateway/README.md` (the credential-scheme surface),
  `docs/guides/architecture-overview.md` (the tool-gateway capability row), the ADR index
  (`docs/adr/README.md`) if ADR-0015 is written, and the delivery-roadmap (mark the
  substrate delivered; note SPEC-069's production path now depends on it).

## Open Questions

**OQ-1 and OQ-2 block `approved`.** SPEC-070 is *not* decision-complete: the delegation
mechanism is a genuine fork with different trust, storage, and ADR consequences, and the
first production target's acceptance is a live fact. The invariants above hold under any
answer; the mechanism-specific fields, grant type, trust config, and ADR text do not exist
until these resolve. Approval, implementation, commit/push, deployment, and any version
bump remain separate authorization boundaries not granted by this `draft`.

- **OQ-1 (CENTRAL, blocks `approved`) — which delegation mechanism?**
  (a) **connector-local OAuth2 Token Exchange (RFC 8693)** at the target's IdP, presenting
  the inbound user token (or a platform user-assertion) as `subject_token`;
  (b) **on-behalf-of** (e.g. an Azure-AD-style OBO flow) with the platform's client
  credential;
  (c) **per-user OAuth authorization-code** with stored per-user refresh tokens (needs R-6's
  user-scoped store + a consent flow);
  (d) **shared-IdP SSO / federation** (the identity model's Keycloak + AD stack), where the
  target already trusts the enterprise IdP and maps the user's groups to its own RBAC.
  Each implies different R-1 fields, a different R-3 trust contract, a different R-6
  storage need, and a different ADR-0015 scope.
- **OQ-2 (blocks `approved`) — does the mechanism require the identity-broker to mint a new
  outbound-facing token?** If yes (a new audience class / signing context), ADR-0015 records
  a *broker-minted outbound user assertion* and `identity-token.schema.json` likely changes.
  If the mechanism can stay **connector-local** — reusing the inbound delegated token as the
  `subject_token` at a target IdP that already trusts the platform issuer — ADR-0015 records
  an *outbound user-delegated federation* and the broker is untouched. Either way an ADR is
  expected (this is the first outbound user-delegated trust); only its scope differs.
- **OQ-3 (Stage-0 live fact) — what does the first production target actually accept?**
  Red Hat AAP's MCP server uses "dual-layer auth inheriting user RBAC"; does it accept a
  federated user assertion, a token-exchanged token, or per-user AAP credentials? This is a
  checkable fact (mirrors SPEC-067 OQ-1 / SPEC-069 OQ-1), not a design decision, and it
  constrains OQ-1.
- **OQ-4 — per-user credential storage.** If OQ-1 selects per-user OAuth (c), where do
  user-scoped refresh tokens live, and how are consent, rotation, and revocation handled?
  SPEC-068's store is platform-config, not user-scoped, so this is a new capability that
  may itself warrant review.
- **OQ-5 — self-contained dev validation.** How is user-delegated outbound identity
  validated without a live external target — a mock IdP supporting token exchange, or a
  self-hosted Keycloak + AWX? Ties to
  [SPEC-069](../SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) OQ-5's
  self-contained in-cluster validation.
- **OQ-6 — authority floor and no-downgrade confirmation.** Confirm the outbound
  user-delegated token can never exceed the user's target-side RBAC (R-2), and that a failed
  delegation fails **closed** with no service-account fallback (R-5) — the governance
  invariant the OQ-4 directive exists to protect.

## Changelog

- 2026-10-12: created as `draft`; full scaffold (`spec.md` + `plan.md` + `tasks.md`)
  authored together per the SPEC-064..069 precedent. Extracted from
  [SPEC-069](../SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) OQ-4 (operator
  direction 2026-10-11: user-delegated identity all the way to the targets). Records the
  trust-model finding that an **ADR-0015 is expected** (the platform's first outbound
  user-delegated identity) but **not drafted** because its decision turns on OQ-1
  (mechanism) and OQ-2 (broker-minting). **OQ-1 and OQ-2 block `approved`**; the spec is
  not decision-complete. Extends SPEC-068 additively; no implementation, commit/push,
  deployment, or version bump authorized.
