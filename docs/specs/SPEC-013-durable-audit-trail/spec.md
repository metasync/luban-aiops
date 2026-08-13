# SPEC-013: Durable Audit Trail — Audit Event Contract, Store, and Query API

## Status

- status: `delivered`
- owner: workspace maintainers
- created: 2026-08-11
- release slice: `R1` residual close (bridge before `R2`)
- related ADRs: ADR-0004 (broker-mediated token delegation), ADR-0005 (platform gateway extraction)

## Summary

Replace the ephemeral pod-log audit trail with a durable, queryable, permission-scoped audit service: a shared audit-event contract, an `audit-service` that ingests and retains audit events from all platform services, a policy-gated query API, and a read-only audit view in the operator portal.

## Motivation

Release 1 delivered audit *emission* but not audit *durability*:

1. **Audit trail is ephemeral and unqueryable**: every audited event (`tool_invoked`, policy decisions, token exchanges, session lifecycle) is a structured JSON log line in pod logs. Pod restarts, log rotation, and redeployments destroy the record; there is no way to answer "what tools did user X invoke last week" or "who triggered this chat" across services. Both R1 release notes (`2026-08-10`, `2026-08-11`) name this as the primary known limitation and point at SPEC-013 as the resolution.
2. **The `auditor` role has nothing to read**: the authorization matrix (`docs/agentic-aiops-platform/authorization-matrix.md`) defines an `auditor` role whose primary use is "view audit trails" and "inspect approvals and execution attribution". Today that role can only `kubectl logs` — not a platform capability.
3. **Cross-user troubleshooting is impossible**: the portal audit card (SPEC-011) renders streamed evidence for the caller's own turn only. An operator cannot investigate what happened in another user's session.
4. **R4 prerequisite**: the roadmap's approval-gated actions release requires "verify the full audit chain is present" as a completion signal. That chain needs a durable home before execution events arrive on top of it.

Evidence: R1 hardening release notes Known Limitations; R1 close release notes Known Limitations; authorization matrix auditor role definition.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Audit event contract

A canonical audit-event schema in `shared/shared-contracts` that all emitting services and the audit service bind to, mirroring the contract-test pattern used for existing schemas.

Acceptance criteria:

- New `shared/shared-contracts/schemas/audit-event.schema.json` defines the event envelope: `event_id`, `occurred_at`, `event_type`, `service`, `request_id`, `subject`, `username`, `actor` (delegation `act` claim, optional), `roles`, `session_id` (optional), `outcome` (`allow` | `deny` | `success` | `error`), and a typed `details` object
- Covered event types at minimum: `tool_invoked` (including policy-denied invocations), `policy_decision`, `token_exchange` (granted and rejected), `session_created`, `chat_started`, `chat_completed`
- Contract tests bind emitting-service and audit-service Pydantic models to the schema (same pattern as `tool-invocation.schema.json` bindings)
- `http_request` middleware events are explicitly excluded from the audit contract (they are observability data, high-volume, and remain in logs/metrics)

### R-2: Audit service with durable store

A new `products/audit-service` (FastAPI, following the frozen-dataclass settings and structured-logging conventions of the existing services) that stores audit events in a durable backend selected by a strategy-pattern interface, per the SPEC-006 precedent.

Acceptance criteria:

- `AuditStore` protocol with at least two implementations: an in-memory store for tests/dev and a PostgreSQL-backed store for deployed environments; backend selected via `AUDIT_STORE_BACKEND` env (`memory` | `postgres`, default `memory`)
- PostgreSQL-backed store survives pod restarts (WAL-durable, PVC-backed in the dev-k8s overlay); graceful degradation when the database is unreachable is defined (ingest fails open to local log only, never blocks emitters — see R-3)
- Store backend and readiness are reported in `/health`; always-on `/metrics` surface following `observability-conventions.md` (ingest total, query total, store size, store errors)
- Product structure follows the existing per-product layout (Makefile, Dockerfile on `base-uv`, uv lockfile, `make verify` coverage)

### R-3: Authenticated non-blocking ingestion

Emitting services (tool-gateway, platform-gateway, identity-broker) forward audit events to the audit service over HTTP; ingestion is authenticated with the existing service-identity mechanisms and must never block or fail the originating request.

