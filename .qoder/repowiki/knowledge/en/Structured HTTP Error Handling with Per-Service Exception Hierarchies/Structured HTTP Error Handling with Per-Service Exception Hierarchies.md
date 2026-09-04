---
kind: error_handling
name: Structured HTTP Error Handling with Per-Service Exception Hierarchies
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/session_service.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/identity-broker/src/identity_service/api/routes/identity.py
---

## What system/approach is used

The platform uses FastAPI as the HTTP framework across all Python services and handles errors by raising `fastapi.HTTPException` directly from route handlers and service functions. There are no global exception handlers registered in any service (`app.exception_handler` is never used); instead, each route or service layer catches lower-level exceptions (e.g. `httpx.HTTPError`, domain-specific exceptions) and re-raises them as `HTTPException` with an explicit `status_code` and a short human-readable `detail` string. The only cross-cutting error surface is a per-service logging middleware that records every request/response pair including status code — it does not transform errors.

## Key files and packages

- **Agent Platform (`agent_service/api/v2/routes.py`)**: Central hub where domain-layer exceptions are mapped to HTTP responses. It imports and catches structured client exceptions (`IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentClientRejected`, `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`) and converts them to 503/502/4xx `HTTPException`s. It also defines local helpers like `_user_id` that raise 401 for missing headers.
- **Domain exception hierarchies**:
  - `agent_service/services/hitl_confirmations.py`: Defines `ConfirmationNotFound` and `ConfirmationExpired` (both subclasses of `LookupError`) raised by the in-memory confirmation registry during HITL bridging; routes catch these to return 409/410.
  - `agent_service/services/incident_client.py`: Defines `IncidentClientError` base plus `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`; transport failures log at `warning` level before re-raising.
  - `agent_service/services/skills_client.py`: Mirrors the incident-client pattern with `SkillsClientError`, `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`.
- **Identity Broker (`identity_service/api/routes/auth.py`, `identity_service/api/routes/identity.py`)**: Raises 401 for missing/malformed `Authorization` headers and propagates upstream auth errors as 401.
- **Gateway services (`platform_gateway/services/gateway_service.py`, `tool_gateway/services/gateway_service.py`)**: Raise 401 for malformed authorization headers and propagate upstream auth errors.
- **Session service (`agent_service/services/session_service.py`)**: Raises 404 for unknown sessions and intentionally returns 404 (never 403) when a user accesses another user's session — an anti-enumeration convention documented in a comment.
- **App bootstraps (`platform_gateway/app.py`, `tool-gateway/app.py`)**: Register only an HTTP logging middleware that emits structured `http_request` events with method, path, status_code, duration_ms; no error transformation occurs here.

## Architecture and conventions

1. **Per-service exception hierarchy**: Each outbound client (incident, skills) defines a small tree rooted at a service-specific `*ClientError` base class. This lets callers distinguish configuration errors (503), transport/upstream 5xx errors (502), and upstream 4xx errors (passed through with their original status code).
2. **Routes are the boundary**: Domain/service layers raise typed exceptions; route handlers translate them into `HTTPException(status_code=..., detail=...)`. No raw stack traces or internal exception types leak over HTTP.
3. **Status-code mapping rules observed in code**:
   - Missing auth header → 401.
   - Unknown resource (session, document, incident) → 404.
   - Foreign ownership on a known resource → 404 (not 403) to avoid enumeration.
   - Conflict (duplicate confirmation, model already pinned) → 409.
   - Unknown model id → 422.
   - Dependency not configured → 503.
   - Transport failure / upstream 5xx → 502.
   - Upstream 4xx → passed through with original status code and upstream message.
4. **Fail-open bookkeeping**: Non-critical side effects (session title pinning, evidence deletion, confirmation-record cleanup) are wrapped in try/except blocks that log warnings but never fail the primary operation — delete-session continues even if state/evidence/confirmation cleanup fails.
5. **Single-flight guarantees via exceptions**: The confirmation registry uses `ConfirmationNotFound` vs `ConfirmationExpired` to coordinate between confirm and expiry paths so a parked batch is never resumed twice.
6. **No global error handler**: Services rely on FastAPI's default `HTTPException` renderer; there is no custom JSON error envelope defined.
7. **Request tracing**: Every request is logged with `x-request-id` (resolved from headers or generated), enabling correlation of errors across the gateway → agent-platform chain.

## Conventions and constraints

- **Never expose raw tracebacks**: All client modules explicitly wrap `httpx.HTTPError` and upstream responses, logging at warning level and raising a typed exception with a stable message. Route handlers then convert those to `HTTPException`.
- **Use `from None` or `from exc` consistently**: When wrapping an upstream error into `HTTPException`, routes use `from None` to suppress the inner traceback (e.g. 503/502 cases) and `from exc` when preserving context (e.g. passing through an upstream 4xx `HTTPException`).
- **404 over 403 for authorization failures on resources**: Session access checks deliberately return 404 for foreign users so clients cannot enumerate valid session IDs by observing 403 vs 404.
- **Configuration gating**: Outbound dependencies are checked via `is_configured()` before any network call; misconfiguration raises a dedicated `*DependencyNotConfigured` exception that maps to 503.
- **Best-effort cleanup**: Destructive operations (delete session) proceed even if secondary stores (state, evidence, confirmation records, execution records) fail to clean up — cleanup is logged and ignored.