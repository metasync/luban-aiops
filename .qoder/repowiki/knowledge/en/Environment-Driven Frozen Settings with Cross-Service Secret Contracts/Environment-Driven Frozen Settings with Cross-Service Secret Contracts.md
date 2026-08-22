---
kind: configuration_system
name: Environment-Driven Frozen Settings with Cross-Service Secret Contracts
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - docs/guides/configuration-reference.md
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/deepseek/configmap.yaml
---

# Configuration System

## What system/approach is used

The platform uses a **pure environment-variable configuration model** — every service reads its settings exclusively from `os.getenv` at startup, wraps them in frozen `dataclass` objects, and exposes them via an `lru_cache(maxsize=1)` singleton `get_settings()` accessor. There are no `.env` file loaders, YAML/JSON config files read by the application code, or runtime reloadable configuration. Configuration is injected into pods through Kubernetes ConfigMaps (non-secret knobs) and Secrets (credentials), mounted as environment variables.

A small exception is the agent-platform's `RuntimeSettings`, which also supports Kustomize "runtime profiles" — per-provider ConfigMaps (`shared/platform-ops/gitops/runtime-profiles/<provider>/configmap.yaml`) that set `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`. A shell helper (`select-runtime-profile.sh`) swaps the active profile ConfigMap to switch LLM backends without rebuilding images.

Policy bundles are the only non-env configuration artifact consumed at runtime: each gateway loads a YAML policy file from a path given by `*_POLICY_PATH` (`/etc/luban/policy/policy.yaml` by default). The canonical source is `shared/shared-contracts/policies/policy-default.yaml`; consumers maintain byte-identical copies synced via `make sync-policy`.

## Key files and packages

- Per-service settings modules under `products/<service>/src/<service>/core/config.py`:
  - `audit_service/core/config.py` → `AuditSettings`
  - `identity_service/core/config.py` → `IdentitySettings`
  - `incident_service/core/config.py` → `IncidentSettings`
  - `platform_gateway/core/config.py` → `PlatformGatewaySettings`
  - `tool_gateway/core/config.py` → `GatewaySettings`
  - `skills_hub/core/config.py` → `SkillsSettings`
- Agent-platform provider-specific settings: `agent_platform/src/agent_service/runtime_settings.py` → `RuntimeSettings` (with nested `DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`)
- Shared documentation of all env vars and cross-service contracts: `docs/guides/configuration-reference.md`
- Runtime profile overlays: `shared/platform-ops/gitops/runtime-profiles/{dashscope,deepseek,openai}/configmap.yaml`
- Policy defaults: `shared/shared-contracts/policies/policy-default.yaml` plus copies under each gateway's `policies/` directory
- GitOps secret provisioning scripts: `shared/platform-ops/gitops/sync-*-secrets.sh` (e.g. `sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`)

## Architecture and conventions

### Per-service frozen dataclasses
Each service defines one frozen `@dataclass` holding all its settings, with a classmethod `from_env()` that maps `os.getenv(<VAR>, <DEFAULT>)` to fields. Complex multi-value settings are parsed by dedicated helpers (e.g. `parse_ingest_clients`, `parse_query_clients`, `parse_workload_clients`, `parse_sources`, `parse_connectors`). Boolean flags are normalized via the same pattern: `.strip().lower() in {"1", "true", "yes", "on"}`. Choices are validated against a whitelist using `_optional_choice(name, supported_set)`.

### Global singleton accessor
Every settings module exposes `@lru_cache(maxsize=1) def get_settings()` so callers import once and receive the same instance for the process lifetime. This is the single point where environment is materialized.

### Fail-fast validation
Validation happens in `__post_init__` or during parsing, raising `ValueError` / `SettingsError` at import/startup time rather than failing later. Examples include:
- `RuntimeSettings.__post_init__`: enforces `profile == provider`, `max_iters >= 1`, `context_trigger_ratio ∈ (0, 0.9)`, valid IANA timezone, matching `provider_options` type.
- `SkillsSettings.parse_sources`: rejects unknown types, duplicate `source_id`, malformed JSON, git paths containing `..` or starting with `/`.
- Incident/audit/skills services raise `SettingsError` on malformed `*_CLIENTS` entries.

