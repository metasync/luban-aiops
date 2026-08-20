---
kind: configuration_system
name: Environment-Driven Frozen Settings with Per-Service Dataclass Config
category: configuration_system
scope:
    - '**'
source_files:
    - products/incident-service/src/incident_service/core/config.py
    - products/incident-service/src/incident_service/core/runtime.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/runtime.py
    - products/audit-service/src/audit_service/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - shared/platform-ops/gitops/dev-k8s/base/incident-service/runtime-config.env
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/deepseek/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
---

## What system/approach is used

Every service in this repository (incident-service, platform-gateway, audit-service, identity-broker, skills-hub, tool-gateway, agent-platform) implements configuration as **frozen Python dataclasses** loaded exclusively from **environment variables** at startup. There is no YAML/JSON config file parsing inside services; configuration is a single-phase load that happens before the app starts serving requests. The pattern is:

1. A `core/config.py` (or `runtime_settings.py`) defines one or more `@dataclass(frozen=True)` settings classes.
2. Each class exposes a `classmethod from_env(cls)` that reads values via `os.getenv(...)` with typed defaults and optional validators.
3. A module-level `@lru_cache(maxsize=1)` function `get_settings()` returns a singleton instance so callers can import it without re-parsing.
4. Runtime bootstrap (`main.py` / `app.py`) calls `get_settings()` early and passes the frozen object into dependency injection.

The agent-platform runtime additionally uses a richer `RuntimeSettings` model in `agent_service/runtime_settings.py` with helper parsers (`_optional_str`, `_optional_int`, `_optional_bool`, `_optional_choice`) and `__post_init__` validation that raises `ValueError` on misconfiguration — enforcing bounds such as `AGENTSCOPE_MAX_ITERS >= 1`, `0 < AGENTSCOPE_CONTEXT_TRIGGER_RATIO < 0.9`, valid IANA timezones, and matching `AGENTSCOPE_PROFILE`/`AGENTSCOPE_PROVIDER` pairs.

## Key files and packages

- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` (webhook token, query/workload clients, store backend, connectors, triage timeout, audit client).
- `products/incident-service/src/incident_service/core/runtime.py` — `IncidentRunSettings` (host/port for uvicorn).
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` (service URLs, JWKS cache, policy path, auth flags, downstream client credentials).
- `products/platform-gateway/src/platform_gateway/core/runtime.py` — `GatewayRunSettings`.
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` (store backend, retention, eviction, ingest/workload clients).
- `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings` (Keycloak/OIDC, JWT TTLs, service/workload client registries).
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` (sources JSON, git tokens, query/workload clients).
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` (identity, K8s/Elastic/redaction toggles, downstream service credentials).
- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` (provider selection, model knobs, kernel tuning, middleware flags).
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service env var manifests mounted into pods.
- `shared/platform-ops/gitops/runtime-profiles/{dashscope,deepseek,openai}/configmap.yaml` — shared runtime profile overrides for `AGENTSCOPE_*` vars.

## Architecture and conventions

### One setting class per service
Each service owns exactly one top-level settings dataclass (e.g. `IncidentSettings`, `PlatformGatewaySettings`, `AuditSettings`). Nested sub-settings are represented as nested frozen dataclasses (e.g. `QueryClient`, `WorkloadClient`, `DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`, `SourceSpec`).

### Environment variable naming convention
Variables are scoped by service prefix: `INCIDENT_*`, `PLATFORM_GATEWAY_*`, `AUDIT_*`, `GATEWAY_*`, `IDENTITY_*`, `SKILLS_*`, `AGENTSCOPE_*`. This avoids collisions between services while keeping related knobs grouped under a common namespace. Service-specific prefixes are used for cross-cutting concerns too (e.g. `PLATFORM_GATEWAY_AUDIT_SERVICE_URL` vs `AUDIT_*`).

### Parsing helpers for complex types
Multi-value settings use compact string encodings parsed in-process:
- Comma-separated key=value lists: `INCIDENT_QUERY_CLIENTS`, `INCIDENT_WORKLOAD_CLIENTS`, `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `SKILLS_WORKLOAD_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`, `IDENTITY_WORKLOAD_CLIENTS`.
- JSON blobs for structured data: `SKILLS_SOURCES` (list of source specs), `SKILLS_GIT_TOKENS` (source_id → token map).
- Boolean normalization accepts `"1"|"true"|"yes"|"on"` (case-insensitive) and falls through to `False` otherwise.
- Port resolution tolerates Kubernetes service-link values like `tcp://IP:PORT` by falling back to the default integer.

### Validation strategy
Validation happens during `from_env` / `__post_init__` and fails fast with descriptive exceptions:
- `SettingsError` (custom exception in incident-service and skills-hub) for malformed multi-value configs.
- `ValueError` raised from `RuntimeSettings.__post_init__` for out-of-range numeric fields, invalid timezone strings, mismatched provider/profile pairs, and non-positive token budgets.
- Unknown enum choices raise `ValueError` via `_optional_choice` (e.g. `AGENTSCOPE_PROVIDER` must be one of `dashscope|deepseek|openai`; `DEEPSEEK_REASONING_EFFORT` must be `high|max`; `OPENAI_REASONING_EFFORT` must be one of its six values).

### Secrets vs config separation
Secrets (API keys, client secrets, database URLs) are passed via environment variables but are not embedded in code — they are supplied through `runtime-secrets.example.env` files under `shared/platform-ops/gitops/dev-k8s/base/<service>/` and referenced by deployment manifests. Non-secret runtime knobs live in `runtime-config.env` or in `runtime-profiles/*/configmap.yaml` (for shared `AGENTSCOPE_*` profiles).

### Caching
All settings modules expose a `@lru_cache(maxsize=1)` `get_settings()` accessor so the same frozen instance is reused across the process lifetime. This makes settings effectively immutable after boot.

### Defaults
Defaults are baked into dataclass field defaults and/or constants at the top of each config module (e.g. `DEFAULT_AGENT_SERVICE_URL = "http://agent-service:8000"`, `DEFAULT_HTTP_HOST`, `DEFAULT_HTTP_PORT`). Services ship with sensible defaults so they can run locally without any env vars set.

## Conventions and constraints

- **Configuration is read-only after boot**: all settings classes are `frozen=True`; there is no runtime mutation API.
- **No config file loading inside services**: every value comes from `os.getenv`; YAML/JSON files are only used in GitOps overlays to populate environment variables, never parsed by the application code.
- **Per-service env var prefixes are mandatory**: adding a new service requires choosing a unique prefix and following the existing `core/config.py` + `core/runtime.py` layout.
- **Boolean env vars accept only the canonical truthy set** `{"1", "true", "yes", "on"}`; anything else is treated as false.
- **Complex multi-value settings use comma-separated `key=value` pairs** (with `=` partitioning) rather than JSON, except where the structure is rich enough to warrant JSON (`SKILLS_SOURCES`, `SKILLS_GIT_TOKENS`).
- **Startup-time validation is required**: misconfigured values must raise an exception during `from_env` / `__post_init__` so the pod fails fast instead of running with invalid state.
- **Cross-service credential registries share a vocabulary**: `QueryClient`, `IngestClient`, `ServiceClient`, and `WorkloadClient` appear across multiple services with consistent semantics (client_id/secret pairs, subject→client_id mappings, optional allowed audiences).
- **Agent runtime settings are centralized**: the agent-platform's `RuntimeSettings` is consumed by the agent-service via `agent_service.core.config.get_settings()`, and shared runtime profiles in `shared/platform-ops/gitops/runtime-profiles/` override `AGENTSCOPE_*` vars uniformly across deployments.