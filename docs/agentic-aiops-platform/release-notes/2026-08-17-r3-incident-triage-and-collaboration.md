# Release Notes: 2026-08-17 — R3 Incident Triage and Collaboration (SPEC-015)

## Summary

SPEC-015 delivers Release 3: the platform turns from a query assistant into
an incident-support tool. Alerts enter through an Alertmanager webhook and
manual operator reports, both normalized into one canonical incident model in
the new `incident-service` product. Operators initiate agent triage from the
portal; the agent gathers live evidence with the existing read-only tools and
team skills, and its findings are captured as a schema-validated triage
report with a severity assessment, evidence, hypotheses, and ranked advisory
next steps. Reports dispatch through a pluggable connector framework whose
first sink puts `incident_triaged` events on the durable audit trail. A new
Incidents panel in the operator portal carries the whole workflow, including
"Continue in chat" on the incident's dedicated session.

Two guardrails hold: tool-gateway stays strictly read-only (SPEC-007
invariant — there is no mutating incident tool, and triage next steps are
advisory only; execution remains R4), and the triage report is captured from
the agent as validated fenced JSON rather than through any write tool. Triage
always runs under the operator's real identity via the existing delegation
chain (SPEC-008) — no new token flows.

`make verify` is green: all product tests (agent-platform 130,
audit-service 70, identity-broker 60, incident-service 116,
platform-gateway 113, skills-hub 118, tool-gateway 174 — 781 total), all
four Kustomize overlays render cleanly, and the policy validation target
confirms the eight-rule deny-by-default bundle.

## Change Set 1: Incident and triage-report contracts (R-1)

### Highlights

- `shared/shared-contracts/schemas/incident.schema.json`: canonical incident
  envelope (`incident_id`, `fingerprint`, `source` `alertmanager|manual`,
  `severity`, `status` `new|triaging|triaged|triage_failed|resolved`,
  `title`, `summary`, `labels`, `reported_by`, `session_id`, timestamps)
- `shared/shared-contracts/schemas/triage-report.schema.json`: the triage
  output contract (`summary`, `severity_assessment`, `evidence` list,
  `hypotheses`, ranked `next_steps` with priority, `skills_cited`,
  `session_id`, attribution)
- Contract tests bind the incident-service Pydantic models to both schemas,
  following the audit-event and skill contract patterns

### Why It Matters

- one intake model means Alertmanager groups and manual reports are
  interchangeable downstream — triage, connectors, portal, and tools all see
  the same shape
- the report schema is what makes "agent said X" machine-checkable and
  safe to dispatch to collaboration surfaces

## Change Set 2: incident-service product with dual intake (R-2)

### Highlights

- New `products/incident-service` product: FastAPI on the shared `base-uv`
  image, mirroring the audit-service/skills-hub chassis — frozen-dataclass
  `INCIDENT_*` settings, structured JSON logging, `/health` + `/health/ready`,
  always-on `/metrics`, wired into the root Makefile
- Alertmanager v4 webhook (`POST /api/v1/webhooks/alertmanager`): shared
  bearer token (`INCIDENT_WEBHOOK_TOKEN`), fail-closed 503 when the token is
  unconfigured, one alert group per incident, `groupKey` (or stable label
  hash) fingerprint dedupe — firing re-fires update the open incident,
  `resolved` closes it, unknown-fingerprint resolutions are idempotent no-ops
- Manual intake (`POST /api/v1/incidents`) for the portal report form, with
  `reported_by` captured from the relayed operator identity
- `IncidentStore` protocol with two backends selected by
  `INCIDENT_STORE_BACKEND`: `InMemoryIncidentStore` for tests/dev and
  `PostgresIncidentStore` (psycopg v3, `incidents` / `triage_reports` /
  `connector_dispatches` tables) with behavior parity tests
- Query auth: a dedicated static Basic registry `INCIDENT_QUERY_CLIENTS`
  plus projected workload tokens (`INCIDENT_WORKLOAD_*`) — the SPEC-014
  vocabulary, not the shared ingest/query pattern

### Why It Matters

- the normalization layer isolates alert dialects: future webhook formats
  get their own normalizer feeding the same intake path
- fail-closed webhook auth means an unconfigured deployment cannot silently
  accept alert traffic

## Change Set 3: Operator-initiated agent triage (R-3)

### Highlights

- `POST /api/v1/incidents/{id}/triage` flips the incident to `triaging` and
  runs one agent-platform `/api/v2/chat` turn in the dedicated
  `incident-<id>` session, relaying the operator's delegated bearer
- The triage prompt template instructs the agent to gather evidence with the
  existing `k8s.*` / `elastic.*` / `skills.*` tools and end with a fenced
  `triage-report` JSON block; the reply is extracted and Pydantic-validated
- Success stores the report and dispatches connectors (`triaged`); any parse
  or validation failure lands in `triage_failed` with the raw agent text
  preserved for inspection. Re-triage is latest-wins, counted by
  `incident_triages_total{result}`
- `DEFAULT_SYSTEM_PROMPT` gains the triage-report discipline so the agent
  emits the exact fenced block format when asked to triage

### Why It Matters

- triage is operator-initiated and identity-carrying: the run is attributable
  to the person who asked for it, on the durable trail
- capturing the report as validated fenced JSON keeps the write surface out
  of the tool framework entirely

## Change Set 4: Read-only incident tools (R-4)

### Highlights

- `IncidentsConnector` in tool-gateway registers `incidents.list` and
  `incidents.get` with parameter schemas; Basic-auth httpx transport, 10s
  timeout, structured error mapping (404 → `INCIDENT_NOT_FOUND`, unreachable
  → `TOOL_EXECUTION_ERROR`)
