---
kind: error_handling
name: Structured Domain Exceptions, FastAPI HTTPException Mapping, and Resilient Kernel Fallbacks
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
---

## Overview

The platform uses a layered error-handling strategy across its Python microservices (agent-platform, platform-gateway, audit-service, identity-broker, incident-service, skills-hub, tool-gateway). Errors are modeled as **domain-specific exception classes** in each service's `services/` or `core/` packages, propagated up the call stack, and translated to **FastAPI `HTTPException`s at the API boundary**. The agent-platform runtime kernel adds an additional resilience layer: unhandled exceptions from AgentScope calls are caught, logged, and converted into graceful fallback responses so streaming SSE sessions never terminate abruptly.

## Exception taxonomy by service

| Service | Custom exceptions | Purpose |
|---|---|---|
| `platform-gateway` | `PolicyLoadError`, `TokenVerificationError` | Policy bundle parse/load failures; JWT verification failures |
| `agent-platform` | `ProviderConfigurationError` (subclass of `ValueError`) | Missing/invalid provider config (`AGENTSCOPE_API_KEY`, wrong provider) |
| `agent-platform` | `ConfirmationNotFound`, `ConfirmationExpired`, `ConfirmationOwnerMismatch` (subclasses of `LookupError` / `PermissionError`) | HITL confirmation registry lookups, TTL expiry, ownership checks |
| `audit-service` | `StoreError`, `IngestAuthError` | Audit store I/O failures; ingest auth failures |
| `identity-broker` | `ExchangeError` | Token exchange failures |
| `incident-service` | `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError` | Config, connector, store, normalization, query auth, triage failures |
| `skills-hub` | `SettingsError`, `QueryAuthError`, `StoreError` | Config, query auth, skill store failures |
| `tool-gateway` | `PolicyLoadError`, `TokenVerificationError` | Mirror of gateway policy/JWT errors for tool execution |

Each custom exception is a thin subclass of `Exception` (or a built-in like `ValueError` / `LookupError` / `PermissionError`) carrying a human-readable `detail` string. There is no shared base exception class across services — each product defines its own namespace.

## API boundary mapping: domain exceptions → HTTP status codes

The `platform-gateway` is the central example of how domain exceptions become HTTP responses:

- `TokenVerificationError` is caught in `resolve_request_identity` and re-raised as `HTTPException(status_code=401, detail=exc.detail)` with metrics recorded as `token_verification("expired" | "invalid")`.
- `PolicyLoadError` is caught in `ready_status` and reported as `status: degraded` rather than failing the health check.
- `httpx.HTTPStatusError` from upstream calls is mapped per-status-code: 4xx pass through unchanged (preserving anti-enumeration 404s), all other transport errors map to `502 Bad Gateway` with a uniform `"agent service unavailable"` detail.
- Policy deny decisions raise `HTTPException(status_code=403, detail={...})` after emitting an audit event.

The `agent-platform` v2 routes raise `HTTPException` directly for client errors: missing `X-User-ID` header (401), duplicate session (409), expired confirmation (410), unknown confirmation (404), session not found (404).

Other services follow the same pattern: route handlers catch domain exceptions and return appropriate FastAPI response objects or let FastAPI's default exception handler render them.

## Kernel-level resilience: logging + fallback instead of propagating

The `AgentKernel` in `runtime_kernel.py` wraps both blocking `reply_text` and streaming `stream_events` paths in broad `except Exception` blocks that:

1. Call `self.remember_error(exc)` to persist the last error on the kernel instance (exposed via `runtime_state() == "provider_error"` and `configuration_hint()`).
2. Log with `LOGGER.exception(...)` including the full traceback.
3. Return a user-facing fallback message (`build_provider_error_message`) for blocking replies, or stream a `fallback_stream` of `message_start/message_delta/message_end` frames for SSE so the portal never sees a broken stream.
4. Clear the error on success via `clear_error()` so the health endpoint transitions back to `ready`.

State persistence (`_snapshot_state`) and state restoration (`_restore_state`) are similarly fail-open: snapshot failures log a warning and record a metric but do not abort the turn; restore failures log a warning and start a fresh agent.

## Middleware and observability integration

Every service mounts a FastAPI `@app.middleware("http")` that wraps each request, resolves an `x-request-id`, measures duration, and emits a structured `http_request` event via `log_event`. This middleware does not swallow exceptions — it logs the resulting `response.status_code`, letting FastAPI's default exception handling produce the final response while still capturing error responses in telemetry.

There is no centralized exception handler registered via `@app.exception_handler`; the codebase relies on FastAPI's built-in `HTTPException` rendering and lets domain exceptions bubble to route handlers where they are explicitly mapped.

## Conventions observed

- **Domain exceptions live next to the logic that raises them**, under `services/` or `core/`, never in a shared package.
- **Exceptions carry a single `detail` string** (or dataclass fields) — there is no rich error envelope type.
- **Client-facing errors are always `HTTPException`** raised from routes or service functions called by routes; internal failures stay as domain exceptions.
- **Upstream transport errors are normalized**: `httpx.HTTPStatusError` preserves 4xx, everything else becomes 502 in the gateway.
- **Fail-open degradation**: readiness probes report `degraded` when policy bundles fail to load; agent state snapshots never raise; kernel provider failures fall back to a safe message.
- **HITL confirmation errors use built-in exception hierarchies**: `LookupError` for not-found/expired, `PermissionError` for ownership mismatch — callers can catch these broadly if needed.
- **No `try/except` around every call site**: only boundaries (gateway proxies, kernel entry points, readiness checks) perform explicit mapping; business logic raises domain exceptions freely.
- **Metrics are updated before raising**: token verification counts (`valid`/`expired`/`invalid`/`missing`) and policy decision counters are recorded before the `HTTPException` is raised, ensuring error paths are observable.