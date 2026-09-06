---
kind: error_handling
name: FastAPI HTTPException + domain-specific Exception classes with per-service auth error types
category: error_handling
scope:
    - '**'
source_files:
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/audit-service/src/audit_service/api/routes/ingest.py
    - products/audit-service/src/audit_service/api/routes/export.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/incident-service/src/incident_service/services/normalization.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/platform-gateway/src/platform_gateway/api/routes/auth.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
---

## Overview

The Luban AIOps platform is a multi-product Python workspace (agent-platform, platform-gateway, tool-gateway, audit-service, incident-service, identity-broker, skills-hub) built on FastAPI. Error handling follows a consistent pattern: business-layer code raises typed `Exception` subclasses that are caught at the API boundary and translated into HTTP responses via `fastapi.HTTPException` or `starlette.responses.JSONResponse`. There is no centralized exception-to-HTTP middleware; each service's route handlers perform the translation themselves.

## Domain-specific exception classes

Each product defines small, purpose-built exception classes in its `services/` layer:

- **tool-gateway**: `PolicyLoadError` (`services/policy_engine.py`) raised when a policy bundle YAML is invalid or misconfigured; `TokenVerificationError` (`services/token_verifier.py`) raised for any JWT verification failure (expired, wrong issuer/audience, malformed).
- **audit-service**: `IngestAuthError` (`services/ingest_auth.py`), `StoreError` (`services/audit_store.py`).
- **incident-service**: `QueryAuthError` (`services/query_auth.py`), `NormalizationError` (`services/normalization.py`), `ConnectorConfigError` (`services/connectors.py`), `StoreError` (`services/incident_store.py`), `TriageError` (`services/triage.py`), `SettingsError` (`core/config.py`).
- **skills-hub**: `QueryAuthError` (`services/query_auth.py`), `StoreError` (`services/skill_store.py`), `SettingsError` (`core/config.py`).
- **identity-broker**: `ExchangeError` (`services/exchange_service.py`).
- **platform-gateway**: uses the shared-contract `TokenVerificationError` from `platform_gateway.services.token_verifier`.

These exceptions carry human-readable messages (often strings) and are never exposed directly to clients — they are always wrapped in an HTTP response at the route layer.

## Authentication error handling

Authentication failures follow a uniform shape across services. The `authenticate_caller` functions in `audit_service/services/ingest_auth.py`, `incident_service/services/query_auth.py`, and `skills_hub/services/query_auth.py` all raise their respective `*AuthError` exceptions for missing credentials, invalid Basic auth, expired tokens, unknown workload subjects, etc. Route handlers catch these and return `JSONResponse(status_code=401, content={"detail": str(exc)})` — e.g. `audit_service/api/routes/ingest.py`, `audit_service/api/routes/query.py`, `incident_service/api/routes/incidents.py`, `skills_hub/api/routes/skills.py`. The platform-gateway's `/api/v1/auth/me` endpoint takes a slightly different approach: it catches `TokenVerificationError` and returns `{"authenticated": False}` rather than a 401, because this is an introspection endpoint.

## Upstream / dependency errors

When a gateway proxies calls to downstream services, failures are normalized to stable status codes:

- `httpx.HTTPError` during outbound calls → `HTTPException(status_code=502, detail="... unavailable")` (see `platform_gateway/api/routes/audit.py`, lines 111–124, 166–176, 220–230).
- Downstream 4xx client errors are passed through unchanged so operators can distinguish bad requests from outages (lines 119–123 of the same file).
- Downstream 5xx errors are collapsed to 502.
- Missing configuration is surfaced as 503 (e.g. `HTTPException(status_code=503, detail="audit service not configured")` in multiple routes).

The agent-platform skill-draft validation path (`products/agent-platform/src/agent_service/api/v2/routes.py`, `_validate_skill_markdown`) maps three custom exceptions consistently: `SkillsDependencyNotConfigured` → 503, `SkillsServiceUnavailable` → 502, `SkillsClientRejected` → pass-through `exc.status_code`.

## Validation and request-level errors

FastAPI's built-in request validation is used alongside explicit checks. When input fails validation, `HTTPException(status_code=422, ...)` is raised (e.g. session title length check). Malformed JSON bodies return 400 with a `detail` string (seen in `audit_service/api/routes/ingest.py`).

## Policy evaluation errors

The tool-gateway's policy engine (`services/policy_engine.py`) implements deny-by-default evaluation. Invalid policy bundles raise `PolicyLoadError` with a message identifying the offending rule and source. Load-time validation rejects unknown outcomes, malformed approval blocks, and non-bridged `require_approval` actions (logged as warnings and skipped per SPEC-030 R-2). At runtime, `evaluate()` returns a `PolicyDecision` dataclass rather than raising — only load-time problems propagate as exceptions.

## Response construction patterns

Two response styles coexist:

1. **FastAPI `HTTPException`** — used by agent-platform, platform-gateway, tool-gateway, and identity-broker routes. It integrates with FastAPI's default error handler and produces a JSON body with `status_code` and `detail`.
2. **Starlette `JSONResponse`** — used by audit-service, incident-service, and skills-hub routes, returning `JSONResponse(status_code=..., content={"detail": ...})`. This bypasses FastAPI's exception machinery but yields the same wire format.

Some tool-gateway policy-denial paths return `JSONResponse(content=result.to_dict(), status_code=403)` directly instead of raising, which is a deliberate choice to keep policy decisions structured rather than opaque error messages.

## Conventions observed

- Exceptions are defined close to the code that raises them (in the same `services/` module), not in a shared `errors/` package.
- Each service has its own exception namespace — there is no cross-service exception sharing except where a shared contract type (like `TokenVerificationError`) is reused.
- Route handlers are responsible for translating exceptions to HTTP status codes; there is no global exception handler registered in the examined services.
- Outbound network failures are consistently mapped to 502, missing configuration to 503, authentication failures to 401, and policy denials to 403.
- Structured error payloads use a `detail` field carrying a human-readable string.
- Token verification failures are caught individually (`ExpiredSignatureError`, `InvalidIssuerError`, `InvalidAudienceError`, `InvalidTokenError`) and re-raised as the service's domain exception with a specific message, preserving the original exception via `from exc`.