# SPEC-008 Plan: Service-to-Service Identity — Broker-Mediated Token Delegation

> Drafted 2026-07-30 alongside the spec; implements ADR-0004. The spec's two open questions are resolved (see spec Changelog); the spec is ready for approval review.

## Approach

Work issuer-first, mirroring SPEC-003. Stage 1 makes tokens audience-bound (R-1) — a standalone, low-risk slice that closes a latent replay weakness and is a hard precondition for delegation. Stage 2 adds the exchange capability and the service credential to identity-broker (R-2, R-3). Stage 3 wires the gateway to exchange-and-forward with a per-user token cache (R-4) and turns the tool routes to token-only identity with a `tools:list` action (R-6). Stage 4 makes agent-platform a pure bearer relay (R-5). Contracts, tests, overlays, and metrics (R-7) land alongside each stage.

The design reuses the existing RS256 signing key and JWKS verification path end to end; no new trust root is introduced. The one new secret (the gateway service credential) is scoped to the exchange operation only.

## Design Per Requirement

### R-1: Audience binding on platform JWTs

- affected: `products/identity-broker/src/identity_service/services/token_service.py`, `products/tool-gateway/src/api_gateway/services/token_verifier.py`, `products/tool-gateway/src/api_gateway/core/config.py`, `shared/shared-contracts/schemas/identity-token.schema.json`
- `issue_token` gains an `audience: str | list[str]` parameter and emits `aud`; the login/callback path passes `aud=["tool-gateway"]`
- `verify_token` adds `audience=settings.gateway_token_audience` to `jwt.decode` and `"aud"` to the `require` list; PyJWT raises `InvalidAudienceError` on mismatch, mapped to `401`
- new gateway setting `GATEWAY_TOKEN_AUDIENCE` (default `tool-gateway`)
- schema gains `aud` (required) and `act` (optional, object) — see R-7
- alternatives: make `aud` optional during a transition window — rejected for `GATEWAY_REQUIRE_AUTH=true` deployments; a silent accept-missing-audience path would leave the replay weakness open exactly where auth is enforced

### R-2: Token exchange endpoint on identity-broker

- affected: `products/identity-broker/src/identity_service/` — new `services/exchange_service.py`, new route under `api/routes/auth.py`, config additions
- `POST /api/v1/auth/exchange` body: `{subject_token, audience}`; service credential presented via HTTP Basic (`client_id:client_secret`) — resolved to a static scoped client secret, see spec Changelog
- flow: authenticate service client (R-3) → verify `subject_token` locally (reuse the JWKS verifier logic; the broker holds its own private key so it can verify directly) → check `audience` is in the client's allow-list → mint delegated token
- delegated claims: `sub`, `username`, `roles` copied verbatim from the subject token; `act = {"sub": <client_id>}` (RFC 8693 actor shape); `aud = audience`; `iss = IDENTITY_TOKEN_ISSUER`; `iat`/`exp` from `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS` (default 300)
- roles are copied, never recomputed or elevated — the exchange cannot grant authority the subject token lacks
- config: `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS`, `IDENTITY_SERVICE_CLIENTS` (registry mapping client_id → {secret ref, allowed audiences})
- alternatives: OAuth 2.0 Token Exchange (RFC 8693) full grant types — adopted in spirit (`subject_token`, `act`, `aud`) but scoped to the single delegation grant we need; full federation deferred

### R-3: Service credential for the gateway

- affected: `products/identity-broker` (client registry + validation), `products/tool-gateway/src/api_gateway/core/config.py`, dev-k8s overlay
- gateway settings: `GATEWAY_SERVICE_CLIENT_ID`, `GATEWAY_SERVICE_CLIENT_SECRET`
- broker validates the credential against `IDENTITY_SERVICE_CLIENTS`; each entry pins the audiences that client may request (gateway → `["tool-gateway"]`)
- the secret is mounted from a K8s Secret created in the overlay; a placeholder/generator is used for dev first-boot, never a committed value
- this is the one symmetric secret in the platform; it is deliberately scoped to the exchange endpoint and documented as such
- alternatives: a short-lived service JWT bootstrapped from Kubernetes workload identity is genuinely stronger (no extractable long-lived secret) but is the deferred SPIFFE/workload-identity work (ADR-0004); a short-lived JWT bootstrapped from a static secret adds a round trip for no real gain. Static scoped secret chosen for Release 1 — revisit once for all services at the first non-dev deployment or at R4

### R-4: Gateway performs delegation on the agent-service contract

