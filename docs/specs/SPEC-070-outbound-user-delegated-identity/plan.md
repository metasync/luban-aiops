# SPEC-070 Plan: Outbound User-Delegated Execution Identity (Tool-Gateway Substrate)

> **Provisional — do not implement.** SPEC-070 is `draft` and **not** decision-complete:
> **OQ-1** (the delegation mechanism) and **OQ-2** (whether the identity-broker mints a new
> outbound token, which sets the ADR-0015 scope) both block `approved`, and **OQ-3** (what
> AAP actually accepts) is a Stage-0 live fact that constrains OQ-1. This plan records the
> intended shape and the invariants that hold under *any* mechanism; the mechanism-specific
> build steps are deliberately left as Stage-0 outputs rather than guessed here. No
> implementation, commit/push, deployment, or version bump is authorized.

## Approach

SPEC-070 is the *user-delegated* counterpart to SPEC-068's *service-account* outbound
plane. SPEC-068 proved the reusable half — a per-set `scheme`, a connector-local token
client, and one outbound auth-resolution seam (`tools/auth_resolution.py`) that returns both
an `httpx.Auth` and a raw bearer/header. SPEC-070 **extends that seam to carry a user
subject** rather than replacing it: the requesting user is already present inbound as the
ADR-0004 delegated token (`sub` = user, `act` = service), so the work is to thread that
subject into outbound acquisition and obtain a **target-issued, user-bound** token.

The build is **Stage-0-gated**, because the mechanism is an open fork (OQ-1) with different
trust, storage, and ADR consequences:

1. **Stage 0 — decide the mechanism (OQ-1/OQ-2/OQ-3), then write ADR-0015.** Pin the grant
   (token exchange / OBO / per-user OAuth / shared-IdP SSO), confirm whether the broker
   mints anything new, verify what AAP accepts, and record the trust-model decision in
   ADR-0015. Only after this does the spec become `approved` and the build concrete.
2. **Parse** (R-1) — add the user-delegated scheme to `credential_sets.py`, additive over
   SPEC-068's three schemes; existing sets byte-identical.
3. **Acquire** (R-2) — add the user-delegated grant client (`oauth_client.py` extended, or a
   new `user_delegated_client.py`), threading the request's user subject into the grant.
4. **Resolve** (R-2/R-3) — extend `auth_resolution.py` so a user-delegated set resolves
   through the user-subject path; fail closed when the subject or the federation is absent.
5. **Prove safe** (R-4/R-5) — redaction, fail-closed, and the **no-downgrade-to-service**
   invariant; audit delegation-mode attribution.
6. **Provision** (R-6) — ride SPEC-068 R-5's file-mounted model for target/client config;
   scope any per-user store only if OQ-1/OQ-4 force it.
7. **Deliver** — living-state docs, ADR index, CHANGELOG, version; separate authorization.

## Design Per Requirement

### R-1: User-delegated outbound credential scheme (additive over SPEC-068)

- affected files / modules:
  `products/tool-gateway/src/tool_gateway/tools/credential_sets.py` — add the user-delegated
  scheme to `_SCHEME_REQUIRED_FIELDS` and retain its fields in `_parse_set`, exactly as
  SPEC-068 generalized the parser. The scheme name and required fields are **OQ-1 outputs**.
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
  `tools/user_delegated_client.py` (the grant itself, per OQ-1).
- chosen approach: the resolver already returns both an `httpx.Auth` and a raw bearer/header
  (SPEC-068 R-3, so a non-httpx transport such as an MCP streamable-HTTP client can reuse
  it). SPEC-070 adds a user-delegated branch that (a) takes the requesting user's subject
  from the inbound delegated token, (b) performs the OQ-1 grant against the target's
  endpoint, and (c) returns a **user-bound** target token. In-memory cache keyed by
  (set name, user subject) with near-expiry refresh and single-flight, mirroring
  `oauth_client`'s `_CachedToken`/lock discipline — but **never** shared across users.
