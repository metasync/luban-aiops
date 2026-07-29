# SPEC-006 Tasks: Session Durability

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Redis-backed session persistence

- [x] add `RedisSessionStore` class with JSON serialization, `EXPIRE`, and user sorted set (`products/agent-platform/src/agent_service/services/session_store.py`)
- [x] implement `list_sessions_by_user` and `delete_session` (`products/agent-platform/src/agent_service/services/session_store.py`)

## R-2: Strategy pattern with environment-driven selection

- [x] extract `SessionStore` Protocol and rename existing class to `InMemorySessionStore` (`products/agent-platform/src/agent_service/services/session_store.py`)
- [x] add `build_session_store()` factory reading `SESSION_STORE_BACKEND` (`products/agent-platform/src/agent_service/services/session_store.py`)
- [x] verify `session_service.py` works unchanged with the new interface (`products/agent-platform/src/agent_service/services/session_service.py`)

## R-3: Graceful fallback when Redis is unreachable

- [x] add ping-with-timeout check in factory; log WARNING and return `InMemorySessionStore` on failure (`products/agent-platform/src/agent_service/services/session_store.py`)
- [x] add `session_store_fallbacks_total` counter (`products/agent-platform/src/agent_service/core/metrics.py`)

## R-4: Observability integration

- [x] add `session_store_backend` gauge and `session_store_errors_total` counter (`products/agent-platform/src/agent_service/core/metrics.py`)
- [x] extend `/health` response with `session_store` and `session_store_ready` fields (`products/agent-platform/src/agent_service/api/v2/routes.py`)

## R-5: Tests and CI enforcement

- [x] add `fakeredis` dev dependency (`products/agent-platform/pyproject.toml`)
- [x] add `test_redis_session_store.py` covering CRUD, user listing, TTL, fallback (`products/agent-platform/tests/test_redis_session_store.py`)
- [x] verify existing `test_session_service.py` passes with `SESSION_STORE_BACKEND=memory` (`products/agent-platform/tests/test_session_service.py`)
- [x] add backend selection and fallback tests (`products/agent-platform/tests/test_redis_session_store.py`)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] add Redis deployment + service to `dev-k8s-native` overlay (inherited from transitional base)
- [x] add `SESSION_STORE_BACKEND` and `SESSION_REDIS_*` to `runtime-config.env` (`shared/platform-ops/gitops/dev-k8s-transitional/base/agent-platform/runtime-config.env`)
- [x] living state docs updated: agent-platform `README.md`, `CHANGELOG.md`, `docs/specs/README.md`
- [x] `CHANGELOG.md` entry added referencing SPEC-006
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
- [x] both Kustomize overlay bases render cleanly
- [x] full test suite green for all three products (151 total: 57 + 21 + 73)
