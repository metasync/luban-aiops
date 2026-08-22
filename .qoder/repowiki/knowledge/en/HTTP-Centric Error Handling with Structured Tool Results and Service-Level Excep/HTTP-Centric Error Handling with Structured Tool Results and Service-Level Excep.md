---
kind: error_handling
name: HTTP-Centric Error Handling with Structured Tool Results and Service-Level Exceptions
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/app.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/platform-gateway/src/platform-gateway/api/routes/auth.py
    - products/platform-gateway/src/platform-gateway/api/routes/tools.py
    - products/agent-platform/src/agent_service/app.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/session_service.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/identity-broker/src/identity_service/api/routes/identity.py
    - products/audit-service/src/audit_service/api/routes/ingest.py
    - products/audit-service/src/audit_service/api/routes/query.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - shared/shared-contracts/schemas/tool-result.schema.json
    - shared/shared-contracts/schemas/agent-stream-event.schema.json
    - shared/shared-contracts/schemas/health-response.schema.json
---

## Overview

The platform uses a layered error-handling approach that is consistent across all Python services (agent-platform, audit-service, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway). Errors are expressed as HTTP responses at the API boundary, structured `ToolResult` envelopes for tool execution, and domain-specific exception types in service internals. There is no centralized `errors/` package; instead each product follows the same FastAPI-based pattern.

## HTTP Boundary: FastAPI + `HTTPException`

Every service exposes a FastAPI application via an `app.py` that registers an `http` middleware to log requests and capture `response.status_code`. Routes raise `fastapi.HTTPException` with explicit `status_code` and `detail` strings rather than returning custom response models for errors:

- **401 Unauthorized** — missing or invalid credentials (e.g. agent-platform v2 routes require `X-User-ID`; identity-broker rejects missing `Authorization` headers; audit-service returns 401 on auth failures).
- **400 Bad Request** — malformed JSON bodies, invalid Pydantic payloads, invalid query parameters (audit-service ingest rejects invalid JSON and batch-too-large; platform-gateway rejects invalid `incident_id`).
- **404 Not Found** — session or confirmation not found (agent-platform session/confirmation lookups).
- **409 Conflict** — duplicate confirmation creation.
- **410 Gone** — expired confirmation.
- **502 Bad Gateway** — downstream service failures (identity-broker wraps `httpx.HTTPStatusError` from OIDC calls as 502; platform-gateway maps audit/incident/tool gateway failures to 502).
- **503 Service Unavailable** — optional components not configured (platform-gateway when audit service or policy bundle is unavailable; identity-broker when OIDC exchange fails).

Services do **not** register global exception handlers; they rely on FastAPI's default JSON error shape (`{"detail": ...}`) plus the per-route status code. The shared observability layer records every request including its final `status_code` via the `http_request` event logged in each service's middleware.

## Domain Exceptions (Service Internals)

Services define small, typed exception classes in their `services/` packages to propagate business errors without leaking stack traces:

- `IngestAuthError` (audit-service) — raised by `authenticate_caller`, caught at the route boundary and converted to 401.
- `ExchangeError` (identity-broker) — carries `status_code` and `detail`; routes re-raise it as `HTTPException` after emitting an audit event with `"token_exchange_rejected"`.
- `TokenVerificationError` (platform-gateway) — caught in auth routes to reject invalid bearer tokens.
- `PolicyLoadError` (platform-gateway) — mapped to 503 when the policy bundle cannot be loaded.
- `ConfirmationNotFound`, `ConfirmationExpired`, `ConfirmationOwnerMismatch` (agent-platform) — raised by session/HITL services and caught in routes to return 404/410/409.

These exceptions are always caught at the route layer and translated into HTTP responses; they never bubble out of the process.

## Tool Execution Errors: Structured `ToolResult`

The tool execution framework (SPEC-007, enforced by SPEC-021) does **not** use exceptions to signal tool failure. Instead, tools return a `ToolResult` dataclass whose `status` field is one of `"success" | "error" | "denied"`. Two helpers enforce the envelope:

- `make_error_result(tool_name, code, message, risk_level, source_system, duration_ms)` — produces a result with `status="error"` and an `error={"code", "message"}` payload.
- `make_denied_result(tool_name, reason, risk_level)` — produces `status="denied"` with `error.code="POLICY_DENIED"`.

This design lets the tool-gateway and agent-platform runtime treat denials and errors uniformly while preserving the policy decision for auditing and streaming events. The `tool-result.schema.json` contract enforces this structure across services.

## Streaming / Agent Protocol Errors

Agent chat and tool invocation streams also carry terminal error frames defined in `agent-stream-event.schema.json`: the `type` field can be `"error"` and the frame includes an `error` object with `code` and `message`. Stream events also carry a `status` field (`"success" | "error" | "denied" | "approved" | "expired" | "interrupted"`) used for confirmation results and tool results. This is the protocol-level counterpart to the HTTP-layer error model.

## Audit Trail Integration

Errors are not just returned to callers — they are recorded as audit events. In identity-broker, rejected token exchanges emit an audit event with `decision="deny"` and `reason=exc.detail`. The audit-service itself rejects malformed batches with metrics counters (`record_rejected("auth")`, `record_rejected("malformed")`, `record_rejected("batch_too_large")`) so error rates are observable.

## Conventions Observed Across Services

| Pattern | Evidence |
|---|---|
| Raise `HTTPException(status_code=..., detail=...)` at route boundaries | All services' route files |
| Wrap third-party HTTP errors as 502/401 | identity-broker `auth_callback`, `auth_refresh`; platform-gateway audit proxy |
| Use domain exceptions only inside services, convert to HTTP at routes | audit-service `IngestAuthError`, identity-broker `ExchangeError`, agent-platform HITL exceptions |
| Return structured `ToolResult` with `status` enum for tool failures | tool-gateway `tools/base.py` |
| Log every request including `status_code` via middleware | Every service's `app.py` |
| Emit audit events for authentication and policy failures | identity-broker, audit-service |
| No global exception handlers — rely on FastAPI defaults | Confirmed by absence of `@app.exception_handler` in any service |

## Constraints Enforced by Contracts

- `tool-result.schema.json` requires `status` to be one of `success/error/denied` and `error` to contain `code`/`message` — tool implementations must conform.
- `agent-stream-event.schema.json` constrains stream `type` and `status` enums, forcing error frames to include `error.code`.
- Health schemas constrain `status` to `ready/not_configured/provider_error`, which is how provider initialization errors surface to clients.

There is no repository-wide rule document stating these conventions; they emerge from the repeated implementation pattern across all seven services and are backed by the shared JSON schema contracts.