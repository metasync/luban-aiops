# SPEC-015: Incident Triage And Collaboration (Release 3)

## Status

- status: `delivered`
- owner: workspace maintainers
- created: 2026-08-17
- approved: 2026-08-17
- delivered: 2026-08-17
- release slice: `R3` (Incident Triage and Collaboration)
- related ADRs: none yet

## Summary

Deliver Release 3: alerts enter the platform through an Alertmanager webhook
and manual operator reports, are normalized into one canonical incident model,
and receive agent-driven triage — enriched with live evidence and team skills —
that produces a structured report with a severity assessment and ranked next
steps. Triage outcomes are dispatched through a pluggable connector framework
(built-in structured audit sink; collaboration adapters are contract-only) and
surface in a new Incidents experience in the operator portal. All new tool
surface stays strictly read-only; the platform advises, it does not act (action
remains R4).

## Motivation

- R1 and R2 proved the platform useful for grounded status and diagnostic
  questions, but every interaction is operator-initiated chat: the platform
  has no notion of an incident, cannot receive alerts, and cannot carry
  triage context across people or systems. The delivery roadmap
  (`delivery-roadmap.md`, R3) names this as the release that turns the
  platform from a query assistant into an incident-support tool.
- The reference architecture (Flow 3, "Incident Triage") already describes
  the intended shape: alert normalization, evidence enrichment, hypothesis
  formation, runbook retrieval, and a structured incident summary with
  ranked next steps. R3 delivers the first bounded slice of that flow.
- Every guardrail R3 needs is already delivered: deny-by-default policy
  (SPEC-004), the read-only tool framework (SPEC-007), broker-mediated
  delegation (SPEC-008 / ADR-0004), evidence panels (SPEC-011), the durable
  audit trail (SPEC-013), and federated skills (SPEC-014). Triage reuses
  the chat path and its identity/audit machinery rather than opening a new
  trust surface.
- Ranked, cited next steps are the prerequisite for R4: approval-gated
  actions will attach to exactly the triage recommendations this release
  introduces.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Incident and triage-report contract

Incidents and triage reports are governed by shared JSON schemas so intake,
triage capture, connectors, tools, and the portal agree on one shape.

Acceptance criteria:

- new `shared/shared-contracts/schemas/incident.schema.json` defines the
  incident envelope: `incident_id`, `fingerprint` (dedupe key), `source`
  (`alertmanager` | `manual`), `severity` (`critical` | `warning` |
  `info`), `status` (`new` | `triaging` | `triaged` | `triage_failed` |
  `resolved`), `title`, `summary`, `labels` (string map), `reported_by`,
  `session_id` (dedicated triage session), `triage_raw` (raw agent text
  preserved on failed triage), `created_at`, `updated_at`, `resolved_at`
- new `shared/shared-contracts/schemas/triage-report.schema.json` defines
  the report: `incident_id`, `summary`, `severity_assessment`, `evidence`
  (list of provenance references: tool/source + description), `hypotheses`
  (ranked likely causes), `next_steps` (ranked list: `title`, `rationale`,
  `priority`), `skills_cited`, `session_id`, `generated_at`,
  `generated_by`; the attribution fields (`session_id`, `generated_at`,
  `generated_by`) are server-minted at capture time — never taken from
  agent output — so the durable trail cannot be spoofed via incident
  content
- contract tests bind incident-service Pydantic models to the schemas,
  matching the SPEC-013/SPEC-014 contract-test pattern

### R-2: incident-service product with dual intake

A new `products/incident-service` service receives incidents from two
sources — an Alertmanager-compatible webhook and manual operator reports —
normalizes both into the R-1 model, deduplicates by fingerprint, and serves
the incident record set to platform callers.

Acceptance criteria:

- new FastAPI product following the service-family conventions: frozen
  dataclass `INCIDENT_*` settings from environment, structured JSON
  logging, `/health`, `/metrics` (per `observability-conventions.md`),
  per-product Makefile with uv lockfile, containerized on the shared
  base-uv image as a non-root user
- `POST /api/v1/webhooks/alertmanager` accepts Alertmanager v4 webhook
  payloads, authenticates via a shared bearer webhook token
  (`INCIDENT_WEBHOOK_TOKEN`), normalizes the alert group into one incident
  (labels, annotations → title/summary, `severity` label mapping with
  `warning` default), dedupes on the Alertmanager fingerprint (`groupKey`
  when present, else a stable hash of the label set), marks matching
  incidents `resolved` when the payload status is `resolved`, and returns
  the affected incident id
