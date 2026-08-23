---
kind: configuration_system
name: Environment-Driven Frozen Settings with Kustomize Profiles and Cross-Service Secret Contracts
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/dashscope/runtime-secrets.example.env
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/shared-contracts/policies/policy-default.yaml
    - docs/guides/configuration-reference.md
---

## What system/approach is used

The platform uses a uniform, environment-variable-driven configuration system across all Python services. Each service defines a frozen `@dataclass` settings object in `src/<service>/core/config.py` (or `runtime_settings.py` for the agent-platform) that reads values from `os.getenv`, validates them at startup, and exposes a module-level `get_settings()` cached via `functools.lru_cache(maxsize=1)`. There is no `.env` file loader, YAML config parser, or runtime reload — configuration is immutable for the process lifetime and sourced entirely from Kubernetes environment variables injected by ConfigMaps/Secrets.

Runtime profiles for the agent-service are delivered as Kustomize overlays under `shared/platform-ops/gitops/runtime-profiles/<profile>/configmap.yaml` (e.g. `dashscope`, `deepseek`, `openai`) that set `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`. A helper script `select-runtime-profile.sh` switches the active profile.

Cross-service secrets (client IDs/secrets, webhook tokens, OTLP headers) are provisioned into per-service Kubernetes Secrets (`*-runtime-secrets`) by shell scripts under `shared/platform-ops/gitops/sync-*.sh` (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`). These scripts generate random shared secrets when not exported and write matching entries into each consumer's secret plus the server-side registry (e.g. `IDENTITY_SERVICE_CLIENTS`, `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`).

## Key files and packages

- Per-service settings modules: `products/*/src/*/core/config.py` (platform-gateway, tool-gateway, audit-service, identity-broker, incident-service, skills-hub) and `products/agent-platform/src/agent_service/runtime_settings.py`
- Agent runtime profile overlays: `shared/platform-ops/gitops/runtime-profiles/{dashscope,deepseek,openai}/configmap.yaml` and `runtime-secrets.example.env`
- Dev deployment env injection: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` and `runtime-secrets.example.env`
- Shared runtime defaults: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`
- Policy bundle (configuration-as-code): `shared/shared-contracts/policies/policy-default.yaml`, mirrored to `products/*/policies/policy-default.yaml` and mounted at `/etc/luban/policy/policy.yaml`
- Configuration reference documentation: `docs/guides/configuration-reference.md` (authoritative cross-service dependency map)
- Provisioning scripts: `shared/platform-ops/gitops/sync-*.sh`

## Architecture and conventions

1. **Frozen dataclass + `from_env` factory**: Every settings class is `@dataclass(frozen=True)` with a `@classmethod from_env(cls)` that reads only `os.getenv(key, default)`. No mutable state, no file parsing.
2. **Cached singleton accessor**: Each module exposes `@lru_cache(maxsize=1) def get_settings() -> <Settings>` so callers import once and reuse the parsed instance.
3. **Strict boolean parsing**: Booleans accept only `"1"|"true"|"yes"|"on"` (case-insensitive); unset defaults to `False` unless explicitly overridden. The agent-platform helpers `_optional_bool` raise `ValueError` on unknown values.
4. **Startup validation**: Invalid values fail fast in `__post_init__` or `from_env` (e.g. unsupported provider, out-of-range `max_iters`, invalid IANA timezone, mismatched `AGENTSCOPE_PROFILE` vs `AGENTSCOPE_PROVIDER`). Services like skills-hub and incident-service define a `SettingsError` exception for malformed composite fields.
5. **Per-service namespace prefix on env vars**: Variables are scoped with a service-specific prefix (`PLATFORM_GATEWAY_*`, `GATEWAY_*`, `AUDIT_*`, `IDENTITY_*`, `INCIDENT_*`, `SKILLS_*`, `AGENTSCOPE_*`) to avoid collisions across services.
6. **Comma-separated list parsers for registries**: Client registries use compact string formats parsed at startup:
   - `AUDIT_INGEST_CLIENTS`: `client_id=secret,...`
   - `AUDIT_WORKLOAD_CLIENTS`: `subject=client_id,...`
   - `IDENTITY_SERVICE_CLIENTS`: `client_id:secret:aud1|aud2,...`
   - `SKILLS_SOURCES`: JSON list of `{source_id, type, url?, path?, ref?}` with strict validation
   - `SKILLS_GIT_TOKENS`: JSON map `source_id→token`
7. **Optional feature toggles via empty URL/env**: Many features are opt-in by leaving an env var unset — e.g. `*_AUDIT_SERVICE_URL` falls back to log-only auditing; `GATEWAY_SKILLS_SERVICE_URL` unregisters the skills connector; `PLATFORM_GATEWAY_TOOL_GATEWAY_URL` makes the portal Tools route return 503; `INCIDENT_WEBHOOK_TOKEN` empty disables intake.
8. **Kustomize-based overlay delivery**: Non-secret configuration lives in `runtime-config.env` files mounted as env sources per service; secrets live in separate `runtime-secrets.example.env` templates and are populated by `sync-*.sh` scripts into Kubernetes Secrets.
9. **Policy as code**: The policy bundle is a single canonical YAML (`shared/shared-contracts/policies/policy-default.yaml`) synced to every consumer location and mounted at `/etc/luban/policy/policy.yaml`; consumers read it via `policy_path` env var.
10. **Cross-service secret contracts documented centrally**: `docs/guides/configuration-reference.md` maps every capability to required variables, default values, source (ConfigMap vs Secret), and provisioning script — this is the authoritative contract between services (e.g. token delegation chain, audit ingestion chain, skills query chain).

## Conventions and constraints

- **No runtime reload**: Settings are loaded once at import time and cached; changing env vars requires a pod restart.
- **Secrets never committed**: All sensitive values (API keys, client secrets, webhook tokens, OTLP headers) are provisioned via `sync-*.sh` into Kubernetes Secrets; example files end in `.example.env` and contain placeholders only.
- **Fail-closed defaults**: Features are disabled by default unless their enabling env var is explicitly set to a truthy value (e.g. `GATEWAY_MUTATING_TOOLS_ENABLED=false`, `GATEWAY_ELASTIC_ENABLED=false`, `PLATFORM_GATEWAY_REQUIRE_AUTH=true`).
- **Typed validation at startup**: Unsupported providers, invalid ranges, malformed JSON, duplicate source IDs, and mismatched profile/provider pairs raise exceptions during process start — misconfiguration is caught before serving traffic.
- **Shared credential registries enforce cross-service auth**: Each consumer service maintains its own registry (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`) that must match the corresponding `*_CLIENT_SECRET` configured on the caller; mismatches cause authentication failures.
- **Workload identity support**: Services expose parallel `*_WORKLOAD_ISSUER_URL` / `*_WORKLOAD_AUDIENCE` / `*_WORKLOAD_CLIENTS` variables to accept projected Kubernetes ServiceAccount tokens alongside static client credentials.
- **Profile isolation**: Only one LLM runtime profile is active at a time; switching requires reapplying the Kustomize overlay via `select-runtime-profile.sh`.