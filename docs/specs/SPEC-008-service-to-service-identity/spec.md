# SPEC-008: Service-to-Service Identity — Broker-Mediated Token Delegation

## Status

- status: `approved`
- owner: workspace maintainers
- created: 2026-07-30
- release slice: `Release 1` (read-only operations copilot)
- related ADRs: ADR-0004 (broker-mediated token delegation), ADR-0003 (platform-owned agent service contract)

## Summary

Give `agent-platform` a least-privilege credential for its loopback calls to `tool-gateway` by having the gateway exchange the verified user token for a short-lived, audience-bound delegated token that `agent-platform` relays as a bearer token. This unblocks the authenticated end-to-end tool path (SPEC-007 R-4/R-6) without placing the user's broad credential in the least trustworthy process, and it establishes the service-to-service identity pattern the rest of the platform will reuse.

## Motivation

SPEC-007 delivered the tool execution framework, but its authenticated end-to-end path does not work: the gateway forwards only `x-request-id` and `X-User-ID` to `agent-platform`, so the agent holds no credential to present when calling `POST /api/v2/tools/invoke` or `GET /api/v2/tools` back through the gateway. With `GATEWAY_REQUIRE_AUTH=true` every such call returns `401`, and the graceful-degradation path silently leaves the agent with an empty Toolkit. This is recorded as SPEC-007 open question Q-1 and blocks R-4 and R-6.

ADR-0004 decides the model: broker-mediated delegation, not token pass-through and not a service-self-signed assertion. This spec implements that decision. It also closes a latent weakness the decision depends on — platform JWTs carry no `aud` claim, so any token is replayable at any service that trusts the issuer.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Audience binding on platform JWTs

Platform JWTs are bound to an intended recipient so they cannot be replayed across services.

Acceptance criteria:

- `identity-broker` `issue_token` accepts a target audience and emits an `aud` claim; portal-issued tokens carry `aud: ["tool-gateway"]` (the gateway is the only direct consumer of user tokens today)
- the gateway's `verify_token` validates `aud` against a configured expected audience (`GATEWAY_TOKEN_AUDIENCE`, default `tool-gateway`) and rejects tokens whose `aud` does not include it with `401`
- `aud` is added to the `require` list in the gateway verifier and to `identity-token.schema.json`
- tokens minted before this change (no `aud`) are rejected once enforcement is on — there is no silent accept-missing-audience path in a `GATEWAY_REQUIRE_AUTH=true` deployment
- the JWKS verification path (signature, `exp`, `iss`) is otherwise unchanged

### R-2: Token exchange endpoint on identity-broker

`identity-broker` mints delegated tokens for authenticated service callers.

Acceptance criteria:

