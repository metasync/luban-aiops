---
kind: error_handling
name: FastAPI HTTPException + Domain-Specific Exception Classes with Best-Effort Degradation
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/identity-broker/src/identity_service/api/routes/identity.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/api/routes/ingest.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - shared/shared-contracts/observability-conventions.md
---

## What system/approach is used

The platform uses a **layered error model** across all Python microservices (agent-platform, platform-gateway, identity-broker, audit-service, incident-service, skills-hub, tool-gateway):

1. **HTTP surface**: `fastapi.HTTPException` raised in route handlers to produce structured JSON responses with explicit HTTP status codes (`400`, `401`, `404`, `409`, `410`, `422`, `502`, `503`). There are no global exception handlers — each service relies on FastAPI's default exception handler.
2. **Domain layer**: Each service defines small, purpose-specific exception classes that inherit from `Exception` or `ValueError`, e.g. `StoreError`, `PolicyLoadError`, `TokenVerificationError`, `QueryAuthError`, `NormalizationError`, `TriageError`, `ConnectorConfigError`, `SettingsError`, `ProviderConfigurationError`, `UnknownModelError`, `ExchangeError`, `IngestAuthError`. These carry semantic meaning and are caught by callers before reaching the HTTP layer.
3. **Best-effort degradation**: Long-running or non-critical operations (agent state snapshots, evidence persistence, telemetry export) wrap their work in `try/except` blocks that log warnings and continue — they never raise to the caller. The agent kernel explicitly documents this pattern: "Never raises: a failed snapshot degrades durability, not the turn" and "Never raises: a failed write degrades replay parity, not the turn".
4. **Fail-open observability**: Per `shared/shared-contracts/observability-conventions.md`, OTel push is gated by `OTEL_ENABLED`; missing/misconfigured backends produce 401s at export time but the batch processor drops telemetry and setup guards initialization rather than raising. Structured logging via `configure_logging()` raises the root logger to INFO so audit records are never silently discarded.

No `panic`/`recover` equivalent exists; Python exceptions are the sole mechanism.

## Key files and packages

- `products/agent-platform/src/agent_service/runtime_kernel.py` — domain exceptions `UnknownModelError(ValueError)` and best-effort degradation for state/evidence persistence, streaming fallbacks, and provider errors surfaced as structured frames (`event: error` with `code: unknown_model`).
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError(ValueError)` for invalid provider settings.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError(Exception)` for malformed policy bundles; routes raise `HTTPException(503|502)` when downstream services are unavailable.
- `products/tool-gateway/src/tool_gateway/services/policy_engine.py` — same `PolicyLoadError` pattern mirrored in the tool gateway.
- `products/audit-service/src/audit_service/services/audit_store.py` — `StoreError(Exception)` wrapping store failures; cursor decoding wraps lower-level errors into `StoreError("invalid cursor")`.
- `products/incident-service/src/incident_service/services/*` — `StoreError`, `NormalizationError`, `TriageError`, `ConnectorConfigError`, `QueryAuthError`, `SettingsError`.
- `products/skills-hub/src/skills_hub/services/*` — `StoreError`, `QueryAuthError`, `SettingsError`.
- `products/identity-broker/src/identity_service/services/exchange_service.py` — `ExchangeError(Exception)`.
- Route layers across all services raise `HTTPException` directly (e.g. `agent_platform/api/v2/routes.py`, `platform_gateway/api/routes/audit.py`, `identity_broker/api/routes/auth.py`, `audit_service/api/routes/ingest.py`).

## Architecture and conventions

- **Per-service app bootstrap** (`app.py` in each product) installs only an HTTP middleware that logs requests with `x-request-id`, method, path, `status_code`, and duration. No custom exception handler is registered — FastAPI's built-in handler converts uncaught `HTTPException`s to JSON responses.
- **Domain exceptions stay internal**: business logic raises typed exceptions; route handlers catch them and translate to `HTTPException` with appropriate status codes. For example, `agent_platform/api/v2/routes.py` catches `ConfirmationNotFound`, `ConfirmationExpired`, `ConfirmationOwnerMismatch` and maps them to `404`, `410`, `409` respectively.
- **Downstream service failures map to 5xx**: the platform gateway translates downstream failures to `502 Bad Gateway` (service unavailable) or `503 Service Unavailable` (not configured), keeping the contract stable for callers.
- **Streaming error frames**: the agent kernel yields `{"event": "error", "code": "unknown_model", "message": ...}` frames instead of raising during streaming, so clients can handle partial streams gracefully.
- **Structured error payloads**: responses consistently use a `detail` field (FastAPI convention) or a `code`+`message` pair for streaming events.
- **No centralized error registry**: error codes and messages are defined inline near the code that produces them, not in a shared constants module.

## Conventions and constraints

- Routes must raise `HTTPException` with an explicit `status_code`; ad-hoc `JSONResponse(status_code=...)` is used sparingly (audit ingest/query routes).
- Domain-layer functions raise typed `Exception` subclasses; callers are responsible for mapping to HTTP responses.
- Non-critical side effects (state snapshots, evidence writes, telemetry export) must be wrapped in `try/except` that logs and continues — they must never propagate to the caller.
- Unknown or misconfigured external dependencies (model catalog entries, policy bundles, downstream services) fail closed with explicit 4xx/5xx responses rather than falling through to defaults.
- All services instrument request lifecycle via the same `log_event(...)` call capturing `status_code`, enabling consistent error-rate metrics without custom exception handling.