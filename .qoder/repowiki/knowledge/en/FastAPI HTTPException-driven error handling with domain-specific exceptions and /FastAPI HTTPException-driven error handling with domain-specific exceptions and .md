---
kind: error_handling
name: FastAPI HTTPException-driven error handling with domain-specific exceptions and structured tool results
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/session_service.py
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
---

## What system/approach is used

The codebase uses **FastAPI's built-in `HTTPException`** as the primary mechanism for translating application errors into HTTP responses. There are no custom exception-to-HTTP-middleware converters (`@app.exception_handler`, `@router.exception_handler`) — routes raise `HTTPException(status_code=..., detail=...)` directly, letting FastAPI serialize them to JSON responses. For non-HTTP boundaries (tool execution framework), errors are returned as structured `ToolResult` objects with a `status` field of `"success" | "error" | "denied" | "approved" | "expired" | "interrupted"` and an `error` dict containing `code` and `message`. Domain-layer failures use small, purpose-built Python exception classes rather than generic `Exception`s.

## Key files and packages

- **Agent Platform v2 routes**: `products/agent-platform/src/agent_service/api/v2/routes.py` — raises `HTTPException` for auth failures (401), model validation (422), session conflicts (409), expired confirmations (410), missing sessions/documents (404).
- **Session service**: `products/agent-platform/src/agent_service/services/session_service.py` — centralizes 404 semantics; foreign-session access is deliberately indistinguishable from unknown-session via 404 (anti-enumeration convention).
- **HITL confirmation registry**: `products/agent-platform/src/agent_service/services/hitl_confirmations.py` — defines `ConfirmationNotFound` and `ConfirmationExpired` (both subclass `LookupError`); callers map these to 409/410 in routes.
- **Provider configuration**: `products/agent-platform/src/agent_service/providers/base.py` — defines `ProviderConfigurationError(ValueError)` raised when provider settings are incomplete or invalid.
- **Policy engine**: `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — defines `PolicyLoadError(Exception)` for malformed policy bundles; load-time failures are fatal (no silent fallback) per docstring: "path set + missing/invalid → raise PolicyLoadError (no silent fallback)".
- **Identity broker auth routes**: `products/identity-broker/src/identity_service/api/routes/auth.py` — maps downstream `httpx.HTTPStatusError` to 502 and re-raises upstream `ExchangeError` with its own status code/detail.
- **Tool execution framework**: `products/tool-gateway/src/tool_gateway/tools/base.py` — `ToolResult` dataclass with `status` enum-like values and helper constructors `make_error_result()` / `make_denied_result()` that produce standardized `{"code": ..., "message": ...}` error payloads.

## Architecture and conventions

1. **HTTP boundary = `HTTPException`**. Every route handler converts domain errors into `HTTPException` with explicit `status_code` and human-readable `detail`. There is no centralized exception handler; FastAPI's default serializer is relied on.

2. **Domain exceptions stay below the API layer**. Services like `hitl_confirmations` and `providers.base` raise typed exceptions (`ConfirmationNotFound`, `ConfirmationExpired`, `ProviderConfigurationError`). Routes catch these and translate them to appropriate HTTP codes. This keeps business logic free of HTTP concerns.

3. **Fail-open bookkeeping pattern**. Non-critical side effects (session title updates, model pinning, evidence loading, confirmation record reads) are wrapped in `try/except Exception` blocks that log via `LOGGER.warning(...)` and degrade gracefully instead of failing the request. See `session_service.py`'s `mark_session_turn`, `pin_session_model`, and `delete_session`; `routes.py`'s `_load_evidence_turns`, `_load_confirmation_cards`, and confirmation claim-time resolution.

4. **Structured tool errors, not exceptions**. The tool gateway does not propagate exceptions over the wire. Tools return `ToolResult` with `status="error"` plus an `error={"code": ..., "message": ...}` envelope, produced via `make_error_result()`. Policy denials use `make_denied_result()` with `status="denied"` and `code="POLICY_DENIED"`. This lets the agent kernel surface tool failures as first-class stream events without crashing the runtime.

5. **Deny-by-default policy errors are load-time failures**. `policy_engine.load_bundle()` raises `PolicyLoadError` if a configured bundle path is missing or malformed — there is no runtime fallback to a safe default. Packaged defaults are only used when no path is configured.

6. **Anti-enumeration via 404-for-foreign-access**. `session_service._assert_session_owner` raises 404 when a user accesses another user's session, making foreign IDs indistinguishable from unknown ones. This is documented as a deliberate security choice.

7. **No `raise ... from None` suppression for user-facing errors**. Most `HTTPException` raises preserve the chain (e.g., identity broker re-raises `httpx.HTTPStatusError` with `from exc`). Only internal retries where the original stack adds noise use `from None` (e.g., parked confirmation retry in routes).

8. **Streaming error frames**. The SSE stream normalizer accepts an `error` event type and passes through `error` dicts from the kernel, so tool/runtime errors flow to clients as structured stream events rather than HTTP failures.

## Conventions and constraints

- **Every route must raise `HTTPException` for client errors**; do not return bare strings or tuples — FastAPI will not format them consistently.
- **Service functions should raise domain exceptions**, not `HTTPException`; let the route layer decide the HTTP mapping.
- **Non-critical store operations must be fail-open**: wrap in `try/except Exception`, log with `LOGGER.warning(...)`, and continue with degraded state rather than propagating the error.
- **Tool implementations must return `ToolResult`** using `build_evidence()` and `make_error_result()` / `make_denied_result()` so the evidence envelope is always present and schema-conformant.
- **Policy bundle loading is strict**: a configured `PLATFORM_GATEWAY_POLICY_PATH` that is missing or invalid causes startup failure via `PolicyLoadError`; there is no silent degradation.
- **Foreign resource access returns 404, never 403**, to avoid leaking existence information (documented in `session_service._assert_session_owner`).
- **Parked confirmations are process-scoped and ephemeral**: after a restart they are gone, and confirm attempts fail closed (404/410) — this is by design, not a bug.