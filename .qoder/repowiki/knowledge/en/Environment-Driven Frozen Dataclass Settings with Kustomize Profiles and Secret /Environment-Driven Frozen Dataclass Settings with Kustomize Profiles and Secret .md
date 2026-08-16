---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Kustomize Profiles and Secret Sync Scripts
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/openai/runtime-secrets.example.env
    - shared/shared-contracts/policies/policy-default.yaml
    - docs/guides/configuration-reference.md
---

## What system/approach is used

Every microservice in the Luban AIOps platform follows a uniform, code-first configuration pattern:

1. **Frozen dataclasses** define all settings for a service (e.g. `PlatformGatewaySettings`, `AuditSettings`, `SkillsSettings`, `IdentitySettings`, `RuntimeSettings`).
2. Each dataclass exposes a classmethod `from_env()` that reads values from environment variables via `os.getenv` with typed defaults.
3. A module-level `@lru_cache(maxsize=1)` function `get_settings()` returns a singleton instance loaded once at import time.
4. Configuration is consumed by calling `get_settings()` — no global mutable state.
5. Complex multi-value settings are parsed by dedicated helpers (`parse_ingest_clients`, `parse_workload_clients`, `parse_sources`, `_parse_service_clients`, etc.) that split comma-separated key=value pairs or JSON blobs.
6. Boolean flags use a consistent truthy set `{"1", "true", "yes", "on"}`; invalid booleans raise `ValueError`.
7. Invalid or malformed configuration fails fast during startup (e.g. `SettingsError` in skills-hub, `ValueError` on unknown provider).

There is no YAML/JSON config file loader inside services — files are only referenced as paths (e.g. `policy_path`, `workload_token_path`, `jwt_private_key_path`) and read at runtime by the feature that needs them.

## Key files and packages

- Per-service settings modules: `products/*/src/*_service/core/config.py` (platform-gateway, audit-service, tool-gateway, identity-broker, skills-hub) and `products/agent-platform/src/agent_service/runtime_settings.py`.
- Shared runtime env fragments mounted into every pod: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (OTel endpoint, shared `IDENTITY_SERVICE_URL`).
- Per-service non-secret env: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`.
- Per-service secret templates: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-secrets.example.env`.
- LLM backend profiles as Kustomize overlays: `shared/platform-ops/gitops/runtime-profiles/{openai,dashscope,deepseek}/configmap.yaml` + `runtime-secrets.example.env`.
- Policy bundle canonical source: `shared/shared-contracts/policies/policy-default.yaml`, synced to each gateway's `policies/policy-default.yaml` and mounted at `/etc/luban/policy/policy.yaml`.
- Provisioning scripts that generate secrets and wire cross-service contracts: `shared/platform-ops/gitops/sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`, `select-runtime-profile.sh`.
- Authoritative cross-service dependency map: `docs/guides/configuration-reference.md`.

## Architecture and conventions

### Layered configuration sources

| Layer | Where it lives | Purpose |
|---|---|---|
| Code defaults | frozen dataclass field defaults | Safe fallbacks when nothing is configured |
| Service `runtime-config.env` | per-service ConfigMap | Non-secret tuning (URLs, timeouts, feature toggles) |
| Shared `runtime.env` | single ConfigMap mounted into every pod | Cross-cutting concerns (OTel endpoint, identity broker URL) |
| Profile ConfigMaps | `runtime-profiles/<profile>/configmap.yaml` | Switch LLM provider/model/base-url without rebuilding images |
| Secrets (K8s Secret) | provisioned by `sync-*` scripts | API keys, client secrets, OIDC secrets, OTLP auth headers |
| Mounted files | paths read at runtime (policy YAML, JWT private key, projected SA token) | Large or binary config that cannot fit in env vars |

### Cross-service secret contracts

The configuration system enforces relationships between services through matching environment variables:

- **Token delegation**: `PLATFORM_GATEWAY_SERVICE_CLIENT_ID` / `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match an entry in `IDENTITY_SERVICE_CLIENTS` (`client_id:secret:audience1|audience2`); `PLATFORM_GATEWAY_DELEGATION_AUDIENCE` becomes the delegated token audience (default `tool-gateway`).
- **Audit ingestion**: each emitter's `*_AUDIT_CLIENT_ID` / `*_AUDIT_CLIENT_SECRET` must match an entry in `AUDIT_INGEST_CLIENTS` (`client_id=secret,...`). Unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing.
- **Skills query**: `GATEWAY_SKILLS_CLIENT_ID` / `GATEWAY_SKILLS_CLIENT_SECRET` must match `SKILLS_QUERY_CLIENTS` in skills-hub.
- **Identity verification**: `IDENTITY_TOKEN_ISSUER` and `IDENTITY_TOKEN_AUDIENCE` on consumers must match what identity-service emits; JWKS fetched from `IDENTITY_JWKS_URL`.
- **Workload identity**: `PLATFORM_GATEWAY_WORKLOAD_TOKEN_PATH` points to a projected Kubernetes SA token; `IDENTITY_WORKLOAD_ISSUER_URL` + `IDENTITY_WORKLOAD_CLIENTS` map `system:serviceaccount:<ns>:<sa>` subjects to registered clients.

### Runtime profiles

The agent-service supports pluggable LLM backends via Kustomize profile overlays. Only one profile is active at a time, selected by `select-runtime-profile.sh`. Profiles set `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`; secrets (API keys) are injected separately per profile.

### Policy configuration

Policy bundles are stored as YAML and consumed by both gateways. The canonical source is `shared/shared-contracts/policies/policy-default.yaml`; consumers keep byte-identical copies under their own `policies/policy-default.yaml`. Consumers load policy via the `policy_path` setting (default `/etc/luban/policy/policy.yaml`).

### Conventions and constraints

- **All settings are immutable**: dataclasses are declared `frozen=True`; settings are cached once via `lru_cache(maxsize=1)`.
- **Booleans are normalized**: accepted values are `1`, `true`, `yes`, `on` (case-insensitive); anything else raises an error.
- **Complex lists are comma-separated key=value pairs** (e.g. `AUDIT_INGEST_CLIENTS`, `AUDIT_WORKLOAD_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`, `SKILLS_QUERY_CLIENTS`) or JSON blobs (e.g. `SKILLS_SOURCES`, `SKILLS_GIT_TOKENS`).
- **Secrets are never committed**: every secret has a `.example.env` template; real values are generated by `sync-*` scripts and stored in K8s Secrets.
- **Feature toggling via presence**: many features activate when their required env var is set (e.g. unset `*_AUDIT_SERVICE_URL` disables durable audit; unset `GATEWAY_SKILLS_SERVICE_URL` disables skills tools; unset `OTEL_EXPORTER_OTLP_HEADERS` makes OTel push anonymous).
- **Fail-fast validation**: malformed settings raise exceptions at load time (`SettingsError`, `ValueError`) rather than failing later in request handling.
- **Cross-service documentation as enforcement**: `docs/guides/configuration-reference.md` documents every variable, its default, and its source; it is the authoritative contract used by operators.