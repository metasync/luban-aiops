---
kind: error_handling
name: 'Error Handling: FastAPI HTTPException, Domain-Specific Exceptions, and Policy-Driven Denials'
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/identity-broker/src/identity_service/api/routes/identity.py
    - products/identity-broker/src/identity_service/services/token_service.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
---

## What system/approach is used

The codebase uses a layered error-handling strategy built on **FastAPI's `HTTPException`** for API-layer errors and **domain-specific Python exceptions** (custom subclasses of `ValueError`, `Exception`) for internal service logic. There is no centralized exception-to-JSON mapper or global `@app.exception_handler`; instead, each product service raises `HTTPException(status_code=..., detail=...)` directly from route handlers and middleware, relying on FastAPI's default JSON error response shape (`{"detail": ...}`) plus the standard HTTP status code.

For non-API internals, services define small, purpose-specific exception classes (e.g. `ProviderConfigurationError`, `UnknownModelError`, `PolicyLoadError`, `TokenVerificationError`, `StoreError`, `ConnectorConfigError`, `NormalizationError`, `QueryAuthError`, `TriageError`, `ExchangeError`, `SettingsError`, `WorkerHandoffError`, `IngestAuthError`). These are raised within service layers and caught by callers that translate them into either structured return values (tool results) or `HTTPException`s at the boundary.

There is no `panic`/`recover` equivalent in Python; startup-time failures (e.g. invalid policy bundles, missing config) raise exceptions during module import or `create_app()` setup, which crash the process — an intentional fail-fast posture.

## Key files and packages

- **Agent Platform**: `products/agent-platform/src/agent_service/providers/base.py` defines `ProviderConfigurationError`; `runtime_kernel.py` defines `UnknownModelError`; routes in `api/v2/routes.py` raise `HTTPException` with codes 401, 404, 409, 410, 422.
- **Platform Gateway**: `services/policy_engine.py` defines `PolicyLoadError` and returns typed `PolicyDecision` dataclasses (`allow` / `deny` / `require_approval`); `gateway_service.py` translates deny decisions to `HTTPException(403)` and token verification failures to `HTTPException(401)`.
- **Tool Gateway**: `services/gateway_service.py` centralizes auth + policy enforcement, raising `HTTPException(401)` for malformed/missing tokens and `HTTPException(403)` for policy denials; tool execution returns structured `tool-result` JSON with `status` fields (`success`, `denied`, `error`) rather than HTTP exceptions internally.
- **Identity Broker**: `services/token_service.py` issues JWTs; routes raise `HTTPException(401)` for missing/malformed authorization headers and token refresh failures.
- **Audit / Incident / Skills services**: Each defines domain exceptions (`StoreError`, `ConnectorConfigError`, `NormalizationError`, `QueryAuthError`, `TriageError`, `SettingsError`, `QueryAuthError`, `StoreError`) under their respective `services/` modules.

## Architecture and conventions

1. **API boundary = `HTTPException`**: Every public-facing route converts business errors into `fastapi.HTTPException` with an explicit `status_code` and a human-readable `detail` string. Common codes observed: 401 (unauthenticated / bad token), 403 (policy denied), 404 (not found), 409 (conflict / duplicate session), 410 (confirmation expired), 422 (validation).

2. **Domain layer = custom exceptions**: Internal validation and configuration errors use small, named exception classes (e.g. `ProviderConfigurationError(ValueError)`, `PolicyLoadError(Exception)`, `TokenVerificationError(Exception)`). This lets callers distinguish between "bad input", "misconfiguration", and "downstream failure" without parsing strings.

3. **Policy-driven denials are first-class**: The gateway services model access control as a three-way decision (`allow`, `deny`, `require_approval`) returned by `evaluate()`. A deny becomes `HTTPException(403)` with a structured `detail` containing `action`, `reason`, and `matched_rule_ids`. A `require_approval` decision is propagated up the call stack (not converted to an HTTP error) so the caller can bridge it to the HITL confirmation flow.

4. **Tool results use structured payloads, not exceptions**: Tool invocations return a `tool-result` schema object with a `status` field (`success`, `denied`, `error`) and an `evidence` block carrying `duration_ms`, `risk_level`, etc. Errors inside tools are represented as result objects, not raised exceptions, allowing the gateway to redact output before returning it.

5. **No global exception handler**: Services set up logging, metrics, and telemetry via `core/observability.py` and `core/telemetry.py`, but none register a custom `@app.exception_handler`. Error responses therefore follow FastAPI's default JSON format.

6. **Startup failures are fatal**: Invalid policy bundles, missing signing keys, or misconfigured settings raise exceptions at import/startup time (e.g. `PolicyLoadError` from `load_bundle`, `RuntimeError` from runtime entrypoints). This enforces a fail-fast deployment posture — a misconfigured service does not start serving requests.

7. **Audit trail for errors**: Denial and error paths emit audit events through `audit_emitter.emit_audit_event(...)` with `decision="deny"` or `status="error"`, ensuring errors are persisted independently of the HTTP response.

## Conventions and constraints

- **Every route must map errors to HTTP status codes** — observed consistently across agent-platform, platform-gateway, identity-broker, and tool-gateway routes; there is no catch-all handler to rely on.
- **Policy engine outcomes are immutable dataclasses**, not exceptions — `PolicyDecision` carries `decision`, `matched_rule_ids`, `reason`, and optional `approval`; callers match on `.decision` rather than catching exceptions.
- **Authentication errors always use 401**; authorization/policy denials always use 403; resource-not-found uses 404; conflicts use 409; validation errors use 422; expired confirmations use 410.
- **Custom exceptions are narrow and local** to their service package — they are not re-raised across service boundaries as HTTP errors; cross-service calls serialize errors into shared schemas defined under `shared/shared-contracts/schemas/`.
- **Redaction overflow is treated as a controlled error**: when tool output exceeds redaction thresholds, the gateway returns a `make_error_result` with code `REDACTION_OVERFLOW` instead of leaking credentials, and logs a warning with the redacted fraction.
- **Tests exercise error paths explicitly**: test files such as `test_policy_enforcement.py`, `test_gateway_auth.py`, `test_execution_signing.py`, `test_token_verifier.py`, `test_contracts.py` assert both success and failure branches, confirming the expected status codes and error shapes.