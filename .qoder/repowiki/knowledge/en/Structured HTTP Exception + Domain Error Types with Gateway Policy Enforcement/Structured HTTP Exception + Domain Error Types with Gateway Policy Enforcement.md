---
kind: error_handling
name: Structured HTTP Exception + Domain Error Types with Gateway Policy Enforcement
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/audit-service/src/audit_service/app.py
    - products/identity-broker/src/identity_service/app.py
---

## System Overview

The platform uses a layered error-handling strategy built on FastAPI's `HTTPException` for boundary responses, domain-specific Python exceptions for internal failures, and a deny-by-default policy engine that converts authorization decisions into structured 401/403 responses. There is no centralized exception-to-HTTP-middleware; instead, each service's route handlers and gateway services explicitly raise `HTTPException` with explicit status codes and detail payloads.

## Key Patterns

### 1. Domain Exceptions (internal layer)
Each service defines small, purpose-built exception classes in its own modules:
- `agent_service.providers.base.ProviderConfigurationError(ValueError)` — raised when provider settings are incomplete or invalid (e.g. missing `AGENTSCOPE_API_KEY`, wrong provider adapter).
- `agent_service.runtime_kernel.UnknownModelError(ValueError)` — raised when an unknown model id is requested.
- `platform_gateway.services.token_verifier.TokenVerificationError(Exception)` — wraps JWT verification failures (`token expired`, `invalid token issuer`, `invalid token audience`, `unable to resolve signing key`).
- `platform_gateway.services.policy_engine.PolicyLoadError(Exception)` — raised when a policy bundle YAML cannot be loaded or is malformed.
- `tool_gateway.services.policy_engine.PolicyLoadError` — parallel definition in the tool-gateway.

These exceptions carry descriptive messages and are caught at the service boundary where they are translated into HTTP responses.

### 2. HTTP Boundary Responses (FastAPI `HTTPException`)
All public-facing routes raise `fastapi.HTTPException` with explicit `status_code` and `detail`. Observed status codes include:
- **401** — missing/malformed `Authorization` header, authentication required, token verification failure (`malformed authorization header`, `authentication required`, `token expired`).
- **403** — policy denial (`action denied by policy`), approval tier enforcement failures (`not_a_designated_approver`, `self_approval`), tool invocation denied by policy.
- **404** — session not found, confirmation not found.
- **409** — session conflict, confirmation conflict.
- **410** — confirmation expired.
- **422** — validation errors from Pydantic/FastAPI.
- **502** — upstream agent-service unavailability or transport failures during proxying.

Detail payloads are consistently structured: strings for simple cases, dicts containing `action`, `reason`, `requirement`, `approval_tier`, etc. for richer context (especially around policy and approval flows).

### 3. Upstream Proxy Error Mapping (gateway pattern)
The platform-gateway and tool-gateway both follow an identical pattern when calling downstream services via `httpx`: catch `httpx.HTTPStatusError`, pass through 4xx client errors unchanged (so 404/409 reach callers intact), and map all other `httpx.HTTPError` / upstream 5xx to `HTTPException(status_code=502)`. This is documented inline in comments such as "upstream 4xx passes through unchanged; transport failures and upstream 5xx map to 502".

### 4. Policy Engine as Centralized Authorization Error Source
`platform_gateway/services/policy_engine.py` implements deny-by-default evaluation with three outcomes: `allow`, `deny`, `require_approval`. The `enforce_policy()` helper in both gateways raises `HTTPException(403, ...)` on deny, enriched with `action`, `reason`, and `matched_rule_ids`. For `require_approval`, the flow continues to a confirmation bridge rather than returning immediately.

### 5. Readiness/Liveness Degradation
Readiness endpoints (`ready_status`) catch `PolicyLoadError` and `httpx.HTTPError` and return `{"status": "degraded", ...}` with the error string embedded, so Kubernetes probes can distinguish full outage from degraded state.

### 6. Request-Level Middleware
Every service mounts a `@app.middleware("http")` that logs every request/response pair with `method`, `path`, `status_code`, `duration_ms`, and `request_id`. This middleware does NOT transform exceptions — it only observes them after the handler has produced a response (including `HTTPException` responses). This keeps error transformation localized to the handler/gateway layer.

### 7. Structured Audit Trail for Errors
Errors are mirrored to the durable audit trail via `emit_audit_event(...)` with event types like `policy_decision`, `confirmation_decided`, `chat_completed`, `tool_invoked`. Denied approvals emit `confirmation_decided` with `blocked=True` and `blocked_reason` so blocked attempts are observable even though no decision was applied.

## Conventions and Constraints

- **No global exception handler**: Each service relies on FastAPI's default `HTTPException` handler; there is no custom `exception_handler` registered in any `app.py`.
- **Explicit status codes**: Every error path specifies a concrete HTTP status code; there is no reliance on implicit defaults.
- **Deny-by-default policy**: The policy engine returns `deny` when no rule matches, which callers convert to 403 — enforcing least privilege at the gateway layer.
- **Upstream 4xx passthrough**: Gateways never mask upstream client errors; they preserve 4xx status codes so callers can distinguish business errors from infrastructure failures.
- **Token verification failures are surfaced as 401**, not bubbled up as raw JWT exceptions — the `TokenVerificationError` is always caught and converted to `HTTPException(401, ...)`. 
- **Provider configuration errors surface as 422/400-equivalent** via the route layer that calls provider validation, since `ProviderConfigurationError` derives from `ValueError`.
- **Approval-tier enforcement is fail-closed**: If parked-state lookup fails during `chat_confirm`, the gateway raises 502 rather than bypassing policy, documented as "fail closed: without the parked state the tier cannot be checked, and bypassing enforcement would run a mutating batch under a weaker guarantee than the bundle promises."

## Key Files

- `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — central gateway error mapping, policy enforcement, upstream proxy error translation.
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError` and JWT error conversion.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — deny-by-default policy evaluation, `PolicyLoadError`, `PolicyDecision` dataclass.
- `products/tool-gateway/src/tool_gateway/services/gateway_service.py` — parallel gateway error handling for tool invocations, including redaction overflow error.
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError` and provider config validation.
- `products/agent-platform/src/agent_service/runtime_kernel.py` — `UnknownModelError`.
- `products/agent-platform/src/agent_service/api/v2/routes.py` — route-level `HTTPException` usage (401, 404, 409, 410, 422).
- `products/audit-service/src/audit_service/app.py`, `products/platform-gateway/src/platform_gateway/app.py`, `products/identity-broker/src/identity_service/app.py` — uniform request logging middleware pattern.