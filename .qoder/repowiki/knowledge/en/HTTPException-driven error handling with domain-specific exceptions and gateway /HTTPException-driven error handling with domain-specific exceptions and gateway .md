---
kind: error_handling
name: HTTPException-driven error handling with domain-specific exceptions and gateway status mapping
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/providers/base.py
---

## Error Handling Approach

The platform uses a layered, HTTP-first error model built on FastAPI's `HTTPException` for boundary responses and domain-specific Python exceptions for internal failure propagation. There is no centralized exception handler registered at the application level; instead, each service raises `HTTPException` directly from route handlers or gateway proxy functions, letting FastAPI serialize them into JSON responses with appropriate status codes.

### Boundary Layer: FastAPI HTTPException

Every product service (`agent-platform`, `platform-gateway`, `tool-gateway`, `audit-service`, `incident-service`, `skills-hub`, `identity-broker`) raises `fastapi.HTTPException(status_code=..., detail=...)` to signal client-facing errors. Status codes are chosen semantically:
- `401` for missing/invalid authentication (e.g., missing `X-User-ID` header, malformed `Authorization` header, token verification failures)
- `403` for policy denials and approval-tier blocks (e.g., `action denied by policy`, `not_a_designated_approver`, `self_approval`)
- `404` for not-found resources (sessions, documents, confirmations)
- `409` for conflict states (parked confirmations being resolved)
- `410` for expired confirmations
- `422` for validation/model resolution errors (unknown model id)
- `502` for upstream transport failures when proxying to downstream services

No custom exception-to-status-code mapping is registered — the codebase relies entirely on FastAPI's default behavior of converting `HTTPException` instances into JSON responses.

### Domain Exceptions for Internal Propagation

Internal modules define typed exceptions that carry structured context and are caught at service boundaries where they are translated to `HTTPException`:

- `TokenVerificationError` (`platform_gateway/services/token_verifier.py`): wraps JWT verification failures (expired, invalid issuer/audience, unable to resolve signing key). Callers catch it and re-raise as `HTTPException(401, detail=exc.detail)`.
- `PolicyLoadError` (`platform_gateway/services/policy_engine.py`): raised when the YAML policy bundle is malformed, missing, or contains invalid rules. Caught only by readiness/liveness probes which return `{"status": "degraded", ...}` rather than failing the request.
- `ProviderConfigurationError` (`agent_platform/src/agent_service/providers/base.py`): `ValueError` subclass for invalid provider configuration.
- `UnknownModelError`, `WorkerHandoffError`: domain exceptions in agent-platform services.
- `ConfirmationNotFound`, `ConfirmationExpired` (`agent_platform/src/agent_service/services/hitl_confirmations.py`): raised by confirmation stores and caught in routes to produce `409`/`410` responses.

### Gateway Proxy Error Mapping Pattern

The `platform-gateway` and `tool-gateway` implement a consistent pattern for proxying calls to downstream services using `httpx`. Each proxy function wraps the call in a try/except block that distinguishes between:

1. **Upstream 4xx** (`httpx.HTTPStatusError` with status < 500): passed through unchanged so client errors (unknown session, foreign-session denial, unknown/expired confirmation) reach the caller without being masked.
2. **Upstream 5xx or transport errors** (`httpx.HTTPError` / non-4xx `HTTPStatusError`): mapped to `HTTPException(502, detail="... unavailable")` so upstream outages never masquerade as client errors.

This pattern appears consistently across `get_session`, `list_sessions`, `approvals_inbox`, `list_models`, `delete_session`, `update_session_title`, `create_document`, `list_documents`, `fetch_document`, `publish_document`, `delete_document`, and both streaming endpoints (`chat_stream`, `chat_confirm`).

### Policy Enforcement Errors

Policy evaluation lives in a dependency-free module (`policy_engine.py`) that returns a `PolicyDecision` dataclass with three outcomes: `allow`, `deny`, `require_approval`. The calling layer (`enforce_policy` in both gateways) converts `deny` decisions into `HTTPException(403, detail={...})` containing the action, reason, and matched rule IDs. For approval-required flows (SPEC-030), additional tier checks raise `HTTPException(403, ...)` with structured reasons like `not_a_designated_approver` or `self_approval`, and these blocked attempts are audited via `emit_audit_event` before the exception propagates.

### Tool Execution Error Model

The tool-gateway does not use exceptions for tool execution results. Instead, tools return a `ToolResult` dataclass (`tool_gateway/tools/base.py`) with a `status` field of `success`, `error`, or `denied`, plus an `error` dict carrying `code` and `message`. Helper functions `make_error_result()` and `make_denied_result()` construct these envelopes uniformly. The gateway maps `status == "success"` to HTTP 200, `status == "error"` to HTTP 400, and `status == "denied"` to HTTP 403. Redaction overflow produces a synthetic `REDACTION_OVERFLOW` error result rather than raising.

### Streaming Error Handling

For SSE streaming endpoints (`chat_stream`, `chat_confirm`), the gateway checks the upstream response status *before* opening the stream. If the initial call raises `httpx.HTTPStatusError`, it is converted to `HTTPException` so the client receives an HTTP error status rather than a 200 with an empty stream. During streaming, parsing errors for frame extraction (`_extract_message_end`, `_extract_confirmation_result`, `_frame_type`) are silently ignored (returning `None`) to tolerate malformed frames without crashing the stream.

### Readiness/Liveness Degradation

Startup health checks (`ready_status`, `live_status`) catch `PolicyLoadError` and `httpx.HTTPError` to report `status: degraded` with the error string embedded, allowing Kubernetes probes to detect misconfiguration without crashing the process.

### Conventions Observed

- No `try/except Exception` global handlers exist; errors bubble to FastAPI's default handler.
- Domain logic raises typed exceptions; HTTP boundaries translate them to `HTTPException`.
- Upstream failures are explicitly categorized as 4xx (passthrough) vs 5xx (mapped to 502).
- Policy denials always include structured `detail` dicts with `action`, `reason`, and `matched_rule_ids`.
- Token verification failures preserve the original exception via `from exc` chaining.
- Audit events are emitted *before* raising policy-denial exceptions so denials are durable even when requests fail.