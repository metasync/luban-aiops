---
kind: error_handling
name: Cross-Service Error Handling — Structured Exception Hierarchies Mapped to HTTP Status Codes
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/services/execution_worker_client.py
    - products/agent-platform/src/agent_service/services/shift_summary.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/incident-service/src/incident_service/core/config.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
    - products/execution-runtime/src/execution_runtime/services/execution_protocol.py
    - samples/acme-admin/app/src/acme_admin/main.py
---

## Approach

Luban is a multi-service Python monorepo (FastAPI + httpx). Each service defines its own small, local exception hierarchy under `services/` (and occasionally `core/`) and maps those exceptions to HTTP responses **inline in route handlers** rather than via a global `@app.exception_handler`. There is no shared error package; each product owns its types.

## Key files and packages

- `products/agent-platform/src/agent_service/services/skills_client.py` — `SkillsClientError` → `SkillsDependencyNotConfigured` / `SkillsServiceUnavailable` / `SkillsClientRejected`; caller in `api/v2/routes.py` maps them to 503 / 502 / passthrough.
- `products/agent-platform/src/agent_service/services/incident_client.py` — same shape: `IncidentClientError` → `IncidentDependencyNotConfigured` / `IncidentServiceUnavailable` / `IncidentNotFound`.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError` for invalid policy bundles; `TokenVerificationError` for JWT failures.
- `products/audit-service/src/audit_service/services/audit_store.py` — `StoreError`.
- `products/identity-broker/src/identity_service/services/exchange_service.py` — `ExchangeError`.
- `products/incident-service/src/incident_service/core/config.py` — `SettingsError`.
- `products/incident-service/src/incident_service/services/connectors.py` — `ConnectorConfigError`.
- `products/incident-service/src/incident_service/services/query_auth.py` — `QueryAuthError`.
- `products/incident-service/src/incident_service/services/triage.py` — `TriageError`.
- `products/skills-hub/src/skills_hub/core/config.py` — `SettingsError`.
- `products/skills-hub/src/skills_hub/services/query_auth.py` — `QueryAuthError`.
- `products/skills-hub/src/skills_hub/services/skill_store.py` — `StoreError`.
- `products/execution-runtime/src/execution_runtime/services/execution_protocol.py` — `ProtocolError(ValueError)`.
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError(ValueError)` used by every LLM provider.
- `products/agent-platform/src/agent_service/runtime_kernel.py` — `UnknownModelError(ValueError)`.
- `products/agent-platform/src/agent_service/services/execution_worker_client.py` — `WorkerHandoffError(Exception)`.
- `products/agent-platform/src/agent_service/services/shift_summary.py` — `DigestInputError` / `UnknownSessionError`.
- `products/agent-platform/src/agent_service/services/execution_protocol.py` — `ProtocolError(ValueError)`.

## Architecture and conventions

1. **Per-service exception hierarchy.** A base class (e.g. `SkillsClientError`, `IncidentClientError`, `ExchangeError`, `StoreError`, `QueryAuthError`) sits next to the concrete variants. This lets callers catch the broad category while still distinguishing configured vs. unavailable vs. rejected.

2. **Structured transport-layer classification.** For outbound calls (skills-hub, incident-service), the client raises one of three categories:
   - *dependency not configured* → 503 (`SkillsDependencyNotConfigured`, `IncidentDependencyNotConfigured`)
   - *transport failure or upstream 5xx* → 502 (`SkillsServiceUnavailable`, `IncidentServiceUnavailable`)
   - *upstream 4xx* → passthrough with original status code (`SkillsClientRejected`, carrying `status_code` and `message` attributes).

   See `skills_client.py` lines 90–110 and the mapping in `routes.py` `_validate_skill_markdown` (lines 1073–1080).

3. **Route-level mapping, not middleware.** Neither `agent_service/app.py` nor `platform_gateway/app.py` registers an `exception_handler`. Errors surface as `fastapi.HTTPException` raised directly from route handlers (see `agent_service/api/v2/routes.py` throughout, e.g. lines 148, 193, 235, 262, 399, 418, 427, 437, 514, 966, 1002, 1016, 1022, 1044, 1076–1080, 1102, 1209, 1236, 1245–1251). The HTTP middleware only logs request/response metadata; it does not transform errors.

4. **Domain errors stay as plain exceptions.** Validation/configuration errors in non-HTTP layers raise `ValueError` subclasses (`ProviderConfigurationError`, `UnknownModelError`, `ProtocolError`) or bare `Exception` subclasses (`WorkerHandoffError`, `DigestInputError`, `UnknownSessionError`). They are caught closer to the boundary where they can be mapped to HTTP.

5. **Policy bundle loading errors use a dedicated sentinel.** `PolicyLoadError` wraps YAML/schema violations during policy bundle parsing (`policy_engine.py` `_parse_approval`, `_parse_rules`); it is distinct from runtime authorization decisions.

6. **No panics/recover.** Python has no panic/recover; the codebase uses structured exceptions consistently. No `try/except ... finally` blocks perform recovery outside of test infrastructure (`products/execution-runtime/tests/failure/support/infrastructure.py` defines `PrerequisiteError(RuntimeError)`, `products/skills-hub/tests/support/postgres_infra.py` mirrors it).

7. **Sample app shows the alternative path exists but is not used by platform services.** `samples/acme-admin/app/src/acme_admin/main.py` registers `@app.exception_handler(AdminAuthRequired)`, demonstrating FastAPI's built-in mechanism, but none of the nine production services register custom exception handlers.

## Conventions and constraints observed

- Outbound dependency errors follow a fixed triad: *not configured* → 503, *unreachable/upstream 5xx* → 502, *upstream 4xx* → passthrough. This is documented in the docstring of `skills_client.py` (lines 11–15) and enforced by the caller in `routes.py` `_validate_skill_markdown`.
- An unvalidated skill draft is never returned to the operator; generation failures degrade to a facts-only skeleton, and a second validation failure returns 502 (`routes.py` `_validated_draft_sequence`, lines 1155–1213).
- `from None` is used on re-raised `HTTPException`s when the original traceback should not leak (e.g. `routes.py` lines 966, 1076–1080, 1245–1249).
- Settings validation across services raises `ValueError` (or a subclass like `SettingsError`) with a human-readable message describing the offending env var and allowed values (`runtime_settings.py`, `incident_service/core/config.py`, `skills_hub/core/config.py`).
- Provider configuration errors are uniformly `ProviderConfigurationError(ValueError)` raised from every LLM provider implementation (`providers/luban.py`, `openai.py`, `dashscope.py`, `deepseek.py`, `registry.py`).
- Test fixtures reuse a `PrerequisiteError(RuntimeError)` helper to signal missing external dependencies in integration tests.