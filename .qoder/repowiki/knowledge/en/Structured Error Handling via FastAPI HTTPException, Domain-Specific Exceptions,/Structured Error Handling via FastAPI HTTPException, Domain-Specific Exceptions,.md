---
kind: error_handling
name: Structured Error Handling via FastAPI HTTPException, Domain-Specific Exceptions, and Tool Result Envelopes
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - shared/shared-contracts/schemas/tool-result.schema.json
---

## Overview

The Luban AIOps platform uses a layered error-handling strategy across its Python services (agent-platform, platform-gateway, tool-gateway, audit-service, incident-service, skills-hub). Errors are expressed in three complementary forms:

1. **HTTP-layer errors** — `fastapi.HTTPException` with explicit `status_code` and `detail` payloads.
2. **Domain-specific exceptions** — small, typed exception classes raised inside service modules to signal authentication, configuration, or policy failures.
3. **Structured result envelopes** — the `ToolResult` dataclass (shared contract `tool-result.schema.json`) carries `status: "success" | "error" | "denied"`, an optional `error.code`/`error.message`, and an `evidence` envelope for auditability.

There is no global `@app.exception_handler` registered; each service relies on FastAPI's default JSON error response shape while converting domain exceptions into appropriate HTTP status codes at the boundary.

## Key Files and Packages

- **Agent Platform provider errors**: `products/agent-platform/src/agent_service/providers/base.py` defines `ProviderConfigurationError(ValueError)` raised when provider settings are incomplete or mismatched.
- **Platform gateway identity & proxy errors**: `products/platform-gateway/src/platform_gateway/services/token_verifier.py` defines `TokenVerificationError(Exception)` with a `.detail` attribute; `gateway_service.py` catches `httpx.HTTPStatusError` and maps upstream 4xx through unchanged while mapping transport/5xx to `HTTPException(status_code=502, detail=...)`. Policy denials raise `HTTPException(status_code=403, detail={...})`.
- **Tool gateway identity & invocation errors**: `products/tool-gateway/src/tool_gateway/services/gateway_service.py` mirrors the same `resolve_request_identity` / `enforce_policy` pattern as the platform gateway, plus structured `make_denied_result` / `make_error_result` from `tools/base.py` for tool-level failures.
- **Audit & incident service auth errors**: `audit_service/services/ingest_auth.py` (`IngestAuthError`) and `incident_service/services/query_auth.py` (`QueryAuthError`) both raise domain exceptions that map to 401 at their routes.
- **Shared contract schema**: `shared/shared-contracts/schemas/tool-result.schema.json` enforces the `status` enum (`success|error|denied`) and `error.code`/`error.message` structure used by all tool invocations.
- **Agent runtime session/HITL errors**: `agent_platform/src/agent_service/api/v2/routes.py` raises `HTTPException` with 409 for parked-session conflicts and 410 for expired confirmations, translating internal `ConfirmationExpired` / `ConfirmationNotFound` exceptions.

## Architecture and Conventions

### 1. Authentication failures → 401
All gateways and backend services follow the same pattern: if a bearer token is malformed, missing when required, or fails verification, they raise `HTTPException(status_code=401, detail=...)`. The `resolve_request_identity` helpers in both `platform_gateway` and `tool_gateway` catch `TokenVerificationError` and re-raise it as a 401 with the original `exc.detail` preserved. Audit and incident services wrap their own `IngestAuthError` / `QueryAuthError` similarly.

### 2. Authorization/policy failures → 403
Policy denial is handled uniformly: `enforce_policy()` evaluates the action against the loaded policy bundle and raises `HTTPException(status_code=403, detail={"detail": "action denied by policy", "action": ..., "reason": ...})`. For tool invocations, the same decision path returns a `ToolResult` with `status="denied"` and `error.code="POLICY_DENIED"`, mapped to HTTP 403 by the route.

### 3. Upstream proxy failures → 502
The platform gateway consistently wraps `httpx` calls to downstream services: `httpx.HTTPStatusError` with 4xx status codes are passed through unchanged (preserving anti-enumeration semantics), while any other `httpx.HTTPError` is converted to `HTTPException(status_code=502, detail="... unavailable")`. This pattern appears in `get_session`, `list_sessions`, `delete_session`, `chat_stream`, and `chat_confirm`.

### 4. Structured tool results instead of raw exceptions
Tool implementations return `ToolResult` objects rather than raising exceptions. Errors are encoded as `ToolResult(status="error", error={"code": ..., "message": ...})` via `make_error_result()`, and policy denials use `make_denied_result()`. The shared JSON Schema (`tool-result.schema.json`) guarantees consumers can rely on this envelope. Redaction overflow is treated as a hard failure that replaces the result with an error envelope carrying code `REDACTION_OVERFLOW`.

### 5. Configuration errors → domain exceptions
Provider adapters raise `ProviderConfigurationError` (a `ValueError` subclass) when settings are invalid or missing (e.g. missing `AGENTSCOPE_API_KEY`). These bubble up to the framework layer where they surface as unhandled server errors unless explicitly caught.

### 6. No global exception handler
None of the services register a custom `@app.exception_handler`; error responses are produced by FastAPI's default handler. Logging middleware (`log_requests` in agent-platform) records `response.status_code` after the request completes, so even error responses are observed for metrics and tracing.

### 7. Observability integration
Errors are consistently correlated with `request_id` (from `x-request-id` header) and recorded via `record_token_verification`, `record_policy_decision`, and structured logging with `extra={...}` fields. Durable audit events are emitted for policy decisions and tool invocations regardless of success/failure.

## Conventions and Constraints

- **HTTP status codes are explicit**: every error path sets a concrete `status_code` (401, 403, 404, 409, 410, 502); there are no bare `raise Exception(...)` paths at the API boundary.
- **Upstream client errors pass through**: the platform gateway deliberately preserves 4xx from the agent service so callers can distinguish unknown sessions (404) from outages (502).
- **Policy denials are audited before being surfaced**: both the HTTP 403 and the structured `denied` tool result are preceded by an audit event emission.
- **Tool results must conform to the shared schema**: `tool-result.schema.json` requires `status ∈ {success, error, denied}`, `evidence.executed_at/duration_ms/risk_level/source_system`, and an optional `error.code/message` pair — enforced by tests and schema validation scripts.
- **Authentication is fail-closed**: missing credentials, malformed headers, expired tokens, and unregistered workload subjects all produce 401; there is no fallback to a synthetic identity outside the explicit dev-mode path gated by `settings.require_auth`.
- **No panic/recover pattern**: Python exceptions are used throughout; there is no `try/except Exception` blanket handler at the application level, nor `sys.exit` usage for control flow.