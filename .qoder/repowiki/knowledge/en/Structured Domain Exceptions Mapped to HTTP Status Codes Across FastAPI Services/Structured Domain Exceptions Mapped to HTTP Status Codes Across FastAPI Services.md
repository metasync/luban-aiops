---
kind: error_handling
name: Structured Domain Exceptions Mapped to HTTP Status Codes Across FastAPI Services
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/core/dependencies.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
---

## Overview

The Luban platform uses a consistent, service-local error-handling pattern across all nine Python services. Each service defines small, domain-specific exception hierarchies in its `services/` modules and translates them at the API boundary into FastAPI `HTTPException`s with explicit status codes. There is no shared base error type or global exception handler — each product owns its own error taxonomy.

## Exception Hierarchy Pattern

Each client-facing service builds a three-level hierarchy rooted in a service-specific base `*Error(Exception)`:

- **Configuration errors** (e.g. `IncidentDependencyNotConfigured`, `SkillsDependencyNotConfigured`, `SettingsError`) signal missing runtime configuration; routes answer `503 Service Unavailable`.
- **Service-unavailable / transport errors** (e.g. `IncidentServiceUnavailable`, `SkillsServiceUnavailable`, `StoreError`) wrap network failures or upstream `5xx`; routes answer `502 Bad Gateway`.
- **Domain rejections** (e.g. `IncidentNotFound`, `SkillsClientRejected`, `QueryAuthError`, `TokenVerificationError`, `PolicyLoadError`) carry structured payloads (`status_code`, `message`, `incident_id`, etc.) and are either passed through verbatim or mapped to precise `4xx` codes.

Examples observed:
- `agent_service/services/incident_client.py`: `IncidentClientError` → `IncidentDependencyNotConfigured` / `IncidentServiceUnavailable` / `IncidentNotFound` / `IncidentClientRejected`
- `agent_service/services/skills_client.py`: `SkillsClientError` → `SkillsDependencyNotConfigured` / `SkillsServiceUnavailable` / `SkillsClientRejected`
- `platform_gateway/services/policy_engine.py` and `tool_gateway/services/policy_engine.py`: `PolicyLoadError` for malformed policy bundles
- `audit_service/services/audit_store.py`, `identity_service/services/exchange_service.py`, `incident_service/services/*`, `skills_hub/services/*`: analogous per-service hierarchies

## API Boundary Mapping

Routes in `products/*/src/*/api/routes*.py` catch these exceptions and raise `fastapi.HTTPException(status_code=..., detail=...)`. The mapping is documented inline as a contract:

```python
# agent_service/api/v2/routes.py
except SkillsDependencyNotConfigured as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from None
except SkillsServiceUnavailable as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from None
except SkillsClientRejected as exc:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
```

This pattern appears consistently for both the skills-hub validation path and the incident-service document assembly path, ensuring that an unvalidated draft is never returned — consistency outranks availability on knowledge-production paths.

## Validation Errors

Input validation errors use FastAPI's built-in `HTTPException(422, ...)` directly in route handlers (e.g. missing `X-User-ID`, malformed session IDs, duplicate sessions). These are not wrapped in custom exceptions; they stay at the boundary where request parsing occurs.

## Middleware and Global Handling

There is no repository-wide `@app.exception_handler` registered. Instead, each service's `create_app()` installs only an `http` logging middleware that records `method`, `path`, `status_code`, and `duration_ms` via `log_event`. Error responses flow through FastAPI's default exception handler, which serializes `HTTPException.detail` into the response body. Custom exceptions raised outside the API layer (e.g. `ProviderConfigurationError` in `agent_service/providers/base.py`) propagate up and become 500s unless caught by a route handler.

## Configuration-Time Errors

Startup-time validation raises plain `ValueError` subclasses (e.g. `ProviderConfigurationError`, `SettingsError`) during app construction. These are not converted to HTTP responses — they crash the process, which is appropriate for misconfiguration before any request is served.

## Policy Engine Errors

Both `platform_gateway` and `tool_gateway` define identical `PolicyLoadError` exceptions when loading YAML policy bundles. The tool-gateway additionally logs a warning and skips `require_approval` rules whose actions are not bridged (SPEC-030 R-2), while the platform gateway enforces approval tiers server-side. Both compute a content fingerprint (`_bundle_hash`) at load time for auditability.

## Cross-Service Contract

The error model is intentionally local to each service; cross-service communication uses HTTP status codes plus JSON bodies defined in `shared/shared-contracts/schemas/` (e.g. `policy-decision.schema.json`). Clients decode those schemas rather than relying on shared exception types.

## Conventions Observed

1. Every outbound HTTP call wraps `httpx.HTTPError` into a service-specific `*ServiceUnavailable` and raises it, so callers can distinguish transport failure from business rejection.
2. Upstream `4xx` responses are captured as `*ClientRejected` carrying the original `status_code` and `message`, then re-raised as `HTTPException` with the same code — preserving the upstream semantics.
3. Missing configuration is always `503`, never a silent fallback.
4. Transport/network failures are always `502`, never `500`, keeping infrastructure errors distinct from application bugs.
5. Route handlers use `from None` when chaining `HTTPException` to suppress the internal traceback in logs.
6. No `try/except Exception` blocks swallow errors silently; broad catches are used only around optional background tasks (e.g. model discovery loop) with `contextlib.suppress(asyncio.CancelledError)`.