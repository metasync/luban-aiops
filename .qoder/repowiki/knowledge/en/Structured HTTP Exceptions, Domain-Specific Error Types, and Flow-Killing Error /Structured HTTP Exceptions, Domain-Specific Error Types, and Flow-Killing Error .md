---
kind: error_handling
name: Structured HTTP Exceptions, Domain-Specific Error Types, and Flow-Killing Error Codes Across FastAPI Services
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/services/flow_approvals.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/tool-gateway/src/tool_gateway/tools/browser_connector.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
---

## What system/approach is used

The platform uses a layered error model built on Python exceptions and FastAPI's `HTTPException`:

1. **Domain-specific exception classes** are defined per service (e.g. `TokenVerificationError`, `StoreError`, `PolicyLoadError`, `SkillsClientError`, `IncidentClientError`, `UnknownModelError`, `ProviderConfigurationError`). Each lives in the service module that owns the failure domain.
2. **Routes raise `fastapi.HTTPException`** with explicit `status_code` and a human-readable `detail` string or dict — there is no centralized exception handler registered; FastAPI's default JSON error response format is relied upon.
3. **Flow-killing sentinel codes** (`FLOW_KILLING_ERROR_CODES = frozenset({"BROWSER_REDIRECT_NOT_ALLOWED", "BROWSER_FLOW_DENIED", "BROWSER_FLOW_ORIGIN_DEVIATED", "BROWSER_FLOW_AUTHORITY_STALE"})`) propagate from tool-gateway browser tools through the agent-platform kernel to terminate flows deterministically.
4. **Tool-level errors** use a structured envelope: `make_error_result(...)` / `_denied(...)` return a `ToolResult` with `status="error"`/`"denied"` plus an `{"code": ..., "message": ...}` payload, which the kernel normalizes into stream events.
5. **Middleware only logs requests** (method, path, status_code, duration_ms) — it does not transform errors. No global `exception_handler` is attached in any service's `app.py`.
6. **Fail-closed posture**: unknown model IDs, missing `X-User-ID`, expired confirmations, and policy refusals all produce 4xx responses rather than falling back silently.

## Key files and packages

- `products/agent-platform/src/agent_service/api/v2/routes.py` — primary route file raising `HTTPException` for auth (401), validation (422), conflict (409), not-found (404), gone (410), upstream failures (502/503), and incident proxy mapping.
- `products/agent-platform/src/agent_service/runtime_kernel.py` — defines `UnknownModelError(ValueError)` and consumes `FLOW_KILLING_ERROR_CODES`; maps provider/tool errors into stream `error` frames via `build_provider_error_message`.
- `products/agent-platform/src/agent_service/services/flow_approvals.py` — declares `FLOW_KILLING_ERROR_CODES` and flow context/approval stores whose `get()` returns `None` on expiry (fail-safe).
- `products/tool-gateway/src/tool_gateway/tools/browser_connector.py` — returns `(record, error_code, error_message)` tuples and uses `_denied(tool_name, code, message, risk_level)` to build `ToolResult` envelopes with `status="denied"` and `{"code", "message"}`.
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — defines `TokenVerificationError(Exception)` with a `.detail` attribute; callers map it to HTTP responses.
- Per-service `services/*.py` modules define domain exceptions: `audit_store.StoreError`, `exchange_service.ExchangeError`, `incident_store.StoreError`, `query_auth.QueryAuthError`, `policy_engine.PolicyLoadError`, `skills_client.SkillsClientError`, etc.
- Service `app.py` files (`agent_service/app.py`, `platform_gateway/app.py`, `tool_gateway/app.py`) register only request-logging middleware; no custom exception handlers.

## Architecture and conventions

### Exception hierarchy by layer

| Layer | Mechanism | Example |
|---|---|---|
| Infrastructure / config | Custom `*Error` subclasses of `Exception` or `ValueError` | `ProviderConfigurationError`, `SettingsError` |
| Service boundary | Custom `*Error` raised by services | `TokenVerificationError`, `StoreError`, `ExchangeError` |
| Route layer | `raise HTTPException(status_code=..., detail=...)` | 401/404/409/410/422/502/503 |
| Tool execution | `ToolResult(status="error"|"denied", error={"code","message"})` | Browser connector denied results |
| Stream events | Kernel normalizes tool errors into `AgentStreamEvent(type="error", error={...})` | Propagated to portal |

### Status-code conventions observed in routes

- **401** — missing `X-User-ID` header.
- **404** — session not found, confirmation not found, incident not found, no pending confirmation.
- **409** — parked confirmation blocks new turns, session has parked confirmation on delete, skill target conflicts.
- **410** — confirmation expired.
- **422** — unknown model id, invalid skill target URL.
- **502** — upstream tool-gateway / identity-broker / skills-service / incidents-service unavailable.
- **503** — runtime kernel / evidence store unreadable, downstream service unavailable.

Upstream call sites wrap `httpx` calls in `try/except` and re-raise as `HTTPException(502|503, detail=str(exc))` with `from None` to suppress the original traceback in the client response.

### Flow-killing error propagation

Browser-tool errors carry string codes like `BROWSER_FLOW_DENIED`. The agent-platform kernel checks `code in FLOW_KILLING_ERROR_CODES` to decide whether to kill the flow (stop streaming, park a confirmation, surface refusal). This is a cross-service contract: tool-gateway emits codes, agent-platform interprets them.

### Fail-safe degradation

Read-only helpers deliberately swallow exceptions and degrade:
- `_load_evidence_turns` catches `Exception`, logs a warning, returns `None`.
- `_load_confirmation_cards` catches store read errors, returns `None`.
- `FlowApprovalStore.get` returns `None` for both missing and expired entries.
- `_persist_claimed_outcome` wraps the durable write in try/except and logs a warning without aborting the decision.

This means transient storage failures never escalate to 500s on query endpoints.

### Token verification error shape

`TokenVerificationError` carries a `.detail` string. Routes in `platform_gateway` and `identity-broker` catch it and translate to appropriate HTTP responses (the pattern is consistent across both gateways' token verifiers).

## Conventions and constraints

1. **No global exception handler exists.** Every service's `create_app()` registers only a logging middleware; error serialization is delegated to FastAPI's default `HTTPException` handler. Adding a custom handler would be a deviation from the observed pattern.
2. **Route-layer errors are expressed as `HTTPException`**, not returned values. There are no `ResponseModel` error variants — clients must inspect `status_code` and `detail`.
3. **Domain errors stay as exceptions within a service.** Cross-service boundaries convert them to HTTP status codes at the route layer; internal callers catch specific exception types.
4. **Flow-killing errors are string constants**, not typed exceptions. They live in `flow_approvals.FLOW_KILLING_ERROR_CODES` and are checked via membership against a `frozenset`.
5. **Tool errors are structured payloads**, not exceptions. A tool returning `{"status":"error", "error":{"code":"...","message":"..."}}` is the canonical form; the kernel then emits an `error` stream event.
6. **Transient store failures degrade gracefully** — read paths log and return `None`/empty lists instead of raising, ensuring API availability under partial outages.
7. **Anti-enumeration posture**: unknown session ids and unparked sessions answer 404 indistinguishably from genuinely absent resources, preventing enumeration of valid identifiers.