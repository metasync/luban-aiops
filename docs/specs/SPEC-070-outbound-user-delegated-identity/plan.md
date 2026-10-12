# SPEC-070 Plan: Outbound User-Delegated Execution Identity (Tool-Gateway Substrate)

> **Approved — implementation authorized (2026-10-12).** SPEC-070 is `approved`:
> **OQ-1** resolved to **(c) per-user OAuth 2.x authorization-code, connector-local**;
> **OQ-2** to **no identity-broker mint**; **OQ-3** answered by research (Red Hat AAP's MCP
> server takes per-user OAuth auth-code / PATs and inherits user RBAC; no OIDC discovery /
> token-exchange / OBO in 2.6).
> [ADR-0015](../../adr/0015-outbound-user-delegated-identity-via-per-user-oauth.md) is
> **accepted**. Stage 0 is complete, so this plan now pins the **chosen** mechanism's build
> steps rather than leaving them mechanism-agnostic. Commit/push, deployment, and any
> version bump remain **separate** authorization boundaries **not** granted by approval.

## Approach

SPEC-070 is the *user-delegated* counterpart to SPEC-068's *service-account* outbound
plane. SPEC-068 proved the reusable half — a per-set `scheme`, a connector-local token
client, and one outbound auth-resolution seam (`tools/auth_resolution.py`) that returns both
an `httpx.Auth` and a raw bearer/header. SPEC-070 **extends that seam to carry a user
subject** rather than replacing it: the requesting user is already present inbound as the
ADR-0004 delegated token (`sub` = user, `act` = service), so the work is to thread that
subject into outbound acquisition and obtain a **target-issued, user-bound** token.

The build was **Stage-0-gated** while the mechanism was an open fork; **Stage 0 is now
complete** (OQ-1 = per-user OAuth authorization-code, OQ-2 = no broker mint, OQ-3 = AAP
takes per-user auth-code/PATs, ADR-0015 accepted), so the steps are concrete:

1. **Stage 0 — DONE.** Mechanism decided (per-user OAuth 2.x authorization-code,
   connector-local), broker-mint ruled out, AAP's acceptance verified, and the trust-model
   decision recorded in ADR-0015 (**accepted**). The spec is `approved`.
2. **Parse** (R-1) — add the `oauth2_authorization_code` scheme to `credential_sets.py`,
   additive over SPEC-068's three schemes; existing sets byte-identical.
3. **Acquire** (R-2) — add the authorization-code / refresh-token grant client
   (`oauth_client.py` extended, or a new `user_delegated_client.py`), threading the request's
   user subject into the grant against the **target's** token endpoint.
4. **Resolve** (R-2/R-3) — extend `auth_resolution.py` so a user-delegated set resolves
   through the user-subject path; fail closed when the subject or the per-user consent is
   absent.
5. **Prove safe** (R-4/R-5) — redaction, fail-closed, and the **no-downgrade-to-service**
   invariant; audit delegation-mode attribution.
6. **Provision** (R-6) — ride SPEC-068 R-5's file-mounted model for target/client config;
   **and** build the user-scoped credential store (OQ-1 = c forces it; OQ-4 in scope).
7. **Deliver** — living-state docs, ADR index, CHANGELOG, version; separate authorization.

## Design Per Requirement

### R-1: User-delegated outbound credential scheme (additive over SPEC-068)

- affected files / modules:
  `products/tool-gateway/src/tool_gateway/tools/credential_sets.py` — add the user-delegated
  scheme to `_SCHEME_REQUIRED_FIELDS` and retain its fields in `_parse_set`, exactly as
  SPEC-068 generalized the parser. The scheme is provisionally named
  `oauth2_authorization_code`; its required fields (target authorization + token endpoints,
  platform client id/secret, scopes, user-scoped-store reference) are pinned by OQ-1 = (c).
- chosen approach: extend the existing per-scheme field map; do not fork the parser. A
  `basic`/`bearer`/`oauth2_client_credentials` set (or one with no `scheme`) parses
  byte-for-byte as post-SPEC-068; the new scheme is inert until provisioned. Unknown scheme
  or missing required field → ignored with a `LOGGER.warning` (fail-closed), reusing
  SPEC-068 R-1's pattern verbatim.
- backward compatibility: no existing set changes shape; the `acme-admin` sample and the
  browser `fill_credential` path are untouched.

