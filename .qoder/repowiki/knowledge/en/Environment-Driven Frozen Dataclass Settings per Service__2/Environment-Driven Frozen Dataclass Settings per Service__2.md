---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings per Service
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/runtime.py
    - products/audit-service/src/audit_service/core/runtime.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/README.md
---

## What system/approach is used

Every service in the monorepo loads its runtime configuration exclusively from **environment variables** into **frozen `dataclass` settings objects**, cached via `functools.lru_cache(maxsize=1)` behind a module-level `get_settings()` accessor. There is no YAML/JSON config file loading at runtime, no `.env` parser, and no framework-based config (e.g. Pydantic-settings, dynaconf). Configuration is split into two layers:

1. **Service-specific settings** — one frozen dataclass per product under `<product>/src/<service>/core/config.py`, parsed by a `from_env()` classmethod.
2. **Runtime/hosting settings** — a small `runtime.py` per service that reads only `*_HOST` / `*_PORT` to configure the Uvicorn server entrypoint (`main.py`).

The agent-platform runtime additionally has a richer `RuntimeSettings` in `agent_service/runtime_settings.py` that validates provider options, kernel tuning knobs, and timezone values in `__post_init__`.

## Key files and packages

- `products/*/src/*_service/core/config.py` — per-service frozen settings + `get_settings()` cache.
- `products/*/src/*_service/core/runtime.py` — host/port run settings consumed by `main.py`.
- `products/agent-platform/src/agent_service/runtime_settings.py` — agent runtime profile/provider/model/kernel middleware settings with typed validation.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared env injected into every pod (OTel endpoint, default identity broker URL).
- `shared/platform-ops/gitops/runtime-profiles/<profile>/configmap.yaml` — non-secret LLM provider profiles mounted as ConfigMap keys (e.g. `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL`).
- `shared/platform-ops/gitops/runtime-profiles/<profile>/runtime-secrets.example.env` — template for secret-only env (API keys, client secrets) provisioned by sync scripts.

## Architecture and conventions

### Per-service frozen dataclass settings
Each service defines a single frozen dataclass representing all of its configuration:
- `PlatformGatewaySettings` (platform-gateway)
- `GatewaySettings` (tool-gateway)
- `AuditSettings` (audit-service)
- `IncidentSettings` (incident-service)
- `SkillsSettings` (skills-hub)
- `IdentitySettings` (identity-broker)
- `RuntimeSettings` (agent-platform runtime)

Defaults are declared as dataclass field defaults; there is no separate "defaults" file.

### Environment variable naming
Variables follow a `<SERVICE>_` prefix convention so each service owns its namespace:
- `PLATFORM_GATEWAY_*` for platform-gateway
- `GATEWAY_*` for tool-gateway
- `AUDIT_*` for audit-service
- `INCIDENT_*` for incident-service
- `SKILLS_*` for skills-hub
- `IDENTITY_*` / `KEYCLOAK_*` / `OIDC_*` for identity-broker
- `AGENTSCOPE_*` / `AGENT_*` / `DASHSCOPE_*` / `DEEPSEEK_*` / `OPENAI_*` for agent-runtime

Boolean flags are normalized via `.strip().lower() in {"1", "true", "yes", "on"}` (or an explicit `_optional_bool` helper that also accepts `0/false/no/off`).

### Complex list/map parsing helpers
Multi-value settings use compact string formats parsed in dedicated helpers:
- Comma-separated `client_id=secret,...` lists (used by audit, incident, skills, identity services for static client registries).
- Comma-separated `subject=client_id,...` workload subject-to-client mappings.
- JSON-encoded lists/maps for skill sources (`SKILLS_SOURCES`) and git tokens (`SKILLS_GIT_TOKENS`).
- Colon/pipe-delimited audience allow-lists in identity broker's `IDENTITY_SERVICE_CLIENTS` and `IDENTITY_WORKLOAD_CLIENTS`.

These parsers raise a `SettingsError` (or `ValueError`) on malformed input, causing startup failure rather than silent misconfiguration.

### Cached singleton access
Every settings module exposes `@lru_cache(maxsize=1)`-decorated `get_settings()` returning the same instance for the process lifetime. Consumers import and call it wherever they need configuration (routes, app startup, dependency factories). Tests can patch or replace the module-level function.

### Validation strategy
Validation happens in two places:
1. **Parser functions** validate format (e.g. `parse_sources` rejects unknown types, duplicate `source_id`, path traversal).
2. **`__post_init__`** on `RuntimeSettings` enforces business constraints: matching `profile`/`provider`, bounds on `max_iters`, `context_trigger_ratio`, `tool_result_limit`, `model_max_retries`, positive token weights, valid IANA timezone, and type-matching `provider_options` against the selected provider.

### Secrets vs non-secrets
Non-secret configuration lives in ConfigMaps (e.g. `agent-platform-runtime-profile`, `platform-runtime-config`). Secrets (API keys, client secrets, JWT private key paths) are expected to be mounted as environment variables from Kubernetes Secrets provisioned by scripts like `sync-otel-secrets.sh`, `sync-delegation-secrets.sh`, `sync-runtime-secret.sh`. The `runtime-secrets.example.env` files document the contract but are not committed.

### Runtime profiles
The agent-platform supports pluggable LLM backends through Kustomize overlays under `shared/platform-ops/gitops/runtime-profiles/`. Each profile contributes a ConfigMap named `agent-platform-runtime-profile` setting `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`. The active profile is selected by including exactly one overlay in the `dev-k8s` deployment; `mutating-dev` is a posture overlay (not an LLM profile) that sets `GATEWAY_MUTATING_TOOLS_ENABLED=true`.

## Conventions and constraints

- **No file-based config at runtime**: All settings come from `os.getenv`; there is no `pyproject.toml` `[tool.*]` config read by the services, no YAML loader in `from_env`, and no dotenv file.
- **Frozen dataclasses**: Settings objects are immutable once constructed, preventing accidental mutation at runtime.
- **Fail-fast on bad config**: Malformed environment values raise exceptions during `from_env()` / `__post_init__`, so invalid configuration kills the process before serving requests.
- **Per-service env namespaces**: Each service prefixes its env vars with its own namespace to avoid collisions across the multi-service deployment.
- **Default deny posture**: Feature flags like `require_auth`, `mutating_tools_enabled`, `k8s_enabled`, `elastic_enabled` default to `False` unless explicitly enabled.
- **Shared base env**: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` provides common env (OTel endpoint, default identity broker URL) injected into every pod; service-specific overrides live in per-service overlays.
- **Spec-driven evolution**: Many settings comments reference SPEC numbers (SPEC-009, SPEC-013, SPEC-014, SPEC-015, SPEC-017, SPEC-018, SPEC-020), tying configuration surfaces to spec requirements.