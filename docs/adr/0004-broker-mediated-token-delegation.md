# ADR-0004: Broker-Mediated Token Delegation for Service-to-Service Calls

## Status

`accepted`

- date: 2026-07-30
- accepted: 2026-07-30
- deciders: workspace maintainers
- related specs: `SPEC-003`, `SPEC-004`, `SPEC-007`, `SPEC-008`

## Context

`agent-platform` calls `tool-gateway` on a loopback path (`POST /api/v2/tools/invoke`, `GET /api/v2/tools`) but holds no credential it can present. The gateway forwards only `x-request-id` and `X-User-ID` downstream (`agent_client._headers`) — never the caller's bearer token — so with `GATEWAY_REQUIRE_AUTH=true` (the Release 1 default) every tool call and discovery request is rejected with `401`, and SPEC-007's graceful-degradation path silently leaves the agent with an empty Toolkit. This blocks SPEC-007 R-4 and R-6.

Three facts constrain the choice:

- `identity-and-authorization-design.md` Principle 5 already commits the platform to "Service identity and human identity are different," names a "Platform Service Identity" for services "when calling each other," and requires audit to record the requester identity and the "service identity used for execution" separately.
- Policy decisions are keyed on `roles` (`policy_engine.evaluate(settings, roles, action)`). Whoever can assert roles can assert `platform-admin`.
- `agent-platform` is the component that processes untrusted user text *and* untrusted tool output (raw pod logs enter the LLM context). It is the most likely place for a prompt injection to become a confused deputy, so it is the least trustworthy holder of a broad credential.

Platform JWTs today carry no `aud` claim (issuer, verifier, and `identity-token.schema.json` all omit it), so any token minted for the portal is replayable at any service that trusts the issuer.

## Decision

Adopt broker-mediated token delegation. Before dispatching to `agent-platform`, the gateway exchanges the already-verified user token at `identity-broker` for a short-lived delegated token: `sub` is the real user, `act` names `agent-platform` as the acting service, `aud` is `tool-gateway`, `roles` are copied from the presented token, and the TTL is short (order of minutes). The gateway forwards that delegated token — not the user's token — and `agent-platform` relays it as `Authorization: Bearer` on its tool calls. `agent-platform` signs nothing and holds no signing key; the identity-broker remains the sole signing authority.

As a precondition, platform JWTs gain an `aud` claim and the gateway enforces it on verification, so tokens are bound to an intended recipient and are not replayable across services.

## Alternatives Considered

- forward the user's access token downstream and re-present it on the tool call — rejected: places the broadest credential (valid for `chat`, `session:create`, `session:read`, `tools:invoke`, 15-minute TTL) in the least trustworthy process; a prompt-injected agent becomes a confused deputy with the user's full authority; contradicts Principle 5; and with no `aud` claim the token is replayable at every service.
- `agent-platform` self-signs an on-behalf-of assertion with a service key the gateway trusts — rejected: an impersonation oracle. Because policy is keyed on `roles`, a component that asserts its own roles can grant itself `platform-admin`; this is strictly weaker than pass-through, where the roles at least come from a broker-signed token the service cannot rewrite.
- mTLS / SPIFFE workload identity between services — deferred: heavier, does not reuse the existing RS256/JWKS machinery, and is disproportionate for a single-namespace dev deployment; kept as a future sender-constraining hardening on top of this decision, not a replacement.
- a "skip auth for internal callers" flag — rejected: breaches the deny-by-default model established by SPEC-004 and removes the trust boundary before a second caller exists.

## Consequences

- a compromised `agent-platform` collapses to: invoke read-only tools, as a user who actually called it, for a few minutes — close to the minimum authority the feature requires
- honors Principle 5: `sub` carries the human requester, `act` carries the service identity, giving audit the separate attribution the design requires
- reuses the existing RS256 signing key and JWKS verification path; no new trust root, no second key hierarchy
- sets the precedent for every future service-to-service hop (execution workers in R4 will follow the same delegation shape)
- cost: the exchange reintroduces a broker call that SPEC-003 deliberately removed from the verification hot path; mitigated by caching one delegated token per user in the gateway (its authority is per-user, not per-session), so the cost is per-user-per-TTL, not per-request
- cost: one new exchange endpoint and one service credential; the credential is a deliberate, scoped exception to the platform's otherwise asymmetric model — it can only request tokens for the `tool-gateway` audience and confers no user authority on its own
- cost: `aud` is a contract change to `identity-token.schema.json` and to issuer/verifier behavior
- follow-up: `SPEC-008` implements this decision and closes SPEC-007 R-4/R-6 and open questions Q-1/Q-2; `SPEC-007` stays `draft` until SPEC-008 lands
