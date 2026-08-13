# SPEC-013 Plan: Durable Audit Trail

## Approach

Deliver the durable audit trail in five stacked stages, each leaving `make verify` green:

1. **Contract first** (R-1 + policy action): the audit-event schema and the `audit:read` policy rule land in `shared/shared-contracts` before any service code, following the contracts-first discipline used by SPEC-007/008.
2. **The audit service** (R-2, R-6, R-3 ingest endpoint): a new `products/audit-service` with the `AuditStore` strategy interface, in-memory and PostgreSQL backends, authenticated ingest, retention eviction, health, and metrics.
3. **Emitters** (R-3): fire-and-forget audit forwarding in tool-gateway, platform-gateway, and identity-broker, feature-gated by a per-service audit URL env var.
4. **Portal path** (R-4): platform-gateway proxies the query API under its standard token verification and policy enforcement.
5. **Portal view + deployment** (R-5 + overlay): the read-only audit view in the operator portal, and the dev-k8s overlay additions (PostgreSQL StatefulSet, audit-service deployment, secrets, Makefile plumbing).

The design reuses established patterns rather than inventing new ones: frozen-dataclass settings from env (all services), the strategy-pattern store factory (SPEC-006 `build_session_store` precedent), the SPEC-008/009 credential vocabulary for ingest auth, and the platform-gateway proxy + deny-by-default policy pattern for the query path.

## Design Per Requirement

### R-1: Audit event contract

- affected files: `shared/shared-contracts/schemas/audit-event.schema.json` (new); Pydantic models in each emitter's `schemas/` package and in audit-service; contract tests in each product's `tests/`
- chosen approach: one envelope schema with a closed set of top-level fields (`event_id`, `occurred_at`, `event_type`, `service`, `request_id`, `subject`, `username`, `actor`, `roles`, `session_id`, `outcome`, `details`) and `event_type` as an enum (`tool_invoked`, `policy_decision`, `token_exchange`, `session_created`, `chat_started`, `chat_completed`). `details` is a per-event-type open object (e.g. `tool_invoked` carries `tool_name`, `status`, `duration_ms`, `redacted_spans`) so the envelope stays stable while event payloads grow
- `event_id` is a UUID minted by the emitter; `occurred_at` is the emitter's UTC timestamp — the audit service never rewrites either, so log lines and stored records correlate 1:1
- alternatives considered: a separate schema per event type (rejected — multiplies contract-test and versioning surface for little type-safety gain; the per-type `details` object documents its fields in the schema description instead)

### R-2: Audit service with durable store

- affected files: new product `products/audit-service` (package `audit_service`), mirroring the tool-gateway layout: `api/routes/{health,ingest,query}.py`, `core/{config,metrics,observability,request_context,runtime,telemetry}.py`, `services/{audit_store,retention}.py`, `schemas/audit.py`
- store design (SPEC-006 precedent):

```python
class AuditStore(Protocol):
    async def add(self, events: Sequence[AuditEvent]) -> int: ...
    async def query(self, filters: AuditQuery, cursor: str | None, limit: int) -> AuditPage: ...
    async def count(self) -> int: ...
    async def evict(self, older_than: datetime, max_events: int) -> int: ...
    async def ready(self) -> bool: ...

def build_audit_store(settings: AuditSettings) -> AuditStore: ...
```

  - `InMemoryAuditStore` for tests/dev: bounded deque + dict indexes per filter dimension
  - `PostgresAuditStore` for deployed environments: single `audit_events` table; `CREATE TABLE IF NOT EXISTS` at startup (schema v1, no migration framework yet — recorded as a known boundary); indexes on `occurred_at DESC`, `username`, `session_id`, `request_id`, `event_type`; keyset pagination over `(occurred_at, event_id)`
