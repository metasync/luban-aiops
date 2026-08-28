---
kind: error_handling
name: FastAPI HTTPException + Domain-Specific Exceptions with Per-Service Error Responses
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/shift_summary.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/tool-gateway/src/tool_gateway/core/dependencies.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/incident-service/src/incident_service/core/config.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/incident-service/src/incident_service/services/normalization.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/audit-service/src/audit_service/api/routes/query.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/skills-hub/src/skills_hub/api/routes/skills.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
---

## Overview

The platform uses a **per-service, FastAPI-native error handling model** rather than a shared exception hierarchy or global exception handler. Each product service defines its own domain-specific exception classes and converts them to HTTP responses at the API boundary (routes or thin helpers). There is no repository-wide `BaseError` class, no centralized `@app.exception_handler`, and no use of `panic`/`recover` equivalents — Python exceptions are the sole propagation mechanism.

## Exception taxonomy per service

| Service | Custom exceptions | Where they are raised | Boundary conversion |
|---|---|---|---|
| `agent-platform` | `ProviderConfigurationError(ValueError)`, `UnknownModelError(ValueError)`, `WorkerHandoffError(Exception)`, `DigestInputError(Exception)`, `UnknownSessionError(Exception)`, `ForeignSessionDenied(Exception)` | Services (`providers/base.py`, `runtime_kernel.py`, `services/shift_summary.py`, `services/execution_worker_client.py`) | `api/v2/routes.py` catches each specific exception and raises `fastapi.HTTPException` with a precise status code (400, 403, 404, 409) and a human-readable `detail` string; `from None` is used to suppress chaining for input errors. |
| `platform-gateway` | `PolicyLoadError(Exception)`, `TokenVerificationError(Exception)` | `services/policy_engine.py`, `services/token_verifier.py` | Routes raise `HTTPException(401, ...)` on malformed/bad tokens; readiness endpoints return `{status: "degraded", ...}` instead of failing hard. |
| `tool-gateway` | `PolicyLoadError(Exception)`, `TokenVerificationError(Exception)` | Same shape as platform-gateway | `core/dependencies.py` raises `HTTPException(503, "tool registry not initialised")` when app state is missing; `gateway_service.enforce_policy` raises `HTTPException(403, {"detail": "action denied by policy", ...})`; tool invocation returns a JSON body via `make_denied_result` / `make_error_result`. |
| `incident-service` | `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError` | Various services | Not shown in the sampled routes but follow the same pattern of route-level try/except → `HTTPException`. |
| `audit-service` | `StoreError`, `IngestAuthError` | `services/audit_store.py`, `services/ingest_auth.py` | Route wraps `authenticate_caller` and `decode_cursor` in try/except and returns `JSONResponse(status_code=401|400, content={"detail": str(exc)})` — an explicit non-FastAPI response shape. |
| `skills-hub` | `SettingsError`, `QueryAuthError`, `StoreError` | `services/query_auth.py`, `services/skill_store.py` | Uses a local `_error(status_code, code, message)` helper that returns `JSONResponse({"error": {"code": ..., "message": ...}})` — a different envelope from FastAPI's default. |
| `identity-broker` | `ExchangeError` | `services/exchange_service.py` | Imported into routes for conversion. |

## Common patterns

1. **Domain exceptions stay internal.** Business-layer functions raise typed exceptions (`UnknownSessionError`, `PolicyLoadError`, `QueryAuthError`, etc.). The route layer is the only place that maps them to HTTP status codes. This keeps business logic free of HTTP concerns.

2. **FastAPI `HTTPException` is the universal wire format.** Most services rely on FastAPI's built-in exception handler to produce the standard `{"detail": "..."}` JSON envelope. Two services diverge:
   - `audit-service` returns `JSONResponse({"detail": ...})` directly.
   - `skills-hub` returns `JSONResponse({"error": {"code": ..., "message": ...}})` via a local helper.

3. **No global exception handlers.** No `@app.exception_handler` was found in any service's `app.py`. Errors bubble through FastAPI's default handler, so response shape is inherited from how exceptions are raised.

4. **Middleware is logging-only.** Every service registers an `http` middleware that logs method, path, status code, duration, and request ID — it does not transform or catch exceptions.

5. **Readiness/liveness degrade gracefully.** Both `platform-gateway` and `tool-gateway` implement `ready_status()` that catches `PolicyLoadError` and returns `{"status": "degraded", ...}` instead of raising, allowing Kubernetes probes to pass while reporting problems.

6. **Degrade-on-failure for secondary reads.** In `agent_platform/services/shift_summary.py`, `_safe_read` and per-source `try/except Exception` blocks log warnings and return sentinel values (`UNAVAILABLE`, `None`) so a failed transcript/evidence source does not abort the whole summary.

7. **Structured denial bodies for tools.** `tool_gateway.services.gateway_service.invoke_tool` returns a structured JSON body via `make_denied_result` / `make_error_result` for tool invocations, separate from the HTTP 403 `HTTPException` used for auth/policy checks.

8. **Pydantic validation errors propagate naturally.** Several routes accept Pydantic models (e.g., `AuditQuery`, `Incident` schemas); `ValidationError` bubbles up to FastAPI's default handler, producing the framework's standard 422 response. No custom mapping is applied.

## Conventions observed

- Raise domain-specific subclasses of `Exception` (or `ValueError` for configuration/input issues) inside services; never raise raw `Exception` for control flow.
- Convert to `HTTPException` at the route boundary with an explicit `status_code` and a concise `detail` string (or dict).
- Use `from None` when re-raising user-facing input errors to avoid leaking stack traces in logs.
- Distinguish between structural input errors (400), authorization failures (401), policy denials (403), not-found (404), and conflict (409).
- For cross-service calls, let `httpx` raise `HTTPError` and surface it via `response.raise_for_status()`; readiness endpoints catch these and report degraded status.
- Avoid catching broad `Exception` except where degradation is intentional (shift summary sources, telemetry emission) and always log the failure.

## Constraints enforced by the codebase

- There is no shared base exception type across products; each service owns its own exception namespace.
- There is no central error-response formatter — response shapes vary between services (`{"detail": ...}`, `{"error": {"code": ..., "message": ...}}`, tool result objects).
- All services share the same FastAPI middleware pattern for request logging but do not share an error-handling middleware.