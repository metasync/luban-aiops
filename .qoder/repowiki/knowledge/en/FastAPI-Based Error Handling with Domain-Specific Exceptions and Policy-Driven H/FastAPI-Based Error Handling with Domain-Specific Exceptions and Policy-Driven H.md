---
kind: error_handling
name: FastAPI-Based Error Handling with Domain-Specific Exceptions and Policy-Driven HTTP Responses
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/agent-platform/src/agent_service/app.py
    - products/identity-broker/src/identity_service/app.py
---

## Overview

The Luban AIOps platform is a multi-product FastAPI workspace (agent-platform, identity-broker, platform-gateway, tool-gateway). Error handling follows a consistent pattern across all services: domain-specific exception classes in service layers, conversion to `fastapi.HTTPException` at the API boundary, structured logging via a shared observability layer, and policy-driven deny-by-default authorization.

## Exception Types by Layer

**Service-layer domain exceptions** are raised deep inside business logic and carry human-readable detail:
- `TokenVerificationError` (`platform_gateway/services/token_verifier.py`, `tool_gateway/services/token_verifier.py`) — wraps JWT verification failures (expired, invalid issuer/audience, key resolution failure) with a `detail` string; both gateways define an identical class for local JWKS-based token verification.
- `PolicyLoadError` (`platform_gateway/services/policy_engine.py`, `tool_gateway/services/policy_engine.py`) — raised when a YAML policy bundle cannot be parsed or is malformed; used as a startup/load-time invariant so misconfiguration fails fast.
- `ProviderConfigurationError(ValueError)` (`agent-platform/src/agent_service/providers/base.py`) — raised when provider settings are incomplete or mismatched.
- `ExchangeError(Exception)` (`identity-broker/src/identity_service/services/exchange_service.py`) — carries both `detail` and a mapped `status_code` (401 for credential/verification failures, 400 for disallowed audience) used by the broker's delegation endpoint.

**HTTP boundary conversion** happens in gateway service modules:
- `tool_gateway/services/gateway_service.py::resolve_request_identity` catches `TokenVerificationError` and raises `HTTPException(status_code=401, detail=exc.detail)`; missing auth raises 401; malformed Authorization header raises 401.
- `platform_gateway/services/gateway_service.py::resolve_request_identity` mirrors the same mapping.
- `identity-broker/api/routes/auth.py` maps `httpx.HTTPStatusError` from OIDC calls to 502, and re-raises `ExchangeError` status codes directly as `HTTPException`.
- `agent-platform/src/agent_service/api/v2/routes.py` raises `HTTPException(status_code=401, detail="X-User-ID header required")` for missing headers.

**Policy enforcement returns HTTP responses directly:**
- `enforce_policy()` in both gateways raises `HTTPException(status_code=403, detail={"detail": "action denied by policy", "action": ..., "reason": ...})` on deny.
- Tool invocation in `tool_gateway/services/gateway_service.py::invoke_tool` returns `JSONResponse` with status 403 for denied tools and 400 for non-success tool results.

## Middleware and Global Error Handling

Each service registers a single `@app.middleware("http")` that wraps every request, extracts `x-request-id`, measures duration, and emits a structured `log_event("http_request", ...)` including `response.status_code`. There is no custom exception handler registered — FastAPI's default JSON error response format is used. The middleware logs both success and error responses uniformly, making errors observable without special-casing.

## Cross-Cutting Conventions

1. **Fail-fast configuration**: `PolicyLoadError` is raised at load time (startup/readiness probe); readiness endpoints return `{"status": "degraded", "policy_error": str(exc)}` rather than crashing the process.
2. **Deny-by-default authorization**: Both policy engines evaluate against a deny-by-default model; if no rule matches, the decision is `deny` with reason `"no matching policy rule"`, surfaced as 403.
3. **Structured error details**: All domain exceptions carry a `detail` string; gateway services preserve this string in the HTTP 401/403 response body. For policy denials, the detail is a dict containing `action` and `reason` for machine readability.
4. **Observability on every error path**: Every error branch (token expired, invalid issuer, policy deny, OIDC upstream failure) calls `log_event` or `LOGGER.warning`/`info` with `request_id`, subject, roles, action, and decision fields — enabling correlation of errors across services.
5. **No panics / no bare `except Exception` in request paths**: Broad `except Exception` blocks appear only in telemetry wrappers (`agent-platform/core/telemetry.py`) around metrics emission, ensuring observability code never crashes the request. Service code uses specific exception types.
6. **Upstream failure mapping**: Outbound `httpx` calls use `response.raise_for_status()` in gateway service functions; callers catch `httpx.HTTPStatusError` and map to appropriate HTTP codes (e.g., 502 for OIDC exchange failures).
7. **Synthetic dev identity fallback**: When `settings.require_auth` is false and no bearer token is present, services synthesize a `dev` identity with `roles=["developer"]`; policy rules then decide access, preventing implicit bypass.

## Key Files

- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError`, local JWT verify
- `products/tool-gateway/src/tool_gateway/services/token_verifier.py` — duplicate verifier with identical error contract
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError`, deny-by-default evaluation
- `products/tool-gateway/src/tool_gateway/services/policy_engine.py` — mirrored policy engine
- `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — `resolve_request_identity`, `enforce_policy` (401/403 mapping)
- `products/tool-gateway/src/tool_gateway/services/gateway_service.py` — mirrored gateway service + tool invoke error mapping
- `products/identity-broker/src/identity_service/services/exchange_service.py` — `ExchangeError(detail, status_code)`
- `products/identity-broker/src/identity_service/api/routes/auth.py` — maps upstream errors to HTTP codes
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError`
- `products/*/src/*/app.py` — per-service middleware that logs `response.status_code` for all requests
- `shared/shared-contracts/schemas/policy-decision.schema.json` — defines the shape of policy decisions returned in 403 bodies