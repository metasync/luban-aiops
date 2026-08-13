# SPEC-013 Tasks: Durable Audit Trail

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Audit event contract

- [x] Create `shared/shared-contracts/schemas/audit-event.schema.json` (envelope fields, `event_type` enum, per-type `details` documentation)
- [x] Add `audit:read` rule (roles: `auditor`, `platform-admin`) to canonical `shared/shared-contracts/policies/policy-default.yaml` and run `make sync-policy`
- [x] Contract test binding emitter/audit-service Pydantic models to the schema (`products/*/tests/`)

## R-2: Audit service with durable store

- [x] Scaffold `products/audit-service`: Makefile (image+python fragments), Dockerfile on `base-uv`, pyproject + uv lock, `.python-version`, package layout mirroring tool-gateway (`shared/`, `products/audit-service/`)
- [x] `AuditSettings` frozen dataclass from env (`AUDIT_STORE_BACKEND`, `AUDIT_DB_URL`, ingest auth, retention, batch knobs) (`products/audit-service/src/audit_service/core/config.py`)
- [x] App skeleton: structured logging (`configure_logging`), request-id middleware, telemetry, `/health` + `/health/ready`, always-on `/metrics` (`products/audit-service/src/audit_service/`)
- [x] `AuditStore` protocol + `InMemoryAuditStore` + `build_audit_store` factory (`products/audit-service/src/audit_service/services/audit_store.py`)
- [x] `PostgresAuditStore`: psycopg v3 async pool, `CREATE TABLE IF NOT EXISTS` + indexes at startup, keyset pagination query (`products/audit-service/src/audit_service/services/audit_store.py`)
- [x] Store tests: in-memory protocol coverage; Postgres SQL logic against a fake driver double (`products/audit-service/tests/`)
- [x] Add `audit-service` to root Makefile (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, `.images.env` `AUDIT_SERVICE_IMAGE`, kind-load list) (`Makefile`)

## R-3: Authenticated non-blocking ingestion

- [x] Ingest route `POST /api/v1/audit/events` with batch cap and 400 rejection counting (`products/audit-service/src/audit_service/api/routes/ingest.py`)
- [x] Ingest auth: static Basic registry (`AUDIT_INGEST_CLIENTS`) + projected workload token verification against cluster OIDC issuer JWKS (`AUDIT_WORKLOAD_*`), mirroring identity-broker `exchange_service` (`products/audit-service/src/audit_service/services/ingest_auth.py`)
- [x] Ingest auth tests: static accept/reject, workload accept/expired/wrong-audience/unregistered (`products/audit-service/tests/`)
- [x] `audit_emitter.py` in tool-gateway: fire-and-forget task, 2s timeout, failure counter, feature-gated by `GATEWAY_AUDIT_SERVICE_URL`; emit at the `invoke_tool` choke point incl. denied invocations (`products/tool-gateway/`)
- [x] `audit_emitter.py` in platform-gateway: emit policy decisions, `session_created`, `chat_stream_started`, `chat_completed`; gated by `PLATFORM_GATEWAY_AUDIT_SERVICE_URL` (`products/platform-gateway/`)
- [x] `audit_emitter.py` in identity-broker: emit token exchange granted/rejected; gated by `IDENTITY_AUDIT_SERVICE_URL` (`products/identity-broker/`)
- [x] Emitter tests per service: unset URL = byte-identical log-only behavior; unreachable audit-service swallowed + counted (`products/*/tests/`)

## R-4: Permission-scoped query API

- [x] Query route `GET /api/v1/audit/events` with filters + keyset cursor + limit bounds (`products/audit-service/src/audit_service/api/routes/query.py`)
- [x] Query tests: filters, ordering, pagination, verbatim envelope round-trip (`products/audit-service/tests/`)
- [x] platform-gateway proxy route `/api/v1/audit/*` with token verification + `enforce_policy("audit:read")`; extend `PROTECTED_ACTIONS` (`products/platform-gateway/src/platform_gateway/api/routes/audit.py`)
- [x] platform-gateway tests: route inventory + per-role allow/deny proxy test (`products/platform-gateway/tests/`)

## R-5: Operator portal audit view

- [x] Audit trail panel: filter bar (username, event type, service, time range), newest-first table, cursor pagination, expandable event envelope (`products/operator-portal/web-ui/`)
- [x] Client-side gating: nav entry renders only for `auditor` / `platform-admin` roles from the portal JWT (`products/operator-portal/web-ui/`)

## R-6: Retention and bounded growth

- [x] Retention background task: window eviction + `AUDIT_MAX_EVENTS` cap, batched deletes, eviction metric (`products/audit-service/src/audit_service/services/retention.py`)
- [x] Retention tests: window eviction, max-count cap, in-memory bounds on add (`products/audit-service/tests/`)
- [x] Expose retention window + store size in `/health` / `/metrics` (`products/audit-service/`)

## Deployment and Integration

- [x] dev-k8s: PostgreSQL StatefulSet + PVC + Service (`shared/platform-ops/gitops/dev-k8s/base/infra/`)
- [x] dev-k8s: audit-service deployment + service + runtime-config (`AUDIT_STORE_BACKEND=postgres`, `AUDIT_DB_URL`, ingest registry env) (`shared/platform-ops/gitops/dev-k8s/base/audit-service/`)
- [x] dev-k8s: `sync-audit-secrets.sh` for shared ingest credentials (following `sync-delegation-secrets.sh` pattern), wired into `make deploy` with skip switch (`shared/platform-ops/gitops/dev-k8s/`)
- [x] dev-k8s: emitter env vars (`*_AUDIT_SERVICE_URL`) in tool-gateway, platform-gateway, identity-service runtime-config
- [x] Live dev-cluster validation: chat + tool call → events visible via query API and portal view as `auditor`; denied as `operator`; trail survives audit-service pod restart; retention knob eviction observed

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated:
  - [x] root `README.md` (service inventory)
  - [x] product READMEs (emitters + new audit-service README)
  - [x] dev-k8s overlay README (Postgres, audit secrets, env vars)
  - [x] `docs/guides/configuration-reference.md` (audit env vars + dependency chain)
  - [x] `docs/guides/architecture-overview.md` (audit-service in topology)
  - [x] `docs/guides/tool-configuration.md` or dedicated section (audit-service activation checklist)
  - [x] `docs/guides/troubleshooting.md` (audit symptoms: events missing, ingest 401, query denied)
- [x] `CHANGELOG.md` entry added referencing SPEC-013
- [x] spec index in `docs/specs/README.md` updated
- [x] `make verify` green (all product tests incl. audit-service + all overlay renders + policy validation)
- [x] release notes for the SPEC-013 wave
- [x] spec status set to `delivered`
