---
kind: configuration_system
name: Environment-Driven Frozen Settings with Cross-Service Secret Contracts
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - docs/guides/configuration-reference.md
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml
---

# Configuration System

## What system/approach is used

Every service in the Luban platform uses a **pure environment-variable configuration model** built on Python `dataclasses` decorated with `@dataclass(frozen=True)`. There is no YAML/JSON config file loading at runtime; each service defines a single frozen settings class (e.g. `PlatformGatewaySettings`, `AuditSettings`, `IncidentSettings`, `SkillsSettings`, `IdentitySettings`, `GatewaySettings`, `RuntimeSettings`) and exposes a module-level `get_settings()` accessor cached via `functools.lru_cache(maxsize=1)`. The `from_env()` classmethod reads values from `os.getenv(...)` with explicit defaults, parses composite types (comma-separated lists, JSON blobs), and raises typed errors (`ValueError`, or per-service `SettingsError`) on invalid input — so misconfiguration fails fast at startup.

Configuration is delivered to pods through Kubernetes ConfigMaps and Secrets mounted as environment variables. Shared variables live in `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`; per-service overrides are in `<service>/runtime-config.env`; secrets are in `<service>/runtime-secrets.example.env` and provisioned by scripts under `shared/platform-ops/gitops/` (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`).

## Key files and packages

- Per-service configuration modules: `products/*/src/*_service/core/config.py` (and `agent_service/runtime_settings.py` for the agent kernel).
- Cross-service documentation of every variable and secret contract: `docs/guides/configuration-reference.md`.
- Kustomize overlays that mount env vars into pods: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` and `runtime-secrets.example.env`.
- Shared runtime variables: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`.
- Policy bundles consumed at runtime: `shared/shared-contracts/policies/policy-default.yaml` plus per-service copies under `products/*/policies/policy-default.yaml`.
- Runtime profile overlays for LLM provider selection: `shared/platform-ops/gitops/runtime-profiles/default/` and `mutating-dev/`.

## Architecture and conventions

### One frozen dataclass per service
Each service has exactly one frozen dataclass representing its complete configuration surface. Fields have sensible defaults so services start in a safe, minimal mode when only shared env is present. Boolean flags are parsed uniformly: `value.strip().lower() in {"1", "true", "yes", "on"}`. Integer/float fields use `int()`/`float()` wrappers around `os.getenv(..., default)`.

### Complex values are parsed inline
List-like and structured settings are parsed inside helper functions rather than delegated to a library:
- Comma-separated key=value pairs: `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`, `*_WORKLOAD_CLIENTS`.
- JSON blobs: `SKILLS_SOURCES` (list of source specs), `SKILLS_GIT_TOKENS` (map of source_id→token).
- Colon-delimited entries with optional sub-fields: `IDENTITY_SERVICE_CLIENTS` (`client_id:secret:aud1|aud2`), `IDENTITY_WORKLOAD_CLIENTS` (`subject=client_id:aud1|aud2`).

### Validation happens in `__post_init__` or during parsing
The agent-service `RuntimeSettings.__post_init__` enforces bounds (e.g. `max_iters >= 1`, `context_trigger_ratio` in `(0, 0.9)`, valid IANA timezone, matching `provider_options` type). Other services raise `SettingsError` during parsing of complex inputs (e.g. unknown skill source type, duplicate `source_id`, malformed JSON). This ensures invalid configuration is caught before any request is served.

### Global singleton access pattern
Every settings module exposes `get_settings()` wrapped in `@lru_cache(maxsize=1)`. Callers import this function rather than reading env directly, guaranteeing a single parsed instance per process lifetime.

### Secrets are never committed
Secrets live exclusively in Kubernetes `Secret` objects provisioned by shell scripts. Each service's `runtime-secrets.example.env` documents required keys but contains no real values. Scripts generate random shared secrets (or honor exported override variables like `DELEGATION_CLIENT_SECRET`, `AUDIT_INGEST_SECRET`, `SKILLS_GIT_TOKEN`) and write them into the appropriate `*-runtime-secrets` Secret.

### Cross-service secret contracts are explicit
The configuration reference documents paired secrets that must match across services:
- Token delegation: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry.
- Audit ingestion: each emitter's `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` entry.
- Skills query: `GATEWAY_SKILLS_CLIENT_SECRET` / `PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`.
- Incident query: `GATEWAY_INCIDENTS_CLIENT_SECRET` / `PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET` ↔ `INCIDENT_QUERY_CLIENTS`.
- Identity verification: `IDENTITY_TOKEN_ISSUER` / `IDENTITY_TOKEN_AUDIENCE` ↔ gateway `IDENTITY_*` settings + JWKS URL.

### Feature toggles are environment-driven
Capabilities activate when their required variables are set to non-empty values. Unset URLs disable features gracefully (e.g. unset `PLATFORM_GATEWAY_TOOL_GATEWAY_URL` makes the portal Tools route return 503; unset `GATEWAY_SKILLS_SERVICE_URL` leaves skills tools unregistered; unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing). Mutating tool execution requires multiple coordinated flags (`GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_K8S_ENABLED`, `AGENT_HITL_CONFIRM_TIMEOUT > 0`, policy grant `tools:mutate`, RBAC opt-in).

### Policy bundle is version-controlled and synced
The canonical policy lives in `shared/shared-contracts/policies/policy-default.yaml` and is validated against a JSON schema (`make validate-policy`) then copied byte-for-byte to consumer locations (`products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`). Consumers load it via the `*_POLICY_PATH` env var (default `/etc/luban/policy/policy.yaml`).

### Agent runtime profiles
The agent-service supports pluggable LLM backends via Kustomize profile overlays under `shared/platform-ops/gitops/runtime-profiles/`. Profiles are decoupled from providers (a generic `default` label hosts any configured provider). Provider selection is driven by `AGENTSCOPE_PROVIDER` plus per-provider keys (`DASHSCOPE_*`, `DEEPSEEK_*`, `OPENAI_*`, `LUBAN_*`). Live model discovery can be enabled to periodically refresh models from each provider's `/models` endpoint.

## Conventions and constraints

- **All configuration is read from environment variables.** No `.env` files, YAML configs, or TOML files are loaded at runtime by the services themselves.
- **Settings classes are frozen dataclasses.** Once constructed they cannot be mutated, making them safe to share across threads.
- **Boolean env vars accept `1`, `true`, `yes`, `on` (case-insensitive).** Any other value is treated as false.
- **Unknown store backends fail startup.** For example, an unrecognized `*_STORE_BACKEND` causes startup failure rather than silently falling back.
- **Cross-service secrets must match exactly.** The configuration reference treats mismatched client IDs/secrets as deployment failures; provisioning scripts enforce this by generating shared secrets once and distributing them consistently.
- **Feature gating is additive and fail-closed.** Missing configuration disables the feature (503, disabled connector, log-only audit) rather than crashing.
- **Policy files must stay byte-identical across all consumers.** The sync workflow (`make sync-policy`) enforces this convention.
- **OTel push is opt-in via `OTEL_ENABLED=true`** plus `OTEL_EXPORTER_OTLP_ENDPOINT`; authentication headers are injected per-service via runtime-secrets.