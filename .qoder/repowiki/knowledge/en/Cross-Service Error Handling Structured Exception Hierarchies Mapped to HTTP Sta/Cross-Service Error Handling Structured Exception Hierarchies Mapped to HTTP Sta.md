---
kind: error_handling
name: 'Cross-Service Error Handling: Structured Exception Hierarchies Mapped to HTTP Status Codes'
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/services/execution_worker_client.py
    - products/agent-platform/src/agent_service/services/shift_summary.py
---

## Approach

Luban's Python services (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) use a uniform pattern:

1. **Domain-specific exception classes** per service, grouped under a small base class.
2. **Client-layer translation**: outbound `httpx` calls wrap transport / upstream errors into those domain exceptions.
3. **Route-layer mapping**: FastAPI route handlers catch the domain exceptions and raise `fastapi.HTTPException` with an explicit `status_code` and a human-readable `detail`, never propagating raw stack traces.
4. **Global middleware logging**: each service registers an `@app.middleware("http")` that logs request lifecycle via `log_event`; the platform-gateway additionally catches exceptions in its authorization edge path and returns `503 {"detail": "Target authorization unavailable"}` for secret-edge failures.
5. **No global exception handler** is registered — FastAPI's default JSON error response is used after the route layer has already converted domain errors to `HTTPException`.
6. **Configuration validation** uses plain `ValueError` raised from `__post_init__` of frozen dataclasses (`ExecutionSettings`, `RuntimeSettings`, etc.), failing fast at startup rather than at first use.

There is no centralized `errors/` package; error types live next to the code that owns them.

## Key Files

