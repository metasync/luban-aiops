# SPEC-003 Tasks: Identity Trust Hardening

Task states: `[ ]` pending, `[x]` done. Implementation starts when the spec is `approved`.

## R-1: identity-broker as JWT issuer

- [x] add `PyJWT[crypto]` dependency to `products/identity-broker/pyproject.toml`
- [x] create `services/token_service.py`: RSA key load/generate/persist, JWT signing, JWKS serialization, `kid` thumbprint
- [x] add config settings: `IDENTITY_JWT_PRIVATE_KEY_PATH`, `IDENTITY_TOKEN_TTL_SECONDS`, `IDENTITY_TOKEN_ISSUER`
- [x] add route `POST /api/v1/auth/token` (issues signed JWT for a given username)
- [x] add route `GET /.well-known/jwks.json` (serves public key set, RFC 7517)
- [x] update `/auth/callback` to include `access_token` in response
- [x] add identity-broker tests: token issuance, JWKS format, expiry, key persistence

## R-2: Gateway local JWT verification

- [x] add `PyJWT[crypto]` dependency to `products/tool-gateway/pyproject.toml`
- [x] create `services/token_verifier.py`: `PyJWKClient` setup, `verify_token()` → `IdentityContext`
- [x] add gateway config: `IDENTITY_JWKS_URL`, `IDENTITY_JWKS_CACHE_SECONDS`, `IDENTITY_TOKEN_ISSUER`
- [x] replace `fetch_current_identity` / per-request introspection with local `verify_token()`
- [x] validate `iss` claim against `IDENTITY_TOKEN_ISSUER`; reject mismatch with 401

## R-3: Verified identity propagation

- [x] simplify `resolve_user_id`: verified identity `username` claim wins; caller headers ignored
- [x] update chat/sessions routes to use verified identity for `X-User-ID` forwarding
- [x] structured logs include `authenticated`, `synthetic`, `sub`, `roles`

## R-4: Dev fallback hardening

- [x] remove `DEFAULT_USER_ID` from `GatewaySettings` and all code paths
- [x] add `GATEWAY_DEV_USER` setting (default: `dev.operator`)
- [x] inject synthetic `IdentityContext` when auth optional + no token; log `synthetic: true`
- [x] update overlay `runtime-config.env` files: remove `DEFAULT_USER_ID`, add `GATEWAY_DEV_USER`

## R-5: Contract and CI enforcement

- [x] create `identity-token.schema.json` in `shared/shared-contracts/schemas/`
- [x] gateway tests: valid token → 200, expired → 401, wrong issuer → 401, missing+required → 401, missing+optional → synthetic
- [x] verify CI passes for all three products
- [x] confirm SPEC-001/002 regression tests pass (auth, roles, sessions, contracts)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (root README, identity-broker README, tool-gateway README, CHANGELOG)
- [x] `CHANGELOG.md` entry added referencing `SPEC-003`
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
