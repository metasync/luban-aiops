---
kind: configuration_system
name: Environment-Driven Settings with Frozen Dataclass Profiles and GitOps ConfigMaps
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/env.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - docs/guides/configuration-reference.md
---

## What system/approach is used

The platform uses a uniform, environment-variable-driven configuration system across every Python service. Each service defines a frozen `dataclass` settings object (e.g. `RuntimeSettings`, `PlatformGatewaySettings`, `GatewaySettings`) with a `from_env()` classmethod that reads values from `os.getenv(...)` against well-known uppercase variable names, then exposes the instance via an `@lru_cache(maxsize=1)`-decorated `get_settings()` accessor. There are no YAML/JSON/TOML config files consumed at runtime by the services; configuration lives exclusively in Kubernetes ConfigMaps and Secrets mounted as environment variables.

Configuration is provisioned declaratively through Kustomize overlays under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` plus per-service `runtime-secrets.example.env` files, with secrets rotated by `sync-*-secrets.sh` scripts. A shared `base/shared/runtime.env` file provides cluster-wide defaults (OTel endpoint, identity broker URL) applied to every pod.

## Key files and packages

- Per-service settings modules:
  - `products/agent-platform/src/agent_service/core/config.py` → `get_settings()` returning `RuntimeSettings`
  - `products/agent-platform/src/agent_service/runtime_settings.py` → `RuntimeSettings` dataclass, provider option types (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`), validation in `__post_init__`, and `from_env()`
  - `products/platform-gateway/src/platform_gateway/core/config.py` → `PlatformGatewaySettings`
  - `products/tool-gateway/src/tool_gateway/core/config.py` → `GatewaySettings`
  - Other services follow the same pattern under their own `src/<service>/core/config.py` (audit-service, execution-runtime, identity-broker, incident-service, skills-hub)
- Shared env helpers: `products/agent-platform/src/agent_service/core/env.py` (`get_env_value`, `get_env_int`)
- GitOps overlay configs:
  - `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (cluster-wide OTel + identity)
  - `shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env` (per-service non-secret knobs)
  - `shared/platform-ops/gitops/runtime-profiles/` (Kustomize overlays for browser-dev, mutating-dev, default profiles)
  - `shared/platform-ops/gitops/sync-*.sh` scripts that generate and mount secrets into pods
- Authoritative cross-service dependency map: `docs/guides/configuration-reference.md`

## Architecture and conventions

1. **Frozen dataclass settings objects** — Every service's settings are `@dataclass(frozen=True)` so they are immutable after construction. This prevents accidental mutation at runtime.
2. **Single-source-of-truth `from_env()`** — All environment parsing happens in one place per service. Boolean flags are parsed uniformly via `_env_bool(name, default)` or a shared truthy set `{"1", "true", "yes", "on"}`; integers and floats use `int()`/`float()` wrappers; optional strings return `None` when unset.
3. **Process-level caching** — `get_settings()` is wrapped with `functools.lru_cache(maxsize=1)`, so each process reads env vars exactly once on first access.
4. **Startup-time validation** — `RuntimeSettings.__post_init__` enforces bounds (e.g. `max_iters >= 1`, `context_trigger_ratio` in `(0, 0.9)`, IANA timezone validity, positive timeouts). Invalid configuration fails fast at import/startup rather than later in a request.
5. **Provider polymorphism** — The agent-service selects provider-specific options (`DashScopeOptions` / `DeepSeekOptions` / `OpenAIOptions`) based on `AGENTSCOPE_PROVIDER`, validated against `SUPPORTED_RUNTIME_PROVIDERS = ("dashscope", "deepseek", "openai", "luban")`. Unknown providers raise a startup error.
6. **Feature-flag gating** — Optional capabilities (browser connector, mutating tools, Elastic, kernel tracing, model discovery, HITL confirmation bridging) are disabled by default and activated only when their corresponding `GATEWAY_*_ENABLED` / `AGENT_*` flags are set. Unset URLs leave connectors unregistered and routes fail-closed (503).
7. **Secrets vs config separation** — Non-sensitive knobs live in `runtime-config.env` (ConfigMap); sensitive values (API keys, client secrets, signing keys, OTLP headers) live in per-service `*-runtime-secrets` Kubernetes Secrets provisioned by `sync-*` scripts. Secrets are never committed to Git.
8. **Cross-service contracts via env var pairs** — Many features require matching pairs across services (e.g. `*_AUDIT_CLIENT_ID` + `*_AUDIT_CLIENT_SECRET` must match entries in `AUDIT_INGEST_CLIENTS`; `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match `IDENTITY_SERVICE_CLIENTS`). These contracts are documented centrally in `docs/guides/configuration-reference.md`.
9. **Policy bundle as immutable deployment artifact** — Policy enforcement is configured via `*_POLICY_PATH` pointing to a YAML file loaded at startup; the canonical source is `shared/shared-contracts/policies/policy-default.yaml`, synced byte-identically to consumers via `make sync-policy`. Missing or invalid bundles fail startup (`PolicyLoadError`), with no silent fallback.
10. **GitOps profile overlays** — Feature postures (mutating-dev, browser-dev, default) are composed via Kustomize overlays that merge additional env into `platform-runtime-config`, keeping base deny-by-default posture intact.

## Conventions and constraints

- **All runtime configuration comes from environment variables**; no `.env` files, JSON, or YAML are read by application code at runtime.
- **Boolean flags** are parsed case-insensitively against `{"1", "true", "yes", "on"}`; any other value is treated as false.
- **Optional string env vars** are normalized to `None` when empty or whitespace-only (via `_optional_str`).
- **Unknown store backends** (e.g. `SESSION_STORE_BACKEND`, `AUDIT_STORE_BACKEND`) fail startup; unknown values are not silently ignored.
- **Missing required secrets** cause feature-specific failures: absent `AGENT_EXECUTION_SIGNING_KEY` rejects mutating resumes with `signing_unavailable`; absent `AGENT_EXECUTION_WORKER_URL` / `AGENT_EXECUTION_HANDOFF_TOKEN` rejects with `worker_unavailable`; unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing (fail-open for observability, fail-closed for security-sensitive paths).
- **Cross-service secret pairs must match**: every emitter's `*_CLIENT_ID` + `*_CLIENT_SECRET` must be registered in the consumer's client registry (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`). Mismatches result in authentication failures.
- **Policy bundle path must exist and parse**: `*_POLICY_PATH` points to a file that must load successfully; there is no packaged default fallback if the configured path is missing.
- **No hot reload of configuration**: policy bundles and settings take effect only on pod restart; changes to ConfigMaps/Secrets require rolling restarts.
- **Defaults are conservative**: mutating tools, browser tools, and audit emission are disabled by default; activation requires explicit opt-in flags plus matching policy grants and RBAC.