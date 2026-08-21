---
kind: error_handling
name: Domain-Specific Exceptions, HTTPException Routing, and Structured Tool Error Envelopes
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/platform-gateway/src/platform_gateway/api/routes/incidents.py
    - products/platform-gateway/src/platform_gateway/api/routes/tools.py
    - products/platform-gateway/src/platform_gateway/api/routes/policy.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/app.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/incident-service/src/incident_service/core/config.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - shared/shared-contracts/schemas/tool-result.schema.json
    - shared/shared-contracts/observability-conventions.md
---

## Approach

The platform uses a layered error model that separates **domain exceptions** (raised inside services), **HTTP-level errors** (FastAPI `HTTPException` raised in route handlers), and **structured tool results** (a shared JSON schema for tool invocations). There is no centralized exception-to-HTTP mapper; each service's route layer decides which domain exception becomes which HTTP status code. Errors are never surfaced via `raise Exception` — every failure path raises a named subclass of `Exception` or `ValueError`, and callers catch only the specific types they know about.

## Domain-specific exception classes per service

Each product defines small, purpose-built exception classes near the code that raises them:

| Service | Exception class | Purpose |
|---|---|---|
| `agent-platform` (`providers/base.py`) | `ProviderConfigurationError(ValueError)` | Invalid or missing provider settings |
| `platform-gateway` (`services/policy_engine.py`) | `PolicyLoadError(Exception)` | Policy bundle YAML cannot be loaded or parsed |
| `platform-gateway` (`services/token_verifier.py`) | `TokenVerificationError(Exception)` | JWT verification failure |
| `identity-broker` (`services/exchange_service.py`) | `ExchangeError(Exception)` | Token exchange failure |
| `identity-broker` (`services/token_service.py`) | No custom exception — relies on `jwt` / `cryptography` errors |
| `incident-service` (`services/triage.py`) | `TriageError(Exception)` | Agent turn or report capture failure |
| `incident-service` (`core/config.py`) | `SettingsError(Exception)` | Missing/invalid config |
| `incident-service` (`services/connectors.py`) | `ConnectorConfigError(Exception)` | Connector misconfiguration |
| `incident-service` (`services/incident_store.py`) | `StoreError(Exception)` | Store I/O failure |
| `incident-service` (`services/normalization.py`) | `NormalizationError(Exception)` | Incident normalization failure |
| `incident-service` (`services/query_auth.py`) | `QueryAuthError(Exception)` | Query authorization failure |
| `audit-service` (`services/audit_store.py`) | `StoreError(Exception)` |
| `audit-service` (`services/ingest_auth.py`) | `IngestAuthError(Exception)` |
| `skills-hub` (`core/config.py`) | `SettingsError(Exception)` |
| `skills-hub` (`services/query_auth.py`) | `QueryAuthError(Exception)` |
| `skills-hub` (`services/skill_store.py`) | `StoreError(Exception)` |
| `tool-gateway` (`services/policy_engine.py`) | `PolicyLoadError(Exception)` |
| `tool-gateway` (`services/token_verifier.py`) | `TokenVerificationError(Exception)` |

This pattern means a caller can distinguish configuration problems from runtime failures by catching the specific type rather than a generic `Exception`.

## HTTP boundary: FastAPI routes raise `HTTPException`

All HTTP-facing services use FastAPI's built-in `HTTPException`. Route handlers translate domain errors into appropriate status codes:

- `401 Unauthorized` for missing/malformed auth headers (`platform-gateway/services/gateway_service.py`, `agent-platform/src/agent_service/api/v2/routes.py`).
- `404 Not Found` for unknown sessions or confirmations (`agent-platform/src/agent_service/api/v2/routes.py`).
- `409 Conflict` for duplicate confirmation attempts (`agent-platform/src/agent_service/api/v2/routes.py`).
- `410 Gone` for expired confirmations (`agent-platform/src/agent_service/api/v2/routes.py`).
- `502 Bad Gateway` when downstream services (audit, incidents, tools) are unreachable (`platform-gateway/api/routes/audit.py`, `incidents.py`, `tools.py`).
- `503 Service Unavailable` when policy bundles or dependent services are not configured (`platform-gateway/api/routes/policy.py`, `audit.py`, `tools.py`).
- `400 Bad Request` for malformed input (`platform-gateway/api/routes/incidents.py`).

