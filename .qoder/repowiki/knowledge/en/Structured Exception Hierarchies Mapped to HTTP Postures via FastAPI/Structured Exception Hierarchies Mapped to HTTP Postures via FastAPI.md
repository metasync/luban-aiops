---
kind: error_handling
name: Structured Exception Hierarchies Mapped to HTTP Postures via FastAPI
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/core/dependencies.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/incident-service/src/incident_service/services/triage.py
---

## Overview

The Luban platform uses a consistent, layered error-handling model across all Python services (agent-platform, platform-gateway, tool-gateway, audit-service, identity-broker, incident-service, skills-hub). Errors are expressed as typed Python exceptions with small domain-specific hierarchies, and the API layer translates them into structured FastAPI `HTTPException` responses. There is no global exception handler registered; instead, each route or service function explicitly catches lower-level exceptions and re-raises them as HTTP errors with a well-defined status code and detail string.

## Exception Hierarchy Pattern

Each service defines a small base exception plus specialized subclasses that encode the failure mode:

- **Agent Platform** (`agent_service/`): `ProviderConfigurationError(ValueError)` for invalid provider settings; `UnknownModelError(ValueError)` in `runtime_kernel.py`; per-client hierarchies such as `IncidentClientError` → `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`; similarly `SkillsClientError` → `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`; `WorkerHandoffError`, `DigestInputError`, `UnknownSessionError`, `FlowKillingErrorCodesTests`.
- **Platform Gateway** (`platform_gateway/`): `PolicyLoadError(Exception)`, `TokenVerificationError(Exception)` with a `detail` attribute; `_identity_leg` in `gateway_service.py` wraps downstream calls so 4xx pass through and any transport / 5xx becomes a 502.
- **Tool Gateway** (`tool_gateway/`): connector-specific not-configured errors (e.g. `ElasticConnectorNotConfigured`, `K8sConnectorNotConfigured`) surfaced by connectors and caught at the route layer.
- **Audit / Identity / Incident / Skills Hub**: each has its own `StoreError`, `IngestAuthError`, `ExchangeError`, `SettingsError`, `QueryAuthError`, `NormalizationError`, `TriageError`, `ConnectorConfigError` — one base per subsystem.

The hierarchy is deliberately shallow: a base class groups related failures, and leaf classes carry enough context (status code, message, detail) for the caller to map to an HTTP response without inspecting strings.

## HTTP Posture Mapping

Routes consistently translate exceptions into these HTTP postures:

| Failure category | HTTP status | Example source |
|---|---:|---|
| Missing auth header / unauthorized | 401 | `routes.py` raises `HTTPException(401, "X-User-ID header required")` |
| Validation / malformed input | 400–422 | `422` for unknown model id; `400` for title length validation |
| Conflict (pending confirmation, parked session) | 409 | Confirmation-pending and session-has-parked-confirmation checks |
| Not found (session, incident, confirmation) | 404 | Explicit `"session not found"`, `"incident not found"`, `"confirmation not found"` |
| Expired confirmation | 410 | `"confirmation expired"` |
| Dependency not configured (skills/incidents client missing URL/secret) | 503 | `SkillsDependencyNotConfigured`, `IncidentDependencyNotConfigured` mapped to 503 |
| Upstream transport failure / 5xx from peer service | 502 | `httpx.HTTPError` / upstream 5xx wrapped as 502 with human-readable detail |
| Upstream 4xx from peer service | passthrough | `SkillsClientRejected.status_code` forwarded verbatim |
| Internal server error | 500 | Default FastAPI behavior when no explicit mapping exists |

The mapping is enforced at call sites rather than via middleware. For example, `_validate_skill_markdown` in `agent_service/api/v2/routes.py` catches `SkillsDependencyNotConfigured` → 503, `SkillsServiceUnavailable` → 502, `SkillsClientRejected` → pass-through status, and guarantees an unvalidated draft is never returned.

## Cross-Service Error Propagation

Services that call other services wrap the outbound call in a try/except block that normalizes the response:

- `platform_gateway/services/gateway_service.py::_identity_leg` catches `httpx.HTTPStatusError` (4xx pass through with extracted `detail`, 5xx become 502), and generic `httpx.HTTPError` (transport failure → 502).
- `agent_service/services/skills_client.py::validate_skill_draft` catches `httpx.HTTPError` → `SkillsServiceUnavailable`, then branches on `response.status_code >= 500` vs `< 500` to raise `SkillsServiceUnavailable` or `SkillsClientRejected(status_code, message)`.
- `agent_service/services/incident_client.py` follows the same pattern with `Incident*` exceptions.

This means callers only need to handle the domain exception types; they never see raw `httpx` errors.

## Configuration and Startup Errors

Configuration loading is defensive: `core/config.py` files in multiple services parse environment variables and raise `SettingsError` (or `ValueError`) when values are missing or malformed. The `ready_status` endpoint in the platform gateway catches `PolicyLoadError` and reports `status: degraded` rather than failing the health check outright.

## Telemetry and Non-Functional Error Handling

Telemetry modules (`core/telemetry.py` in every product) wrap async export calls in `try/except Exception:` blocks that log and swallow failures. This ensures observability instrumentation never causes request failures — telemetry errors degrade silently.

## Conventions Observed

1. **No global exception handler**: Each route/service function performs explicit catch-and-map; there are no `@app.exception_handler` decorators anywhere in the codebase.
2. **Domain exceptions stay below the API layer**: Services return typed exceptions; routes convert them to `HTTPException`.
3. **Structured client errors carry metadata**: Rejection exceptions store `status_code` and `message` attributes so callers can forward the exact upstream posture.
4. **Unconfigured dependencies answer 503, not 4xx**: A missing URL/secret is treated as a service availability problem, not a client error.
5. **Upstream 5xx are always normalized to 502**: Callers never expose raw 5xx from peers directly to clients.
6. **Upstream 4xx are passed through**: Client-facing semantics (validation, not-found) are preserved across service boundaries.
7. **Never return unvalidated artifacts**: Draft-generation paths guarantee format validation before returning content; second failure degrades to a skeleton, third failure answers 502.
8. **Telemetry failures are fire-and-forget**: Instrumentation swallows exceptions so they cannot affect request outcomes.