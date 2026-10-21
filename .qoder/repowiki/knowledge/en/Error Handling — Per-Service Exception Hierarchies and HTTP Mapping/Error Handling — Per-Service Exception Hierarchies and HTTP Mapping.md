---
kind: error_handling
name: Error Handling — Per-Service Exception Hierarchies and HTTP Mapping
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/api/routes/auth.py
    - products/platform-gateway/src/platform_gateway/api/routes/policy.py
    - products/platform-gateway/src/platform_gateway/api/routes/tools.py
    - products/platform-gateway/src/platform_gateway/services/incident_client.py
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
---

## Approach

The Luban platform does not use a shared error framework. Each Python service under `products/` defines its own small exception hierarchy rooted at plain `Exception` (or sometimes `ValueError`) and translates those exceptions to FastAPI `HTTPException`s at the API boundary. There is no global exception handler; routes catch domain exceptions explicitly and raise `HTTPException(status_code=..., detail=...)`. The only place a custom `@app.exception_handler` decorator appears is in the sample app (`samples/acme-admin/app/src/acme_admin/main.py`).

## Key files and packages

**Agent-platform** (`products/agent-platform/src/agent_service/`):
- `services/skills_client.py` — `SkillsClientError` base, plus `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected` (with `status_code`/`message` attributes).
- `services/incident_client.py` — `IncidentClientError` base, plus `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`.
- `services/hitl_confirmations.py` — `ConfirmationNotFound(LookupError)`.
- `services/shift_summary.py` — `DigestInputError`, `UnknownSessionError`, `DevelopmentSessionRejected`.
- `services/execution_protocol.py` — `ProtocolError(ValueError)`.
- `providers/base.py` — `ProviderConfigurationError(ValueError)`.
- `runtime_kernel.py` — `UnknownModelError(ValueError)`.
- `api/v2/routes.py` — central mapping site for client errors into 503/502/4xx `HTTPException`s (see `_validate_skill_markdown` and incident-draft route).

**Platform-gateway** (`products/platform-gateway/src/platform_gateway/`):
- `services/token_verifier.py` — `TokenVerificationError(Exception)`, raised on key resolution failure, expiry, wrong issuer/audience.
- `services/policy_engine.py` — `PolicyLoadError(Exception)`, raised for invalid YAML, missing fields, malformed rules.
- `api/routes/auth.py` — catches `TokenVerificationError` and returns `{"authenticated": False}` rather than propagating it.
- `api/routes/policy.py` — catches `PolicyLoadError` and maps to an HTTP response.
- `api/routes/tools.py` — catches `HTTPException` from downstream calls and wraps it in a `JSONResponse` with `Cache-Control: no-store`.
- `services/incident_client.py` — translates non-2xx upstream responses into `HTTPException` with the upstream status code or a fallback 502.

**Other services** follow the same per-service pattern:
- `audit-service`: `StoreError`, `IngestAuthError`.
- `incident-service`: `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError`.
- `skills-hub`: `SettingsError`, `QueryAuthError`, `StoreError`.
- `execution-runtime`: `ProtocolError(ValueError)`.

## Architecture and conventions

1. **Per-service exception hierarchies.** Each outbound client or domain layer defines a small tree of exceptions. For example, `SkillsClientError` → `SkillsDependencyNotConfigured` / `SkillsServiceUnavailable` / `SkillsClientRejected`; `IncidentClientError` → `IncidentDependencyNotConfigured` / `IncidentServiceUnavailable` / `IncidentNotFound` / `IncidentClientRejected`. This lets callers branch on exact failure mode rather than inspecting strings.

2. **Structured attributes on rejected-client errors.** `SkillsClientRejected` and `IncidentClientRejected` carry both `status_code` and `message`, so the route can pass through the upstream's original 4xx posture instead of collapsing it to a generic 400.

3. **HTTP mapping lives at the route layer, not in middleware.** Routes wrap calls like `build_incident_skill_draft_bundle` and `validate_skill_draft` in explicit `try/except` blocks that map each exception to a specific `HTTPException`. The docstring in `agent_service/api/v2/routes.py` codifies the house posture: "not configured 503, unreachable or upstream 5xx 502, any other 4xx passed through".

4. **Consistency over availability on knowledge-production paths.** The skill-draft generation path (`_validated_draft_sequence`) is designed so generation never raises — failures degrade to a facts-only skeleton, and a second validation failure answers 502 rather than returning an unvalidated draft. The comment states: "consistency outranks availability on a knowledge-production path".

5. **Domain-layer exceptions are `Exception` subclasses; configuration/validation errors are `ValueError` subclasses.** Provider configuration, unknown model, and protocol errors derive from `ValueError`; transport/auth/store/domain errors derive from `Exception`. Tests assert against these concrete types (e.g. `test_gateway_auth.py` asserts `TokenVerificationError`).

6. **No global exception-to-HTTP mapper.** Unlike many FastAPI apps, there is no `@app.exception_handler` wiring for these domain exceptions. Each route handles its own exceptions. The only global handler in the repo is in the sample app.

7. **Upstream clients normalize transport vs. application errors.** Both `skills_client.validate_skill_draft` and `platform_gateway.services.incident_client` distinguish between `httpx.HTTPError` (transport → 502/unavailable), upstream 5xx (service unavailable), and upstream 4xx (rejected, passed through). Configuration absence is caught before the network call and mapped to 503.

## Conventions and constraints observed

- Domain exceptions are defined as classes inside the module that raises them, not in a shared package.
- Client-facing errors surface as `fastapi.HTTPException` with a numeric `status_code` and a human-readable `detail` string; raw tracebacks are not returned to callers.
- Dependency-not-configured failures consistently map to HTTP 503; transport/upstream 5xx failures map to 502; upstream 4xx failures are passed through via the `status_code` attribute on `*ClientRejected`.
- `from None` is used when re-raising `HTTPException` to suppress the chained traceback in logs.
- Token verification failures in the gateway are swallowed silently and converted to `{"authenticated": False}` rather than surfaced as errors, keeping auth endpoints idempotent and safe for probing.
- Policy load failures are caught at the policy route and translated to an HTTP response, preventing startup-time policy parsing errors from crashing the process.