---
kind: error_handling
name: FastAPI HTTPException + Domain-Specific Exceptions with Policy-Driven Denials
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_platform/core/config.py
---

## System Overview

The repository is a multi-product Python workspace (FastAPI services) that uses **no global exception handler** and instead relies on two complementary patterns:

1. **HTTP-level errors**: `fastapi.HTTPException` raised directly in route handlers and service functions, with explicit `status_code` values (401, 403, 404, 409, 410, 422, 502). FastAPI's default JSON error response format is used everywhere — no custom exception-to-response mapper exists.
2. **Domain-level exceptions**: Small, typed `Exception` subclasses defined per service to signal internal failures (policy load, token verification, store access, configuration). These are caught at the boundary where an HTTP status must be produced.

There is no `panic/recover` equivalent; Python exceptions propagate up to the FastAPI router, which serializes them as JSON responses.

## Key Files and Packages

- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — defines `TokenVerificationError(Exception)` with a `.detail` attribute; callers catch it and raise `HTTPException(401, detail=exc.detail)`.
- `products/tool-gateway/src/tool_gateway/services/token_verifier.py` — mirrors the same pattern for tool-gateway.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — defines `PolicyLoadError(Exception)` and the `PolicyDecision` dataclass (`allow`, `deny`, `require_approval` outcomes); `evaluate()` returns a decision rather than raising on deny.
- `products/tool-gateway/src/tool_gateway/services/policy_engine.py` — identical policy engine with its own `PolicyLoadError`.
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError(ValueError)` for invalid provider settings.
- `products/agent-platform/src/agent_service/runtime_kernel.py` — `UnknownModelError(ValueError)`.
- Per-service stores/auth: `StoreError`, `IngestAuthError`, `ExchangeError`, `SettingsError`, `ConnectorConfigError`, `NormalizationError`, `QueryAuthError`, `TriageError` — all plain `Exception` subclasses, each scoped to one service.
- Route files (e.g. `products/agent-platform/src/agent_service/api/v2/routes.py`) raise `HTTPException` with specific codes: 401 for missing headers, 404 for not found, 409 for conflicts, 410 for expired confirmations, 422 for validation failures.

## Architecture and Conventions

### Identity & Authorization Errors

Every gateway (`platform-gateway`, `tool-gateway`) implements `resolve_request_identity()` identically:

- Missing or malformed `Authorization` header → `HTTPException(401, "malformed authorization header")`.
- `TokenVerificationError` from JWT decode/JWKS lookup → mapped to `HTTPException(401, detail=exc.detail)`.
- Auth required but no token → `HTTPException(401, "authentication required")`.
- Optional auth falls back to a synthetic dev identity (not an error).

Policy enforcement is centralized in `enforce_policy(settings, identity, action, request_id)`: `evaluate()` returns a `PolicyDecision`; if `decision == "deny"`, raise `HTTPException(403, detail={"detail": "action denied by policy", "action": action, "reason": decision.reason})`. The `require_approval` outcome is handled specially in the confirmation bridge (`chat_confirm`) — blocked approvals emit a structured 403 with fields like `not_a_designated_approver` or `self_approval`.

### Upstream Proxy Error Mapping

Gateway proxy functions follow a consistent posture (documented in comments):

```python
try:
    return await agent_client.<op>(...)
except httpx.HTTPStatusError as exc:
    status = exc.response.status_code
    if 400 <= status < 500:
        raise HTTPException(status_code=status, detail="...") from exc
    raise HTTPException(status_code=502, detail="agent service unavailable") from exc
except httpx.HTTPError as exc:
    raise HTTPException(status_code=502, detail="agent service unavailable") from exc
```

Upstream 4xx client errors pass through unchanged (preserving structured bodies via `_upstream_error_detail`); transport failures and upstream 5xx map to 502.

### Readiness/Liveness Degradation

`ready_status()` catches `httpx.HTTPError` and `PolicyLoadError` and returns `{"status": "degraded", ...}` with the error string embedded — never raises. This is the only place domain exceptions are swallowed for health reporting.

### Tool-Gateway Specifics

Tool invocation returns a structured `ToolResult` (success/denied/error) and maps it to HTTP status: 200 for success, 403 for denied, 400 otherwise. Redaction overflow produces a deliberate `make_error_result(tool_name, "REDACTION_OVERFLOW", ...)`. Mutating tools additionally require a `tools:mutate` policy check before dispatch.

### Agent-Platform Provider Errors

Provider adapters validate their settings in `validate()`, raising `ProviderConfigurationError` when the configured provider name does not match the adapter or when `AGENTSCOPE_API_KEY` is missing. These are application startup-time configuration errors, not request-time errors.

## Conventions and Constraints

- **No global exception middleware**: Each service's `app.py` registers only an HTTP logging middleware; there is no `@app.exception_handler(Exception)` or custom exception-to-JSON converter. All HTTP responses come from explicit `raise HTTPException(...)` calls.
- **Structured 403 details**: Policy denials and approval-tier blocks use dict-shaped `detail` payloads carrying `action`, `reason`, `requirement`, and `approval_tier` so clients can distinguish denial reasons.
- **Consistent 401 taxonomy**: `malformed authorization header`, `token expired`, `invalid token issuer/audience`, `authentication required` — each maps to a distinct `TokenVerificationError.detail` value consumed by metrics recording (`record_token_verification("expired"|"invalid"|"missing")`).
- **Fail-closed on upstream errors**: Proxies never return 200 on upstream failure; they always surface 502. Client errors (4xx) are passthrough to preserve semantics like unknown-session 404.
- **Deny-by-default policy**: `evaluate()` returns `deny` when no rule matches; this is enforced at every gateway entry point.
- **Audit trail parity**: Every policy decision (allow/deny/require_approval), confirmation block, and tool invocation is mirrored to the durable audit service via `emit_audit_event(...)`, even when the request ultimately fails.
- **Domain exceptions stay local**: `PolicyLoadError`, `TokenVerificationError`, `StoreError`, etc. are raised inside services and converted to HTTP statuses only at the API boundary; they do not leak into business logic.