### Environment variable naming convention
Variables follow `<SERVICE_PREFIX>_` + descriptive name, scoped per service:
- `AGENTSCOPE_*` for agent-platform runtime options
- `PLATFORM_GATEWAY_*` for the platform gateway
- `GATEWAY_*` for tool-gateway
- `AUDIT_*`, `SKILLS_*`, `INCIDENT_*`, `IDENTITY_*` for their respective services
- Cross-cutting shared variables live in `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (e.g. `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `IDENTITY_SERVICE_URL`)

### Cross-service secret contracts
Configuration is not isolated per service; many secrets must match across service boundaries. The `configuration-reference.md` documents these as explicit chains:
- **Token delegation**: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry `platform-gateway:<secret>:tool-gateway`
- **Audit ingestion**: each emitter's `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` entry `<client_id>=<secret>`
- **Skills query**: `GATEWAY_SKILLS_CLIENT_SECRET` / `PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`
- **Incidents query**: `PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET` / `GATEWAY_INCIDENTS_CLIENT_SECRET` ↔ `INCIDENT_QUERY_CLIENTS`
- **Identity verification**: `IDENTITY_TOKEN_ISSUER` / `IDENTITY_TOKEN_AUDIENCE` ↔ consumer `*_TOKEN_ISSUER` / `*_TOKEN_AUDIENCE` + JWKS URL

Secrets are provisioned via `make deploy` calling `sync-*-secrets.sh` scripts that generate random values (or reuse exported overrides) and create per-service Kubernetes `Secret` objects — never committed to Git.

### Feature activation matrix
Capabilities are toggled purely by setting specific environment variables to truthy values. The reference table in `configuration-reference.md` enumerates required variables per capability (chat/sessions, portal auth, token delegation, K8s tools, mutating tools, Elastic observability, output redaction, policy enforcement, OTel push, LLM runtime, workload identity, audit trail, skills, incidents).

### Policy-as-code
Policy bundles are YAML files loaded from disk via `*_POLICY_PATH`. They are version-controlled centrally and copied verbatim to each consumer. Validation is enforced via `make validate-policy` against a JSON schema in `shared/shared-contracts/scripts/validate_policy.py`.

## Conventions and constraints

- **No runtime reload**: settings are read once at import time and cached; changing env vars requires a process restart.
- **Defaults are safe**: every field has a sensible default; unset optional features (audit, skills, incidents, elastic, mutating tools) remain disabled unless explicitly enabled.
- **Unknown store backends fail startup**: e.g. `SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND`, `INCIDENT_STORE_BACKEND` reject unknown values.
- **Boolean normalization is uniform**: all boolean env vars accept `1|true|yes|on` (case-insensitive); false accepts `0|false|no|off`.
- **Multi-value lists use comma-separated key=value pairs**: `*_CLIENTS` entries use `client_id=secret,...` (ingest/query) or `subject=client_id,...` (workload mapping); identity broker additionally supports `client_id:secret:aud1|aud2` format.
- **Complex configs use JSON strings**: `SKILLS_SOURCES` (list of source specs) and `SKILLS_GIT_TOKENS` (map of source_id→token) are passed as JSON-encoded environment variables and parsed at startup with strict validation.
- **Cross-boundary secrets are provisioned together**: related secrets for a feature are generated and applied atomically by a single `sync-*` script (e.g. `sync-delegation-secrets.sh` creates both the gateway and identity-broker secrets).
- **Profiles override provider settings**: selecting a runtime profile sets `AGENTSCOPE_PROFILE`/`AGENTSCOPE_PROVIDER`/`AGENTSCOPE_MODEL_NAME`/`AGENTSCOPE_BASE_URL` via a ConfigMap overlay; `RuntimeSettings.from_env` validates that `profile` matches `provider`.
- **Policy files must stay byte-identical** across all consumer locations; `make sync-policy` enforces this contract.