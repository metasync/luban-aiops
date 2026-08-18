# SPEC-016 Tasks: Session Store Separation — Postgres Backend

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Postgres session store backend

- [x] implement `PostgresSessionStore` (CRUD, user listing, idle-TTL expiry + read-refresh, bounded opportunistic sweep) (`products/agent-platform/src/agent_service/services/session_store.py`)
- [x] idempotent `sessions` table DDL applied at startup when the postgres backend is active (`services/session_store.py`)
- [x] parameterized SQL with fixed identifier constants throughout

## R-2: Configuration and factory extension

- [x] settings: `SESSION_STORE_BACKEND` (`memory` | `redis` | `postgres`, unknown fails startup) + `SESSION_DB_URL` (`products/agent-platform/src/agent_service/runtime_settings.py` + `tests/test_runtime_settings.py`)
- [x] factory: postgres backend selection with fail-open fallback to `InMemorySessionStore` (WARNING log + `session_store_fallbacks_total`)
- [x] verify redis backend byte-compatibility (no change to existing path)

## R-3: dev-k8s deployment switchover

- [x] `create-sessions-db.sql` initdb script + ConfigMap mount (`shared/platform-ops/gitops/dev-k8s/base/infra/`)
- [x] `sync-sessions-db.sh`: idempotent `CREATE DATABASE sessions` for running clusters (`shared/platform-ops/gitops/`)
- [x] `runtime-config.env`: `SESSION_STORE_BACKEND=postgres` + `SESSION_DB_URL`, `SESSION_REDIS_*` removed (`dev-k8s/base/agent-platform/`)
- [x] wire deploy scripts to the sessions-db sync step
- [x] confirm redis deployment unchanged (`AGENTSCOPE_REDIS_*`, DB 0)

## R-4: Observability and health invariants

- [x] `session_store_backend` gauge reports `postgres`; `session_store_errors_total` on failed operations (`core/metrics.py`)
- [x] `/health` `session_store` fields keep contract (`agent-health.schema.json` unchanged)
- [x] structured startup log line naming the selected backend

## R-5: Tests and documentation

- [x] `tests/test_postgres_session_store.py` (19 tests) mirroring redis coverage against the fake psycopg driver double
- [x] factory/backend-selection tests
- [x] `psycopg[binary]` dependency + `uv.lock` refresh (`products/agent-platform/pyproject.toml`)
- [x] `docs/guides/configuration-reference.md`: `SESSION_DB_URL` + three-valued backend switch
- [x] agent-platform README session-store section (Postgres deployed, Redis kernel-only)
- [x] dev-k8s README sessions-DB section

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
