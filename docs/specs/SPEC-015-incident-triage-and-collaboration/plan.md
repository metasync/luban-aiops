# SPEC-015 Plan: Incident Triage And Collaboration (Release 3)

## Approach

incident-service is built as a near-twin of `skills-hub`/`audit-service` —
same frozen-dataclass settings, structured logging, `/health` + `/metrics`,
store-protocol with in-memory and Postgres backends, Basic-client/workload-
token auth — so the platform absorbs the seventh service with zero new
architectural vocabulary. On top of that chassis sit three incident-specific
subsystems: an Alertmanager normalizer, a triage orchestrator that drives the
existing agent runtime, and a pluggable connector framework.

Triage reuses the chat identity path end to end: platform-gateway resolves
the operator, enforces `incident:triage`, obtains the delegated token exactly
as chat does, and forwards it to incident-service, which calls agent-platform
`/api/v2/chat` in a dedicated `incident-<id>` session. The report comes back
as a fenced `triage-report` JSON block validated against the shared schema —
no write tool is introduced, so the SPEC-007 read-only invariant holds.

Implementation stages: (1) contracts, (2) incident-service chassis + intake +
stores, (3) triage orchestration + connectors, (4) tool-gateway connector,
(5) platform-gateway proxy routes + policy, (6) agent-platform prompt and
allow-list, (7) operator portal Incidents experience, (8) overlay + demo +
secrets sync, (9) living docs and delivery artifacts.

## Design Per Requirement

### R-1: Incident and triage-report contract

- affected files: `shared/shared-contracts/schemas/incident.schema.json`
  (new), `shared/shared-contracts/schemas/triage-report.schema.json` (new),
  `products/incident-service/src/incident_service/schemas/incident.py` (new
  Pydantic models), contract tests
- incident envelope fields per spec R-1; `labels` is a string map (bounded
  key/value lengths), `summary` ≤ 2000 chars; timestamps are RFC-3339
  strings produced by the service
- report fields per spec R-1; `next_steps` capped at 10 entries, each
  `priority` one of `high` | `medium` | `low`; `evidence` entries carry
  `source` (tool name or `skills`) and `description` (≤ 400 chars);
  `skills_cited` is a list of `skill_id`s
- contract tests follow `skills-hub/tests/test_contracts.py`: model
  instances validate against the JSON schemas, required fields asserted

### R-2: incident-service product with dual intake

- affected files: new `products/incident-service` product (Dockerfile,
  Makefile, pyproject + uv lock, README, src tree, tests), layout mirroring
  skills-hub:
  - `app.py`, `main.py`, `metadata.py`
  - `api/routes/health.py`, `api/routes/incidents.py`,
    `api/routes/webhooks.py`
  - `core/config.py`, `core/metrics.py`, `core/observability.py`,
    `core/request_context.py`, `core/runtime.py`, `core/telemetry.py`
  - `services/normalization.py` (Alertmanager → canonical),
    `services/incident_store.py` (protocol + InMemory + Postgres),
    `services/query_auth.py` (Basic registry + workload tokens),
    `services/triage.py` (orchestration), `services/connectors.py`
    (protocol + registry + audit sink), `services/audit_emitter.py`
- settings (frozen dataclass, env → field): `INCIDENT_WEBHOOK_TOKEN`
  (secret), `INCIDENT_QUERY_CLIENTS` (Basic registry JSON),
  `INCIDENT_WORKLOAD_ISSUER_URL`, `INCIDENT_WORKLOAD_AUDIENCE` (default
  `incident-service`), `INCIDENT_WORKLOAD_CLIENTS`, `INCIDENT_STORE_BACKEND`
  (`memory` | `postgres`), `INCIDENT_DB_URL`, `INCIDENT_CONNECTORS`
  (default `audit`), `INCIDENT_AGENT_SERVICE_URL` (default
  `http://agent-service:8000`), `INCIDENT_AUDIT_SERVICE_URL`,
  `INCIDENT_AUDIT_CLIENT_ID`, `INCIDENT_AUDIT_CLIENT_SECRET`,
  `INCIDENT_TRIAGE_TIMEOUT_SECONDS` (default 120), `INCIDENT_LOG_LEVEL`
