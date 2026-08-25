---
kind: error_handling
name: FastAPI HTTPException + Domain-Specific Exceptions Across Services
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/platform-gateway/src/platform_gateway/api/routes/incidents.py
    - products/platform-gateway/src/platform_gateway/api/routes/tools.py
    - products/agent-platform/src/agent_service/app.py
    - products/tool-gateway/src/tool_gateway/app.py
---

## Overview

The monorepo is a collection of independent FastAPI Python services (agent-platform, identity-broker, platform-gateway, tool-gateway, incident-service, audit-service, skills-hub). Each product defines its own HTTP boundary and error strategy; there is no shared error-handling library or cross-cutting exception-to-HTTP mapper.

## What system/approach is used

- **FastAPI `HTTPException`** is the universal mechanism for turning errors into HTTP responses at every API boundary. Routes raise `HTTPException(status_code=..., detail=...)` directly — no custom exception-to-response middleware is registered in any service's `app.py`. All services use a uniform `@app.middleware("http")` logging wrapper that records `method`, `path`, `status_code`, and `duration_ms`; it does not intercept or transform exceptions.
- **Domain-specific exception classes** are raised inside service layers and caught by routes, which then translate them to `HTTPException`. Examples: `QueryAuthError` (incident-service), `PolicyLoadError` (tool-gateway policy engine), `ProviderConfigurationError` / `UnknownModelError` (agent-platform providers/kernel), `ExchangeError` (identity-broker exchange service).
- **Structured `detail` payloads**: when the response body needs more than a string, `detail` is a dict (e.g. confirmation already-resolved payload includes `reason`, `status`, `decider_user_id`, `decision`, `decided_at`).
- **Upstream failures are re-raised as `HTTPException`** with appropriate 5xx codes: `platform-gateway` maps upstream audit/incident/tool calls to 502/503; `identity-broker` maps OIDC token-exchange failures to 502; `agent-platform` returns 410 for expired confirmations, 409 for parked-session conflicts, 422 for unknown model ids.
- **No `try/except` global catch-all**: each route handles only the specific exceptions it expects (e.g. `ConfirmationExpired`, `ConfirmationNotFound`) and lets unhandled exceptions surface to FastAPI's default handler. Best-effort store reads (evidence, confirmation cards) wrap calls in `try/except Exception` and log warnings instead of failing the request.

## Key files and packages

- `products/agent-platform/src/agent_service/api/v2/routes.py` — primary example of route-level error mapping: raises `HTTPException` for 401/404/409/410/422 across chat, session, and confirmation endpoints; catches `ConfirmationExpired`/`ConfirmationNotFound` from the HITL registry.
- `products/agent-platform/src/agent_service/providers/base.py` — defines `ProviderConfigurationError(ValueError)` used by all LLM provider implementations.
- `products/agent-platform/src/agent_service/runtime_kernel.py` — defines `UnknownModelError(ValueError)` for invalid model IDs.
- `products/identity-broker/src/identity_service/services/exchange_service.py` — defines `ExchangeError(Exception)` carrying status codes; routes re-raise as `HTTPException`.
- `products/incident-service/src/incident_service/services/query_auth.py` — defines `QueryAuthError(Exception)` and raises it for missing/expired/invalid credentials; routes convert to 401.
- `products/tool-gateway/src/tool_gateway/services/policy_engine.py` — defines `PolicyLoadError` for malformed policy bundles; `evaluate()` returns a `PolicyDecision` object rather than raising on deny (policy decision is modeled as a value, not an exception).
- `products/platform-gateway/src/platform_gateway/api/routes/{audit,incidents,policy,tools}.py` — gateway routes raise `HTTPException` for 400/502/503 when downstream services are unavailable or misconfigured.
- Per-service `src/*/app.py` — contains only the logging middleware; no exception handlers.

## Architecture and conventions

1. **Layered separation**: business logic raises domain exceptions (`QueryAuthError`, `PolicyLoadError`, `ProviderConfigurationError`, `ExchangeError`, `ConfirmationExpired`, `ConfirmationNotFound`); route handlers catch those and emit `HTTPException` with the correct status code. This keeps service internals decoupled from HTTP semantics.
2. **Status-code discipline observed across services**:
   - `401` — missing/invalid auth header, expired workload token, invalid bearer token.
   - `404` — resource not found (session, confirmation, unknown session id).
   - `409` — conflict (parked confirmation still pending, duplicate confirm, session has parked confirmation).
   - `410` — gone (confirmation expired).
   - `422` — validation failure (unknown model id).
   - `502` — upstream service call failed (audit, identity broker).
   - `503` — service not configured or bundle unavailable.
3. **Best-effort degradation**: optional data sources (evidence store, confirmation record store) are wrapped in `try/except Exception` with `LOGGER.warning(...)` and return `None` so the response degrades gracefully rather than returning 500.
4. **No panics/recover**: Python `raise` is used exclusively; there is no `try/except BaseException` top-level guard in any service.
5. **Consistent middleware posture**: every service registers an `http` middleware that logs the outgoing `response.status_code` but never inspects or modifies exceptions — error handling lives entirely in route handlers.
6. **Policy decisions as values, not exceptions**: the tool-gateway policy engine returns a `PolicyDecision` object (`allow`/`deny`/`require_approval`) and routes map that to `JSONResponse(status_code=200|403)` or `HTTPException(403)`, keeping policy evaluation side-effect free.

## Conventions and constraints

- Every public route must resolve domain exceptions to explicit `HTTPException` status codes — implicit 500s from uncaught exceptions are treated as a defect (evidenced by the deliberate `from None` chaining used to drop internal tracebacks in user-facing errors).
- Authentication failures always map to `401`; authorization denials map to `403`; resource-not-found maps to `404`; state conflicts map to `409`; configuration/validation errors map to `422`; upstream failures map to `502`/`503`.
- Optional storage reads degrade silently with a warning log rather than failing the request — this is the established convention for non-critical auxiliary data (evidence turns, confirmation cards).
- Structured error details (dict-valued `detail`) are used when the caller needs machine-readable fields (e.g. confirmation resolution outcome); plain strings are used for simple messages.