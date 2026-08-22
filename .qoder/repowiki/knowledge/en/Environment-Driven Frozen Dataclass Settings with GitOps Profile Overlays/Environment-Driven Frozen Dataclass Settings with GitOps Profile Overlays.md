---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with GitOps Profile Overlays
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
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - docs/guides/configuration-reference.md
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/deepseek/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/mutating.env
---

# Configuration System

## What system/approach is used

Every microservice in the platform implements a **pure environment-variable configuration layer** built on Python `dataclasses` decorated with `@dataclass(frozen=True)`. Each service exposes a single `Settings` dataclass (e.g. `PlatformGatewaySettings`, `AuditSettings`, `SkillsSettings`, `IncidentSettings`, `GatewaySettings`, `IdentitySettings`, `RuntimeSettings`) that:

1. Declares every configurable field with a sensible default.
2. Provides a classmethod `from_env()` that reads values from `os.getenv(...)` and parses them into typed fields.
3. Exposes a module-level `get_settings()` function wrapped with `functools.lru_cache(maxsize=1)` so settings are loaded once at process start and reused throughout the request lifecycle.
4. Performs validation in `__post_init__` (for `RuntimeSettings`) or via dedicated parser helpers (`parse_sources`, `parse_query_clients`, `_parse_service_clients`, etc.) to fail fast at startup rather than later in a request.

Complex multi-value settings use compact string formats parsed at load time:
- Comma-separated key=value pairs for client registries: `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `AUDIT_WORKLOAD_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`, `IDENTITY_WORKLOAD_CLIENTS`.
- JSON strings for structured lists/maps: `SKILLS_SOURCES` (list of source specs), `SKILLS_GIT_TOKENS` (source_id→token map).
- Boolean flags accept `"true"|"false"|"yes"|"no"|"on"|"off"|"1"|"0"` after `.strip().lower()`.

There is no YAML/JSON config file loading inside services — configuration files live exclusively in the deployment layer (see below). The agent-service additionally supports Kustomize runtime profiles under `shared/platform-ops/gitops/runtime-profiles/<profile>/configmap.yaml` that inject `AGENTSCOPE_*` variables to select LLM provider, model, base URL, and API key.

## Key files and packages

- Per-service settings modules: `products/*/src/*_service/core/config.py` plus `products/agent-platform/src/agent_service/runtime_settings.py`.
- Cross-service configuration reference: `docs/guides/configuration-reference.md` — the authoritative matrix of which env vars activate which features, cross-service dependency chains, secret contracts, and per-service variable tables.
- Runtime profile overlays: `shared/platform-ops/gitops/runtime-profiles/{dashscope,deepseek,openai}/configmap.yaml` and `mutating-dev/mutating.env`.
- Policy bundles consumed by gateways: `shared/shared-contracts/policies/policy-default.yaml` (canonical), mirrored into `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml` and `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, mounted at `GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH`.
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`, `select-runtime-profile.sh`.

## Architecture and conventions

### One setting object per service
Each service has exactly one frozen dataclass representing its complete configuration surface. Consumers never call `os.getenv` directly; they call `get_settings()` from `core.config` (or `runtime_settings.get_settings()` for the agent-service). This centralizes parsing, defaults, and validation.

### Fail-fast startup validation
Invalid configuration raises exceptions during `from_env()` / `__post_init__`:
- `SettingsError` (skills-hub, incident-service) for malformed complex settings like `SKILLS_SOURCES` or `INCIDENT_CONNECTORS`.
- `ValueError` (agent-service `RuntimeSettings`) for out-of-range kernel tuning knobs, invalid IANA timezone, mismatched `AGENTSCOPE_PROFILE` vs `AGENTSCOPE_PROVIDER`, unsupported provider names, negative token budgets, etc.
- Unknown store backends (`SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND`, `INCIDENT_STORE_BACKEND`) cause startup failure.

### Feature toggles via empty-or-set convention
Many capabilities are opt-in by leaving an env var unset:
- `*_AUDIT_SERVICE_URL` unset → log-only auditing (never blocks requests).
- `PLATFORM_GATEWAY_TOOL_GATEWAY_URL` / `PLATFORM_GATEWAY_SKILLS_HUB_URL` unset → portal routes return 503.
- `GATEWAY_SKILLS_SERVICE_URL` unset → skills connector stays unregistered.
- `GATEWAY_INCIDENTS_SERVICE_URL` unset → incident tools unregistered.
- `INCIDENT_WEBHOOK_TOKEN` empty → intake disabled (503).
- `AGENT_HITL_CONFIRM_TIMEOUT=0` disables HITL bridging and excludes mutating tools from the toolkit.

### Cross-service secret contracts
Configuration is not just per-service env vars — it defines **contracts between services** enforced by provisioning scripts:
- Token delegation: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match the `platform-gateway` entry in `IDENTITY_SERVICE_CLIENTS`; `PLATFORM_GATEWAY_DELEGATION_AUDIENCE` becomes the delegated token audience.
- Audit ingestion: each emitter's `*_AUDIT_CLIENT_SECRET` must match its `*_AUDIT_CLIENT_ID` entry in `AUDIT_INGEST_CLIENTS`.
- Skills query: `GATEWAY_SKILLS_CLIENT_SECRET` and `PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET` must both match their respective entries in `SKILLS_QUERY_CLIENTS`.
- Incident query: `PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET` and `GATEWAY_INCIDENTS_CLIENT_SECRET` must match `platform-gateway` / `tool-gateway` entries in `INCIDENT_QUERY_CLIENTS`.

These contracts are generated centrally by `sync-*-secrets.sh` scripts invoked from `make deploy`, ensuring consistency across all consumers.

### Policy as immutable config artifact
Policy enforcement uses a single canonical YAML (`shared/shared-contracts/policies/policy-default.yaml`) copied verbatim into each consumer and mounted into pods at `policy_path`. Changes require running `make validate-policy` against the JSON schema then `make sync-policy` to propagate byte-identical copies.

### GitOps-driven overlay composition
Runtime configuration is composed via Kustomize overlays under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` and `runtime-profiles/<profile>/configmap.yaml`. Operators switch LLM backends by running `select-runtime-profile.sh <profile>`; dev-specific toggles (e.g. `mutating-dev/mutating.env`) are layered on top. Secrets are injected via separate Kubernetes `Secret` objects provisioned by the `sync-*` scripts — never committed to Git.

## Conventions and constraints

- **All settings are read-only after construction**: every `Settings` dataclass is `frozen=True`; callers cannot mutate runtime configuration.
- **Single global instance**: `get_settings()` is cached with `lru_cache(maxsize=1)`; reloading requires process restart.
- **Boolean parsing is uniform**: values are stripped, lowercased, and matched against `{"1", "true", "yes", "on"}` for truthy.
- **Multi-value lists use comma-delimited key=value pairs** with optional trailing segments (e.g. `client_id:secret:aud1|aud2` for identity clients, `subject=client_id:aud1|aud2` for workload clients).
- **Structured lists/maps use JSON strings** and are validated at parse time, raising `SettingsError` on malformed input.
- **Store backends are enumerated**: only known values (`memory`, `postgres`, `redis` where supported) are accepted; unknown values fail startup.
- **Cross-service secrets are never inline**: they are provisioned into Kubernetes `Secret` objects by the `sync-*` scripts and referenced via env var names documented in `configuration-reference.md`.
- **Feature activation follows a deny-by-default pattern**: capabilities like mutating tools, Elastic connectors, OIDC workload identity, and policy enforcement are disabled unless explicitly enabled via env vars.
- **Policy files must stay byte-identical** across all consumer locations; the build enforces this through the sync workflow.