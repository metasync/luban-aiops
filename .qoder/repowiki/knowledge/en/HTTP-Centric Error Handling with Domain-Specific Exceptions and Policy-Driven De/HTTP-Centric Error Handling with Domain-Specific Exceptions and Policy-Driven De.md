---
kind: error_handling
name: HTTP-Centric Error Handling with Domain-Specific Exceptions and Policy-Driven Denials
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/audit-service/src/audit_service/api/routes/ingest.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
    - shared/shared-contracts/schemas/policy-decision.schema.json
---

# Error Handling in the Agentic AIOps Platform

## Overview

The platform uses a **FastAPI-based HTTP error model** across all Python services (agent-platform, platform-gateway, tool-gateway, identity-broker, audit-service, incident-service, skills-hub). There is no centralized exception-to-HTTP mapping middleware; instead, each service's route handlers and service-layer functions raise `fastapi.HTTPException` directly or return `JSONResponse` with explicit status codes. Domain-level failures are represented by small, purpose-specific Python exceptions that callers translate to appropriate HTTP responses.

## Core Patterns Observed

### 1. FastAPI HTTPException at API Boundaries

Every product service raises `fastapi.HTTPException` from its route handlers or thin service wrappers:

- **Authentication failures**: 401 with `detail="authentication required"`, `"malformed authorization header"`, `"missing Authorization header"`, or `"token refresh failed"` (identity-broker, tool-gateway, platform-gateway).
- **Authorization/policy denials**: 403 with a structured detail containing `action`, `reason`, and `matched_rule_ids` (platform-gateway, tool-gateway).
- **Client validation errors**: 422 for unknown model IDs (`"unknown model id: ..."`) and 400/422 for malformed request bodies (audit-service ingest/query routes).
- **Resource conflicts**: 409 for parked confirmation states and concurrent session operations (agent-platform v2 routes).
- **Not found / expired**: 404 for missing sessions/confirmations; 410 for expired confirmations (agent-platform).
- **Upstream proxy failures**: 502 with descriptive details like `"agent service unavailable"` or `"agent service chat stream failed"` when the platform-gateway proxies fail over httpx (platform-gateway gateway_service.py).

### 2. Domain-Specific Exception Classes

Each service defines small, named exception classes in their service layers rather than using generic `Exception`:

| Service | Exception Class | Purpose |
|---------|----------------|---------|
| agent-platform | `ProviderConfigurationError(ValueError)` | Invalid provider config |
| agent-platform | `UnknownModelError(ValueError)` | Model not in catalog |
| agent-platform | `ConfirmationNotFound`, `ConfirmationExpired`, `ConfirmationOwnerMismatch` | HITL confirmation state machine |
| platform-gateway | `PolicyLoadError(Exception)` | Invalid/unreadable policy bundle |
| platform-gateway | `TokenVerificationError(Exception)` | JWT verification failure |
| tool-gateway | `PolicyLoadError(Exception)` | Invalid policy bundle |
| tool-gateway | `TokenVerificationError(Exception)` | JWT verification failure |
| audit-service | `StoreError(Exception)`, `IngestAuthError(Exception)` | Store/auth failures |
| incident-service | `SettingsError`, `ConnectorConfigError`, `NormalizationError`, `TriageError`, `QueryAuthError`, `StoreError` | Domain failures |
| identity-broker | `ExchangeError(Exception)` | OIDC token exchange failure |
| skills-hub | `SettingsError`, `StoreError`, `QueryAuthError` | Domain failures |

These domain exceptions are caught at the boundary and translated into HTTP responses — they do not leak through the HTTP layer.

### 3. Policy Enforcement as an Error Source

Both the platform-gateway and tool-gateway implement **deny-by-default policy evaluation** via a shared contract (`shared/shared-contracts/schemas/policy-decision.schema.json`). The `evaluate()` function returns a `PolicyDecision` dataclass with fields `decision`, `matched_rule_ids`, `reason`, plus optional `action` and `subject`. When `decision == "deny"`, the caller raises `HTTPException(status_code=403, detail={...})` and emits an audit event. This makes policy denial a first-class error path, indistinguishable from other authorization failures at the HTTP level but fully auditable.

