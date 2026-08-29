---
kind: error_handling
name: FastAPI HTTPException + domain-specific Exception classes with per-service token verification and policy enforcement
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/identity-broker/src/identity_service/services/token_service.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
---

## Overview

The Agent Platform Service codebase uses a layered error-handling approach across its four Python services (agent-platform, platform-gateway, tool-gateway, identity-broker). Errors are expressed as:

1. **FastAPI `HTTPException`** at API boundaries for client-facing errors (401, 404, 502, 503).
2. **Domain-specific exception classes** (`ProviderConfigurationError`, `TokenVerificationError`, `PolicyLoadError`) raised in service logic to signal configuration, authentication, or policy failures.
3. **Defensive `except Exception` fallbacks** around third-party runtime calls (AgentScope) that degrade gracefully into user-visible fallback responses instead of propagating raw exceptions.

There is no centralized global exception handler registered; FastAPI's default JSON error response is used, and each service raises `HTTPException` directly from route/dependency functions.

## Key Files and Patterns

### Domain-specific exceptions
- `products/agent-platform/src/agent_service/providers/base.py` defines `ProviderConfigurationError(ValueError)` — raised when provider settings are incomplete or mismatched (e.g. missing `AGENTSCOPE_API_KEY`).
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` and the identical copy under `tool-gateway` define `TokenVerificationError(Exception)` with a `detail` attribute, raised on JWT decode failures (expired, invalid issuer/audience, unknown signing key).
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` and `tool-gateway`'s equivalent define `PolicyLoadError(Exception)` for malformed or missing policy bundles; `evaluate()` returns a frozen `PolicyDecision` dataclass rather than raising, so policy denials are values, not exceptions.

### Token verification and auth errors
Both gateway services implement local JWT verification via JWKS (`PyJWKClient`). The `verify_token()` function catches `jwt.ExpiredSignatureError`, `InvalidIssuerError`, `InvalidAudienceError`, `InvalidTokenError`, and generic key-resolution failures, re-raising them as `TokenVerificationError`. Callers then translate these into `HTTPException(401, ...)`:
- `platform_gateway/services/gateway_service.py`: raises 401 for malformed authorization headers, failed verification, and missing tokens.
- `tool_gateway/services/gateway_service.py`: same pattern.
- `identity_broker/api/routes/auth.py`: raises 502 for OIDC exchange failures and 401 for refresh failures.

### Policy enforcement
Policy evaluation is **value-based**, not exception-based: `evaluate(settings, roles, action)` returns `PolicyDecision(decision="allow"|"deny", reason=..., matched_rule_ids=...)`. A deny-by-default semantics is enforced in the evaluator itself; callers check the decision value and raise `HTTPException(403, ...)` when denied. This keeps policy logic pure and testable.

### Runtime kernel resilience
`AgentKernel` in `runtime_kernel.py` wraps all AgentScope calls in broad `except Exception` blocks. On failure it:
- Calls `remember_error(exc)` to persist the last error string on the kernel instance.
- Logs via `LOGGER.exception(...)`.
- Returns a user-friendly fallback message (`build_provider_error_message`) or yields a `fallback_stream` of SSE events with an error payload.
The kernel exposes `runtime_state()` returning `not_configured`, `provider_error`, or `ready`, and `configuration_hint()` which surfaces the last error to clients via `/api/v2/runtime`.

### Route-level validation
Routes use small helper functions that raise `HTTPException` early:
- `_user_id(x_user_id)` → 401 if missing.
- `_bearer_token(authorization)` → returns `None` for non-Bearer headers (no exception); downstream logic treats absent bearer as unauthenticated.
- Session routes raise 404 when a session is not found.

### Configuration and startup errors
- `runtime_settings.py` raises `ValueError` for invalid setting types/values during startup.
- `entrypoints/runtime.py` raises `RuntimeError` when AgentScope is not importable in the target environment.
- Provider adapters call `validate()` during initialization and raise `ProviderConfigurationError` for missing keys.

## Architecture and Conventions

- **Layered boundary**: Services accept raw HTTP input, validate at the route layer (raise `HTTPException`), delegate to service logic (raise domain `Exception`s), and let FastAPI convert those to JSON responses. There is no shared base exception class across services — each service defines its own domain exceptions locally.
- **Deny-by-default policy**: Both gateways enforce a deny-by-default policy model where `evaluate()` returns a decision object; explicit denies override allows, and highest-priority rules win. No exceptions are raised for policy decisions.
- **Graceful degradation over crash**: The agent-platform kernel never lets AgentScope exceptions escape to the HTTP layer; they are captured, logged, and converted into structured SSE events or plain text fallbacks.
- **No global exception middleware**: Each service relies on FastAPI's built-in handling of `HTTPException`; there are no custom `@app.exception_handler` registrations observed.
- **Test isolation helpers**: Modules expose `reset_*_state()` functions (`reset_verifier_state`, `reset_policy_state`, `reset_key_state`) to clear module-level singleton caches between tests, indicating stateful error paths are intentionally isolated.

## Conventions and Constraints

- Client-facing errors are always `fastapi.HTTPException` with explicit `status_code` and `detail` strings — never bare `Exception` bubbles out of routes.
- Internal failures (config, crypto, policy parsing) are raised as typed `Exception` subclasses specific to the service; callers translate them to appropriate HTTP codes.
- Policy denials are modeled as return values (`PolicyDecision.decision == "deny"`), not exceptions, making policy outcomes part of normal control flow.
- Third-party runtime calls (AgentScope, external HTTP via httpx) are wrapped in `try/except Exception` blocks that log and degrade gracefully rather than failing the request outright.
- Authentication failures consistently map to 401 with human-readable `detail` messages; upstream OIDC failures map to 502; service readiness issues map to 503.