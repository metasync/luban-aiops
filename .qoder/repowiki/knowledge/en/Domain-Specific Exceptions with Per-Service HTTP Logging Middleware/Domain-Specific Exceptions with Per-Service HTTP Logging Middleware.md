---
kind: error_handling
name: Domain-Specific Exceptions with Per-Service HTTP Logging Middleware
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
---

## Overview

The Luban AIOps platform uses a **domain-specific exception hierarchy** per microservice, with no shared base error package. Each service defines its own small set of typed exceptions (e.g. `PolicyLoadError`, `TokenVerificationError`, `ExchangeError`, `StoreError`, `SettingsError`, `UnknownModelError`, `ProviderConfigurationError`) that carry enough context to be logged and mapped downstream. There is **no global FastAPI exception handler** (`@app.exception_handler` was not found in any service); instead, each service mounts a uniform `http_request` logging middleware that records the final `response.status_code` after the request completes, so errors are observed through structured logs rather than centralized response shaping.

## Exception types by service

| Service | Custom exceptions | Purpose |
|---|---|---|
| `agent-platform` | `UnknownModelError(ValueError)`, `ProviderConfigurationError(ValueError)` | Kernel model selection fail-closed; provider config validation |
| `agent-platform` services | `WorkerHandoffError`, `IncidentClientError`, `SkillsClientError`, `DigestInputError`, `UnknownSessionError` | Inter-service call failures |
| `platform-gateway` | `PolicyLoadError(Exception)`, `TokenVerificationError(Exception)` | Policy bundle parse/validation; JWT verification failures |
| `tool-gateway` | `PolicyLoadError(Exception)`, `TokenVerificationError(Exception)` | Same policy engine / token verifier contract as platform-gateway |
| `incident-service` | `SettingsError(Exception)`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError` | Config, connector, store, normalization, auth, triage failures |
| `skills-hub` | `SettingsError(Exception)`, `StoreError`, `QueryAuthError` | Config, skill store, query auth failures |
| `audit-service` | `StoreError(Exception)`, `IngestAuthError(Exception)` | Audit persistence, ingestion auth failures |
| `identity-broker` | `ExchangeError(Exception)` with `status_code` attribute | Token exchange / delegation failures, carrying the intended HTTP status (401/400) |

## Conventions

1. **Fail-fast configuration validation.** Services validate environment variables at startup via `from_env()` on frozen dataclasses and raise a dedicated `SettingsError` (or `ProviderConfigurationError`) when values are malformed. This prevents partially-initialized processes from serving requests.
2. **Domain exceptions wrap lower-level errors using `raise ... from exc`.** For example, `_parse_rules` wraps YAML/JSON parsing errors into `PolicyLoadError` with `from exc`, preserving the original traceback while presenting a stable domain boundary.
3. **Authentication/token errors carry an explicit HTTP status code.** `ExchangeError.__init__` stores `status_code` alongside `detail`; callers map it to the HTTP response. `TokenVerificationError` carries only a `detail` string, leaving mapping to the caller.
4. **Best-effort side effects degrade gracefully.** Store writes during confirmation resolution are wrapped in `try/except Exception` blocks that log a warning and continue — a failure to persist a confirmation record never aborts the decision flow.
5. **No panics or `sys.exit` in request paths.** The codebase avoids `panic`/`os._exit`; unhandled exceptions propagate to the ASGI server, which returns a 500. Errors are surfaced via structured logs emitted by the per-request middleware.
6. **Cross-service clients raise their own typed exceptions** (`IncidentClientError`, `SkillsClientError`, `WorkerHandoffError`) so callers can distinguish network/store failures from business logic errors.

## Architecture & conventions

- **Per-service app factories** (`create_app()`) install an `http` middleware that wraps every request, resolves `x-request-id`, measures duration, and emits a `log_event("http_request", ..., status_code=...)` entry. This is the single place where response status codes are observed uniformly across all eight services.
- **No centralized error-to-HTTP mapper exists.** Routes handle exceptions locally (e.g. catching kernel/streaming exceptions and returning appropriate responses), or rely on FastAPI's default behavior for unhandled exceptions. The identity broker is the clearest example: `ExchangeError` carries the target HTTP status, and the route layer maps it directly.
- **Policy engines in both gateways share the same exception shape** (`PolicyLoadError`, `ApprovalSpec`, `PolicyRule`, `PolicyDecision`), indicating a deliberate cross-service convention even though the modules are duplicated rather than shared.
- **Store backends expose a `Protocol` (`AuditStore`) and a domain `StoreError`**, allowing in-memory and PostgreSQL implementations to swap without changing callers' error handling.

## Key files

- `products/agent-platform/src/agent_service/runtime_kernel.py` — `UnknownModelError`, kernel error tracking (`remember_error`/`clear_error`)
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError`
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError`, policy rule validation
- `products/tool-gateway/src/tool_gateway/services/policy_engine.py` — duplicate policy engine with same exception shape
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError`
- `products/identity-broker/src/identity_service/services/exchange_service.py` — `ExchangeError(detail, status_code)`
- `products/incident-service/src/incident_service/core/config.py` — `SettingsError`
- `products/skills-hub/src/skills_hub/core/config.py` — `SettingsError`
- `products/audit-service/src/audit_service/services/audit_store.py` — `StoreError`, cursor decode wrapper
- `products/*/src/*/app.py` — uniform `http_request` logging middleware recording `status_code`

## Constraints enforced by the code

- Provider configuration must include `AGENTSCOPE_API_KEY`; missing keys raise `ProviderConfigurationError` at adapter `validate()` time.
- Policy bundles must be valid YAML with a `rules` list; malformed rules raise `PolicyLoadError` with the offending rule index/source.
- `require_approval` rules may only reference bridged actions; non-bridged actions are skipped with a warning (tool-gateway) or rejected (platform-gateway).
- `tier_2` approval cannot allow self-approval; attempting this raises `PolicyLoadError`.
- Settings parsers reject unknown source types, duplicate `source_id`s, and invalid JSON, raising `SettingsError` before the service starts.