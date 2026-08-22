---
kind: configuration_system
name: Environment-Driven Frozen Settings with GitOps Secret Separation
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/audit_service/src/audit_service/core/config.py
    - products/identity_service/src/identity_service/core/config.py
    - products/incident_service/src/incident_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-secrets.example.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env
    - shared/platform-ops/gitops/dev-k8s/base/incident-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/incident-service/runtime-secrets.example.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env
    - shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env
---

## What system/approach is used

Every Python service in the platform follows a uniform, zero-dependency configuration pattern: frozen `dataclass` settings objects loaded exclusively from environment variables via `os.getenv`, wrapped in an `@lru_cache(maxsize=1)` singleton accessor (`get_settings()`). There is no YAML/JSON config loader at runtime — configuration is purely env-driven, with defaults baked into the dataclass field values and parsed/composed in `from_env()`. Complex multi-value settings (client registries, workload mappings) are parsed from comma-delimited strings by small helper functions inside each service's `core/config.py`.

The agent-platform runtime additionally validates settings in `__post_init__` (range checks, type matching between `AGENTSCOPE_PROVIDER` and `provider_options`, IANA timezone validation), failing startup on misconfiguration rather than deferring errors.

## Key files and packages

- Per-service settings modules under `products/<service>/src/<service>/core/config.py`:
  - `platform_gateway/core/config.py` → `PlatformGatewaySettings`
  - `audit_service/core/config.py` → `AuditSettings` (+ `IngestClient`, `WorkloadClient`) with `parse_ingest_clients` / `parse_workload_clients`
  - `identity_service/core/config.py` → `IdentitySettings` (+ `ServiceClient`, `WorkloadClient`) with `_parse_service_clients` / `_parse_workload_clients`
  - `incident_service/core/config.py` → `IncidentSettings` (+ `QueryClient`, `WorkloadClient`) with `parse_query_clients` / `parse_workload_clients` / `parse_connectors`
  - `agent_platform/src/agent_service/runtime_settings.py` → `RuntimeSettings` (provider-specific options for dashscope/deepseek/openai)
  - `agent_platform/src/agent_service/core/config.py` thin re-export of `RuntimeSettings.get_settings()`
- GitOps deployment assets under `shared/platform-ops/gitops/dev-k8s/base/<service>/`:
  - `runtime-config.env` — non-secret per-environment knobs (URLs, feature flags, DB URLs, policy paths)
  - `runtime-secrets.example.env` — secret contract template (never committed; real values provisioned by `sync-*-secrets.sh` scripts)
  - Deployment manifests reference both files (ConfigMap + optional Secret volume mounts)
- Shared secrets provisioning scripts: `shared/platform-ops/gitops/sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`, `sync-delegation-secrets.sh`

## Architecture and conventions

### One frozen settings object per service
Each service defines exactly one frozen dataclass (`*Settings`) whose fields map 1:1 to environment variables. Defaults provide sane behavior when a variable is unset. The `from_env()` classmethod reads every field via `os.getenv(key, default)`, performing only lightweight coercion (`int`, `float`, boolean normalization via `{"1","true","yes","on"}`).

### Cached singleton accessor
A module-level `@lru_cache(maxsize=1)` function named `get_settings()` returns the same instance for the process lifetime. Consumers import `get_settings` rather than calling `from_env()` directly, ensuring single initialization.

