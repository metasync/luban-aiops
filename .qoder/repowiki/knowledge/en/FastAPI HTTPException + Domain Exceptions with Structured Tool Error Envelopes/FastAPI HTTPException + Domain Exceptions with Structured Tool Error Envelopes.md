---
kind: error_handling
name: FastAPI HTTPException + Domain Exceptions with Structured Tool Error Envelopes
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - shared/shared-contracts/schemas/tool-result.schema.json
    - shared/shared-contracts/schemas/stream-event.schema.json
    - shared/shared-contracts/schemas/agent-stream-event.schema.json
    - shared/shared-contracts/schemas/policy-decision.schema.json
---

## Overview

The Agentic AIOps Platform is a Python monorepo of FastAPI microservices. Error handling follows a layered pattern: domain-level exceptions are raised in services, routes translate them into HTTP responses via `fastapi.HTTPException`, and tool/tool-gateway boundaries return structured error envelopes defined by shared JSON Schema contracts. There is no centralized exception handler registered per service — the default FastAPI exception-to-JSON behavior is relied upon.

## 1. What system/approach is used

- **Framework**: FastAPI is the HTTP framework across all services (`platform-gateway`, `tool-gateway`, `agent-platform`, `audit-service`, `identity-broker`, `incident-service`, `skills-hub`).
- **HTTP errors**: Routes raise `fastapi.HTTPException(status_code=..., detail=...)` directly. Status codes used consistently include 401 (missing/invalid auth), 403 (policy deny), 404 (not found), 409 (conflict — parked confirmations / session conflicts), 410 (expired confirmation), and 502 (upstream proxy failures).
- **Domain exceptions**: Each service defines small, typed exception classes for internal failure modes:
  - `ProviderConfigurationError(ValueError)` in `agent_service/providers/base.py` for invalid provider settings.
  - `TokenVerificationError(Exception)` in `platform_gateway/services/token_verifier.py` (and mirrored in `tool_gateway`) wrapping JWT verification failures; callers map it to 401.
  - `PolicyLoadError` in both gateway policy engines.
  - `ConfirmationExpired`, `ConfirmationNotFound`, `ConfirmationOwnerMismatch` in `agent_service/services/hitl_confirmations.py`, caught at route boundaries and mapped to 404/409/410.
- **Structured tool errors**: The tool execution layer does not raise exceptions to the caller. Instead, `tool_gateway/tools/base.py` provides `make_error_result(...)` and `make_denied_result(...)` which build a `ToolResult` dataclass whose shape is enforced by `shared/shared-contracts/schemas/tool-result.schema.json`. The schema mandates `status ∈ {"success", "error", "denied"}` and an `error` object with required `code` and `message` fields.
- **Streaming error frames**: For SSE streams, errors are emitted as typed events rather than HTTP errors. `agent_service/api/v2/routes.py` normalizes kernel stream chunks through `_normalize_stream_event`, which whitelists event types (`message_start`, `message_delta`, `message_end`, `error`, `tool_call`, `tool_result`, `confirmation_request`, `confirmation_result`) and coerces unknown types to `message_delta` for safety. A mid-stream `ConfirmationOwnerMismatch` yields an `error` frame with `{"code": "confirmation_owner_mismatch", ...}` instead of aborting the stream.

## 2. Key files and packages