- Alertmanager normalization (`normalization.py`): pure function
  `normalize_alertmanager(payload) -> IncidentInput | NormalizationError`;
  uses `status`, `groupKey`, `commonLabels`, `commonAnnotations`,
  `alerts[]`; fingerprint = `groupKey` when present else sha256 over the
  sorted `commonLabels` items; severity from `commonLabels.severity`
  (`critical` passes through, `warning`/absent → `warning`, anything else
  → `info`); title from `commonAnnotations.summary` (fallback:
  `commonLabels.alertname`); summary from `commonAnnotations.description`
  (fallback: label render); `startsAt`/`endsAt` ignored beyond status
- resolved handling: `status == "resolved"` resolves the fingerprint's open
  incident (sets `resolved` + `resolved_at`); unknown fingerprint on
  resolved is a no-op success (idempotent webhook semantics)
- manual intake: Pydantic request (title required ≤ 200 chars, summary
  ≤ 2000 chars, severity enum default `warning`, labels optional map);
  fingerprint = `manual:` + sha256 of title+summary so identical manual
  reports dedupe within a short window is intentionally NOT done — manual
  incidents always create (fingerprint carries a uuid suffix); `source`
  `manual`, `reported_by` from the `X-Reported-By` header (gateway sets it
  to the operator username)
- store: `IncidentStore` protocol — `create`, `get`, `list` (filters +
  offset/limit), `update_status`, `set_report`, `resolve`; Postgres schema:
  `incidents` (incident_id pk, fingerprint, source, severity, status,
  title, summary, labels jsonb, reported_by, created_at, updated_at,
  resolved_at) + `triage_reports` (incident_id pk/fk, report jsonb,
  generated_at) + `connector_dispatches` (id, incident_id, connector,
  status, reference, created_at); index on (status, created_at desc) and
  fingerprint
- auth: `query_auth.py` mirrors skills-hub's — Basic registry first,
  workload tokens when configured; the webhook route uses its own bearer
  token check (`INCIDENT_WEBHOOK_TOKEN` required non-empty at startup when
  the route is to serve; empty token → webhook route returns 503 to fail
  closed)

### R-3: Operator-initiated agent triage with structured report capture

- affected files: `products/incident-service/src/incident_service/
  services/triage.py`, `api/routes/incidents.py` (triage endpoint),
  `products/platform-gateway/src/platform_gateway/api/routes/incidents.py`
  (new proxy), `products/agent-platform/src/agent_service/
  runtime_settings.py` (prompt)
- gateway route `POST /api/v1/incidents/{incident_id}/triage`: resolve
  identity → `enforce_policy(..., "incident:triage")` →
  `obtain_delegated_token(...)` (identical to chat) → POST to
  incident-service with Basic service credential, `X-User-ID: <username>`,
  `X-Request-Id`, and `Authorization: Bearer <delegated>`; timeout uses
  `INCIDENT_TRIAGE_TIMEOUT_SECONDS` on the incident-service side (gateway
  proxy timeout = same value + margin)
