# SPEC-003 Plan: Identity Trust Hardening

> Finalized 2026-07-28 alongside spec approval; open questions resolved in the spec changelog.

## Approach

Work issuer-first: identity-broker gains JWT issuance + JWKS (R-1), then the gateway switches to local verification (R-2), identity propagation is tightened (R-3), and the dev fallback is hardened (R-4). Tests and contract schema (R-5) land alongside each step.

## Design Per Requirement

### R-1: identity-broker as JWT issuer

- affected: `products/identity-broker/src/identity_service/`
- new module: `services/token_service.py` — owns key lifecycle (load/generate/persist), JWT signing, JWKS serialization
- key loading logic:
  - `IDENTITY_JWT_PRIVATE_KEY_PATH` set + file exists → load PEM
  - path set + file missing → generate RSA 2048, write PEM to path (dev first-boot), log warning
  - path not set → generate ephemeral in-memory key (CI/tests), log insecure warning
- `kid` derived from a SHA-256 thumbprint of the public key (deterministic, survives restarts with persisted key)
- new routes:
  - `POST /api/v1/auth/token` — accepts `{username}` (dev) or extracts from existing session; returns `{access_token, token_type: "bearer", expires_in}`
  - `GET /.well-known/jwks.json` — returns `{"keys": [{kty, kid, use, n, e}]}`
- existing `/auth/callback` updated to include `access_token` in its response alongside the identity context
- config additions: `IDENTITY_JWT_PRIVATE_KEY_PATH`, `IDENTITY_TOKEN_TTL_SECONDS` (default 900), `IDENTITY_TOKEN_ISSUER` (default `luban-identity-broker`)
- dependency: `PyJWT[crypto]>=2.8,<3.0` added to `pyproject.toml`
- alternatives: ECDSA (P-256) instead of RSA — viable but RSA has broader library/tooling support and JWKS examples; deferred consideration

### R-2: Gateway local JWT verification

- affected: `products/tool-gateway/src/api_gateway/`
- new module: `services/token_verifier.py` — wraps `jwt.PyJWKClient` for JWKS fetch/cache + `jwt.decode` for verification
- verification validates: signature (via JWKS public key), `exp`, `iss` (against `IDENTITY_TOKEN_ISSUER`)
- the existing `resolve_authenticated_identity` / `fetch_current_identity` functions (which call identity-broker per request) are replaced by the local verifier
- `IdentityContext` is now constructed from JWT claims directly (no network call)
- config additions: `IDENTITY_JWKS_URL` (default `http://identity-service:8000/.well-known/jwks.json`), `IDENTITY_JWKS_CACHE_SECONDS` (default 300), `IDENTITY_TOKEN_ISSUER` (default `luban-identity-broker`)
- config removals: none yet (identity_service_url stays for login flow endpoints)
- dependency: `PyJWT[crypto]>=2.8,<3.0` added to gateway `pyproject.toml`
- alternatives: `python-jose` — rejected; PyJWT is more actively maintained and has native `PyJWKClient`

### R-3: Verified identity propagation

- affected: `api_gateway/core/request_context.py`, `api_gateway/api/routes/chat.py`, `api_gateway/api/routes/sessions.py`
- `resolve_user_id` simplified: if a verified identity exists, its `username` claim is the user_id — caller-supplied `X-User-ID` and body `user_id` are ignored
- when no verified identity exists and auth is not required, the synthetic dev identity (R-4) provides the username
- the `user_id` field in `ChatRequest` and `CreateSessionRequest` gateway schemas becomes ignored (kept for backward compat but not used for identity resolution)
- structured logs include `authenticated: true/false`, `synthetic: true/false`, `sub`, `roles`

### R-4: Dev fallback hardening

- affected: `api_gateway/core/config.py`, overlay env files
- `DEFAULT_USER_ID` removed from `GatewaySettings`
- new setting: `GATEWAY_DEV_USER` (default: `dev.operator`) — used only when `GATEWAY_REQUIRE_AUTH=false` AND no bearer token present
- synthetic identity: `IdentityContext(subject="dev", username=<GATEWAY_DEV_USER>, roles=["developer"], groups=[])`
- all synthetic identity usage logs `synthetic: true` at INFO level
- overlay `runtime-config.env` files: remove `DEFAULT_USER_ID`, add `GATEWAY_DEV_USER=demo.operator`

### R-5: Contract and CI enforcement

- affected: `shared/shared-contracts/schemas/`, tests in both products
- new schema: `identity-token.schema.json` documenting the JWT claim set (for documentation/validation, not wire transport)
- identity-broker tests: token issuance returns valid JWT, JWKS endpoint returns RFC 7517 format, expired token is distinguishable, malformed token rejected
- gateway tests: valid token → verified identity, expired → 401, wrong issuer → 401, missing when required → 401, missing when optional → synthetic identity
- regression: all SPEC-001/002 tests pass (session integrity, contract alignment, role logging)

## Sequencing And Dependencies

1. R-1 (issuer) — no dependencies; the JWKS endpoint must exist before the gateway can verify
2. R-2 + R-3 + R-4 (gateway changes) — depends on 1; implemented together as they're tightly coupled
3. R-5 (tests + schema) — lands alongside 1 and 2

## Test Strategy

- unit tests: token_service key loading, JWT signing/verification, JWKS serialization
- integration tests: TestClient hitting identity-broker's token + JWKS endpoints; gateway verifying a real token issued by the test fixture
- regression: existing auth enforcement, role logging, session integrity, contract alignment tests must pass unchanged (or with minimal fixture updates for the new identity model)

## Rollout And Migration

- identity-broker changes are additive (new endpoints); existing endpoints preserved
- gateway changes replace the verification mechanism but preserve route behavior (same URLs, same response shapes)
- the portal is unaffected (it already sends `Authorization: Bearer`; it just gets a real JWT from the login flow now)
- rollback: reverting gateway to SPEC-002 code restores per-request introspection; identity-broker's new endpoints are inert if not called
