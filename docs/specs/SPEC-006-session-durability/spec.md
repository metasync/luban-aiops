# SPEC-006: Session Durability — Redis-Backed Session Store

## Status

- status: `delivered`
- owner: workspace maintainers
- created: 2026-07-28
- delivered: 2026-07-28
- release slice: `Release 1` (stateful foundation)
- related risks: C1 (sessions are ephemeral — lost on restart, not shared across replicas)

## Summary

Replace the in-memory session store with a Redis-backed implementation so sessions survive pod restarts and can be shared across multiple agent-platform replicas. The store exposes a strategy-pattern interface: an `InMemorySessionStore` for development and CI, and a `RedisSessionStore` for deployed environments. Backend selection is driven by the `SESSION_STORE_BACKEND` environment variable, with graceful fallback to in-memory if Redis is unreachable at startup.

## Motivation

- the current `SessionStore` in `session_store.py` is a single-process in-memory dictionary: all sessions are lost when the agent-platform pod restarts
- multi-replica deployments are impossible because each replica has an independent session state — a user routed to a different replica sees "session not found"
- Redis 7.2-alpine is already deployed in the dev cluster (`dev-k8s-transitional`) for AgentScope's storage and message bus; reusing it for sessions avoids new infrastructure
- SPEC-005 called out "C1 session durability" as the next stateful milestone once observability was in place; the metrics and tracing infrastructure is now available to monitor session store health
- the `redis>=6.2,<7.0` Python client is already a declared dependency

## Requirements

### R-1: Redis-backed session persistence

Sessions are stored in Redis so they survive pod restarts and are accessible to all replicas.

Acceptance criteria:

- a `RedisSessionStore` implementation stores sessions as JSON-serialized blobs keyed by `session:{session_id}`
- Redis native `EXPIRE` is used for TTL management (replaces the in-memory `_purge_expired` sweep)
- sessions are stored in a separate Redis DB (`SESSION_REDIS_DB`, default `1`) to avoid key collisions with AgentScope's DB (`0`)
- the `create_session`, `get_session`, and `delete_session` operations work against Redis with the same semantics as the current in-memory store
- `list_sessions_by_user(user_id)` returns all non-expired sessions for a given user via a `user_sessions:{user_id}` sorted set

### R-2: Strategy pattern with environment-driven selection

The session store backend is selectable without code changes.

Acceptance criteria:

- `SessionStore` is a Protocol (or abstract base) defining the public interface: `create_session`, `get_session`, `list_sessions_by_user`, `delete_session`, `__len__`
- `InMemorySessionStore` preserves the existing behaviour (TTL sweep, max-entry eviction)
- `RedisSessionStore` implements the same interface against Redis
- a factory function `build_session_store()` reads `SESSION_STORE_BACKEND` (`memory` | `redis`, default `redis`) and returns the appropriate implementation
- the module-level `SESSION_STORE` singleton uses the factory
- the existing `session_service.py` API is unchanged — callers import `SESSION_STORE` and call methods as before

### R-3: Graceful fallback when Redis is unreachable

The service starts even if Redis is unavailable.

Acceptance criteria:

- if `SESSION_STORE_BACKEND=redis` but Redis is unreachable at startup (ping fails within a 3-second timeout), a warning is logged and the store falls back to `InMemorySessionStore`
- a `session_store_fallbacks_total` Prometheus counter is incremented on every fallback event
- the active backend is reported in the `/health` readiness response (a `session_store` field: `redis` or `memory`)
- the fallback is logged at WARNING level with the Redis connection error details

### R-4: Observability integration

Session store operations are observable via the SPEC-005 metrics surface.

Acceptance criteria:

- `session_store_backend` info gauge reports the active backend (label: `backend`)
- `session_store_errors_total` counter tracks Redis connection and operation failures (label: `operation`)
- the `/health` readiness endpoint reports `session_store: redis|memory` and `session_store_ready: true|false`
- counters follow the naming conventions in `shared/shared-contracts/observability-conventions.md`

### R-5: Tests and CI enforcement

Acceptance criteria:

- existing `test_session_service.py` tests pass with the in-memory backend (no regression)
- new `test_redis_session_store.py` tests cover Redis store CRUD, user-scoped listing, TTL expiry, and fallback behaviour using `fakeredis`
- backend selection test: `SESSION_STORE_BACKEND=memory` uses in-memory; `SESSION_STORE_BACKEND=redis` uses Redis; unreachable Redis falls back to in-memory
- both Kustomize overlay bases render cleanly with the new env vars
- SPEC-001..005 regression suites pass for all three products

## Non-Goals

- session conversation history or message persistence — sessions carry identity and lifecycle only; chat history is a separate spec
- Redis Cluster, Sentinel, or HA configuration — dev single-replica is sufficient; production HA is future platform-ops work
- Redis AOF/RDB persistence tuning — the current emptyDir volume means sessions are durable across pod restarts but not node failures; this is acceptable for dev
- session migration from in-memory to Redis — clean cutover; existing in-memory sessions are ephemeral by definition
- cross-service session sharing — only agent-platform reads/writes sessions; the gateway proxies session API calls to agent-platform

## Impact

- products touched: `products/agent-platform` (session store, metrics, health, tests)
- contracts touched: none (internal implementation detail)
- identity / policy / audit / execution safety impact: none — session ownership checks (SPEC-001) are preserved in the service layer
- deployment impact: `dev-k8s-native` overlay gains Redis deployment + service; `runtime-config.env` gains `SESSION_STORE_BACKEND` and `SESSION_REDIS_*` vars
- living state docs to update on delivery: agent-platform `README.md`, `CHANGELOG.md`, `docs/specs/README.md` spec index

## Open Questions

None — all resolved.

## Changelog

- 2026-07-28: created as `draft` addressing risk C1
- 2026-07-28: approved — strategy pattern with Redis backend, graceful fallback, observability integration
- 2026-07-28: status → `delivered`
