---
kind: error_handling
name: FastAPI HTTPException + Domain Exceptions with Structured Tool Results
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/services/session_service.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/audit-service/src/audit_service/app.py
    - products/skills-hub/src/skills_hub/app.py
    - products/tool-gateway/src/tool_gateway/app.py
---

## Overview

The Luban Agentic AIOps Platform is a multi-product Python platform (agent-platform, audit-service, identity-broker, platform-gateway, skills-hub, tool-gateway) built on FastAPI. Error handling follows a consistent two-layer pattern: domain-level exceptions are raised inside services and tools, and route/service layers translate them into standardized HTTP responses via `fastapi.HTTPException`. There is no global exception handler — each service relies on FastAPI's default JSON error response shape.

## Layered Exception Model

### Domain / internal exceptions
Each product defines small, purpose-specific exception classes for non-HTTP failures:
- `ProviderConfigurationError(ValueError)` in `agent_service/providers/base.py` signals missing or invalid provider configuration (e.g. missing `AGENTSCOPE_API_KEY`).
- `TokenVerificationError(Exception)` in `platform_gateway/services/token_verifier.py` wraps JWT verification failures (`token expired`, `invalid token issuer`, `invalid token audience`, `unable to resolve signing key`) with a `.detail` string.
- `ExchangeError` in `identity_service/services/exchange_service.py` carries both `status_code` and `detail` so the auth route can re-raise it as an `HTTPException` preserving the upstream status.
- `PolicyLoadError` in `tool_gateway/services/policy_engine.py` is caught by the `/ready` health endpoint and reported as `status: degraded` rather than failing the process.

These exceptions are never returned to clients directly; they are always caught at the boundary layer and mapped to HTTP status codes.

### HTTP error mapping
All public-facing routes raise `fastapi.HTTPException(status_code=..., detail=...)`:
- **401 Unauthorized**: malformed/missing `Authorization` header, missing bearer token when auth is required, invalid/expired JWT, failed OIDC refresh, missing `X-User-ID` header in agent-platform v2 routes.
- **403 Forbidden**: policy engine deny decisions (`action denied by policy`), tool invocation without identity context.
- **404 Not Found**: session not found in `agent_service/services/session_service.py`.
- **502 Bad Gateway**: OIDC token exchange failure, downstream audit query failure.
- **503 Service Unavailable**: audit service not configured, tool registry not initialized.

The identity-broker route in `identity_service/api/routes/auth.py` demonstrates the canonical translation pattern: catch a domain `ExchangeError`, log and emit an audit event, then `raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc`.

### Tool execution result envelope
Tool execution errors do not use HTTP exceptions. Instead, `tool_gateway/tools/base.py` defines a structured `ToolResult` dataclass with fields `tool_name`, `status` (`success` | `error` | `denied`), `data`, `evidence`, and `error` (a `{code, message}` dict). Factory helpers `make_error_result()` and `make_denied_result()` build these envelopes consistently. The `invoke_tool` pipeline in `tool_gateway/services/gateway_service.py` maps `ToolResult.status` to HTTP status codes: `success → 200`, `error → 400`, `denied → 403`. This keeps tool errors self-describing and auditable independent of HTTP transport.

## Middleware and Global Handling

Every service registers an identical HTTP middleware that logs every request/response pair with `service`, `request_id`, `method`, `path`, `status_code`, and `duration_ms` via `core.observability.log_event`. This middleware runs around all routes and captures the final `response.status_code`, including those produced by `HTTPException`. No custom `@app.exception_handler` is registered anywhere in the codebase; the platform depends on FastAPI's default exception-to-JSON conversion.

## Cross-Cutting Conventions Observed

1. **Raise low-level, map at the boundary.** Services raise typed exceptions (`TokenVerificationError`, `ProviderConfigurationError`, `ExchangeError`); routes convert them to `HTTPException` with explicit status codes.
2. **Use `from exc` chaining.** When wrapping lower-level exceptions into `HTTPException`, the code consistently uses `raise HTTPException(...) from exc` to preserve the original traceback (seen in identity-broker and tool-gateway).
3. **Structured denial results for tools.** Policy denials and tool errors go through `make_denied_result` / `make_error_result` rather than raising exceptions, enabling uniform audit logging and redaction.
4. **Health/readiness reflect error state.** The tool-gateway `/ready` endpoint catches `PolicyLoadError` and returns `status: degraded` instead of failing, signaling partial availability.
5. **Audit events accompany denials.** Every authentication and policy denial path emits an audit event before returning the error, ensuring security-relevant failures are durable even when HTTP responses vary.
6. **No global error formatter.** Each service's `app.py` only sets up logging, metrics, telemetry, and the request logger middleware; error serialization is delegated to FastAPI defaults.
7. **Consistent 4xx/5xx semantics across products.** 401 = auth failure, 403 = policy denial, 404 = resource missing, 502 = downstream failure, 503 = dependency unavailable — used uniformly across platform-gateway, tool-gateway, identity-broker, and agent-platform.