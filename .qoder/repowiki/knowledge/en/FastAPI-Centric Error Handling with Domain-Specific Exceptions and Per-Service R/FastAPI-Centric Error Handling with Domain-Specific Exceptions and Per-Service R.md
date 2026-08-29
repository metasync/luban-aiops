---
kind: error_handling
name: FastAPI-Centric Error Handling with Domain-Specific Exceptions and Per-Service Response Conventions
category: error_handling
scope:
    - '**'
source_files:
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/incident-service/src/incident_service/api/routes/incidents.py
    - products/skills-hub/src/skills_hub/api/routes/skills.py
    - products/identity-broker/src/identity_broker/services/exchange_service.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/agent-platform/src/agent_service/app.py
---

## Overview

The monorepo uses FastAPI as the HTTP framework across all Python services (`agent-platform`, `audit-service`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`). There is no shared error-handling library; each product defines its own domain exceptions and routes their errors to HTTP responses at the service boundary. The pattern is consistent: business-layer functions raise typed domain exceptions, route handlers catch them and return either `fastapi.HTTPException` (for gateway-facing services) or a structured `JSONResponse` (for data services).

## Domain Exception Types

Each service defines small, purpose-specific exception classes in its `services/` layer:

- **audit-service**: `IngestAuthError` (authentication failures → 401), `StoreError` (persistence failures, e.g. invalid cursor)
- **platform-gateway**: `TokenVerificationError` (JWT verification failures, carries a `detail` string), `PolicyLoadError`
- **tool-gateway**: `PolicyLoadError`, `TokenVerificationError` (mirrors platform-gateway's type)
- **identity-broker**: `ExchangeError(detail, status_code)` — a reusable exception that carries both a human-readable message and the target HTTP status code so callers can re-raise it directly
- **skills-hub**: `SettingsError` for configuration validation failures
- **incident-service**: `QueryAuthError`, `NormalizationError`, `ConnectorConfigError`

These exceptions are raised deep in service logic (auth, store, policy, token verification) and never propagate to the HTTP layer uncaught.

## Route-Level Error Mapping

### Gateway-facing services (platform-gateway, agent-platform, identity-broker, tool-gateway)

Route handlers convert domain exceptions into `fastapi.HTTPException` with explicit `status_code` and `detail`. Examples:

- `platform_gateway/api/routes/audit.py`: upstream `httpx.HTTPError` → `HTTPException(502, "audit service unavailable")`; 4xx from upstream passed through unchanged
- `platform_gateway/services/token_verifier.py`: `jwt.ExpiredSignatureError` / `InvalidIssuerError` / `InvalidAudienceError` / `InvalidTokenError` → `TokenVerificationError`, caught by routes which map to `HTTPException(401, ...)`
- `tool_gateway/services/gateway_service.py`: policy deny → `HTTPException(403, {"detail": "action denied by policy", "action": ..., "reason": ...})`; missing auth → `HTTPException(401, "authentication required")`
- `agent_platform/src/agent_service/api/v2/routes.py`: `ConfirmationNotFound` → `HTTPException(404, ...)`, `ConfirmationExpired` → `HTTPException(410, ...)`, `ConfirmationOwnerMismatch` → `HTTPException(409, ...)`
- `identity_broker/api/routes/auth.py`: `ExchangeError` re-raised as `HTTPException(exc.status_code, exc.detail)`

No global `@app.exception_handler` is registered in any service; FastAPI's default exception handler renders `HTTPException` responses.

### Data services (audit-service, incident-service, skills-hub)

These services return structured JSON error bodies via a local `_error(status_code, code, message)` helper that produces `{"error": {"code": ..., "message": ...}}`:

- `incident_service/api/routes/incidents.py`: `UNAUTHORIZED`, `INVALID_PAYLOAD`, `INCIDENT_NOT_FOUND`, `REPORT_NOT_FOUND`, `INVALID_PARAMETERS`
- `skills_hub/api/routes/skills.py`: same pattern
- `audit_service/api/routes/ingest.py`: returns `JSONResponse(status_code=400, content={"detail": ...})` for parse/validation failures, and `JSONResponse(status_code=401, content={"detail": str(exc)})` for `IngestAuthError`

This gives clients a stable machine-readable error envelope on these services.

## Cross-Cutting Patterns

1. **Authentication failures are always 401** — whether from Basic credentials, Bearer tokens, or missing headers, the response is 401 with a short detail string.
2. **Authorization/policy denials are 403** — `tool_gateway.services.gateway_service.enforce_policy` raises `HTTPException(403, {...})` carrying `action`, `reason`, and matched rule IDs; mutating tools additionally require `tools:mutate`.
3. **Upstream service failures are proxied or wrapped** — `platform-gateway` catches `httpx.HTTPError` and maps them to 502; if the upstream returns 4xx it passes the status through; 5xx becomes 502.
4. **Fire-and-forget audit emission swallows errors** — `audit_emitter.py` in multiple services wraps outbound audit calls in `try/except Exception` with a `# noqa: BLE001` comment, ensuring audit delivery never breaks the request path.
5. **Readiness/liveness paths never raise** — `audit_store.ready()` wraps operations in `except Exception` returning `False` so health checks stay green even when the backend is down.
6. **Request-level middleware logs every response** — each service registers an `@app.middleware("http")` that records `method`, `path`, `status_code`, and `duration_ms` via `log_event`, regardless of success or failure.
7. **No panics / no `sys.exit`** — the codebase avoids `raise SystemExit` and `sys.exit`; unrecoverable conditions surface as exceptions rather than process termination.
8. **Structured config validation errors** — `settings` modules raise typed `SettingsError` with descriptive messages for malformed environment variables (e.g. `SKILLS_SOURCES` not valid JSON, duplicate `source_id`).

## Notable Absences

- There is no shared `errors/` package or base `AppError` class across products; each service defines its own exception hierarchy locally.
- There is no global exception handler registered in `create_app()` — services rely on FastAPI's built-in handling of `HTTPException`.
- There is no standardized error-code enumeration; codes like `INVALID_PAYLOAD`, `INCIDENT_NOT_FOUND`, `UNAUTHORIZED` are ad hoc strings defined per route module.
- No `pydantic` `ValidationError` is caught globally; each route handles it inline and converts to its own error envelope.