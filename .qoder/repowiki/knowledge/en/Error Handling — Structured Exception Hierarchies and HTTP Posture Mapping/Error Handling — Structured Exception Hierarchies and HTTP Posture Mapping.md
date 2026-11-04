---
kind: error_handling
name: Error Handling — Structured Exception Hierarchies and HTTP Posture Mapping
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/services/delegated_identity.py
    - products/agent-platform/src/agent_service/services/execution_protocol.py
    - products/agent-platform/src/agent_service/services/execution_worker_client.py
    - products/agent-platform/src/agent_service/services/shift_summary.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/execution-runtime/src/execution_runtime/services/execution_protocol.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/incident-service/src/incident_service/core/config.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/incident-service/src/incident_service/services/normalization.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
    - products/tool-gateway/src/tool_gateway/services/authorization_service.py
    - samples/acme-admin/app/src/acme_admin/main.py
---

## Approach

Luban is a multi-product Python workspace (FastAPI services) that uses **domain-specific exception classes** rather than raw `Exception`/`ValueError` propagation, combined with **per-route HTTP posture mapping** at the API layer. There is no global FastAPI `exception_handler` decorator; instead each route handler catches client exceptions and raises `fastapi.HTTPException` with an explicit `status_code` and human-readable `detail`. No `try/except` blocks catch `HTTPException`, so it bubbles to FastAPI's default handler.

The pattern is most clearly documented in the service-client modules:

- `products/agent-platform/src/agent_service/services/skills_client.py` — docstring: "Errors surface as a small structured hierarchy so the generation route maps them to the house posture — 503 when the dependency is not configured, 502 on transport failure or upstream 5xx — and an unvalidated draft is never returned."
- `products/agent-platform/src/agent_service/services/incident_client.py` — identical docstring wording for its own hierarchy.

## Key Files and Packages

**Agent platform (primary example of the pattern):**
- `products/agent-platform/src/agent_service/services/skills_client.py` — `SkillsClientError` base + `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected(status_code, message)`.
- `products/agent-platform/src/agent_service/services/incident_client.py` — `IncidentClientError` base + `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound(incident_id)`, `IncidentClientRejected(status_code, message)`.
- `products/agent-platform/src/agent_service/api/v2/routes.py` — central place where these are caught and mapped to `HTTPException` (lines 1205–1210, 1374–1381).
- `products/agent-platform/src/agent_service/runtime_kernel.py` — `UnknownModelError(ValueError)`.
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError(ValueError)`.
- `products/agent-platform/src/agent_service/services/delegated_identity.py` — `DelegatedIdentityError(ValueError)`.
- `products/agent-platform/src/agent_service/services/execution_protocol.py` — `ProtocolError(ValueError)`.
- `products/agent-platform/src/agent_service/services/execution_worker_client.py` — `WorkerHandoffError(Exception)`.
- `products/agent-platform/src/agent_service/services/shift_summary.py` — `DigestInputError`, `UnknownSessionError`.

**Other products define analogous per-service hierarchies:**
- `audit-service`: `StoreError`, `IngestAuthError`.
- `execution-runtime`: `ProtocolError(ValueError)`.
- `identity-broker`: `ExchangeError`.
- `incident-service`: `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError`.
- `platform-gateway`: `PolicyLoadError`, `TokenVerificationError`.
- `skills-hub`: `SettingsError`, `QueryAuthError`, `StoreError`.
- `tool-gateway`: `AuthorizationError`.

## Architecture and Conventions

### 1. Three-tier exception taxonomy

For outbound HTTP clients the taxonomy is uniform across agent-platform:

| Exception | Meaning | HTTP posture | Example file |
|---|---|---|---|
| `*DependencyNotConfigured` | Service URL / secret missing | `503` (service unavailable) | `skills_client.py`, `incident_client.py` |
| `*ServiceUnavailable` | Transport failure (`httpx.HTTPError`) or upstream `>= 500` | `502` (bad gateway) | same |
| `*NotFound` | Domain-level "not found" (e.g. unknown incident id) | `404` | `incident_client.py` |
| `*Rejected` | Upstream `4xx` | Pass-through `exc.status_code` | same |

The classification logic lives in the client module itself (`response.status_code >= 300` branch), not in the caller.

### 2. Caller-side posture mapping

Route handlers in `api/v2/routes.py` contain explicit `except <DomainError> as exc: raise HTTPException(...)` blocks. The `_validate_skill_markdown` helper (line 1194–1210) is the canonical template:

```python
except SkillsDependencyNotConfigured as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from None
except SkillsServiceUnavailable as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from None
except SkillsClientRejected as exc:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
```

The `from None` suppresses the chained traceback in logs; domain errors never leak raw stack traces to the response.

### 3. Validation failures degrade gracefully

The skill-draft generation path (`_validated_draft_sequence`, line 1275–1343) demonstrates a resilience convention: generation failures fall back to a facts-only skeleton, one bounded regeneration is attempted, and only after a second validation failure does the route return `502`. The docstring states: "generation never raises — any failure degrades to the anchor's facts-only skeleton, which is always format-valid; a second validation failure answers 502, never an unvalidated draft." This is a product-level invariant enforced by the code path, not just a comment.

### 4. Non-HTTP domains use plain exceptions

Domain logic inside services raises typed exceptions (`ValueError` subclasses for configuration/model errors, `Exception` subclasses for business failures). These are expected to be caught by the nearest route handler; there is no global middleware catching them. For example, `RuntimeKernel.get_model()` raises `UnknownModelError`; callers must handle it.

### 5. Samples show the alternative

`samples/acme-admin/app/src/acme_admin/main.py` registers a custom `@app.exception_handler(AdminAuthRequired)` — demonstrating that custom exception handlers exist but are used sparingly (only in sample apps, not in the core Luban services).

## Conventions and Constraints

- **Structured exception hierarchy**: Each outbound client defines a small base class plus named subclasses for `DependencyNotConfigured`, `ServiceUnavailable`, `NotFound`, and `Rejected`. Observed in both `skills_client.py` and `incident_client.py`.
- **Posture mapping at the boundary**: Route handlers translate domain exceptions into `HTTPException` with explicit status codes; the translation table is documented in the client module docstrings.
- **No raw tracebacks**: All `raise HTTPException(...)` calls use `from None` when wrapping domain exceptions, preventing stack traces from leaking into logs/responses.
- **Upstream 4xx pass-through**: `*Rejected` exceptions carry the original `status_code` and `message` attributes, and routes re-raise them verbatim via `exc.status_code` / `exc.message`.
- **Validation paths never return unvalidated artifacts**: The skill-draft generation flow enforces that every response is either a validated draft or a degraded skeleton; this is stated in docstrings and implemented by the fallback-to-skeleton logic.
- **No global exception middleware**: A grep for `@app.exception_handler` finds only the sample app; core services rely on per-route `try/except` blocks.
- **Domain errors are plain Python exceptions**, not Pydantic/validation errors — FastAPI's built-in 422 handling is used separately for request-body validation, while business errors use the custom hierarchies above.