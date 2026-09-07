---
kind: error_handling
name: FastAPI HTTPException + domain-specific Exception hierarchy with per-service error response conventions
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/incident-service/src/incident_service/api/routes/incidents.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/identity-broker/src/identity_service/api/routes/identity.py
    - products/skills-hub/src/skills_hub/api/routes/skills.py
    - products/audit-service/src/audit_service/api/routes/ingest.py
    - products/audit-service/src/audit_service/api/routes/query.py
---

## Overview

The Luban AIOps platform is a multi-product Python workspace (agent-platform, platform-gateway, tool-gateway, audit-service, identity-broker, incident-service, skills-hub, execution-runtime) built on FastAPI. Error handling follows a consistent two-layer pattern: **domain-level exceptions** raised deep in services, and **HTTP boundary mapping** at route/dependency layers that translate them into standardized HTTP responses. There is no centralized exception middleware; each product owns its own error surface.

## Domain-level exceptions

Each service defines small, purpose-specific exception classes in its `services/` or `core/` packages:

- **agent-platform**: `ConfirmationNotFound`, `ConfirmationExpired` (in `hitl_confirmations.py`); `DigestInputError`, `ForeignSessionDenied`, `UnknownSessionError` (in `shift_summary.py`); `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`; `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`.
- **tool-gateway**: `PolicyLoadError` (policy engine), `TokenVerificationError` (token verifier).
- **audit-service**: `StoreError`, `IngestAuthError`.
- **incident-service**: `SettingsError`, `ConnectorConfigError`, `NormalizationError`, `QueryAuthError`, `TriageError`, `StoreError`.
- **identity-broker**: `ExchangeError` carrying a `status_code` field for downstream mapping.
- **skills-hub**: `SettingsError`, `StoreError`, `QueryAuthError`.

These exceptions are intentionally narrow — they carry enough context to be mapped but never leak internal state to the wire.

## HTTP boundary mapping

### FastAPI `HTTPException` as the primary wire format

Most products raise `fastapi.HTTPException(status_code=..., detail=...)` directly at route boundaries:

- **agent-platform v2 routes** (`agent_service/api/v2/routes.py`) raise `HTTPException` for auth failures (401), conflict states like parked confirmations (409), unknown model ids (422), expired confirmations (410), not-found sessions (404), and upstream dependency failures (503 for agent-platform, 502 for skill/incident clients). Dependency errors are caught explicitly by type so callers can distinguish configuration vs. availability vs. rejection.
- **platform-gateway** proxies map upstream failures uniformly: `httpx.HTTPError` → 502 "service unavailable"; client errors from the audit service (4xx) are re-raised unchanged so operators can distinguish bad requests from outages; missing config → 503.
- **tool-gateway** raises 401 for malformed/missing bearer tokens, 403 for policy denials (with structured `{detail, action, reason}`), and returns `JSONResponse` with status 403 for authorization results.
- **identity-broker** raises 401 for missing/invalid tokens and re-raises upstream OIDC exchange errors with their original status codes.
- **audit-service, skills-hub, incident-service** use a local `_error(status_code, code, message)` helper returning `JSONResponse(content={"error": {"code": ..., "message": ...}})` — a uniform envelope distinct from FastAPI's default JSON body.

### Upstream proxying convention

Gateway-style services (platform-gateway, tool-gateway, identity-broker, audit-service) follow the same pattern when calling downstream services:

```python
try:
    response = await httpx.AsyncClient(...).get(url, ...)
except httpx.HTTPError as exc:
    raise HTTPException(status_code=502, detail="... unavailable") from exc
if response.status_code >= 300:
    if 400 <= response.status_code < 500:
        raise HTTPException(status_code=response.status_code, detail="... rejected ...")
    raise HTTPException(status_code=502, detail="... failed")
```

This preserves client errors while collapsing network/transient failures into 502.

### Structured error envelopes

Two conventions coexist:

1. **FastAPI default** (`HTTPException`): used by agent-platform, platform-gateway, tool-gateway, identity-broker. The `detail` field may be a string or a dict (e.g., tool-gateway policy denial includes `action` and `reason`).
2. **Custom envelope** (`{"error": {"code": ..., "message": ...}}`): used by incident-service, skills-hub, and audit-service query/ingest routes. This gives stable machine-readable error codes (`UNAUTHORIZED`, `INVALID_PAYLOAD`, `INCIDENT_NOT_FOUND`, `REPORT_NOT_FOUND`, etc.).

## Conventions and constraints

- **No global exception handler**: Each product handles errors locally in its routes/dependencies rather than via a shared FastAPI exception handler. This keeps error surfaces explicit per service.
- **Domain exceptions stay below the wire**: Service-layer exceptions are never returned directly over HTTP; they are always caught and translated to `HTTPException` or a custom JSON envelope at the API layer.
- **Status-code discipline**: 401 for missing/malformed auth headers, 403 for policy denials, 404 for not-found resources, 409 for conflict/parked-state, 410 for expired HITL confirmations, 422 for unknown model ids, 502 for upstream unavailability, 503 for missing service configuration.
- **`from None` chaining on route-level raises**: Routes often suppress exception chains (`raise HTTPException(...) from None`) to avoid leaking stack traces in production logs.
- **Audit emission is fire-and-forget with failure logging**: When audit ingestion fails (non-2xx), services log the status code and continue — audit delivery is best-effort and does not fail the primary request.
- **Per-process in-memory state is guarded**: The confirmation registry in agent-platform is deliberately process-scoped; expired entries are closed through kernel interrupts rather than silently evicted, preventing wedged sessions.
- **No panics / no `sys.exit`**: Errors propagate as exceptions; there is no use of `panic()` or `os._exit` anywhere in the Python services.