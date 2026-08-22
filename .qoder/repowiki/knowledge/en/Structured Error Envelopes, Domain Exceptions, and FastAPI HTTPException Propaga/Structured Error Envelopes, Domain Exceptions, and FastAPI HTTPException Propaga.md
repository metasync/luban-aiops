---
kind: error_handling
name: Structured Error Envelopes, Domain Exceptions, and FastAPI HTTPException Propagation
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - shared/shared-contracts/schemas/tool-result.schema.json
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/agent-platform/src/agent_service/app.py
---

## Overview

The Luban Agentic AIOps platform uses a layered error-handling strategy across its Python microservices (agent-platform, platform-gateway, tool-gateway, identity-broker, audit-service, incident-service, skills-hub). Errors are expressed as domain-specific exception classes within each service, propagated up to the API layer where they are translated into HTTP responses. For tool invocations, errors are returned as structured JSON envelopes defined by shared JSON Schema contracts rather than HTTP exceptions.

## Domain Exception Classes

Each service defines small, purpose-built exception classes in its `services/` or `core/` modules:

- **agent-platform**: `ProviderConfigurationError(ValueError)` for invalid provider settings (`providers/base.py`).
- **platform-gateway**: `PolicyLoadError`, `TokenVerificationError` (`policy_engine.py`, `token_verifier.py`).
- **tool-gateway**: `PolicyLoadError`, `TokenVerificationError` (mirrored under `tool_gateway/services/`).
- **identity-broker**: `ExchangeError` (`exchange_service.py`).
- **audit-service**: `StoreError`, `IngestAuthError`.
- **incident-service**: `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError`.
- **skills-hub**: `SettingsError`, `QueryAuthError`, `StoreError`.

These exceptions are raised deep in service logic and caught at the boundary (routes or gateway service functions) where they are converted to user-facing responses.

## HTTP Layer: FastAPI + `HTTPException`

All services use FastAPI. There is no global exception handler registered — instead, routes and gateway service functions raise `fastapi.HTTPException` with explicit `status_code` and `detail` payloads. Common patterns observed:

- **401 Unauthorized**: raised when authentication is missing, malformed, or token verification fails (e.g., `resolve_request_identity` in both gateways raises 401 on missing/malformed bearer tokens; `TokenVerificationError` is mapped to 401).
- **403 Forbidden**: raised by policy enforcement (`enforce_policy`) when the policy engine returns `deny`; includes `{"detail": "action denied by policy", "action": ..., "reason": ...}`.
- **404 Not Found**: used for missing confirmations in agent-service v2 routes.
- **409 Conflict**: used for duplicate session creation in agent-service.
- **410 Gone**: used for expired confirmations.
- **502 Bad Gateway**: upstream failures from `httpx` calls in the platform-gateway's `chat_confirm` path map non-4xx upstream errors to 502, while preserving 4xx client errors unchanged so operators can distinguish upstream rejections from outages.

The FastAPI app factories (`app.py` in each product) register only an HTTP request logging middleware that records `method`, `path`, `status_code`, and `duration_ms`. No custom exception handler overrides FastAPI's default JSON error response shape.

## Structured Tool Result Envelope

Tool invocations do not return HTTP exceptions directly. Instead, every tool result conforms to `shared/shared-contracts/schemas/tool-result.schema.json`, which defines a uniform envelope with fields `tool_name`, `status` (enum: `success`, `error`, `denied`), `data`, `evidence`, and `error` (with required `code` and `message`).

The `tool_gateway/tools/base.py` module provides factory helpers:
- `make_error_result(tool_name, code, message, risk_level, source_system, duration_ms)` — produces a `ToolResult` with `status="error"`.
- `make_denied_result(tool_name, reason, risk_level)` — produces a `ToolResult` with `status="denied"` and `error.code = "POLICY_DENIED"`.

The `ToolRegistry.invoke` path wraps tool execution results through this envelope. The gateway maps `status == "success"` → HTTP 200, `status == "denied"` → HTTP 403, otherwise → HTTP 400. Redaction overflow is treated as an error result with code `REDACTION_OVERFLOW` rather than raising.

## Upstream Failure Isolation

The incident-service connector framework (`connectors.py`) demonstrates a deliberate isolation pattern: dispatch failures are caught with a broad `except Exception` (explicitly marked with `# noqa: BLE001 - isolation by design`) and recorded as `ConnectorOutcome(status="failed")` without aborting the triage flow. This ensures external collaboration sinks (Slack, Jira, ...) cannot turn a successful triage into a failure.

Similarly, readiness probes in both gateways catch `PolicyLoadError` and `httpx.HTTPError` and return `status: "degraded"` rather than failing the health check entirely.

## Cross-Cutting Conventions

1. **Request-scoped context**: Every route receives a `request_id` (via `x-request-id` header resolved by `core.request_context.resolve_request_id`) and logs it in all error paths via structured log events (`log_event` / `LOGGER.info(..., extra={"request_id": ...})`).
2. **Audit trail mirroring**: Policy denials and tool invocations emit durable audit events via `emit_audit_event` before returning any error response, ensuring the audit trail is independent of the caller-visible response.
3. **Metrics instrumentation**: Token verification outcomes (`valid`, `invalid`, `expired`, `missing`) and policy decisions (`allow`, `deny`) are recorded through per-service `metrics.record_*` functions before raising or returning errors.
4. **No panics/recover**: Python `raise` is used exclusively; there are no `try/except` blocks around top-level entry points attempting to recover from unexpected exceptions. Failures propagate to FastAPI's default handler.
5. **Service boundaries**: Each product owns its own exception types — there is no shared `errors` package. Cross-service communication errors are represented as HTTP status codes (401/403/404/409/410/502) plus structured `detail` bodies, never as serialized domain exceptions.