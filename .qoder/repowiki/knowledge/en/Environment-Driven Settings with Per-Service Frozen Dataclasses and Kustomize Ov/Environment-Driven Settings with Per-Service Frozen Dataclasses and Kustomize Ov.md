---
kind: configuration_system
name: Environment-Driven Settings with Per-Service Frozen Dataclasses and Kustomize Overlays
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - docs/guides/configuration-reference.md
---

## What system/approach is used

The platform uses a **pure environment-variable configuration system** — every runtime setting is read from `os.environ` at process startup into frozen, typed dataclasses. There are no YAML/JSON config files loaded by the application code; configuration is supplied via Kubernetes ConfigMaps and Secrets mounted as environment variables (or file-mounted secrets consumed as paths). Each service owns its own settings module under `products/<service>/src/<service>/core/config.py` (or `runtime_settings.py` for agent-service), and each exposes a cached `get_settings()` accessor that returns a single frozen instance.

Configuration values are layered through **Kustomize overlays**: the canonical defaults live in `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`, with per-feature overlays (e.g. `browser-dev`, `mutating-dev`) merging additional env vars on top. A shared `shared/runtime.env` supplies cluster-wide values like `OTEL_*` and `IDENTITY_SERVICE_URL`. Secrets are provisioned separately via scripts (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-browser-credentials.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`) that generate or reuse shared secrets and write them into per-service K8s Secret objects.

## Key files and packages

- `products/agent-platform/src/agent_service/core/config.py` — thin `@lru_cache(maxsize=1)` accessor returning `RuntimeSettings.from_env()`
- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` frozen dataclass with `from_env()`, provider-specific option parsing, and extensive `__post_init__` validation
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` frozen dataclass with browser connector knobs
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` frozen dataclass
- `products/execution-runtime/src/execution_runtime/core/config.py`, `identity-broker/src/identity_service/core/config.py`, `audit-service/src/audit_service/core/config.py`, `skills-hub/src/skills_hub/core/config.py`, `incident-service/src/incident_service/core/config.py` — analogous per-service settings modules
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service default env var definitions
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared env vars (OTLP, identity broker URL)
- `docs/guides/configuration-reference.md` — authoritative cross-service dependency map, secret contracts, feature activation matrix, policy rollout workflow, and per-service variable tables
- `shared/platform-ops/gitops/gitops/<profile>/...` — Kustomize profile overlays that merge runtime profiles and feature flags

## Architecture and conventions

1. **Frozen dataclass + `from_env()` constructor.** Every service defines a frozen `@dataclass` whose fields mirror environment variables. The classmethod `from_env()` reads each variable with `os.getenv(name, default)`, casts to the correct type, and returns an immutable instance. This makes configuration immutable after startup and easy to test.

2. **Single-process singleton via `lru_cache`.** Each settings module exposes `get_settings()` decorated with `@lru_cache(maxsize=1)` so callers import once and get a cached instance. This avoids repeated env lookups and lets tests monkey-patch `os.environ` between imports.

3. **Strict validation in `__post_init__` (agent-service).** The agent-service's `RuntimeSettings.__post_init__` enforces bounds (e.g. `max_iters >= 1`, `context_trigger_ratio ∈ (0, 0.9)`, valid IANA timezone, non-negative timeouts) and raises `ValueError` at startup if invalid. This is the enforcement mechanism — misconfiguration fails fast rather than silently degrading.

4. **Feature flags as boolean env vars.** Features are toggled via explicit env vars (`GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_BROWSER_ENABLED`, `PLATFORM_GATEWAY_REQUIRE_AUTH`, `AGENT_MODEL_DISCOVERY_ENABLED`, etc.). Defaults are deny-by-default: mutating tools, browser tools, and auth are all disabled unless explicitly enabled.

5. **Secrets separated from config.** Sensitive values (API keys, client secrets, signing keys, OTLP headers) live in Kubernetes Secrets and are mounted as env vars or file paths. Non-sensitive tuning knobs live in ConfigMaps/env files. The `*_CLIENT_SECRET` / `*_AUDIT_CLIENT_SECRET` naming convention consistently pairs a client id with its secret across services.

6. **Cross-service credential registries.** Services expose their own client registries (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`) in the form `client_id=secret,...`. Provisioning scripts generate matching secrets on both sides of each chain, documented in `configuration-reference.md`'s "Secret Contracts" section.

7. **Policy bundle as a separate concern.** Policy is not part of env-based settings — it is a YAML bundle at a configured path (`GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH`). The canonical source is `shared/shared-contracts/policies/policy-default.yaml`, synced to consumers via `make sync-policy`. Missing or invalid bundles fail startup (`PolicyLoadError`); there is no silent fallback.

8. **Runtime profiles via Kustomize.** LLM backends are selected through Kustomize profile overlays that set `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL`, `AGENTSCOPE_API_KEY`, plus optional `<PROVIDER>_MODELS` overrides. Profiles are decoupled from providers (SPEC-026 R-5): the profile label is a free-form deploy label.

## Conventions and constraints

- **Every setting has a default.** Even when a value is optional, the dataclass field has a sensible default so the service starts without every possible env var being set. Optional dependencies (audit-service, skills-hub, incident-service) degrade gracefully when their URLs/secrets are unset.
- **Boolean env vars accept `1|true|yes|on` (case-insensitive).** Parsed uniformly across services via helper functions like `_env_bool` or inline `.strip().lower() in {"1", "true", "yes", "on"}`.
- **Unknown backend values fail startup.** For example, unknown `SESSION_STORE_BACKEND` or `AGENT_STATE_STORE_BACKEND` values cause startup failure; unknown `AGENTSCOPE_PROVIDER` values raise `ValueError` listing supported providers.
- **Mutating operations are fail-closed without required secrets.** Missing `AGENT_EXECUTION_SIGNING_KEY` rejects mutating resumes with `signing_unavailable`; missing `AGENT_EXECUTION_WORKER_URL`/`AGENT_EXECUTION_HANDOFF_TOKEN` rejects with `worker_unavailable`; unset `INCIDENT_WEBHOOK_TOKEN` disables intake with 503.
- **Audit emission is fire-and-forget.** Unreachable audit-service degrades to log-only auditing; user-facing requests are never blocked.
- **Policy changes require restart.** Bundles are cached keyed on path; hot reload is deliberately absent. Changed ConfigMaps take effect only on pod restart.
- **Secrets are never committed to Git.** All provisioning goes through `sync-*` scripts that either generate random secrets or accept exported tokens. The `SKIP_*_SECRETS=true` pattern allows opt-out during local dev.
- **Cross-service chains must be symmetric.** The documentation documents exact contract pairs (e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry; `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` registry). Mismatches break the chain at runtime.