---
kind: error_handling
name: Structured Domain Exceptions, FastAPI HTTPException Mapping, and Gateway Error Posture
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/incident-service/src/incident_service/core/config.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/agent-platform/src/agent_service/app.py
---

## Overview

The Luban platform uses a layered error-handling model across its seven Python services. At the domain layer each service defines small, purpose-specific exception classes (e.g. `TokenVerificationError`, `PolicyLoadError`, `StoreError`, `SettingsError`, `ProviderConfigurationError`, `UnknownModelError`). These exceptions carry a human-readable `detail`/`message` and are raised from business logic. At the API boundary, routes and gateway services translate them into FastAPI `HTTPException` instances with explicit HTTP status codes, so callers always receive structured JSON responses rather than raw stack traces. There is no global exception handler registered — FastAPI's default exception handling is used, and the consistent pattern lives in the route/service code that raises `HTTPException`.

## Domain-layer exceptions

Each product keeps its domain errors close to the subsystem that owns the failure:

- **Platform gateway**: `platform_gateway.services.token_verifier.TokenVerificationError` wraps JWT decode failures (expired, invalid issuer/audience, signing key resolution) with a string `detail`; `platform_gateway.services.policy_engine.PolicyLoadError` is raised when the YAML policy bundle is malformed or missing.
- **Tool gateway**: `tool_gateway.tools.base.ToolResult` carries a structured `error: {code, message}` envelope for tool-level failures; `make_error_result` / `make_denied_result` are the only constructors, ensuring every tool response has an `evidence` block with `risk_level`, `duration_ms`, `executed_at`, and `source_system`.
- **Agent platform**: `agent_service.providers.base.ProviderConfigurationError(ValueError)` signals incomplete provider settings; `agent_service.runtime_kernel.UnknownModelError(ValueError)` signals unknown model IDs.
- **Audit service**: `audit_service.services.audit_store.StoreError(Exception)` wraps store-level failures (e.g. invalid cursor decoding).
- **Incident service**: `incident_service.core.config.SettingsError(Exception)` fails startup fast on malformed `INCIDENT_*` env vars.
- **Identity broker**: `identity_service.services.exchange_service.ExchangeError(Exception)` and `ingest_auth.IngestAuthError(Exception)` wrap upstream exchange/auth failures.

These exceptions are never propagated across service boundaries; they are caught at the edge of the process and mapped to HTTP responses.

## API-layer mapping to HTTP status codes

Routes raise `fastapi.HTTPException(status_code=..., detail=...)` consistently:

| Status | Meaning | Where it appears |
|--------|---------|------------------|
| 401 | Missing/malformed auth header, expired token, authentication required | Platform & tool gateway identity resolution, agent-service confirmation routes |
| 403 | Policy deny (`action denied by policy`) or approval-tier blocked (`not_a_designated_approver`, `self_approval`) | Both gateways' `enforce_policy()` and `_enforce_approval_tier()` |
| 404 | Session not found, confirmation not found | Agent-service session/confirmation routes |
| 409 | Confirmation already exists / conflict | Agent-service confirmation creation |
| 410 | Confirmation expired | Agent-service confirmation routes |
| 422 | Validation error (e.g. missing confirm_id) | Agent-service confirmation routes |
| 502 | Upstream agent/tool/identity service unavailable or transport failure | All gateway proxy methods (`get_session`, `list_sessions`, `chat_stream`, `chat_confirm`, etc.) map `httpx.HTTPStatusError` with 4xx through unchanged and everything else to 502 |
| 500 | Not used explicitly — unhandled exceptions bubble to FastAPI's default handler |

The gateway services follow a uniform posture documented in their docstrings: "upstream 4xx passes through unchanged; transport failures and upstream 5xx map to 502". This preserves client-error semantics (unknown session, parked session, unknown model) while hiding backend outages behind a single 502.

## Policy and approval errors

