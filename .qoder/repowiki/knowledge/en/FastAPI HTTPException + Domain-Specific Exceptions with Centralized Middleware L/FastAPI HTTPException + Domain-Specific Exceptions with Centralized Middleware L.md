---
kind: error_handling
name: FastAPI HTTPException + Domain-Specific Exceptions with Centralized Middleware Logging
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/app.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/agent-platform/src/agent_service/app.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/audit-service/src/audit_service/app.py
    - products/skills-hub/src/skills_hub/app.py
---

## Overview

The Luban platform is a monorepo of seven Python microservices, all built on FastAPI. Error handling follows a consistent pattern across every service: domain-level exceptions are raised in business logic, converted to `fastapi.HTTPException` at the API boundary, and observed through a uniform middleware that logs request lifecycle events including status codes.

## Framework and Core Mechanism

- **FastAPI** is the web framework for every service (`platform-gateway`, `agent-platform`, `audit-service`, `identity-broker`, `skills-hub`, `tool-gateway`).
- Errors surface to clients as `HTTPException(status_code=..., detail=...)` — no custom exception-to-response mapping is registered; FastAPI's default JSON error response format is used.
- Each service mounts an `http` middleware named `log_requests` in its `app.py` that wraps `call_next`, measures duration, resolves `x-request-id`, and emits a structured log event via `core.observability.log_event`. The middleware records `response.status_code`, so both success and error responses are uniformly observable.

## Domain-Specific Exception Types

Each service defines small, purpose-specific exception classes rather than reusing generic `Exception`:

| Service | Exception class | Purpose |
|---|---|---|
| `agent-platform` (providers) | `ProviderConfigurationError(ValueError)` | Missing/invalid provider settings (e.g. missing `AGENTSCOPE_API_KEY`) |
| `platform-gateway` | `PolicyLoadError(Exception)` | Policy bundle YAML load or parse failure |
| `platform-gateway` | `TokenVerificationError(Exception)` | JWT verification failures (expired, invalid issuer/audience, key resolution) |
| `identity-broker` | `ExchangeError(Exception)` | Token exchange failures; carries `status_code` (401 vs 400) and `detail` |
| `tool-gateway` | `PolicyLoadError(Exception)` | Same shape as platform-gateway's policy load errors |
| `tool-gateway` | `TokenVerificationError(Exception)` | Same shape as platform-gateway's token verification errors |

These exceptions are raised deep in services and caught by route handlers or gateway helpers, which then raise `HTTPException` with the appropriate 4xx code.

## Conversion Points: Business Exceptions → HTTP Responses

- **Authentication failures**: `TokenVerificationError` is caught in `resolve_request_identity` and re-raised as `HTTPException(401, detail=exc.detail) from exc` in both `platform-gateway` and `tool-gateway`.
- **Authorization/policy denial**: `enforce_policy()` raises `HTTPException(403, detail={"detail": "action denied by policy", "action": ..., "reason": ...})` after emitting an audit event.
- **Missing auth header**: `HTTPException(401, detail="malformed authorization header")` when the `Authorization` header is not a valid bearer token.
- **Explicitly required auth**: `HTTPException(401, detail="authentication required")` when `settings.require_auth` is true and no token is present.
- **Identity broker exchange**: `ExchangeError` is mapped to `HTTPException(status_code=exc.status_code, detail=exc.detail) from exc` in `auth.py` routes.
- **Agent platform v2 routes**: Direct `raise HTTPException(status_code=401, detail="X-User-ID header required")` for missing headers.

## Readiness/Liveness Error Handling

Readiness endpoints swallow configuration/network errors and report `status: "degraded"` instead of failing:

```python
async def ready_status(settings):
    try:
        rules = load_bundle(settings)
        agent_health = await agent_client.health(settings)
        return {"status": "ok", ...}
    except httpx.HTTPError as exc:
        return {"status": "degraded", "agent_service_error": str(exc)}
    except PolicyLoadError as exc:
        return {"status": "degraded", "policy_error": str(exc)}
```

This applies to both `platform-gateway` and `tool-gateway`.

## Fire-and-Forget Audit Emission

Audit emission is intentionally fire-and-forget: `emit_audit_event` wraps the HTTP call in `try/except Exception` and swallows failures (annotated with `# noqa: BLE001 — fire-and-forget never propagates`). A rejected ingest (`response.status_code != 200`) raises `RuntimeError` inside the emitter but is caught by the outer `except Exception` block, ensuring audit delivery never blocks the calling request.

## Configuration Validation Errors

Settings validation uses `ValueError` with descriptive messages (e.g. `"{name} must be a boolean value."`, `"{name} must be one of: {supported_values}."`) raised during startup/configuration loading. These are not caught and propagate as service startup failures.

## Defensive Try/Except Blocks

Defensive error handling appears in non-critical paths:
- Telemetry/metrics modules wrap spans/logs in `try/except Exception` so observability failures cannot crash requests.
- Runtime kernel catches tool execution exceptions and returns structured error results rather than raising.
- Provider registry catches `KeyError` and converts it to `ProviderConfigurationError`.

## Conventions Observed

1. **Never catch `Exception` in request handlers** — only in infrastructure layers (telemetry, audit, runtime kernel).
2. **Domain exceptions carry semantic meaning**; HTTP status codes are assigned at the API boundary, not in domain logic.
3. **All HTTP errors go through `HTTPException`** — no manual `JSONResponse` construction for error cases in routes (except tool-gateway's tool invocation result, which is a structured tool result, not an HTTP error).
4. **Every service has identical middleware shape**: resolve `x-request-id`, measure duration, emit `http_request` log with `status_code`, include metrics and telemetry setup.
5. **Policy deny is always 403**, authentication failure is always 401, malformed input/config is surfaced via `ValueError` at startup.
6. **No `panic/recover` equivalent** — Python exceptions are the sole control-flow mechanism; there is no global error handler overriding FastAPI's default.
7. **Structured logging via `extra=` dicts** carries `request_id`, `subject`, `action`, `decision`, `matched_rule_ids` alongside errors for correlation.