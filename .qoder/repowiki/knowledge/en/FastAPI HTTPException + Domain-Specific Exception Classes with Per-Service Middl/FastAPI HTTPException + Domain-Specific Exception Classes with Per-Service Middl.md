---
kind: error_handling
name: FastAPI HTTPException + Domain-Specific Exception Classes with Per-Service Middleware Logging
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/core/request_context.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/identity-broker/src/identity_service/services/token_service.py
    - products/audit-service/src/audit_service/app.py
    - products/incident-service/src/incident_service/app.py
    - products/skills-hub/src/skills_hub/app.py
---

## System Overview

The Luban platform is a collection of FastAPI microservices. Error handling follows a consistent, service-local pattern: business and transport errors are surfaced as `fastapi.HTTPException` from route handlers and gateway services, while domain-level failures in libraries (JWT verification, policy bundle loading) are raised as typed Python exceptions that callers translate into HTTP responses.

There is no shared error package across products; each service defines its own small set of exception classes in the relevant service module and handles them at the boundary between the service layer and the HTTP layer.

## Key Files and Packages

- **Platform Gateway** — `platform_gateway/services/token_verifier.py` defines `TokenVerificationError`; `platform_gateway/api/routes/auth.py` catches it to return `{"authenticated": False}`; `platform_gateway/services/policy_engine.py` defines `PolicyLoadError` for invalid policy bundles; `platform_gateway/services/gateway_service.py` raises `HTTPException(401)` for auth failures and `HTTPException(403)` for policy denials.
- **Tool Gateway** — `tool_gateway/services/gateway_service.py` raises `HTTPException(401)` on malformed/missing tokens and `HTTPException(403)` on policy denial or missing identity; tool invocation returns a structured JSON response with status codes 200/400/403 based on the tool result.
- **Agent Platform (agent-service)** — `products/agent-platform/src/agent_service/api/v2/routes.py` is the primary place where `HTTPException` is raised directly with explicit status codes: 401 (missing `X-User-ID`), 409 (conflict), 410 (confirmation expired), 422 (validation), 404 (not found), 400 (bad request), 502/503 (upstream failures). It also re-raises upstream `exc.status_code` / `exc.message` from a client call via `from None`.
- **Identity Broker** — `identity_service/services/token_service.py` does not raise custom exceptions; configuration issues surface as log warnings (ephemeral key, dev key generation).
- **Other services** (`audit-service`, `incident-service`, `skills-hub`, `policy-center`) — rely on FastAPI's default exception handling; no custom error types were observed in their app/route files.

## Architecture and Conventions

### 1. Per-request middleware logs every response
Every service registers an `@app.middleware("http")` handler that resolves a correlation `request_id` (via `resolve_request_id` from `core/request_context.py`, which prefers the inbound `x-request-id` header, then the active OTel trace ID, then a generated UUID) and emits a structured `log_event` with `method`, `path`, `status_code`, and `duration_ms`. This means HTTP status codes are the canonical error signal — they are always recorded even when a route handler raises an exception.

### 2. Domain exceptions stay internal; HTTP boundaries use HTTPException
Domain-layer functions raise typed exceptions:
- `TokenVerificationError` (detail string) in token verifiers.
- `PolicyLoadError` (no message field) when a policy YAML cannot be parsed or loaded.

Callers catch these and convert them to `HTTPException` with appropriate status codes (401 for auth failures, 403 for policy denials). The conversion happens in the service layer (`gateway_service.py`, `auth.py`), never in routes.

### 3. Policy enforcement uses a three-outcome model
`platform_gateway/services/policy_engine.py` models decisions as `allow`, `deny`, or `require_approval` with precedence `deny > require_approval > allow`. A deny decision is converted to `HTTPException(status_code=403)` by `enforce_policy()` in both the platform gateway and the tool gateway. There is no generic "error code" field in responses — the reason is embedded in the `detail` dict.

### 4. Tool results carry structured error payloads
Tool invocations do not raise exceptions back to the caller. Instead, `tool_gateway/services/gateway_service.invoke_tool` returns a `JSONResponse` whose body is a tool result object with a `status` field (`success`, `denied`, `error`). Status codes are mapped: 200 for success, 400 for tool errors, 403 for denied. Redaction overflow produces a special `REDACTION_OVERFLOW` error result rather than raising.

### 5. Upstream client errors are re-raised with preserved semantics
In `agent_service/api/v2/routes.py`, calls to downstream services wrap failures so that the original `exc.status_code` and `exc.message` are forwarded to the client via `HTTPException(status_code=exc.status_code, detail=exc.message) from None`, preserving the upstream error shape.

### 6. No global exception handler is registered
No service overrides FastAPI's default exception handler. Errors flow through the standard FastAPI pipeline, which converts `HTTPException` to JSON responses and logs unhandled exceptions via the configured logging backend. The per-request middleware still records the final `status_code` regardless.

### 7. Health/readiness endpoints encode degraded state
Readiness checks (e.g., `ready_status` in `tool_gateway/services/gateway_service.py`) attempt to load the policy bundle and return `{"status": "degraded", "policy_error": str(exc)}` instead of raising, so liveness probes can distinguish startup failures from runtime errors.

## Conventions and Constraints Observed

- **Authentication failures → 401**: Missing bearer token, malformed `Authorization` header, expired token, invalid issuer/audience all map to `HTTPException(401)`.
- **Authorization failures → 403**: Policy deny, missing identity context, mutating tool invoked without `tools:mutate` grant all map to `HTTPException(403)`.
- **Business conflicts → 409**: Duplicate session creation, conflicting confirmation states use 409 in agent-service routes.
- **Not found → 404**: Missing confirmations and sessions use 404.
- **Validation errors → 422**: Agent-service routes raise 422 for invalid inputs.
- **Upstream failures → 502/503**: Downstream connectivity problems are mapped to 502/503 with the underlying exception message.
- **Request correlation**: Every service resolves `x-request-id` consistently via `resolve_request_id` (except identity-broker, which inlines the same logic); this ID is attached to all log events and audit entries.
- **No panics/recover**: Python `raise` is used exclusively; there are no `try/except` blocks around entire handlers intended to recover from unexpected errors.
- **Audit trail decoupled from response path**: Audit events are emitted alongside error responses but are fire-and-forget; audit ingestion failures do not alter the HTTP response status.