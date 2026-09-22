---
kind: error_handling
name: Structured Domain Exceptions and HTTP Status Mapping Across Services
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/platform-gateway/src/platform_gateway/api/routes/tools.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
---

## Overview

The Luban platform uses a consistent, service-local error model built on small domain exception hierarchies that are translated into FastAPI `HTTPException`s at the API boundary. There is no shared base error type across products; each product defines its own exceptions in its `services/` layer, and routes (or thin client wrappers) map them to HTTP status codes with stable, operator-facing messages.

## Exception hierarchy per service

- **agent-platform** (`products/agent-platform/src/agent_service/services/`): Each outbound dependency has a four-class hierarchy under a product-specific base:
  - `IncidentClientError` → `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`
  - `SkillsClientError` → `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`
  - `WorkerHandoffError`, `FlowKillingError` (in tests), plus domain errors like `DigestInputError`, `UnknownSessionError`, `ForeignSessionDenied`, `DevelopmentSessionRejected` in `shift_summary.py`, `ProviderConfigurationError` in `providers/base.py`, `UnknownModelError` in `runtime_kernel.py`.
  - The `IncidentClientRejected` / `SkillsClientRejected` variants carry `status_code` and `message` attributes so upstream 4xx responses can be passed through verbatim.

- **audit-service**: `StoreError`, `IngestAuthError`.
- **identity-broker**: `ExchangeError`.
- **incident-service**: `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError`.
- **platform-gateway**: `PolicyLoadError`, `TokenVerificationError`; most failures are raised directly as `HTTPException` from gateway services (`gateway_service.py`, `incident_client.py`, `skills_hub_client.py`, `tool_gateway_client.py`).
- **skills-hub**: `SettingsError`, `QueryAuthError`, `StoreError`.
- **tool-gateway**: `PolicyLoadError`, `TokenVerificationError`, `PasswordPolicyError`.

## Cross-service error contract via structured rejections

Outbound clients normalize upstream responses into a small set of domain exceptions before they reach routes. For example, `incident_client.fetch_incident_bundle` raises `IncidentDependencyNotConfigured` when configuration is missing, `IncidentServiceUnavailable` on transport or upstream 5xx, `IncidentNotFound` on 404, and `IncidentClientRejected(status_code, message)` for any other 4xx. The same pattern is used by `skills_client.validate_skill_draft`. This lets route handlers perform deterministic mapping without inspecting raw HTTP responses.

## Route-level mapping to HTTP status codes

The `agent_platform` v2 routes in `routes.py` centralize the mapping. Every call to an external dependency is wrapped in a `try/except` block that converts the service's domain exception into a stable HTTP response:

| Dependency state | HTTP status | Detail |
|---|---:|---|
| Dependency not configured | 503 | e.g. `"skills service not configured for skill-draft validation"` |
| Transport failure / upstream 5xx | 502 | e.g. `"incident service request failed"` |
| Unknown resource id | 404 | e.g. `"incident not found"`, `"document not found"`, `"unknown incident id: ..."` |
| Upstream 4xx rejection | passthrough | `exc.status_code` + `exc.message` |
| Business rule violation | 409 | e.g. `"no validated triage report to draft from — run triage first"`, `"document is already published"` |
| Validation / input shape error | 422 | e.g. `"skill target must be an absolute http(s) URL ..."`, `"recipient warning acknowledgment required"` |
| Missing auth header | 401 | `"X-User-ID header required"` |
| Expired confirmation | 410 | `"confirmation expired"` |

Other services follow the same pattern: identity-broker's `auth.py` re-raises `HTTPException(exc.status_code, exc.detail)` from token verification, and platform-gateway routes raise `HTTPException(401, "malformed authorization header")` or `"authentication required"` when identity resolution fails.

## Error propagation conventions

- **No raw tracebacks**: All documented client modules explicitly state that errors surface as a structured hierarchy so callers map them to the house posture — never a raw traceback. Raw `httpx.HTTPError` is caught inside clients and re-raised as a domain exception.
- **`from None` vs `from exc`**: Configuration and transport failures use `raise HTTPException(...) from None` to suppress the Python traceback chain. Resource-not-found and business-rule violations preserve the original exception with `from exc` so the caller stack is visible in logs.
- **Upstream 4xx passthrough**: When a downstream service returns a 4xx, the client wraps it in a `*ClientRejected(status_code, message)` exception and the route re-emits it unchanged, preserving the downstream semantics.
- **Secret delivery hardening**: In `platform_gateway/api/routes/tools.py`, secret redemption catches `HTTPException` and normalizes all failure paths to `JSONResponse(status_code=..., content={"detail": "Secret delivery unavailable"})`, deliberately hiding the underlying cause from callers.

## Domain vs infrastructure errors

Infrastructure problems (missing config, network failure, upstream 5xx) are distinguished from domain/business errors (unknown session, duplicate publication, expired confirmation). Infrastructure errors get 502/503 so operators know the platform is degraded; domain errors get 4xx so callers can distinguish user mistakes from outages.

## Where there is no centralized system

There is no global middleware, no shared `ErrorResponse` schema, and no repository-wide error code enum. Each product owns its exception classes and its own route-level mapping. The only cross-cutting convention is the 503/502/4xx distinction described above and the use of FastAPI `HTTPException` as the wire representation.