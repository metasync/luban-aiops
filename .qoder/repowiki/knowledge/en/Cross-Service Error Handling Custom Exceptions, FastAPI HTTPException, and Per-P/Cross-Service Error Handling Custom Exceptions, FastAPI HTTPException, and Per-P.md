---
kind: error_handling
name: 'Cross-Service Error Handling: Custom Exceptions, FastAPI HTTPException, and Per-Product Conventions'
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/services/authorization_service.py
    - products/tool-gateway/src/tool_gateway/api/routes/authorizations.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/execution-runtime/src/execution_runtime/api/routes/handoff.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/identity-broker/src/identity_service/api/routes/identity.py
    - products/audit-service/src/audit_service/api/routes/ingest.py
    - products/incident-service/src/incident_service/api/routes/incidents.py
    - products/skills-hub/src/skills_hub/api/routes/skills.py
---

## Overview

The Luban platform is a multi-product Python workspace (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway). There is no shared `errors/` package; each product defines its own error types and conventions. The common thread is:

1. **FastAPI** is the web framework used by every HTTP service.
2. Route handlers raise either FastAPI's built-in `HTTPException` or a product-specific exception class that carries an HTTP status + detail.
3. Service-layer exceptions are caught at the route boundary and translated to `HTTPException(status_code=..., detail=...)`, often with `from None` to suppress the original traceback from the JSON response.
4. Internal protocol-level failures use dedicated sentinel exceptions (e.g. `ProtocolError`) that are not exposed over HTTP.
5. A single HTTP middleware in `platform-gateway` wraps all requests and converts unhandled exceptions into a safe 503 redirect or JSON body for the secret authorization edge.
6. No `panic`/`recover` exists — this is Python, so `try/except` is the only propagation mechanism.

## Key Files and Packages

| Product | File(s) | Role |
|---|---|---|
| platform-gateway | `products/platform-gateway/src/platform_gateway/app.py` | Global HTTP middleware that catches `Exception`, re-raises for non-secret edges, and returns a fixed 503 JSON body for the secret `/api/v1/targets/authorizations` edge. |
| tool-gateway | `products/tool-gateway/src/tool_gateway/services/authorization_service.py` | Defines `AuthorizationError(Exception)` carrying `status_code` and `detail`; routes catch it and re-raise as `HTTPException`. |
| agent-platform | `products/agent-platform/src/agent_service/providers/base.py` | Defines `ProviderConfigurationError(ValueError)` raised by every LLM provider when configuration is invalid. |
| execution-runtime | `products/execution-runtime/src/execution_runtime/api/routes/handoff.py` | Uses internal `ProtocolError` (reason codes like `bad_request`, `args_digest_mismatch`, `credential_missing`, `gateway_not_configured`) and maps them to structured JSON via `refused()`; also uses `_STORE_ERRORS = (psycopg.Error, ProtocolError)` as a retry/uncertainty sentinel. |
| identity-broker | `products/identity-broker/src/identity_service/api/routes/auth.py`, `identity.py` | Raises `HTTPException` directly for OIDC exchange failures, token refresh failures, and missing/invalid bearer tokens. |
| audit-service | `products/audit-service/src/audit_service/api/routes/ingest.py`, `query.py`, `summary.py`, `export.py` | Returns `JSONResponse(status_code=..., content={"detail": ...})` directly rather than raising `HTTPException`. |
| incident-service | `products/incident-service/src/incident_service/api/routes/incidents.py`, `webhooks.py` | Local helper `_error(status_code, code, message)` builds a uniform `JSONResponse` envelope. |
| skills-hub | `products/skills-hub/src/skills_hub/api/routes/skills.py` | Same `_error(status_code, code, message)` local helper pattern. |

## Architecture and Conventions

### 1. Service-layer exceptions carry HTTP semantics
`AuthorizationError` in tool-gateway is the canonical example:

```python
class AuthorizationError(Exception):
    """A fail-closed refusal carrying an HTTP status and a non-sensitive detail."""
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
```

Every route that calls the authorization service follows the same shape:

