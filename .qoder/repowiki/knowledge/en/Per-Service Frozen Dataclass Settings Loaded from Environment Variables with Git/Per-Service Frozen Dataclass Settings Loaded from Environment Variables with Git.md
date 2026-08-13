---
kind: configuration_system
name: Per-Service Frozen Dataclass Settings Loaded from Environment Variables with GitOps ConfigMaps
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
---

## Overview

Each Python service in the Agent Platform (agent-platform, platform-gateway, tool-gateway, identity-broker) implements its own self-contained configuration system. There is no shared settings library — every product defines a `core/config.py` that exposes a module-level `get_settings()` accessor backed by an `@lru_cache(maxsize=1)` singleton, and a frozen dataclass with a `from_env()` classmethod that reads values exclusively from `os.environ`. Configuration is injected at runtime via Kubernetes environment variables supplied through per-service `runtime-config.env` files and shared `shared/runtime.env`, plus optional profile-specific ConfigMaps.

## Core Pattern (per service)

1. **Frozen dataclass** holding all runtime knobs with sensible defaults declared as class attributes.
2. **`from_env()` classmethod** mapping each env var to a typed field using `os.getenv(key, default)`, with boolean parsing done via `.strip().lower() in {"1","true","yes","on"}` and numeric casts via `int(...)` / `float(...)`.
3. **Module-level `get_settings()`** wrapped in `functools.lru_cache(maxsize=1)` so callers import `from agent_service.core.config import get_settings` and receive a cached instance.
4. **Dependency injection**: FastAPI routes declare `settings: Settings = Depends(get_settings)` (identity-broker) or call `get_settings()` directly (agent-platform).

### Service-specific settings modules

| Service | Settings class | Key env vars (prefix) | Notable behavior |
|---|---|---|---|
| agent-platform | `RuntimeSettings` (`runtime_settings.py`) | `AGENTSCOPE_*`, `SESSION_*`, `TOOL_GATEWAY_URL` | Validates `AGENTSCOPE_PROFILE` against `SUPPORTED_RUNTIME_PROFILES`; enforces `profile == provider` in `__post_init__`; provider-specific options parsed from `DASHSCOPE_*`/`DEEPSEEK_*`/`OPENAI_*` env vars; raises `ValueError` on unknown provider. |
| platform-gateway | `PlatformGatewaySettings` | `IDENTITY_*`, `PLATFORM_GATEWAY_*`, `CHAT_RESPONSE_TIMEOUT_SECONDS`, `AGENT_SERVICE_URL` | Defaults point to in-cluster DNS names (`agent-service:8000`, `identity-service:8000`). |
| tool-gateway | `GatewaySettings` | `GATEWAY_*`, `IDENTITY_*` | Boolean flags for `k8s_enabled`, `redaction_enabled`, `elastic_enabled`, `elastic_verify_tls`. |
| identity-broker | `IdentitySettings` (+ nested `ServiceClient`, `WorkloadClient`) | `KEYCLOAK_*`, `OIDC_*`, `IDENTITY_*` | Complex multi-value env vars parsed by custom helpers: `IDENTITY_SERVICE_CLIENTS` (`client_id:secret:aud1|aud2`) and `IDENTITY_WORKLOAD_CLIENTS` (`subject=client_id:aud1|aud2`). |

## Loading & Layering Order

Configuration is loaded once at process start (e.g. `main.py` calls `get_settings()` during startup). The effective value of any setting follows this precedence:

1. **Process environment variable** — highest priority, set by Kubernetes `env:` entries.
2. **Hardcoded default** in the dataclass attribute.
3. **No fallback** — if a required secret/env is missing and has no default, the service starts with an empty string or disabled feature (e.g. `service_client_secret=""`).

There is no support for loading from YAML/JSON files at runtime; file paths like `policy_path` are passed as env vars and read later by the policy engine.

## GitOps / Deployment Integration

Environment variables are provisioned declaratively under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` (and `runtime-secrets.env` for secrets). A shared `shared/runtime.env` provides cross-cutting keys such as `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and `IDENTITY_SERVICE_URL` consumed by both gateways.

Agent-platform additionally supports **runtime profiles** via a dedicated ConfigMap (`agent-platform-runtime-profile`) mounted into the pod; the profile sets `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL` (see `shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml`). The agent-platform code validates the chosen profile against `SUPPORTED_RUNTIME_PROFILES`.

Secrets follow a convention: sensitive values live in `runtime-secrets.env` (or Kubernetes Secrets referenced by deployments), while non-sensitive tuning lives in `runtime-config.env`. Example secret contract is documented in `runtime-secrets.example.env` for the identity broker, which describes how `IDENTITY_SERVICE_CLIENTS` must match the client secret configured in the gateway's `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET`.

## Conventions & Constraints Observed

- **All settings classes are `@dataclass(frozen=True)`**, making them immutable after construction.
- **Boolean env vars** are normalized via `.strip().lower() in {"1","true","yes","on"}`; unrecognized values raise `ValueError` only for the agent-platform `_optional_bool` helper.
- **Provider selection** is validated at load time: `AGENTSCOPE_PROVIDER` must be one of `dashscope`, `deepseek`, `openai`; `AGENTSCOPE_PROFILE` (if set) must equal `provider`.
- **Complex multi-value env vars** use a compact delimiter format rather than JSON/YAML: comma-separated lists with colon/pipe delimiters, parsed by small private helpers (`_parse_service_clients`, `_parse_workload_clients`).
- **No config validation framework** (pydantic, attrs validators, etc.) is used beyond explicit `raise ValueError` blocks in `__post_init__` and choice helpers.
- **Settings are singletons per process** via `lru_cache(maxsize=1)`; tests can bypass caching by importing the settings class directly or mocking `get_settings`.
- **No hot-reload**: changing env vars requires restarting the process; there is no watcher or re-parse path.
- **Separation of concerns**: `core/config.py` only loads env → settings; business logic never calls `os.getenv` directly but goes through `get_settings()`.

## Key Files

- `products/agent-platform/src/agent_service/core/config.py` — `get_settings()` entrypoint
- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` + provider option parsers
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings`
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings`
- `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings` + client/workload parsers
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared OTel & identity broker endpoint
- `shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env` — per-service non-secret env
- `shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env` — secret contract doc
- `shared/platform-ops/gitops/runtime-profiles/*/configmap.yaml` — agent-platform runtime profiles
