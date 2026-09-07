---
kind: configuration_system
name: Environment-Driven Configuration with Frozen Dataclass Settings and Kustomize Runtime Profiles
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
    - shared/shared-contracts/policies/policy-default.yaml
    - docs/guides/configuration-reference.md
---

## What system/approach is used

The platform uses a uniform, environment-variable-driven configuration system built on Python `dataclasses` (frozen) plus `functools.lru_cache` singletons. Each service defines its own settings dataclass in `src/<service>/core/config.py` (or `runtime_settings.py` for agent-platform), exposes a `from_env()` classmethod that reads values from `os.environ`, and provides a module-level `get_settings()` cached accessor. There are no YAML/JSON config files consumed at runtime by the services themselves; all runtime knobs come from Kubernetes ConfigMaps mounted as environment variables, while secrets are injected via K8s Secrets.

Configuration is layered through Kustomize overlays: a shared base (`shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`) supplies common OTLP identity endpoints, and each service gets a `runtime-config.env` file under its own directory. Non-LLM feature postures (mutating-dev, browser-dev) merge additional env into the same rendered `platform-runtime-config` ConfigMap, so a single pod sees one flat environment.

Policy bundles are the only non-env configuration artifact consumed at runtime — loaded from a filesystem path (`GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH`) and deliberately **not** hot-reloaded; changes take effect only after a rolling restart.

## Key files and packages

- Per-service settings modules:
  - `products/agent-platform/src/agent_service/core/config.py` → `RuntimeSettings.from_env()`
  - `products/agent-platform/src/agent_service/runtime_settings.py` → full `RuntimeSettings` dataclass with validation in `__post_init__`
  - `products/platform-gateway/src/platform_gateway/core/config.py` → `PlatformGatewaySettings`
  - `products/tool-gateway/src/tool_gateway/core/config.py` → `GatewaySettings`
  - Other services follow the same pattern under their own `core/config.py` (identity-service, audit-service, skills-hub, incident-service, execution-runtime)
- Shared helpers: `products/agent-platform/src/agent_service/core/env.py` (`get_env_value`, `get_env_int`)
- Kustomize runtime env sources:
  - `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`
  - `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`
  - `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-secrets.example.env`
- Policy bundle source: `shared/shared-contracts/policies/policy-default.yaml` (replicated to both gateways and dev overlay)
- Authoritative cross-service dependency map: `docs/guides/configuration-reference.md`

## Architecture and conventions

1. **Frozen dataclass + `from_env`**: Every setting surface is a `@dataclass(frozen=True)` with sensible defaults. A classmethod `from_env()` maps `os.getenv(<VAR>, <DEFAULT>)` to constructor arguments. This makes every variable discoverable by grepping the `from_env` body.
2. **Cached singleton access**: `get_settings()` is wrapped in `@lru_cache(maxsize=1)` so the process loads configuration once at import/startup time. Tests can clear the cache or re-import to swap settings.
3. **Boolean parsing convention**: Truthy strings are normalized via `.strip().lower() in {"1", "true", "yes", "on"}` (used consistently across gateways). The agent-platform helper `_optional_bool` additionally rejects unknown values with `ValueError`.
4. **Validation at construction**: `RuntimeSettings.__post_init__` enforces ranges (e.g. `max_iters >= 1`, `context_trigger_ratio` in `(0, 0.9)`, positive timeouts, valid IANA timezone) and raises `ValueError` at startup — invalid configuration fails fast rather than misbehaving later.
5. **Provider polymorphism**: Agent-platform's `RuntimeSettings` selects provider-specific option shapes (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) based on `AGENTSCOPE_PROVIDER`, validated against `SUPPORTED_RUNTIME_PROVIDERS`.
6. **Secrets vs config separation**: Non-secret runtime knobs live in `runtime-config.env` (ConfigMap); sensitive values (API keys, client secrets, signing keys, OTLP headers) live in per-service `*-runtime-secrets` K8s Secrets and are mounted via `secretKeyRef`. The reference doc explicitly marks which variables must be provisioned versus which have code defaults.
7. **Feature flags are opt-in / deny-by-default**: Mutating tools (`GATEWAY_MUTATING_TOOLS_ENABLED=false`), browser tools (`GATEWAY_BROWSER_ENABLED=false`), Elastic connector (`GATEWAY_ELASTIC_ENABLED=false`), kernel tracing (`AGENTSCOPE_KERNEL_TRACING=false`) — enabling them requires explicit env plus matching policy grants and RBAC.
8. **Cross-service contracts are documented centrally**: `docs/guides/configuration-reference.md` enumerates every variable, its default, its source (runtime-config vs runtime-secrets), and the secret contracts between services (delegation chain, audit ingestion, skills query, incidents query).
9. **Policy bundle immutability**: The canonical `policy-default.yaml` is replicated byte-identically to both gateway consumers and the dev overlay via `make sync-policy`; a missing or invalid bundle fails startup (`PolicyLoadError`, no silent fallback). Consumers expose the SHA-256 fingerprint of the loaded bundle on `/health/ready`.
10. **Kustomize profile overlays**: LLM backends are selected by swapping the active profile ConfigMap via `select-runtime-profile.sh`; mutating-dev and browser-dev postures permanently merge extra env into the base render, keeping base deny-by-default.

## Conventions and constraints

- **Every runtime knob is an environment variable.** No `.env` files, JSON configs, or TOML files are read by application code.
- **Defaults live in code, not in env files.** Env files override; unset variables fall back to the dataclass default.
- **Booleans are case-insensitive truthy sets.** All boolean env vars accept `1|true|yes|on` (and sometimes `0|false|no|off` for optional booleans).
- **Missing required secrets fail closed.** Absent `AGENT_EXECUTION_SIGNING_KEY`, `AGENT_EXECUTION_HANDOFF_TOKEN`, `AGENT_AUDIT_CLIENT_SECRET`, etc., cause the relevant capability to fail closed (e.g. `signing_unavailable`, `worker_unavailable`, 503) rather than degrading silently.
- **Optional capabilities degrade gracefully.** Unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing; unset `GATEWAY_SKILLS_SERVICE_URL` leaves the skills connector unregistered; unset `PLATFORM_GATEWAY_TOOL_GATEWAY_URL` leaves the portal Tools route returning 503.
- **Policy bundles are immutable at runtime.** Changes require a rolling restart; there is no hot reload.
- **Secrets are never committed.** All `*-secrets.example.env` files are templates; real secrets are provisioned by scripts under `shared/platform-ops/gitops/sync-*.sh` and stored as K8s Secrets.
- **Cross-service client IDs and secrets must match registries.** E.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match the `IDENTITY_SERVICE_CLIENTS` entry; `*_AUDIT_CLIENT_SECRET` must match the corresponding `AUDIT_INGEST_CLIENTS` entry. Mismatches cause authentication failures.