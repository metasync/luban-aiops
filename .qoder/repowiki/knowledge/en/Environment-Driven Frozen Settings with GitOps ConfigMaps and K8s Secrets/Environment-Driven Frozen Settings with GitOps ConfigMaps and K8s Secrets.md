---
kind: configuration_system
name: Environment-Driven Frozen Settings with GitOps ConfigMaps and K8s Secrets
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/agent-platform/src/agent_platform/runtime_settings.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/shared-contracts/policies/policy-default.yaml
    - docs/guides/configuration-reference.md
---

## What system/approach is used

Luban uses a **12-factor environment-variable configuration** model. Each Python service defines its own frozen `dataclass` settings object in `src/<service>/core/config.py`, loaded exclusively from `os.getenv(...)` via a `from_env()` classmethod, and exposed through an `@lru_cache(maxsize=1)` `get_settings()` accessor. There are no YAML/JSON config files consumed at runtime by the services themselves; configuration is injected as Kubernetes environment variables (via ConfigMaps) and secrets (via Secrets). Policy bundles are the only exception — they are read from disk paths (`PLATFORM_GATEWAY_POLICY_PATH`, `GATEWAY_POLICY_PATH`) mounted into pods.

The agent-platform's `agent_service/core/config.py` is a thin shim that delegates to `RuntimeSettings.from_env()` defined in `agent_platform/runtime_settings.py`, which consumes `AGENTSCOPE_*` provider knobs plus session/state store backends.

## Key files and packages

- Per-service settings modules: `products/*/src/*_service/core/config.py` (and `agent_platform/runtime_settings.py`).
- GitOps overlays under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` define the per-service environment variable sets.
- Shared shared-environment: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (OTel endpoint, identity broker URL).
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`.
- Authoritative cross-service dependency map: `docs/guides/configuration-reference.md`.
- Policy bundle source: `shared/shared-contracts/policies/policy-default.yaml`, mirrored into each gateway's `policies/` directory and the dev overlay's `shared/policy.yaml`.

## Architecture and conventions

### Frozen dataclass + cached singleton
Every service follows the same pattern:
- A `@dataclass(frozen=True)` named `<Service>Settings` with typed defaults.
- A `classmethod from_env(cls)` that reads every field from `os.getenv(key, default)`, parsing booleans via `.strip().lower() in {"1","true","yes","on"}` and complex values via dedicated parsers (e.g. `parse_ingest_clients`, `parse_sources`, `_parse_service_clients`).
- An `@lru_cache(maxsize=1)` `get_settings()` returning the singleton instance.

This makes settings immutable after process start and guarantees one load per container.

### Environment variable naming convention
Variables are scoped per service using a prefix matching the service name:
- `PLATFORM_GATEWAY_*` for platform-gateway
- `GATEWAY_*` for tool-gateway
- `AUDIT_*` for audit-service
- `SKILLS_*` for skills-hub
- `INCIDENT_*` for incident-service
- `IDENTITY_*` for identity-broker
- `AGENTSCOPE_*` / `AGENT_*` for agent-platform
- `OTEL_*` for all pods

Cross-service URLs use plain names like `IDENTITY_SERVICE_URL`, `AGENT_SERVICE_URL`, `TOOL_GATEWAY_URL`, `INCIDENT_AGENT_SERVICE_URL` so callers can be configured independently of their own namespace.

### Complex value formats
Multi-value settings use compact string encodings parsed at startup:
- Comma-separated key=value pairs: `AUDIT_INGEST_CLIENTS`, `AUDIT_WORKLOAD_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`, `IDENTITY_WORKLOAD_CLIENTS`.
- JSON lists/maps: `SKILLS_SOURCES` (list of `{source_id,type,path,url,ref}`), `SKILLS_GIT_TOKENS` (map `source_id→token`).
- Colon-pipe delimited audience lists: `client_id:secret:aud1|aud2`.

Validation is strict — malformed values raise `SettingsError` or fail fast during `from_env()` rather than silently degrading.

### Secrets vs non-secret configuration
Non-secret runtime knobs live in per-service `runtime-config.env` files (ConfigMaps). Sensitive material lives in per-service `*-runtime-secrets` Kubernetes Secrets provisioned by `sync-*` scripts. The reference doc explicitly marks which variables come from "runtime-config" vs "runtime-secrets".

### Policy-as-code
Policy bundles are YAML files validated against a JSON schema (`make validate-policy`) and synchronized across consumers (`make sync-policy`). Consumers mount them at fixed paths (`/etc/luban/policy/policy.yaml`) and read them at startup. The canonical source is `shared/shared-contracts/policies/policy-default.yaml`.

### Runtime profiles (agent-platform)
The agent-service supports pluggable LLM providers via Kustomize profile overlays under `shared/platform-ops/gitops/runtime-profiles/<profile>/`. Profiles select the active provider/model through `AGENTSCOPE_*` env vars and optionally inject provider-specific keys via `runtime-secrets.example.env`. Switching is done with `select-runtime-profile.sh <profile-name>`.

### Cross-service secret contracts
Configuration is not just per-service — many features require coordinated secrets across services:
- **Token delegation**: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry must match.
- **Audit trail**: each emitter's `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` entry.
- **Skills hub**: `GATEWAY_SKILLS_CLIENT_SECRET` / `PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS` entries.
- **Incidents**: `PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET` / `GATEWAY_INCIDENTS_CLIENT_SECRET` ↔ `INCIDENT_QUERY_CLIENTS` entries.
- **OpenTelemetry**: `OTEL_EXPORTER_OTLP_HEADERS` provisioned into every service's runtime-secrets.

These contracts are documented in `docs/guides/configuration-reference.md` with diagrams showing the chains.

## Conventions and constraints

- **No runtime config reload**: settings are loaded once at process start; changes require redeploy.
- **Fail-fast on bad config**: boolean parsing rejects unknown strings; JSON/list parsers raise `SettingsError`; unknown `store_backend` values cause startup failure.
- **Defaults are safe**: most optional integrations (audit, skills, incidents, elastic) default to disabled/unset, making deployments work without extra secrets.
- **Feature flags are explicit**: enabling mutating tools requires multiple coordinated flags (`GATEWAY_MUTATING_TOOLS_ENABLED=true`, `GATEWAY_K8S_ENABLED=true`, policy grant `tools:mutate`, RBAC, `AGENT_HITL_CONFIRM_TIMEOUT>0`) — no single toggle activates risky behavior.
- **Workload identity is opt-in**: projected SA token support (`*_WORKLOAD_ISSUER_URL`, `*_WORKLOAD_CLIENTS`) is disabled by default and must be explicitly configured per service.
- **Shared env is centralized**: common variables (`OTEL_*`, `IDENTITY_SERVICE_URL`) live in `base/shared/runtime.env` and are applied to every pod.
- **Secrets are never committed**: all sensitive values are generated by `sync-*` scripts and stored only in K8s Secrets.