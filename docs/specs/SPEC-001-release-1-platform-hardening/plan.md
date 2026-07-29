# SPEC-001 Plan: Release 1 Platform Hardening

> Finalized 2026-07-28 alongside spec approval; open questions resolved in the spec changelog.

## Approach

Work in three stages: gateway identity hardening first (R-1, R-2), then runtime session integrity (R-3), then contracts, resilience, and CI (R-4, R-5, R-6). Each stage is independently shippable and validated by its own tests.

## Design Per Requirement

### R-1: Gateway authentication enforcement

- affected: `api_gateway/core/config.py`, `api_gateway/core/request_context.py`, session/chat routes
- add `require_auth: bool` to `GatewaySettings` (env `GATEWAY_REQUIRE_AUTH`, default `false` until Release 1 closes)
- introduce a shared dependency that resolves identity once per request and raises `401` when auth is required and missing
- alternatives: FastAPI global middleware — rejected; per-route dependency keeps health/auth routes exempt without path lists

### R-2: Role propagation baseline

- affected: `api_gateway/services/gateway_service.py`, route log events
- parse the identity payload into a typed model (see R-4) exposing `username` and `roles`
- log `roles` in existing structured events; return `502` on malformed identity payloads

### R-3: Session integrity in the transitional runtime

- affected: `agent_service/services/session_store.py`, `session_service.py`, `runtime_service.py`, `runtime_kernel.py`
- split `ensure_session` into `create_session` (server-generated IDs only) and `get_owned_session(session_id, user_id)` returning `404`/`403`
- add TTL and max-entry eviction to `SessionStore` (env: `SESSION_TTL_SECONDS`, `SESSION_MAX_ENTRIES`)
- change `AgentKernel` to hold a bounded `dict[session_id, Agent]` cache instead of a single `_agent`; evict with the session store
- alternatives: per-request agent construction — rejected; loses in-conversation memory within a session

### R-4: Contract enforcement at the gateway

- affected: new `api_gateway/schemas/` package, session/chat/identity code paths
- define `pydantic` models for chat request/response, session create, and identity context
- contract tests use `jsonschema` to validate model JSON Schema output compatibility with `shared/shared-contracts/schemas/`
- alternatives: code generation from schemas — rejected for now; four small models do not justify a codegen pipeline (revisit via ADR if schema count grows)

### R-5: Gateway resilience

- affected: `api_gateway/services/agent_backends.py`, `gateway_service.py`, `core/config.py`
- module-level resolution cache keyed by `(agent_service_url, configured_mode)` with TTL (env `BACKEND_RESOLUTION_TTL_SECONDS`, default `30`)
- replace `timeout=None` on the non-streaming chat client with `httpx.Timeout(connect=5, read=chat_response_timeout_seconds)`
- move `AgentBackendContext` and mode literals into `api_gateway/core/backend_context.py`; `services` imports from `core`, never the reverse

### R-6: CI baseline and living-doc alignment

- affected: `.github/workflows/`, root `README.md`, product `README.md` files
- `ci.yml`: matrix over the three Python products, `uv sync --frozen` + `uv run pytest`
- `overlays.yml`: `kustomize build` for both dev overlays
- doc updates as listed in the spec acceptance criteria

## Sequencing And Dependencies

1. R-4 identity/typed models — no dependencies (R-1, R-2 build on it)
2. R-1, R-2 gateway auth and roles — depends on 1
3. R-3 runtime session integrity — independent of 1-2
4. R-5 resilience and layering fix — independent; touches same files as R-1, do after 2 to avoid conflicts
5. R-6 CI and docs — last, so CI lands green over the finished work

## Test Strategy

- unit tests: per-requirement additions in each product's `tests/` directory
- contract tests: new gateway test module binding models to `shared-contracts` schemas
- integration / overlay validation: `kustomize build` in CI; live validation of the auth-required path against the dev overlay before flipping the default

## Rollout And Migration

- both dev overlays gain explicit `GATEWAY_REQUIRE_AUTH` entries (start `false`, flip after live validation)
- session-store eviction and `404`-on-unknown-session are behavior changes for the portal; portal already handles session recreation, no UI change expected
- rollback: all changes are flag-guarded or additive; reverting the overlay flag restores Release 0 behavior