- driver choice: `psycopg[binary]` v3 async, used directly (no SQLAlchemy) — consistent with the repo's minimal-dependency style (raw `httpx`, raw `redis`)
- settings (`AuditSettings.from_env`, frozen dataclass): `AUDIT_STORE_BACKEND` (`memory` | `postgres`, default `memory`), `AUDIT_DB_URL`, `AUDIT_INGEST_CLIENTS` (static registry, format `client_id=secret,...`), `AUDIT_WORKLOAD_ISSUER_URL` / `AUDIT_WORKLOAD_AUDIENCE` / `AUDIT_WORKLOAD_CLIENTS`, `AUDIT_RETENTION_DAYS`, `AUDIT_MAX_EVENTS`, `AUDIT_EVICTION_INTERVAL_SECONDS`, `AUDIT_MAX_BATCH`
- `/health` reports store backend, readiness, retention window, and approximate event count; `/metrics` follows `observability-conventions.md` with `audit_events_ingested_total{service,event_type}`, `audit_ingest_rejected_total`, `audit_query_total`, `audit_evicted_total`, `audit_store_errors_total`, `audit_store_events` (gauge)
- Dockerfile builds `FROM luban-aiops/base-uv:al2023`; product Makefile includes `mk/image.mk` + `mk/python.mk`; `.python-version` matches the other services

### R-3: Authenticated non-blocking ingestion

- ingest endpoint: `POST /api/v1/audit/events` accepts `{"events": [...]}` up to `AUDIT_MAX_BATCH` (default 50). Malformed events → 400 with `audit_ingest_rejected_total` incremented; nothing is partially stored
- **ingest auth refinement of Q-3**: emitters authenticate to the audit service using the same credential *vocabulary* the broker validates, verified locally by audit-service (the same architecture as tool-gateway verifying user JWTs via JWKS rather than calling the broker per request):
  - static path: HTTP Basic against `AUDIT_INGEST_CLIENTS` (dev default; the dev-k8s overlay reuses the shared delegation-secret generation so no second secret vocabulary appears)
  - workload path: Bearer projected SA token validated against the cluster OIDC issuer JWKS with audience + subject-registry checks, mirroring identity-broker's `authenticate_workload_client`
  - this avoids a new broker client-credentials endpoint (the exchange flow is user-subject-bound by design and cannot mint pure service tokens); the decision is recorded here since Q-3's wording ("register audit-service as a new audience/client") could be misread as requiring one
- emitter design (one small `services/audit_emitter.py` per product; the repo keeps per-service copies rather than a shared SDK):
  - enabled only when `<PREFIX>_AUDIT_SERVICE_URL` is set (`GATEWAY_AUDIT_SERVICE_URL`, `PLATFORM_GATEWAY_AUDIT_SERVICE_URL`, `IDENTITY_AUDIT_SERVICE_URL`); unset preserves today's byte-identical log-only behavior
  - `emit(event)` schedules `asyncio.create_task(_post(...))` with a 2s `httpx` timeout; all failures are swallowed, counted (`audit_emit_failures_total` on the emitter), and logged at WARNING once per interval — the originating request path never awaits or fails on audit delivery
  - volume argument for direct-per-event (no internal queue): audit events fire at business-request frequency (tool calls, chats, exchanges), not per-HTTP-request; `http_request` middleware events are excluded by R-1
- emission points: tool-gateway `invoke_tool` choke point (`tool_invoked`, both statuses, plus policy-denied invocations); platform-gateway policy decisions, `session_created`, `chat_stream_started`, `chat_completed`; identity-broker `token_exchange` granted and `token_exchange_rejected`. Existing `log_event` pod-log emission is retained untouched at every point

### R-4: Permission-scoped query API

- audit-service: `GET /api/v1/audit/events?username=&session_id=&request_id=&event_type=&service=&since=&until=&cursor=&limit=`; newest-first; keyset cursor (`occurred_at|event_id`, opaque base64); `limit` default 50, max 200; response `{events: [...], next_cursor, total_estimate}`
- policy: new rule `audit:read` in the canonical `policy-default.yaml` granted to `auditor` and `platform-admin` only; propagated with `make sync-policy` to all consumer copies; the route inventory/policy tests in both gateways are extended
- platform-gateway: new `api/routes/audit.py` proxies the query route to `audit-service` (`PLATFORM_GATEWAY_AUDIT_URL`), behind the standard portal-token verification and `enforce_policy("audit:read")`; added to `PROTECTED_ACTIONS`; deny returns the existing structured 403
- stored records are returned verbatim — no field mapping between ingest and query; redaction is inherited because emitters send post-redaction payloads (SPEC-009 choke point)

### R-5: Operator portal audit view

- affected files: `products/operator-portal/web-ui/` (new audit panel markup/script/style hooks reusing the existing CSS variables and drawer idioms)
- design: a new "Audit trail" panel reachable from the existing header; filter bar (username, event type, service, time range), newest-first table with cursor-paginated "load more", and expandable rows showing the full envelope (including `actor` delegation chain and request/session IDs)
- client-side gating: the panel's navigation entry renders only when the decoded portal JWT `roles` include `auditor` or `platform-admin`; the API denies everyone else regardless, so the client check is UX, not security
- the SPEC-011 per-turn evidence/audit groups remain untouched

