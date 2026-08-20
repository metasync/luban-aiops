---
kind: error_handling
name: FastAPI-Based Error Handling with Domain-Specific Exceptions and Structured JSON Responses
category: error_handling
scope:
    - '**'
source_files:
    - products/incident-service/src/incident_service/api/routes/incidents.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/incident-service/src/incident_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/audit-service/src/audit_service/app.py
    - products/skills-hub/src/skills_hub/app.py
    - products/identity-broker/src/identity_service/app.py
---

## Overview

The Incident Service repository is a multi-service Python platform built on FastAPI. Each service follows the same architectural pattern for error handling: domain-specific exception classes are raised in services, caught at route boundaries, and converted into structured JSON error responses with consistent `code`/`message` fields. There is no centralized global exception handler — each service's routes handle errors locally.

## Framework and Conventions

- **FastAPI** is the HTTP framework across all services (`agent-platform`, `audit-service`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`).
- **Pydantic v2** models enforce request/response schemas; `pydantic.ValidationError` is caught explicitly to return `400 INVALID_PAYLOAD`.
- **No global exception middleware**: Services do not register FastAPI `exception_handler` decorators. Errors are handled inline in route functions via try/except blocks.
- **Structured JSON error envelope**: A local helper `_error(status_code, code, message)` returns `JSONResponse` with `{"error": {"code": ..., "message": ...}}`. This pattern is used consistently in `incident_service/api/routes/incidents.py`.
- **HTTPException** from FastAPI is used sparingly (e.g., `agent_platform/src/agent_service/api/v2/routes.py` raises `HTTPException(401, detail=...)` for missing headers).

## Domain-Specific Exception Classes

Each service defines small, purpose-built exception classes near the logic that raises them:

| Service | Exception Class | Purpose |
|---|---|---|
| `incident-service` | `QueryAuthError` | Authentication failures (maps to 401) |
| `incident-service` | `StoreError` | Store backend failures |
| `incident-service` | `ConnectorConfigError` | Invalid connector configuration |
| `incident-service` | `NormalizationError` | Alert normalization failures |
| `incident-service` | `TriageError` | Triage execution failures |
| `incident-service` | `SettingsError` | Configuration validation failures |
| `platform-gateway` | `PolicyLoadError` | Policy bundle YAML parse/load failures |
| `platform-gateway` | `TokenVerificationError` | Token verification failures |
| `tool-gateway` | `PolicyLoadError` | Tool gateway policy loading failures |
| `tool-gateway` | `TokenVerificationError` | Token verification failures |
| `audit-service` | `StoreError` | Audit store failures |
| `audit-service` | `IngestAuthError` | Ingestion auth failures |
| `skills-hub` | `StoreError` | Skill store failures |
| `skills-hub` | `QueryAuthError` | Query authentication failures |
| `agent-platform` | `ProviderConfigurationError(ValueError)` | Provider config validation failures |
| `identity-broker` | `ExchangeError` | Token exchange failures |

These exceptions are raised deep in service layers and caught at route boundaries where they map to appropriate HTTP status codes.

## Route-Level Error Handling Pattern

Routes follow a consistent pattern in `incident_service/api/routes/incidents.py`:

1. **Authentication**: Wrap `authenticate_caller()` in try/except `QueryAuthError` → return `_error(401, "UNAUTHORIZED", ...)`.
2. **Request parsing**: Catch generic `Exception` when reading JSON body → return `_error(400, "INVALID_PAYLOAD", ...)`.
3. **Schema validation**: Catch `ValidationError` → return `_error(400, "INVALID_PAYLOAD", f"invalid incident: {exc}")`.
4. **Business validation**: Return `_error(400, "INVALID_PARAMETERS", ...)` for out-of-range query params, missing required headers (`X-User-ID`, `X-Delegated-Token`), or invalid enum values.
5. **Not-found cases**: Return `_error(404, "INCIDENT_NOT_FOUND", ...)` or `_error(404, "REPORT_NOT_FOUND", ...)`.
6. **Success**: Return `JSONResponse` with typed payload.

This pattern ensures every client-facing error has a stable machine-readable `code` field alongside a human-readable `message`.

## Tool Execution Error Model

The tool-gateway uses a structured result model rather than exceptions for tool execution outcomes. In `tool_gateway/tools/base.py`:

- `ToolResult` dataclass carries `status` (`success` | `error` | `denied`), optional `data`, optional `error` dict, and an `evidence` envelope.
- `make_error_result(tool_name, code, message, ...)` creates a standardized error result.
- `make_denied_result(tool_name, reason)` creates a policy-denied result with `status="denied"` and `error.code="POLICY_DENIED"`.
- `build_evidence(risk_level, source_system, duration_ms)` attaches execution metadata.

This allows tools to return errors as normal return values instead of raising exceptions through the call stack, which is important since tools execute in a runtime kernel context.

## Middleware and Observability

All services register an `http` middleware that wraps `call_next(request)` and logs `method`, `path`, `status_code`, and `duration_ms` via `log_event`. The middleware does NOT catch exceptions — it observes whatever response FastAPI produces (including those from unhandled exceptions). This means uncaught exceptions still produce FastAPI's default 500 JSON, but are logged with full context.

Lifespan hooks (`asynccontextmanager`) initialize stores and connectors at startup and close them on shutdown. Startup failures (e.g., unknown connector names per SPEC-015 R-5) raise exceptions during lifespan, causing the process to fail fast rather than serving degraded requests.

## Cross-Cutting Constraints

- **Deny-by-default policy evaluation**: `platform_gateway/services/policy_engine.py` evaluates actions against loaded rules; if no rule matches, `evaluate()` returns `PolicyDecision(decision="deny", reason="no matching policy rule")`. Policy load failures raise `PolicyLoadError` (no silent fallback).
- **Structured error envelopes**: Both API responses (`{"error": {"code": ..., "message": ...}}`) and tool results (`ToolResult.error = {"code": ..., "message": ...}`) use the same two-field shape for consistency.
- **Validation-driven errors**: Pydantic schema validation is the primary input validation mechanism; custom business rules add additional `_error(400, "INVALID_PARAMETERS", ...)` checks.
- **No panics/recover**: Python `try/except` is used everywhere; there is no `try/finally` cleanup around critical paths except in lifespan hooks for resource management.
- **Defensive fallbacks**: Some internal paths (e.g., `agent_platform/runtime_kernel.py`) catch `Exception` broadly with comments like `# defensive fallback` to prevent one failing subsystem from taking down the whole process.