There is **no global exception handler** registered in any `app.py`; FastAPI's default `HTTPException` serialization is used as-is. The only cross-cutting middleware is an HTTP logging middleware that records `http_request` events with `method`, `path`, `status_code`, and `duration_ms` (see `platform_gateway/app.py`, `agent_platform/app.py`).

## Structured tool error envelope (shared contract)

Tool execution errors do not propagate as Python exceptions across the tool boundary. Instead, `tool-gateway` returns a `ToolResult` dataclass whose shape is enforced by `shared/shared-contracts/schemas/tool-result.schema.json`. The schema defines three allowed `status` values: `success`, `error`, `denied`. Errors carry a structured `error` object with required `code` and `message` fields. Helper functions in `tool-gateway/tools/base.py` provide factory constructors:

- `make_error_result(tool_name, code, message, ...)` — for tool execution failures.
- `make_denied_result(tool_name, reason)` — for policy-denied executions.
- `build_evidence(risk_level, source_system, duration_ms)` — attaches audit provenance (`executed_at`, `duration_ms`, `risk_level`, `source_system`).

Downstream consumers (e.g., agent-platform's gateway tools) treat `status == "denied"` differently from `status == "error"`, so the distinction is part of the protocol, not just a string in a message.

## Downstream error handling patterns

Services that call other services wrap transport-layer failures in their own domain exceptions:

- `incident-service/services/triage.py` wraps `httpx.HTTPError` responses from agent-platform into `TriageError`, then catches both `TriageError` and `httpx.HTTPError` to mark the incident `triage_failed` and persist the raw response text for debugging.
- `platform-gateway/services/audit_emitter.py` raises `RuntimeError` when ingest is rejected with a non-2xx status.
- `platform-gateway/services/policy_engine.py` raises `PolicyLoadError` for invalid YAML, missing files, or malformed rules — these bubble up to the route layer, which converts them to `503`.

## Observability integration with errors

Errors are observable through two channels:

1. **Structured logs**: Every service calls `configure_logging()` at startup (per `shared/shared-contracts/observability-conventions.md`), raising the root logger from uvicorn's WARNING default to INFO so audit records are never silently discarded. Failures emit `log_event(...)` with an event name like `triage_failed`, `http_request`, etc., including `request_id`, `service`, and human-readable details.
2. **Metrics**: RED metrics record `status` labels for HTTP responses; domain counters use bounded enum labels (e.g., `decision ∈ {allow, deny}`, `result ∈ {valid, invalid, expired, missing}`). High-cardinality labels (raw URLs, user IDs, session IDs) are explicitly forbidden.
3. **OpenTelemetry**: OTel push is opt-in (`OTEL_ENABLED`), fails open, and bridges stdout JSON logs to OTLP so errors appear in traces without breaking requests.

## Conventions and constraints

- **No bare `raise Exception`**: All application errors are named subclasses of `Exception` or `ValueError`, enabling precise `except` clauses.
- **Route layer owns HTTP semantics**: Domain logic raises domain exceptions; route handlers convert them to `HTTPException(status_code=...)`. Services do not share a central mapping table.
- **Tool errors are data, not exceptions**: Cross-process tool boundaries return `ToolResult` with `status="error"` or `status="denied"`; exceptions stay within process boundaries.
- **Fail-open observability**: Telemetry setup catches all exceptions during initialization and continues without OTel (`agent_platform/core/telemetry.py`).
- **Request correlation**: `x-request-id` is generated if absent and forwarded on every outbound call; it appears in every log event, making error tracing consistent across services.
- **Deny-by-default policy**: Policy evaluation returns a `PolicyDecision` with `decision="deny"` when no rule matches; this is treated as an error outcome at the tool layer (`make_denied_result`).
- **Audit preservation**: When triage fails, the raw agent reply is preserved in `incident.triage_raw` (truncated to 65536 chars) so operators can debug LLM output even when validation fails.