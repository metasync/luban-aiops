---
kind: error_handling
name: Structured Exception Hierarchy with HTTPException Mapping in FastAPI Services
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/audit-service/src/audit_service/app.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
---

## What system/approach is used

The platform uses a layered error model across all Python services built on **FastAPI**:

1. **Domain/service-level exceptions** — each service defines small, named exception classes (e.g. `IncidentClientError` hierarchy in `agent_service/services/incident_client.py`, `SkillsClientError` in `skills_client.py`, `PolicyLoadError` in `platform_gateway/services/policy_engine.py`, `StoreError`/`QueryAuthError`/`TriageError` in other services) that encode the *semantic* failure mode and often carry structured fields (`incident_id`, `status_code`, `message`).
2. **HTTP boundary mapping** — route handlers catch those domain exceptions and translate them into `fastapi.HTTPException(status_code=..., detail=...)`, which FastAPI serializes to JSON responses. No raw stack traces or internal exception types leak over the wire.
3. **Logging as audit trail** — every service configures logging via a shared `core.observability.configure_logging()` / `log_event()` helper that writes structured JSON events at INFO level (overriding Uvicorn's default WARNING root level). An `http_request` log event records method, path, status_code, duration_ms per request through an `app.middleware("http")` hook.
4. **No global exception handler** — there are no `@app.exception_handler` registrations; error translation happens inline at the call site inside each route function.
5. **No panics/recover** — Python has no panic mechanism; the codebase avoids bare `raise Exception(...)` for control flow and instead raises typed subclasses of `Exception`/`ValueError`.

## Key files and packages

- `products/agent-platform/src/agent_service/api/v2/routes.py` — central route layer that catches client-service exceptions (`IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`, `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`, `DigestInputError`, `ForeignSessionDenied`, `UnknownSessionError`, `ConfirmationExpired`, `ConfirmationNotFound`) and maps them to HTTP status codes (400, 401, 403, 404, 409, 410, 422, 502, 503).
- `products/agent-platform/src/agent_service/services/incident_client.py` — defines the `IncidentClientError` hierarchy and documents the posture: "503 when dependency not configured, 502 on transport/upstream 5xx, 4xx passed through".
- `products/agent-platform/src/agent_service/services/skills_client.py` — analogous `SkillsClientError` hierarchy.
- `products/agent-platform/src/agent_service/services/hitl_confirmations.py` — domain errors `ConfirmationNotFound` / `ConfirmationExpired` (both subclass `LookupError`) raised when parked confirmations expire or are missing.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError` raised for invalid policy bundles; policy decisions encoded as `PolicyDecision` dataclasses rather than exceptions.
- `products/tool-gateway/src/tool_gateway/app.py`, `products/platform-gateway/src/platform_gateway/app.py`, `products/audit-service/src/audit_service/app.py` — each service's `create_app()` installs the same `http_request` middleware and calls `configure_logging()`.
- `products/*/src/*/core/observability.py` — identical `configure_logging()` + `log_event(logger, event, **fields)` helpers used across services.
- `products/agent-platform/src/agent_service/runtime_kernel.py` — contains `UnknownModelError(ValueError)` and defensive `except Exception` blocks around kernel operations.

## Architecture and conventions

- **Per-route try/catch mapping**: Each route that calls an external client wraps the call in a `try/except` block catching the service-specific exception class and raising `HTTPException` with a stable status code. The pattern is repeated identically for incident-client and skills-client calls (see lines 962–970, 1129–1140, 1560–1575 in `routes.py`).
- **Status-code semantics are consistent**: 
  - `503` = dependency not configured (service knobs absent)
  - `502` = transport failure or upstream 5xx
  - `404` = unknown resource id (passed through from upstream 404)
  - `409` = conflict (duplicate state, expired confirmation, already published)
  - `401` / `403` = auth/authz failures
  - `422` = input validation failure
  - `410` = confirmation expired
- **Chaining without stack traces**: Mapped exceptions use `from None` to suppress the internal traceback so clients see only the HTTP response body. When re-raising a caught exception that carries its own message/status, `from exc` preserves context (e.g. `IncidentNotFound`'s `incident_id`).
- **Structured logging as the audit trail**: Every service emits `http_request` events with `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`. The root logger is explicitly set to INFO because Uvicorn defaults to WARNING, which would drop these audit events.
- **No centralized exception handler**: Error translation is deliberately local to the route that knows the semantic meaning of the exception. This keeps the mapping between domain error and HTTP posture explicit and auditable per endpoint.
- **Domain errors stay in-process**: Exceptions like `PolicyLoadError`, `StoreError`, `ConnectorConfigError`, `SettingsError` never cross process boundaries; they are converted to HTTP responses only at the API boundary.

## Conventions and constraints

- **External client calls must be wrapped**: Every call to `fetch_incident_bundle`, `validate_skill_draft`, etc. is followed by a `try/except` block that maps the client's exception hierarchy to HTTP status codes. Unwrapped calls would propagate internal exceptions to the client.
- **Never return raw tracebacks**: The incident client docstring states the house posture is "never a raw stack trace"; mapped `HTTPException`s use human-readable `detail` strings.
- **Use `from None` when converting to HTTP**: When translating a domain exception into `HTTPException`, the code consistently chains with `from None` so the server log retains the original traceback but the HTTP response does not leak internals.
- **HTTP middleware logs every request**: All four gateway/backend services install an `http` middleware that records `http_request` events with timing and status code, providing a uniform audit surface regardless of how the route handled errors.
- **Configuration errors are distinct from runtime errors**: `SettingsError` (in `incident-service` and `skills-hub`), `IncidentDependencyNotConfigured`, `SkillsDependencyNotConfigured` are separate from transport/runtime exceptions, enabling callers to distinguish misconfiguration (503) from transient failure (502).
- **Policy loading failures are fatal to the bundle, not the request**: `PolicyLoadError` is raised during policy bundle parsing/validation, not during request handling, keeping policy enforcement deterministic once loaded.