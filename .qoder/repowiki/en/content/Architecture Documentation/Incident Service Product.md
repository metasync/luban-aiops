# Incident Service Product

<cite>
**Referenced Files in This Document**
- [README.md](file://products/incident-service/README.md)
- [main.py](file://products/incident-service/src/incident_service/main.py)
- [app.py](file://products/incident-service/src/incident_service/app.py)
- [router.py](file://products/incident-service/src/incident_service/api/router.py)
- [incidents.py](file://products/incident-service/src/incident_service/api/routes/incidents.py)
- [webhooks.py](file://products/incident-service/src/incident_service/api/routes/webhooks.py)
- [incident.py](file://products/incident-service/src/incident_service/schemas/incident.py)
- [config.py](file://products/incident-service/src/incident_service/core/config.py)
- [normalization.py](file://products/incident-service/src/incident_service/services/normalization.py)
- [incident_store.py](file://products/incident-service/src/incident_service/services/incident_store.py)
- [triage.py](file://products/incident-service/src/incident_service/services/triage.py)
- [connectors.py](file://products/incident-service/src/incident_service/services/connectors.py)
- [query_auth.py](file://products/incident-service/src/incident_service/services/query_auth.py)
- [incident.schema.json](file://shared/shared-contracts/schemas/incident.schema.json)
- [triage-report.schema.json](file://shared/shared-contracts/schemas/triage-report.schema.json)
</cite>

## Table of Contents
1. Introduction
2. Project Structure
3. Core Components
4. Architecture Overview
5. Detailed Component Analysis
6. Dependency Analysis
7. Performance Considerations
8. Troubleshooting Guide
9. Conclusion

## Introduction
The Incident Service turns alert noise and operator reports into tracked incidents, runs agent-driven triage on them, and dispatches outcomes through a pluggable connector framework. It supports dual intake (Alertmanager webhook and manual report), fingerprint-based deduplication, operator-initiated triage via the Agent Platform, and a query API for portal and tool integrations. The service is designed to be read-only from the tooling perspective and does not execute operational actions; next steps are advisory.

Key responsibilities:
- Normalize and ingest alerts and manual reports into a canonical incident model
- Deduplicate by fingerprint and manage lifecycle status transitions
- Run a single agent turn per incident to produce a validated triage report
- Dispatch validated reports to configured connectors (audit sink built-in)
- Expose secure query endpoints behind platform-caller authentication

**Section sources**
- [README.md:3-14](file://products/incident-service/README.md#L3-L14)
- [README.md:21-41](file://products/incident-service/README.md#L21-L41)

## Project Structure
The product follows a layered FastAPI application with clear separation between entrypoints, routing, services, schemas, and configuration.

```mermaid
graph TB
A["main.py<br/>process entrypoint"] --> B["app.py<br/>FastAPI lifespan & middleware"]
B --> C["api/router.py<br/>route aggregation"]
C --> D["api/routes/webhooks.py<br/>Alertmanager intake"]
C --> E["api/routes/incidents.py<br/>manual intake, query, triage"]
E --> F["services/normalization.py<br/>alert normalization"]
E --> G["services/triage.py<br/>agent triage orchestration"]
E --> H["services/incident_store.py<br/>store abstraction"]
E --> I["services/connectors.py<br/>connector dispatch"]
E --> J["services/query_auth.py<br/>caller auth"]
B --> K["core/config.py<br/>IncidentSettings"]
E --> L["schemas/incident.py<br/>models bound to shared contracts"]
```

**Diagram sources**
- [main.py:1-9](file://products/incident-service/src/incident_service/main.py#L1-L9)
- [app.py:20-69](file://products/incident-service/src/incident_service/app.py#L20-L69)
- [router.py:1-9](file://products/incident-service/src/incident_service/api/router.py#L1-L9)
- [webhooks.py:69-102](file://products/incident-service/src/incident_service/api/routes/webhooks.py#L69-L102)
- [incidents.py:74-283](file://products/incident-service/src/incident_service/api/routes/incidents.py#L74-L283)
- [normalization.py:68-109](file://products/incident-service/src/incident_service/services/normalization.py#L68-L109)
- [triage.py:186-363](file://products/incident-service/src/incident_service/services/triage.py#L186-L363)
- [incident_store.py:30-66](file://products/incident-service/src/incident_service/services/incident_store.py#L30-L66)
- [connectors.py:73-127](file://products/incident-service/src/incident_service/services/connectors.py#L73-L127)
- [query_auth.py:104-117](file://products/incident-service/src/incident_service/services/query_auth.py#L104-L117)
- [config.py:72-126](file://products/incident-service/src/incident_service/core/config.py#L72-L126)
- [incident.py:37-116](file://products/incident-service/src/incident_service/schemas/incident.py#L37-L116)

**Section sources**
- [main.py:1-9](file://products/incident-service/src/incident_service/main.py#L1-L9)
- [app.py:20-69](file://products/incident-service/src/incident_service/app.py#L20-L69)
- [router.py:1-9](file://products/incident-service/src/incident_service/api/router.py#L1-L9)

## Core Components
- Application lifecycle and middleware: initializes store and connectors, logs requests, sets up metrics and telemetry.
- Routing: aggregates health, webhooks, and incidents routes under /api/v1.
- Intake:
  - Alertmanager webhook: authenticates via bearer token, normalizes payload, creates or updates incidents by fingerprint, resolves open incidents.
  - Manual report: authenticated via platform-caller credentials, creates new incidents with unique fingerprints.
- Triage: orchestrates a single agent turn in a dedicated session, validates output against the triage report schema, persists report and updates incident status.
- Storage: abstracted via IncidentStore protocol with in-memory and PostgreSQL backends; stores incidents, reports, and connector dispatch records.
- Connectors: pluggable dispatchers that push validated reports to collaboration surfaces; failures are recorded but do not fail triage.
- Authentication: supports static Basic credentials and projected workload tokens for query endpoints.

**Section sources**
- [app.py:20-69](file://products/incident-service/src/incident_service/app.py#L20-L69)
- [webhooks.py:69-206](file://products/incident-service/src/incident_service/api/routes/webhooks.py#L69-L206)
- [incidents.py:74-283](file://products/incident-service/src/incident_service/api/routes/incidents.py#L74-L283)
- [triage.py:186-363](file://products/incident-service/src/incident_service/services/triage.py#L186-L363)
- [incident_store.py:30-66](file://products/incident-service/src/incident_service/services/incident_store.py#L30-L66)
- [connectors.py:73-127](file://products/incident-service/src/incident_service/services/connectors.py#L73-L127)
- [query_auth.py:104-117](file://products/incident-service/src/incident_service/services/query_auth.py#L104-L117)

## Architecture Overview
High-level flow across components for intake, triage, and query.

```mermaid
sequenceDiagram
participant AM as "Alertmanager"
participant GW as "Platform Gateway"
participant IS as "Incident Service"
participant ST as "Incident Store"
participant AG as "Agent Platform"
participant CN as "Connectors"
Note over AM,IS : Webhook intake
AM->>IS : POST /api/v1/webhooks/alertmanager
IS->>ST : get_open_by_fingerprint()
alt Open incident exists
IS->>ST : save(updated incident)
else No open incident
IS->>ST : create(new incident)
end
IS-->>AM : {action, incident_id}
Note over GW,IS : Manual intake
GW->>IS : POST /api/v1/incidents (Basic/Bearer)
IS->>ST : create(new incident)
IS-->>GW : {incident envelope}
Note over GW,AG : Operator triage
GW->>IS : POST /api/v1/incidents/{id}/triage (X-User-ID, X-Delegated-Token)
IS->>AG : POST /api/v2/chat (response_schema)
AG-->>IS : content + structured_output
IS->>ST : set_report(), save(triaged)
IS->>CN : dispatch_report()
CN-->>IS : ConnectorOutcome
IS-->>GW : {incident, report, dispatches}
Note over GW,IS : Query
GW->>IS : GET /api/v1/incidents[...] (Basic/Bearer)
IS->>ST : list/get/report/dispatches
IS-->>GW : JSON response
```

**Diagram sources**
- [webhooks.py:69-206](file://products/incident-service/src/incident_service/api/routes/webhooks.py#L69-L206)
- [incidents.py:74-283](file://products/incident-service/src/incident_service/api/routes/incidents.py#L74-L283)
- [triage.py:186-363](file://products/incident-service/src/incident_service/services/triage.py#L186-L363)
- [incident_store.py:30-66](file://products/incident-service/src/incident_service/services/incident_store.py#L30-L66)
- [connectors.py:87-127](file://products/incident-service/src/incident_service/services/connectors.py#L87-L127)

## Detailed Component Analysis

### Webhook Intake (Alertmanager)
- Authenticates using a shared bearer token; fails closed when unconfigured.
- Normalizes Alertmanager v4 payloads into a canonical input with stable fingerprinting.
- Creates new incidents for unknown fingerprints; updates existing open incidents for firing events; resolves open incidents for resolved events.

```mermaid
flowchart TD
Start(["POST /api/v1/webhooks/alertmanager"]) --> Auth{"Webhook token valid?"}
Auth --> |No| Reject["401 UNAUTHORIZED"]
Auth --> |Yes| Parse["Parse JSON payload"]
Parse --> Valid{"Valid JSON?"}
Valid --> |No| Malformed["400 INVALID_PAYLOAD"]
Valid --> |Yes| Normalize["normalize_alertmanager()"]
Normalize --> CheckOpen{"Open incident by fingerprint?"}
CheckOpen --> |Yes| Update["Update severity/title/summary/labels"]
CheckOpen --> |No| Create["Create new incident (NEW)"]
Update --> Done(["Return updated action"])
Create --> Done
CheckOpen --> Resolved{"Payload resolved?"}
Resolved --> |Yes| Resolve["Mark RESOLVED with timestamp"]
Resolve --> Done
Resolved --> |No| Done
```

**Diagram sources**
- [webhooks.py:69-206](file://products/incident-service/src/incident_service/api/routes/webhooks.py#L69-L206)
- [normalization.py:68-109](file://products/incident-service/src/incident_service/services/normalization.py#L68-L109)

**Section sources**
- [webhooks.py:69-206](file://products/incident-service/src/incident_service/api/routes/webhooks.py#L69-L206)
- [normalization.py:68-109](file://products/incident-service/src/incident_service/services/normalization.py#L68-L109)

### Manual Intake and Query API
- Manual creation requires platform-caller authentication (Basic or workload token).
- Enforces label limits and length constraints during validation.
- Query endpoints support filtering by status, severity, source with capped pagination.

```mermaid
sequenceDiagram
participant Client as "Caller (Basic/Bearer)"
participant Inc as "incidents.py"
participant Store as "IncidentStore"
Client->>Inc : POST /api/v1/incidents
Inc->>Inc : validate payload & labels
Inc->>Store : create(Incident)
Store-->>Inc : saved incident
Inc-->>Client : 201 {incident envelope}
Client->>Inc : GET /api/v1/incidents?status&severity&source&offset&limit
Inc->>Store : list(offset, limit, filters)
Store-->>Inc : [incidents], total
Inc-->>Client : {incidents, total, offset, limit}
```

**Diagram sources**
- [incidents.py:74-176](file://products/incident-service/src/incident_service/api/routes/incidents.py#L74-L176)
- [incident_store.py:43-50](file://products/incident-service/src/incident_service/services/incident_store.py#L43-L50)

**Section sources**
- [incidents.py:74-176](file://products/incident-service/src/incident_service/api/routes/incidents.py#L74-L176)

### Triage Orchestration
- Establishes a dedicated agent session per incident, with per-operator fallback to handle re-triage by different operators.
- Calls Agent Platform chat endpoint with a structured output schema; prefers kernel-validated structured output, falls back to fenced block parsing.
- Forces server-minted attribution fields to prevent spoofing; validates against the triage report schema.
- Persists report and updates incident status; records metrics and observability events.

```mermaid
sequenceDiagram
participant Caller as "Platform Gateway"
participant Inc as "incidents.py"
participant Tri as "triage.py"
participant AG as "Agent Platform"
participant Store as "IncidentStore"
Caller->>Inc : POST /api/v1/incidents/{id}/triage
Inc->>Inc : authenticate_caller()
Inc->>Tri : run_triage(settings, store, incident, operator, token, request_id)
Tri->>AG : POST /api/v2/sessions (create incident-<id>)
AG-->>Tri : session created or 404 (fallback per operator)
Tri->>AG : POST /api/v2/chat (message, response_schema)
AG-->>Tri : content + structured_output
Tri->>Store : set_report(), save(triaged)
Tri-->>Inc : (incident, report)
Inc->>Inc : dispatch_report(store, connectors, incident, report)
Inc-->>Caller : {incident, report, dispatches}
```

**Diagram sources**
- [incidents.py:235-283](file://products/incident-service/src/incident_service/api/routes/incidents.py#L235-L283)
- [triage.py:186-363](file://products/incident-service/src/incident_service/services/triage.py#L186-L363)

**Section sources**
- [triage.py:186-363](file://products/incident-service/src/incident_service/services/triage.py#L186-L363)
- [incidents.py:235-283](file://products/incident-service/src/incident_service/api/routes/incidents.py#L235-L283)

### Data Models and Contracts
- Incident and TriageReport models enforce field constraints and mirror shared contract schemas.
- IncidentStatus enumerates lifecycle states; IncidentSource distinguishes intake channels.
- ConnectorDispatch captures per-connector outcomes for auditability.

```mermaid
classDiagram
class Incident {
+string incident_id
+string fingerprint
+IncidentSource source
+IncidentSeverity severity
+IncidentStatus status
+string title
+string summary
+dict labels
+string reported_by
+string session_id
+string triage_raw
+datetime created_at
+datetime updated_at
+datetime resolved_at
+envelope() dict
+list_entry() dict
}
class TriageReport {
+string incident_id
+string summary
+IncidentSeverity severity_assessment
+EvidenceRef[] evidence
+string[] hypotheses
+NextStep[] next_steps
+string[] skills_cited
+string session_id
+datetime generated_at
+string generated_by
+envelope() dict
}
class EvidenceRef {
+string source
+string description
}
class NextStep {
+string title
+string rationale
+string priority
}
class ConnectorDispatch {
+string connector
+string status
+string reference
+string error
+datetime created_at
}
TriageReport --> EvidenceRef : "contains"
TriageReport --> NextStep : "contains"
```

**Diagram sources**
- [incident.py:37-116](file://products/incident-service/src/incident_service/schemas/incident.py#L37-L116)

**Section sources**
- [incident.py:37-116](file://products/incident-service/src/incident_service/schemas/incident.py#L37-L116)
- [incident.schema.json:1-95](file://shared/shared-contracts/schemas/incident.schema.json#L1-L95)
- [triage-report.schema.json:1-120](file://shared/shared-contracts/schemas/triage-report.schema.json#L1-L120)

### Storage Strategy
- IncidentStore protocol defines CRUD operations for incidents, reports, and dispatch records.
- InMemoryIncidentStore for development/testing; PostgresIncidentStore for production with durable tables and indexes.
- Factory selects backend based on settings; ensures required DB URL when using Postgres.

```mermaid
flowchart TD
Build["build_incident_store(settings)"] --> Backend{"settings.store_backend"}
Backend --> |memory| Mem["InMemoryIncidentStore"]
Backend --> |postgres| Pg["PostgresIncidentStore(db_url)"]
Mem --> Init["initialize() -> no-op"]
Pg --> InitDDL["CREATE TABLES if not exists"]
Init --> Ready["ready() -> True"]
InitDDL --> Ready
```

**Diagram sources**
- [incident_store.py:508-517](file://products/incident-service/src/incident_service/services/incident_store.py#L508-L517)
- [incident_store.py:72-154](file://products/incident-service/src/incident_service/services/incident_store.py#L72-L154)
- [incident_store.py:280-313](file://products/incident-service/src/incident_service/services/incident_store.py#L280-L313)

**Section sources**
- [incident_store.py:30-66](file://products/incident-service/src/incident_service/services/incident_store.py#L30-L66)
- [incident_store.py:508-517](file://products/incident-service/src/incident_service/services/incident_store.py#L508-L517)

### Connectors Framework
- Pluggable connector protocol with name and async dispatch method.
- Registry maps connector names to factories; startup validates configured names.
- Dispatch failures are isolated, recorded, and counted without failing triage.

```mermaid
sequenceDiagram
participant Inc as "incidents.py"
participant Conn as "connectors.py"
participant Audit as "AuditConnector"
participant Store as "IncidentStore"
Inc->>Conn : dispatch_report(store, connectors, incident, report)
loop For each connector
Conn->>Audit : dispatch(incident, report)
Audit-->>Conn : ConnectorOutcome
Conn->>Store : add_dispatch(incident_id, ConnectorDispatch)
end
Conn-->>Inc : [dispatches]
```

**Diagram sources**
- [connectors.py:73-127](file://products/incident-service/src/incident_service/services/connectors.py#L73-L127)

**Section sources**
- [connectors.py:73-127](file://products/incident-service/src/incident_service/services/connectors.py#L73-L127)

### Authentication
- Query endpoints authenticate callers via:
  - Static Basic credentials against INCIDENT_QUERY_CLIENTS registry
  - Workload tokens validated against cluster OIDC issuer JWKS with audience and subject mapping
- Webhook endpoint uses HMAC-safe comparison of bearer token.

```mermaid
flowchart TD
Req["Incoming Request"] --> Header{"Authorization header"}
Header --> |Bearer| Workload["authenticate_workload()"]
Header --> |Basic| Static["authenticate_static()"]
Workload --> OK{"Valid workload token?"}
Static --> OK
OK --> |Yes| Allow["Proceed"]
OK --> |No| Deny["401 UNAUTHORIZED"]
```

**Diagram sources**
- [query_auth.py:33-43](file://products/incident-service/src/incident_service/services/query_auth.py#L33-L43)
- [query_auth.py:68-93](file://products/incident-service/src/incident_service/services/query_auth.py#L68-L93)
- [query_auth.py:104-117](file://products/incident-service/src/incident_service/services/query_auth.py#L104-L117)
- [webhooks.py:57-82](file://products/incident-service/src/incident_service/api/routes/webhooks.py#L57-L82)

**Section sources**
- [query_auth.py:33-43](file://products/incident-service/src/incident_service/services/query_auth.py#L33-L43)
- [query_auth.py:68-93](file://products/incident-service/src/incident_service/services/query_auth.py#L68-L93)
- [query_auth.py:104-117](file://products/incident-service/src/incident_service/services/query_auth.py#L104-L117)
- [webhooks.py:57-82](file://products/incident-service/src/incident_service/api/routes/webhooks.py#L57-L82)

## Dependency Analysis
Component coupling and external integration points:

```mermaid
graph LR
A["incidents.py"] --> B["triage.py"]
A --> C["incident_store.py"]
A --> D["connectors.py"]
A --> E["query_auth.py"]
D --> F["audit_emitter (built-in)"]
B --> G["Agent Platform (/api/v2/chat, /api/v2/sessions)"]
A --> H["normalization.py"]
C --> I["PostgreSQL (psycopg)"]
```

**Diagram sources**
- [incidents.py:74-283](file://products/incident-service/src/incident_service/api/routes/incidents.py#L74-L283)
- [triage.py:186-363](file://products/incident-service/src/incident_service/services/triage.py#L186-L363)
- [incident_store.py:280-313](file://products/incident-service/src/incident_service/services/incident_store.py#L280-L313)
- [connectors.py:73-127](file://products/incident-service/src/incident_service/services/connectors.py#L73-L127)
- [normalization.py:68-109](file://products/incident-service/src/incident_service/services/normalization.py#L68-L109)

**Section sources**
- [incidents.py:74-283](file://products/incident-service/src/incident_service/api/routes/incidents.py#L74-L283)
- [triage.py:186-363](file://products/incident-service/src/incident_service/services/triage.py#L186-L363)
- [incident_store.py:280-313](file://products/incident-service/src/incident_service/services/incident_store.py#L280-L313)
- [connectors.py:73-127](file://products/incident-service/src/incident_service/services/connectors.py#L73-L127)
- [normalization.py:68-109](file://products/incident-service/src/incident_service/services/normalization.py#L68-L109)

## Performance Considerations
- Low-volume incident traffic justifies per-operation database connections in PostgresIncidentStore.
- List queries use indexed ordering and pagination to avoid full scans.
- Triage timeout is configurable to balance responsiveness with agent processing time.
- Connector dispatch failures are isolated to prevent cascading latency or failures.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and diagnostics:
- Webhook disabled: If INCIDENT_WEBHOOK_TOKEN is empty, the service returns 503 for webhook calls.
- Invalid webhook token: Returns 401 UNAUTHORIZED; verify shared secret matches Alertmanager configuration.
- Malformed webhook payload: Returns 400 INVALID_PAYLOAD; ensure Alertmanager sends valid JSON with status and labels.
- Unknown connector name: Startup fails fast with ConnectorConfigError; verify INCIDENT_CONNECTORS entries match registered names.
- Triage failure: Incident status becomes triage_failed with raw agent text preserved; inspect triage_raw and logs for reasons.
- Query auth errors: Ensure Authorization header contains either Basic credentials from INCIDENT_QUERY_CLIENTS or a valid workload token.

Operational checks:
- Health endpoints: /health/live and /health/ready indicate service readiness.
- Metrics: Observe intake counters, triage success/failure counts, and connector dispatch totals.
- Logs: Look for incident_created, incident_updated, incident_resolved, triage_started, triage_completed, triage_failed, and connector_dispatched events.

**Section sources**
- [webhooks.py:73-93](file://products/incident-service/src/incident_service/api/routes/webhooks.py#L73-L93)
- [connectors.py:73-84](file://products/incident-service/src/incident_service/services/connectors.py#L73-L84)
- [triage.py:271-363](file://products/incident-service/src/incident_service/services/triage.py#L271-L363)
- [README.md:43-61](file://products/incident-service/README.md#L43-L61)

## Conclusion
The Incident Service provides a robust, extensible foundation for incident management within the Luban AIOps platform. It standardizes intake, enforces data contracts, orchestrates agent-driven triage safely, and exposes secure APIs for integration. Its modular design allows easy extension of connectors and storage backends while maintaining strong observability and reliability guarantees.

[No sources needed since this section summarizes without analyzing specific files]