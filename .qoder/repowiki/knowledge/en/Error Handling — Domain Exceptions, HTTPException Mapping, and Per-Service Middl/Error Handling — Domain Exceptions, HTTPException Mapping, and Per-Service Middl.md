---
kind: error_handling
name: Error Handling — Domain Exceptions, HTTPException Mapping, and Per-Service Middleware
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/audit-service/src/audit_service/app.py
    - products/incident-service/src/incident_service/app.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/execution-runtime/src/execution_runtime/services/execution_protocol.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/incident-service/src/incident_service/core/config.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
---

## Approach

Luban's services are FastAPI applications that follow a two-tier error model:

1. **Domain exceptions** — per-service `*Error` classes (subclassing `Exception` or `ValueError`) raised by business logic and client wrappers.
2. **HTTP translation layer** — route handlers catch domain exceptions and raise `fastapi.HTTPException` with explicit `status_code` and human-readable `detail`, so the API surface is uniform across all products.

There is no repository-wide exception base class, no centralized `@app.exception_handler` registration, and no `try/except Exception` blanket handler. Each service owns its own app factory and middleware stack.

## Key Files

- `products/agent-platform/src/agent_service/app.py` — FastAPI lifespan + request logging middleware; no custom exception handler.
- `products/platform-gateway/src/platform_gateway/app.py` — identical pattern: lifespan + `log_requests` middleware.
- `products/audit-service/src/audit_service/app.py` — same pattern, plus store/retention lifecycle.
- `products/incident-service/src/incident_service/app.py` — same pattern, plus connector/store lifecycle.
- `products/agent-platform/src/agent_service/api/v2/routes.py` — primary HTTP → domain exception mapper (`_validate_skill_markdown`, incident draft routes).
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError(ValueError)` used by every provider adapter.
- `products/agent-platform/src/agent_service/services/skills_client.py` — `SkillsClientError(Exception)` hierarchy (`SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`).
- `products/agent-platform/src/agent_service/services/incident_client.py` — `IncidentClientError(Exception)` hierarchy (`IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`, `NoValidatedTriageReport`).
- `products/execution-runtime/src/execution_runtime/services/execution_protocol.py` — `ProtocolError(ValueError)`.
- `products/identity-broker/src/identity_service/services/exchange_service.py` — `ExchangeError(Exception)`.
- `products/incident-service/src/incident_service/core/config.py` — `SettingsError(Exception)`.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError(Exception)`.
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError(Exception)`.
- `products/skills-hub/src/skills_hub/core/config.py` — `SettingsError(Exception)`.
- `products/tool-gateway/src/tool_gateway/services/policy_engine.py` — `PolicyLoadError(Exception)`.
- `products/tool-gateway/src/tool_gateway/services/token_verifier.py` — `TokenVerificationError(Exception)`.
- `samples/acme-admin/app/src/acme_admin/main.py` — only place in the repo using `@app.exception_handler(...)`, for a sample app.

## Architecture and Conventions

### Per-service app factory
Every product exposes a `create_app()` function in `<product>/src/<package>/app.py`. The function:
- Calls `configure_logging()` from `core.observability`.
- Instantiates `FastAPI(title=..., version=...)`.
- Registers an `@app.middleware("http")` named `log_requests` that wraps `call_next`, measures `duration_ms`, resolves `x-request-id`, and emits a structured `http_request` event via `log_event`.
- Includes the router, calls `setup_metrics(app)`, and calls `setup_telemetry(app, SERVICE_NAME)`.
- Returns the app; module-level `app = create_app()` is the WSGI/ASGI entrypoint.

This means error propagation through the HTTP layer is always observed as a log line carrying method, path, status_code, duration_ms, and request_id — regardless of whether the response came from a normal return value or an `HTTPException`.

### Domain exceptions live next to the code that raises them
Each service defines small, purpose-specific exception classes rather than reusing a shared base:
- `ProviderConfigurationError` under `providers/base.py` (used by all LLM providers).
- `WorkerHandoffError`, `DigestInputError`, `UnknownSessionError`, `SkillsClientError`, `IncidentClientError` under `services/`.
- `StoreError`, `IngestAuthError` under `audit_service/services/`.
- `ConnectorConfigError`, `NormalizationError`, `QueryAuthError`, `TriageError` under `incident_service/services/`.
- `PolicyLoadError`, `TokenVerificationError` under both `platform-gateway/services/` and `tool-gateway/services/`.

Some validation errors subclass `ValueError` (`ProviderConfigurationError`, `UnknownModelError`, `ProtocolError`) because they represent invalid input/configuration rather than runtime failures.

### Route-level mapping to HTTP status codes
The agent-platform v2 routes are the canonical example. In `_validate_skill_markdown` and the incident/skill-draft endpoints, domain exceptions are caught and mapped explicitly:

| Domain exception | HTTP status | Detail |
|---|---:|---|
| `*DependencyNotConfigured` | 503 | `str(exc)` |
| `*ServiceUnavailable` | 502 | `str(exc)` |
| `*ClientRejected` | `exc.status_code` | `exc.message` |
| `IncidentNotFound` | 404 | `"incident not found"` |
| `NoValidatedTriageReport` | 409 | deterministic message |

The pattern uses `from None` on most `raise HTTPException(...)` lines to suppress the Python exception chain in logs, keeping the user-facing detail clean while preserving the original exception where needed (e.g. `from exc` for `IncidentNotFound`).

### No global exception handler
Across all five production services (`agent-platform`, `platform-gateway`, `audit-service`, `incident-service`, `skills-hub`, `tool-gateway`), there is no `@app.exception_handler` decorator registered. Unhandled exceptions bubble out of FastAPI and become 500 responses with the default JSON body. The only custom exception handler in the repo lives in `samples/acme-admin/app/src/acme_admin/main.py`, which is a sample application, not a platform service.

### Validation vs. runtime errors
- Configuration/runtime setup errors (missing env vars, unknown connectors, invalid settings) raise domain exceptions during startup or first use, surfaced as 503/400/422 via route handlers.
- Input validation errors in Pydantic models are handled by FastAPI automatically (422 Unprocessable Entity); route handlers additionally raise `HTTPException(status_code=422, ...)` for semantic validation beyond schema shape (e.g. missing `X-User-ID`, empty recovery query, missing recipient acknowledgment).

## Conventions and Constraints

- **Observed convention**: each service defines its own `create_app()` in `<service>/app.py` that registers a single `http` middleware for request logging and never registers a custom exception handler.
- **Observed convention**: domain exceptions are defined close to the code that raises them and named `<Purpose>Error`; configuration/input errors subclass `ValueError`, operational/client errors subclass `Exception`.
- **Observed convention**: route handlers translate domain exceptions into `fastapi.HTTPException` with explicit `status_code` and a short `detail` string; dependency-not-configured cases map to 503, upstream-unavailable cases map to 502, rejected client requests pass through their own `status_code`/`message`.
- **Observed convention**: `from None` is used when wrapping domain exceptions in `HTTPException` to avoid leaking internal tracebacks to callers; `from exc` is retained when the original exception carries useful context (e.g. `IncidentNotFound`).
- **Constraint enforced by structure**: every product follows the same `app.py` skeleton (lifespan + `log_requests` middleware + router include + metrics/telemetry setup), making cross-service error observability consistent even though there is no shared framework.
- **No enforcement mechanism**: there is no lint rule, test, or CI check that verifies the presence of an exception handler or the absence of bare `raise Exception(...)`. The patterns above are conventions documented by code structure, not by tooling.