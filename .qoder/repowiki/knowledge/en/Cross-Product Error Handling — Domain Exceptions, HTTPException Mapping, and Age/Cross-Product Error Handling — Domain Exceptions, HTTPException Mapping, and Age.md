---
kind: error_handling
name: Cross-Product Error Handling — Domain Exceptions, HTTPException Mapping, and AgentScope Middleware
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/kernel_middleware.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/execution_protocol.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/services/delegated_identity.py
    - products/agent-platform/src/agent_service/services/execution_worker_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/shift_summary.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/incident-service/src/incident_service/core/config.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/incident-service/src/incident_service/services/normalization.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/incident-service/src/incident_service/services/triage.py
---

## Approach

Luban is a multi-product Python monorepo (FastAPI services + AgentScope runtime) with no single shared error package. Each product defines its own domain exception classes near the code that raises them, and API routes translate those exceptions into FastAPI `HTTPException`s. Cross-cutting behavior inside the agent runtime is expressed as AgentScope `MiddlewareBase` subclasses rather than try/except blocks.

## Key files and packages

**Domain exception definitions (per product):**
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError(ValueError)`
- `products/agent-platform/src/agent_service/runtime_kernel.py` — `UnknownModelError(ValueError)`
- `products/agent-platform/src/agent_service/services/delegated_identity.py` — `DelegatedIdentityError(ValueError)`
- `products/agent-platform/src/agent_service/services/execution_protocol.py` — `ProtocolError(ValueError)` with a `.reason` attribute; also `VerifiedOriginal` authority wrapper
- `products/agent-platform/src/agent_service/services/execution_worker_client.py` — `WorkerHandoffError(Exception)`
- `products/agent-platform/src/agent_service/services/incident_client.py` — `IncidentClientError(Exception)`
- `products/agent-platform/src/agent_service/services/skills_client.py` — `SkillsClientError(Exception)`
- `products/agent-platform/src/agent_service/services/shift_summary.py` — `DigestInputError`, `UnknownSessionError`
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError(Exception)` (+ `HumanIdentityRequired` subclass)
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError`
- `products/audit-service/src/audit_service/services/audit_store.py` — `StoreError`
- `products/audit-service/src/audit_service/services/ingest_auth.py` — `IngestAuthError`
- `products/incident-service/src/incident_service/core/config.py` — `SettingsError`
- `products/incident-service/src/incident_service/services/connectors.py` — `ConnectorConfigError`
- `products/incident-service/src/incident_service/services/incident_store.py` — `StoreError`
- `products/incident-service/src/incident_service/services/normalization.py` — `NormalizationError`
- `products/incident-service/src/incident_service/services/query_auth.py` — `QueryAuthError`
- `products/incident-service/src/incident-service/services/triage.py` — `TriageError`
- `products/skills-hub/src/skills_hub/core/config.py` — `SettingsError`
- `products/skills-hub/src/skills_hub/services/query_auth.py` — `QueryAuthError`
- `products/skills-hub/src/skills_hub/services/skill_store.py` — `StoreError`

**HTTP boundary translation:**
- `products/agent-platform/src/agent_service/api/v2/routes.py` — the principal place where domain exceptions are caught and re-raised as `fastapi.HTTPException` with explicit status codes (401, 404, 422, 502, 503).

**AgentScope middleware (cross-cutting kernel behavior):**
- `products/agent-platform/src/agent_service/services/kernel_middleware.py` — `GatewayPermissionMiddleware`, `ToolEvidenceMiddleware`, `TargetAuthorizationMiddleware`, `TokenUsageMiddleware`. These implement permission gates, evidence emission, authorization flow control, and token accounting via the supported `MiddlewareBase` hooks (`on_check_permission`, `on_acting`, `on_model_call`, `on_compress_context`). They do not raise domain errors; they return `PermissionDecision(ASK/DENY/ALLOW)` or transform tool results.

**Application-level exception handler:**
- Only one `@app.exception_handler(...)` exists in the repo, in `samples/acme-admin/app/src/acme_admin/main.py` (for `AdminAuthRequired`). No product registers a global FastAPI exception handler; translation happens inline in route handlers.

## Architecture and conventions

1. **Layered exception propagation.** Domain logic raises typed exceptions (e.g. `ProtocolError`, `DelegatedIdentityError`, `TokenVerificationError`). Service-layer callers catch them and either log/warn-and-return-fallback or re-raise as an `HTTPException` at the API boundary. For example, `runtime_kernel._resolve_run_id` catches `ProtocolError` and logs a warning, returning `None` instead of propagating it.

2. **HTTP mapping is explicit per route.** In `api/v2/routes.py`, each call site wraps a service call in `try/except` and raises `HTTPException(status_code=..., detail=...)`. There is no centralized exception-to-status-code registry.

3. **Domain exceptions extend `ValueError` or `Exception`.** Configuration/validation failures typically subclass `ValueError` (e.g. `ProviderConfigurationError`, `UnknownModelError`, `ProtocolError`), while client/network/service failures subclass bare `Exception` (e.g. `WorkerHandoffError`, `IncidentClientError`, `SkillsClientError`). This lets callers distinguish "bad input" from "external failure" without importing a common base.

4. **Fail-soft / best-effort paths swallow exceptions.** Methods whose contract says "never raises" (e.g. `_snapshot_state`, `_persist_evidence`) catch `Exception`, record a metric via `record_agent_state_error` / `record_evidence_write`, and log a `LOGGER.warning`. Corrupt persisted state is discarded rather than failing the session.

5. **Kernel middlewares replace ad-hoc try/except for cross-cutting concerns.** Permission checks, evidence emission, authorization gating, and LLM-token accounting live in `kernel_middleware.py` as `MiddlewareBase` subclasses, keeping the agent runtime free of scattered error-handling branches.

6. **Structured protocol errors carry a stable reason code.** `ProtocolError` stores a string `.reason` (`"bad_request"`, `"protocol_unsupported"`, `"signing_unavailable"`, `"signature_invalid"`, `"lifetime_invalid"`, `"identity_conflict"`, `"response_invalid"`, `"metadata_replay"`). Callers match on the exception type and log the reason rather than parsing message text.

7. **Credential redaction around error surfaces.** `AgentKernel.remember_error` runs the exception message through `redact_assistant_text` before storing it in `_last_error`; `build_provider_error_message` then exposes the redacted version to the portal. Evidence frames similarly run parameters/results through `redact_structure` / `redact_result_data`.

8. **Pydantic validation errors are treated as protocol/input errors.** `ValidationError` is caught alongside `ValueError`/`TypeError` when validating execution contracts and converted to `ProtocolError("bad_request")`.

## Conventions and constraints

- **Observed convention:** Domain exceptions are defined next to the module that raises them and named `<Area>Error` (e.g. `StoreError`, `SettingsError`, `PolicyLoadError`, `TokenVerificationError`). There is no shared `errors/` package across products.
- **Observed convention:** API routes raise `fastapi.HTTPException` directly with an explicit numeric `status_code`; no custom JSON error envelope class is used.
- **Observed convention:** Non-critical side effects (state snapshots, evidence persistence, audit emission) catch `Exception`, emit a structured metric, log a warning, and continue — documented in docstrings as "Never raises".
- **Enforced by design:** `GatewayPermissionMiddleware` returns `PermissionBehavior.ASK` for tools outside the vetted allow-list rather than delegating to agentscope's `PermissionEngine`, because the engine's read-only fast path would auto-allow unvetted read-only gateway tools and silently bypass the platform allow-list (documented in the middleware docstring).
- **Enforced by design:** The auto-allow list is constrained to read-only tools only; mutating tools carrying `is_read_only=False` cannot be auto-approved even if named in `AGENT_GATEWAY_TOOL_AUTO_ALLOW` (enforced by the `tool is not None and getattr(tool, "is_read_only", False)` guard in `GatewayPermissionMiddleware.on_check_permission`).
- **Enforced by design:** `VerifiedOriginal` rejects copy/reduce operations (`__copy__`, `__deepcopy__`, `__reduce__` all raise `TypeError`) so validated original responses cannot leak across process boundaries; `revalidate` additionally checks `os.getpid()`.
- **Enforced by design:** `ProtocolError` is raised for every schema/signature/lifetime mismatch in the execution protocol; callers match on the exception type and map to a stable reason code rather than inspecting messages.
- **Not enforced:** There is no repository-wide rule against using bare `except Exception`; several defensive fallbacks use it explicitly (with `# noqa: BLE001` comments). The convention is to prefer specific exception types but fall back to broad catches for fire-and-forget paths.