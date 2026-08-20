---
kind: configuration_system
name: Environment-Driven Frozen Settings with Cross-Service Secret Contracts
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - docs/guides/configuration-reference.md
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-secrets.env
    - shared/shared-contracts/policies/policy-default.yaml
---

# Configuration System

## What system/approach is used

The platform uses a uniform **12-factor-style environment-variable configuration** pattern across every Python service. Each service defines a frozen `@dataclass` settings object in `src/<service>/core/config.py` (or `runtime_settings.py` for the agent-platform) that reads values from `os.getenv`, applies type coercion and validation, and exposes a module-level `get_settings()` accessor cached via `functools.lru_cache(maxsize=1)`. There are no YAML/JSON config files consumed at runtime by services; configuration lives entirely in Kubernetes ConfigMaps (`*-runtime-config.env`) and Secrets (`*-runtime-secrets`), mounted as environment variables into pods.

Complex multi-value settings use compact string serialization formats parsed at startup:
- Comma-separated key=value pairs: `<client_id>=<secret>,...` (used for ingest/query client registries like `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`).
- JSON strings: `SKILLS_SOURCES` (a list of source dicts), `SKILLS_GIT_TOKENS` (a map of `source_id`→token).
- Colon/pipe-delimited entries: `IDENTITY_SERVICE_CLIENTS` uses `client_id:secret:aud1|aud2` format.

Boolean flags are normalized via a shared helper that accepts `"1", "true", "yes", "on"` (and rejects unknown values). Numeric and optional fields use typed helpers (`_optional_int`, `_optional_float`, `_optional_bool`, `_optional_choice`) in the agent-platform's `runtime_settings.py`.

## Key files and packages

- Per-service settings modules:
  - `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` with provider-specific option subtypes (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) and kernel middleware tuning knobs.
  - `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` (JWKS URLs, delegation audience, audit/incident client wiring).
  - `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` (K8s/Elastic connectors, redaction, skills/incidents clients).
  - `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` (store backend, retention, eviction, ingest/workload client registries).
  - `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` (federated sources, git tokens, query/workload clients).
  - `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` (webhook token, connector list, query/workload clients).
  - `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings` (Keycloak/OIDC, JWT signing, service/workload client registries).
- Shared documentation: `docs/guides/configuration-reference.md` — authoritative cross-service env var dependency map, secret contracts, and provisioning scripts.
- Deployment overlays: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` and `runtime-secrets.env` per service.
- Profile overlays: `shared/platform-ops/gitops/runtime-profiles/{dashscope,deepseek,openai}/configmap.yaml` plus `sync-runtime-secret.sh`.
- Policy bundle: `shared/shared-contracts/policies/policy-default.yaml` synced to consumer locations under each gateway's `policies/` directory.

## Architecture and conventions

1. **Frozen dataclasses**: Every settings class is declared with `@dataclass(frozen=True)`, making configuration immutable after construction. This prevents accidental mutation at runtime.

2. **Startup-time parsing & validation**: All complex parsing happens in `from_env()`. Invalid values raise `ValueError` or a service-specific `SettingsError` during import/startup, ensuring misconfiguration fails fast rather than causing silent runtime errors. Examples include range checks on `AGENTSCOPE_MAX_ITERS >= 1`, open-interval check on `context_trigger_ratio ∈ (0, 0.9)`, IANA timezone validation via `zoneinfo.ZoneInfo`, and duplicate `source_id` detection in `SKILLS_SOURCES`.

3. **Single-source-of-truth accessor**: Each module exports `@lru_cache(maxsize=1) get_settings()` so the process loads env vars once and reuses the same frozen instance everywhere.

4. **Feature toggles via presence**: Many capabilities are opt-in by setting an empty/default value:
   - `*_STORE_BACKEND=memory` vs `postgres` selects persistence backends.
   - `*_SERVICE_URL` unset disables a connector (e.g., skills tools unregistered when `GATEWAY_SKILLS_SERVICE_URL` is empty).
   - `*_AUDIT_SERVICE_URL` unset falls back to log-only auditing.
   - `PLATFORM_GATEWAY_REQUIRE_AUTH=false` enables dev mode with synthetic identity.

5. **Cross-service secret contracts**: The configuration reference documents explicit pairing rules between emitter secrets and receiver registries:
   - Token delegation: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ entry in `IDENTITY_SERVICE_CLIENTS` (`platform-gateway:<secret>:tool-gateway`).
   - Audit ingestion: each emitter's `*_AUDIT_CLIENT_SECRET` ↔ matching `client_id=secret` in `AUDIT_INGEST_CLIENTS`.
   - Skills/incidents query: `*_CLIENT_SECRET` ↔ matching entry in `*_QUERY_CLIENTS`.
   These are provisioned by dedicated shell scripts (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`) that generate random secrets and write K8s `Secret` objects.

6. **Runtime profiles**: The agent-platform supports pluggable LLM backends via Kustomize profile overlays under `runtime-profiles/`; only one profile is active at a time, selected by `select-runtime-profile.sh`. Profiles set `AGENTSCOPE_PROVIDER`, model name, base URL, and API key.

7. **Policy-as-code**: The policy bundle is maintained centrally in `shared/shared-contracts/policies/policy-default.yaml`, validated against a JSON schema (`make validate-policy`), then byte-synced to all consumers (`make sync-policy`). Consumers load it via `policy_path` env var pointing to `/etc/luban/policy/policy.yaml`.

## Conventions and constraints

- **All configuration comes from environment variables**; no `.env` files, YAML configs, or TOML files are read by application code.
- **Secrets never live in Git**: they are generated at deploy time and mounted as Kubernetes Secrets. The configuration reference explicitly marks which keys come from `runtime-secrets` vs `runtime-config.env`.
- **Unknown store backends fail startup**: `store_backend` values are stripped and lowercased but must be recognized (`memory`, `postgres`); unknown values cause startup failure.
- **Boolean normalization is strict**: accepted values are exactly `{"1", "true", "yes", "on"}`; any other string raises an error.
- **Cross-service client registries are comma-separated key=value lists** parsed by small dedicated `parse_*` functions; malformed entries are silently skipped, but missing required parts are ignored.
- **Workload identity mapping** follows a consistent `subject=client_id[:aud1|aud2]` format across services (`AUDIT_WORKLOAD_CLIENTS`, `SKILLS_WORKLOAD_CLIENTS`, `INCIDENT_WORKLOAD_CLIENTS`, `IDENTITY_WORKLOAD_CLIENTS`).
- **Agent-platform provider options are type-checked against the active provider**: `provider_options_type(provider)` returns the expected subtype, and `__post_init__` raises if the configured options don't match.
- **Timezone values are validated as valid IANA names** at startup via `zoneinfo.ZoneInfo`.
- **Configuration reference is the authoritative contract**: `docs/guides/configuration-reference.md` enumerates every variable, its purpose, default, and source, and is treated as the single source of truth for operators.