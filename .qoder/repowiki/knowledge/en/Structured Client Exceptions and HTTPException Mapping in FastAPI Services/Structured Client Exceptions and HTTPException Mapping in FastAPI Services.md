---
kind: error_handling
name: Structured Client Exceptions and HTTPException Mapping in FastAPI Services
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/incident-service/src/incident_service/services/triage.py
---

## Overview

The Luban platform uses a consistent, per-service error-handling pattern across its Python FastAPI services. Errors are modeled as typed exception hierarchies at the service boundary (client layers), then mapped to standardized HTTP status codes in route handlers. There is no global `@app.exception_handler` — each service relies on FastAPI's default HTTPException handling after explicit mapping.

## Exception Hierarchy Pattern

Each outbound client defines a small, documented hierarchy rooted in a service-specific base `Exception`:

- **agent-platform**
  - `ProviderConfigurationError(ValueError)` in `providers/base.py`
  - `UnknownModelError(ValueError)` in `runtime_kernel.py`
  - `WorkerHandoffError(Exception)`, `IncidentClientError`, `SkillsClientError`, `DigestInputError`, `UnknownSessionError` in their respective service modules
  - `ConfirmationNotFound(LookupError)` in `services/hitl_confirmations.py`

- **incident-service**: `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError`
- **audit-service**: `StoreError`, `IngestAuthError`
- **identity-broker**: `ExchangeError`
- **platform-gateway**: `PolicyLoadError`, `TokenVerificationError`
- **tool-gateway**: `PolicyLoadError`, `TokenVerificationError`
- **skills-hub**: `SettingsError`, `QueryAuthError`, `StoreError`

These exceptions carry structured attributes (`status_code`, `message`, `incident_id`) rather than raw tracebacks, so callers can inspect them for routing decisions.

## Outbound Client Error Mapping

Clients that call other services (e.g. `agent_service/services/skills_client.py`, `agent_service/services/incident_client.py`) translate HTTP responses into this hierarchy uniformly:

| Condition | Exception raised | Route-level mapping |
|---|---|---|
| Dependency not configured (missing URL/secret) | `<Service>DependencyNotConfigured` | `HTTPException(503, detail=...)` |
| Transport failure or upstream 5xx | `<Service>ServiceUnavailable` | `HTTPException(502, detail=str(exc)) from None` |
| Upstream 4xx | `<Service>ClientRejected(status_code, message)` | `HTTPException(exc.status_code, detail=exc.message) from None` |
| Specific resource missing (e.g. 404) | `<Service>NotFound` | `HTTPException(404, detail=...) from exc` |

This is enforced by the client module docstrings (e.g. "Errors surface as a small structured hierarchy so the generation route maps them to the house posture — 503 when the dependency is not configured, 502 on transport failure or upstream 5xx — and an unvalidated draft is never returned") and consistently applied in every route that calls these clients.

## Route-Level Handling

Routes raise `fastapi.HTTPException` directly with explicit `status_code` and `detail` strings. Examples include:
- `401` for missing `X-User-ID` header
- `409` for conflict / expired confirmation / no validated triage report
- `410` for expired confirmations
- `422` for validation failures
- `503` for unconfigured dependencies
- `502` for upstream failures
- `404` for missing sessions/incidents

There are no custom exception handler registrations anywhere in the codebase; the project relies on FastAPI's built-in HTTPException serialization.

## Policy Engine Validation Errors

The policy engines in both `platform-gateway` and `tool-gateway` define a `PolicyLoadError` raised during bundle parsing/validation. This is a load-time concern: malformed YAML, invalid rule shapes, unknown outcomes, or disallowed approval configurations all raise `PolicyLoadError` with a human-readable message indicating the offending rule id and source. These errors propagate up to the caller (policy loading endpoint) rather than being caught inside the engine.

## Middleware and Observability

Services register an `http` middleware that wraps every request, captures `x-request-id`, measures duration, and emits a structured `http_request` event via `log_event`. The middleware logs the final `response.status_code`, which is how errors are observed end-to-end. No middleware catches or rewrites exceptions — it only observes.

## Conventions Observed

1. **Never expose raw tracebacks**: client-layer exceptions wrap underlying `httpx` errors and strip stack traces before reaching routes.
2. **Status-code semantics are stable**: 503 = dependency not configured; 502 = transport/upstream server error; 4xx from upstream are passed through verbatim.
3. **Structured attributes over string messages**: `ClientRejected` stores both `status_code` and `message` so routes can map without parsing text.
4. **No global exception handlers**: each route handles its own domain exceptions and converts them to `HTTPException`.
5. **Policy bundle validation fails fast**: `PolicyLoadError` is raised during bundle parse/load, not at decision time.
6. **Request context propagation**: `x-request-id` is threaded through middleware and included in outbound client requests for tracing.