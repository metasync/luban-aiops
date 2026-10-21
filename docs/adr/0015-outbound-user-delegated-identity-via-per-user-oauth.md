# ADR-0015: Outbound User-Delegated Identity Via Per-User OAuth Authorization-Code, Connector-Local

## Status

`superseded by ADR-0016`

- date: 2026-10-12
- accepted: 2026-10-12
- superseded: 2026-10-18 by [ADR-0016](0016-just-in-time-outbound-oauth-authorization.md),
  which retains this record's target-issued authorization-code / no-broker-mint core and
  per-user credential store, and revises its provisioning-only one-time enrollment, the PAT
  interim variant for this slice, and the blanket no-kernel-change scope assumption to the
  first-use/reauthorization workflow. This accepted body is immutable; only the status and
  this supersession link changed.
- deciders: workspace operator, through explicit SPEC-070 OQ-1 mechanism selection
- related specs: [SPEC-070](../specs/SPEC-070-outbound-user-delegated-identity/spec.md)
  (the outbound user-delegated substrate this decision unblocks);
  [SPEC-069](../specs/SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md)
  (OQ-4 directive — user-delegated identity all the way to the targets — extracted to
  SPEC-070); [SPEC-068](../specs/SPEC-068-outbound-execution-credential-schemes/spec.md)
  (the machine-grant outbound plane this extends additively)
- related ADRs: [ADR-0004](0004-broker-mediated-token-delegation.md) — the *inbound /
  internal* delegation this is the outbound-to-external-target analogue of
- evidence: Red Hat Ansible Automation Platform 2.6 "Authenticate with OAuth" MCP-server
  docs and "Introducing the MCP server for Red Hat Ansible Automation Platform"
  (researched 2026-10-12): AAP's MCP server accepts **per-user OAuth 2.x
  authorization-code** (or personal access tokens) against **AAP Gateway's own**
  authorization server (`/o/authorize/`, `/o/token/`) and *inherits the requesting user's
  RBAC*; AAP 2.6 provides **no automatic OIDC discovery** and documents
  **authorization-code and password** grants — **not** RFC 8693 token-exchange or an
  on-behalf-of flow. Corroborated by the project memory "Ansible MCP server landscape."
- scope: records the approved outbound trust-model decision (per-user OAuth
  authorization-code, connector-local target-issued token, **no identity-broker mint**,
  plus a new **user-scoped credential store**). Implementation detail remains in the
  SPEC-070 [plan](../specs/SPEC-070-outbound-user-delegated-identity/plan.md). Acceptance
  is not a claim of shipped behavior, nor authorization for deployment or a version bump.

## Context

SPEC-069 OQ-4 resolved (operator, 2026-10-11) that **user-delegated identity should run
all the way to the targets**, so the agent never acts toward an external system on its own
service identity. That capability did not exist, so it was extracted to SPEC-070. Four
facts force the mechanism decision:

- **SPEC-068 shipped the outbound plane with only a machine grant.** Its schemes
  (`basic` / `bearer` / `oauth2_client_credentials`) carry **no user subject**. At a target
  that enforces per-user RBAC, a machine grant presents a **shared service identity**:
  per-user attribution is lost and the agent acts with the service account's blanket
  authority regardless of which operator asked — precisely the confused-deputy risk
  [ADR-0004](0004-broker-mediated-token-delegation.md) was written to prevent *internally*.
- **ADR-0004's delegation is inbound/internal only.** The identity-broker is the sole
  signing authority and mints audience-bound JWTs for service-to-service hops *within*
  Luban. **External targets do not trust the platform's JWKS**, so the internal delegated
  token cannot be forwarded outbound. Carrying a user subject to an external system is a
  **new trust relationship**, not an extension of ADR-0004.
- **The first production target constrains the mechanism.** Red Hat AAP's MCP server
  authenticates **each user** via OAuth 2.x authorization-code (or a PAT) against **its
  own** authorization server and inherits that user's AAP RBAC; it exposes **no OIDC
  discovery** (2.6) and documents **authorization-code and password** grants, **not** RFC
  8693 token-exchange or OBO. The target therefore issues the user-bound token itself; the
  platform cannot assert a federated user identity that AAP would accept.
- **Platform-side, the user subject already exists.** Human users arrive via Keycloak/AD →
  OIDC, and the ADR-0004 inbound delegated token carries `sub` = the requesting user. The
  gap is purely outbound: a credential the **target** will accept **as that user**.

## Decision

**Outbound user-delegated execution identity is obtained by per-user OAuth 2.x
authorization-code, resolved connector-locally in the tool-gateway against the target's own
token endpoint using a platform-custodied per-user refresh token. The identity-broker mints
nothing new outbound.**

1. **Mechanism (SPEC-070 OQ-1 = c).** A user completes a **one-time consent**
   (authorization-code) flow against the target; the platform stores the resulting
   **per-user refresh token** in a new **user-scoped credential store**. At call time the
   connector exchanges that refresh token at the **target's** token endpoint for a
   short-lived, **target-issued, user-bound** access token and presents it on the outbound
   call. The target enforces **its own** RBAC on the user.
