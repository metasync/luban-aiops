---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Kustomize Profiles and Secret Sync Scripts
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - docs/guides/configuration-reference.md
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/openai/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/shared-contracts/policies/policy-default.yaml
---

# Configuration System

## What system/approach is used

Every Python microservice in the platform implements a **12-factor-style environment-variable configuration** backed by `@dataclass(frozen=True)` settings classes. There is no shared configuration library — each service defines its own `core/config.py` (or equivalent) that:

1. Declares a frozen dataclass holding all runtime knobs with sensible defaults.
2. Exposes a `from_env()` classmethod that reads values from `os.getenv(...)` and parses them into typed fields.
3. Exposes a module-level `get_settings()` function decorated with `functools.lru_cache(maxsize=1)` so settings are loaded once at process start and reused everywhere.
4. Raises `ValueError` / `SettingsError` during `__post_init__` or parsing to fail fast on malformed configuration rather than deferring errors to runtime.

The agent-service is slightly different: its settings live in `agent_service/runtime_settings.py` as `RuntimeSettings`, consumed via `agent_service/core/config.py` which simply calls `RuntimeSettings.from_env()` through an `lru_cache`-cached `get_settings()`.

Configuration is delivered to pods through two Kubernetes layers:
- **ConfigMaps** for non-secret runtime knobs, mounted as env files (`runtime-config.env`) per service under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`.
- **Kubernetes Secrets** for sensitive values (API keys, client secrets, OTLP headers), provisioned by dedicated shell scripts under `shared/platform-ops/gitops/sync-*.sh` and mounted into each pod's secret volume.

LLM provider selection uses **Kustomize runtime profiles** under `shared/platform-ops/gitops/runtime-profiles/<profile>/configmap.yaml` (e.g. `openai`, `dashscope`, `deepseek`). Each profile sets `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`; only one profile overlay is active at a time, selected via `select-runtime-profile.sh`.

Policy bundles are a separate but related configuration concern: the canonical source is `shared/shared-contracts/policies/policy-default.yaml`, validated against a JSON schema (`make validate-policy`) and synced to every consumer location (`products/*/policies/policy-default.yaml` plus `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`) via `make sync-policy`.

## Key files and packages

- Per-service settings modules:
  - `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` with provider-specific option subtypes (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) and validation.
  - `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings`.
  - `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings`.
  - `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings` with `ServiceClient` / `WorkloadClient` registries.
  - `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` with `IngestClient` / `WorkloadClient` registries.
  - `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` with `QueryClient` / `WorkloadClient` registries.
  - `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` with `SourceSpec`, `QueryClient`, `WorkloadClient` and strict JSON-based federation config parsing.
- Deployment manifests and env sources:
  - `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service non-secret env vars.
  - `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared variables like `OTEL_*` and `IDENTITY_SERVICE_URL`.
  - `shared/platform-ops/gitops/runtime-profiles/<profile>/configmap.yaml` — LLM profile ConfigMaps.
- Secret provisioning scripts:
  - `shared/platform-ops/gitops/sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`, `sync-sessions-db.sh`, `sync-runtime-secret.sh`.
- Documentation:
  - `docs/guides/configuration-reference.md` — authoritative cross-service variable dependency map, secret contracts, and per-service tables.

## Architecture and conventions

### Frozen dataclass + lru_cache pattern
Every service follows the same shape: a frozen dataclass with default values, a `from_env()` parser, and an `lru_cache(maxsize=1)`-decorated `get_settings()`. This makes settings immutable after load and guarantees single initialization per process.

### Boolean parsing convention
Boolean flags accept `"1"`, `"true"`, `"yes"`, `"on"` (case-insensitive) as truthy; most services implement this inline in `from_env()` using `.strip().lower() in {"1", "true", "yes", "on"}`. The agent-service centralizes this in `_optional_bool()` helpers that also raise `ValueError` for unrecognized boolean strings.

### Typed complex-value parsers
Multi-valued configuration is parsed from comma-separated or JSON strings into tuples of small frozen dataclasses:
- `AUDIT_INGEST_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `SKILLS_QUERY_CLIENTS`: `client_id=secret,...` → tuple of `*Client` records.
- `*_WORKLOAD_CLIENTS`: `subject=client_id,...` → workload subject-to-client mappings.
- `IDENTITY_SERVICE_CLIENTS`: `client_id:secret:aud1|aud2,...` with optional audience allow-lists.
- `SKILLS_SOURCES`: JSON list of `{source_id, type, url?, path?, ref?}` with strict validation (regex on `source_id`, duplicate detection, relative-path checks).
- `SKILLS_GIT_TOKENS`: JSON map `source_id → token`.

Parsing failures raise `SettingsError` (skills-hub, incident-service) or `ValueError` (agent-service) at startup, never silently.

### Cross-service secret contracts
Secrets are never committed to Git. They are created by `sync-*.sh` scripts that either generate random values or read from exported variables, then write matching pairs into the relevant K8s Secrets. Examples:
- Token delegation: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match the `platform-gateway` entry in `IDENTITY_SERVICE_CLIENTS`.
- Audit ingestion: each emitter's `*_AUDIT_CLIENT_SECRET` must match the corresponding `client_id=secret` in `AUDIT_INGEST_CLIENTS`.
- Skills query: `GATEWAY_SKILLS_CLIENT_SECRET` and `PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET` must both be registered under `SKILLS_QUERY_CLIENTS`.
- Incident query: `PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET` and `GATEWAY_INCIDENTS_CLIENT_SECRET` must match entries in `INCIDENT_QUERY_CLIENTS`.

### Feature gating via empty URLs
Many features are opt-in by leaving their URL unset: if `PLATFORM_GATEWAY_TOOL_GATEWAY_URL`, `PLATFORM_GATEWAY_SKILLS_HUB_URL`, `GATEWAY_SKILLS_SERVICE_URL`, `GATEWAY_INCIDENTS_SERVICE_URL`, or `*_AUDIT_SERVICE_URL` are empty, the corresponding route/connector stays disabled and returns 503 or falls back to log-only behavior. This lets deployments compose capabilities without dead dependencies.

### Policy-as-code
Policy bundles are maintained as YAML under `shared/shared-contracts/policies/policy-default.yaml`, validated against a JSON schema, and copied byte-for-byte to every consumer. Consumers read policy via a `policy_path` setting (e.g. `GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH`) pointing to `/etc/luban/policy/policy.yaml`.

### Runtime profiles
The agent-service supports pluggable LLM providers via Kustomize overlays. Each profile under `shared/platform-ops/gitops/runtime-profiles/<name>/` provides a ConfigMap that sets `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`. Only one profile is active per deployment, switched with `select-runtime-profile.sh`.

## Conventions and constraints

- **All configuration is environment-driven.** No `.env` files are read at runtime; values come from Kubernetes ConfigMaps and Secrets injected as environment variables.
- **Settings are immutable and cached.** The `lru_cache(maxsize=1)` on `get_settings()` means settings cannot be reloaded at runtime; changes require a pod restart.
- **Malformed configuration fails fast.** Invalid booleans, out-of-range numeric values, unknown store backends, invalid IANA timezones, and malformed JSON federation configs raise exceptions during `from_env()` / `__post_init__`, preventing misconfigured processes from starting.
- **Store backends are chosen by string:** `memory` | `postgres` (unknown values fail startup). Default is `memory` except in dev-k8s where Postgres is configured.
- **Secrets are provisioned exclusively via scripts.** The `sync-*.sh` scripts under `shared/platform-ops/gitops/` are the single source of truth for creating K8s Secrets; they are invoked by `make deploy`.
- **Cross-service credentials are paired, not self-describing.** A caller's `*_CLIENT_ID` / `*_CLIENT_SECRET` must be manually mirrored in the callee's registry (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`). There is no auto-discovery.
- **Policy files must stay byte-identical across consumers.** The `make sync-policy` target enforces this contract documented in `configuration-reference.md`.
- **Feature toggles follow a consistent naming scheme:** `<SERVICE>_FEATURE_ENABLED` (e.g. `GATEWAY_K8S_ENABLED`, `GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_REDACTION_ENABLED`, `GATEWAY_ELASTIC_ENABLED`, `PLATFORM_GATEWAY_REQUIRE_AUTH`).
- **OIDC/workload identity is opt-in:** `*_WORKLOAD_ISSUER_URL` and `*_WORKLOAD_CLIENTS` are empty by default, disabling projected-token authentication unless explicitly configured.