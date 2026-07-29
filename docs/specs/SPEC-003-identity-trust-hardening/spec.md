# SPEC-003: Identity Trust Hardening

## Status

- status: `delivered`
- owner: workspace maintainers
- created: 2026-07-28
- release slice: `Release 1` (identity before privilege)
- related risks: B1 (identity trust model is dev-only)

## Summary

Replace the caller-asserted identity model with cryptographically verified JWTs. identity-broker becomes a real token issuer (RSA-signed, JWKS-published); the gateway verifies tokens locally without per-request network calls; downstream services receive identity derived from verified claims, never from untrusted headers.

## Motivation

Today, identity in the platform is a trust assertion without cryptographic backing:

- `GATEWAY_REQUIRE_AUTH=false` (the default) accepts any request unauthenticated
- when auth is "required," the gateway calls identity-broker's `/identity/me` per request — but identity-broker returns an identity for *any* bearer token without verifying it
- the `X-User-ID` header forwarded to agent-service is caller-asserted when auth is disabled — any client can impersonate any user
- `DEFAULT_USER_ID=demo.operator` is a code-level fallback that silently applies in production if misconfigured

This means the platform has no real identity boundary. Policy enforcement (B2, future spec) is impossible on top of unverified identities.

## Decision: Local JWT Verification via JWKS

The gateway verifies tokens locally using asymmetric keys (RSA) published by identity-broker at a JWKS endpoint. This means:

- zero per-request network calls for verification (pure crypto, ~microseconds)
- the gateway cannot forge tokens (it holds only the public key)
- future migration to an external IdP (Keycloak, Auth0) is a config change (swap the JWKS URL), not a rewrite
- key rotation is possible without downtime (publish new key alongside old)

## Requirements

### R-1: identity-broker as JWT issuer

identity-broker issues RSA-signed JWTs and publishes its public key set.

Acceptance criteria:

- identity-broker generates or loads an RSA key pair (2048-bit minimum) at startup
- key material is read from a PEM file path (`IDENTITY_JWT_PRIVATE_KEY_PATH`); in production this is a K8s Secret mount; in dev, if the configured path does not exist, the service auto-generates a key pair and writes it to that path (persisted across restarts, git-ignored); if no path is configured at all, an ephemeral in-memory key is generated (CI/tests only, logged as insecure)
- `POST /api/v1/auth/token` issues a signed JWT containing claims: `sub`, `username`, `email`, `roles`, `groups`, `iat`, `exp`, `iss`
- token TTL is configurable via `IDENTITY_TOKEN_TTL_SECONDS` (default: 900 = 15 minutes)
- `GET /.well-known/jwks.json` serves the public key set in standard JWKS format (RFC 7517) with a `kid` identifier
- the existing `/api/v1/identity/me` endpoint remains as a convenience (returns identity for a valid token) but is no longer in the gateway's verification hot path
- the existing login flow endpoints (`/auth/login-url`, `/auth/login`, `/auth/callback`) are preserved; `/auth/callback` now returns a JWT alongside the identity context

### R-2: Gateway local JWT verification

The gateway verifies bearer tokens locally using identity-broker's JWKS endpoint.

Acceptance criteria:

- the gateway fetches the JWKS from `IDENTITY_JWKS_URL` (default: `http://identity-service:8000/.well-known/jwks.json`) at startup and caches with a configurable refresh interval (`IDENTITY_JWKS_CACHE_SECONDS`, default: 300)
- a middleware or dependency extracts `Authorization: Bearer <jwt>`, verifies signature + expiry + issuer locally, and produces a verified `IdentityContext`
- expired, malformed, or missing tokens (when auth is required) return `401` with a structured error body
- verification does NOT call identity-broker per request — it is a local crypto operation
- the `iss` claim is always validated against `IDENTITY_TOKEN_ISSUER` (default: `luban-identity-broker`); tokens with a mismatched issuer are rejected with `401` regardless of environment
- the `PyJWT` library with `cryptography` backend is used for verification (`PyJWKClient` handles JWKS fetch/cache)
- when `GATEWAY_REQUIRE_AUTH=false`, unauthenticated requests are still allowed but receive a synthetic dev identity (see R-4)