- `POST /api/v1/incidents` creates a manual incident (title, summary,
  severity, labels) authenticated by the platform-caller credential
  registry (static Basic clients via `INCIDENT_QUERY_CLIENTS` or projected
  workload tokens via `INCIDENT_WORKLOAD_*`, SPEC-014 R-3 vocabulary);
  `reported_by` records the caller-supplied operator name
- store backends behind an `IncidentStore` protocol: `InMemoryIncidentStore`
  (dev/tests) and `PostgresIncidentStore` (psycopg v3), selected via
  `INCIDENT_STORE_BACKEND`, following the audit-service/skills-hub
  precedent; incidents and their triage reports live in one store
- query API: `GET /api/v1/incidents` (list with `status`/`severity`/
  `source` filters + capped offset pagination, newest first),
  `GET /api/v1/incidents/{incident_id}` (full record),
  `GET /api/v1/incidents/{incident_id}/report` (triage report, structured
  404 when absent); all query endpoints use the platform-caller credential
  registry; unknown ids return 404, malformed parameters 400
- webhook token missing or mismatched returns 401; unauthenticated query
  requests return 401; no unhandled 500 paths for caller-controlled input

### R-3: Operator-initiated agent triage with structured report capture

Triage runs the existing agent runtime against an incident in a dedicated
session, gathers live evidence and skills through the existing read-only
tools, and captures the outcome as a schema-validated triage report.

Acceptance criteria:

- platform-gateway gains `POST /api/v1/incidents/{incident_id}/triage`:
  resolves the operator's identity, enforces the `incident:triage` action,
  obtains the operator's delegated token exactly as chat does, and forwards
  the request to incident-service with `X-User-ID` (operator name) and the
  delegated bearer — triage always runs under a real operator identity,
  never under a service-owned or synthetic tool authority
- incident-service marks the incident `triaging`, builds a triage prompt
  (incident context + triage discipline + report format) from a service
  template, calls agent-platform `POST /api/v2/chat` with a dedicated
  session (`incident-<incident_id>`) relaying the delegated bearer, and
  parses the agent reply for a fenced `triage-report` JSON block validated
  against the R-1 report schema; because agent-platform sessions are
  single-owner, re-triage by a second operator falls back to a
  per-operator session (`incident-<incident_id>--<operator>`) and the
  incident record tracks the session actually used so "Continue in chat"
  follows it
- on successful validation the report is stored, the incident becomes
  `triaged`, and connectors are dispatched (R-5); on parse/validation or
  agent-call failure the incident becomes `triage_failed` with the raw
  agent text preserved in the record, and no report is dispatched
- `POST /api/v1/incidents/{incident_id}/triage` on incident-service is
  idempotent-safe: re-triage of an already triaged incident stores a new
  report (latest wins) and records both the operator and the session
- the triage prompt instructs the agent to consult `skills.search` for
  matching runbooks and cite them in `skills_cited`, and to ground every
  hypothesis and next step in tool evidence or cited guidance — never to
  fabricate; ranked next steps are advisory (R3 does not execute anything)
- agent-platform gains the triage-report output discipline in
  `DEFAULT_SYSTEM_PROMPT`: when asked to triage an incident, emit exactly
  one fenced `triage-report` JSON block conforming to the schema, after the
  evidence gathering, with no prose inside the block

### R-4: Read-only incident tools in the tool execution framework

The agent can query live incident state through tool-gateway so triage and
chat answers can reference open incidents.

Acceptance criteria:

- new `incidents_connector.py` in tool-gateway registers `incidents.list`
  and `incidents.get` with `risk_level="read"`, `category="incidents"`,
  and parameter schemas matching the R-2 query API
- the connector authenticates to incident-service with a gateway-held
  credential (`GATEWAY_INCIDENTS_CLIENT_ID` /
  `GATEWAY_INCIDENTS_CLIENT_SECRET` ↔ `INCIDENT_QUERY_CLIENTS`), never
  forwarding the user's token
- unsetting `GATEWAY_INCIDENTS_SERVICE_URL` leaves the gateway exactly as
  before this spec (tools simply do not register); a configured but
  unreachable incident-service yields structured `TOOL_EXECUTION_ERROR`
  results; upstream 404 maps to a structured `INCIDENT_NOT_FOUND` error
- invocations flow through the existing choke points unchanged: policy
  (`tools:invoke`), output redaction, `tool_invoked` audit emission, and
  SPEC-011 `tool_call`/`tool_result` stream frames
