---
kind: error_handling
name: Structured Error Types, HTTP Exception Mapping, and Policy-Driven Denial in FastAPI Services
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/core/request_context.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
---

# Error Handling in the Agentic AIOps Platform

## Approach Overview

The platform is a multi-product Python workspace (agent-platform, platform-gateway, tool-gateway, audit-service, identity-broker, incident-service, skills-hub) built on **FastAPI**. Error handling follows a consistent pattern across all services:

1. **Domain-specific exception classes** are raised in service layers to represent business failures.
2. **HTTP boundaries** translate those exceptions into `fastapi.HTTPException` with appropriate status codes.
3. **Policy decisions** are modeled as structured return values (`PolicyDecision`, `ToolResult`) rather than exceptions — policy denials are explicit data, not control flow.
4. **Cross-cutting concerns** (auth, observability, metrics) are handled via FastAPI middleware that wraps every request uniformly.
5. **Upstream proxying** normalizes third-party errors: 4xx pass through unchanged; transport/5xx map to 502.

## Key Files and Packages

| Area | File(s) | Role |
|------|---------|------|
| Agent provider config errors | `products/agent-platform/src/agent_service/providers/base.py` | `ProviderConfigurationError(ValueError)` for missing/invalid provider settings |
| HITL confirmation errors | `products/agent-platform/src/agent_service/services/hitl_confirmations.py` | `ConfirmationNotFound`, `ConfirmationExpired`, `ConfirmationOwnerMismatch` |
| Token verification | `products/platform-gateway/src/platform_gateway/services/token_verifier.py` | `TokenVerificationError(Exception)` with `.detail` string |
| Policy engine | `products/platform-gateway/src/platform_gateway/services/policy_engine.py` | `PolicyLoadError(Exception)` + `PolicyDecision` dataclass |
| Tool result envelope | `products/tool-gateway/src/tool_gateway/tools/base.py` | `ToolResult(status="success"|"error"|"denied")` with `make_error_result` / `make_denied_result` helpers |
| Gateway error mapping | `products/platform-gateway/src/platform_gateway/services/gateway_service.py` | Proxies upstream 4xx unchanged, maps transport/5xx to 502 |
| Route-level validation | `products/agent-platform/src/agent_service/api/v2/routes.py` | Raises `HTTPException(401/409/422)` for header/model/session errors |
| Request context | `products/agent-platform/src/agent_service/core/request_context.py` | Resolves `x-request-id` correlation key (trace_id → UUID fallback) |
| Middleware | `products/platform-gateway/src/platform_gateway/app.py`, `products/agent-platform/src/agent_platform/core/metrics.py` | HTTP logging middleware, RED metrics middleware |

## Architecture and Conventions

### Domain Exceptions vs. Structured Results

Business-layer failures raise typed exceptions:
- `ProviderConfigurationError` (subclass of `ValueError`) when agent provider settings are invalid.
- `TokenVerificationError` wrapping JWT decode failures, carrying a `.detail` string used by callers to distinguish expired vs. invalid tokens.
- `PolicyLoadError` when the YAML policy bundle cannot be parsed or loaded.
- `ConfirmationNotFound` / `ConfirmationExpired` / `ConfirmationOwnerMismatch` for HITL state machine transitions.

Policy outcomes are **not** exceptions. The policy engine returns a frozen `PolicyDecision` dataclass (`decision: "allow" | "deny"`, `matched_rule_ids`, `reason`). Callers explicitly branch on `decision == "deny"` and emit audit events and `HTTPException(403)` — this makes deny-by-default visible in logs and traces without relying on exception control flow.

Similarly, tool execution returns a `ToolResult` dataclass with `status` field (`"success"` / `"error"` / `"denied"`) plus an optional `error` dict (`code`, `message`). This lets the tool layer fail fast while preserving structured evidence (duration, risk level, source system).

### HTTP Boundary Translation

Every gateway/service route translates internal errors to HTTP responses:

- **Auth failures**: `HTTPException(status_code=401, detail=...)` for missing `X-User-ID`, malformed `Authorization` headers, or `TokenVerificationError`.
- **Policy denial**: `HTTPException(status_code=403, detail={"detail": "action denied by policy", "action": ..., "reason": ...})`.
- **Validation errors**: `HTTPException(status_code=422, detail=f"unknown model id: {requested}")` for unknown model selections.
- **Conflict**: `HTTPException(status_code=409, detail="confirmation pending...")` when a session has a parked HITL confirmation.
- **Not found**: `HTTPException(status_code=404, detail="session not found")`.

### Upstream Proxy Posture

In `platform_gateway.services.gateway_service`, all calls to downstream services follow the same rule documented in comments: *upstream 4xx pass through unchanged* (so unknown sessions, foreign sessions, expired confirmations surface as client errors), while *transport failures and upstream 5xx map to 502* with a generic `"agent service unavailable"` detail. This is applied consistently across `get_session`, `list_sessions`, `delete_session`, `chat_stream`, and `chat_confirm`.

### Middleware and Cross-Cutting Concerns

Each service mounts a FastAPI HTTP middleware that:
- Resolves a per-request `request_id` from `x-request-id`, OTel trace ID, or generated UUID.
- Logs every request with method, path, status code, and duration via `log_event`.
- Records metrics (RED: requests, errors, duration) through a separate metrics middleware.

There are no global exception handlers registered — FastAPI's default `HTTPException` handler is relied upon, so all HTTP errors must be raised as `HTTPException` at the boundary.

### Kernel-Level Middleware

The agent runtime kernel composes its own middleware stack (`runtime_kernel._build_middlewares`): permission middleware, evidence sink, optional OpenTelemetry tracing middleware, and optional reply budget control middleware. Errors inside the kernel propagate through these middlewares before reaching the v2 routes, which then convert them to HTTP responses.

## Conventions and Constraints

- **No bare `raise Exception`**: domain errors use named subclasses of `Exception`, `ValueError`, `LookupError`, or `PermissionError`.
- **Deny-by-default policy**: `evaluate()` returns `PolicyDecision(decision="deny", reason="no matching policy rule")` when no rule matches — access is rejected unless explicitly allowed.
- **Structured results over exceptions for tools**: tool implementations return `ToolResult` instead of raising; `make_error_result` and `make_denied_result` enforce a uniform error shape (`code`, `message`, `evidence.duration_ms`, `evidence.risk_level`).
- **Audit trail parity**: every policy decision (allow/deny) and tool invocation is mirrored to the durable audit service via `emit_audit_event`, regardless of success or failure.
- **Request correlation**: `x-request-id` flows end-to-end; if absent, it bridges to the active OTel trace ID, falling back to a generated UUID — never silently dropped.
- **HITL single-flight**: confirmation registry uses `claim` / `take_for_expiry` to prevent double-resume of parked tool calls; concurrent confirm attempts fail closed with `ConfirmationNotFound`.
- **Redaction overflow is a hard error**: if redaction would drop too much output, the tool response is replaced with `make_error_result(tool_name, "REDACTION_OVERFLOW", ...)` and logged at warning level.
- **Startup-time validation**: configuration errors (missing API keys, invalid policy bundles) raise during startup (`ProviderConfigurationError`, `PolicyLoadError`) rather than failing at first request.

## Notable Absences

- No `try/except` blocks catch broad `Exception` in request paths except in telemetry/logging helpers where failures are deliberately swallowed to avoid breaking the primary request flow.
- No centralized error response schema beyond FastAPI's default `HTTPException` JSON format.
- No retry or circuit-breaker wrappers around outbound HTTP calls — failures surface immediately as 502.
- No `panic/recover` equivalent; Python's exception model is used throughout.