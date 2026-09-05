---
kind: error_handling
name: Structured HTTP Error Model with Domain-Specific Exception Types Across Microservices
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/incident-service/src/incident_service/api/routes/incidents.py
    - products/incident-service/src/incident_service/services/normalization.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/agent-platform/src/agent_service/core/request_context.py
---

## Overview

The Luban platform uses a consistent, layered error-handling model across its Python microservices (agent-platform, platform-gateway, tool-gateway, audit-service, incident-service, identity-broker, skills-hub). Errors are expressed as domain-specific Python `Exception` subclasses in service layers and translated to standardized FastAPI `HTTPException` responses at the API boundary. There is no centralized exception base class; instead each product defines its own small set of typed exceptions that callers catch to decide whether to pass through, map, or wrap them.

## Core patterns

### 1. Domain-layer exceptions (service internals)
Each service defines purpose-built exception classes in its `services/` or `core/` packages:
- `platform_gateway`: `TokenVerificationError` (`token_verifier.py`) for JWT failures; `PolicyLoadError` (`policy_engine.py`) for invalid policy bundles.
- `tool_gateway`: `PolicyLoadError` (`services/policy_engine.py`).
- `audit_service`: `StoreError` (`services/audit_store.py`), `IngestAuthError` (`services/ingest_auth.py`).
- `incident_service`: `SettingsError`, `ConnectorConfigError`, `NormalizationError`, `StoreError`, `QueryAuthError`.
- `agent_platform`: route handlers raise `HTTPException` directly rather than domain exceptions.

These exceptions carry a human-readable `detail` string and are raised with `from <cause>` chaining so the original traceback is preserved.

### 2. Gateway-side upstream error mapping
The platform gateway (`platform_gateway/services/gateway_service.py`) implements a uniform posture when calling downstream services via `httpx`:
- `httpx.HTTPStatusError` with status `< 500` → re-raise as `HTTPException(status_code=..., detail=...)`, preserving the client-facing 4xx posture (e.g. unknown session, expired confirmation).
- `httpx.HTTPStatusError` with status `>= 500` → translate to `HTTPException(502, "...failed" / "...unavailable")`.
- Generic `httpx.HTTPError` (timeouts, DNS) → `HTTPException(502, "agent service unavailable")`.

This pattern is repeated verbatim for every proxied operation: `get_session`, `list_sessions`, `delete_session`, `create_document`, `publish_document`, `delete_document`, `chat_stream`, `chat_confirm`, etc., ensuring callers never see raw 500s from an upstream outage.

### 3. Identity-leg posture
The `_identity_leg` helper normalizes calls to the identity broker: 4xx errors pass through with their structured `detail` body (parsed from JSON when present); any 5xx or transport failure becomes `HTTPException(502, "identity service unavailable — retry the sign-in")`. This guarantees the sign-in surface never leaks raw 500s during rollout races.

### 4. Policy enforcement returns structured 403
`enforce_policy()` raises `HTTPException(403, detail={"detail": "action denied by policy", "action": ..., "reason": ...})` on deny decisions, and logs + emits an audit event for every decision. The same function is used by both the platform gateway and the tool gateway.

### 5. Service-local HTTP error helpers
Services that do not use FastAPI's built-in validation return `JSONResponse(status_code=..., content={"detail": ...})` directly:
- `audit_service` routes return `JSONResponse(status_code=401, content={"detail": str(exc)})` for auth failures and `status_code=400` for malformed bodies.
- `incident_service` exposes a local `_error(status_code, code, message)` helper returning `JSONResponse` with a `{code, message}` envelope.
- `tool_gateway` sometimes returns `JSONResponse(content=result.to_dict(), status_code=403)` for policy-denied tool invocations.

### 6. Request correlation and observability
Errors are correlated via `x-request-id`, resolved by `resolve_request_id()` in `agent_service/core/request_context.py` (inbound header wins, else OTel trace_id, else generated UUID). The gateway injects this header into all upstream calls via `_service_headers()`. Metrics capture response status codes uniformly under `core/metrics.py` in each service.

### 7. Readiness/liveness degradation reporting
`ready_status()` in the gateway catches `httpx.HTTPError` and `PolicyLoadError` and returns `{"status": "degraded", ...}` with the error embedded, so probes can distinguish a healthy but partially degraded service from a fully failed one.

### 8. No panics / no global middleware
There is no `try/except Exception` blanket handler, no `@app.exception_handler` override, and no `panic`/`recover` equivalent. Errors bubble to FastAPI's default exception handler, which serializes `HTTPException` into JSON. Business logic errors stay as typed exceptions until they reach the API layer where they are mapped.

## Conventions observed

| Concern | Convention | Where enforced |
|---|---|---|
| Client errors (4xx) from upstream | Pass through unchanged | All gateway proxy functions in `gateway_service.py` |
| Upstream server errors (5xx) | Map to 502 with a stable `detail` string | Same proxy functions |
| Transport failures | Map to 502 `"...unavailable"` | Same proxy functions |
| Policy denial | Raise `HTTPException(403, structured detail)` | `enforce_policy()` |
| Token verification failure | Raise `TokenVerificationError`, caught and converted to 401 | `resolve_request_identity()` |
| Invalid policy bundle | Raise `PolicyLoadError`, surfaced via readiness as `degraded` | `load_bundle()` |
| Audit ingest/auth failure | Return `JSONResponse(401/400, {"detail": ...})` | `audit_service/api/routes/*.py` |
| Request ID propagation | Injected as `x-request-id` on all outbound calls | `_service_headers()` |

## Key files

- `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — upstream error mapping, policy enforcement, streaming error handling
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError`
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError`, `PolicyDecision`, deny-by-default semantics
- `products/tool-gateway/src/tool_gateway/services/policy_engine.py` — `PolicyLoadError` (tool-gateway variant)
- `products/agent-platform/src/agent_service/api/v2/routes.py` — direct `HTTPException` usage for session/confirmation errors
- `products/audit-service/src/audit_service/services/audit_store.py` — `StoreError`
- `products/audit-service/src/audit_service/services/ingest_auth.py` — `IngestAuthError`
- `products/incident-service/src/incident_service/api/routes/incidents.py` — `_error` helper
- `products/incident-service/src/incident_service/services/normalization.py` — `NormalizationError`
- `products/incident-service/src/incident_service/services/connectors.py` — `ConnectorConfigError`
- `products/incident-service/src/incident_service/services/query_auth.py` — `QueryAuthError`
- `products/agent-platform/src/agent_service/core/request_context.py` — request ID resolution
- `shared/shared-contracts/schemas/policy-decision.schema.json` — contract for policy decision payloads returned on 403