### R-3: Verified identity propagation

Downstream services receive identity derived exclusively from verified token claims.

Acceptance criteria:

- the `X-User-ID` header forwarded to agent-service is extracted from the verified token's `username` claim (or `sub` if username is absent)
- caller-supplied `X-User-ID` headers are **ignored** when a verified identity exists — the token is the single source of truth
- the `x-request-id` correlation header continues to be forwarded (it is not identity)
- agent-service's v2 adapter continues to require `X-User-ID` — it trusts the gateway as the sole caller (network-level trust; service-to-service auth is a future concern)
- the gateway's structured logs record the verified `sub` and `roles` from the token

### R-4: Dev fallback hardening

The `DEFAULT_USER_ID` code fallback is removed; dev environments use explicit configuration.

Acceptance criteria:

- `DEFAULT_USER_ID` is removed from `GatewaySettings` and all code paths
- when `GATEWAY_REQUIRE_AUTH=false` and no bearer token is present, the gateway injects a synthetic identity: `username` from `GATEWAY_DEV_USER` env var (default: `dev.operator`), `roles: ["developer"]`, `subject: "dev"`
- this synthetic identity is clearly marked in logs (`authenticated: false, synthetic: true`)
- the dev Kustomize overlays set `GATEWAY_DEV_USER=demo.operator` explicitly, making the dev-only nature visible in deployment config
- there is no code path that silently falls back to a hardcoded user without logging

### R-5: Contract and CI enforcement

Acceptance criteria:

- identity-broker tests validate: token issuance, JWKS endpoint format, token expiry, malformed token rejection
- gateway tests validate: local verification (valid token → 200, expired → 401, missing when required → 401, synthetic when optional → 200 with dev identity)
- a new `identity-token.schema.json` in `shared/shared-contracts` documents the JWT claim set
- CI continues to pass for all three Python products
- the existing SPEC-001/SPEC-002 regression tests (auth enforcement, role logging, session integrity, contract alignment) continue passing

## Non-Goals

- external IdP integration (Keycloak, Auth0, Azure AD) — the JWKS pattern makes this a future config swap
- token revocation lists or refresh tokens — short TTL (15 min) is sufficient for the current phase
- mTLS or service-to-service authentication (gateway → agent-service trust is network-level for now)
- RBAC / policy enforcement / role-based denial — that is B2, a separate spec
- portal login UI changes — the portal already sends `Authorization: Bearer`; it just receives a real JWT now
- renaming or restructuring identity-broker's existing route paths

## Impact

- products touched: `products/identity-broker` (JWT issuer + JWKS), `products/tool-gateway` (local verification middleware, remove per-request introspection)
- contracts touched: new `identity-token.schema.json` in `shared/shared-contracts`
- dependencies added: `PyJWT[crypto]` (identity-broker + tool-gateway), `cryptography` (transitive)
- deployment impact: dev overlays gain `IDENTITY_JWT_PRIVATE_KEY_PATH` (or rely on ephemeral dev key); `DEFAULT_USER_ID` entries removed; `GATEWAY_DEV_USER` added
- living state docs to update on delivery: root `README.md`, `products/identity-broker/README.md`, `products/tool-gateway/README.md`, `CHANGELOG.md`

## Open Questions

None — all resolved (see Changelog).

## Changelog

- 2026-07-28: created as `draft` addressing risk B1
- 2026-07-28: resolved open questions — (1) dev key persists to a git-ignored local file at the configured path; production uses a K8s Secret at the same path; same code, different provisioning; (2) `iss` claim is always validated against `IDENTITY_TOKEN_ISSUER`, no dev bypass; status → `approved`
- 2026-07-28: implementation started; status → `in-progress`
- 2026-07-28: all requirements implemented and verified (92 tests passing); status → `delivered`
