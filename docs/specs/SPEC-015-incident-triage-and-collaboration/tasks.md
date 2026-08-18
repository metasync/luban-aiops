# SPEC-015 Tasks: Incident Triage And Collaboration (Release 3)

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Incident and triage-report contract

- [x] add `incident.schema.json` envelope (`shared/shared-contracts/schemas/`)
- [x] add `triage-report.schema.json` (`shared/shared-contracts/schemas/`)
- [x] implement Pydantic incident/report models (`products/incident-service/src/incident_service/schemas/incident.py`)
- [x] contract tests binding models to both schemas (`products/incident-service/tests/test_contracts.py`)

## R-2: incident-service product with dual intake

- [x] scaffold product: Dockerfile, Makefile (image+python fragments), pyproject + uv lock, metadata, README scaffold (`products/incident-service/`)
- [x] port core chassis: config, metrics, observability, request_context, runtime, telemetry, health route (mirror skills-hub)
- [x] Alertmanager normalization: severity mapping, fingerprint derivation, resolved handling (`services/normalization.py` + tests)
- [x] query auth: `INCIDENT_QUERY_CLIENTS` Basic registry + workload tokens, 401 path (`services/query_auth.py` + tests)
- [x] webhook route with bearer token auth, fail-closed on empty token (`api/routes/webhooks.py` + tests)
- [x] `IncidentStore` protocol + `InMemoryIncidentStore` (`services/incident_store.py` + tests)
- [x] `PostgresIncidentStore` (incidents + triage_reports + connector_dispatches tables, parameterized SQL) against a fake driver double
- [x] manual intake `POST /api/v1/incidents` with validation + `X-Reported-By` (tests)
- [x] query API: list with filters + capped pagination, get, get report; structured 404/400 (tests)

## R-3: Operator-initiated agent triage with structured report capture

- [x] `TRIAGE_PROMPT_TEMPLATE` + fenced `triage-report` extraction/validation (`services/triage.py` + tests with a fake agent double)
- [x] `POST /api/v1/incidents/{id}/triage` on incident-service: triaging → triaged/triage_failed, raw text preserved on failure, re-triage latest-wins (tests)
- [x] `incident_triages_total{result}` counter
- [x] extend `DEFAULT_SYSTEM_PROMPT` with the triage-report discipline (`products/agent-platform/.../runtime_settings.py` + tests)

## R-4: Read-only incident tools in the tool execution framework

- [x] settings: `incidents_service_url`, `incidents_client_id`, `incidents_client_secret` (`products/tool-gateway/.../core/config.py` + settings tests)
- [x] `IncidentsConnector` with `incidents.list` / `incidents.get` definitions and parameter schemas (`tools/incidents_connector.py`)
- [x] httpx transport with Basic auth, 10s timeout, error mapping (404 → `INCIDENT_NOT_FOUND`, unreachable → `TOOL_EXECUTION_ERROR`) (`tests/test_incidents_connector.py`)
- [x] registration in `_build_tool_registry()` gated on `GATEWAY_INCIDENTS_SERVICE_URL` (tests incl. unset-URL parity)
- [x] contract tests binding connector payloads to the R-1 schemas
- [x] add `incidents.list`, `incidents.get` to `DEFAULT_AUTO_ALLOWED_TOOLS` (sanitized-name test) (`products/agent-platform/.../tools/gateway_tools.py`)

## R-5: Collaboration connector framework with built-in audit sink

- [x] `Connector` protocol + registry, `INCIDENT_CONNECTORS` parsing, unknown-name startup failure (`services/connectors.py` + tests)
- [x] `audit` connector emitting `incident_triaged` to audit-service (`services/audit_emitter.py` + tests)
- [x] dispatch records persisted per incident; failures counted, never failing triage (tests)
- [x] document the connector extension point in the incident-service README

## R-6: Operator portal Incidents experience

- [x] sidebar `Incidents` entry + incidents list view with status/severity filters and auto-refresh (`web-ui/app.js`, `index.html`, `styles.css`)
- [x] incident detail: triage report sections, connector dispatch outcomes, Run triage action with triaging/failed states (raw-text collapsible)
- [x] Report incident form wired through the gateway
- [x] Continue in chat action opening the chat view on `incident-<id>` session

## R-7: Deployment, configuration, and living-state docs

- [x] platform-gateway incidents proxy routes (list/get/report/create/triage) with per-action policy + delegation forwarding (`api/routes/incidents.py`, `services/incident_client.py` + tests)
- [x] platform-gateway settings: `incident_service_url`, `incident_client_id`, `incident_client_secret`, triage proxy timeout (+ settings tests)
- [x] policy bundles: incident rules in `base/shared/policy.yaml` and `shared/shared-contracts/policies/policy-default.yaml` (validate script green)
- [x] incident-service overlay base: deployment, service, runtime-config.env, runtime-secrets.env + example (`dev-k8s/base/incident-service/`)
- [x] postgres: initdb script creating `incidents` database for fresh clusters (`dev-k8s/base/infra/`)
- [x] `sync-incident-secrets.sh`: idempotent `CREATE DATABASE incidents` + secrets writes, `SKIP_INCIDENT_SECRETS` opt-out (`shared/platform-ops/gitops/`)
- [x] wire deploy: `deploy.sh` calls the sync script, `deploy-overlay.sh` handles the incident-service image, kustomization includes the new base
- [x] tool-gateway + platform-gateway runtime-config/secrets fragments for incident wiring
- [x] e2e demo smoke script `shared/platform-ops/e2e/incident-demo.sh` (intake, 401s, query, tool visibility, resolved flip, chat-leg frame pair)
- [x] write the Incident triage tour section in `getting-started.md` (report → triage → ranked steps → continue in chat → audit) as UAT checklist
- [x] update living docs: root README, product READMEs, dev-k8s README, configuration-reference, tool-configuration, architecture-overview, delivery-roadmap status

## R-8: Tests and verification gate

- [x] all new suites green per product (`make test`)
- [x] `make verify` green: all product suites + all overlay renders + policy validation

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] release note written (`docs/agentic-aiops-platform/release-notes/`)
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
