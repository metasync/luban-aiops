---
kind: configuration_system
name: Environment-Driven Frozen Settings with Kustomize Runtime Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env
    - shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/mutating.env
---

## What system/approach is used

Every service in the platform uses a uniform, environment-variable-driven configuration system built on Python `dataclasses` decorated as frozen (`@dataclass(frozen=True)`). Each product exposes a single settings class (e.g. `PlatformGatewaySettings`, `RuntimeSettings`, `AuditSettings`, `ExecutionSettings`, `IdentitySettings`, `IncidentSettings`, `SkillsSettings`, `GatewaySettings`) under its `src/<service>/core/config.py`. A module-level `get_settings()` function wrapped in `functools.lru_cache(maxsize=1)` provides process-wide singleton access. There are no `.env` files loaded at runtime, no YAML/TOML config parsers, and no feature-flag libraries — configuration is purely `os.getenv` with typed defaults.

Deployment-time configuration is expressed as Kubernetes ConfigMaps and Secrets mounted via **Kustomize runtime profiles** under `shared/platform-ops/gitops/runtime-profiles/`. The default profile (`default/`) defines a `ConfigMap` named `agent-platform-runtime-profile` that sets `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`; secrets such as API keys live in a separate `runtime-secrets.example.env` file that is never committed and provisioned by scripts like `sync-audit-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-otel-secrets.sh`, etc. Profile overlays (e.g. `mutating-dev/mutating.env`) patch boolean toggles like `GATEWAY_MUTATING_TOOLS_ENABLED=true` for dev postures.

## Key files and packages

- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` with per-provider option types (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`), provider selection via `AGENTSCOPE_PROVIDER`, model discovery knobs, execution worker handoff, audit/incident/skills client credentials, and extensive `__post_init__` validation.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` with service URLs, JWKS cache, token issuer/audience, policy path, and proxy endpoints for tool-gateway/skills-hub.
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` controlling identity/JWKS, mutating tools, redaction, Elastic alerts, and downstream service clients.
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` with store backend, retention, eviction, export limits, ingest/workload client registries parsed from comma-delimited env strings.
- `products/execution-runtime/src/execution_runtime/core/config.py` — `ExecutionSettings` for isolated worker: signing key, handoff token, state store backend (`memory`/`postgres`), flight retention.
- `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings` with Keycloak/OIDC, JWT TTL, delegated token TTL, static service-client registry, and workload subject mapping.
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` with webhook token, query clients, connectors, agent-service URL, triage timeout.
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` with JSON-parsed `SKILLS_SOURCES` (git/local federation entries), `SKILLS_GIT_TOKENS`, sync interval, data path, query/workload client registries.
- `shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml` — base runtime profile ConfigMap.
- `shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env` — example secret variables (API keys, OTLP headers, audit secrets).
- `shared/platform-ops/gitops/runtime-profiles/mutating-dev/mutating.env` — overlay enabling mutating tools for dev.

## Architecture and conventions

1. **One settings class per service.** Each service owns exactly one frozen dataclass of settings plus a `from_env()` classmethod and an `lru_cache`-wrapped `get_settings()` accessor. Consumers call `get_settings()` rather than reading `os.environ` directly.
2. **All values come from environment variables.** Defaults are declared as dataclass field defaults; `from_env()` reads `os.getenv(name, default)`. Boolean parsing consistently accepts `"1", "true", "yes", "on"` (case-insensitive, stripped); optional booleans use a shared `_optional_bool` helper that raises `ValueError` on invalid input.
3. **Startup-time validation via `__post_init__`.** Invalid ranges, unknown enum choices, or inconsistent combinations raise `ValueError` immediately during settings construction, so misconfiguration fails fast before any request is served. Examples include enforced bounds on `max_iters`, `context_trigger_ratio`, `tool_result_limit`, `model_max_retries`, `reply_token_budget`, `timezone` (IANA zone validated via `zoneinfo.ZoneInfo`), supported store backends, and positive timeouts.
4. **Typed sub-settings per capability.** Provider-specific options are distinct dataclasses (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) selected by `provider_options_type(provider)`. Complex multi-value configs are parsed into tuples of small frozen records (`IngestClient`, `WorkloadClient`, `ServiceClient`, `QueryClient`, `SourceSpec`).
5. **Comma-separated list parsing for registries.** Client registries and connector lists are encoded as compact env strings and parsed at startup:
   - `AUDIT_INGEST_CLIENTS`: `client_id=secret,client_id=secret`
   - `AUDIT_WORKLOAD_CLIENTS`: `subject=client_id,subject=client_id`
   - `IDENTITY_SERVICE_CLIENTS`: `client_id:secret:aud1|aud2`
   - `IDENTITY_WORKLOAD_CLIENTS`: `subject=client_id:aud1|aud2`
   - `INCIDENT_QUERY_CLIENTS`, `SKILLS_QUERY_CLIENTS`: same `client_id=secret` format
   - `SKILLS_SOURCES`: JSON list of source objects (validated strictly)
6. **Secrets are kept out of version control.** The example `runtime-secrets.example.env` documents which variables hold secrets (API keys, OTLP auth, audit client secrets, execution signing keys) and notes they are provisioned by `sync-*` scripts and never committed. Services treat missing secrets as disabled features (e.g. unset `audit_service_url` keeps log-only behavior; unset `AGENT_EXECUTION_SIGNING_KEY` fails mutating resumes closed).
7. **Kustomize runtime profiles drive deployments.** Base profiles live under `shared/platform-ops/gitops/runtime-profiles/`. The default profile sets LLM provider metadata; overlays add patches (e.g. `mutating-dev/mutating.env` flips `GATEWAY_MUTATING_TOOLS_ENABLED`). Scripts `select-runtime-profile.sh`, `verify-runtime-profile.sh`, and `deploy-overlay.sh` orchestrate profile selection and application.
8. **Cross-service credential naming is consistent.** Every service that calls another registers itself with a `*_CLIENT_ID` and `*_CLIENT_SECRET` pair (e.g. `PLATFORM_GATEWAY_AUDIT_CLIENT_ID`/`_SECRET`, `AGENT_INCIDENT_CLIENT_ID`/`_SECRET`, `GATEWAY_SKILLS_CLIENT_ID`/`_SECRET`), and each target service declares matching `*_WORKLOAD_*` / `*_QUERY_CLIENTS` / `*_INGEST_CLIENTS` registries.

## Conventions and constraints

- **Frozen settings**: every settings class is immutable (`frozen=True`), preventing accidental mutation after startup.
- **Fail-fast validation**: `__post_init__` rejects invalid values with explicit `ValueError` messages referencing the env var name; there is no silent fallback for bad configuration.
- **Boolean env vars accept only canonical truthy/falsy sets**: `"1", "true", "yes", "on"` → True; `"0", "false", "no", "off"` → False; anything else raises `ValueError`.
- **Optional fields return `None` when unset**, not empty strings, using helpers like `_optional_str` that strip whitespace and coerce to `None`.
- **Store backends are enumerated**: services explicitly validate against frozensets like `{"memory", "postgres"}` and reject unknown values.
- **Missing secrets disable features rather than crashing**: e.g. unset `audit_service_url` keeps log-only posture; unset `AGENT_EXECUTION_SIGNING_KEY` causes signing-unavailable rejections; unset `TOOL_GATEWAY_URL` disables the tool gateway proxy (503).
- **Provider selection is constrained**: `AGENTSCOPE_PROVIDER` must be one of `("dashscope", "deepseek", "openai", "luban")`; unsupported values raise `ValueError` at startup.
- **Profile is decoupled from provider**: `AGENTSCOPE_PROFILE` is a free-form deploy label (SPEC-026 R-5) and no longer implies a specific provider.
- **Per-provider model pinning overrides live discovery**: setting `<PROVIDER>_MODELS` pins the curated series deterministically and skips discovery for that provider.
- **Configuration is layered at deployment time**: base ConfigMap + overlay env patches + injected secrets form the final environment; there is no runtime reload — changes require a restart.