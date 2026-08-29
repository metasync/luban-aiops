---
kind: error_handling
name: FastAPI HTTPException + Domain Exceptions with Upstream Status Mapping
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
---

## Overview

The platform is a Python/FastAPI microservices monorepo (agent-platform, platform-gateway, tool-gateway, audit-service, identity-broker, incident-service, skills-hub). Error handling follows a consistent pattern: domain logic raises typed Python exceptions; the HTTP boundary converts them to `fastapi.HTTPException` with explicit status codes; upstream HTTP calls propagate client errors and map transport/server failures to 502. There are no global exception handlers — FastAPI's default JSON error response is used.

## Exception taxonomy by layer

### Domain-layer exceptions (service-internal)
Each service defines small, purpose-specific exception classes:
- `identity_service/services/exchange_service.py`: `ExchangeError(Exception)` carrying `(detail, status_code)` for credential/token/audience failures (401/400).
- `agent_platform/src/agent_service/services/hitl_confirmations.py`: `ConfirmationNotFound`, `ConfirmationExpired`, `ConfirmationOwnerMismatch` (subclasses of `LookupError` / `PermissionError`) raised by the in-memory confirmation registry.
- `incident_service/services/triage.py`: `TriageError(Exception)` wrapping agent-call or report-validation failures so triage can mark an incident `triage_failed` instead of crashing.
- `platform_gateway/services/policy_engine.py` and `tool_gateway/services/policy_engine.py`: `PolicyLoadError` for malformed policy bundles.
- `agent_platform/src/agent_service/providers/base.py`: `ProviderConfigurationError(ValueError)` for misconfigured LLM providers.

These exceptions never leak across process boundaries — they are caught at the route/service boundary and translated to HTTP responses.

### HTTP boundary: `HTTPException` with explicit status codes
Routes raise `fastapi.HTTPException(status_code=..., detail=...)` directly:
- **401** unauthorized: missing `X-User-ID` header (`agent_platform/api/v2/routes.py`), malformed `Authorization` header (`platform_gateway` and `tool_gateway` `resolve_request_identity`), token verification failure (`TokenVerificationError` mapped to 401), authentication required when `require_auth=True`.
- **403** forbidden: policy engine deny (`enforce_policy` in both gateways returns `HTTPException(403, {"detail": "action denied by policy", ...})`).
- **404** not found: unknown session, foreign session (anti-enumeration convention), expired/missing confirmation.
- **409** conflict: parked confirmation blocks new turns or session delete.
- **410** gone: confirmation TTL expired.
- **502** bad gateway: upstream `httpx.HTTPStatusError` with 5xx, or generic `httpx.HTTPError` (transport failure) in gateway proxy functions (`get_session`, `list_sessions`, `delete_session`, `chat_confirm`).

Upstream 4xx from agent-platform are passed through unchanged (e.g. unknown/foreign session 404, parked-session 409) so callers can distinguish business errors from outages.

### Tool execution results as structured error envelopes
Tool invocations do not raise exceptions into the caller; they return a `ToolResult` dataclass (`tool_gateway/tools/base.py`) with `status` in `{success, error, denied}` plus an `error` dict containing `code` and `message`. Helper constructors `make_error_result` and `make_denied_result` build these consistently. The gateway maps `denied → 403`, `error → 400`, `success → 200`.

### Streaming error handling
SSE streams handle errors inline rather than via HTTP status:
- `agent_platform/api/v2/routes.py` `_normalize_stream_event` coerces unknown event types to `message_delta` for safety.
- During `resume_confirmation`, a `ConfirmationOwnerMismatch` caught mid-stream yields an `AgentStreamEvent(type="error", error={"code": "confirmation_owner_mismatch", ...})` frame instead of aborting the stream.
- Unknown stream events degrade gracefully to `message_delta`.

### Upstream call error posture
Gateway services use `httpx.AsyncClient` with explicit timeouts and uniform error mapping:
```python
except httpx.HTTPStatusError as exc:
    status = exc.response.status_code
    if 400 <= status < 500:
        raise HTTPException(status_code=status, detail="...")
    raise HTTPException(status_code=502, detail="...")
except httpx.HTTPError as exc:
    raise HTTPException(status_code=502, detail="...")
```
This pattern appears in every proxy function (`get_session`, `list_sessions`, `delete_session`, `chat_confirm`) ensuring clients see 4xx for business errors and 502 for infrastructure failures.

### Readiness/liveness error reporting
`ready_status()` catches `httpx.HTTPError` and `PolicyLoadError` and returns `{"status": "degraded", ...}` with the error string embedded, allowing Kubernetes probes to detect partial failures without failing the pod.

### Audit trail integration with errors
Every policy decision (allow/deny) and tool invocation is mirrored to the durable audit trail via `emit_audit_event(...)`, including denied cases. Errors during audit emission are fire-and-forget and do not affect the primary response path.

## Conventions and constraints

- **No global exception handlers**: Services rely on FastAPI's default `HTTPException` JSON response shape; custom formatting is not implemented.
- **Domain exceptions stay internal**: They are only raised within a service and converted to `HTTPException` at the route boundary.
- **Status code discipline**: 401 for auth failures, 403 for policy denials, 404 for unknown/foreign resources, 409 for state conflicts (parked confirmations), 410 for expired confirmations, 502 for upstream failures. These are enforced by repeated identical patterns across gateway services.
- **Anti-enumeration**: Foreign sessions always return 404 (never 403) to prevent enumeration of other users' sessions.
- **Structured tool errors**: Tool implementations must return `ToolResult` via `make_error_result` / `make_denied_result`; raw exceptions are not propagated to callers.
- **Streaming resilience**: SSE endpoints catch domain errors mid-stream and emit typed `error` frames rather than terminating the connection.
- **Fail-closed redaction**: In tool-gateway, excessive PII in tool output triggers a `REDACTION_OVERFLOW` error result (400) instead of leaking sensitive data.
- **Request context propagation**: `x-request-id` is captured in middleware and attached to all logs and audit events, enabling correlation of errors across services.