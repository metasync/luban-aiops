# SPEC-016: Session Store Separation — Postgres Backend

## Status

- status: `delivered`
- owner: workspace maintainers
- created: 2026-08-18
- approved: 2026-08-18
- delivered: 2026-08-18
- release slice: post-R3 infrastructure hygiene (candidate R4 prerequisite or standalone)
- related ADRs: ADR-0002 (AgentScope runtime kernel — kernel Redis stays)

## Summary

Move the agent-platform session store off the AgentScope kernel's Redis
instance and onto Postgres, as a third pluggable backend behind the existing
`SessionStore` protocol. Sessions are small relational records already served
by an in-cluster Postgres (audit, incidents, skills); placing them there
detaches platform session state from the agent framework's infrastructure, so
a future agent-framework swap leaves session storage untouched. The kernel's
Redis usage (`RedisStorage` / `RedisMessageBus`) is explicitly out of scope —
AgentScope ships no Postgres alternative.

## Motivation

- The session store is a **platform concern** (SPEC-001 session contract,
  SPEC-006 durability), consumed by the operator portal's chat and by
  incident triage sessions. Today it is framework-independent in code but
  shares the kernel's Redis instance (DB 1 vs DB 0) — the only remaining
  coupling between platform session state and the agent framework's
  infrastructure.
- Separation of concerns: if the platform ever swaps the agent kernel
  (ADR-0002 permits evolution), session storage must survive unchanged.
  Hosting sessions on framework-agnostic infrastructure (Postgres) makes
  that guarantee structural rather than accidental.
- Infrastructure consolidation: Postgres already runs in dev-k8s for audit,
  incidents, and skills databases. Sessions fit the same record-store
  pattern; kernel Redis then becomes the single Redis consumer, which also
  sharpens the later durability question (its `emptyDir` volume).
- Verified constraint: the kernel message bus ships only `RedisMessageBus`
  + `InMemoryMessageBus` in every agentscope release up to the installed
  2.0.6, and the deployed runtime path depends on it — kernel Redis
  therefore stays. (Since 2.0.5 the kernel *storage* layer additionally
  offers `AsyncSQLAlchemyStorage`, a future kernel-side option noted in
  SPEC-017; that does not change this spec's scope.)

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Postgres session store backend

A new `PostgresSessionStore` implements the existing `SessionStore` protocol
(`backend_name`, `create_session`, `get_session`, `list_sessions_by_user`,
`delete_session`, `is_ready`, `__len__`) with identical semantics to the
Redis backend.

Acceptance criteria:

- sessions persist in a `sessions` table: `session_id` (PK), `user_id`
  (nullable, indexed), `created_at`, `last_accessed_at`; the record payload
  matches `SessionRecord` field-for-field.
- TTL is idle-based and equivalent to the Redis backend's `EXPIRE`
  (`SESSION_TTL_SECONDS`, default 3600): reads refresh `last_accessed_at`;
  expired rows are excluded from every query and swept opportunistically
  (bounded delete per operation; no long-running sweeper thread required).
- single-owner semantics are preserved: `get_session` returns the record for
  any caller; ownership enforcement stays in `session_service` (unchanged).
- SQL is parameterized everywhere; identifiers are fixed constants.
- the driver is synchronous `psycopg[binary]` (mirrors the audit-service /
  incident-service choice and the synchronous `SessionStore` protocol).

### R-2: Configuration and factory extension

The backend stays environment-selected with memory as the code default.

Acceptance criteria:

- `SESSION_STORE_BACKEND` accepts `memory` | `redis` | `postgres`;
  unknown values fail startup with a clear error.
- `SESSION_DB_URL` supplies the Postgres DSN (vocabulary matches
  incident-service's `INCIDENT_DB_URL`); required when backend is
  `postgres`, ignored otherwise.
- fail-open parity with the Redis backend: if the initial Postgres
  connection fails, the factory falls back to `InMemorySessionStore` with a
  WARNING log and increments `session_store_fallbacks_total`.
- the `redis` backend remains available and byte-compatible — no behavioral
  change for existing deployments that keep it.

### R-3: dev-k8s deployment switchover

The dev-k8s overlay moves session storage to Postgres; kernel Redis is
untouched.

Acceptance criteria:

- new `create-sessions-db.sql` bootstrap (same initdb ConfigMap pattern as
  `create-incidents-db.sql` / `create-skills-db.sql`) creates the `sessions`
  database; the table DDL is applied by agent-platform on startup
  (idempotent `CREATE TABLE IF NOT EXISTS`).
- `dev-k8s/base/agent-platform/runtime-config.env` switches to
  `SESSION_STORE_BACKEND=postgres` with `SESSION_DB_URL` pointing at the
  shared Postgres; `SESSION_REDIS_*` settings are removed from deployed
  configs.
- the `redis` deployment keeps running for the kernel
  (`AGENTSCOPE_REDIS_*`, DB 0) with no configuration change.
- no data migration: sessions are ephemeral working state; the switchover
  starts from an empty store (documented in the release note).

### R-4: Observability and health invariants

Acceptance criteria:

- `session_store_backend` gauge reports `postgres` when active;
  `session_store_errors_total` increments on failed operations.
- `/health` `session_store` / `session_store_ready` fields keep their
  contract (`agent-health.schema.json` unchanged).
- one structured log line at startup names the selected backend.

### R-5: Tests and documentation

Acceptance criteria:

- Postgres backend tests mirror `test_redis_session_store.py` coverage
  (CRUD, user listing, idle-TTL expiry and refresh, fallback, backend
  selection) against the fake psycopg driver pattern already used by
  audit-service.
- `docs/guides/configuration-reference.md` documents `SESSION_DB_URL` and
  the three-valued backend switch; agent-platform README and CHANGELOG
  updated; the session-store section names Postgres as the deployed
  backend and Redis as kernel-only.

## Out of Scope

- replacing the AgentScope kernel's Redis (`RedisStorage` /
  `RedisMessageBus`) — no Postgres backend exists upstream; custom kernel
  adapters are a fork-level burden.
- deleting the Redis session backend — it stays as a supported option;
  removal can be revisited one release after the switchover proves out.
- migrating existing session data (ephemeral by design).
- a gateway-served `/api/v1/version` endpoint (tracked separately with the
  versioning discipline).

## Risks

- **R1: TTL semantics drift.** Redis `EXPIRE` is exact and per-key; sweep
  expiry is eventually consistent. Mitigation: expiry checked on every read
  (exact from the caller's perspective); sweep only reclaims storage.
- **R2: Postgres becomes a hard dependency of chat.** Postgres outage now
  affects sessions as well as audit/incidents/skills. Mitigation: fail-open
  fallback to memory at startup (R-2), matching today's Redis behavior;
  Postgres is already the cluster's most load-bearing stateful dependency.
- **R3: driver weight.** `psycopg[binary]` adds a dependency to
  agent-platform. Mitigation: same pinned range as audit-service /
  incident-service; no new operational surface (same server, same
  credentials pattern).