Policy evaluation lives in `platform_gateway.services.policy_engine.evaluate()`, which returns a frozen `PolicyDecision` dataclass with fields `decision` (`allow` | `deny` | `require_approval`), `matched_rule_ids`, `reason`, and optional `approval`. A `deny` decision is converted to `HTTPException(403, detail={"detail": "action denied by policy", "action", "reason"})` in both gateways' `enforce_policy()` helpers. For HITL bridging (`chat_confirm`), `_enforce_approval_tier()` additionally checks decider roles and self-approval rules, emitting a `confirmation_decided` audit event with `blocked=True` and raising a structured 403 containing `requirement`, `approval_tier`, and `blocked_reason`.

## Tool execution errors

Tool invocations do not raise exceptions to the caller. Instead, `tool_gateway/services/gateway_service.invoke_tool()` returns a `ToolResult` via `make_error_result` / `make_denied_result`. The result envelope matches `shared/shared-contracts/schemas/tool-result.schema.json` and includes:
- `status`: `success` | `error` | `denied`
- `data`: present on success
- `error.code`: e.g. `POLICY_DENIED`, `REDACTION_OVERFLOW`
- `evidence.duration_ms`, `evidence.risk_level`, `evidence.executed_at`

Redaction overflow (SPEC-009 R-1/R-2) converts a successful tool result into an `error` result with `REDACTION_OVERFLOW` before the response and audit trail are emitted. Mutating tools additionally require `tools:mutate` policy; denial returns 403 with `POLICY_DENIED`.

## Readiness / health error posture

Both gateways expose `/ready` endpoints that catch domain errors and report `status: degraded` instead of failing the probe:
- Platform gateway catches `httpx.HTTPError` (agent service down) and `PolicyLoadError` (policy bundle bad) in `ready_status()`.
- Tool gateway catches `PolicyLoadError` in its own `ready_status()`.

This means a broken policy bundle or downstream outage degrades readiness without crashing the process.

## Middleware and observability (no custom exception handler)

Every service registers a `@app.middleware("http")` that logs `http_request` events with method, path, `status_code`, and `duration_ms`. There is no `@app.exception_handler` override anywhere in the codebase — the middleware records whatever status code FastAPI emits, whether from a route handler or FastAPI's built-in validation/error machinery. Structured logging is done via `core.observability.log_event` / `log_event(LOGGER, ...)` rather than print statements.

## Cross-service error propagation

Outbound calls use `httpx.AsyncClient` and call `response.raise_for_status()` immediately after the request, then catch `httpx.HTTPStatusError` to distinguish client vs server errors. Token verification failures propagate as `TokenVerificationError` up to the route layer where they become 401s. Audit emission is fire-and-forget (`emit_audit_event` called after the response is decided); failures there do not affect the response status.

## Key files

- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError`, JWT decode mapping
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError`, `PolicyDecision`, evaluate()
- `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — proxy error posture (4xx passthrough, 502 mapping), approval-tier enforcement
- `products/tool-gateway/src/tool_gateway/tools/base.py` — `ToolResult`, `make_error_result`, `make_denied_result`
- `products/tool-gateway/src/tool_gateway/services/gateway_service.py` — tool invocation policy + redaction error flow
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError`
- `products/agent-platform/src/agent_service/runtime_kernel.py` — `UnknownModelError`
- `products/audit-service/src/audit_service/services/audit_store.py` — `StoreError`, cursor decode error
- `products/incident-service/src/incident_service/core/config.py` — `SettingsError`
- `products/identity-broker/src/identity_service/services/exchange_service.py` — `ExchangeError`
- `products/identity-broker/src/identity_service/api/routes/auth.py` — maps upstream exchange errors to 502/401
- `products/*/src/*/app.py` — per-service FastAPI app with request-logging middleware (no custom exception handler)

## Conventions observed

1. **Domain exceptions stay in-process** — they are never serialized over the wire; only `HTTPException` leaves the service.
2. **Gateway proxies preserve 4xx, collapse 5xx to 502** — documented in comments and enforced uniformly across every proxy method.
3. **Policy denies are 403 with structured detail** — always include `action`, `reason`, and (for approvals) `requirement` / `approval_tier`.
4. **Tool results use a typed envelope** — `ToolResult.status` plus `error.code`/`message` instead of ad-hoc dicts.
5. **Readiness probes degrade gracefully** — policy load and downstream failures return `status: degraded` rather than raising.
6. **No global exception handler** — error shaping is done explicitly at the route/service boundary, not via a centralized handler.