- both tools join the read-only auto-approval allow-list
  (`DEFAULT_AUTO_ALLOWED_TOOLS`) in agent-platform
- no mutating incident tool is registered in this release — write-back is
  internal service-to-service only (R-3), not an agent tool

### R-5: Collaboration connector framework with built-in audit sink

Triage outcomes reach collaboration surfaces through a pluggable connector
contract; R3 ships the contract plus one built-in sink.

Acceptance criteria:

- incident-service defines a `Connector` protocol: `name` plus
  `dispatch(incident, report)` returning a structured outcome (status +
  optional external reference); connectors are selected via
  `INCIDENT_CONNECTORS` (comma list) and instantiated from a registry;
  unknown names fail startup fast
- the built-in `audit` connector emits a structured `incident_triaged`
  event to audit-service (same ingest-credential pattern as the other
  emitters) carrying the incident envelope, report summary, next-step
  titles, and skills cited; dispatch outcomes are recorded per incident as
  connector-dispatch records (connector, status, reference, timestamp) and
  surfaced through the incident record
- connector failures never fail the triage itself: the report stays stored
  and the incident stays `triaged`; dispatch failure is recorded and
  counted
- the connector contract is documented in `products/incident-service`
  README as the extension point for future collaboration adapters (Slack,
  ticketing); no external adapter ships in this release

### R-6: Operator portal Incidents experience

The portal surfaces the incident workflow: browsing, reporting, triage,
and continuation into chat.

Acceptance criteria:

- new Incidents view: list with status/severity filters, each row showing
  title, severity, status, source, and age; incident detail showing the
  full record plus — when present — the triage report (summary, severity
  assessment, ranked hypotheses and next steps, evidence references, cited
  skills) and connector dispatch outcomes
- a "Report incident" form (title, summary, severity, labels) creating a
  manual incident through the gateway
- a "Run triage" action on the incident detail triggering the gateway
  triage endpoint, with in-progress and failed states rendered from the
  incident status
- a "Continue in chat" action opening the chat view on the incident's
  dedicated session so the triage conversation context carries over
- the portal reaches incident-service exclusively through platform-gateway
  (no direct service calls), using the existing auth/session machinery
- existing dark-theme design tokens and panel conventions are reused; no
  new design system vocabulary

### R-7: Deployment, configuration, and living-state docs

Acceptance criteria:

- dev-k8s overlay deploys incident-service (Deployment, Service,
  runtime-config ConfigMap, runtime-secrets Secret) behind `make deploy`;
  the Postgres instance gains an `incidents` database created idempotently
  (initdb script for fresh clusters, secrets-sync script for existing ones,
  same pattern as the skills DB)
- policy bundle gains the incident action vocabulary: `incident:read`
  (operational roles and read-only-observer), `incident:create` and
  `incident:triage` (operational roles); deny-by-default covers everything
  else; both shared-contracts `policy-default.yaml` and the dev-k8s
  `policy.yaml` stay in sync
- an end-to-end demo smoke script
  (`shared/platform-ops/e2e/incident-demo.sh`) runs after `make deploy` and
  asserts deterministic outcomes only: webhook intake creates an incident
  with the expected fingerprint and severity; bad/missing webhook token is
  rejected (401); the incident is visible through the query API and through
  the `incidents.list` tool; a resolved Alertmanager payload resolves the
  incident — LLM triage prose is left to human validation via the scripted
  "Incident triage tour" in the getting-started guide (UAT checklist)
- living-state docs updated on delivery: root `README.md`,
  `products/incident-service/README.md` (new product doc), tool-gateway
  README, platform-gateway README, operator-portal README, dev-k8s README,
  `docs/guides/configuration-reference.md`,
  `docs/guides/tool-configuration.md`,
  `docs/guides/architecture-overview.md`, `docs/guides/getting-started.md`
- delivery artifacts: CHANGELOG entry, release note, spec index updated to
  `delivered`, roadmap doc reflects R3 delivery

### R-8: Tests and verification gate

Acceptance criteria:

- incident-service unit suite covers: Alertmanager normalization (severity
  mapping, fingerprint derivation, resolved handling, malformed payload
  400), dedupe, manual intake validation, webhook-token auth 401/200
  paths, query auth 401/200 paths, list filtering/pagination bounds,
  triage orchestration (report parse success, malformed JSON fallback →
  `triage_failed` with raw text preserved, agent-call failure fallback),
  connector dispatch (success, failure recorded without failing triage,
  unknown connector startup failure), and the Postgres store against a
  fake driver double