### R-6: Retention and bounded growth

- `services/retention.py` runs an `asyncio` background task started in the app lifespan: every `AUDIT_EVICTION_INTERVAL_SECONDS` (default 3600) it deletes `occurred_at < now - AUDIT_RETENTION_DAYS` in batches, then enforces `AUDIT_MAX_EVENTS` by deleting the oldest excess; evictions are counted and logged
- deletes run as their own short transactions so ingest is never blocked beyond normal contention; batch size bounded (default 1000)
- in-memory backend applies the same bounds on add (cheap, keeps dev behavior honest)

## Sequencing And Dependencies

1. shared-contracts: `audit-event.schema.json` + `audit:read` policy rule (depends on nothing; `make sync-policy` after)
2. audit-service skeleton: product scaffolding (Makefile, Dockerfile, pyproject/uv lock, settings, app, health, metrics) — depends on stage 1 for the Pydantic model
3. audit-service stores: `AuditStore` protocol + `InMemoryAuditStore`, then `PostgresAuditStore`; ingest + query routes; retention task — depends on stage 2
4. emitters in tool-gateway, platform-gateway, identity-broker — depends on stage 1 (contract); independent of stages 2/3 at code level (feature-gated off by default), but integration-tested after stage 3
5. platform-gateway audit proxy + `audit:read` enforcement — depends on stages 1, 3
6. operator portal audit view — depends on stage 5
7. dev-k8s overlay: PostgreSQL StatefulSet + PVC + Service, audit-service deployment/service/runtime-config, emitter env vars, ingest-credential secret + sync script, root Makefile plumbing (`PYTHON_PRODUCTS`/`IMAGE_PRODUCTS` + `.images.env` `AUDIT_SERVICE_IMAGE` + kind-load list) — depends on stages 2–6
8. docs and delivery housekeeping: guides updates, READMEs, CHANGELOG, spec index, release notes — depends on stage 7 validation

## Test Strategy

- unit tests:
  - audit-service: ingest validation (400 paths, batch cap), auth (static accept/reject, workload accept/reject/unregistered), query filters + pagination + ordering, retention eviction (window and max-count), store factory selection, health/metrics surfaces; `InMemoryAuditStore` exercises the full protocol; `PostgresAuditStore` SQL logic tested against a fake driver double (the repo's existing `FakeHttp`-style test-double convention), with live Postgres exercised only in dev-cluster validation
  - emitters: enabled/disabled behavior byte-identical when URL unset; failure swallow + counter when audit-service unreachable (fake transport)
  - platform-gateway: route-inventory test extended for `/api/v1/audit/*`; proxy test with `audit:read` allow/deny per role
- contract tests: emitter and audit-service models bound to `audit-event.schema.json` (same pattern as the `tool-invocation.schema.json` bindings); policy contract test binds the synced `audit:read` copies
- integration / overlay validation: `make verify` (all suites + every overlay render + `validate-policy`); live dev-cluster validation: deploy, chat + tool call, then verify stored events via the portal audit view and direct query API as an `auditor`-role user, verify denial as `operator`, restart the audit-service pod and confirm trail survives, advance retention knob to confirm eviction

## Rollout And Migration

- deployment changes: new PostgreSQL StatefulSet (single replica, PVC, `postgres:16-alpine`) and audit-service deployment in the dev-k8s overlay; new optional secret for ingest credentials generated by a `sync-audit-secrets.sh` script following the `sync-delegation-secrets.sh` pattern (wired into `make deploy`, skippable via env switch)
- backward compatibility: everything is feature-gated — emitters stay log-only until `<PREFIX>_AUDIT_SERVICE_URL` is set; the audit-service query route is deny-by-default until the `audit:read` rule exists; portal navigation hides the panel for unauthorized roles. Existing request paths are untouched: no chat, tool, or identity behavior changes
- rollback: unset the emitter audit URLs to return to log-only auditing immediately; the audit-service deployment can be deleted independently without affecting any request path; dropping the `audit:read` rule closes the query surface. The PostgreSQL PVC can be retained or deleted depending on whether the trail should survive a rollback