- incident-service triage endpoint: fetch record (404 unknown) → set
  `triaging` → build prompt from `TRIAGE_PROMPT_TEMPLATE` (module constant:
  incident context block + discipline + fenced report-format instructions
  with the exact JSON shape) → `httpx` POST to
  `{INCIDENT_AGENT_SERVICE_URL}/api/v2/chat` with `session_id =
  incident-<id>`, `X-User-ID` relayed, bearer relayed → extract the
  ```triage-report fenced block, `json.loads`, validate via the Pydantic
  report model → store, set `triaged`, dispatch connectors; any failure in
  fetch/parse/validation sets `triage_failed` and stores the raw agent text
  in a record field (`triage_raw`), counted by an
  `incident_triages_total{result}` counter
- re-triage: latest report wins (`triage_reports` upsert by incident_id);
  prior dispatch history retained
- agent-platform `DEFAULT_SYSTEM_PROMPT` gains the triage-report
  discipline paragraph (one fenced `triage-report` block, schema shape,
  evidence/skill grounding, no fabrication, advisory-only next steps)

### R-4: Read-only incident tools in the tool execution framework

- affected files: `products/tool-gateway/src/tool_gateway/tools/
  incidents_connector.py` (new), `core/config.py` (settings), `app.py`
  (registration), agent-platform `tools/gateway_tools.py` (allow-list)
- settings additions: `incidents_service_url`
  (`GATEWAY_INCIDENTS_SERVICE_URL`, default empty → disabled),
  `incidents_client_id` (`GATEWAY_INCIDENTS_CLIENT_ID`, default
  `tool-gateway`), `incidents_client_secret`
  (`GATEWAY_INCIDENTS_CLIENT_SECRET`)
- `IncidentsConnector` follows the `SkillsConnector` shape:
  `incidents.list` (params: `status`/`severity`/`source` optional, `limit`
  optional capped 50) and `incidents.get` (param: `incident_id` required,
  includes the triage report when present), both `risk_level="read"`,
  `category="incidents"`
- transport: `httpx.AsyncClient`, 10s timeout, Basic auth from the
  gateway-held credential; upstream 404 → `INCIDENT_NOT_FOUND`, other 4xx
  pass through, connection failure → `TOOL_EXECUTION_ERROR`; evidence
  envelope via `build_evidence("read", "incidents", duration_ms)`
- `incidents.list` result `data`: `{"incidents": [<envelope minus
  summary>], "total": n}`; this object is the `data_summary` of the
  `tool_result` frame rendered by the portal evidence panel
- allow-list: `DEFAULT_AUTO_ALLOWED_TOOLS` gains `incidents.list` and
  `incidents.get`

### R-5: Collaboration connector framework with built-in audit sink

- affected files: `products/incident-service/src/incident_service/
  services/connectors.py`, `services/audit_emitter.py`
- `Connector` protocol: `name: str`, `async def dispatch(incident, report)
  -> ConnectorOutcome(status: "delivered" | "failed", reference: str |
  None, error: str | None)`
- registry maps names → factories receiving `IncidentSettings`; the `audit`
  connector posts an `incident_triaged` event to audit-service's ingest
  endpoint with the gateway-held-style Basic credential
  (`INCIDENT_AUDIT_*`); dispatch records persisted via the store; failures
  logged + counted (`incident_connector_dispatches_total{connector,
  result}`), never raised into the triage path
- README documents the extension point: implement `Connector`, register in
  `CONNECTOR_REGISTRY`, add the name to `INCIDENT_CONNECTORS`

### R-6: Operator portal Incidents experience

- affected files: `products/operator-portal/web-ui/index.html`,
  `app.js`, `styles.css`
- sidebar gains an `Incidents` entry alongside Chat/Audit; the incidents
  view renders through the gateway API (`/api/v1/incidents*`) with the
  existing bearer machinery
- list: filter chips (status, severity), newest-first rows (title,
  severity badge, status badge, source, relative age), auto-refresh every
  15s while visible
- detail: record header + triage report sections (summary, severity
  assessment, hypotheses, ranked next steps with priority badges, evidence
  list, cited skill ids, connector dispatch outcomes); "Run triage" button
  (disabled with spinner while `triaging`; on `triage_failed` shows the
  preserved raw text in a collapsible block); "Report incident" form in the
  list header; "Continue in chat" switches to the chat view with
  `session_id=incident-<id>`
- styling reuses the existing design tokens (badges reuse the severity-ish
  palette already present for statuses); no new CSS vocabulary beyond
  incident-specific section classes

### R-7: Deployment, configuration, and living-state docs

- affected files: `shared/platform-ops/gitops/dev-k8s/base/incident-
  service/` (new: deployment, service, runtime-config.env,
  runtime-secrets.env + example), `base/infra/postgres-statefulset.yaml`
  (initdb mount gains `create-incidents-db.sql`),
  `shared/platform-ops/gitops/sync-incident-secrets.sh` (new, mirrors
  sync-skills-secrets.sh: idempotent `CREATE DATABASE incidents`, writes
  `incident-service-runtime-secrets` incl. webhook token + query clients +
  audit credential, `SKIP_INCIDENT_SECRETS` opt-out), `deploy.sh` /
  `deploy-overlay.sh` wiring, `base/shared/policy.yaml` +
  `shared/shared-contracts/policies/policy-default.yaml` (incident rules),
  platform-gateway and tool-gateway runtime-config/secrets fragments
- policy additions (both bundles): `allow-ops-incidents` —
  `["platform-admin", "approver", "operator", "developer"]` ×
  `["incident:read", "incident:create", "incident:triage"]`;
  `allow-observer-incidents-read` — `["read-only-observer"]` ×
  `["incident:read"]`; priority 100 to match the existing table
- demo script `shared/platform-ops/e2e/incident-demo.sh`: webhook POST with
  token asserts 200 + incident visible; missing/bad token asserts 401;
  query API returns the incident; `incidents.list` tool via
  tool-gateway returns it; resolved payload flips status; chat-leg asserts
  an `incidents.list` `tool_call`/`tool_result` frame pair — LLM triage
  prose left to the scripted Incident triage tour in getting-started.md
  (UAT checklist: report → triage → report quality → continue in chat →
  audit presence)

### R-8: Tests and verification gate

- see Test Strategy below

## Sequencing And Dependencies

1. Contracts: `incident.schema.json` + `triage-report.schema.json` —
   depends on nothing
2. incident-service chassis + normalization + stores + auth — depends on (1)
3. Triage orchestration + connectors + triage endpoint — depends on (2)
4. tool-gateway incidents connector — depends on (2)'s API shape only
   (testable against a fake); parallel with (3)
5. platform-gateway proxy routes + policy actions — depends on (2)+(3)
   API shape
6. agent-platform prompt + allow-list — depends on (4) tool names only
7. operator portal Incidents experience — depends on (5) route shape
8. Overlay, secrets sync, demo script — depends on (2) image + env contract
9. Living docs, CHANGELOG, release note, delivery gate — depends on all

## Test Strategy

- unit tests (incident-service): normalization matrix (severity mapping,
  fingerprint with/without groupKey, resolved known/unknown, malformed
  payload → structured 400), dedupe on repeat firing, manual intake
  validation, webhook-token 401/200, query-auth 401/200, list filters +
  pagination bounds, triage orchestration (happy path via fake agent
  double, malformed JSON → `triage_failed` + raw preserved, agent 5xx →
  `triage_failed`), connector dispatch success/failure isolation +
  unknown-connector startup failure, Postgres store against a fake driver
  double
- unit tests (tool-gateway): registration gating, credential wiring, error
  mapping (404 → INCIDENT_NOT_FOUND, unreachable → TOOL_EXECUTION_ERROR),
  evidence envelope shape, contract tests vs R-1 schemas
- unit tests (platform-gateway): per-route policy enforcement (allow/deny
  paths for each incident action), delegation forwarding on triage, 503
  unconfigured, upstream 4xx pass-through / 5xx → 502
- unit tests (agent-platform): prompt contains the triage-report
  discipline, allow-list contains both incident tools (sanitized names)
- contract tests: incident-service models ↔ both schemas
- integration / overlay validation: `kustomize build` renders the dev-k8s
  overlay with the new base; policy validation script passes on both
  bundles; live-cluster verification is delivery-time `make deploy` +
  `incident-demo.sh`, not part of the gate

## Rollout And Migration

- deployment: `make deploy` gains incident-service automatically; existing
  clusters upgrade in place — the `incidents` database is created
  idempotently, no data migration
- backward compatibility: `GATEWAY_INCIDENTS_SERVICE_URL` unset leaves
  tool-gateway as before; incident-service absent from the cluster changes
  nothing for other services; policy additions are additive rules; the
  prompt extension is additive
- rollback: remove incident-service from the overlay, unset gateway URLs;
  the `incidents` database can be dropped without affecting any other
  service; no schema changes to existing databases