### Two-tier env separation: config vs secrets
- **Non-secret runtime config** lives in `runtime-config.env` files and is mounted as a ConfigMap or plain env block. These contain URLs, feature toggles (`GATEWAY_MUTATING_TOOLS_ENABLED`, `PLATFORM_GATEWAY_REQUIRE_AUTH`), store backends (`AUDIT_STORE_BACKEND=postgres`), DB URLs, policy paths, and connector lists.
- **Secrets** live in `runtime-secrets.example.env` templates and are materialized by `sync-*-secrets.sh` scripts into per-deployment Kubernetes Secrets (`*-runtime-secrets`). Examples: `IDENTITY_SERVICE_CLIENTS`, `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `OTEL_EXPORTER_OTLP_HEADERS`, `*_CLIENT_SECRET` fields.

### Cross-service credential registry pattern
Services expose a shared client registry via a comma-separated env var that consumers must mirror on the server side:
- `IDENTITY_SERVICE_CLIENTS=client_id:secret:aud1|aud2` (identity-broker)
- `AUDIT_INGEST_CLIENTS=client_id=secret,...` (audit-service)
- `SKILLS_QUERY_CLIENTS=client_id=secret,...` (skills-hub)
- `INCIDENT_QUERY_CLIENTS=client_id=secret,...` (incident-service)

The `runtime-secrets.example.env` comments explicitly document this cross-reference contract (e.g., "`PLATFORM_GATEWAY_AUDIT_CLIENT_SECRET` must match the secret registered for client id 'platform-gateway' in the audit-service's `AUDIT_INGEST_CLIENTS` registry").

### Workload identity support
Several services accept projected-token subjects via `*_WORKLOAD_ISSUER_URL`, `*_WORKLOAD_AUDIENCE`, and `*_WORKLOAD_CLIENTS` (comma list of `subject=client_id[:aud1|aud2]`), enabling Kubernetes ServiceAccount-based auth alongside static client secrets. The identity broker also supports `IDENTITY_WORKLOAD_CLIENTS` mapping SA subjects to registered clients.

### Feature-flag style booleans
Boolean env vars are normalized case-insensitively against `{"1","true","yes","on"}` (and the inverse set for false). This is applied consistently across `PLATFORM_GATEWAY_REQUIRE_AUTH`, `GATEWAY_REQUIRE_AUTH`, `GATEWAY_K8S_ENABLED`, `GATEWAY_ELASTIC_ENABLED`, `GATEWAY_MUTATING_TOOLS_ENABLED`, `AGENTSCOPE_KERNEL_TRACING`, etc.

### Policy files as path references
Policy enforcement is configured by setting `*_POLICY_PATH` (e.g., `PLATFORM_GATEWAY_POLICY_PATH=/etc/luban/policy/policy.yaml`, `GATEWAY_POLICY_PATH=/etc/luban/policy/policy.yaml`) pointing to a YAML file mounted into the pod. Default policy bundles live in `policies/policy-default.yaml` next to each gateway's code.

### Agent runtime provider profiles
The agent platform uses `AGENTSCOPE_PROFILE` (constrained to `dashscope`/`deepseek`/`openai`) which must match `AGENTSCOPE_PROVIDER`; mismatch raises a startup error. Provider-specific knobs (`DASHSCOPE_*`, `DEEPSEEK_*`, `OPENAI_*`) are read conditionally based on the selected provider.

## Conventions and constraints

- **All runtime configuration comes from environment variables.** No `.env` file parsing, no YAML/JSON config loading at application start. Configuration is immutable after construction (frozen dataclasses).
- **Defaults are safe:** every field has a sensible default so services start without any env vars (though many features like DBs, OIDC, and inter-service auth require explicit configuration).
- **Malformed settings fail fast:** `RuntimeSettings.__post_init__` raises `ValueError` for out-of-range kernel tuning values, invalid timezones, provider/options mismatches, and unsupported providers. `IncidentSettings` defines a `SettingsError` exception type for malformed `INCIDENT_*` settings.
- **Cross-service secrets are coordinated by sync scripts, not committed.** Each `runtime-secrets.example.env` header instructs operators to copy it to `runtime-secrets.env` (never committed) or run the corresponding `sync-*-secrets.sh` script, which generates a shared secret and writes all per-service `runtime-secrets.env` files.
- **Comma-delimited multi-value settings use consistent parsers:** `client_id=secret,...` for client registries, `subject=client_id[:aud1|aud2],...` for workload mappings, `client_id:secret:aud1|aud2,...` for identity broker service clients.
- **Optional OTel headers are opt-in:** `OTEL_EXPORTER_OTLP_HEADERS` is commented out by default in every `runtime-secrets.example.env`; when unset exporters fall open without affecting the service.
- **Feature gates are explicit:** mutating tools, elastic connectors, kernel tracing, task tools, HITL bridging, and other capabilities are disabled by default and require explicit env var activation plus matching RBAC/policy changes.