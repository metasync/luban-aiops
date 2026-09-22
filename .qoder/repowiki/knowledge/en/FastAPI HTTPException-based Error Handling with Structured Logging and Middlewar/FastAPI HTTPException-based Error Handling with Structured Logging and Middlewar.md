---
kind: error_handling
name: FastAPI HTTPException-based Error Handling with Structured Logging and Middleware
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/app.py
    - products/identity-broker/src/identity_service/app.py
    - products/incident-service/src/incident_service/app.py
    - products/skills-hub/src/skills_hub/app.py
    - products/execution-runtime/src/execution_runtime/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/execution-runtime/src/execution_runtime/api/routes/handoff.py
    - products/audit-service/src/audit_service/api/routes/ingest.py
---

## Overview

The Luban platform uses a uniform, lightweight error-handling approach across all nine product services. There is no centralized exception hierarchy or custom error-type library; instead, each service raises FastAPI's `HTTPException` (or returns `JSONResponse` directly) from route handlers, while a per-service HTTP middleware logs every request/response pair as structured JSON events via a shared `core/observability.log_event` helper.

## Key files and packages

- Per-service app entry points that install the logging middleware:
  - `products/platform-gateway/src/platform_gateway/app.py`
  - `products/tool-gateway/src/tool_gateway/app.py`
  - `products/agent-platform/src/agent_service/app.py`
  - `products/audit-service/src/audit_service/app.py`
  - `products/identity-broker/src/identity_service/app.py`
  - `products/incident-service/src/incident_service/app.py`
  - `products/skills-hub/src/skills_hub/app.py`
  - `products/execution-runtime/src/execution_runtime/app.py`
- Per-service observability helpers that configure logging and emit structured events:
  - `products/*/src/*_service/core/observability.py` (e.g. `platform_gateway.core.observability`, `tool_gateway.core.observability`, `agent_service.core.observability`, etc.)
- Route modules where errors are raised, e.g. `products/agent-platform/src/agent_service/api/v2/routes.py`, `products/identity-broker/src/identity_service/api/routes/auth.py`, `products/execution-runtime/src/execution_runtime/api/routes/handoff.py`, `products/audit-service/src/audit_service/api/routes/*.py`.

## Architecture and conventions

### 1. HTTP-level errors: `HTTPException` and `JSONResponse`

Route handlers raise `fastapi.HTTPException(status_code=..., detail="...")` for client/server errors. Examples in this repo include 400 (bad input), 401 (missing auth header / invalid token), 404 (not found), 409 (conflict), 410 (expired confirmation), 422 (validation), 502 (upstream failure), and 503 (unavailable). The agent-platform routes also wrap upstream exceptions (`exc.status_code`, `exc.message`) back into `HTTPException` so downstream callers see a consistent shape.

Some services (notably `audit-service`) return `starlette.responses.JSONResponse(status_code=..., content={"detail": ...})` directly rather than raising an exception, which produces the same HTTP response shape without invoking FastAPI's exception machinery.

There are **no global exception handlers** registered via `@app.exception_handler`; error responses are produced inline at the call site.

### 2. Request/response tracing via middleware

Every service installs an `http` middleware on its `FastAPI` app that:
- Resolves a `request_id` from the `x-request-id` header using `core.request_context.resolve_request_id`.
- Wraps `call_next(request)` to capture the response status code and duration.
- Emits a structured `log_event("http_request", ...)` record containing `service`, `request_id`, `method`, `path`, `status_code`, and `duration_ms`.

This makes the HTTP status code the single source of truth for whether a request succeeded or failed — the middleware records it regardless of how the handler exited.

### 3. Structured audit/error logging

Each service's `core/observability.configure_logging()` raises the root logger level to INFO (overriding Uvicorn's default WARNING) so that `log_event` records survive. Errors and audit events are emitted through `log_event(logger, "event_name", **fields)`, which serializes them as sorted-key JSON lines. This pattern is used both for normal operations and for error paths (e.g. `auth_login_url_requested`, `secret_delivered`, `http_request`).

### 4. Upstream error translation

In the agent-platform routes, calls to other services (e.g. incidents proxy) catch domain exceptions and translate them to `HTTPException` with specific status codes (404 for not found, 502/503 for transport failures, 409 for conflicts). This keeps the API surface stable even when underlying services change their error semantics.

### 5. No panics / no custom exception classes

Across the scanned services there are no `raise SomeCustomError(...)` patterns, no `try/except Exception` blocks outside route handlers, and no `panic` equivalents. Errors bubble up to FastAPI's default exception handler, which converts unhandled exceptions into 500 responses. The only explicit exception handling is the deliberate wrapping of upstream errors into `HTTPException`.

## Conventions and constraints

- **Status-code-first**: Handlers signal errors by setting `status_code` on `HTTPException` or `JSONResponse`; there is no enum or sentinel-error module.
- **Detail messages are plain strings**: `detail` fields contain human-readable text (e.g. `"X-User-ID header required"`, `"confirmation expired"`, `"incident not found"`).
- **Auth failures consistently use 401**: Missing `Authorization` headers, invalid bearer tokens, and OIDC exchange failures all return 401.
- **Upstream failures map to 502/503**: Network or service-to-service errors are surfaced as 502 (Bad Gateway) or 503 (Unavailable) rather than leaking internal tracebacks.
- **Structured logging is mandatory for observability**: Every service configures logging identically via `configure_logging()` and emits events through `log_event()`, ensuring error-related events are captured at INFO level.
- **Request correlation**: All error responses are correlated to a `request_id` propagated through the middleware, enabling end-to-end tracing of failed requests.