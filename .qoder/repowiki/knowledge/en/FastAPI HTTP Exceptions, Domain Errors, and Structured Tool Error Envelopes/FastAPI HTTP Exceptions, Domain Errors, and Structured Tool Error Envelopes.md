---
kind: error_handling
name: FastAPI HTTP Exceptions, Domain Errors, and Structured Tool Error Envelopes
category: error_handling
scope:
    - '**'
source_files:
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - shared/shared-contracts/schemas/tool-result.schema.json
    - products/tool-gateway/src/tool_gateway/app.py
    - products/platform-gateway/src/platform-gateway/app.py
    - products/agent-platform/src/agent-platform/src/agent_service/app.py
---

## What system/approach is used

The platform uses a layered error model built on FastAPI:

- **HTTP-layer errors** are raised as `fastapi.HTTPException` with explicit `status_code` and structured `detail` payloads. There is no global exception handler; FastAPI's default JSON error response is relied upon.
- **Domain-level errors** are expressed as custom Python exceptions (e.g. `UnknownModelError`, `PolicyLoadError`, `TokenVerificationError`) that carry semantic meaning and are caught at service boundaries to translate into HTTP responses or structured results.
- **Structured tool execution errors** are not propagated as HTTP exceptions — they are returned inside the shared `tool-result.schema.json` envelope with `status: "error"` / `"denied"` and an `error.code` + `error.message` pair, so callers can distinguish policy denial from transient failures.
- **Configuration/runtime validation errors** raise plain `ValueError` during settings construction, failing fast at startup rather than returning HTTP errors.
- **Background task failures** are swallowed via broad `except Exception` blocks with `# pragma: no cover - defensive fallback` comments, logging the exception and continuing — a deliberate resilience pattern for non-critical kernel work.

There is no centralized `errors/` package, no sentinel error objects, and no `panic`/`recover` equivalent in Python code.

## Key files and packages

- `products/tool-gateway/src/tool_gateway/services/gateway_service.py` — central place where `HTTPException(401)` (malformed auth, missing token), `HTTPException(403)` (policy deny), and downstream transport errors are raised.
- `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — wraps identity-service calls in `_identity_leg`, mapping `httpx.HTTPStatusError < 500` to pass-through `HTTPException` and all 5xx/transport failures to `HTTPException(502, ...)` so the sign-in surface never leaks raw 500s.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — defines `PolicyLoadError` and the three outcomes `allow` / `deny` / `require_approval`; routes call `enforce_policy()` which raises `HTTPException(403)` on deny.
- `products/agent-platform/src/agent_service/runtime_kernel.py` — defines `UnknownModelError(ValueError)` with a comment enforcing fail-closed behavior (SPEC-024 R-1) and catches provider/tool errors in many `try/except Exception` blocks to keep the kernel running.
- `products/agent-platform/src/agent_service/runtime_settings.py` — raises `ValueError` for every invalid environment variable, making misconfiguration a hard failure at import/startup.
- `shared/shared-contracts/schemas/tool-result.schema.json` — declares the canonical `status` enum (`success`, `error`, `denied`) plus the `error.code` / `error.message` shape consumed by the portal and agent runtime.
- Each product's `app.py` registers a uniform `@app.middleware("http") log_requests` that records `response.status_code` but does not transform it — error status codes flow through unchanged.

## Architecture and conventions

1. **Per-service FastAPI app with identical middleware**: Every product (`agent-platform`, `platform-gateway`, `tool-gateway`, `audit-service`, `identity-broker`, `incident-service`, `skills-hub`, `execution-runtime`) builds its `FastAPI` instance via a `create_app()` function, installs a `log_requests` middleware that logs method/path/status_code/duration_ms, includes routers, then wires metrics and telemetry. No service overrides error handling — errors bubble to FastAPI's default handler.

2. **Gateway services own boundary translation**: Business logic lives in `services/*.py`. Routes call helpers like `resolve_request_identity`, `enforce_policy`, and downstream client functions. Those helpers raise either `HTTPException` (for client-facing 4xx/502) or domain exceptions (`PolicyLoadError`, `TokenVerificationError`). Routes do not catch them — they let FastAPI serialize them.

3. **Deny-by-default policy enforcement**: The platform gateway and tool gateway both evaluate a YAML policy bundle. A `deny` decision raises `HTTPException(status_code=403, detail={...})` including the action and reason. A `require_approval` decision returns a structured decision object (not an HTTP error) so the caller can park the request for human approval.

4. **Tool execution errors are data, not HTTP**: When a tool connector fails (e.g. K8S API error, browser CDP disconnect), the tool layer returns a `tool-result.schema.json` envelope with `status: "error"` and `error.code` / `error.message`. This lets the agent runtime render the error in chat without treating it as a failed HTTP request.

5. **Fail-fast configuration vs graceful degradation**: Settings validation raises `ValueError` immediately (fail fast). Background tasks (model discovery, retention, sync) wrap their work in `try/except Exception` blocks that log and continue, keeping the service alive when optional subsystems fail.

6. **Cross-service error posture**: The platform gateway explicitly converts upstream 5xx and transport failures to `HTTPException(502, "...unavailable — retry...")` so clients see a retryable proxy error instead of a raw 500. Downstream services (agent-platform, audit-service, etc.) do not perform this wrapping — they return whatever their dependencies raise.

## Conventions and constraints observed

- **HTTP errors use `fastapi.HTTPException`** with numeric `status_code` and a `detail` field; there is no custom exception-to-status-code registry.
- **Authentication failures** consistently map to 401 (`malformed authorization header`, `authentication required`, or the underlying `TokenVerificationError.detail`).
- **Authorization failures** consistently map to 403 with a `detail` dict containing `action`, `reason`, and sometimes `matched_rule_ids`.
- **Upstream service failures** behind the platform gateway are normalized to 502 with user-facing retry messages; internal services do not do this normalization themselves.
- **Tool execution outcomes** must conform to the shared `tool-result.schema.json` `status` enum (`success`, `error`, `denied`); `denied` is reserved for policy rejections, `error` for operational failures.
- **Kernel background work** is defensively wrapped in `try/except Exception` with `# pragma: no cover - defensive fallback` comments, indicating the convention that non-critical kernel paths should never crash the process.
- **Settings validation** raises `ValueError` with a message naming the offending env var; there is no config-level error type.
- **No global exception handlers** exist in any service; error serialization is delegated entirely to FastAPI's default JSON error response.