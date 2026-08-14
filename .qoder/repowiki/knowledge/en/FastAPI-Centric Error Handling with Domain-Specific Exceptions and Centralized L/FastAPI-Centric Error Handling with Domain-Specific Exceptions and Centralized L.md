---
kind: error_handling
name: FastAPI-Centric Error Handling with Domain-Specific Exceptions and Centralized Logging
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/services/session_service.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/audit-service/src/audit_service/app.py
    - products/identity-broker/src/identity_service/app.py
---

## What system/approach is used

The codebase uses FastAPI as the HTTP framework across all services (`agent-platform`, `platform-gateway`, `identity-broker`, `audit-service`, `tool-gateway`). Errors are handled primarily through:

1. **FastAPI's built-in `HTTPException`** — raised directly in route handlers and service functions to produce structured JSON error responses with appropriate HTTP status codes.
2. **Domain-specific exception classes** — small, purpose-built exceptions (e.g., `ProviderConfigurationError`, `StoreError`, `IngestAuthError`, `ExchangeError`, `TokenVerificationError`, `PolicyLoadError`) that encapsulate domain failure modes before being translated to HTTP responses at boundaries.
3. **Per-service HTTP middleware** — every service registers an `@app.middleware("http")` handler that logs each request/response pair with timing, status code, method, path, and a propagated `x-request-id`. This is the only cross-cutting concern applied uniformly; there are no global exception handlers registered via `@app.exception_handler`.
4. **No `try/except`-based response mapping** — errors bubble up to FastAPI's default exception handler, which converts `HTTPException` into JSON responses. There is no centralized error-to-JSON mapper or custom exception handler class.

## Key files and packages

- `products/agent-platform/src/agent_service/providers/base.py` — defines `ProviderConfigurationError(ValueError)` for provider misconfiguration.
- `products/agent-platform/src/agent_service/services/session_service.py` — raises `HTTPException(status_code=404, detail="session not found")` for missing sessions; intentionally returns 404 instead of 403 so foreign session IDs are indistinguishable from unknown ones.
- `products/agent-platform/src/agent_service/api/v2/routes.py` — raises `HTTPException(status_code=401, detail="X-User-ID header required")` when identity headers are missing.
- `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — centralizes identity resolution (`resolve_request_identity`) and policy enforcement (`enforce_policy`), raising `HTTPException(401, ...)` for auth failures and `HTTPException(403, {"detail": "action denied by policy", ...})` for policy denials.
- `products/tool-gateway/src/tool_gateway/services/gateway_service.py` — mirrors the same pattern: `HTTPException(401, ...)` for malformed/missing tokens, `HTTPException(403, ...)` for policy denial, plus a `ready_status` that catches `PolicyLoadError` to report degraded readiness.
- `products/identity-broker/src/identity_service/api/routes/auth.py` — translates upstream OIDC failures (`httpx.HTTPStatusError`) into `HTTPException(502, ...)`, and wraps exchange failures (`ExchangeError`) into `HTTPException(exc.status_code, exc.detail)` after emitting audit events.
- `products/audit-service/src/audit_service/services/audit_store.py` — defines `StoreError(Exception)` for store-level failures; `build_audit_store` raises it when `AUDIT_DB_URL` is missing for postgres backend.
- Per-service `app.py` files (`platform_gateway/app.py`, `tool_gateway/app.py`, `audit_service/app.py`, `identity_service/app.py`) — register the uniform logging middleware and include routers.

## Architecture and conventions

### Exception taxonomy
- **Domain exceptions** live next to the logic that raises them (e.g., `ProviderConfigurationError` in providers, `StoreError` in audit store, `ExchangeError` in exchange service). They inherit from `ValueError` or bare `Exception` and carry a string message.
- **Boundary translation** happens at the API layer: domain exceptions are caught in routes or gateway services and re-raised as `HTTPException` with explicit status codes. For example, `identity_service/api/routes/auth.py` catches `ExchangeError` and emits an audit event before re-raising as `HTTPException(exc.status_code, exc.detail)`.
- **Upstream client errors** (e.g., `httpx.HTTPStatusError` from calls to the identity broker) are caught and mapped to 502 or 401 responses.

### Status code conventions
- **401 Unauthorized** — missing or malformed `Authorization` header, missing `X-User-ID` header, expired token, failed token refresh.
- **403 Forbidden** — policy engine returning `deny`; tool invocation denied due to missing identity context; redaction overflow results in a 400 but policy denial stays 403.
- **404 Not Found** — missing session; deliberately used instead of 403 to avoid leaking whether a session exists but belongs to another user.
- **400 Bad Request** — tool execution returned a non-success status (e.g., tool runtime error).
- **502 Bad Gateway** — upstream OIDC token exchange failed.

### Middleware-only cross-cutting behavior
Each service's `create_app()` installs identical middleware:
```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = resolve_request_id(request.headers.get("x-request-id"))
    started_at = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    log_event(LOGGER, "http_request", ..., status_code=response.status_code, duration_ms=duration_ms)
    return response
```
This ensures every request — including errored ones — is logged with its final status code and duration. No per-route error logging is needed.

### Readiness vs liveness
- `live_status()` always returns `{"status": "ok"}`.
- `ready_status()` attempts to load the policy bundle (and in platform-gateway, also pings the agent service); on `PolicyLoadError` or `httpx.HTTPError`, it returns `{"status": "degraded", ...}` rather than raising.

### Audit trail integration
Errors that represent security-relevant decisions (policy deny, token exchange reject) are mirrored to the durable audit trail via `emit_audit_event(...)` before the HTTP exception is raised, ensuring the error is recorded even if the HTTP response fails.

## Conventions and constraints

- **No global exception handlers**: The codebase does not define `@app.exception_handler` anywhere; all error-to-HTTP mapping is done explicitly at the boundary.
- **Structured error bodies**: When returning error responses, the `detail` field is either a plain string (for simple cases like `"authentication required"`) or a dict containing `detail`, `action`, and `reason` (for policy denials), enabling clients to distinguish error categories.
- **Identity leakage prevention**: Session ownership checks raise 404 (not 403) so callers cannot enumerate valid session IDs by checking authorization outcomes.
- **Redaction overflow is fail-closed**: If PII redaction exceeds configured thresholds, the tool result is replaced with an error result (`REDACTION_OVERFLOW`) and logged as a warning — the response is withheld rather than leaking sensitive data.
- **Readiness endpoints never raise**: `ready_status()` swallows `PolicyLoadError` and network errors to keep health probes passing in degraded states.
- **Audit events accompany errors**: Token exchange rejections and policy denials emit audit events with outcome `"deny"` before raising HTTP exceptions, making the audit trail the source of truth for security decisions.