# SPEC-001: Release 1 Platform Hardening

## Status

- status: `delivered`
- owner: workspace maintainers
- created: 2026-07-28
- release slice: `Release 1` preparation (post-`Release 0` hardening)
- related ADRs: `ADR-0001`

## Summary

Close the security, session-integrity, contract-enforcement, and resilience gaps identified in the post-`Release 0` code review, and add CI so these guarantees stay enforced mechanically.

## Motivation

The `Release 0` review (2026-07-28) found issues that are acceptable in a development sandbox but block any environment beyond it:

- the gateway resolves identity by fallback (`payload` → `X-User-ID` header → default user), so unauthenticated callers can act as any user
- roles resolved by `identity-broker` are never enforced anywhere
- the transitional runtime shares one agent instance across all sessions and users, and adopts arbitrary client-supplied session IDs
- `shared/shared-contracts` schemas exist but no service validates against them; malformed payloads surface as `500` errors
- backend resolution re-probes on every request and the transitional chat path has an unbounded timeout
- no CI exists, so tests, overlay render checks, and doc consistency rely on manual discipline

## Requirements

### R-1: Gateway authentication enforcement

`tool-gateway` supports a required-authentication mode controlled by `GATEWAY_REQUIRE_AUTH`. When enabled, session and chat routes reject requests without a valid bearer-backed identity, and the `user_id` fallback chain (payload, header, default) is disabled.

Acceptance criteria:

- with `GATEWAY_REQUIRE_AUTH=true`, unauthenticated calls to `POST /api/v1/sessions`, `GET /api/v1/sessions/{id}`, `POST /api/v1/chat`, and `GET /api/v1/chat/stream` return `401`
- with `GATEWAY_REQUIRE_AUTH=true`, `user_id` from request payloads and `X-User-ID` headers is ignored; only the authenticated username is used
- with `GATEWAY_REQUIRE_AUTH=false` (development), current behavior is preserved and the resolved mode is visible in structured logs
- the default when unset is `false`; flipping the default to `true` is the final acceptance step when `Release 1` closes
- the `dev-k8s-transitional` and `dev-k8s-native` overlays set the flag explicitly (`false`) so the choice is Git-diffable
- unit tests cover both modes

### R-2: Role propagation baseline

Authenticated identity resolution exposes normalized roles to the gateway request path, and role context is recorded in structured logs, preparing for `policy-center` enforcement without implementing the full authorization matrix yet. R-2 is observation-only: no allow/deny decisions are made from roles.

Acceptance criteria:

- `session_created`, `session_retrieved`, `chat_completed`, and `chat_stream_started` log events include the authenticated user's roles when available
- the gateway rejects authenticated requests whose identity payload is missing the `username` field with a `502`-class error instead of an unhandled `KeyError`
- unit tests cover role propagation and the malformed-identity case

### R-3: Session integrity in the transitional runtime

`agent-platform` stops adopting arbitrary client-supplied session IDs, scopes sessions to their owning user, bounds the in-memory store, and isolates agent conversation state per session.

Acceptance criteria:

- requesting an unknown `session_id` on chat or session routes returns `404` instead of silently creating a session with that ID
- a session created by one `user_id` is not readable or continuable by a different `user_id` (`403` or `404`)
- the in-memory session store enforces a TTL and a maximum entry count, both configurable by environment variables
- the transitional kernel keys agent instances by `session_id` so conversation state never crosses sessions; a regression test proves two sessions do not share memory
- the in-memory store limitation (single replica, non-persistent) is documented in the product `README.md`

### R-4: Contract enforcement at the gateway

`tool-gateway` validates request bodies with `pydantic` models kept in sync with `shared/shared-contracts` schemas, and contract tests bind the two together.

Acceptance criteria:

- `POST /api/v1/chat` and `POST /api/v1/sessions` reject malformed bodies with `422` (never `500`); a missing `message` field no longer raises `KeyError`
- contract tests validate the gateway request/response models against `chat-request.schema.json`, `chat-response.schema.json`, and `session.schema.json`; a schema/model mismatch fails the test suite
- `identity-context.schema.json` is validated against the identity payload consumed by the gateway (fixes the untyped `identity["username"]` access)

### R-5: Gateway resilience

Backend mode resolution is cached and outbound timeouts are bounded.

Acceptance criteria:

- in `auto` mode, backend resolution is cached with a configurable TTL; steady-state chat requests do not re-probe the agent service every call
- the transitional non-streaming chat path uses a bounded read timeout aligned with `CHAT_RESPONSE_TIMEOUT_SECONDS` instead of `timeout=None`
- streaming paths keep unbounded read while retaining bounded connect timeouts
- the `core` → `services` import inversion in `api_gateway/core/config.py` is removed; backend context types move to a layer `core` may depend on

### R-6: CI baseline and living-doc alignment

GitHub Actions enforce tests and overlay rendering, and stale living state docs are corrected.

Acceptance criteria:

- a workflow runs `uv run pytest` for `agent-platform`, `tool-gateway`, and `identity-broker` on pull requests and pushes to `main`
- a workflow renders (`kustomize build`) both development overlays and fails on error
- the root `README.md` current-state section reflects the implemented `Release 0` platform and links the SDD workflow
- the `tool-gateway` product `README.md` states its current transitional role (portal/API gateway) versus the documented target role (tool and connector gateway), with a pointer to the workspace-model description

## Non-Goals

- `policy-center` implementation and full authorization-matrix enforcement (later release slice)
- persistent session storage (Redis or database) for the transitional runtime — deferred; the native runtime already delegates session state
- approval workflows, execution runtime, and skills ingestion
- renaming the `tool-gateway` product directory or the `api_gateway` package (decision deferred to a future ADR)
- portal token-storage hardening beyond the current demo scope
- role-based denial (including `read-only-observer` restrictions) — all allow/deny semantics land with `policy-center` so authorization logic stays in one product

## Impact

- products touched: `products/tool-gateway`, `products/agent-platform`, `products/identity-broker` (contract test only), `shared/platform-ops/gitops`
- contracts touched: consumed (not modified): `chat-request`, `chat-response`, `session`, `identity-context` schemas
- identity / policy / audit / execution safety impact: strengthens identity enforcement and audit attribution at the gateway; no trust-zone changes
- living state docs to update on delivery: root `README.md`, `products/tool-gateway/README.md`, `products/agent-platform/README.md`, `CHANGELOG.md`

## Open Questions

None — all resolved (see Changelog).

## Changelog

- 2026-07-28: created as `draft` from the post-`Release 0` code review findings
- 2026-07-28: resolved open questions — `GATEWAY_REQUIRE_AUTH` defaults to `false` until `Release 1` closes (then flips to `true`); R-2 stays observation-only and all denial semantics defer to `policy-center`; status → `approved`
- 2026-07-28: implementation started; status → `in-progress`
- 2026-07-28: all requirements implemented and validated (`agent-platform` 44, `identity-broker` 11, `tool-gateway` 41 tests passing; both overlays render); status → `delivered`. Outstanding release-close step (not spec scope): flip `GATEWAY_REQUIRE_AUTH` default to `true` after live validation of the auth-required path against the dev overlay