### 4. Upstream Proxy Error Posture

The platform-gateway consistently applies this rule when proxying to the agent-service:

- Upstream `4xx` status codes pass through unchanged (preserving client-facing semantics like 404 unknown session, 409 parked confirmation, 422 unknown model).
- Upstream `5xx` and transport errors map to `502 Bad Gateway` with a uniform `"agent service ... failed"` detail.
- Non-HTTP `httpx.HTTPError` maps to `502 "agent service unavailable"`.

This gives clients a stable surface: business errors come from the agent-service, infrastructure errors come from the gateway.

### 5. Streaming Error Handling

For SSE streams (`/chat/stream`, `/chat/confirm`), errors cannot be returned as HTTP status codes after headers are sent. Instead:

- Pre-stream validation (model resolution, session lookup, parked-session check) raises `HTTPException` before the response opens.
- Mid-stream errors (e.g., `ConfirmationOwnerMismatch`) are emitted as typed `AgentStreamEvent` frames of type `"error"` carrying `{code, message}`.
- Stream consumers can distinguish between normal termination and error frames.

### 6. Health and Readiness as Degradation Signals

Services expose `live_status` (always returns `ok`) and `ready_status` endpoints. Readiness checks attempt critical dependencies (policy bundle load, downstream health) and return `status: "degraded"` with an error field instead of raising — e.g., `policy_error` or `agent_service_error`. This lets orchestrators detect partial failure without crashing.

### 7. Observability Integration

Errors are consistently logged via a structured `log_event` helper with `request_id`, `service`, `method`, `path`, `status_code`, and `duration_ms` fields. Policy decisions are additionally emitted as durable audit events via `emit_audit_event`, creating a parallel audit trail independent of application logs.

## Conventions and Constraints

- **No global exception handler**: Each service builds its own FastAPI app without registering a custom `@app.exception_handler`; FastAPI's default JSON error response is used.
- **Status code discipline**: 401 for auth, 403 for policy deny, 404 for missing resources, 409 for conflicts, 410 for expired state, 422 for validation, 502 for upstream failures. These are enforced by repeated patterns across services.
- **Domain exceptions stay internal**: Service-layer exceptions are never raised from route handlers; they are always caught and converted to HTTP responses.
- **Audit parity**: Every policy denial and tool invocation is mirrored to the audit service regardless of success/failure, ensuring errors are observable outside the process.
- **Streaming safety**: Unknown or unexpected stream frames degrade to safe defaults (e.g., unrecognized event types become `message_delta`) rather than raising, preventing stream crashes.
- **No panics/recover**: Python has no panic mechanism; unhandled exceptions propagate to FastAPI's default error handler, which returns a 500 JSON body. No `try/except Exception` catch-all exists at the app level.

## Key Files

- `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — proxy error posture, policy enforcement, streaming error handling
- `products/tool-gateway/src/tool_gateway/services/gateway_service.py` — tool invocation error flow, redaction overflow error
- `products/agent-platform/src/agent_service/api/v2/routes.py` — HITL confirmation errors, model resolution errors, session conflict errors
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError`, `PolicyRule`, `PolicyDecision`
- `products/tool-gateway/src/tool_gateway/services/policy_engine.py` — duplicate policy engine with `PolicyLoadError`
- `products/identity-broker/src/identity_service/api/routes/auth.py` — OIDC exchange error mapping
- `products/audit-service/src/audit_service/api/routes/ingest.py` — JSON parse and batch validation errors
- `shared/shared-contracts/schemas/policy-decision.schema.json` — canonical policy decision shape
- `products/agent-platform/src/agent_service/app.py` — HTTP request logging middleware (no error handler)

## Applicable Scope

This pattern applies uniformly across all Python services in the monorepo. The web portal (`operator-portal/web-ui`) is a separate TypeScript/Vite frontend and does not participate in this Python error model.