- `products/agent-platform/src/agent_service/services/incident_client.py` — `IncidentClientError` hierarchy (`DependencyNotConfigured`, `ServiceUnavailable`, `NotFound`, `Rejected`).
- `products/agent-platform/src/agent_service/services/skills_client.py` — parallel `SkillsClientError` hierarchy.
- `products/agent-platform/src/agent_service/api/v2/routes.py` — central mapper translating client-layer exceptions into `HTTPException(4xx|5xx)`.
- `products/agent-platform/src/agent_service/app.py` — service-level HTTP middleware logging.
- `products/platform-gateway/src/platform_gateway/app.py` — gateway middleware that swallows exceptions on the secret authorization edge and returns 503.
- `products/execution-runtime/src/execution_runtime/core/config.py` — `ExecutionSettings.__post_init__` validation raising `ValueError`.
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError(ValueError)`.
- `products/agent-platform/src/agent_service/runtime_kernel.py` — `UnknownModelError(ValueError)`.
- `products/agent-platform/src/agent_service/services/execution_worker_client.py` — `WorkerHandoffError(Exception)`.
- `products/agent-platform/src/agent_service/services/shift_summary.py` — `DigestInputError`, `UnknownSessionError`.
- `products/audit-service/src/audit_service/services/audit_store.py` — `StoreError`.
- `products/audit-service/src/audit_service/services/ingest_auth.py` — `IngestAuthError`.
- `products/incident-service/src/incident_service/core/config.py` — `SettingsError`.
- `products/incident-service/src/incident_service/services/connectors.py` — `ConnectorConfigError`.
- `products/incident-service/src/incident_service/services/incident_store.py` — `StoreError`.
- `products/incident-service/src/incident_service/services/normalization.py` — `NormalizationError`.
- `products/incident-service/src/incident_service/services/query_auth.py` — `QueryAuthError`.
- `products/incident-service/src/incident_service/services/triage.py` — `TriageError`.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError`.
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError`.
- `products/skills-hub/src/skills_hub/core/config.py` — `SettingsError`.
- `products/skills-hub/src/skills_hub/services/query_auth.py` — `QueryAuthError`.

## Architecture and Conventions

### Client-layer exception hierarchy

Each outbound client defines a small, flat hierarchy rooted at a service-scoped base:

```
IncidentClientError
├── IncidentDependencyNotConfigured
├── IncidentServiceUnavailable
├── IncidentNotFound
└── IncidentClientRejected(status_code, message)
```

The same shape is repeated for `SkillsClientError`. The `*Rejected` variant carries both `status_code` and `message` so the caller can pass through the upstream posture verbatim.

### Route-layer mapping rule

The comment in `incident_client.py` states the invariant explicitly: *"503 when the dependency is not configured, 502 on transport failure or upstream 5xx, and 4xx passed through … never a raw stack trace."*

`routes.py` enforces it by catching each variant:

- `IncidentDependencyNotConfigured` → `HTTPException(503, str(exc))`
- `IncidentServiceUnavailable` → `HTTPException(502, str(exc))`
- `IncidentNotFound` → `HTTPException(404, "incident not found")`
- `IncidentClientRejected` → `HTTPException(exc.status_code, exc.message)`

The same mapping is applied to the skills-hub client and to other downstream dependencies (e.g. `NoValidatedTriageReport` → 409).

### Validation vs runtime errors

- Configuration / schema validation errors are raised as `ValueError` from `__post_init__` of frozen settings dataclasses (`EXECUTION_GATEWAY_TIMEOUT_SECONDS must be > 0 and <= 30`, unknown store backend, empty candidate name, invalid JSON). These fail at import/startup time.
- Runtime/domain failures are raised as the structured exception subclasses above.
- Outbound transport failures (`httpx.HTTPError`) are caught inside the client and re-raised as `*ServiceUnavailable`.

### Gateway edge behavior

The platform-gateway's `create_app()` installs an HTTP middleware that wraps `call_next` in `try/except Exception`. For requests to the secret authorization edge (`BASE`), any exception is suppressed and replaced with either a redirect or `JSONResponse({"detail": "Target authorization unavailable"}, status_code=503)`. Non-secret paths re-raise the original exception.

### Logging and observability

All services call `configure_logging()` and `setup_telemetry(app, SERVICE_NAME)` during app creation. The HTTP middleware records `http_request` events with `service`, `request_id`, `method`, `path`, `status_code`, and `duration_ms`. No custom exception logger is installed — exceptions bubble to FastAPI's default handler after being converted to `HTTPException`.

### Fire-and-forget suppression

Where errors must not propagate (e.g. audit emission, background tasks), the code uses explicit `except Exception as exc:` blocks with `noqa: BLE001` comments and `contextlib.suppress(asyncio.CancelledError)`, documenting why the blanket catch is intentional.

## Conventions and Constraints

- **Observed convention**: Each product defines its own domain exception classes near the code that raises them; there is no shared `errors` module across products.
- **Observed convention**: Outbound HTTP clients translate `httpx.HTTPError` and upstream status codes into a small fixed set of domain exceptions (`DependencyNotConfigured`, `ServiceUnavailable`, `NotFound`, `Rejected`).
- **Observed convention**: Route handlers catch those domain exceptions and map them to `fastapi.HTTPException` with an explicit numeric `status_code` and a short `detail` string.
- **Observed convention**: `ValueError` is reserved for configuration / input validation failures raised from settings `__post_init__` methods; business/runtime errors use the named exception subclasses.
- **Enforced by design**: The `IncidentClientError` / `SkillsClientError` hierarchies guarantee that callers cannot accidentally return a raw traceback — the only way out of the client layer is one of the four documented variants, which the route layer maps deterministically to 404/409/502/503.
- **Enforced by design**: The platform-gateway middleware suppresses exceptions only for the secret authorization edge (`request.url.path.startswith(BASE)`); all other routes let exceptions propagate unchanged.
- **Enforced by design**: Settings dataclasses are `frozen=True` and validate every field in `__post_init__`, so missing or malformed environment variables fail before the service starts serving traffic.
- **Documented invariant** (in docstrings): skill-draft generation degrades to a facts-only skeleton on first validation failure and answers 502 if even the skeleton fails — an unvalidated draft is never returned to the operator.