- a new `POST /api/v1/auth/exchange` endpoint accepts a service credential plus a `subject_token` (the user's verified JWT) and a requested `audience`
- the caller must present a valid service credential (R-3); an exchange request without one is rejected with `401` regardless of the `subject_token`
- the `subject_token` is verified (signature, `exp`, `iss`) before any delegated token is minted; an invalid or expired subject token yields `401`
- the minted delegated token carries: `sub` and `username` copied from the subject token, `roles` copied from the subject token (never elevated), `act` naming the calling service, `aud` equal to the requested audience, `iss` equal to the platform issuer, and a short TTL (`IDENTITY_DELEGATED_TOKEN_TTL_SECONDS`, default 300)
- the requested `audience` must be in a configured allow-list of audiences the calling service may request; a disallowed audience yields `400`
- the endpoint never mints a delegated token whose roles exceed the subject token's roles
- exchange events are logged with the calling service, the subject, and the requested audience

### R-3: Service credential for the gateway

The gateway authenticates to the exchange endpoint as a known service.

Acceptance criteria:

- the gateway holds a service credential (`GATEWAY_SERVICE_CLIENT_ID`, `GATEWAY_SERVICE_CLIENT_SECRET`) loaded from environment / K8s Secret
- the identity-broker validates the credential against a configured registry of service clients, each with an allow-list of audiences it may request
- the credential confers no user authority on its own — it only authorizes the exchange operation
- a missing or invalid credential yields `401` on the exchange endpoint
- the secret is provisioned via the dev-k8s overlay as a K8s Secret, not committed to the repository
- a static, audience-scoped client secret is the deliberate Release-1 root of trust for the gateway's service identity; Kubernetes workload-identity-bound short-lived tokens are the documented upgrade path, to be adopted once for all services rather than bespoke per-service plumbing

### R-4: Gateway performs delegation on the agent-service contract

The gateway exchanges the user token and forwards the delegated token to `agent-platform`.

Acceptance criteria:

- on a chat request with a verified user identity, the gateway obtains a delegated token (audience `tool-gateway`, `act: agent-platform`) and forwards it to `agent-platform` as `Authorization: Bearer`
- `x-request-id` continues to be forwarded; `X-User-ID` is retained for backward compatibility but is no longer the identity source of truth for the agent's downstream calls
- the delegated token is cached in the gateway keyed by the user subject and reused until near expiry, so the exchange happens at most once per user per TTL window per gateway replica, not per request (the token's authority is per-user, so it is interchangeable across that user's sessions; the gateway does not reach into agent-platform's session store)
- the delegated token TTL is configured shorter than the user token TTL (default 300s < 900s) so an active user's tool capability never gaps; re-exchange is driven by the incoming chat request and uses that request's user token, so no separate refresh mechanism is required and the tool path's lifetime equals the portal session's lifetime
- on exchange failure the chat request still succeeds (the agent simply runs without tools) and the failure is logged and counted; delegation failure never breaks chat
- when `GATEWAY_REQUIRE_AUTH=false` and a synthetic dev identity is in use, the gateway mints a delegated token for the synthetic identity through the same path (no special bypass)

### R-5: agent-platform relays the delegated token

`agent-platform` presents the delegated token on its tool calls and stops carrying identity in the request body.

Acceptance criteria:

- `discover_tools` and `invoke_gateway_tool` send `Authorization: Bearer <delegated token>` when a token is available
- the toolkit is built with the owning user's delegated token bound into its closures, so one user's credential is never used for another user's session
- the `identity_context` field is removed from the invoke request body; identity is carried exclusively by the bearer token
- when no delegated token is available, tool discovery degrades to an empty Toolkit (existing behavior) and invocation returns a structured error result, never an unhandled exception

### R-6: Gateway tool routes derive identity from the token only

The gateway's tool surface trusts only the verified token and enforces audience.

Acceptance criteria:

- `invoke_tool` resolves identity solely from the verified bearer token; any `identity_context` in the request body is ignored (and the field is removed from the request contract)
- `GET /api/v2/tools` requires authentication and is gated by a `tools:list` policy action (closes SPEC-007 Q-2)
- `POST /api/v2/tools/invoke` continues to be gated by `tools:invoke`
- the policy bundle gains a `tools:list` rule granting the same roles as `tools:invoke`
- a request whose token audience is not `tool-gateway` is rejected before policy evaluation
- audit logs record both the human subject (`sub`) and the acting service (`act`)

### R-7: Contracts, tests, overlays, observability

The change is covered by contracts, tests, deployment config, and metrics.

Acceptance criteria:

- `identity-token.schema.json` documents `aud` and `act`; a `delegated-token` note distinguishes delegated from portal tokens
- a contract test binds the gateway and identity-broker models to the updated schema
- identity-broker tests cover: exchange success, missing credential → 401, invalid subject token → 401, disallowed audience → 400, roles never elevated
- gateway tests cover: audience enforcement (valid aud → 200, wrong/missing aud → 401), delegation forwarding, per-user caching, exchange-failure degradation, `tools:list` denial for unauthorized roles
- agent-platform tests cover: bearer token sent on invoke and discovery, empty-Toolkit degradation without a token
- the dev-k8s overlay provisions the gateway service secret and sets `GATEWAY_TOKEN_AUDIENCE`, `GATEWAY_SERVICE_CLIENT_ID`, and the identity-broker client registry; `kustomize build` renders without errors
- metrics record exchange attempts/failures and delegated-token cache hits/misses

## Non-Goals

- mTLS / SPIFFE workload identity between services — future sender-constraining hardening on top of this decision (ADR-0004), not part of it
- token revocation lists or refresh of delegated tokens — the short TTL and per-user re-exchange are sufficient for this phase
- delegating authority for mutating tools — SPEC-007 is read-only; action tools and their approval gating belong to Release 4
- log redaction before tool output reaches the model provider — tracked separately as SPEC-007 Q-3
- a general policy dimension keyed on the calling service — `act` is logged and available, but policy decisions remain keyed on user roles for now

## Impact

- products touched: `products/identity-broker` (exchange endpoint, service-client registry, `aud`/`act` claims), `products/tool-gateway` (audience verification, delegation client, per-user token cache, tool-route identity source, `tools:list` action), `products/agent-platform` (bearer relay, remove body identity)
- contracts touched: `identity-token.schema.json` (add `aud`, `act`), agent-service contract header note (gateway now sends `Authorization` downstream), `policy-default.yaml` (add `tools:list`)
- identity / policy / audit / execution safety impact: strengthens the trust model — tokens become audience-bound, the agent holds only a short-lived least-privilege credential, and audit gains separate human/service attribution; no deny-by-default rule is relaxed
- living state docs to update on delivery: root `README.md`, `products/identity-broker/README.md`, `products/tool-gateway/README.md`, `products/agent-platform/README.md`, `CHANGELOG.md`, `docs/agentic-aiops-platform/identity-and-authorization-design.md` (mark the Service Identity Model as implemented)

## Open Questions

None — both resolved (see Changelog).

## Changelog

- 2026-07-30: created as `draft`, implementing ADR-0004 and closing SPEC-007 Q-1/Q-2
- 2026-07-30: resolved the delegated-token lifetime question — per-user TTL cache with re-exchange driven by the incoming request's user token; delegated TTL (300s) kept shorter than the user token TTL (900s) so an active user never gaps and no refresh mechanism is needed (the portal already sends a fresh token on every request and refreshes it ahead of expiry)
- 2026-07-30: resolved the service-credential question — a static, audience-scoped client secret for Release 1 (it confers no user authority, since the exchange still requires a valid user token, so its blast radius is already narrow), with Kubernetes workload-identity-bound short-lived tokens as the documented upgrade path to be done once for all services at the first non-dev deployment or at Release 4
- 2026-07-30: approved by workspace maintainers and ADR-0004 accepted; implementation may begin, sequenced issuer-first per `plan.md` (R-1 → R-2/R-3 → R-4/R-6 → R-5, with R-7 alongside)
