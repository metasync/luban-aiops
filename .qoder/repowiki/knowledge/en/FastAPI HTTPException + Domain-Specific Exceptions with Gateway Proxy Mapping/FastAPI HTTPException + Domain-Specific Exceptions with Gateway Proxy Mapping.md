---
kind: error_handling
name: FastAPI HTTPException + Domain-Specific Exceptions with Gateway Proxy Mapping
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/agent-platform/src/agent_service/app.py
---

## What system/approach is used

The codebase uses a layered error model built on FastAPI's `HTTPException` for the HTTP boundary and domain-specific Python exceptions for internal service boundaries. There is no centralized exception-to-JSON mapper registered via `@app.exception_handler`; instead, each service raises `HTTPException` directly from route handlers or service functions, and relies on FastAPI's default JSON error response shape (`{"detail": ...}`) plus a numeric `status_code`. Cross-service failures are handled by catching `httpx.HTTPStatusError` / `httpx.HTTPError` at gateway proxies and re-raising as `HTTPException` with mapped status codes.

## Key files and packages

- **Platform gateway** — `products/platform-gateway/src/platform_gateway/services/gateway_service.py`: central proxy layer that catches upstream `httpx` errors and converts them to `HTTPException` (401/403/404/409/410/502). Also defines `enforce_policy`, which raises 403 on deny.
- **Tool gateway** — `products/tool-gateway/src/tool_gateway/services/gateway_service.py`: same pattern; additionally returns structured `ToolResult` envelopes via `make_denied_result` / `make_error_result` for tool invocations.
- **Token verification** — `products/platform-gateway/src/platform_gateway/services/token_verifier.py` and `products/tool-gateway/src/tool_gateway/services/token_verifier.py`: define `TokenVerificationError(Exception)` with a `.detail` string; callers catch it and raise `HTTPException(status_code=401, detail=exc.detail)`.
- **Policy engine** — `products/platform-gateway/src/platform_gateway/services/policy_engine.py` and `products/tool-gateway/src/tool_gateway/services/policy_engine.py`: define `PolicyLoadError(Exception)` raised when policy bundles are invalid; caught in `ready_status` to report `status: degraded` rather than failing the process.
- **Agent platform providers** — `products/agent-platform/src/agent_service/providers/base.py`: defines `ProviderConfigurationError(ValueError)` for invalid provider settings.
- **Other domain exceptions** — `WorkerHandoffError`, `IncidentClientError`, `StoreError`, `ConnectorConfigError`, `NormalizationError`, `QueryAuthError`, `TriageError`, `ExchangeError`, `DigestInputError`, `UnknownSessionError`, `IngestAuthError` — one small `Exception` subclass per subsystem, raised within that subsystem and surfaced to the API layer where needed.
- **Tool result envelope** — `products/tool-gateway/src/tool_gateway/tools/base.py`: `ToolResult` dataclass with `status` in `{"success", "error", "denied"}`, plus `make_error_result` and `make_denied_result` helpers that build the structured error payload consumed by the tool-gateway routes.

## Architecture and conventions

1. **Gateway as the single HTTP boundary.** The platform gateway and tool gateway are the only services that translate internal exceptions into HTTP responses. Routes call service functions; those functions raise either `HTTPException` (for client-facing errors like auth/policy/validation) or domain `Exception`s (for internal failures). The gateway wraps every outbound `httpx` call in a `try/except httpx.HTTPStatusError` block that:
   - Passes through 4xx status codes unchanged (so anti-enumeration 404s, expired confirmations, unknown sessions reach the caller verbatim).
   - Maps transport failures and upstream 5xx to `HTTPException(status_code=502, detail="...")`.
   - For document creation and confirmation flows, preserves the upstream structured `detail` body via `_upstream_detail` / `_upstream_error_detail` so surfaces can render refusal messages verbatim.

2. **Authentication errors are uniform.** Missing/malformed bearer tokens and `TokenVerificationError` all resolve to `HTTPException(status_code=401, detail=...)` in both gateways' `resolve_request_identity`. A synthetic dev identity is returned when `require_auth` is false, never bypassing policy.

3. **Authorization is deny-by-default.** `enforce_policy` evaluates roles against the loaded bundle and raises `HTTPException(status_code=403, detail={"action", "reason"})` on deny. For approval-required actions, an additional tier check (`_enforce_approval_tier`) rejects self-approval and non-designated approvers with a structured 403 containing `requirement`, `approval_tier`, and `blocked_reason`.

4. **Structured tool results replace exceptions for tool execution.** Tool implementations return `ToolResult` objects rather than raising exceptions. The gateway maps `status == "error"` to HTTP 400 and `status == "denied"` to HTTP 403; success stays 200. Redaction overflow short-circuits the result into `make_error_result(..., code="REDACTION_OVERFLOW")`.

5. **No global exception handler.** Neither `platform_gateway/app.py` nor `tool_gateway/app.py` register an `@app.exception_handler`; they only install an HTTP middleware that logs every request/response pair. Agent platform follows the same pattern in `agent_service/app.py`. Errors bubble up to FastAPI's default handler.

6. **Defensive `except Exception` blocks are used sparingly as fallbacks.** In `runtime_kernel.py` and telemetry paths, bare `except Exception` blocks log and continue or degrade gracefully (e.g., missing index, cancelled task), but they do not swallow errors at the API boundary.

## Conventions and constraints

- **Upstream 4xx passthrough is enforced at the gateway.** Every proxy function in `gateway_service.py` documents the posture in its docstring: "Upstream 4xx (...) passes through unchanged; transport failures and upstream 5xx map to 502." This is the consistent contract between platform-gateway and agent-service.
- **Policy denials always carry structured detail.** Deny responses include `action`, `reason`, and often `matched_rule_ids` so audit trails and UIs can explain the decision.
- **Approval-tier violations produce a richer 403.** Blocked approvals include `requirement`, `approval_tier`, and `blocked_reason` (`not_a_designated_approver` or `self_approval`).
- **Domain exceptions stay internal.** `TokenVerificationError`, `PolicyLoadError`, `ProviderConfigurationError`, and the per-subsystem `*Error` classes are raised inside services and converted to `HTTPException` at the boundary; they are not serialized directly over HTTP.
- **Readiness endpoints fail closed on configuration errors.** `ready_status` catches `PolicyLoadError` and reports `status: degraded` rather than crashing, allowing liveness probes to pass while signaling misconfiguration.
- **Audit trail mirrors errors.** Every denied policy decision, blocked approval, and tool invocation is emitted as a durable audit event alongside the HTTP response, so errors are observable even when the caller does not inspect the response body.