### R-2: User-subject threading + the user-delegated grant

- affected files / modules:
  `products/tool-gateway/src/tool_gateway/tools/auth_resolution.py` (thread the request's
  user-identity context into resolution), and `tools/oauth_client.py` extended **or** a new
  `tools/user_delegated_client.py` (the authorization-code / refresh-token grant).
- chosen approach: the resolver already returns both an `httpx.Auth` and a raw bearer/header
  (SPEC-068 R-3, so a non-httpx transport such as an MCP streamable-HTTP client can reuse
  it). SPEC-070 adds a user-delegated branch that (a) takes the requesting user's subject
  from the inbound delegated token, (b) uses it to look up that user's stored **refresh
  token** and exchanges it at the **target's** token endpoint (`refresh_token` grant; the
  one-time `authorization_code` consent happens at provisioning), and (c) returns a
  **target-issued, user-bound** access token. In-memory cache keyed by (set name, user
  subject) with near-expiry refresh and single-flight, mirroring `oauth_client`'s
  `_CachedToken`/lock discipline — but **never** shared across users.
- no-elevation invariant: the outbound token carries at most the user's target-side
  authority; the platform does not translate or synthesize roles (mirrors
  `exchange_service.exchange_token`, which copies `roles` verbatim and "can never grant
  authority the subject token lacks").
- alternatives considered (OQ-1 decided — full rationale in ADR-0015):
  - **Chosen: per-user OAuth authorization-code** — strongest per-user consent and the only
    one the first production target (Red Hat AAP) actually accepts; costs R-6's user-scoped
    refresh-token store + a one-time consent flow (a new capability).
  - **Token exchange (RFC 8693) at the target IdP** — rejected for the first target: AAP
    documents no RFC 8693 and (2.6) has no OIDC discovery, so there is no evidence it accepts
    an exchanged `subject_token` or trusts the platform issuer.
  - **On-behalf-of** — rejected: vendor-specific (e.g. Azure AD); the first target is not
    Azure AD and documents no OBO flow.
  - **Shared-IdP SSO / federation** — deferred: viable only if the target federates to the
    same enterprise IdP, and even then a user-bound target token is still needed.

### R-3: Trust-boundary / federation contract

- affected files / modules: connector config + `auth_resolution.py`.
  **`products/identity-broker` is NOT touched** — OQ-2 resolved to no broker mint
  (connector-local, target-issued token).
- chosen approach: the trust prerequisite is **connector-local** — a platform OAuth client
  registered at the target (client id/secret + redirect URI) plus a completed **per-user
  consent** at the target's own authorization endpoint — held as **explicit per-set config**,
  never auto-negotiated (the same posture as SPEC-068's explicit `client_auth` variant). The
  target issues the user-bound token itself and enforces its own RBAC. A missing/broken
  client registration or consent fails closed with a structured gateway error; the platform
  never asserts a user identity to a target not configured to trust it.
- why this matters: this is the trust-model change ADR-0015 records. The platform crossing
  its boundary with a *user* assertion an external party relies on for access decisions is
  the outbound analogue of ADR-0004's internal delegation.

### R-4: End-to-end attribution fidelity

- affected files / modules: the audit emission path for outbound tool calls (reuse the
  existing trail; add a delegation-mode dimension). No new HITL surface.
- chosen approach: an outbound user-delegated call records the human subject **and** that
  the call was user-delegated (vs a SPEC-068 service-account call), so a target-side action
  is attributable end to end (identity Principles 2/3/5; ADR-0004's separate `sub`/`act`).
  No token/secret surfaces (reuse SPEC-068 R-4 + SPEC-009 R-1 redaction).

### R-5: Secret-handling, fail-closed, no-fabrication, **no-downgrade**

- affected files / modules: tests under `products/tool-gateway/tests/`; no production
  vocabulary change expected.
- chosen approach: assert, don't assume. Drive a user-delegated token through a URL
  projection, a tool result, an evidence field, and audit; confirm masking (the existing
  `SECRET_QUERY_PARAMS` / `_VALUE_PATTERNS` already cover `token`/`secret`/`authorization`).
  Confirm `make validate-secret-vocabulary` stays green with no new canonical field set.
  In-memory-only token, log the failure *class* + set **name** only.
- **no-downgrade test (the governance crux):** assert that when user-delegated acquisition
  fails, there is **no** code path that retries with `oauth2_client_credentials`/`bearer`/
  `basic`. A silent service-account fallback would violate the OQ-4 directive, so its
  absence is a first-class tested invariant, not a comment.

### R-6: Provisioning + per-user credential storage (in scope)

- affected files / modules: `shared/platform-ops/gitops/sync-browser-credentials.sh` (the
  extended shape), `shared/platform-ops/gitops/dev-k8s/` (overlay), tool-gateway README;
  **and a new user-scoped credential store** (OQ-1 = c forces it; OQ-4 in scope).
- chosen approach: the target/client config is just another entry in the file-mounted
  `credential-sets.json` (SPEC-068 R-5 verbatim) — no new platform-config secret, never
  inline env, never committed; `make overlays` green; inert until provisioned. The
  **user-scoped refresh-token store is now in the slice** because OQ-1 forces it: its own
  reviewed capability (one-time consent capture, encrypted-at-rest persistence, in-memory
  use, rotation, revocation, redaction-covered per R-5), **not** an ad-hoc file. Its concrete
  backend is the principal implementation decision left under OQ-4.

## Sequencing And Dependencies

1. **Stage 0 — mechanism + ADR (OQ-1/OQ-2/OQ-3): DONE.** Produced ADR-0015 (**accepted**)
   and flipped the spec to `approved`; the OQ-3 AAP fact is recorded.
2. **R-1 parse** — the `oauth2_authorization_code` scheme's fields (pinned).
3. **R-2 acquire + thread** — depends on R-1; the authorization-code / refresh-token grant.
4. **R-3 trust contract** — connector-local client registration + per-user consent; **no**
   identity-broker change (OQ-2 = no mint).
5. **R-4 attribution** — depends on R-2/R-3 (proves the path they add).
6. **R-5 invariants** — depends on R-1–R-4.
7. **R-6 provisioning + user-scoped store** — depends on R-1; the per-user store is in scope
   (OQ-1 = c); its concrete backend is the OQ-4 implementation decision.
8. **Delivery boundary** — separate authorization (docs, ADR index, CHANGELOG, version).

SPEC-070's **Stage-0 gate is cleared** — the mechanism and the first target's acceptance are
pinned, so the build is concrete. SPEC-069's production path consumes this substrate but its
read-only **dev** slice does not block on it.

## Test Strategy

- unit tests: the user-delegated scheme parsing + field retention + fail-closed on
  unknown/incomplete (R-1); the grant client's cache keyed by (set, user), near-expiry
  refresh, single-flight, never-cross-user token reuse, and never-logged token (R-2); the
  resolver's user-delegated branch + its fail-closed path when the subject/federation is
  absent (R-2/R-3).
- **no-downgrade test (R-5):** assert no fallback to a service-account scheme when
  user-delegated acquisition fails — the governance invariant.
- contract tests: `make validate-secret-vocabulary` asserted unchanged; a SPEC-068-scheme
  regression proving `basic`/`bearer`/`oauth2_client_credentials` resolution is
  byte-identical.
- integration: exercise the user-delegated path against a **mock OAuth token endpoint**
  (`httpx.MockTransport`, the seam `HttpConnector` already accepts) so CI makes no live
  external call; cover a successful user-bound `refresh_token` acquisition, the no-subject
  fail-closed path, the missing/broken-consent fail-closed path, and the no-downgrade
  assertion. `make overlays` renders the dev-k8s wiring. Per OQ-5, the self-contained dev
  topology is a **self-hosted Keycloak** (target IdP, authorization-code + refresh grants)
  fronting **AWX**.

## Rollout And Migration

- deployment or configuration changes required: none for the substrate until an operator
  provisions a user-delegated set **and** each user completes the one-time consent; a **new
  user-scoped credential secret** (the refresh-token store, OQ-4) is required. **No broker
  audience** — OQ-2 resolved to no mint.
- backward compatibility: SPEC-068's three schemes are unchanged; the resolver's existing
  branches are behavior-identical; the browser `fill_credential` path is untouched. The grant
  is a plain `httpx` POST to the target's token endpoint; only the one-time consent flow may
  need more.
- rollback approach: remove any user-delegated set from the credential file — the added code
  paths are dead without one. `identity-token.schema.json` is unchanged (no broker mint), so
  there is no schema migration; the user-scoped store is inert without a consuming set and
  its own rollback follows its reviewed-capability migration note.