- no-elevation invariant: the outbound token carries at most the user's target-side
  authority; the platform does not translate or synthesize roles (mirrors
  `exchange_service.exchange_token`, which copies `roles` verbatim and "can never grant
  authority the subject token lacks").
- alternatives considered and why deferred (not rejected — OQ-1 decides):
  - **Token exchange (RFC 8693) at the target IdP** — connector-local, likely a single
    `httpx` POST, no new platform signing authority; needs the target IdP to trust the
    platform issuer as a `subject_token` source.
  - **On-behalf-of** — similar shape, vendor-specific (e.g. Azure AD); same trust question.
  - **Per-user OAuth authorization-code** — strongest per-user consent, but needs R-6's
    user-scoped refresh-token store + a consent flow (a new capability).
  - **Shared-IdP SSO / federation** — aligns with the identity model's Keycloak + AD stack;
    pushes the user assertion to an IdP the target already trusts.

### R-3: Trust-boundary / federation contract

- affected files / modules: connector config + `auth_resolution.py`; **possibly**
  `products/identity-broker` *iff* OQ-2 selects a broker-minted outbound token.
- chosen approach: the trust prerequisite (a federated issuer the target trusts, a per-user
  consent, or a shared IdP) is **explicit per-set config**, never auto-negotiated — the same
  posture as SPEC-068's explicit `client_auth` variant. A missing/broken federation fails
  closed with a structured gateway error; the platform never asserts a user identity to a
  target not configured to trust it.
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

### R-6: Provisioning + (OQ-dependent) per-user storage

- affected files / modules: `shared/platform-ops/gitops/sync-browser-credentials.sh` (the
  extended shape), `shared/platform-ops/gitops/dev-k8s/` (overlay), tool-gateway README;
  **possibly** a new user-scoped credential store *iff* OQ-1 picks per-user OAuth (OQ-4).
- chosen approach: the target/client config is just another entry in the file-mounted
  `credential-sets.json` (SPEC-068 R-5 verbatim) — no new platform-config secret, never
  inline env, never committed; `make overlays` green; inert until provisioned. Per-user
  refresh-token storage is **out of the first slice** unless OQ-1 forces it, in which case it
  is its own reviewed capability (consent, rotation, revocation), not an ad-hoc file.

## Sequencing And Dependencies

1. **Stage 0 — mechanism + ADR (OQ-1/OQ-2/OQ-3).** Gate for everything else; produces
   ADR-0015 and flips the spec to `approved`. Depends on the OQ-3 AAP live fact.
2. **R-1 parse** — depends on Stage 0 (the scheme's fields).
3. **R-2 acquire + thread** — depends on R-1 and Stage 0 (the grant).
4. **R-3 trust contract** — depends on Stage 0; may touch identity-broker iff OQ-2 says so.
5. **R-4 attribution** — depends on R-2/R-3 (proves the path they add).
6. **R-5 invariants** — depends on R-1–R-4.
7. **R-6 provisioning** — depends on R-1; per-user storage gated by OQ-4.
8. **Delivery boundary** — separate authorization (docs, ADR index, CHANGELOG, version).

Unlike SPEC-068 (no external-fact gate), SPEC-070 has a **Stage-0 gate**: the mechanism and
the first target's acceptance must be pinned before the build is concrete. SPEC-069's
production path consumes this substrate but its read-only **dev** slice does not block on it.

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
- integration: exercise the user-delegated path against a **mock IdP / token endpoint**
  (`httpx.MockTransport`, the seam `HttpConnector` already accepts) so CI makes no live
  external call; cover a successful user-bound acquisition, the no-subject fail-closed path,
  the broken-federation fail-closed path, and the no-downgrade assertion. `make overlays`
  renders the dev-k8s wiring. OQ-5 pins the self-contained dev topology (mock IdP vs a
  self-hosted Keycloak + AWX).

## Rollout And Migration

- deployment or configuration changes required: none for the substrate until an operator
  provisions a user-delegated set; **possibly** a new broker audience (OQ-2) or a user-scoped
  secret (OQ-4), both flagged Stage-0 outputs, not assumed.
- backward compatibility: SPEC-068's three schemes are unchanged; the resolver's existing
  branches are behavior-identical; the browser `fill_credential` path is untouched. New
  dependency only if OQ-1's mechanism cannot be a plain `httpx` POST.
- rollback approach: remove any user-delegated set from the credential file — the added code
  paths are dead without one. If OQ-2 added a broker audience, it is inert without a
  consuming set. No schema change is forced unless OQ-2/OQ-4 select one, in which case
  rollback follows that contract's own migration note.
