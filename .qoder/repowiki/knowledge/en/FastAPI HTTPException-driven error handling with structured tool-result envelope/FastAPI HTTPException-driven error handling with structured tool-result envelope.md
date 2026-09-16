---
kind: error_handling
name: FastAPI HTTPException-driven error handling with structured tool-result envelopes
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/tool-gateway/src/tool_gateway/tools/registry.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
    - products/agent-platform/src/agent_service/services/shift_summary.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/services/execution_worker_client.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
---

## Overview

The Luban platform is a multi-product FastAPI workspace. Error handling is **not centralized in a shared error module**; instead, each product service defines its own boundaries and uses FastAPI's `HTTPException` at the API layer while returning structured `ToolResult` envelopes for internal tool execution. There are no global exception handlers registered — the default FastAPI behavior surfaces `HTTPException`s as JSON responses.

## API-layer errors (HTTP)

- **Primary mechanism**: `fastapi.HTTPException` raised directly in route handlers with an explicit `status_code` and a human-readable `detail` string. Observed across all services:
  - `agent-platform`: routes raise 401 (`X-User-ID header required`), 404 (`session not found`, `confirmation not found`, `document not found`, `incident not found`), 409 (`confirmation pending`, `no validated triage report`), 410 (`confirmation expired`), 422 (`skill target must be an absolute http(s) URL`, `unknown model id`), 502/503 (`skills service not configured`, upstream failures).
  - Errors from downstream clients are mapped explicitly: `IncidentClientRejected` → `exc.status_code`/`exc.message`; `IncidentServiceUnavailable` → 502; `IncidentDependencyNotConfigured` → 503; `SkillsServiceUnavailable` → 502; `SkillsDependencyNotConfigured` → 503.
- **No custom exception-to-status-code mapping** is registered in any `app.py`. The `create_app()` functions in `agent-platform`, `platform-gateway`, and `tool-gateway` only install an `http` middleware that logs `method/path/status_code/duration_ms` via `log_event`; they do not intercept or transform exceptions.
- **Request validation errors** come from Pydantic models attached to route signatures (e.g. `AgentChatRequest`) and are handled by FastAPI's built-in 422 machinery — no custom handler needed.
- **Header extraction helpers** like `_user_id` in `agent_service/api/v2/routes.py` short-circuit invalid input with 401 before reaching business logic.

## Service-domain exceptions (internal propagation)

Domain-specific exceptions are defined per service and caught at the boundary:

| Module | Exception classes | Purpose |
|---|---|---|
| `agent_service/services/hitl_confirmations.py` | `ConfirmationNotFound`, `ConfirmationExpired` | Parked HITL confirmation lifecycle |
| `agent_service/services/incident_client.py` | `IncidentClientError`, `IncidentNotFound`, `IncidentServiceUnavailable`, `IncidentDependencyNotConfigured`, `IncidentClientRejected` | Upstream incident-service communication |
| `agent_service/services/skills_client.py` | `SkillsClientRejected`, `SkillsServiceUnavailable`, `SkillsDependencyNotConfigured` | Upstream skills-hub communication |
| `agent_service/services/shift_summary.py` | `DigestInputError`, `UnknownSessionError`, `ForeignSessionDenied`, `DevelopmentSessionRejected` | Shift-summary generation |
| `agent_service/providers/base.py` | `ProviderConfigurationError(ValueError)` | LLM provider misconfiguration |
| `agent_service/runtime_kernel.py` | `UnknownModelError(ValueError)` | Model catalog lookup failure |
| `agent_service/services/execution_worker_client.py` | `WorkerHandoffError(Exception)` | Execution worker handoff |
| `platform_gateway/services/policy_engine.py` | `PolicyLoadError(Exception)` | Policy bundle load/validation failure |

These exceptions are **caught in route handlers** and re-raised as `HTTPException` with appropriate status codes, so callers never see domain types over the wire.

## Tool execution errors (structured envelopes)

The `tool-gateway` separates HTTP errors from tool-call errors. Tools return a `ToolResult` dataclass (`tool_gateway/tools/base.py`) with fields `tool_name`, `status` (`success` | `error` | `denied`), optional `data`, `evidence`, and optional `error` dict containing `code` and `message`. The registry's `invoke` method wraps every call:

```python
try:
    return await tool.execute(parameters, identity)
except Exception as exc:
    LOGGER.exception("tool execution failed: %s", name)
    return make_error_result(tool_name=name, code="TOOL_EXECUTION_ERROR", message=str(exc), ...)
```

- Unknown tool names return `make_error_result(code="TOOL_NOT_FOUND")`.
- Policy denials (e.g. mutating tools disabled) return `make_denied_result(code="POLICY_DENIED", reason=...)`.
- Evidence is always attached via `build_evidence(risk_level, source_system, duration_ms)`.
- This envelope matches `shared/shared-contracts/schemas/tool-result.schema.json`, making tool errors part of the cross-product contract rather than HTTP responses.

## Middleware and observability (not error transformation)

Each service installs an `@app.middleware("http")` named `log_requests` that records `method`, `path`, `status_code`, and `duration_ms` through `core.observability.log_event`. It does **not** catch or rewrite exceptions — it simply observes the response after `call_next` returns, whether successful or error.

## Conventions observed

1. **Fail closed on unknown inputs**: parameter/model validation rejects early with 422; missing auth headers reject with 401.
2. **Downstream failures map to distinct HTTP codes**: unconfigured dependency → 503, unreachable/upstream 5xx → 502, client rejection → pass-through `exc.status_code`.
3. **Domain exceptions stay internal**: route handlers translate them to `HTTPException`; callers never receive service-internal types.
4. **Tool invocations never raise over HTTP**: the registry swallows exceptions into a `ToolResult.error` envelope, preserving a stable schema for agents consuming tools.
5. **No global exception handler**: error shape is determined by where `HTTPException` is raised, not by a central mapper.
6. **Structured logging accompanies errors**: `LOGGER.exception` is used when catching unexpected exceptions in tool dispatch; route-level errors are logged by the request middleware which captures the resulting status code.