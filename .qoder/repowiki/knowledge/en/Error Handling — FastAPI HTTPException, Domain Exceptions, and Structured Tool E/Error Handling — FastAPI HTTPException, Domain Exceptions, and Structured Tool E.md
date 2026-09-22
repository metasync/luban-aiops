---
kind: error_handling
name: Error Handling — FastAPI HTTPException, Domain Exceptions, and Structured Tool Errors
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/agent-platform/src/agent_platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/execution_worker_client.py
    - products/tool-gateway/src/tool_gateway/tools/secrets_connector.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/platform-gateway/src/platform_gateway/api/routes/incidents.py
---

## Overview

The Luban platform uses a layered error-handling strategy across its nine Python services (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway). At the API boundary every service is a FastAPI application that raises `fastapi.HTTPException` with explicit `status_code` and `detail` payloads. Inside services, domain-specific exceptions are raised to represent business failures, and cross-process calls wrap transport errors into typed exceptions. Tools return structured error results rather than raising exceptions.

## API Boundary: FastAPI HTTPException

Every product service defines its own `app.py` that creates a `FastAPI` instance and mounts an HTTP middleware for request logging; none of them register custom exception handlers. Errors surface as `HTTPException` instances:

- **Authentication / authorization**: 401 for missing or malformed tokens (`platform_gateway/services/gateway_service.py` raises 401 on invalid bearer headers and when `require_auth` is true); 403 for policy denials via `enforce_policy`, which wraps the policy engine's decision into a 403 with `{detail, action, reason}`.
- **Client errors**: 400/404/409/410/422 used directly in route handlers (e.g. agent-platform routes raise 404 for missing sessions/incidents, 409 for duplicate sessions, 410 for expired confirmations, 422 for validation failures).
- **Upstream failures**: 502/503 are used when downstream services are unreachable or misconfigured (audit, identity, agent services in platform-gateway; execution worker in agent-platform routes).

The pattern is consistent: routes call service functions, and services either raise `HTTPException` directly or let upstream `httpx` errors be caught and re-raised as `HTTPException` with a stable status code and human-readable detail.

## Domain Exceptions (in-process)

Services define small, purpose-built exception classes to distinguish failure modes within a process:

- `WorkerHandoffError` and `WorkerHandoffTimeout` in `execution_worker_client.py`: fail-closed handoff failures carry a string `reason` (e.g. `worker_unavailable`) so callers can decide whether to retry or surface a timeout receipt.
- `IncidentClientError`, `SkillsClientError`, `DigestInputError`, `UnknownSessionError`, `PasswordPolicyError` in various services/tools — each represents a specific failure class that callers handle explicitly.

These exceptions are never serialized over the wire; they are converted to `HTTPException` at the boundary or to structured tool results inside tools.

## Cross-Process Error Propagation

Cross-service calls use `httpx.AsyncClient` with bounded timeouts and convert transport errors into typed exceptions:

- `execution_worker_client.handoff` catches `httpx.TimeoutException` → `WorkerHandoffTimeout`; catches `httpx.HTTPError` → `WorkerHandoffError(reason="worker_unavailable")`. Non-200 responses are parsed for a structured `{error: {reason}}` payload; unparsable bodies degrade to `worker_unavailable`.
- `platform_gateway.services.gateway_service._identity_leg` catches `httpx.HTTPStatusError < 500` and re-raises the upstream status code with the upstream `detail` body; ≥500 and transport errors become 502 with stable messages like "identity service unavailable".
- Agent-platform routes catch `WorkerHandoffError` and map it to 503/502/404 depending on context.

This ensures clients see stable HTTP semantics even when internal workers or downstream services fail.

## Tool-Level Errors: Structured Results

Tools do not raise exceptions to callers; they return a `ToolResult` produced by `make_error_result`, which carries a stable `error_code` string alongside a message. Examples from `secrets_connector.py`:

- `INVALID_PARAMETERS` for bad inputs
- `EMAIL_NOT_CONFIGURED`, `EMAIL_RECIPIENT_NOT_ALLOWED`
- `UPSTREAM_ERROR` for transient failures

The delivery outcome object also carries an `error_code` field, enabling callers (and the portal) to render user-friendly messages without parsing free-form text. This pattern keeps tool contracts machine-readable and testable.

## Middleware and Logging

Each service registers an `@app.middleware("http")` that logs `method`, `path`, `status_code`, and `duration_ms` via a shared `log_event` helper. There is no global error handler that transforms exceptions; instead, the middleware observes the final response status code after FastAPI converts `HTTPException` to JSON. Request correlation IDs flow through `x-request-id` resolved by `resolve_request_id`.

## Conventions Observed

- **Never log raw transport payloads** in error paths: `execution_worker_client` logs only `exc.__class__.__name__` because transport messages may echo URLs or credentials.
- **Fail-closed posture**: missing configuration (e.g. execution worker URL/token) raises before any network call.
- **Stable status codes**: upstream client errors (<500) are proxied with their original status; upstream server errors and transport failures are normalized to 502/503.
- **Structured reasons**: domain errors carry a string `reason` or `error_code` field so consumers can branch on machine-readable values while still showing a human `detail`/message.
- **No panics/recover**: Python `raise` is used exclusively; no `try/except Exception` blocks swallow errors silently, and no `panic` equivalent exists in this Python codebase.
- **No centralized exception handler**: each service relies on FastAPI's default `HTTPException` serialization; there is no `@app.exception_handler(Exception)` registered anywhere.