- Registration in `_build_tool_registry()` is gated on
  `GATEWAY_INCIDENTS_SERVICE_URL`; unset preserves the prior tool surface
  byte-for-byte (gating test)
- `incidents.list` / `incidents.get` join `DEFAULT_AUTO_ALLOWED_TOOLS` in
  agent-platform, so chat can reference live incidents without overlay changes

### Why It Matters

- the tools inherit policy, audit, redaction, and evidence-panel behavior
  from the SPEC-007 choke point — no new trust surface, and no mutating
  incident tool exists
- the agent can ground triage in the incident record itself ("what else is
  open right now?")

## Change Set 5: Connector framework with built-in audit sink (R-5)

### Highlights

- `Connector` protocol (`name`, `async dispatch(incident, report) ->
  ConnectorOutcome`) with a config-driven registry: `INCIDENT_CONNECTORS`
  selects active connectors, unknown names fail startup fast
- Built-in `audit` connector emits structured `incident_triaged` events to
  audit-service using the service's ingest credential
- Dispatch records persist per incident and surface in the detail/report
  responses; failures are counted
  (`incident_connector_dispatches_total{connector,result}`) but never fail
  the triage path
- The extension contract (Slack/Jira adapters) is documented in the
  incident-service README — contract-only in R3

### Why It Matters

- triage outcomes land on the same durable, `audit:read`-gated trail as
  every other platform decision
- collaboration adapters can arrive later without touching the triage path

## Change Set 6: Portal Incidents experience and gateway proxy (R-6/R-7)

### Highlights

- platform-gateway gains the incidents proxy surface (list, get, report,
  create, triage) with per-action policy (`incident:read`, `incident:create`,
  `incident:triage`) and identity relay: queries use its service credential,
  triage additionally forwards `X-User-ID` and the operator's delegated
  bearer; an unset upstream fails closed (503) and triage without a working
  delegation chain fails closed too
- Policy bundle grows from five to eight allow rules: `incident:read` also
  covers `read-only-observer` (a viewing surface), while create/triage stay
  with the operational and developer roles
- Operator portal gains the Incidents panel: filterable list with
  auto-refresh, incident detail with the full triage report (severity
  assessment, evidence, hypotheses, ranked advisory next steps, cited
  skills), connector dispatch outcomes, Run triage with live
  triaging/failed states (failed runs expose the raw agent text), the
  Report incident form, and Continue in chat on the `incident-<id>` session;
  the audit view gains the `incident_triaged` event type
- dev-k8s overlay: incident-service deployment/service, postgres `incidents`
  database (initdb ConfigMap for fresh clusters), gateway `*_INCIDENT*`
  config fragments, and `sync-incident-secrets.sh` (idempotent
  `CREATE DATABASE incidents`, webhook token, shared query secret across the
  three K8s secrets) wired into `make deploy` with a
  `SKIP_INCIDENT_SECRETS` opt-out; `sync-audit-secrets.sh` registers
  incident-service as a fourth audit emitter
- `shared/platform-ops/e2e/incident-demo.sh`: deterministic smoke test —
  webhook 401 control checks, intake → dedupe → resolve, query visibility,
  operator triage through the gateway yielding a validated report, and the
  `incident_triaged` event on the durable trail

### Why It Matters

- the whole R3 loop — alert in, triage out, trail recorded — is one portal
  workflow, and one script proves it end to end
- `make deploy` brings up the incident slice with no manual steps

## Post-Delivery Refinements

Live acceptance (`make deploy` + `incident-demo.sh`) and a code/doc review
landed a few follow-ups on top of the delivered slice:

- Named-session support in agent-platform (`POST /api/v2/sessions` accepts an
  optional caller-supplied `session_id`, idempotent for the owning user):
  agent-platform rejects unknown session ids on `/chat`, so incident-service
  now establishes the dedicated `incident-<id>` session before the triage
  turn
- Multi-operator re-triage: agent sessions are single-owner, so a second
  operator's triage falls back to `incident-<id>--<operator>`; the incident
  tracks the session actually used so Continue in chat follows it
- Report attribution (`incident_id` / `session_id` / `generated_at` /
  `generated_by`) is server-minted at capture time — agent output can no
  longer set it, closing a prompt-injection route to audit-trail spoofing
- Webhook token comparison encodes to bytes so non-ASCII bearer values
  answer 401 instead of an unhandled 500
- `incident-demo.sh` fixes found by running it: the `groupKey` payload
  quoting produced invalid JSON, and the query/audit credential parsing was
  order-dependent on the client registries (now parsed entry-wise)
- Operator documentation: new Incident Triage and Collaboration Guide
  (`docs/guides/incident-guide.md`) covering Alertmanager wiring, lifecycle
  and dedupe semantics, the portal workflow, triage interpretation, and
  re-triage collaboration; troubleshooting gains three incident symptoms
  (webhook 401/503, stuck/failed triage, missing incidents connector)

## Known Limitations

- collaboration connectors are contract-only: Slack/Jira adapters implement
  the documented `Connector` protocol in a future release
- triage is a single agent turn with a bounded timeout; long investigations
  stay in chat via Continue in chat
- the Alertmanager webhook uses a shared bearer token (per-source tokens are
  a hardening candidate); webhook delivery itself is not retried by the
  platform — Alertmanager's own retry policy covers it
- next steps are advisory by design; acting on them is R4 (approval-gated
  bounded actions)

## Related Documents

- `../../specs/SPEC-015-incident-triage-and-collaboration/spec.md`
- `../../specs/SPEC-015-incident-triage-and-collaboration/plan.md`
- `../../specs/README.md` (spec index, SPEC-015 delivered)
- `../../../CHANGELOG.md`
