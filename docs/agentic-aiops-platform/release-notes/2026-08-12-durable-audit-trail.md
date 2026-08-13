# Release Notes: 2026-08-12 — Durable Audit Trail (SPEC-013)

## Summary

SPEC-013 replaces the ephemeral pod-log audit trail with a durable,
queryable, permission-scoped audit service. The release delivers a
canonical audit-event contract, a new `audit-service` product with
in-memory and PostgreSQL stores, authenticated fire-and-forget ingestion
from the three emitting services, a policy-gated query API proxied
through platform-gateway, a read-only audit view in the operator portal,
and bounded retention.

This closes the primary known limitation named by both Release 1 release
notes — "the authoritative audit trail remains in pod logs only" — and
gives the `auditor` role defined in the authorization matrix its first
platform surface to read from.

`make verify` is green: all product tests (agent-platform 122,
audit-service 68, identity-broker 57, platform-gateway 92, tool-gateway
117 — 456 total), all four Kustomize overlays render cleanly, and the
policy validation target confirms the five-rule deny-by-default bundle.

## Change Set 1: Audit event contract and policy rule (R-1)

### Highlights

- `shared/shared-contracts/schemas/audit-event.schema.json`: canonical
  envelope (`event_id`, `occurred_at`, `event_type`, `service`,
  `request_id`, `subject`, `username`, optional `actor` delegation chain,
  `roles`, optional `session_id`, `outcome`, typed `details`) covering
  `tool_invoked`, `policy_decision`, `token_exchange`, `session_created`,
  `chat_started`, `chat_completed`
- New `audit:read` action in the canonical policy bundle, granted to
  `auditor` and `platform-admin` only; synced to all consumer copies via
  `make sync-policy` and validated by `make validate-policy`
- Contract tests in audit-service bind the Pydantic models to the schema,
  following the existing `tool-invocation.schema.json` pattern

### Why It Matters

- every emitting service and the store now bind to one schema, so the
  envelope cannot drift between emitter and query surface
- `http_request` middleware noise stays out of the audit contract by
  design — the trail records decisions and actions, not traffic

## Change Set 2: audit-service product (R-2, R-6)

### Highlights

- New `products/audit-service` product: FastAPI on the shared `base-uv`
  image, frozen-dataclass `AUDIT_*` settings, structured JSON logging,
  `/health` + `/health/ready`, always-on `/metrics`, wired into the root
  Makefile (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, `.images.env`, kind-load)
- `AuditStore` protocol with two backends selected by `AUDIT_STORE_BACKEND`:
  `InMemoryAuditStore` for tests/dev and `PostgresAuditStore` (psycopg v3
  async pool, startup DDL with indexes, keyset pagination) for deployed
  environments
- Retention background task: `AUDIT_RETENTION_DAYS` (default 30) window
  eviction plus an `AUDIT_MAX_EVENTS` hard cap, batched deletes, eviction
  counted in metrics, never blocking ingest; window and store size exposed
  in `/health` and `/metrics`

### Why It Matters

- audit events survive pod restarts and redeployments in dev-k8s
  (WAL-durable Postgres on a PVC) and remain queryable across services
- bounded growth means the trail cannot exhaust its backend, even within
  the retention window

## Change Set 3: Authenticated non-blocking ingestion (R-3)

### Highlights

- `POST /api/v1/audit/events` accepts small batches (capped by
  `AUDIT_MAX_BATCH`), rejects malformed events with 400 and a counter,
  and authenticates callers via a static Basic client registry
  (`AUDIT_INGEST_CLIENTS`) or projected workload tokens (`AUDIT_WORKLOAD_*`)
  — the SPEC-008/009 credential vocabulary, verified locally
- Fire-and-forget emitters in tool-gateway, platform-gateway, and
  identity-broker: 2s bounded timeout, delivery counted in
  `audit_emits_total{result}`; audit-service unreachability degrades to
  log-only auditing and the user-facing request still succeeds
- Feature-gated by `*_AUDIT_SERVICE_URL`: unset preserves today's
  byte-identical log-only behavior; structured pod-log emission retained
  alongside the audit service