Acceptance criteria:

- `POST /api/v1/audit/events` on the audit service accepts single events or small batches conforming to the R-1 schema; malformed events are rejected with 400 and a counter, not silently dropped
- Emitter authentication uses the SPEC-008/009 service-identity mechanisms (registered service client credential or projected workload token); unauthenticated ingest returns 401
- Emission is fire-and-forget with a bounded timeout on the emitter side: audit-service unreachability degrades to structured-log-only auditing plus an emitter-side metric/counter, and the user-facing request still succeeds
- Every event currently emitted via `log_event` for `tool_invoked`, policy decisions, token exchange, and session/chat lifecycle is also forwarded to the audit service when `*_AUDIT_SERVICE_URL` is configured; unset URL preserves today's behavior exactly (log-only)
- Structured pod-log emission is retained alongside the audit service (logs stay the first-line diagnostic surface)

### R-4: Permission-scoped query API

A query API on the audit service, exposed to the portal through the platform-gateway, gated by a new `audit:read` policy action.

Acceptance criteria:

- `GET /api/v1/audit/events` supports filters: `username`, `session_id`, `request_id`, `event_type`, `service`, time range (`since`/`until`), and cursor pagination with newest-first default ordering
- A new `audit:read` action is added to the canonical policy bundle (and synced copies); granted to `auditor` and `platform-admin` only, deny-by-default for all other roles — matching the authorization matrix's auditor definition
- platform-gateway proxies the query route under `/api/v1/audit/*` with its standard portal-token verification and policy enforcement; deny returns the structured 403
- Query results carry the exact stored event envelope (no field loss between ingest and query); results of redacted tool invocations stay redacted (audit-service stores what emitters send, post-redaction)

### R-5: Operator portal audit view

A read-only audit view in the operator portal so auditors and platform admins can browse the durable trail without cluster access.

Acceptance criteria:

- New portal panel or view listing audit events with the R-4 filters (at minimum: username, event type, time range) and pagination; follows the existing dark-theme CSS variable conventions
- View is only reachable for identities whose roles hold `audit:read`; unauthorized identities see no audit navigation entry (and the API denies them regardless)
- Each event row expands to the full event envelope including delegation chain (`actor`), request/session IDs, and outcome
- The per-turn portal audit card from SPEC-011 remains unchanged

### R-6: Retention and bounded growth

The audit store is bounded by a configurable retention policy so unbounded growth cannot exhaust the backend.

Acceptance criteria:

- `AUDIT_RETENTION_DAYS` (default 30) evicts events older than the window; eviction runs on a bounded periodic schedule, oldest-first
- A hard `AUDIT_MAX_EVENTS` cap (default configurable) protects the store even within the retention window; eviction is counted in a metric (Postgres implementation may use table partitioning or batched deletes)
- Retention window and approximate store size are visible in `/health` or `/metrics`
- Eviction never blocks ingest

## Non-Goals

- Tamper-proof or cryptographically signed audit records (append-only WORM storage, hash chains) — belongs to the `R4` approval-gated actions release when execution events raise the integrity stakes
- Redis or other NoSQL backends for the audit store — sessions (SPEC-006) remain cache-shaped Redis data, but audit events are append-only, multi-dimensionally queried, and loss-intolerant, which is relational-shaped; the dev-k8s Redis is also non-persistent (`appendonly no`, `emptyDir`), so it cannot host an audit trail without rework
- Log-collection pipelines (Fluentd/Vector/OTel logs exporter into an external SIEM) — the audit service owns its own ingest; external export is a future spec
- Agent-platform as a direct emitter — tool invocations are audited at the tool-gateway choke point and chat/session events at platform-gateway; agent-platform adds no new audit event types in this spec
- Backfilling or parsing historical pod logs into the audit store
- Archival to object storage or long-term compliance retention beyond the bounded R-6 window

## Impact

