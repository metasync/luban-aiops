# SPEC-070: Outbound User-Delegated Execution Identity (Tool-Gateway Substrate)

## Status

- status: `approved`
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
- target version: **v0.49.0** — pinned at approval (2026-10-12). SPEC-068 shipped the
  machine-grant outbound plane at v0.47.0 and SPEC-069's read-only **dev** slice targets
  v0.48.0 **without** this spec; SPEC-070 is the substrate the **production**
  user-delegated path needs, so it lands at the next minor. The `VERSION` file bump itself
  is a separate release gate, crossed neither by approval nor by implementation.
- related ADRs: [ADR-0015](../../adr/0015-outbound-user-delegated-identity-via-per-user-oauth.md)
  (**accepted** 2026-10-12). This spec establishes the platform's **first outbound
  user-delegated identity** — carrying a human subject's identity and authority across the
  platform boundary to an external system that enforces its own RBAC on that user. That is
  a **trust-model change** of the same weight as
  [ADR-0004](../../adr/0004-broker-mediated-token-delegation.md), which established
  *inbound/internal* delegation, so — unlike SPEC-068's **target-issued, user-less**
  `client_credentials` shape — it is **not** ADR-free. ADR-0015 records the resolved
  decision: **per-user OAuth 2.x authorization-code, resolved connector-locally** against
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

> **Approval note (SDD discipline).** The full scaffold (`spec.md` + `plan.md` +
> `tasks.md`) was authored together per the SPEC-064..069 same-session precedent, and
> drafting **deliberately stopped short of approval** because a **central Open Question** —
> OQ-1, the delegation mechanism — plus OQ-2 (the ADR scope it determines) blocked
> `approved`. **Both are now resolved by operator direction (2026-10-12):** OQ-1 →
> **(c) per-user OAuth 2.x authorization-code**, informed by the OQ-3 fact that Red Hat
> AAP's MCP server accepts exactly that (per-user auth-code / PATs, inheriting user RBAC)
> and **not** a federated token-exchange assertion; OQ-2 → **no identity-broker mint**
> (connector-local, target-issued).
> [ADR-0015](../../adr/0015-outbound-user-delegated-identity-via-per-user-oauth.md) records
> the decision and is **accepted**. SPEC-070 is therefore decision-complete and
> **`approved`** (operator, 2026-10-12); per the SPEC-066/069 precedent, **approval
> authorizes implementation to begin**. Commit/push, deployment, and any version bump
> remain separate authorization boundaries **not** granted here.

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
- **Why the mechanism was an operator decision, now made.** The mechanism was a genuine
  fork with different trust-federation, storage, and ADR consequences (OQ-1), gated on the
  first production target's actual acceptance (OQ-3, like SPEC-067 OQ-1 / SPEC-069 OQ-1).
  Research on 2026-10-12 settled OQ-3 — Red Hat AAP's MCP server accepts **per-user OAuth
  authorization-code / PATs and inherits user RBAC**, not a federated assertion — and the
  operator resolved OQ-1 to **(c) per-user OAuth authorization-code** accordingly
  (ADR-0015). The invariants below were written to hold under any mechanism and now bind
  the chosen one.

## Requirements

Each requirement holds under the mechanism OQ-1 resolved — **per-user OAuth 2.x
authorization-code, connector-local** (ADR-0015) — so the field names, grant type, and
trust config below are now **pinned to it** rather than left mechanism-agnostic.
Requirements are stable at `approved` and carry testable acceptance criteria.

### R-1: User-delegated outbound credential scheme (extends SPEC-068 additively)

Add a **user-delegated** scheme to the `credential_sets` vocabulary
(`products/tool-gateway/src/tool_gateway/tools/credential_sets.py`) alongside SPEC-068's
`basic` | `bearer` | `oauth2_client_credentials` — provisionally named
`oauth2_authorization_code` — carrying the target-side configuration needed to obtain a
**user-bound** token: the target's **authorization and token endpoints**, the platform's
**client id/secret** registered at that target, the **requested scopes**, and a reference to
the **user-scoped credential store** (R-6) holding each user's refresh token. These fields
are pinned by OQ-1's resolution to per-user OAuth authorization-code (ADR-0015).

Acceptance criteria (mechanism-agnostic):

- Every existing SPEC-068 set (`basic`, `bearer`, `oauth2_client_credentials`, and a set
  with no `scheme` key) parses **byte-for-byte** as it does post-SPEC-068; the user-
  delegated scheme is inert until such a set is provisioned.
