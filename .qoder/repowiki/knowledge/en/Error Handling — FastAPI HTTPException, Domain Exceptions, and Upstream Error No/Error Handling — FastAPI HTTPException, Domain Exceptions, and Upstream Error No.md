---
kind: error_handling
name: Error Handling — FastAPI HTTPException, Domain Exceptions, and Upstream Error Normalization
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/execution-runtime/src/execution_runtime/api/routes/handoff.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/identity-broker/src/identity_service/api/routes/identity.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
---

## What system/approach is used

The Luban platform is a collection of independent FastAPI services (agent-platform, platform-gateway, tool-gateway, execution-runtime, identity-broker, audit-service, incident-service, skills-hub). There is no shared error-handling library or global exception handler. Each product defines its own small set of domain exceptions in `services/` and converts them into HTTP responses at the API boundary using FastAPI's built-in `HTTPException` or explicit `JSONResponse(status_code=...)`. Outbound calls to other services are wrapped so that upstream 4xx errors pass through with their original status code while transport failures and 5xx responses are normalized to a structured `502 Bad Gateway` response.

## Key files and packages

- **Platform gateway** — `products/platform-gateway/src/platform_gateway/services/gateway_service.py`: centralizes proxy error normalization (`_identity_leg`, agent-session fetch, chat relay) mapping upstream failures to `HTTPException(502)` and forwarding 4xx details.
- **Tool gateway** — `products/tool-gateway/src/tool_gateway/services/policy_engine.py` (`PolicyLoadError`) and `token_verifier.py` (`TokenVerificationError`); routes return `JSONResponse(status_code=403)` for policy denials.
- **Agent platform** — `products/agent-platform/src/agent_service/api/v2/routes.py` raises `HTTPException` for session conflicts (`409`), expired confirmations (`410`), missing confirmations (`404`), unconfigured skill validation (`503`), unreachable skills service (`502`), and client rejections (`exc.status_code`). Helper `_validate_skill_markdown` maps `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected` to specific status codes.
- **Execution runtime** — `products/execution-runtime/src/execution_runtime/api/routes/handoff.py` returns `JSONResponse` with `status_code=401/400/200` for signature/validation outcomes.
- **Identity broker** — `products/identity-broker/src/identity_service/api/routes/auth.py` and `routes/identity.py` raise `HTTPException` for OIDC exchange failures (`502`), refresh failures (`401`), missing/invalid bearer tokens (`401`).
- **Audit service** — `products/audit-service/src/audit_service/services/audit_store.py` (`StoreError`), `ingest_auth.py` (`IngestAuthError`); routes return `JSONResponse(status_code=400/401/202/200)` for ingest/query errors.
- **Incident service** — `products/incident-service/src/incident_service/core/config.py` defines `SettingsError` raised during startup when `INCIDENT_*` env vars are malformed; failure-to-start is enforced rather than surfaced as an HTTP error.
- **Skills hub** — `products/skills-hub/src/skills_hub/core/config.py` (`SettingsError`), `query_auth.py` (`QueryAuthError`), `skill_store.py` (`StoreError`); routes return `JSONResponse(status_code=...)` for ingestion and query errors.
- **Shared contracts** — JSON schemas under `shared/shared-contracts/schemas/` define the shape of cross-service payloads (e.g., `chat-response.schema.json`, `tool-result.schema.json`); they do not define error types but constrain the `detail` fields returned by `HTTPException`/`JSONResponse` bodies.

## Architecture and conventions

1. **Domain exceptions live next to the logic that raises them.** Each service keeps small, single-purpose exception classes in its `services/` directory (e.g. `WorkerHandoffError`, `IncidentClientError`, `SkillsClientError`, `PolicyLoadError`, `TokenVerificationError`, `StoreError`, `SettingsError`, `ExchangeError`). They are never caught outside the owning service.

2. **API layers translate domain exceptions into HTTP responses.** Routes and service entry points catch domain exceptions and raise `fastapi.HTTPException(status_code=..., detail=...)` or return `fastapi.responses.JSONResponse(content=..., status_code=...)`. No global `@app.exception_handler` is registered anywhere in the repo; FastAPI's default exception handler renders these objects.

3. **Upstream errors are normalized at the call site, not globally.** The pattern in `platform_gateway.services.gateway_service._identity_leg` is representative: `httpx.HTTPStatusError` with status < 500 is re-raised as `HTTPException` preserving the upstream status and extracting `detail`; any 5xx or transport `httpx.HTTPError` becomes `HTTPException(502, "... unavailable — retry...") from None`. This ensures callers (the portal) never see raw 500s from downstream races.

4. **Structured error bodies use `detail` strings.** Whether via `HTTPException` or `JSONResponse`, the response body carries a `detail` field describing the failure (e.g. `"session not found"`, `"confirmation expired"`, `"skills service not configured for skill-draft validation"`, `"malformed authorization header"`). Tests assert on both `status_code` and `detail` values, making this the de facto contract between services.

5. **Startup-time configuration errors fail fast.** Services like `incident-service` and `skills-hub` raise `SettingsError` during settings parsing so misconfiguration is detected before the process starts, rather than being converted to HTTP errors later.

6. **No panics / no `sys.exit` in request paths.** Python has no panic concept; the codebase avoids `sys.exit()` inside request handlers and instead returns HTTP responses. Process-level failures surface as container restarts.

7. **Middleware is limited to metrics/RED.** Each service mounts a `@app.middleware("http")` in `core/metrics.py` that records RED metrics and always forwards the response (including error responses) unchanged — there is no error-transforming middleware.

## Conventions and constraints observed

- **Downstream 4xx pass through; downstream 5xx become 502.** Enforced by the explicit branching in `_identity_leg` and similar wrappers across gateway services.
- **Unconfigured optional dependencies degrade to 503.** Skill-draft validation, incident triage, and similar optional legs raise `HTTPException(503, ...)` when their backing service is not configured, rather than failing the caller's primary operation.
- **Validation failures are 400/422; not-found is 404; conflict is 409; unauthorized is 401; forbidden is 403.** These status codes are consistently used across all services' route handlers.
- **`from None` is used when wrapping upstream exceptions into `HTTPException`** to suppress the chained traceback in logs (e.g. `raise HTTPException(...) from None` after catching `httpx.HTTPStatusError`).
- **Policy denials return 403 explicitly**, sometimes via `JSONResponse(status_code=403, content=result.to_dict())` in the tool-gateway policy engine path.
- **Tests drive the error contract.** Every service's test suite asserts on exact `status_code` and often on `response.json()["detail"]`, which acts as an enforcement mechanism keeping route behavior stable.