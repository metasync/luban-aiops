---
kind: error_handling
name: Error Handling in the Tool Execution Framework
category: error_handling
scope:
    - '**'
source_files:
    - products/tool-gateway/src/api_gateway/tools/base.py
    - products/tool-gateway/src/api_gateway/services/token_verifier.py
    - products/tool-gateway/src/api_gateway/services/policy_engine.py
    - products/tool-gateway/src/api_gateway/services/gateway_service.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/tool-gateway/src/api_gateway/app.py
    - products/identity-broker/src/identity_service/app.py
---

This repository implements error handling across three FastAPI services (tool-gateway, agent-platform, identity-broker) using a consistent pattern of domain-specific exception types, structured result envelopes, and HTTP-level responses. There is no centralized error-handling framework; instead, each service defines its own exceptions and lets FastAPI's default exception handler convert `HTTPException` instances into JSON responses.

**1. Domain-specific exception classes**
- `ProviderConfigurationError(ValueError)` in `agent_service/providers/base.py` signals invalid provider settings.
- `TokenVerificationError(Exception)` in `api_gateway/services/token_verifier.py` wraps JWT verification failures with a `detail` attribute used by callers to distinguish expired vs. invalid tokens.
- `PolicyLoadError(Exception)` in `api_gateway/services/policy_engine.py` indicates malformed or missing policy bundles.
- `ExchangeError(Exception)` in `identity_service/services/exchange_service.py` carries both a message and an HTTP status code for OIDC/workload-token exchange failures.

These exceptions are raised at the boundary of their subsystems and caught higher up where they are translated into either structured tool results or HTTP responses.

**2. Structured tool-result envelope**
The gateway uses `ToolResult` (dataclass in `tools/base.py`) as the canonical error container for tool invocations. Errors are produced via `make_error_result(tool_name, code, message, ...)` which sets `status="error"` and an `error={code, message}` payload. Policy denials use `make_denied_result(...)` with `status="denied"`. This envelope is serialized directly to the response body, so callers always receive a uniform shape regardless of failure mode.

**3. HTTP-level error propagation**
- Routes raise `fastapi.HTTPException` with explicit `status_code` and `detail` for authentication/authorization failures (401, 403) and upstream errors (502, 503). The `resolve_request_identity` function converts `TokenVerificationError` into 401 responses, and `enforce_policy` raises 403 on deny decisions.
- The `gateway_service.invoke_tool` method maps `ToolResult.status` to HTTP codes: 200 for success, 400 for generic errors, 403 for denied.
- Identity broker routes re-raise upstream `httpx` errors as 502 and translate `ExchangeError` status codes directly into HTTP responses.

**4. Middleware and global logging**
Each service registers an `@app.middleware("http")` that logs every request with `request_id`, method, path, `status_code`, and `duration_ms` through a shared `log_event` helper. No custom exception handlers are registered; FastAPI's built-in handler converts `HTTPException` to JSON. Unhandled exceptions bubble up as 500 responses and are logged via `LOGGER.exception` in defensive try/except blocks (e.g., AgentScope reply/stream fallbacks).

**5. Defensive fallback patterns**
- `runtime_kernel.reply_text` and `stream_events` wrap AgentScope calls in `try/except Exception`, log the stack trace, remember the last error, and return a user-friendly fallback message rather than propagating the exception.
- `ready_status` catches `httpx.HTTPError` and `PolicyLoadError` to report degraded health without failing the endpoint.
- Delegation client swallows non-fatal exceptions (`except Exception as exc`) to keep delegation failures from breaking core flows.

**6. Redaction-driven error conversion**
When redaction overflow is detected, `invoke_tool` converts the successful `ToolResult` into an error result with `code="REDACTION_OVERFLOW"` and returns it with HTTP 400, ensuring sensitive data never leaks even when the underlying tool succeeds.

**Key files and packages**
- `products/tool-gateway/src/api_gateway/tools/base.py` — `ToolResult`, `make_error_result`, `make_denied_result`
- `products/tool-gateway/src/api_gateway/services/token_verifier.py` — `TokenVerificationError`
- `products/tool-gateway/src/api_gateway/services/policy_engine.py` — `PolicyLoadError`, `PolicyDecision`
- `products/tool-gateway/src/api_gateway/services/gateway_service.py` — HTTP error mapping, policy enforcement, redaction overflow
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError`
- `products/agent-platform/src/agent_service/runtime_kernel.py` — defensive fallbacks for AgentScope failures
- `products/identity-broker/src/identity_service/services/exchange_service.py` — `ExchangeError` with embedded HTTP codes
- `products/tool-gateway/src/api_gateway/app.py` and `products/identity-broker/src/identity_service/app.py` — request logging middleware

**Conventions and constraints**
- All tool-facing errors go through the `ToolResult` envelope; raw exceptions are never returned over the wire.
- Authentication failures use 401 with descriptive `detail`; authorization/policy denials use 403 with a reason field.
- Upstream service failures are surfaced as 502/503; configuration errors surface as 400/422 equivalents via `HTTPException.detail`.
- Every request is logged with a stable `request_id` for cross-service tracing.
- Fallback paths exist for critical external dependencies (AgentScope, token verification, policy loading) so partial degradation does not crash the service.