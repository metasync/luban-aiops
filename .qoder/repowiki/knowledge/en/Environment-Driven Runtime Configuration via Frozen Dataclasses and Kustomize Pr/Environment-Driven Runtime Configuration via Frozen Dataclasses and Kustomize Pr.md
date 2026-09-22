---
kind: configuration_system
name: Environment-Driven Runtime Configuration via Frozen Dataclasses and Kustomize Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/metadata.py
    - products/audit-service/src/audit_service/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-secrets.example.env
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/browser.env
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/mutating.env
---

## What system/approach is used

The platform uses a uniform, environment-variable-driven configuration system across all nine product services. Each service defines its own frozen `dataclass` settings object (e.g. `RuntimeSettings`, `AuditSettings`, `PlatformGatewaySettings`, `GatewaySettings`, `IncidentSettings`, `SkillsSettings`, `ExecutionSettings`, `IdentitySettings`) with a `from_env()` classmethod that reads values from `os.environ`. Settings are loaded once at process start and cached via `functools.lru_cache(maxsize=1)` through a module-level `get_settings()` accessor. There is no external config library — pure stdlib (`os.getenv`, `dataclasses`, `functools`).

Configuration is layered in two stages:
1. **Base runtime env** — shared across every pod via `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (OTel endpoint, identity broker URL).
2. **Per-service runtime env** — per-deployment files under each service's directory (e.g. `base/agent-platform/runtime-config.env`, `base/tool-gateway/runtime-config.env`) plus optional secret overlays (`runtime-secrets.example.env` files provisioned by `sync-*-secrets.sh` scripts into Kubernetes Secrets).
3. **Runtime profiles** — pluggable overlays under `shared/platform-ops/gitops/runtime-profiles/<profile>/` (default, browser-dev, mutating-dev) that merge additional env vars into the `platform-runtime-config` ConfigMap via Kustomize.

## Key files and packages

- Per-service settings modules: `products/*/src/*_service/core/config.py` (audit, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) and `products/agent-platform/src/agent_service/runtime_settings.py`.
- Service metadata defaults: `products/agent-platform/src/agent_service/metadata.py` (provides `RUNTIME_APP_NAME` default for `AGENTSCOPE_AGENT_NAME`).
- Base runtime env: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`.
- Per-service base env: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`.
- Secret examples: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-secrets.example.env`.
- Profile overlays: `shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml`, `runtime-profiles/default/runtime-secrets.example.env`, `runtime-profiles/browser-dev/browser.env`, `runtime-profiles/mutating-dev/mutating.env`.
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-audit-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-incident-secrets.sh`, `sync-skills-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`, etc.

## Architecture and conventions

### Frozen dataclass + `from_env()` pattern
Every service exposes a single frozen dataclass holding all runtime knobs. Defaults are declared as class attributes; `from_env()` maps one or more environment variables to fields, often with type coercion helpers (`int`, `float`, boolean truthiness checks against `{"1","true","yes","on"}`). The `get_settings()` function wraps `from_env()` in `@lru_cache(maxsize=1)` so the configuration is parsed exactly once per process.

### Strict validation in `__post_init__`
The agent-platform's `RuntimeSettings` demonstrates the validation convention: after parsing, `__post_init__` enforces domain constraints (e.g. `max_iters >= 1`, `context_trigger_ratio` in `(0, 0.9)`, valid IANA timezone, provider-options type must match selected provider). Invalid configuration fails startup rather than propagating bad state.

### Boolean parsing helper
Both `agent_platform.runtime_settings._optional_bool` and `tool_gateway.core.config._env_bool` parse booleans using the same truthy set `{"1", "true", "yes", "on"}`, ensuring consistent flag semantics across services.

### Feature flags are opt-in / deny-by-default
Many capabilities are disabled by default and enabled only when explicitly configured:
- Browser connector (`GATEWAY_BROWSER_ENABLED=false` in base, toggled via `browser-dev` profile).
- HTTP connector (`GATEWAY_HTTP_ENABLED=false` in base, toggled via `browser-dev` profile).
- Mutating tools (`GATEWAY_MUTATING_TOOLS_ENABLED=false` in base, toggled via `mutating-dev` profile).
- Kernel tracing (`AGENTSCOPE_KERNEL_TRACING` unset in dev, overridden to `true` in dev env).
- Model discovery (`AGENT_MODEL_DISCOVERY_ENABLED=True` default but can be pinned off).

### Secrets vs non-secrets separation
Non-secret configuration lives in `runtime-config.env` files mounted as ConfigMaps. Secrets (API keys, client secrets, OTLP auth headers) live in `runtime-secrets.example.env` templates and are materialized into Kubernetes Secrets by `sync-*` scripts — these files are never committed to source control. The comments in each `runtime-secrets.example.env` document which sync script provisions it and what contract it satisfies.

### Runtime profiles as Kustomize overlays
Profiles under `runtime-profiles/` are merged on top of the base overlay. The `default` profile sets `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL` via a ConfigMap; `browser-dev` adds browser/HTTP connector enablement and allowlists; `mutating-dev` enables mutating tools. A `select-runtime-profile.sh` script selects which profile to apply.

### Cross-service dependency URLs
Services discover peers via environment variables with sensible defaults pointing to Kubernetes service DNS names (`identity-service:8000`, `agent-service:8000`, `tool-gateway:8000`, etc.). Optional dependencies (audit-service, incident-service, skills-hub) are configured via their own `*_SERVICE_URL` + `*_CLIENT_ID` + `*_CLIENT_SECRET` triplets; if unset, the calling service returns a 503 with a "dependency not configured" posture rather than crashing.

### Provider abstraction
The agent-platform's `RuntimeSettings` abstracts LLM providers behind `AGENTSCOPE_PROVIDER` (`dashscope`, `deepseek`, `openai`, `luban`) with provider-specific option namespaces (`DASHSCOPE_*`, `DEEPSEEK_*`, `OPENAI_*`, `LUBAN_*`). The `default` runtime profile pins deepseek; local/on-prem deployments use the `luban` provider backed by Ollama/vLLM.

## Conventions and constraints

- **One settings class per service**: each product has exactly one frozen dataclass in `core/config.py` (or `runtime_settings.py` for agent-platform) with a `from_env()` constructor.
- **All configuration comes from environment variables**: no `.yaml`/`.toml` config files are read at runtime by application code; deployment manifests mount env files into pods.
- **Defaults are explicit in code**: every field has a sensible default attribute on the dataclass; missing env vars fall back to those defaults.
- **Boolean flags use a canonical truthy set**: `{"1", "true", "yes", "on"}` — case-insensitive, stripped whitespace.
- **Secrets are never committed**: `runtime-secrets.example.env` files contain placeholders and are overwritten by `sync-*` scripts into cluster Secrets.
- **Feature flags are deny-by-default**: security-sensitive features (browser automation, HTTP egress, mutating tools) are disabled unless explicitly enabled via a profile overlay.
- **Validation fails fast**: invalid configuration raises `ValueError` during `__post_init__`, preventing the service from starting misconfigured.
- **Profile label decoupling**: `AGENTSCOPE_PROFILE` is a free-form deploy label (SPEC-026 R-5) and is independent of `AGENTSCOPE_PROVIDER`; there is no profile-to-provider allowlist.
- **Optional dependencies fail closed**: missing audit/incident/skills service URLs result in 503 responses rather than silent degradation.
- **Shared runtime env is centralized**: `base/shared/runtime.env` holds cross-cutting settings (OTel, identity broker URL) consumed by every pod.