---
kind: error_handling
name: Error Handling Across Luban Services — Structured Exceptions, HTTPException Mapping, and Per-Service Error Hierarchies
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/app.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/execution_worker_client.py
    - products/agent-platform/src/agent_service/services/shift_summary.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/incident-service/src/incident_service/services/normalization.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
---

## Approach

Luban is a multi-service Python monorepo (FastAPI + httpx). There is no shared error package; each product defines its own small exception hierarchy and maps those exceptions to HTTP responses at the API boundary. The common pattern is:

1. Domain / client-layer code raises a **structured subclass of `Exception`** (or `ValueError`) carrying a human-readable message.
2. The FastAPI route layer catches those exceptions and converts them into `fastapi.HTTPException(status_code=..., detail=...)`.
3. No global `@app.exception_handler` is registered in any service — error mapping is done inline in routes or small helpers.
4. For cross-service calls, the caller wraps `httpx.HTTPError` and upstream status codes into a per-client structured exception so the caller can distinguish "not configured" (503) from "unreachable/upstream 5xx" (502) from "upstream rejected us" (pass-through 4xx).

## Key files and packages

Per-product exception definitions (non-exhaustive):

- `products/agent-platform/src/agent_service/services/skills_client.py` — `SkillsClientError`, `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected` (with `status_code` + `message` attributes).
- `products/agent-platform/src/agent_service/services/incident_client.py` — `IncidentClientError` and related client errors.
- `products/agent-platform/src/agent_service/services/execution_worker_client.py` — `WorkerHandoffError`.
- `products/agent-platform/src/agent_service/services/shift_summary.py` — `DigestInputError`, `UnknownSessionError`.
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError(ValueError)`.
- `products/agent-platform/src/agent_service/runtime_kernel.py` — `UnknownModelError(ValueError)`.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError(Exception)` raised during bundle load/validation.
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError(Exception)` with a `detail` attribute.
- `products/audit-service/src/audit_service/services/audit_store.py` — `StoreError`.
- `products/audit-service/src/audit_service/services/ingest_auth.py` — `IngestAuthError`.
- `products/incident-service/src/incident_service/core/config.py` — `SettingsError`.
- `products/incident-service/src/incident_service/services/connectors.py` — `ConnectorConfigError`.
- `products/incident-service/src/incident_service/services/incident_store.py` — `StoreError`.
- `products/incident-service/src/incident_service/services/normalization.py` — `NormalizationError`.
- `products/incident-service/src/incident_service/services/query_auth.py` — `QueryAuthError`.
- `products/incident-service/src/incident_service/services/triage.py` — `TriageError`.
- `products/skills-hub/src/skills_hub/core/config.py` — `SettingsError`.
- `products/skills-hub/src/skills_hub/services/query_auth.py` — `QueryAuthError`.
- `products/skills-hub/src/skills_hub/services/skill_store.py` — `StoreError`.

HTTP mapping locations:

- `products/agent-platform/src/agent_service/api/v2/routes.py` — central place where domain/client exceptions are caught and turned into `HTTPException`. Example: `_validate_skill_markdown` maps `SkillsDependencyNotConfigured → 503`, `SkillsServiceUnavailable → 502`, `SkillsClientRejected` → pass-through `exc.status_code` with `exc.message`; similar try/except blocks around incident/draft builders map `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`, `NoValidatedTriageReport`.
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — wraps PyJWT exceptions (`ExpiredSignatureError`, `InvalidIssuerError`, `InvalidAudienceError`, `InvalidTokenError`) into `TokenVerificationError(detail=...)`.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — raises `PolicyLoadError` for malformed YAML, missing fields, invalid outcomes, and disallowed `require_approval` combinations.

Observability/logging middleware:

- `products/agent-platform/src/agent_service/app.py` registers an `http` middleware that logs every request/response pair (method, path, status_code, duration_ms) via `log_event` with `service="agent-service"` and `request_id`. It does not transform errors — it observes them after they have been converted to `HTTPException` by the route layer.

## Architecture and conventions

### Structured exception hierarchies per subsystem

Each service defines a small tree rooted at a per-subsystem `*Error(Exception)` class. The root carries only a message; subclasses specialize the semantic meaning (e.g. dependency-not-configured vs. transport failure vs. upstream rejection). This lets callers match on the most specific type rather than inspecting strings.

The `SkillsClientError` hierarchy is the clearest example: the base class exists solely as a namespace, while `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, and `SkillsClientRejected` carry enough context for the caller to choose the correct HTTP posture (503, 502, or passthrough 4xx).

### HTTP mapping lives at the route boundary

Domain and client code never raise `HTTPException`. Routes (or small route-level helpers like `_validate_skill_markdown`) catch the structured exceptions and emit `HTTPException`. This keeps business logic framework-free and makes the HTTP contract explicit at the edge.

### Cross-service error classification is uniform

For outbound calls the convention is three-way classification:

| Condition | Exception raised | HTTP mapped to |
|---|---|---|
| Dependency not configured | `*DependencyNotConfigured` | 503 |
| Transport failure or upstream 5xx | `*ServiceUnavailable` | 502 |
| Upstream 4xx | `*ClientRejected(status_code, message)` | passthrough `status_code` |

This is documented in the module docstring of `skills_client.py` and implemented identically for the incident client path.

### Policy and token verification use flat single-purpose errors

`PolicyLoadError` and `TokenVerificationError` are not part of a larger hierarchy — they are leaf exceptions raised by their respective services. `TokenVerificationError` stores its message in a `detail` attribute so the caller can surface it directly.

### No global exception handler

A search for `@app.exception_handler` across `products/*/src/**/*.py` returns zero matches. Error-to-HTTP conversion is always explicit in route handlers. The agent-platform's `app.py` only installs logging and metrics middleware; it does not install a top-level exception handler.

### Validation failures return structured HTTP codes

Route-level validation uses standard HTTP semantics: 400 for bad input, 401 for missing auth headers, 404 for not-found resources, 409 for conflict (e.g. missing triage report), 410 for expired confirmations, 422 for schema/validation failures, 502/503 for degraded dependencies. These are raised directly as `HTTPException(...)` in `routes.py`.

## Conventions and constraints

- **Observed convention:** Each product defines its own `*Error` classes under the relevant `services/` or `core/` module; there is no shared `errors` package.
- **Observed convention:** Outbound client layers wrap `httpx.HTTPError` and upstream status codes into a three-tier structured exception hierarchy (`*DependencyNotConfigured`, `*ServiceUnavailable`, `*ClientRejected`).
- **Observed convention:** Route handlers catch these structured exceptions and convert them to `HTTPException` with a stable status code; the message comes from `str(exc)` or an explicit `exc.message` attribute.
- **Observed constraint:** `SkillsClientError` subclasses are designed so the generation route "maps them to the house posture — 503 when the dependency is not configured, 502 on transport failure or upstream 5xx — and an unvalidated draft is never returned" (documented in `skills_client.py` module docstring and enforced by the `_validated_draft_sequence` helper which falls back to a facts-only skeleton on second validation failure).
- **Observed constraint:** `PolicyLoadError` is raised whenever a policy bundle is malformed, missing, or contains invalid rule shapes; `load_bundle` documentation states it raises `PolicyLoadError` on a configured-but-missing/invalid path rather than falling back silently.
- **Observed constraint:** `TokenVerificationError` wraps all PyJWT exceptions uniformly, so callers do not need to know about `jwt.ExpiredSignatureError`, `jwt.InvalidIssuerError`, etc.
- **Observed constraint:** No service registers a global `@app.exception_handler`; error mapping is performed inline at the route layer.