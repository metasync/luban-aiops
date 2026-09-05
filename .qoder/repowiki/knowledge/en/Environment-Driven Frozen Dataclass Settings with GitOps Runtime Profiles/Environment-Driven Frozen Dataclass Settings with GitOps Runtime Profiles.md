---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with GitOps Runtime Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/browser.env
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/mutating.env
    - docs/guides/configuration-reference.md
---

## What system/approach is used

Every microservice in the Luban platform loads configuration exclusively from **environment variables** via Python `os.getenv`, into **frozen `dataclass` settings objects**. There are no `.env` files read at runtime, no YAML/JSON config files parsed by the services themselves, and no feature-flag libraries. Configuration is layered through Kubernetes: a base `platform-runtime-config` ConfigMap plus per-profile overlays (e.g. `browser-dev`, `mutating-dev`) merge environment variables into each pod's container spec. Secrets (API keys, signing keys, client secrets) are injected as separate K8s Secrets mounted as env vars or file paths.

The pattern is uniform across all eight services:
- A `core/config.py` module defines one frozen dataclass (e.g. `PlatformGatewaySettings`, `AuditSettings`, `GatewaySettings`, `RuntimeSettings`, `IncidentSettings`, `SkillsSettings`, `ExecutionSettings`).
- Each class exposes a `@classmethod from_env(cls)` that reads its prefixed env vars and builds the object.
- A module-level `@lru_cache(maxsize=1) get_settings()` function returns the singleton instance.
- Services import `get_settings()` wherever they need configuration; tests can call it to obtain the same cached instance.

## Key files and packages

- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` (`PLATFORM_GATEWAY_*`, `AGENT_SERVICE_URL`, `IDENTITY_*`, `AUDIT_*`, `INCIDENT_*`, `SKILLS_*`)
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` (`GATEWAY_*`, browser connector knobs, Elastic, mutating tools)
- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` (`AGENTSCOPE_*`, `AGENT_*`, provider-specific options for dashscope/deepseek/openai/luban)
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` (`AUDIT_*`, ingest/workload client registries)
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` (`INCIDENT_*`, query/workload clients)
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` (`SKILLS_*`, git sources JSON, query/workload clients)
- `products/execution-runtime/src/execution_runtime/core/config.py` — `ExecutionSettings` (`EXECUTION_*`, state store backend)
- `shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml` — default runtime profile exposing `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL`
- `shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env` — example LLM provider keys and per-provider model pinning
- `shared/platform-ops/gitops/runtime-profiles/browser-dev/browser.env`, `mutating-dev/mutating.env` — feature toggles merged into the profile
- `docs/guides/configuration-reference.md` — cross-service dependency map and provisioning notes

## Architecture and conventions

### Per-service frozen settings object
Each service owns exactly one settings dataclass. Fields have sensible defaults so services start in a safe posture without any env vars set (e.g. `store_backend="memory"`, `require_auth=True`, `browser_enabled=False`, `k8s_enabled=False`, `mutating_tools_enabled=False`). The dataclasses are `frozen=True`, making them immutable after construction.

### Environment variable naming
- Service-scoped prefix: `PLATFORM_GATEWAY_*`, `GATEWAY_*`, `AGENTSCOPE_*` / `AGENT_*`, `AUDIT_*`, `INCIDENT_*`, `SKILLS_*`, `EXECUTION_*`.
- Cross-service shared values use the target service's prefix (e.g. `AGENT_SERVICE_URL` is consumed by platform-gateway but named after the agent service).
- Boolean flags accept `true/false/yes/no/1/0/on/off` via a shared truthy set `{"1", "true", "yes", "on"}`.
- Complex lists are comma-separated key=value pairs (e.g. `AUDIT_INGEST_CLIENTS=client_id=secret,...`, `INCIDENT_QUERY_CLIENTS=...`, `SKILLS_WORKLOAD_CLIENTS=subject=client_id,...`).
- Complex structures are JSON strings (e.g. `SKILLS_SOURCES=[{"source_id":"...","type":"git","url":"..."}]`, `SKILLS_GIT_TOKENS={...}`).

### Parsing helpers
Services define small typed parsers for repeated patterns: `parse_ingest_clients`, `parse_query_clients`, `parse_workload_clients`, `parse_connectors`, `parse_sources`, `parse_git_tokens`, `parse_positive_int`. These enforce format constraints at load time.

