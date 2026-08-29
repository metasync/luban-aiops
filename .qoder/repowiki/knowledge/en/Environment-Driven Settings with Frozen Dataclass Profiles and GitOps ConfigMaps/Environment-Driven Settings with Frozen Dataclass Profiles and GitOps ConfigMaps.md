---
kind: configuration_system
name: Environment-Driven Settings with Frozen Dataclass Profiles and GitOps ConfigMaps
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-secrets.example.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
---

# Configuration System

## What system/approach is used

Every service in the monorepo uses a uniform, environment-driven configuration pattern built on Python `dataclasses`:

1. A frozen `@dataclass` defines all settings for a service (e.g. `PlatformGatewaySettings`, `AuditSettings`, `IdentitySettings`, `GatewaySettings`, `RuntimeSettings`).
2. Each dataclass exposes a classmethod `from_env()` that reads values from `os.getenv(...)` with typed coercion (`int`, `float`, boolean parsing via `{"1","true","yes","on"}`) and sensible defaults.
3. A module-level `@lru_cache(maxsize=1)` function `get_settings()` returns a singleton instance of the settings object, so the process loads config once at startup.
4. The agent-platform adds an extra layer: `runtime_settings.py` defines nested provider-specific option dataclasses (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) selected by `AGENTSCOPE_PROVIDER`, validated in `__post_init__` to ensure `profile == provider` and that `provider_options` matches the expected type.

There is no YAML/JSON config file loader inside the services — configuration is purely env-var driven at runtime. Policy files are loaded as separate mounted files (see `policy_path`), but they are not part of the core settings mechanism.

## Key files and packages

- `products/*/src/<service>/core/config.py` — per-service frozen settings dataclass + `from_env()` + cached `get_settings()`.
- `products/agent-platform/src/agent_service/runtime_settings.py` — richer settings with provider options, validation, and choice helpers (`_optional_str/int/float/bool/choice`).
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — non-secret env vars per service.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-secrets.example.env` — secret templates (never committed; real values injected or synced).
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared env (OTEL, common `IDENTITY_SERVICE_URL`) applied to every pod.
- `shared/platform-ops/gitops/runtime-profiles/<provider>/configmap.yaml` — profile ConfigMaps that set `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL` to switch LLM backends without code changes.
- `shared/platform-ops/gitops/runtime-profiles/<provider>/runtime-secrets.example.env` — per-provider secret templates (e.g. `AGENTSCOPE_API_KEY`).

## Architecture and conventions

### Per-service settings objects
Each service owns its own settings dataclass with a consistent shape:

| Service | Settings class | Notable fields |
|---|---|---|
| platform-gateway | `PlatformGatewaySettings` | downstream URLs (`AGENT_SERVICE_URL`, `IDENTITY_SERVICE_URL`), JWKS cache TTL, token issuer/audience, policy path, audit client |
| tool-gateway | `GatewaySettings` | identity/JWKS, K8s connector flags, Elastic connector flags, redaction settings, audit client |
| audit-service | `AuditSettings` | store backend (`memory`/`postgres`), DB URL, retention/eviction tuning, ingest/workload client registries parsed from comma-separated env strings |
| identity-broker | `IdentitySettings` | Keycloak/OIDC endpoints, JWT TTLs, service clients registry, workload subject mapping, audit client |
| agent-platform | `RuntimeSettings` | provider selection (`dashscope`/`deepseek`/`openai`), model name, base URL, Redis session store, tool gateway URL |

### Boolean parsing convention
Booleans are parsed uniformly as case-insensitive membership in `{"1", "true", "yes", "on"}`. The agent-platform helper `_optional_bool` additionally rejects unknown values by raising `ValueError`; other services accept any string and coerce via `in {...}`.

### Composite/env-string parsing
Complex multi-value settings use custom parsers over comma-separated env strings:
- `AUDIT_INGEST_CLIENTS`: `client_id=secret,client_id=secret`
- `AUDIT_WORKLOAD_CLIENTS`: `subject=client_id,subject=client_id`
- `IDENTITY_SERVICE_CLIENTS`: `client_id:secret:aud1|aud2`
- `IDENTITY_WORKLOAD_CLIENTS`: `subject=client_id:aud1|aud2`

These allow registering multiple clients without a dedicated config file.

### Secrets vs. non-secrets separation
The GitOps layout enforces a strict split:
- `runtime-config.env` — safe to commit; holds URLs, feature toggles, policy paths, audiences.
- `runtime-secrets.example.env` — template only; never committed. Real secrets are either copied into `runtime-secrets.env` locally or generated/synced by scripts like `sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-runtime-secret.sh`.
- `base/shared/runtime.env` — shared across all pods (OTEL endpoint, shared `IDENTITY_SERVICE_URL`).

### Runtime profiles
The agent-platform supports pluggable LLM providers through `runtime-profiles/`. Each profile is a pair of a `configmap.yaml` (non-secret settings) and a `runtime-secrets.example.env` (API keys). Switching providers is done by selecting a different profile overlay during deployment rather than editing service code.

### Cross-service credential contracts
Configuration is cross-referenced between services via documented contracts in the `.env` files:
- `PLATFORM_GATEWAY_AUDIT_CLIENT_SECRET` must match the secret registered under `platform-gateway` in `AUDIT_INGEST_CLIENTS` (audit-service).
- `IDENTITY_SERVICE_CLIENTS` must contain matching entries for each service's `*_SERVICE_CLIENT_SECRET`.
- `GATEWAY_AUDIT_CLIENT_SECRET` must match the entry registered for `tool-gateway` in `AUDIT_INGEST_CLIENTS`.

## Conventions and constraints

**Observed conventions:**
- Every service exposes `core.config.get_settings()` as the single entry point to read configuration.
- Settings dataclasses are `frozen=True`, making them immutable after construction.
- Defaults are declared as dataclass field defaults and/or passed to `os.getenv(key, default)`.
- Provider-specific options are validated at construction time (`__post_init__` raises `ValueError` if `profile != provider` or if `provider_options` type mismatches).
- Supported providers are enumerated in `SUPPORTED_RUNTIME_PROVIDERS = ("dashscope", "deepseek", "openai")` and enforced when parsing `AGENTSCOPE_PROVIDER`.
- Feature toggles like `require_auth`, `k8s_enabled`, `elastic_enabled`, `redaction_enabled` follow the same boolean env-parsing convention.
- Audit emission is configured per service via `*_AUDIT_SERVICE_URL` / `*_AUDIT_CLIENT_ID` / `*_AUDIT_CLIENT_SECRET` triplets.

**Enforced rules (by code):**
- `AGENTSCOPE_PROVIDER` must be one of `dashscope`, `deepseek`, `openai`; otherwise `from_env()` raises `ValueError`.
- If both `AGENTSCOPE_PROFILE` and `AGENTSCOPE_PROVIDER` are set, they must match; otherwise `__post_init__` raises `ValueError`.
- `provider_options` must be an instance of the dataclass returned by `provider_options_type(provider)`; type mismatch raises `ValueError`.
- Unknown boolean values in `_optional_bool` raise `ValueError` with the offending variable name.
- `AGENTSCOPE_REDIS_*` variables are required for the Redis session store backend chosen via `SESSION_STORE_BACKEND=redis`.

**Deployment-time constraints:**
- Secrets are delivered via Kubernetes `Secret` objects referenced by deployments; example `.env` files document the contract but are not deployed.
- Shared runtime env is mounted as a single ConfigMap consumed by every pod.
- Profile switching is done by swapping the `agent-platform-runtime-profile` ConfigMap via Kustomize overlays under `runtime-profiles/`.