---
kind: error_handling
name: FastAPI HTTPException + Domain-Specific Exceptions with Per-Service Error Boundaries
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/incident-service/src/incident_service/core/config.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/platform-gateway/src/platform_gateway/api/routes/incidents.py
    - products/platform-gateway/src/platform_gateway/api/routes/tools.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/agent-platform/src/agent_service/app.py
---

## Overview

The Luban AIOps platform is a multi-product Python workspace (agent-platform, platform-gateway, tool-gateway, audit-service, identity-broker, incident-service, execution-runtime, skills-hub). Each product is an independent FastAPI service. There is no shared error-handling library or cross-cutting exception hierarchy; instead, each service defines its own small set of domain-specific `Exception` subclasses and converts them at the API boundary into standardized `fastapi.HTTPException` responses.

## Approach per layer

### 1. Domain-layer exceptions (service-scoped)
Each service declares narrowly scoped exception classes in the module where they are raised:

| Service | Exception types | Purpose |
|---|---|---|
| `audit-service` | `StoreError`, `IngestAuthError` | Store operations, ingestion auth failures |
| `incident-service` | `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError` | Config, connectors, store, normalization, query auth, triage |
| `tool-gateway` | `PolicyLoadError`, `TokenVerificationError` | Policy bundle load/validation, JWT verification |
| `agent-platform` | `ConfirmationNotFound`, `ConfirmationExpired`, `UnknownSessionError`, `ForeignSessionDenied`, `DigestInputError`, `NoValidatedTriageReport`, plus client errors from `incident_client` (`IncidentDependencyNotConfigured`, `IncidentNotFound`, `IncidentServiceUnavailable`, `IncidentClientRejected`) and `skills_client` (`SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`) |

These exceptions carry only domain context — never HTTP status codes — so callers can decide how to translate them.

### 2. API boundary: explicit try/except → HTTPException
Routes catch domain exceptions and map them to `HTTPException(status_code=..., detail=...)`. The canonical pattern appears in `products/agent-platform/src/agent_service/api/v2/routes.py`:

```python
except SkillsDependencyNotConfigured as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from None
except SkillsServiceUnavailable as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from None
except SkillsClientRejected as exc:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
```

The same pattern is used for `Incident*` client errors, `ConfirmationNotFound`, `ConfirmationExpired`, `UnknownSessionError`, `ForeignSessionDenied`, `DigestInputError`, and `NoValidatedTriageReport`. Downstream services follow the same shape: e.g. `audit-service` routes catch `IngestAuthError` and `StoreError`; `execution-runtime` catches broad `Exception` blocks with comments like `# noqa: BLE001 — malformed bodies reject uniformly` / `durability degrades, never the response`.

### 3. Identity/auth path: early HTTPException
Authentication and authorization failures raise `HTTPException` directly at the edge, before any domain logic runs:
- `agent-platform`: missing `X-User-ID` header → `401`.
- `platform-gateway`: malformed `Authorization` header → `401`; missing token when required → `401`.
- `tool-gateway`: `resolve_request_identity` raises `401` for malformed bearer, expired/invalid tokens, or missing token when `require_auth=True`; policy deny raises `403` with `{detail, action, reason}`.

### 4. No global exception handler
A grep across all products finds **no** `@app.exception_handler` registrations. Unhandled exceptions therefore fall through to FastAPI's default JSON error response. Services rely on explicit `try/except` blocks in route handlers rather than centralized exception-to-HTTP mapping.

### 5. Startup-time validation via exceptions
Configuration parsing raises typed exceptions to fail fast:
- `incident-service.core.config.SettingsError` — "Raised when an INCIDENT_* setting is malformed (fail startup fast)."
- `tool-gateway.services.policy_engine.PolicyLoadError` — raised during YAML parse and rule validation; surfaced on the readiness endpoint as `status: degraded` with `policy_error` string.

### 6. Observability integration
Every service registers a `log_requests` middleware that logs method, path, status code, duration, and request ID. Errors are captured by this middleware; domain exceptions are not swallowed here — they bubble up to produce the final status code that gets logged.

## Conventions observed

1. **Domain exceptions stay transport-neutral.** They carry structured context (e.g. `exc.message`, `exc.detail`) but no HTTP status. Only the API layer assigns status codes.
2. **Status-code mapping is explicit per call site.** Routes contain `except X as exc:` branches that choose between 401, 403, 404, 409, 422, 502, 503 depending on the specific exception type.
3. **Downstream client errors propagate their own status.** `SkillsClientRejected` and `IncidentClientRejected` expose `status_code`/`message` attributes that the agent-platform routes forward verbatim, preserving the callee's intent.
4. **Malformed input uses 422.** Unknown model IDs and invalid payloads consistently return 422 rather than generic 400.
5. **Missing dependencies use 503.** Unconfigured downstream services (`SkillsDependencyNotConfigured`, `IncidentDependencyNotConfigured`, audit/service not configured) return 503.
6. **Readiness endpoints degrade gracefully.** `tool-gateway`'s `/ready` returns `status: degraded` with `policy_error` instead of failing hard when `PolicyLoadError` occurs.
7. **No panics/recover.** Python `raise` is used exclusively; there is no `try/finally` teardown around user code paths beyond background task cancellation in the lifespan.
8. **Request-scoped correlation.** Every error path preserves `request_id` via the `x-request-id` header resolved by `core.request_context.resolve_request_id`, which is then included in log events and audit payloads.