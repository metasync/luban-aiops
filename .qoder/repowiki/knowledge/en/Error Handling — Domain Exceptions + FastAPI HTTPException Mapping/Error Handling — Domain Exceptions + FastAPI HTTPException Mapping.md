---
kind: error_handling
name: Error Handling — Domain Exceptions + FastAPI HTTPException Mapping
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/incident_client.py
    - products/tool-gateway/src/tool_gateway/api/routes/authorizations.py
    - products/tool-gateway/src/tool_gateway/core/dependencies.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - samples/acme-admin/app/src/acme_admin/main.py
---

## Approach

Luban's services use a two-layer error model built on Python exceptions and FastAPI:

1. **Domain/service-level exceptions** — per-product, per-module exception classes (usually `*Error` or `*Exception`) that carry structured context rather than raw tracebacks.
2. **HTTP translation at the API layer** — route handlers / service clients catch domain exceptions and raise `fastapi.HTTPException(status_code=..., detail=...)`, which is FastAPI's standard response mechanism. There is no global exception handler; each product translates locally.

The only repository-wide `@app.exception_handler(...)` registration lives in the sample app (`samples/acme-admin/app/src/acme_admin/main.py`), where `AdminAuthRequired` is mapped to a JSON `unauthorized()` response. None of the production microservices register a custom global exception handler — they rely on FastAPI's default JSON error shape.

## Key files and packages

- `products/agent-platform/src/agent_service/services/skills_client.py` — defines `SkillsClientError` base plus `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`; the docstring explicitly states the mapping: dependency-not-configured → 503, transport/upstream-5xx → 502, upstream 4xx passed through with its status code.
- `products/agent-platform/src/agent_service/api/v2/routes.py` — central HTTP translator for agent-service routes; catches client errors and raises `HTTPException(503|502|exc.status_code, ...)`. Also contains ad-hoc `HTTPException` raises for auth/validation failures (401, 422, 404, 409).
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError` base with `HumanIdentityRequired` subclass; all `jwt.*` exceptions are caught and re-raised as `TokenVerificationError("token expired" | "invalid token issuer" | ...)`.
- `products/platform-gateway/src/platform_gateway/services/incident_client.py` — wraps HTTP calls to incident-service, raising `HTTPException` directly (no intermediate domain class) with status codes from the upstream response.
- Per-product stores/auth modules define their own `StoreError`, `IngestAuthError`, `ConnectorConfigError`, `NormalizationError`, `QueryAuthError`, `TriageError`, `ExchangeError`, `PolicyLoadError`, `CliError`, etc., following the same `*Error(Exception)` pattern.

## Architecture and conventions

### Exception hierarchy

Each product keeps its domain exceptions close to the code that raises them:

| Product | Base exception(s) | Purpose |
|---|---|---|
| agent-platform | `ProviderConfigurationError(ValueError)`, `UnknownModelError(ValueError)`, `DelegatedIdentityError(ValueError)`, `ProtocolError(ValueError)`, `WorkerHandoffError`, `IncidentClientError`, `SkillsClientError`, `DigestInputError`, `UnknownSessionError` | Configuration, protocol, worker handoff, skill-draft validation |
| audit-service | `StoreError`, `IngestAuthError` | Store and ingestion auth failures |
| execution-runtime | `ProtocolError(ValueError)` | Execution protocol violations |
| identity-broker | `ExchangeError` | OIDC exchange failures |
| incident-service | `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError` | Config, store, normalization, triage |
| platform-gateway | `PolicyLoadError`, `TokenVerificationError` (+ `HumanIdentityRequired`) | Policy engine, JWT verification |
| skills-hub | `SettingsError`, `QueryAuthError`, `StoreError` | Store/query/auth |
| tool-gateway | `CliError` | CLI invocation failures |

Some base classes derive from `ValueError` (configuration/protocol errors that are really invalid inputs) while others derive from plain `Exception` (operational failures). The choice is local to each module; there is no shared root exception type across products.

### Client-side error classification

The `skills_client` module documents and enforces a consistent three-class split for outbound dependencies:

- `*DependencyNotConfigured` → caller maps to **503 Service Unavailable** (feature not configured).
- `*ServiceUnavailable` → caller maps to **502 Bad Gateway** (transport failure or upstream 5xx).
- `*ClientRejected` → carries `status_code` and `message`; caller passes the original status through unchanged.

This pattern appears in `routes.py`'s `_validate_skill_markdown` helper:

```python
except SkillsDependencyNotConfigured as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from None
except SkillsServiceUnavailable as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from None
except SkillsClientRejected as exc:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
```

The `from None` suppresses the traceback chain for user-facing errors; `from exc` preserves it for internal diagnostics.

### Upstream passthrough

Services that proxy to other Luban services often forward the upstream HTTP status verbatim:

- `platform-gateway/services/incident_client.py`: `raise HTTPException(status_code=response.status_code, detail=message)`
- `tool-gateway/api/routes/authorizations.py`: `raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None`
- `identity-broker/api/routes/auth.py`: `raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc`

### Validation vs. operational errors

Route handlers distinguish between input-validation failures (400/422/409) and downstream failures (502/503). For example, `_validated_draft_sequence` in `agent_service/api/v2/routes.py` guarantees that an unvalidated draft is never returned: generation failure degrades to a facts-only skeleton, and if even the skeleton fails format validation, it answers 502.

### No global exception middleware

No product registers a global `exception_handler` for `HTTPException` or for its domain exceptions. Error responses follow FastAPI's default JSON shape (`{"detail": ...}`), except the acme-admin sample which overrides `AdminAuthRequired` to return a custom `unauthorized()` JSON body.

## Conventions and constraints

- Domain exceptions are raised inside service/client layers; API route handlers translate them to `HTTPException`. This separation is observed consistently across agent-platform, platform-gateway, tool-gateway, and the other products.
- Outbound dependency failures are classified into configuration-missing (503), transport/upstream-5xx (502), and upstream-4xx (passthrough) using a small exception hierarchy — documented explicitly in `skills_client.py` and mirrored in callers.
- `from None` is used when chaining suppressed tracebacks for user-facing errors; `from exc` is used when preserving diagnostic chains for internal errors.
- Structured fields on exceptions (e.g. `SkillsClientRejected.status_code` / `.message`, `TokenVerificationError.detail`, `AdminAuthRequired.message`) are consumed by the route handler rather than relying on exception string representation alone.
- There is no repository-wide base error class, no centralized error-code registry, and no global FastAPI exception handler in production services — the pattern is decentralized per product.
- The only documented enforcement is the contract stated in `skills_client.py`'s module docstring: "errors surface as a small structured hierarchy so the generation route maps them to the house posture — 503 when the dependency is not configured, 502 on transport failure or upstream 5xx — and an unvalidated draft is never returned." The caller in `routes.py` enforces this contract via explicit `try/except` blocks.