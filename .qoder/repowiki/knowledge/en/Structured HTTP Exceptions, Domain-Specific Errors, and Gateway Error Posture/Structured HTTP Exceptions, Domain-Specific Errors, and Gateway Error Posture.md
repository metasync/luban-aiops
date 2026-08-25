---
kind: error_handling
name: Structured HTTP Exceptions, Domain-Specific Errors, and Gateway Error Posture
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
---

## Overview

The Luban platform uses a layered error-handling strategy across its FastAPI-based microservices. At the HTTP boundary, errors are surfaced as `fastapi.HTTPException` with explicit status codes and structured `detail` payloads. Below the boundary, each product defines domain-specific exception classes (e.g. `TokenVerificationError`, `PolicyLoadError`, `StoreError`) to carry semantic failure information through service boundaries. Cross-service calls use `httpx` exceptions that are caught and remapped into consistent HTTP responses.

## HTTP Boundary: FastAPI `HTTPException`

Every public-facing route raises `fastapi.HTTPException` rather than returning generic 500s:

- **Authentication failures** → 401 with a short string detail (`"authentication required"`, `"malformed authorization header"`, `"X-User-ID header required"`).
- **Authorization/policy denials** → 403 with a structured dict containing `action`, `reason`, and sometimes `requirement`/`approval_tier` (platform-gateway `enforce_policy`, tool-gateway policy enforcement).
- **Business-state conflicts** → 409 for parked confirmations, session-delete-with-parked-confirmation, already-resolved confirmation races.
- **Not-found / anti-enumeration** → 404 for unknown sessions or confirmations; unknown model ids → 422.
- **Upstream proxy failures** → 502 with a human-readable detail, never leaking upstream stack traces.

The agent-platform routes in `products/agent-platform/src/agent_service/api/v2/routes.py` consistently raise these exceptions from helper functions like `_user_id`, `_reject_if_parked`, and `_resolve_model`, keeping route handlers focused on happy-path orchestration.

## Domain-Specific Exception Classes

Each product defines small, typed exception classes in the module where they originate:

| Product | Exception class | Purpose |
|---|---|---|
| platform-gateway | `TokenVerificationError` | JWT verification failures (expired, invalid issuer/audience, key resolution) |
| platform-gateway | `PolicyLoadError` | Invalid or missing policy bundle |
| tool-gateway | `TokenVerificationError` | Same shape as platform-gateway (parallel implementation) |
| tool-gateway | `PolicyLoadError` | Policy bundle load/validation failure |
| agent-platform | `UnknownModelError` | Unknown model id passed to kernel |
| agent-platform | `ProviderConfigurationError` | LLM provider misconfiguration |
| audit-service | `StoreError`, `IngestAuthError` | Audit store / ingestion auth failures |
| identity-broker | `ExchangeError` | OIDC token exchange failures |
| incident-service | `SettingsError`, `ConnectorConfigError`, `NormalizationError`, `TriageError`, `QueryAuthError`, `StoreError` | Per-subsystem failures |
| skills-hub | `SettingsError`, `QueryAuthError`, `StoreError` | Per-subsystem failures |

These exceptions are raised inside services and caught at the nearest boundary (gateway/service layer) where they are translated into either an `HTTPException` or a structured tool result.

## Upstream Proxy Error Mapping

The platform-gateway's `gateway_service.py` is the canonical example of cross-service error posture. Every call to the agent-service is wrapped in a `try/except httpx.HTTPStatusError` block that:

1. Passes through 4xx client errors unchanged (unknown session, expired confirmation, unknown model) so callers can distinguish them from outages.
2. Maps transport-level `httpx.HTTPError` and upstream 5xx to 502 with a stable `"agent service unavailable"` / `"agent service <operation> failed"` detail.
3. Uses `from exc` chaining to preserve the original traceback while presenting a clean HTTP response.

This pattern is repeated for `get_session`, `list_sessions`, `approvals_inbox`, `list_models`, `delete_session`, `chat_stream`, and `chat_confirm`. The same posture is mirrored in the tool-gateway's tool invocation path, which returns a `JSONResponse` with status 200/400/403 based on the `ToolResult.status` field rather than raising exceptions for tool errors.

## Tool Execution Error Model

The tool-gateway does not propagate tool failures as HTTP exceptions. Instead, tools return a `ToolResult` dataclass (`tool_gateway/tools/base.py`) with a `status` field of `"success"`, `"error"`, or `"denied"`, plus an optional `error` dict with `code` and `message`. Two factory helpers enforce this contract:

- `make_error_result(tool_name, code, message, ...)` — for runtime/tool execution errors.
- `make_denied_result(tool_name, reason, risk_level)` — for policy-denied invocations.

The gateway maps `ToolResult.status == "success"` → 200, `"error"` → 400, `"denied"` → 403. This keeps tool errors structured, auditable, and independent of HTTP semantics.

## Redaction Overflow as a Controlled Error Path

When redaction detects too much sensitive content in tool output, it converts the successful result into an error via `make_error_result(..., code="REDACTION_OVERFLOW", ...)`, logs a warning with the redaction fraction, and returns 400. This is a deliberate fail-closed design point documented in comments.

## Health / Readiness Degradation

Readiness endpoints (`ready_status`) catch `httpx.HTTPError` and `PolicyLoadError` and return `{"status": "degraded", ...}` with the error string embedded, instead of failing the probe. This lets orchestrators detect partial outages without killing the process.

## No Global Exception Handler

There is no custom FastAPI exception handler registered in any product's `app.py`; the default FastAPI behavior converts `HTTPException` to JSON responses. Unhandled Python exceptions will produce 500s, but the codebase avoids bare `raise Exception(...)` by using the domain-specific classes listed above.

## Conventions Observed

- Authentication errors are always 401 with a short string `detail`.
- Authorization/policy denials are always 403 with a structured dict carrying `action` and `reason`.
- Unknown resources are 404; business-state conflicts are 409.
- Upstream failures are mapped to 502, never leaked verbatim.
- Tool execution errors are returned as structured `ToolResult` objects, not HTTP exceptions.
- Policy evaluation failures during startup cause readiness to degrade, not crash.
- Store/read failures in non-critical paths (evidence turns, confirmation cards) degrade gracefully by returning `None` and logging warnings rather than raising.