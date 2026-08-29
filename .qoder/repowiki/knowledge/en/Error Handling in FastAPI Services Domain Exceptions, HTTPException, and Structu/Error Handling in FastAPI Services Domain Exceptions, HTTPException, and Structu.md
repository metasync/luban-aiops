---
kind: error_handling
name: 'Error Handling in FastAPI Services: Domain Exceptions, HTTPException, and Structured Error Envelopes'
category: error_handling
scope:
    - '**'
source_files:
    - products/incident-service/src/incident_service/api/routes/incidents.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/agent-platform/src/agent_service/providers/base.py
    - shared/shared-contracts/schemas/health-response.schema.json
    - shared/shared-contracts/schemas/policy-decision.schema.json
---

## Overview

The repository is a multi-service Python platform (FastAPI) where each product (`incident-service`, `platform-gateway`, `tool-gateway`, `agent-platform`, `audit-service`, `identity-broker`, `skills-hub`) implements its own error handling. There is no shared exception hierarchy or global exception handler — instead, services follow consistent local patterns.

## Patterns Observed Across Services

### 1. Domain-Specific Exception Classes
Each service defines narrow exception types in its `services/` layer to separate business failures from transport errors:
- `incident_service.services.query_auth.QueryAuthError` — raised when caller authentication fails; routes catch it and return 401 with a structured `{error: {code, message}}` envelope via a local `_error()` helper.
- `platform_gateway.services.token_verifier.TokenVerificationError` — wraps JWT verification failures (expired, invalid issuer/audience, malformed); caught by `resolve_request_identity` which maps it to `HTTPException(401)`.
- `platform_gateway.services.policy_engine.PolicyLoadError` — raised when the policy YAML bundle is missing, malformed, or unparseable; surfaced through readiness checks as `status: degraded`.
- `audit_service.services.audit_store.StoreError` / `IngestAuthError` — domain exceptions for store and ingest auth failures.
- `identity_broker.services.exchange_service.ExchangeError` — carries both a message and an HTTP status code (e.g. 401).
- `agent_platform.providers.base.ProviderConfigurationError(ValueError)` — configuration validation errors for LLM provider backends.

### 2. Route-Level Error Mapping
Routes are thin: they call into services and translate domain exceptions into HTTP responses. Two styles coexist:
- **Structured JSON envelope** (`incident-service`): a private `_error(status_code, code, message)` helper returns `JSONResponse({"error": {"code": ..., "message": ...}})`. Codes include `UNAUTHORIZED`, `INVALID_PAYLOAD`, `INVALID_PARAMETERS`, `INCIDENT_NOT_FOUND`, `REPORT_NOT_FOUND`.
- **FastAPI `HTTPException`** (`platform-gateway`, `identity-broker`, `agent-platform`): routes raise `HTTPException(status_code=..., detail=...)` directly. The gateway uses this for auth failures (401), policy denials (403 with nested `{detail, action, reason}`), and upstream proxy failures.

There is no global `@app.exception_handler` registered in any of the examined `app.py` files; error mapping happens inline at the route boundary.

### 3. Policy Enforcement Errors
Policy decisions flow through `platform_gateway.services.gateway_service.enforce_policy()`, which evaluates the loaded rule bundle and raises `HTTPException(403)` on deny, carrying `{detail: "action denied by policy", action, reason}`. The same decision is mirrored to the audit trail via `emit_audit_event` before raising.

### 4. Tool Execution Error Results
The tool execution framework (`tool_gateway.tools.base.BaseTool`) does not raise exceptions for tool failures. Instead, tools return a `ToolResult` dataclass whose `status` field is one of `success | error | denied`. Helpers `make_error_result(...)` and `make_denied_result(...)` build standardized error envelopes with `{code, message}` inside an `error` field, plus an `evidence` sub-object containing `executed_at`, `duration_ms`, `risk_level`, `source_system`. This keeps tool invocations non-exceptional so the orchestrator can handle partial failures across multiple tools.

### 5. Upstream Client Errors
Outbound HTTP calls use `httpx.AsyncClient` and call `response.raise_for_status()` (e.g., `platform_gateway.services.gateway_service`). Failures propagate as `httpx.HTTPError` and are either re-raised to the caller or converted to `HTTPException` by the route layer.

### 6. Startup-Time Validation
Services validate configuration at startup rather than failing lazily:
- `incident_service.app.lifespan` calls `build_connectors(settings)` and `store.initialize()` during lifespan setup; unknown connector names fail startup fast (per SPEC-015 R-5 comment).
- `platform_gateway.services.policy_engine.load_bundle` raises `PolicyLoadError` if the configured policy path is missing or YAML is invalid, preventing the service from starting with a bad policy.

### 7. Observability Integration
Errors are consistently logged with structured context via `log_event(LOGGER, event_name, ...)`, including `request_id`, `service`, `status_code`, and domain-specific fields. A per-request `http_request` middleware logs every request's method, path, status code, and duration.

### 8. Shared Contract Schemas
Error-related shapes are codified in `shared/shared-contracts/schemas/`:
- `health-response.schema.json` constrains health endpoints to `{status: "ok"|"degraded", service, version?}`.
- `policy-decision.schema.json` constrains policy decisions to `{decision: "allow"|"deny", matched_rule_ids, reason, action?, subject?}`.
- `tool-result.schema.json` (referenced by `ToolResult.to_dict`) standardizes tool invocation results.

## Conventions and Constraints

- **No global exception handlers**: Each service handles errors at the route boundary; there is no centralized `@app.exception_handler` in the examined `app.py` files.
- **Domain exceptions stay in services**: Routes catch domain exceptions and convert them to HTTP responses; services never import `fastapi.HTTPException` except in the gateway where it is the transport surface.
- **Structured error envelopes**: When returning JSON, services use `{error: {code, message}}` (incident-service) or FastAPI's `HTTPException.detail` (gateway/identity-broker). There is no single enforced schema for error bodies.
- **Deny-by-default policy**: The policy engine defaults to `deny` when no rule matches; callers must explicitly allow actions.
- **Tool failures are non-exceptional**: Tools return `ToolResult` with `status="error"` or `status="denied"` rather than raising, enabling partial failure handling in multi-tool workflows.
- **Startup validation**: Configuration and dependency validation happen during app lifespan or module load, not deferred to first request.
- **Request-scoped logging**: Every response is logged with `x-request-id`, `method`, `path`, `status_code`, and `duration_ms` via a common middleware pattern.