# SPEC-016 Plan: Session Store Separation — Postgres Backend

## Approach

The session store already sits behind a platform-owned `SessionStore`
protocol (memory and Redis backends); this spec adds a third backend —
`PostgresSessionStore` — and flips dev-k8s to it. Because the protocol is
synchronous and the records are small relational rows, the implementation
mirrors the audit-service / incident-service Postgres pattern: synchronous
`psycopg[binary]`, parameterized SQL, fixed identifier constants, and a fake
driver double for tests. No session semantics change; ownership enforcement
stays in `session_service`, TTL stays idle-based, and the Redis backend
remains byte-compatible. The kernel's Redis (`RedisStorage` /
`RedisMessageBus`) is untouched per ADR-0002.

Implementation stages: (1) Postgres backend + startup DDL, (2) settings and
factory extension with fail-open parity, (3) observability invariants,
(4) dependency and lock, (5) dev-k8s switchover, (6) tests and docs.

## Design Per Requirement

### R-1: Postgres session store backend

- affected files:
  `products/agent-platform/src/agent_service/services/session_store.py`
  (new `PostgresSessionStore` next to the existing memory/Redis classes),
  startup schema application in the store module
- `sessions` table: `session_id` (PK), `user_id` (nullable, indexed),
  `created_at`, `last_accessed_at`; the row payload maps field-for-field to
  `SessionRecord`
- idle TTL equivalence with Redis `EXPIRE`: every read checks
  `last_accessed_at + SESSION_TTL_SECONDS` (expired rows never returned) and
  refreshes `last_accessed_at`; an opportunistic bounded `DELETE` sweep runs
  inside operations to reclaim storage — no sweeper thread
- single-owner semantics unchanged: the store serves any caller; ownership
  enforcement remains in `session_service`
- DDL applied by agent-platform on startup when the postgres backend is
  active: idempotent `CREATE TABLE IF NOT EXISTS`
- driver: synchronous `psycopg[binary]`, same pinned range as audit-service
  / incident-service

### R-2: Configuration and factory extension

- affected files:
  `products/agent-platform/src/agent_service/runtime_settings.py`
  (`session_store_backend` three-valued, `session_db_url`),
  `services/session_store.py` factory
- `SESSION_STORE_BACKEND` accepts `memory` | `redis` | `postgres`; unknown
  values raise at startup in the existing settings-validation style
- `SESSION_DB_URL` required when backend is `postgres`, ignored otherwise;
  vocabulary matches incident-service's `INCIDENT_DB_URL`
- fail-open parity with the Redis backend: initial connection failure falls
  back to `InMemorySessionStore` with a WARNING log and increments
  `session_store_fallbacks_total`
- the `redis` path is not touched — existing deployments that keep it see no
  behavioral change

### R-3: dev-k8s deployment switchover

- affected files:
  `shared/platform-ops/gitops/dev-k8s/base/infra/create-sessions-db.sql`
  (new initdb script, same pattern as `create-incidents-db.sql` /
  `create-skills-db.sql`), `base/infra/postgres-statefulset.yaml` (initdb
  ConfigMap mount), `base/agent-platform/runtime-config.env`,
  `shared/platform-ops/gitops/sync-sessions-db.sh` (new, idempotent
  `CREATE DATABASE sessions` for running clusters)
- `runtime-config.env` switches to `SESSION_STORE_BACKEND=postgres` with
  `SESSION_DB_URL` pointing at the shared Postgres; `SESSION_REDIS_*`
  removed from deployed configs
- the redis deployment keeps running for the kernel (`AGENTSCOPE_REDIS_*`,
  DB 0) with no configuration change
- no data migration: sessions are ephemeral working state; the switchover
  starts from an empty store (noted in the release-facing docs)

### R-4: Observability and health invariants

- affected files:
  `products/agent-platform/src/agent_service/core/metrics.py`,
  `api/v2/routes.py` (health), `services/session_store.py`
- `session_store_backend` gauge reports `postgres` when active;
  `session_store_errors_total` increments on failed operations
- `/health` `session_store` / `session_store_ready` fields keep their
  existing contract — `agent-health.schema.json` unchanged
- one structured log line at startup names the selected backend

### R-5: Tests and documentation

- see Test Strategy below; docs cover configuration-reference, product
  README, CHANGELOG, spec index

## Sequencing And Dependencies

1. `PostgresSessionStore` + startup DDL — depends on nothing
2. Settings fields + factory extension + fail-open fallback — depends on (1)
3. Metrics / health / startup log invariants — depends on (2)
4. `psycopg[binary]` dependency + `uv.lock` refresh — parallel with (1)
5. dev-k8s initdb, sync script, runtime-config switchover — depends on (2)
   env contract
6. Tests (fake-psycopg backend + factory) and living docs — depends on all

## Test Strategy

- unit tests: `tests/test_postgres_session_store.py` mirrors
  `test_redis_session_store.py` coverage — CRUD, user listing, idle-TTL
  expiry and read-refresh, expired-row exclusion, bounded sweep, fallback,
  backend selection — against the fake psycopg driver pattern used by
  audit-service; factory tests cover the three-valued switch, unknown-value
  startup failure, missing-DSN failure, and fail-open fallback
- contract tests: health contract unchanged (`agent-health.schema.json`)
- integration / overlay validation: `kustomize build` renders dev-k8s with
  the new initdb script and env switchover via `make verify`; live-cluster
  verification is delivery-time `make deploy` + chat/session smoke, not part
  of the gate

## Rollout And Migration

- deployment: dev-k8s switches via committed `runtime-config.env`; fresh
  clusters get the `sessions` database from initdb, running clusters via
  `sync-sessions-db.sh`; table DDL applies idempotently at startup
- backward compatibility: `SESSION_STORE_BACKEND` defaults keep memory as
  the code default; the redis backend remains fully supported; no schema
  changes to any existing database
- rollback: flip `SESSION_STORE_BACKEND` back to `redis` (or `memory`) and
  restore the previous `SESSION_REDIS_*` values — sessions are ephemeral, so
  no data reconciliation is needed