- tool-gateway suite covers the incidents connector: registration gating on
  `GATEWAY_INCIDENTS_SERVICE_URL`, credential handling, upstream error
  mapping (404 → `INCIDENT_NOT_FOUND`, unreachable →
  `TOOL_EXECUTION_ERROR`), and contract tests binding connector payloads to
  the R-1 schemas
- platform-gateway suite covers the incidents proxy routes: policy
  enforcement per action, delegation forwarding on triage, 503 when the
  incident service is unconfigured, upstream error pass-through
- agent-platform suite covers the extended system prompt default and the
  allow-list containing both incident tools
- `make verify` passes: all product suites green and all overlays render

## Non-Goals

- headless/auto triage at ingestion time — triage is operator-initiated so
  it always runs under a real delegated identity; webhook-triggered
  automatic triage needs a service subject-token flow the broker does not
  have today and is a follow-up candidate
- alert correlation and deduplication beyond a single fingerprint (grouping
  related alerts across sources into one incident) — normalization is
  per-alert-group; correlation is a later enrichment layer
- real collaboration adapters (Slack, Jira, PagerDuty) — R3 ships the
  connector contract and the audit sink only
- any mutating operational action, approval workflow, or execution worker —
  next steps are advisory; acting on them is R4 (approval-gated bounded
  actions)
- incident history retrieval for agent grounding (postmortems, past-incident
  similarity search) — candidate for the knowledge layer follow-up
- multi-dialect alert ingestion (PagerDuty, vendor formats) — the
  normalization layer isolates dialects; Alertmanager v4 is the first and
  only one in this release
- per-team incident scoping or RBAC beyond the policy actions — all
  authenticated platform callers see all incidents

## Impact

- products touched: `products/incident-service` (new),
  `products/platform-gateway` (incidents proxy routes + settings + policy
  actions), `products/tool-gateway` (incidents connector + settings),
  `products/agent-platform` (system prompt + allow-list),
  `products/operator-portal` (Incidents view, report form, triage and
  chat-continuation actions)
- contracts touched: new `shared/shared-contracts/schemas/
  incident.schema.json` and `triage-report.schema.json`;
  `shared/shared-contracts/policies/policy-default.yaml` gains the incident
  action rules
- identity / policy / audit / execution safety impact: three new policy
  actions (`incident:read`, `incident:create`, `incident:triage`) under the
  existing deny-by-default engine; triage reuses the chat delegation chain
  (SPEC-008) unchanged — no new token flows; audit coverage for triage
  outcomes via the `audit` connector and the existing policy-decision
  mirror; no execution surface — the platform remains read-only in R3
- living state docs to update on delivery: root `README.md`, product
  READMEs (incident-service, platform-gateway, tool-gateway,
  agent-platform, operator-portal), dev-k8s README,
  `docs/guides/configuration-reference.md`,
  `docs/guides/tool-configuration.md`,
  `docs/guides/architecture-overview.md`,
  `docs/guides/getting-started.md`, `CHANGELOG.md`,
  `docs/agentic-aiops-platform/delivery-roadmap.md`

## Open Questions

None — all resolved (see Changelog).

## Changelog

- 2026-08-17: created as `draft` for the R3 release slice
- 2026-08-17: Q-1 resolved — intake model: Alertmanager webhook ingestion
  plus portal manual reporting, both normalized into one canonical incident
  model (R-2). Webhook-only and manual-only alternatives were rejected:
  the roadmap validation flow requires feeding a real alert, and operators
  must also be able to hand-trigger triage for alerts that never reach the
  webhook.
- 2026-08-17: Q-2 resolved — collaboration scope: a pluggable connector
  contract with a built-in structured audit sink; real Slack/ticketing
  adapters deferred (R-5, Non-Goals), keeping R3 free of external
  collaboration dependencies in dev-k8s.
- 2026-08-17: agreed change to the draft — triage trigger model corrected
  after verifying the delegation chain: the broker exchange always requires
  a user subject token (roles are copied from it; no headless minting path
  exists), so webhook-time background triage cannot carry a delegated tool
  token. Triage is therefore operator-initiated through platform-gateway
  (`POST /api/v1/incidents/{id}/triage`), which resolves identity,
  enforces policy, and forwards the delegated token; incident-service
  orchestrates the agent call. Headless auto-triage moves to Non-Goals as
  a follow-up candidate. R-3 rewritten accordingly. Status → `approved`.
