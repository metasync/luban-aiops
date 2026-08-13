---
kind: error_handling
name: Structured HTTP Error Propagation with Domain-Specific Exceptions in FastAPI Services
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/identity-broker/src/identity_service/api/routes/identity.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
---

## Overview

The Agent Platform Runtime is a set of FastAPI-based Python microservices (agent-platform, platform-gateway, tool-gateway, identity-broker). Error handling follows a consistent pattern: domain-specific exception classes are raised in service logic, and routes translate them into `fastapi.HTTPException` responses with explicit HTTP status codes. There is no global exception handler; each route or service function catches and converts errors at the boundary.

## Custom Exception Types

Each product defines small, purpose-built exceptions rather than reusing generic ones:

- **Agent Platform (`providers/base.py`)**: `ProviderConfigurationError(ValueError)` signals missing/invalid provider configuration (e.g. missing `AGENTSCOPE_API_KEY`).
- **Platform Gateway & Tool Gateway (`services/token_verifier.py`)**: `TokenVerificationError(Exception)` wraps JWT verification failures (expired, invalid issuer/audience, malformed token) and carries a human-readable `detail` string used verbatim in the 401 response.
- **Identity Broker (`services/exchange_service.py`)**: `ExchangeError(Exception)` carries both `detail` and an integer `status_code` (401 for credential/subject failures, 400 for disallowed audience), which routes then map to `HTTPException`.
- **Policy engines (`services/policy_engine.py`)**: `PolicyLoadError(Exception)` indicates policy bundle YAML parse/load failures; it is caught by readiness endpoints and surfaced as `"degraded"` status rather than propagated as an error.

These exceptions are intentionally narrow — they encode only the failure mode, never HTTP semantics (except `ExchangeError`, which is broker-local).

## Authentication & Authorization Error Flow

### Identity Broker
Routes in `identity_service/api/routes/auth.py` and `identity_service/api/routes/identity.py` catch `httpx.HTTPStatusError` from upstream OIDC calls and raise `HTTPException(status_code=502, detail="oidc token exchange failed")`. `ExchangeError` instances are caught and mapped to their embedded `status_code` (401/400). Missing or malformed bearer tokens on identity endpoints raise 401 directly.

### Platform Gateway & Tool Gateway
Both gateways implement identical identity resolution in `services/gateway_service.resolve_request_identity`:
1. If `Authorization` header is present but not `Bearer <token>`, raise `HTTPException(401, "malformed authorization header")`.
2. Call `verify_token(settings, token)`; on `TokenVerificationError`, record a metric (`valid`/`expired`/`invalid`) and raise `HTTPException(401, detail=exc.detail)`.
3. If no token and `settings.require_auth` is true, raise `HTTPException(401, "authentication required")`.
4. Otherwise return a synthetic dev identity (`subject="dev"`, roles `["developer"]`) — this enables local development without breaking downstream policy checks.

Policy enforcement lives in `enforce_policy()`: if the policy engine returns `decision == "deny"`, it raises `HTTPException(403, detail={"detail": "action denied by policy", "action": ..., "reason": ...})`. The agent-platform v2 chat endpoint enforces access via the `X-User-ID` header instead of bearer tokens, raising 401 when absent.

## Streaming & Kernel Errors

In `agent_platform/src/agent_service/runtime_kernel.py`, calls into the underlying AgentScope runtime are wrapped in broad `except Exception` blocks that log via `LOGGER.exception(...)` and fall back to a runtime error response. This is documented as a defensive fallback so streaming/chat operations do not crash the process even if the kernel fails. Stream events include an `error` type that normalizes kernel error payloads into the contract-defined `AgentStreamEvent.error` field.

## Policy Engine Errors

The policy engines in both gateways implement deny-by-default evaluation. YAML parsing errors and malformed rules are wrapped in `PolicyLoadError` during bundle load. Readiness endpoints (`ready_status`) catch these and report `status: "degraded"` with the error string included, rather than failing the health check outright. This lets the service start while signaling misconfiguration.

## HTTP Status Code Conventions

| Scenario | Status Code | Source |
|---|---:|---|
| Missing/invalid bearer token | 401 | `gateway_service.resolve_request_identity` |
| Malformed `Authorization` header | 401 | Same |
| Authentication required but no token | 401 | Same |
| Policy deny | 403 | `enforce_policy` |
| Tool invocation denied (no identity / policy deny) | 403 | `tool_gateway.services.gateway_service.invoke_tool` |
| Tool execution failure (non-denied) | 400 | Same, based on `result.status` |
| OIDC exchange failure | 502 | `identity_service/api/routes/auth.py` |
| Unconfigured agent service | 200 with `status: "not_ready"` | `agent_platform/api/v2/routes.health` |

## Observability Integration

Errors are consistently instrumented:
- Token verification outcomes are recorded via `record_token_verification("valid"|"expired"|"invalid"|"missing")` before raising 401.
- Policy decisions are recorded via `record_policy_decision(action, decision.decision)` before raising 403.
- Telemetry setup failures are swallowed with `except Exception: LOGGER.exception(...)` so startup continues without observability.
- Redaction overflow in tool invocations logs a warning and returns an error result rather than leaking sensitive data.

## Conventions Observed

- **No global exception handlers**: Each route/service layer explicitly catches and converts exceptions to `HTTPException` with a concrete status code.
- **Domain exceptions carry messages, not HTTP codes** (except `ExchangeError`, which is broker-scoped); HTTP mapping happens at the route boundary.
- **Deny-by-default policy**: Any action not explicitly allowed by the loaded YAML bundle results in a 403.
- **Synthetic dev identity**: When auth is optional and no token is provided, a fake identity is injected so downstream policy checks still run — this is a deliberate development convenience, not a security bypass.
- **Defensive fallbacks around third-party runtime calls**: Broad `except Exception` blocks around AgentScope calls log and degrade gracefully rather than propagating unhandled exceptions.
- **Readiness endpoints absorb load-time errors**: Policy bundle parse failures surface as `"degraded"` readiness rather than process exit.