### Startup validation
Validation lives in `__post_init__` or in `from_env` and raises `ValueError` (or a service-specific `SettingsError`) on invalid values. Examples: `max_iters >= 1`, `context_trigger_ratio` in `(0, 0.9)`, `state_store_backend` must be `memory|postgres`, `postgres` requires `state_db_url`, IANA timezone must be valid, `provider` must be one of `dashscope|deepseek|openai|luban`, positive timeouts must be > 0. This ensures misconfiguration fails fast at startup rather than later at runtime.

### Caching
`get_settings()` is wrapped with `functools.lru_cache(maxsize=1)`, so the entire process shares one settings instance. Tests that mutate env vars must clear the cache or run in isolated processes.

### Feature gating
Features are disabled-by-default via boolean fields and enabled by setting the corresponding env var to a truthy value. Notable examples:
- `GATEWAY_MUTATING_TOOLS_ENABLED` — enables write/admin tools (requires policy grant + HITL).
- `GATEWAY_BROWSER_ENABLED` — enables web-check browser connector (deny-by-default origin allowlist).
- `GATEWAY_ELASTIC_ENABLED` — enables Elastic alert ingestion.
- `AGENT_MODEL_DISCOVERY_ENABLED` — enables live model catalog discovery.
- `AGENT_EXECUTION_SIGNING_KEY` / `AGENT_EXECUTION_WORKER_URL` — enable signed execution and isolated worker handoff.

### Secrets handling
Secrets are never embedded in code. They come from K8s Secrets mounted as env vars or file paths:
- `*_CLIENT_SECRET` fields (audit, skills, incident, identity delegation).
- `AGENTSCOPE_API_KEY`, `DASHSCOPE_API_KEY`, `OPENAI_API_KEY`, `LUBAN_API_KEY`.
- `AGENT_EXECUTION_SIGNING_KEY`, `AGENT_EXECUTION_HANDOFF_TOKEN`.
- `GATEWAY_BROWSER_CREDENTIAL_SETS` points to a mounted file path (no inline credentials accepted).
- `OTEL_EXPORTER_OTLP_HEADERS` provisioned by `sync-otel-secrets.sh`.

### GitOps runtime profiles
Deployment configuration is organized under `shared/platform-ops/gitops/runtime-profiles/`. A base `default/` profile sets the LLM provider/model; overlay directories like `browser-dev/` and `mutating-dev/` add feature flags. The `select-runtime-profile.sh` script selects which profile to apply, and `deploy-overlay.sh` applies the resulting Kustomization. Secret provisioning scripts (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`) generate or inject secrets into the cluster and update the active profile's `runtime-secrets.env` in place.

### Cross-service contracts
Configuration references are documented in `docs/guides/configuration-reference.md` as dependency chains showing which env vars must match across services (e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS`, `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`, `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`). These are enforced at runtime by the receiving service's auth logic, not by the settings loader itself.

## Conventions and constraints

- **One settings class per service**, located at `<service>/src/<service_pkg>/core/config.py` (except agent-platform, which uses `runtime_settings.py`).
- **All settings are loaded from environment only** — no file-based config parsing in services.
- **Dataclasses are frozen**; settings are immutable after `from_env`.
- **Boolean env vars** accept `true/false/yes/no/1/0/on/off` uniformly.
- **Complex multi-value settings** use either comma-separated `key=value` pairs or JSON strings; parsers validate and raise on malformed input.
- **Startup validation** rejects invalid values with `ValueError`/`SettingsError`; there is no silent fallback for invalid numeric ranges or unsupported enums.
- **Feature flags default to disabled** (false, empty string, or off) so new features ship opt-in.
- **Cross-service secrets are paired**: every emitter's `*_AUDIT_CLIENT_SECRET` must match a registered entry in the consumer's client registry; mismatches fail at the receiver's auth layer.
- **Profiles override base env**: runtime profiles under `shared/platform-ops/gitops/runtime-profiles/*/` are applied on top of defaults, enabling environment-specific feature toggles without changing source code.
- **Secrets are provisioned by scripts**, not committed: `sync-*` scripts generate random secrets or upsert values into the active profile's `runtime-secrets.env`, keeping credentials out of version control.