```python
try:
    result = await service.start(...)
except AuthorizationError as exc:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
```

This keeps business logic free of FastAPI imports while still producing a precise HTTP response.

### 2. Provider configuration errors form a small hierarchy
All LLM providers (`openai`, `dashscope`, `deepseek`, `luban`) raise `ProviderConfigurationError` (a subclass of `ValueError`) when required environment variables / keys are missing. This lets callers distinguish misconfiguration from runtime failures.

### 3. Internal protocol errors are not exposed over HTTP
`execution-runtime` defines `ProtocolError(reason_code: str)` and raises it for malformed handoff payloads (`bad_request`, `args_digest_mismatch`, `credential_missing`, `gateway_not_configured`). The route handler catches `(ValueError, TypeError, RecursionError)` and translates any `ProtocolError` through `refused()`, which maps reason codes to specific HTTP statuses (401, 410, 409, 400).

### 4. Store-write uncertainty is modeled explicitly
`_STORE_ERRORS = (psycopg.Error, ProtocolError)` is reused throughout `handoff.py` to detect ambiguous database commits. When these occur, the code does not blindly return failure — it reads back the receipt to determine idempotency before deciding whether to report `unavailable` (503) or a refused state.

### 5. Gateway middleware centralizes cross-cutting error logging
`platform-gateway/app.py` installs a single `@app.middleware("http")` that:
- Resolves `x-request-id` per request.
- Wraps `call_next(request)` in `try/except Exception`.
- Re-raises for non-secret edges (letting FastAPI's default error handler respond).
- For the secret authorization edge, converts any exception into a fixed `{"detail": "Target authorization unavailable"}` 503 JSON body.
- Emits a structured `log_event("http_request", ...)` with method, path, status_code, duration_ms for every request regardless of outcome.

### 6. Inconsistent response shapes across products
There is no repository-wide convention for error bodies:
- `platform-gateway`, `tool-gateway`, `agent-platform`, `identity-broker` raise `HTTPException` (FastAPI serializes to `{"detail": ...}`).
- `audit-service` returns `JSONResponse(status_code=..., content={"detail": str(exc)})` directly.
- `incident-service` and `skills-hub` define a local `_error(status_code, code, message)` helper returning a custom JSON envelope.
- `execution-runtime` returns a richer protocol envelope with `protocol_version`, `kind`, `request_id`, `recovery`, `durability`, `reason_code`.

This means clients cannot assume a single error schema across services.

### 7. Secret-bearing responses are guarded at the response layer
The authorization routes in `tool-gateway` attach `_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}` to every success response, and the gateway middleware adds `NO_STORE` headers to every response on the secret edge. Errors raised as `AuthorizationError` do not get these headers automatically — they go through `HTTPException`, which bypasses the normal response object.

## Conventions and Constraints

- **Route handlers translate service-layer exceptions to `HTTPException`** — observed consistently in `tool-gateway` authorization routes and `platform-gateway` policy/audit routes. The translation uses `from None` to avoid leaking library tracebacks in the response body.
- **Fail-closed defaults** — disabled features raise `HTTPException(403, "target authorization not enabled")` or `"target authorization unavailable"` rather than falling through to a 404 or silent pass-through.
- **No sensitive data in error details** — the authorization service docstring states "every refusal is a fixed, non-sensitive class"; workload/token verification failures map to generic messages like `"workload token invalid"`, `"delegated identity verification failed"`, never echoing the raw token or exception text.
- **Store-write uncertainty is handled by re-reading receipts**, not by treating `psycopg.Error` as a simple failure — see `persist()` and `stop()` in `execution-runtime/api/routes/handoff.py`.
- **Audit emission is fire-and-forget**: failures in `emit_audit_event` are caught with `except Exception`, logged at warning level, and recorded via `record_audit_emit("error")`; they do not abort the primary operation.
- **No global exception handler is registered** — FastAPI's default `HTTPException` handler is relied upon for most services. Only `platform-gateway` overrides behavior via its HTTP middleware.
- **No centralized error SDK** — each product independently defines its error types; there is no shared `shared/` error module consumed across products.