- products touched:
  - `products/audit-service` (new product: store, ingest, query API, health/metrics)
  - `products/tool-gateway` (forward `tool_invoked` and denied-invocation events)
  - `products/platform-gateway` (forward policy/session/chat events; proxy `/api/v1/audit/*`; enforce `audit:read`)
  - `products/identity-broker` (forward token exchange granted/rejected events)
  - `products/operator-portal` (R-5 audit view)
  - `shared/platform-ops/gitops/dev-k8s` (audit-service deployment/service/config, PostgreSQL StatefulSet + PVC + credentials secret, emitter `*_AUDIT_SERVICE_URL` and `*_AUDIT_DB_*` env, policy ConfigMap update)
- contracts touched: `shared/shared-contracts/schemas/audit-event.schema.json` (new), `shared/shared-contracts/policies/policy-default.yaml` (`audit:read` action)
- identity / policy / audit / execution safety impact: introduces a new policy action and a new service-to-service caller identity; the audit view exposes cross-user activity and is therefore restricted to `auditor`/`platform-admin` by deny-by-default policy
- living state docs to update on delivery: root `README.md`, `CHANGELOG.md`, product READMEs, dev-k8s overlay README, `docs/guides/configuration-reference.md`, `docs/guides/architecture-overview.md`, `docs/guides/tool-configuration.md` (audit-service activation checklist), spec index

## Open Questions

- **Q-1** *(resolved 2026-08-11)*: Store backend for deployed environments — **PostgreSQL**, not Redis. Rationale: audit events are append-only, retention-windowed, and queried across multiple dimensions (user, session, request, event type, time range) — a relational workload where SQL indexes and `DELETE`-based retention are native, while Redis would require hand-rolled secondary index sets and manual eviction. Durability settles it: the dev-k8s Redis runs `--appendonly no` on an `emptyDir` (zero persistence), acceptable for loss-tolerant sessions but disqualifying for an audit trail, while Postgres is WAL-durable by default. Postgres also supports the roadmap's later audit reporting (R5) and integrity measures (R4). Cost accepted: one new StatefulSet + PVC + secret in the overlay. A Redis audit backend is deliberately not delivered; the `AuditStore` interface keeps future backends open.
- **Q-2** *(resolved 2026-08-11)*: The portal audit view (R-5) ships in this spec. Rationale: the `auditor` role has no platform value without a surface to read from, and the view is small and read-only, so splitting it would defer the role's entire value proposition for little scope savings.
- **Q-3** *(resolved 2026-08-11)*: Ingest authentication reuses the broker-mediated service-identity mechanisms (SPEC-008 service-client registry / SPEC-009 projected workload tokens), with `audit-service` registered as a new audience/client. Rationale: consistency with the existing trust model avoids a second, divergent credential scheme; the workload-token upgrade path applies to audit emitters for free.
- **Q-4** *(resolved 2026-08-11)*: Default retention window is 30 days (`AUDIT_RETENTION_DAYS`), env-overridable, to be revisited during production hardening when organizational retention standards apply.

## Changelog

- 2026-08-11: created as `draft`
- 2026-08-11: Q-1 resolved — PostgreSQL selected as the deployed audit store backend; R-2, Non-Goals, and Impact updated accordingly (Redis audit backend deferred)
- 2026-08-11: Q-2/Q-3/Q-4 resolved (portal view in scope; broker-mediated service identity for ingest; 30-day default retention); all open questions closed and spec flipped to `approved`
- 2026-08-12: `plan.md` written — includes one refinement of Q-3: ingest auth reuses the SPEC-008/009 credential *vocabulary* (static client registry + projected workload tokens) verified locally by audit-service, since the broker exchange flow is user-subject-bound and cannot mint pure service tokens
- 2026-08-12: implementation delivered — all R-1 through R-6 acceptance criteria met; `make verify` green (agent-platform 122, audit-service 67, identity-broker 57, platform-gateway 92, tool-gateway 117; all overlays render; policy bundle validated); status flipped to `delivered`
- 2026-08-12: dev-k8s live test caught a PostgreSQL adaptation bug — `PostgresAuditStore.add` passed `details` as a raw dict, which psycopg cannot adapt for the `JSONB` column (every ingest failed 500); fixed by wrapping in `psycopg.types.json.Jsonb`, regression test added (audit-service tests 67 → 68); end-to-end smoke on the local cluster confirmed a `token_exchange` deny event persisting to the trail and answering via the authenticated query API
