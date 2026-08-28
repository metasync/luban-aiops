---
kind: error_handling
name: FastAPI HTTPException + Domain-Specific Exceptions with Deny-by-Default Policy Errors
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/execution-runtime/src/execution_runtime/services/executor.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/platform-gateway/src/platform_gateway/api/routes/policy.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/agent-platform/src/agent_service/app.py
    - products/incident-service/src/incident_service/app.py
    - products/skills-hub/src/skills_hub/app.py
---

# Error Handling in the Luban AIOps Platform

## Overview

The platform is a collection of independent FastAPI services (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) that share a consistent error-handling approach: domain-specific Python exceptions bubble up to route handlers, which translate them into `fastapi.HTTPException` responses with explicit HTTP status codes. There is no centralized exception-to-HTTP-status middleware; each service's routes are responsible for mapping local errors to appropriate status codes.

## Core Patterns

### 1. Domain-Specific Exception Classes

Each service defines small, purpose-built exception classes near the code that raises them:

- **Policy loading**: `PolicyLoadError` in both `platform_gateway/services/policy_engine.py` and `tool_gateway/services/policy_engine.py` — raised when a YAML policy bundle is missing, malformed, or contains invalid rules/fields.
- **Authentication**: `IngestAuthError` (`audit_service/services/ingest_auth.py`), `TokenVerificationError` (`platform_gateway/services/token_verifier.py`, `tool_gateway/services/token_verifier.py`), `ExchangeError` (`identity_broker/services/exchange_service.py`), `QueryAuthError` / `SettingsError` / `StoreError` across services.
- **Domain failures**: `WorkerHandoffError`, `UnknownSessionError`, `DigestInputError`, `TriageError`, `NormalizationError`, `ConnectorConfigError`, `StoreError`, `ProviderConfigurationError`, `UnknownModelError`, `SettingsError`, `SettingsError`.

These exceptions carry human-readable messages and are never returned over the wire directly — they are always caught at the API boundary and converted to HTTP responses.

### 2. Route-Level Mapping to HTTPStatusCodes

Route handlers catch domain exceptions and raise `HTTPException` with explicit status codes:

| Status | Meaning | Example |
|--------|---------|---------|
| 400 | Client validation / malformed input | agent-platform chat request body, incident-service query store errors |
| 401 | Authentication failure | missing/invalid Authorization header, expired workload token, invalid Basic credentials |
| 403 | Authorization denied by policy | tool-gateway policy engine deny, platform-gateway RBAC deny |
| 404 | Resource not found | confirmation not found, session not found |
| 409 | Conflict (duplicate state) | session already exists, confirmation conflict |
| 410 | Expired resource | confirmation expired |
| 422 | Validation error | model catalog lookup |
| 502 | Upstream service unavailable | agent/audit/incident/skills/tool gateway calls fail |
| 503 | Service not configured / policy bundle unavailable | audit service not configured, policy bundle load fails |

Example from `platform_gateway/services/gateway_service.py`: upstream `httpx.HTTPStatusError` is inspected — if the status is 4xx it is re-raised as-is, otherwise mapped to 502 with a generic "service unavailable" detail.

### 3. No Global Exception Handler

Each service's `app.py` registers only an `http` middleware that logs every request/response pair (method, path, status_code, duration_ms, request_id). There is no global `@app.exception_handler` that converts unhandled exceptions to JSON responses — FastAPI's default exception handler produces its own JSON error shape, while handled exceptions go through `HTTPException(status_code=..., detail=...)`.

### 4. Structured Error Results for Internal Calls

The execution-runtime worker (`execution_runtime/services/executor.py`) does not raise exceptions on tool invocation failures. Instead, it returns a structured dict with `status: "error"`, `error.code` (e.g. `TIMEOUT`, `TRANSPORT_ERROR`, `BAD_GATEWAY_RESPONSE`, `NO_CREDENTIAL`, `NO_GATEWAY`), and `error.message`. This lets the handoff route always sign a receipt regardless of failure mode, and callers map `error.code == "TIMEOUT"` to a terminal `timeout` state and everything else to `failed`.

### 5. Policy Engine Errors Fail Hard

Both `platform_gateway/services/policy_engine.py` and `tool_gateway/services/policy_engine.py` implement deny-by-default policy evaluation. If the configured policy bundle file is missing or invalid, `load_bundle()` raises `PolicyLoadError` — there is no silent fallback to the packaged default when a path is explicitly configured. The platform-gateway exposes this via `/api/v1/policy/bundle` which maps `PolicyLoadError` to 503 "policy bundle unavailable".

### 6. Cross-Service Error Propagation

Gateway services (platform-gateway, tool-gateway) wrap downstream HTTP calls with httpx and translate transport failures into 502/503 responses:

```python
except httpx.HTTPError as exc:
    raise HTTPException(status_code=502, detail="... service unavailable")
```

Audit emitter clients log warnings and raise `RuntimeError("ingest rejected with {status_code}")` when the audit service returns >= 300, letting the caller decide whether to surface it.

### 7. Request Context & Correlation

Every service's `http` middleware resolves an `x-request-id` header via `resolve_request_id()` and includes it in all `log_event` calls. Errors are therefore correlated end-to-end through the same request ID even though they cross multiple services.

## Conventions Observed

- **Never swallow exceptions silently** — policy bundle load failures raise instead of falling back; unknown connector names fail startup fast.
- **Distinguish auth vs authz** — 401 for authentication failures (bad token, missing credential), 403 for authorization denials (policy engine deny).
- **Upstream failures are 5xx** — client errors from downstream services are passed through (4xx), but transport timeouts/unreachability become 502/503.
- **Structured internal errors** — internal service-to-service calls return typed result dicts with `error.code` rather than raising, so callers can branch on specific failure modes without network-layer coupling.
- **No panics/recover** — Python has no panic/recover; the equivalent pattern is catching broad exceptions at boundaries and converting to HTTP responses.
- **Tests exercise error paths** — each service has tests named after error scenarios (e.g. `test_contracts.py`, `test_policy_engine.py`, `test_execution_worker_client.py`, `test_k8s_connector.py`) verifying status code mapping.

## Key Files

- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError`, deny-by-default evaluation, approval tiers
- `products/tool-gateway/src/tool_gateway/services/policy_engine.py` — same pattern, skips require_approval rules (no approval substrate)
- `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — upstream error translation to 401/403/502
- `products/tool-gateway/src/tool_gateway/services/gateway_service.py` — same pattern for tool invocations
- `products/execution-runtime/src/execution_runtime/services/executor.py` — structured error results with `error.code` vocabulary
- `products/audit-service/src/audit_service/services/ingest_auth.py` — `IngestAuthError` → 401 mapping
- `products/identity-broker/src/identity_service/services/exchange_service.py` — `ExchangeError` → 401 mapping
- `products/*/src/*_service/app.py` — per-service `http` middleware logging status_code
- `products/platform-gateway/src/platform_gateway/api/routes/policy.py` — maps `PolicyLoadError` to 503
- `products/agent-platform/src/agent_service/api/v2/routes.py` — route-level `HTTPException` usage (409, 410, 422, 404, 400)