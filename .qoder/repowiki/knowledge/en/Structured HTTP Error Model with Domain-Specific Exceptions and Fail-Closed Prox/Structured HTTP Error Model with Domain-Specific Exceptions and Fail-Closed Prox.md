---
kind: error_handling
name: Structured HTTP Error Model with Domain-Specific Exceptions and Fail-Closed Proxies
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/core/dependencies.py
    - products/execution-runtime/src/execution_runtime/api/routes/handoff.py
    - products/execution-runtime/src/execution_runtime/services/executor.py
    - products/incident-service/src/incident_service/core/config.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
---

## Overview

The Luban AIOps Platform uses a consistent, structured error model across all Python services (agent-platform, platform-gateway, tool-gateway, execution-runtime, identity-broker, audit-service, incident-service, skills-hub). Errors are expressed as FastAPI `HTTPException` instances for HTTP-layer failures, domain-specific `Exception` subclasses for internal validation/loading failures, and structured JSON responses for internal service-to-service contracts. There is no centralized exception base class; instead, each product defines its own small set of typed exceptions in its `services/` or `core/` packages.

## Exception Types by Layer

### Internal / configuration errors
- `PolicyLoadError` (`tool_gateway/services/policy_engine.py`, reused by `platform_gateway/services/policy_engine.py`) — raised when a policy bundle YAML cannot be loaded, parsed, or validated. Used to fail startup fast and surface as `status: degraded` on readiness probes.
- `TokenVerificationError` (`tool_gateway/services/token_verifier.py`, mirrored in platform-gateway) — raised when a bearer JWT is malformed/expired; caught and re-raised as `HTTPException(401)`.
- `SettingsError` (`incident_service/core/config.py`) — raised when an `INCIDENT_*` environment variable is malformed, enforcing fail-fast startup.
- `ValueError` raised directly from config parsers in `execution_runtime/core/config.py` for invalid timeout/retention values.

### HTTP-layer errors (FastAPI)
All public-facing routes raise `fastapi.HTTPException` with explicit `status_code` and `detail`. The most common codes observed:
- `401` — missing/malformed authorization header, token expired, authentication required (`platform_gateway/services/gateway_service.py`, `tool_gateway/services/gateway_service.py`, `agent_service/api/v2/routes.py`).
- `403` — policy deny (`enforce_policy` raises 403 with `{detail, action, reason}`), tool invocation denied by policy, redaction overflow returns 403 via `JSONResponse`.
- `409` — session conflict, confirmation pending, skill graduation conflict (`agent_service/api/v2/routes.py`).
- `404` — confirmation not found, session not found (`agent_service/api/v2/routes.py`).
- `410` — confirmation expired (`agent_service/api/v2/routes.py`).
- `422` — unknown model id, invalid skill target URL (`agent_service/api/v2/routes.py`).
- `502` — upstream proxy failure (audit service unavailable, agent service unreachable, tool gateway unreachable).
- `503` — dependency not configured (audit service not configured, tool registry not initialised).

### Structured internal error responses
Internal service-to-service calls (especially the execution-runtime → tool-gateway path) return a uniform dict shape rather than raising:
```python
{
    "tool_name": ..., "status": "error", "request_id": ..., 
    "error": {"code": "TIMEOUT"|"NO_GATEWAY"|"NO_CREDENTIAL"|"TRANSPORT_ERROR"|"BAD_GATEWAY_RESPONSE", "message": ...}
}
```
This is produced by `_error_result` in `execution_runtime/services/executor.py` and consumed by `map_result_status` to derive receipt status (`succeeded`/`timeout`/`failed`). The handoff route in `execution_runtime/api/routes/handoff.py` wraps every pre-execution rejection through a shared `_reject` helper that emits an `execution_rejected` audit event and returns `JSONResponse(status_code=400/401, content={"error":{"code":"EXECUTION_REJECTED","reason":...}})`.

## Proxy Error Posture (Gateway Pattern)

Every cross-service proxy follows the same pattern, visible in `platform_gateway/services/gateway_service.py` and `platform_gateway/api/routes/audit.py`:

1. Wrap the downstream call in `try/except httpx.HTTPStatusError`.
2. If `400 <= status < 500`: re-raise as `HTTPException(status_code=status, detail=_upstream_detail(exc, ...))` — pass client errors through verbatim so operators can distinguish bad input from outages.
3. If `>= 500` or transport `httpx.HTTPError`: raise `HTTPException(502, detail="... unavailable/failed")`.
4. For optional dependencies (e.g., audit service URL unset): raise `HTTPException(503, detail="... not configured")` before making the call.

This posture is documented inline in comments such as *"Upstream 4xx passes through unchanged; transport failures and upstream 5xx map to 502"* and is applied uniformly to session, document, approval inbox, model catalog, chat stream, and audit proxy endpoints.

## Policy Enforcement as Error Boundary

`enforce_policy(settings, identity, action, request_id)` in both `platform_gateway/services/gateway_service.py` and `tool_gateway/services/gateway_service.py` is the central authorization gate. It evaluates the loaded policy bundle and raises `HTTPException(403, detail={"detail": "action denied by policy", "action": ..., "reason": ...})` on deny. Every decision is also emitted to the durable audit trail via `emit_audit_event(build_audit_event("policy_decision", ...))`. The tool-gateway additionally enforces a second `tools:mutate` check for non-read tools, returning `JSONResponse(..., status_code=403)` for denied mutations.

## Fail-Closed Security Errors

The execution-runtime handoff endpoint (`execution_runtime/api/routes/handoff.py`) implements a strict fail-closed verification chain: unauthenticated, malformed body, missing envelope fields, invalid signature, and argument digest mismatch all reject **before** any execution occurs, each emitting an `execution_handoff_rejected` log event and an `execution_rejected` audit event. Token comparison uses `hmac.compare_digest` (constant-time) and rejects non-ASCII signatures up front. Missing handoff tokens never degrade to open access.

## Observability Integration

Errors are consistently correlated with `request_id` (via `resolve_request_id` from `core/request_context.py`) and logged through a shared `log_event` helper in `core/observability.py`. Audit-emitter modules in each service wrap outbound ingest calls and raise `RuntimeError(f"ingest rejected with {response.status_code}")` on non-2xx, ensuring audit delivery failures are surfaced rather than silently swallowed. Metrics modules record `status=str(response.status_code)` for outbound calls.

## Conventions Observed

- No global `try/except` catching all exceptions at the router level; each route/service handles its own error domain.
- Configuration parsing fails fast with typed exceptions (`SettingsError`, `PolicyLoadError`, `ValueError`) during startup, never deferring to runtime.
- Gateway proxies never leak upstream stack traces; only a human-readable `detail` string is returned to callers.
- Internal service contracts use structured dicts with `error.code` + `error.message` rather than raising exceptions across process boundaries.
- Redaction overflow in the tool-gateway converts a successful tool result into an error result (`REDACTION_OVERFLOW`) with 403 status, treating security-sensitive output as a denial.
- Readiness/liveness endpoints report `status: degraded` with the error message when policy bundles fail to load, rather than failing the probe outright.