| Area | File | Role |
|---|---|---|
| Agent platform routes | `products/agent-platform/src/agent_service/api/v2/routes.py` | Raises `HTTPException` for auth/session/conflict errors; emits `error` SSE frames; maps domain exceptions to 404/409/410 |
| Provider config | `products/agent-platform/src/agent_service/providers/base.py` | Defines `ProviderConfigurationError` |
| Token verification | `products/platform-gateway/src/platform_gateway/services/token_verifier.py` | Defines `TokenVerificationError`; callers convert to 401 |
| Gateway service | `products/platform-gateway/src/platform_gateway/services/gateway_service.py` | Maps upstream `httpx.HTTPStatusError` 4xx → pass-through, 5xx → 502; raises 401/403 for auth/policy |
| Tool gateway service | `products/tool-gateway/src/tool_gateway/services/gateway_service.py` | Same auth/policy posture; returns `ToolResult` with status 403 for denied, 400 for tool error |
| Tool result envelope | `products/tool-gateway/src/tool_gateway/tools/base.py` | `make_error_result`, `make_denied_result`, `ToolResult` dataclass |
| Shared schemas | `shared/shared-contracts/schemas/tool-result.schema.json`, `stream-event.schema.json`, `agent-stream-event.schema.json`, `policy-decision.schema.json` | Contractually enforce error/status shapes |
| App wiring | `products/*/src/**/app.py` | No custom exception handlers; only request logging middleware |

## 3. Architecture and conventions

- **Layered error propagation**: Low-level services raise typed exceptions or return structured results; route handlers translate them to HTTP semantics. Example: `resolve_request_identity` catches `TokenVerificationError` and raises `HTTPException(401)`. `enforce_policy` raises `HTTPException(403)` on deny.
- **Upstream proxy posture** (gateway services): When calling downstream services via `httpx`, 4xx responses are passed through unchanged so client errors (unknown session, expired confirmation) reach the caller verbatim; transport failures and 5xx are rewritten to 502 with a generic message. This preserves the anti-enumeration contract that foreign sessions return 404.
- **Policy denial is first-class**: Both gateways treat policy deny as a distinct error path — logged at `warning`, emitted to the durable audit trail, and returned as 403 with a `detail` dict containing `action`, `reason`, and `matched_rule_ids`.
- **Structured vs. HTTP errors**: Tool invocations never bubble Python exceptions to the caller; they produce a `ToolResult` with `status="error"` or `status="denied"` plus an `error.code`/`error.message` pair. HTTP endpoints use `HTTPException` because there is no global exception handler to normalize them uniformly.
- **SSE error framing**: Streaming endpoints emit `error`-type frames inside the stream when a terminal error occurs mid-flow (e.g., owner mismatch during confirmation resume), keeping the connection open while signaling failure.
- **No panics/recover**: Python `raise` is used exclusively; no `try/except Exception` blocks swallow errors except in defensive telemetry/logging fallbacks marked `# pragma: no cover - defensive fallback`.

## 4. Conventions and constraints

- **Auth errors are 401**: Missing `X-User-ID`, malformed `Authorization` header, missing token when `require_auth=True`, and any `TokenVerificationError` all surface as 401.
- **Policy denials are 403**: `enforce_policy` in both gateways raises 403 with a structured `detail` payload; tool-gateway tool invocation also returns 403 for denied tool calls.
- **Conflict/lock errors are 409**: Parked confirmations block new chat turns and session deletion, returning 409 with a human-readable `detail` explaining the pending confirmation.
- **Not-found is 404**: Unknown sessions, expired confirmations after concurrent resolution, and missing tool definitions yield 404.
- **Expired resources are 410**: Expired HITL confirmations return 410 `confirmation expired`.
- **Upstream failures are 502**: Proxy layers rewrite transport errors and upstream 5xx to 502 with a service-specific message.
- **Tool result schema is mandatory**: `tool-result.schema.json` requires `status ∈ {success, error, denied}` and an `error` object with `code` and `message`; `make_error_result` and `make_denied_result` are the only constructors, ensuring compliance.
- **Stream event schema constrains error frames**: `agent-stream-event.schema.json` defines an `error` field on `error` and failed `tool_result` frames; `_normalize_stream_event` whitelists known event types and drops unknown ones safely.
- **Audit trail mirrors errors**: Every policy decision (allow/deny) and tool invocation (success/error/denied) is emitted to the durable audit service regardless of outcome, including denied and errored paths.