---
kind: error_handling
name: FastAPI HTTPException-driven error handling with domain-specific exception classes per service
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/identity-broker/src/identity_service/api/routes/identity.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/agent-platform/src/agent_service/app.py
---

## Overview

The codebase is a multi-service Python platform (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) built on FastAPI. Error handling follows a consistent pattern across every product: domain-level functions raise typed `Exception` subclasses that are caught at the API boundary and translated into `fastapi.HTTPException` responses with explicit HTTP status codes. There is no centralized global exception handler; each service's routes or services perform the translation locally.

## Domain-specific exception types

Each service defines small, purpose-built exception classes near the code that raises them:

- **audit-service**: `StoreError`, `IngestAuthError`
- **incident-service**: `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError`
- **identity-broker**: `ExchangeError`
- **skills-hub**: `SettingsError`, `QueryAuthError`, `StoreError`
- **tool-gateway**: `PolicyLoadError`, `TokenVerificationError`
- **platform-gateway**: `TokenVerificationError` (imported from tool-gateway/shared policy engine)

These exceptions carry structured information (often `status_code` / `message` / `detail` attributes) so route handlers can map them to precise HTTP responses without losing context.

## Route-layer mapping to HTTP responses

Routes catch domain exceptions and re-raise `HTTPException` with a status code chosen by the failure category. The most common mapping pattern appears in `products/agent-platform/src/agent_service/api/v2/routes.py` (and mirrored in other services):

| Domain exception | HTTP status | Meaning |
|---|---|---|
| `*DependencyNotConfigured` (e.g. `SkillsDependencyNotConfigured`, `IncidentDependencyNotConfigured`) | 503 | Optional downstream not configured — caller should degrade gracefully |
| `*ServiceUnavailable` / `*ClientRejected` | 502 | Downstream unreachable or upstream returned an error |
| `*NotFound` (e.g. `IncidentNotFound`, `UnknownSessionError`) | 404 | Resource does not exist |
| `NoValidatedTriageReport` | 409 | Business precondition missing |
| Token verification failures (`TokenVerificationError`) | 401 | Invalid/expired token |
| Missing auth headers | 401 | Authentication required |
| Policy deny decisions | 403 | Action denied by policy |

Example from agent-platform routes (lines 861–866):
```python
except SkillsDependencyNotConfigured as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from None
except SkillsServiceUnavailable as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from None
except SkillsClientRejected as exc:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
```

## Upstream error propagation

Gateway-style services (platform-gateway, identity-broker, tool-gateway) wrap outbound HTTP calls with `httpx` and translate transport errors into HTTP responses:

- `httpx.HTTPStatusError` with status < 500 → pass through the upstream status code and `detail` body
- `httpx.HTTPStatusError` with status ≥ 500 → return 502 with a user-facing message
- Generic `httpx.HTTPError` → return 502 "unreachable"

This keeps callers of the gateway seeing a uniform 5xx for backend failures while preserving client errors (4xx) from upstream services.

## Policy enforcement errors

The policy engine in `tool-gateway/services/policy_engine.py` raises `PolicyLoadError` when a YAML bundle is malformed or contains invalid rules. This is a load-time error (policy bundle parsing), distinct from runtime denials. At runtime, `enforce_policy()` in `platform-gateway/services/gateway_service.py` raises `HTTPException(403, ...)` with a structured `{detail, action, reason}` payload whenever a rule evaluates to `deny`. The decision is also emitted to the audit trail before raising.

## Middleware and logging

Services register a single FastAPI `@app.middleware("http")` (see `agent_service/app.py`) that wraps every request, extracts `x-request-id`, measures duration, and emits a structured `http_request` log event via `log_event`. No custom exception handler is registered — unhandled exceptions bubble to FastAPI's default JSON error response, which is acceptable because all expected error paths explicitly raise `HTTPException`.

## Conventions observed

- **Never swallow errors silently**: every catch block either converts to `HTTPException` or re-raises with `from None` / `from exc` to preserve chainability.
- **Downstream failures are categorized**: configuration absence → 503, network/unreachable → 502, business precondition → 409, not found → 404, auth → 401, policy deny → 403.
- **Domain exceptions stay out of the API layer**: only routes translate them to HTTP; services keep pure Python semantics.
- **Structured 403 payloads** include `action` and `reason` fields for auditability.
- **No global exception handler exists**; error translation is local to each route/service module.
- **Tests cover error paths**: each product has tests named after error scenarios (e.g. `test_contracts.py`, `test_routes.py`, `test_telemetry.py`) asserting the HTTP status codes produced by these mappings.