### Why It Matters

- the audit path can never take down or slow a user-facing request —
  durability is best-effort on delivery, authoritative in storage
- every event previously visible only in pod logs (`tool_invoked`
  including denied invocations, policy decisions, token exchange
  granted/rejected, session and chat lifecycle) now lands in the durable
  store when the URL is configured

## Change Set 4: Permission-scoped query and portal view (R-4, R-5)

### Highlights

- `GET /api/v1/audit/events` supports `username`, `session_id`,
  `request_id`, `event_type`, `service`, and `since`/`until` filters with
  newest-first cursor pagination; query results carry the exact stored
  envelope (no field loss)
- platform-gateway proxies the route under `/api/v1/audit/*` with its
  standard portal-token verification and `enforce_policy("audit:read")`;
  deny returns the structured 403, and `PROTECTED_ACTIONS` now includes
  `audit:read`
- Operator portal gains a read-only audit trail function view (sidebar
  navigation entry): filter bar
  (username, event type, service, time range), newest-first table, cursor
  pagination, expandable envelopes including the delegation chain; the nav
  entry renders only for identities whose roles hold `audit:read`

### Why It Matters

- cross-user troubleshooting ("what tools did user X invoke last week")
  becomes a platform capability instead of `kubectl logs`
- the `auditor` role is now end-to-end useful without cluster access, and
  deny-by-default keeps cross-user activity visible to exactly two roles

## Change Set 5: dev-k8s deployment

### Highlights

- PostgreSQL StatefulSet + PVC + Service under `base/infra/`
- audit-service deployment/service/runtime-config
  (`AUDIT_STORE_BACKEND=postgres`, `AUDIT_DB_URL`, ingest registry env)
- `sync-audit-secrets.sh` generates the shared ingest credential and the
  matching emitter secrets (following `sync-delegation-secrets.sh`), wired
  into `make deploy` with a skip switch
- Emitter env (`GATEWAY_AUDIT_SERVICE_URL`,
  `PLATFORM_GATEWAY_AUDIT_SERVICE_URL`, `IDENTITY_AUDIT_SERVICE_URL`) set
  in the three emitting services' runtime-config; policy ConfigMap updated

### Why It Matters

- `make deploy` brings up the full durable trail with no manual steps;
  skipping audit secrets keeps existing clusters bootable while the
  feature is opt-in per environment

## Change Set 6: Operator portal shell redesign

### Highlights

- Two-column app shell replacing the stacked panels: left sidebar with the
  logo and the function list (Chat, Settings & Debug, Audit trail); the
  main column shows one function view at a time with state preserved
  across switches; narrow screens (≤800px) collapse the sidebar into a
  hamburger-triggered off-canvas drawer
- Sidebar footer separating state from functions: a user card (initials
  avatar, username, icon-only Sign in / Sign out with tooltips; clicking
  the user opens a popup menu showing granted roles, extensible to future
  user-related info) and a platform version card
- Polish: sticky audit-table column headers, `:focus-visible` keyboard
  focus rings, and `prefers-reduced-motion` guards on animations

### Why It Matters

- the portal stays slim and focused on operating with the agent; identity
  and version are reference state at the bottom, functions on top
- the redesign shipped together with the audit view, so the new trail is
  experienced inside the final navigation model

## Known Limitations

- audit records are not tamper-proof (no append-only WORM storage or hash
  chains) — integrity measures are deferred to the R4 approval-gated
  actions release per the spec's non-goals
- the Postgres store is validated against a fake driver double in unit
  tests; live-cluster soak (restart durability, retention eviction under
  load) is part of operational validation rather than `make verify`
- historical pod logs are not backfilled; the durable trail starts at
  deployment time
- archival to object storage and long-term compliance retention beyond the
  bounded R-6 window are out of scope

## Related Documents

- `../../specs/SPEC-013-durable-audit-trail/spec.md`
- `../../specs/SPEC-013-durable-audit-trail/plan.md`
- `../../specs/README.md` (spec index, SPEC-013 delivered)
- `../../../CHANGELOG.md`
