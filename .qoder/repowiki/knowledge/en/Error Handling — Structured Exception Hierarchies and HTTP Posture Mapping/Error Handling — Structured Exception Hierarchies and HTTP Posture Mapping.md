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
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/execution-runtime/src/execution_runtime/services/execution_protocol.py
---

# Error Handling in Luban Agentic AIOps Platform

## Approach Overview

The platform uses a **two-layer error model** consistent across all Python services (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway):

1. **Domain-level exceptions**: per-module `*Error` classes that encode business semantics (configuration missing, service unavailable, not found, rejected by upstream). These are raised inside services and clients.
2. **HTTP-level translation**: route handlers convert domain exceptions into FastAPI `HTTPException`s with explicit status codes, never leaking raw stack traces to the wire.

There is no centralized exception base class shared across products; each product defines its own hierarchy rooted at either `Exception` or `ValueError`. There is no repository-wide `errors/` package — errors live next to the code that raises them.

## Domain Exception Patterns

### Client-to-upstream error hierarchies

The most consistent pattern appears in cross-service HTTP clients under `services/<name>_client.py`. Two canonical examples:

- `products/agent-platform/src/agent_service/services/skills_client.py` defines `SkillsClientError` → `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`.
- `products/agent-platform/src/agent_service/services/incident_client.py` defines `IncidentClientError` → `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`.

Each client follows the same contract:
- `is_configured(settings)` checks URL + secret presence before making a call.
- Transport failures (`httpx.HTTPError`) become `<Name>ServiceUnavailable`.
- Upstream `>=500` becomes `<Name>ServiceUnavailable`.
- Upstream `4xx` becomes `<Name>ClientRejected(status_code, message)`, carrying both `status_code` and `message` attributes so callers can pass them through verbatim.
- `_upstream_message(response)` extracts the upstream `error.message` field when present, falling back to a generic string.

This pattern is replicated for other outbound clients (e.g., `incident_client.py`, `skills_client.py`).

### In-process domain errors

Other modules define small, purpose-specific hierarchies:

- `agent_service/providers/base.py`: `ProviderConfigurationError(ValueError)` — configuration validation for LLM providers.
- `agent_service/runtime_kernel.py`: `UnknownModelError(ValueError)`.
- `agent_service/services/agent_role.py`: `AgentRoleError(ValueError)`.
- `agent_service/services/delegated_identity.py`: `DelegatedIdentityError(ValueError)`.
- `agent_service/services/execution_protocol.py`: `ProtocolError(ValueError)`.
- `agent_service/services/hitl_confirmations.py`: `ConfirmationNotFound(LookupError)`, `ConfirmationExpired(LookupError)` — in-memory confirmation registry errors.
- `audit-service`: `StoreError`, `IngestAuthError`.
- `execution-runtime`: `ProtocolError(ValueError)` mirroring the agent-platform variant.
- `identity-broker`: `ExchangeError(Exception)`.
- `incident-service`: `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError`.
- `platform-gateway`: `PolicyLoadError(Exception)`, `TokenVerificationError(Exception)`.
- `skills-hub`: `SettingsError`, `QueryAuthError`, `StoreError`.

Most of these inherit from `Exception`; those representing invalid input/configuration often inherit from `ValueError`.

## HTTP Translation Layer

FastAPI route handlers perform the mapping from domain exceptions to HTTP responses. The canonical example is `products/agent-platform/src/agent_service/api/v2/routes.py`:

```python
except SkillsDependencyNotConfigured as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from None
except SkillsServiceUnavailable as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from None
except SkillsClientRejected as exc:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
```

The same shape repeats for incident-client calls:

```python
except IncidentDependencyNotConfigured as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from None
except IncidentServiceUnavailable as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from None
except IncidentNotFound as exc:
    raise HTTPException(status_code=404, detail="incident not found") from exc
except IncidentClientRejected as exc:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
```

Key conventions observed in the translation layer:

- `from None` is used on re-raises to suppress the original traceback chain, preventing raw stack traces from leaking into HTTP responses.
- Dependency-not-configured cases consistently map to **503 Service Unavailable**.
- Transport / upstream 5xx cases consistently map to **502 Bad Gateway**.
- Upstream 4xx cases are passed through via `exc.status_code` and `exc.message`.
- Structural 404s use a fixed human-readable detail rather than echoing the domain exception message.
- Authorization failures raise `HTTPException(status_code=401, detail=...)` directly in routes (e.g., missing `X-User-ID`, unverified human identity).

The platform-gateway's own routes follow the same posture: `503` for "not configured", `502` for transport/upstream failure, and direct `HTTPException` raises for auth/validation failures.

## House Posture Rules

The docstrings and comments codify an explicit policy:

> "structured errors map to the house posture: not configured 503, unreachable or upstream 5xx 502, any other 4xx passed through — an unvalidated draft is never returned."

This rule appears verbatim in multiple places:

- `skills_client.py` module docstring: "Errors surface as a small structured hierarchy so the generation route maps them to the house posture — 503 when the dependency is not configured, 502 on transport failure or upstream 5xx — and an unvalidated draft is never returned (consistency outranks availability on a knowledge-production path)."
- `incident_client.py` module docstring: same wording adapted for the incident document path.
- `_validate_skill_markdown` helper in `api/v2/routes.py`: comment restates the mapping.

## Fail-Closed Design

A recurring safety pattern is **fail-closed over fail-open**:

- In-memory HITL confirmations (`hitl_confirmations.py`): "a parked confirmation never survives a restart — after an agent rebuild the entry is simply gone and any confirm attempt fails closed (404/410), never auto-running a parked tool call."
- Skill-draft generation: if validation fails twice, the route falls back to a facts-only skeleton that is guaranteed format-valid; it never returns an unvalidated draft.
- Secret deliveries generated during a park ride across resume but are released only on commit; mid-approval restart drops them and they expire unreleased — described as "fail-safe — no leak, no orphaned Copy button".

## No Global Middleware

There is no repository-wide exception middleware registered via `@app.exception_handler` or FastAPI's `add_exception_handler`. The only custom handler found is in the sample app `samples/acme-admin/app/src/acme_admin/main.py`, which registers a handler for `AdminAuthRequired`. Production services rely on explicit `try/except` blocks in route handlers rather than global exception handling.

## Summary of Conventions

| Concern | Convention |
|---|---|
| Domain errors | Per-module `*Error` classes, grouped under a base `*Error(Exception)` where there are multiple variants |
| Invalid input / config | Often subclass `ValueError` |
| Cross-service clients | Three-tier hierarchy: `*DependencyNotConfigured` (503), `*ServiceUnavailable` (502), `*ClientRejected` (passthrough 4xx) |
| HTTP translation | Explicit `try/except` in route handlers raising `HTTPException` with documented status codes |
| Traceback hygiene | `raise ... from None` on re-raises to avoid leaking stack traces |
| Safety posture | Fail-closed for parked operations; never return unvalidated artifacts |
| Centralization | No shared exception package; patterns are replicated by convention rather than enforced by a common base class |