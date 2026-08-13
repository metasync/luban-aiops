---
kind: configuration_system
name: Per-Service Frozen Dataclass Settings Loaded from Environment Variables with Kustomize Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/core/env.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.env
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
---

# Configuration System

## What system/approach is used

Each Python service in the platform implements its own configuration layer using **Python `dataclasses` decorated as frozen immutable settings objects** plus a module-level `@lru_cache(maxsize=1)` `get_settings()` accessor. Configuration is loaded exclusively from **environment variables** at process startup; there are no `.yaml`/`.toml` config files read by the application code. Secrets and non-secret runtime values are split into separate `runtime-config.env` and `runtime-secrets.env` files per service, mounted into Kubernetes pods via Kustomize overlays. Provider-specific runtime profiles (e.g. DashScope vs OpenAI) are supplied as a dedicated `ConfigMap` named `agent-platform-runtime-profile` that injects `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`.

## Key files and packages

- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass with nested `DashScopeOptions` / `DeepSeekOptions` / `OpenAIOptions`; validates provider/profile consistency in `__post_init__` and enforces allowed providers via `_optional_choice`.
- `products/agent-platform/src/agent_service/core/config.py` — thin `get_settings()` cache returning `RuntimeSettings.from_env()`.
- `products/agent-platform/src/agent_service/core/env.py` — shared helpers `get_env_value(*names, default)` and `get_env_int` for fallback env lookup.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` dataclass with defaults like `DEFAULT_AGENT_SERVICE_URL`, `DEFAULT_IDENTITY_JWKS_URL`, parsed from `IDENTITY_*`, `PLATFORM_GATEWAY_*`, `CHAT_RESPONSE_TIMEOUT_SECONDS` env vars.
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` dataclass covering identity, policy, K8s connector (`GATEWAY_K8S_ENABLED`, `GATEWAY_K8S_NAMESPACE`), redaction, and Elastic (`GATEWAY_ELASTIC_*`) toggles.
- `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings` plus nested `ServiceClient` / `WorkloadClient` dataclasses; parses comma-separated lists via `_parse_service_clients` and `_parse_workload_clients` from `IDENTITY_SERVICE_CLIENTS` and `IDENTITY_WORKLOAD_CLIENTS`.
- `shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env` — non-secret env vars mounted per service.
- `shared/platform-ops/gitops/dev-k8s/base/*/runtime-secrets.env` — secrets (client secrets, keys) mounted separately.
- `shared/platform-ops/gitops/runtime-profiles/<provider>/configmap.yaml` — profile ConfigMaps that set `AGENTSCOPE_PROFILE` + provider-specific model/base URL.

## Architecture and conventions

### Per-service frozen dataclass settings
Every service defines a single frozen `@dataclass` under `src/<service>/core/config.py` (or `runtime_settings.py` for agent-platform). Each setting has a sensible default constant at the top of the file and is populated in a classmethod `from_env()` that reads one or more environment variables via `os.getenv`. The frozen design means settings cannot be mutated after construction, enforcing immutability across the request lifecycle.

### Single-process caching
A module-level `@lru_cache(maxsize=1)` wraps each `get_settings()` function so the settings object is constructed exactly once per process lifetime. Consumers import `from .config import get_settings` rather than re-parsing env on every call.

### Boolean parsing convention
Boolean env vars are normalized via `.strip().lower() in {"1", "true", "yes", "on"}` consistently across services (see `require_auth`, `k8s_enabled`, `redaction_enabled`, `elastic_verify_tls`). The agent-platform helper `_optional_bool` raises `ValueError` for unrecognized boolean strings, providing stricter validation.

### Choice/validation helpers
The agent-platform uses typed `_optional_str` / `_optional_int` / `_optional_float` / `_optional_bool` / `_optional_choice(name, supported_set)` helpers. `_optional_choice` rejects unsupported values with an error listing the allowed set (used to validate `AGENTSCOPE_PROVIDER` against `SUPPORTED_RUNTIME_PROVIDERS = ("dashscope", "deepseek", "openai")` and `AGENTSCOPE_PROFILE`).

### Nested provider options
`RuntimeSettings._provider_options_from_env(provider)` dispatches to provider-specific option builders (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) based on `AGENTSCOPE_PROVIDER`. A `__post_init__` cross-field validator ensures `profile` matches `provider` and that `provider_options` type matches the selected provider, raising `ValueError` otherwise.

### Secret vs non-secret separation
Kustomize deploys two env sources per service:
- `runtime-config.env` — non-sensitive configuration (URLs, feature flags, timeouts).
- `runtime-secrets.env` — sensitive values (client secrets, signing keys, API keys).
This separation is reflected in the deployment manifests and documented by the presence of `runtime-secrets.example.env` templates.

### Profile-based runtime configuration
The agent-platform supports pluggable LLM backends through the `AGENTSCOPE_PROFILE` mechanism. Each profile lives under `shared/platform-ops/gitops/runtime-profiles/<name>/configmap.yaml` and sets `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`. The selection script `select-runtime-profile.sh` swaps the ConfigMap applied to the agent-platform deployment.

### Comma-delimited list configuration
Complex settings are encoded as delimited strings and parsed at load time:
- `IDENTITY_SERVICE_CLIENTS=<id>:<secret>:<aud1|aud2>,...` → tuple of `ServiceClient`.
- `IDENTITY_WORKLOAD_CLIENTS=<subject>=<client_id>:<aud1|aud2>,...` → tuple of `WorkloadClient`.
The parsers tolerate empty entries and missing fields, producing tuples of registered clients.

### Default service discovery
Default hostnames (`agent-service`, `identity-service`) and ports (`8000`) are embedded as module constants and combined into default URLs (`DEFAULT_AGENT_SERVICE_URL`, `DEFAULT_IDENTITY_JWKS_URL`). These can be overridden via `AGENT_SERVICE_URL`, `IDENTITY_SERVICE_URL`, `IDENTITY_JWKS_URL` env vars, enabling same-cluster DNS resolution without explicit configuration.

## Conventions and constraints

- **Environment-only loading**: Application code never reads files directly for configuration; all values come from `os.getenv`. File-based configuration exists only at deploy time (Kustomize env files and ConfigMaps).
- **Immutable settings**: All settings dataclasses are `frozen=True`; mutation after construction is prohibited.
- **Single-source-of-truth accessor**: Consumers must use `get_settings()` from `core.config` (or `runtime_settings.RuntimeSettings.from_env()` for agent-platform) to benefit from the `lru_cache` singleton.
- **Boolean normalization**: Booleans accept `1`, `true`, `yes`, `on` (case-insensitive); other values are treated as false unless the stricter `_optional_bool` is used, which raises on unknown values.
- **Provider allow-listing**: `AGENTSCOPE_PROVIDER` must be one of `dashscope`, `deepseek`, `openai`; invalid values raise `ValueError` during settings construction.
- **Profile/provider coupling**: When both `AGENTSCOPE_PROFILE` and `AGENTSCOPE_PROVIDER` are set, they must match; mismatch raises `ValueError` in `RuntimeSettings.__post_init__`.
- **Secrets isolation**: Sensitive values are kept in `runtime-secrets.env` and mounted separately from `runtime-config.env`; this is enforced by the Kustomize overlay structure, not by code.
- **Policy path via env**: Policy enforcement is enabled by setting `PLATFORM_GATEWAY_POLICY_PATH` or `GATEWAY_POLICY_PATH` to a file path; when empty, the respective gateways fall back to built-in defaults.
- **No YAML/TOML config in app code**: There is no application-level YAML or TOML loader; configuration is purely env-driven.