- A user-delegated set declares the target's authorization/token endpoints, the platform
  client credential, and the scopes for the `authorization_code`/`refresh_token` grant; a
  set missing any required field is ignored with a `LOGGER.warning` and **never** admitted
  half-formed (reusing SPEC-068 R-1's fail-closed parser).
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
succeed, and fail closed when that trust is absent. Under OQ-1's resolution the
prerequisite is **connector-local**: a platform OAuth **client registered at the target**
(client id/secret + redirect URI) and a **completed per-user consent** at the target's own
authorization endpoint — **not** a federated platform issuer the target must trust, and
**not** a broker-minted assertion (OQ-2 = no mint). The target issues the user-bound token
itself and enforces its own RBAC.

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

### R-6: Provisioning, and per-user credential storage

The **target/client** configuration rides SPEC-068 R-5's existing file-mounted
credential-set model (`credential-sets.json` via `sync-browser-credentials.sh`); no new
platform-config secret mechanism. Because OQ-1 resolved to per-user OAuth
authorization-code, a **new user-scoped credential store** **is required** — it holds each
user's target-issued refresh token and is a capability SPEC-068's platform-config store
does not provide. OQ-4 (its shape: consent capture, encryption-at-rest, rotation,
revocation) is now **in scope** for this substrate and is its own reviewed capability.

Acceptance criteria:

- The platform-config half reuses SPEC-068 R-5 verbatim: an operator supplies the
  user-delegated set's target/client config through the existing file-mounted secret; never
  inline env, never committed; `make overlays` renders the dev-k8s wiring green; the
  extension is inert until such a set is provisioned.
- The per-user-storage half (consent capture, refresh-token persistence, rotation,
  revocation) is **in scope** because OQ-1 forces it: it is its own reviewed capability
  (encrypted at rest, in-memory on use, rotatable, revocable, redaction-covered per R-5),
  **not** an ad-hoc file. Its detailed shape is pinned in the plan under OQ-4.

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
- **The rejected delegation mechanisms.** RFC 8693 token exchange, Azure-style OBO, and
  shared-IdP SSO/federation are **not** this spec's mechanism — OQ-1 resolved to per-user
  OAuth authorization-code and ADR-0015 records why the others were rejected or deferred.

## Impact

- products touched: `products/tool-gateway` — `tools/credential_sets.py` (additive
  `oauth2_authorization_code` scheme), `tools/oauth_client.py` **or** a new
  `tools/user_delegated_client.py` (the authorization-code/refresh-token grant),
  `tools/auth_resolution.py` (thread the user subject into the seam), and a **new
  user-scoped credential store** (R-6/OQ-4). **`products/identity-broker` is NOT touched** —
  OQ-2 resolved to **no broker mint**; the broker's inbound `sub` is only read to look up
  the user's refresh token. **No kernel change.** The grant is a plain `httpx` POST to the
  target's token endpoint; only the one-time consent flow may need more, pinned in the plan.
- contracts touched: the credential-set secret **file shape** (additive scheme) and a **new
  user-scoped credential secret** (the per-user refresh-token store, R-6/OQ-4 — now
  required, not conditional). **`identity-token.schema.json` is UNCHANGED** — OQ-2 resolved
  to no broker mint, so there is no new outbound audience/claim class. No policy-bundle
  change (no new tools). No secret-vocabulary change (existing redaction already covers the
  new names).
- identity / policy / audit / execution-safety impact: establishes the platform's **first
  outbound user-delegated identity** — a **trust-model change** recorded by
  [ADR-0015](../../adr/0015-outbound-user-delegated-identity-via-per-user-oauth.md)
  (**accepted**). The principal new trust surface is the **user-scoped credential store**
  (custody of per-user external refresh tokens), not a broker change. Audit gains a
  delegation-mode dimension (R-4). Fail-closed, no-fabrication, and the new
  **no-downgrade-to-service-account** invariant (R-5) are preserved. The internal ADR-0004
  `sub`/`act` delegation is unaffected.
- ADR: [ADR-0015](../../adr/0015-outbound-user-delegated-identity-via-per-user-oauth.md)
  is **accepted** (2026-10-12); its scope is the connector-local per-user OAuth decision,
  **no broker mint**, and the user-scoped credential store as the new trust surface.
- living state docs to update on delivery: the
  [identity model](../../agentic-aiops-platform/identity-and-authorization-design.md)
  §Service Identity Model / §External Execution Identity (record the user-delegated form
  landing), `products/tool-gateway/README.md` (the credential-scheme surface),
  `docs/guides/architecture-overview.md` (the tool-gateway capability row), the ADR index
  (`docs/adr/README.md`) if ADR-0015 is written, and the delivery-roadmap (mark the
  substrate delivered; note SPEC-069's production path now depends on it).

## Open Questions

**OQ-1, OQ-2, and OQ-3 are RESOLVED (2026-10-12); SPEC-070 is `approved`.** OQ-1 →
per-user OAuth 2.x authorization-code, connector-local; OQ-2 → no identity-broker mint;
OQ-3 → Red Hat AAP's MCP server accepts per-user OAuth authorization-code / PATs and
inherits user RBAC (researched 2026-10-12), which is what made (c) the fit. ADR-0015
records the decision. OQ-4 is **in scope** (forced by OQ-1); OQ-5 and OQ-6 are answered by
the resolved mechanism and are tracked as implementation checks below. Commit/push,
deployment, and any version bump remain separate authorization boundaries **not** granted
by approval.

- **OQ-1 — RESOLVED (operator, 2026-10-12): (c) per-user OAuth authorization-code.** With
  stored per-user refresh tokens, needing R-6's user-scoped store + a one-time consent
  flow. Rejected: (a) connector-local RFC 8693 token exchange and (b) Azure-style OBO — the
  first production target (Red Hat AAP) documents neither and (2.6) has no OIDC discovery,
  so there is no evidence it accepts an exchanged `subject_token` or trusts the platform
  issuer. Deferred: (d) shared-IdP SSO/federation — viable only if the target federates to
  the same enterprise IdP, and even then a user-bound target token is still needed.
  ADR-0015 records the full rationale; R-1 fields, the R-3 trust contract, and the R-6
  store are now pinned to (c).
- **OQ-2 — RESOLVED (2026-10-12): no identity-broker mint.** The mechanism stays
  **connector-local**: the outbound token is issued by the **target**, not signed by the
  platform. The broker's existing inbound delegated token supplies only the user `sub` used
  to look up that user's stored refresh token. `identity-token.schema.json` is **unchanged**
  and the identity-broker gains **no** new outbound audience or signing context. ADR-0015
  records this scope.
- **OQ-3 — RESOLVED (researched 2026-10-12): per-user AAP credentials.** Red Hat AAP's MCP
  server authenticates each user via **OAuth 2.x authorization-code** (or a **PAT**) against
  **AAP Gateway's own** authorization server (`/o/authorize/`, `/o/token/`) and **inherits
  the requesting user's RBAC**; AAP 2.6 enforces **no PKCE** and provides **no automatic
  OIDC discovery** (explicit endpoints required), and documents **authorization-code and
  password** grants — **not** RFC 8693 token-exchange or OBO. This is the checkable fact
  (mirrors SPEC-067 OQ-1 / SPEC-069 OQ-1) that constrained OQ-1 to (c). Source: Red Hat AAP
  2.6 "Authenticate with OAuth" MCP-server docs; corroborated by the project memory
  "Ansible MCP server landscape."
- **OQ-4 — IN SCOPE (forced by OQ-1 = c).** Where do user-scoped refresh tokens live, and
  how are consent, rotation, and revocation handled? SPEC-068's store is platform-config,
  not user-scoped, so this is a **new capability that warrants its own review** — the
  principal new trust surface ADR-0015 introduces. Its detailed shape (encrypted at rest,
  in-memory on use, rotatable, revocable, redaction-covered per R-5) is pinned in the plan;
  R-6 carries the requirement.
- **OQ-5 — answered by the resolved mechanism; tracked as an implementation check.** With
  authorization-code (not token exchange), self-contained dev validation needs a mock OAuth
  authorization server supporting the auth-code + refresh-token grants — a **self-hosted
  Keycloak** as the target IdP fronting **AWX** is the natural in-cluster stand-in. Ties to
  [SPEC-069](../SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) OQ-5's
  self-contained in-cluster validation; the concrete harness is pinned in the plan.
- **OQ-6 — answered; tracked as a test obligation.** The resolved mechanism makes both
  invariants structural: the target issues the token under **its own** RBAC for that user,
  so it can never exceed the user's target-side authority (R-2), and a failed
  authorization-code/refresh acquisition **fails closed** with no service-account fallback
  (R-5 no-downgrade). A test asserts the absence of any downgrade path — the governance
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
