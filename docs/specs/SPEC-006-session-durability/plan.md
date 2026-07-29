# SPEC-006 Plan: Session Durability

## Approach

Refactor the session store behind a Protocol interface, add a Redis-backed implementation, and wire backend selection via environment variables. The strategy pattern isolates the storage backend from the service layer, so `session_service.py` and all callers remain unchanged. Redis reuses the existing in-cluster deployment; a separate DB (`1`) avoids key collisions with AgentScope's DB (`0`).

## Design Per Requirement

### R-1: Redis-backed session persistence

- affected files: `services/session_store.py`
- chosen approach: `RedisSessionStore` class using `redis.Redis` synchronous client; sessions serialized as JSON under key `session:{session_id}` with Redis `EXPIRE` for TTL; user-scoped listing via sorted set `user_sessions:{user_id}` scored by `created_at` epoch
- alternatives considered:
  - async Redis (`aioredis`/`redis.asyncio`) — rejected: the current `SessionStore` interface is synchronous and all callers use it synchronously; switching to async would cascade changes through `session_service.py` and every route handler
  - PostgreSQL / SQLite — rejected: adds a new infrastructure dependency when Redis is already deployed and sufficient for session-scale data

### R-2: Strategy pattern with environment-driven selection

- affected files: `services/session_store.py`
- chosen approach: `SessionStore` as a `typing.Protocol` defining the public interface; `InMemorySessionStore` (renamed from current `SessionStore`) and `RedisSessionStore` both satisfy it; factory function `build_session_store()` reads `SESSION_STORE_BACKEND`
- alternatives considered:
  - ABC with concrete methods — rejected: Protocol is more Pythonic for structural subtyping and avoids inheritance coupling

### R-3: Graceful fallback when Redis is unreachable

- affected files: `services/session_store.py`
- chosen approach: factory attempts `redis.ping()` with a 3-second timeout; on `ConnectionError`/`TimeoutError`, logs WARNING and returns `InMemorySessionStore` with a `fallback=True` flag; Prometheus counter `session_store_fallbacks_total` incremented

### R-4: Observability integration

- affected files: `core/metrics.py`, `api/v2/routes.py` (health endpoint)
- chosen approach: `Gauge` for active backend, `Counter` for errors; health endpoint includes `session_store` and `session_store_ready` fields in the response

### R-5: Tests and CI enforcement

- affected files: `tests/test_session_service.py`, `tests/test_redis_session_store.py` (new)
- chosen approach: `fakeredis` as dev dependency for Redis store tests; existing tests pass unchanged with `SESSION_STORE_BACKEND=memory`

## Sequencing And Dependencies

1. Spec documents — depends on nothing
2. Session store refactor (R-1, R-2, R-3) — depends on spec approval
3. Metrics and health integration (R-4) — depends on store refactor
4. Tests (R-5) — depends on store + metrics
5. Deployment overlays and docs — depends on tests passing

## Test Strategy

- unit tests: `test_redis_session_store.py` covers CRUD, user listing, TTL, fallback using `fakeredis`
- regression: `test_session_service.py` runs with `SESSION_STORE_BACKEND=memory` to verify the in-memory path is unchanged
- integration: backend selection test verifies factory behaviour with both backends and fallback
- overlay validation: `kustomize build` for both dev overlay bases

## Rollout And Migration

- deployment: add `SESSION_STORE_BACKEND=redis` and `SESSION_REDIS_*` vars to `runtime-config.env`; add Redis deployment to `dev-k8s-native` overlay
- backward compatibility: `SESSION_STORE_BACKEND=memory` preserves existing behaviour; default changes to `redis` in deployed overlays
- rollback: set `SESSION_STORE_BACKEND=memory` to revert to in-memory without redeploying