- affected: `products/tool-gateway/src/api_gateway/services/` — new `delegation_client.py`, changes to `agent_client.py` and the chat route, a gateway-side token cache
- `delegation_client.exchange(settings, subject_token)` calls the broker exchange endpoint and returns the delegated token
- a gateway-side TTL cache stores `{token, expires_at}` keyed by the user subject; the token's authority is per-user, so it is reused across that user's sessions. In-memory per replica is sufficient for this phase (worst case one exchange per replica per user per TTL); a Redis-backed cache is an optional later step only if the gateway gains a cache backend. The gateway deliberately does not use agent-platform's SPEC-006 session store — that would cross the product boundary
- `agent_client._headers` adds `Authorization: Bearer <delegated token>` when one is available; `x-request-id` and `X-User-ID` retained
- exchange failure is non-fatal: log + counter, proceed without a token (agent runs tool-less); chat must never fail because delegation failed
- synthetic dev identity goes through the same exchange path (the broker mints a delegated token for the synthetic subject) — no bypass branch
- alternatives: exchange lazily at first tool call inside agent-platform — rejected; keeps the user token (or a broad credential) reachable from the least trustworthy process and splits the trust logic across two services. Exchanging at the gateway keeps agent-platform a dumb relay

### R-5: agent-platform relays the delegated token

- affected: `products/agent-platform/src/agent_service/tools/gateway_tools.py`, `runtime_kernel.py`
- `discover_tools` and `invoke_gateway_tool` accept and send `Authorization: Bearer <token>`
- the toolkit is built with the owning user's delegated token bound into its closures, so one user's credential is never used for another user's session
- remove `identity_context` from the invoke payload entirely
- no-token path: discovery returns `[]` (existing behavior); invoke returns a structured error result, never raises

### R-6: Gateway tool routes derive identity from the token only

- affected: `products/tool-gateway/src/api_gateway/services/gateway_service.py`, `api/routes/tools.py`, `services/policy_engine.py`, `shared/shared-contracts/policies/policy-default.yaml` (+ the three byte-identical copies)
- `invoke_tool` already resolves identity from the verified token; remove the unused `identity_context` body field from the request contract and document that body identity is never trusted
- `GET /api/v2/tools` gains authentication + a `tools:list` policy check via the existing `enforce_policy` path
- policy bundle adds an `allow-operators-tools-list` rule mirroring `allow-operators-tools` roles for the `tools:list` action; all four copies stay byte-identical (enforced by the existing sync test)
- audience is enforced by the verifier (R-1) before policy runs
- audit log adds `act` alongside `sub`

### R-7: Contracts, tests, overlays, observability

- affected: `shared/shared-contracts/schemas/identity-token.schema.json`, contract tests in all three products, overlay env + Secret, metrics modules
- schema: add `aud` (array of string, required) and `act` (object, optional, RFC 8693 actor); note distinguishing delegated vs portal tokens
- metrics: identity-broker `token_exchange_total{result}`; gateway `delegation_exchange_total{result}` and `delegation_cache_total{result=hit|miss}`
- overlay: gateway service Secret + `GATEWAY_TOKEN_AUDIENCE`, `GATEWAY_SERVICE_CLIENT_ID`; broker `IDENTITY_SERVICE_CLIENTS`, `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS`

## Sequencing And Dependencies

1. R-1 (audience binding) — no dependencies; standalone slice, closes the replay weakness and is required by everything below
2. R-2 + R-3 (exchange endpoint + service credential) — depends on 1; broker-side, implemented together
3. R-4 + R-6 (gateway delegation + tool-route identity) — depends on 2; gateway-side
4. R-5 (agent-platform relay) — depends on 3; can be developed against a stubbed delegated token
5. R-7 (contracts, tests, overlays, metrics) — lands alongside each stage; the four-copy policy sync test and contract tests gate delivery

## Test Strategy

- unit tests: `issue_token` audience emission; `verify_token` audience accept/reject; exchange service (credential auth, subject verification, audience allow-list, role non-elevation); delegation client + gateway cache hit/miss/expiry keyed by subject
- integration tests: gateway TestClient exercising audience enforcement end to end; broker exchange endpoint via TestClient with a real issued subject token; agent-platform relay sending the bearer header
- contract tests: gateway and identity-broker models validated against the updated `identity-token.schema.json`; policy bundle four-copy byte-identity
- regression: all SPEC-003/004/007 tests continue passing; in particular the SPEC-007 invoke tests must be re-pointed from monkeypatched identity to a real delegated-token flow so the auth path is genuinely exercised (the gap that hid the original 401)
- overlay validation: `kustomize build` renders for all overlays with the new Secret and env

## Rollout And Migration

- R-1 is a breaking contract change for any consumer that mints/verifies tokens without `aud`; sequence it so the broker emits `aud` before the gateway enforces it, and ship both in the same release slice to avoid a window of rejected tokens
- the exchange endpoint and service credential are additive; the gateway only starts forwarding a delegated token once R-4 lands
- agent-platform changes are backward compatible: with no token it degrades to the current empty-Toolkit behavior
- rollback: reverting the gateway to pre-SPEC-008 restores the (broken) unauthenticated loopback; reverting R-1 alone requires reverting the broker's `aud` emission in the same step
- the dev overlay's `GATEWAY_REQUIRE_AUTH=true` stays on throughout; this spec is what makes that default actually work end to end