2. **No broker mint (SPEC-070 OQ-2).** The outbound token is issued by the **target**, not
   signed by the platform. The broker's existing inbound delegated token supplies only the
   user `sub` used to **look up** that user's stored refresh token. The identity-broker
   gains **no** new outbound audience or signing context, and `identity-token.schema.json`
   is **unchanged**.
3. **No elevation, fail closed, no downgrade.** The outbound token carries **at most** the
   authority the user holds at the target (mirroring `exchange_service.exchange_token`'s
   verbatim-roles invariant); role→RBAC mapping is the **target's** decision, not a platform
   translation layer. A failed user-delegated acquisition (no resolvable subject, broken
   consent, token-endpoint failure) **fails closed** and must **never** silently fall back
   to a `oauth2_client_credentials`/`basic`/`bearer` service credential (SPEC-070 R-5
   no-downgrade).
4. **The new trust surface is the user-scoped credential store.** The genuinely new custody
   responsibility is per-user **external** refresh tokens: encrypted at rest, in-memory on
   use, rotatable and revocable, and covered by the existing redaction vocabulary — never
   logged, never surfaced in a tool result, evidence, or audit (SPEC-068 R-4 / SPEC-009
   R-1). This store, not a broker change, is what this ADR introduces beyond SPEC-068.

## Alternatives Considered

- **Connector-local RFC 8693 token exchange** (present the inbound user token as
  `subject_token` at the target IdP) — rejected for the first target: AAP's MCP server
  documents authorization-code + password grants and (2.6) has no OIDC discovery, so there
  is no evidence it accepts an exchanged `subject_token` or trusts the platform issuer.
  Reconsider only if a future target's IdP supports RFC 8693 **and** trusts the platform as
  an issuer.
- **On-behalf-of (Azure-AD-style OBO)** with the platform's client credential — rejected:
  the first production target is not Azure AD and documents no OBO flow.
- **Shared-IdP SSO / federation** (Keycloak + AD; the target trusts the enterprise IdP and
  maps the user's groups to its own RBAC) — deferred, not rejected: viable only if the
  target federates to the **same** enterprise IdP, and even then the platform still needs a
  **user-bound target token**, so it does not remove the per-user acquisition adopted here;
  it adds a target-side SSO deployment dependency. Kept as an evolution if the enterprise
  standardizes SSO to targets.
- **Broker-minted outbound user assertion** (a new outbound audience class signed by the
  identity-broker) — rejected for the first target: external targets do not trust the
  platform JWKS (the same reason ADR-0004 is internal-only), so a platform-signed assertion
  has no accepting consumer; it would add a signing context and a schema change for nothing.
  Reconsider alongside Kubernetes workload identity (SPEC-068's documented Option C) under
  cluster-to-cluster trust.
- **Forward the inbound ADR-0004 delegated token outbound** — rejected: the internal
  audience-bound token is not trusted by external targets and is scoped to intra-platform
  hops; forwarding it would be both mistrusted and a scope violation.
- **Per-user PATs instead of authorization-code** — accepted as a **simpler interim variant**
  of the same decision (still per-user, still target-issued, still needs the user-scoped
  store), but not the primary: PATs are long-lived static secrets with no refresh/rotation,
  so they are weaker hygiene than an authorization-code + refresh-token pair. A target that
  only offers PATs (e.g., an AAP 2.6 client that requires auto-discovery) uses this variant.

## Consequences

- **Per-user attribution end to end.** A target-side action is attributable to the
  requesting human, and the target enforces its own RBAC on that user — satisfying
  identity-model Principles 2/3/5 and closing the outbound confused-deputy gap SPEC-068's
  machine grant left open.
- **Accepted trade-off — new secret custody.** The platform now custodies per-user
  **external** refresh tokens: a new secret class with consent, storage, rotation, and
  revocation obligations, so SPEC-070 R-6 / OQ-4 moves **into** scope. This is the
  principal new risk surface, bounded by encryption-at-rest, in-memory-only use, redaction,
  and fail-closed handling.
- **Accepted trade-off — one-time interactive consent.** Each user must complete an
  authorization-code consent per target before delegated calls succeed (a provisioning
  step); the PAT variant avoids the flow at the cost of static-secret hygiene.
- **No broker, schema, HITL, tier, or kernel change.** ADR-0004's inbound delegation,
  `identity-token.schema.json`, risk tiering, ADR-0007 one-gate-per-flow, signed execution
  (SPEC-037), and durable claims (SPEC-063) are untouched; the change is additive beneath
  the outbound auth-resolution seam.
- **Additive to SPEC-068.** `basic` / `bearer` / `oauth2_client_credentials` parse and
  resolve byte-for-byte as before; the user-delegated scheme is inert until provisioned.
- **Follow-up work triggered:** SPEC-070 (R-1..R-6) implements this decision and moves to
  `approved`; SPEC-069's **production** user-delegated path depends on SPEC-070 (its
  read-only **dev** slice is unaffected — it validates against the self-hosted server's own
  auth). The user-scoped credential store is its own reviewed capability within SPEC-070,
  not an ad-hoc file.
