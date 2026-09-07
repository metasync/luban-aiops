---
kind: error_handling
name: FastAPI HTTPException + Domain-Specific Exceptions with Per-Service Error Boundaries
category: error_handling
scope:
    - '**'
source_files:
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/api/routes/ingest.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
---

## What system/approach is used

The platform uses **FastAPI's built-in `HTTPException`** as the universal HTTP error type across all Python services (agent-platform, platform-gateway, identity-broker, audit-service, incident-service, skills-hub, tool-gateway). There is no shared exception base class or centralized error-response middleware; each service defines its own domain exceptions and converts them to `HTTPException` at the route boundary. Telemetry/logging are added via per-service FastAPI `http` request middleware that logs every response status code — there is no global exception handler.

## Key files and packages

- `products/identity-broker/src/identity_service/services/exchange_service.py` — defines `ExchangeError(Exception)` carrying a `status_code` and `detail`, raised for credential/token verification failures; routes convert it to `HTTPException(status_code=exc.status_code, detail=exc.detail) from exc`.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — defines `PolicyLoadError(Exception)` for invalid/unavailable policy bundles; routes raise `HTTPException(status_code=503, detail="policy bundle unavailable")`.
- `products/tool-gateway/src/tool_gateway/services/gateway_service.py` — raises `HTTPException(401)` for malformed/missing auth headers and `HTTPException(403)` when policy denies an action; also returns `JSONResponse(..., status_code=403)` directly for tool-level denials.
- `products/audit-service/src/audit_service/services/audit_store.py` — defines `StoreError(Exception)` for store-layer failures; routes return `JSONResponse(status_code=400/401, content={"detail": str(exc)})` rather than using `HTTPException`.
- `products/agent-platform/src/agent_service/api/v2/routes.py` — raises `HTTPException` for missing `X-User-ID` (401), parked-session conflicts (409), expired confirmations (410), and missing sessions (404).
- Per-service `app.py` files (`agent_platform`, `platform_gateway`, `tool_gateway`, `identity_broker`, `audit_service`) register an `@app.middleware("http")` that logs `response.status_code` — this is the only cross-cutting error observability hook.

## Architecture and conventions

1. **Domain exceptions stay in service boundaries.** Each service owns its error types (`ExchangeError`, `PolicyLoadError`, `StoreError`, plus local ones like `IngestAuthError`, `TokenVerificationError`, `ConfirmationNotFound`, `ConfirmationExpired`, `ConfirmationOwnerMismatch`). They are never imported across services; conversion to `HTTPException` happens in the route layer of the same service.

2. **Route handlers are the single point of HTTP error mapping.** Routes catch domain exceptions and translate them into `HTTPException` with explicit `status_code` and `detail`. For example, `exchange_service.exchange_token` raises `ExchangeError(detail, status_code)` and `identity_service/api/routes/auth.py` maps it back to `HTTPException(status_code=exc.status_code, detail=exc.detail) from exc`.

3. **Status-code semantics are consistent across services:**
   - `401` — missing/malformed `Authorization` header, missing `X-User-ID`, invalid bearer token, expired/expired subject token, unregistered workload subject.
   - `403` — policy deny (`evaluate()` returning `decision == "deny"`), mutating tool invoked without `tools:mutate` grant, tool result with `denied` status.
   - `404` — session not found, confirmation not found.
   - `409` — session has a parked confirmation, duplicate confirmation claim.
   - `410` — confirmation expired.
   - `502` — downstream service call failed (audit proxy, OIDC exchange).
   - `503` — service dependency not configured (audit service not configured, policy bundle unavailable, tool registry not initialised).
   - `202` — audit ingest accepted asynchronously.

4. **Fire-and-forget audit emission swallows errors.** In `audit_emitter.py` (present in multiple services), audit ingestion failures raise `RuntimeError` on non-2xx responses but are caught by `except Exception as exc` with a `# noqa: BLE001 — fire-and-forget never propagates` comment, ensuring audit delivery never fails the caller.

5. **No global exception handler.** Services rely on FastAPI's default `HTTPException` handler; there is no custom `exception_handler` registered in any `create_app()`. The only cross-cutting hook is the request-scoped middleware that records `response.status_code` in structured logs.

6. **Streaming endpoints handle errors inside the generator.** The `/chat/stream` and `/chat/confirm` endpoints wrap kernel calls in async generators; if a `ConfirmationOwnerMismatch` occurs mid-stream, they yield an `AgentStreamEvent(type="error", ...)` frame instead of raising, because HTTP headers have already been sent.

7. **Readiness/liveness degrade gracefully.** `ready_status()` in tool-gateway catches `PolicyLoadError` and returns `{"status": "degraded", ...}` rather than failing the health endpoint; `audit_store.ready()` wraps all checks in `try/except Exception` so readiness never raises.

## Conventions and constraints

- **Every route must explicitly set `status_code`** on `HTTPException`; bare `raise HTTPException(...)` without a status code is not observed in this codebase.
- **Domain exceptions carry enough context to map to a precise HTTP status** (e.g., `ExchangeError.__init__(detail, status_code)`); routes do not guess status codes from generic exceptions.
- **Policy decisions are modeled as data (`PolicyDecision`)** rather than exceptions — `evaluate()` returns a decision object, and callers raise `HTTPException(403)` only when the decision is `deny`. This keeps policy evaluation pure and testable.
- **Audit events are always emitted even on error paths**, with `outcome` set to `"error"` or `"denied"`; audit failure is intentionally non-fatal.
- **Telemetry setup failures are swallowed** (`except Exception: LOGGER.exception(...)`) so misconfigured OpenTelemetry does not prevent the service from starting.
- **No `raise` of bare `Exception` or `BaseException` outside tests** — all failures use typed subclasses of `Exception` (or `ValueError` for configuration parsing), then mapped to HTTP status codes at the boundary.