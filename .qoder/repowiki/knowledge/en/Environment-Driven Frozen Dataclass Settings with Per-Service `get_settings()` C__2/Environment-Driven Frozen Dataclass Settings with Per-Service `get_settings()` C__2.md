---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Per-Service `get_settings()` Caching
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - docs/guides/configuration-reference.md
---

## What system/approach is used

Every service in the platform loads configuration exclusively from **environment variables** via Python's `os.getenv`. There are no `.env` file loaders, no YAML/JSON config files read at startup, and no Pydantic `BaseSettings` usage. Each service defines a **frozen `dataclass` settings object** (e.g. `PlatformGatewaySettings`, `GatewaySettings`, `AuditSettings`, `IncidentSettings`, `ExecutionSettings`, `SkillsSettings`, `IdentitySettings`, `RuntimeSettings`) that holds typed defaults and exposes a classmethod `from_env()` that reads its environment variables. A module-level `@lru_cache(maxsize=1)` function named `get_settings()` returns the singleton instance, which callers import directly.

The agent-platform service splits its settings into two layers: `core/config.py` provides the cached `get_settings()` accessor, while `runtime_settings.py` defines the richer `RuntimeSettings` dataclass with provider-specific option sub-dataclasses (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) and extensive `__post_init__` validation.

## Key files and packages

- `products/agent-platform/src/agent_service/core/config.py` — cached `get_settings()` returning `RuntimeSettings`
- `products/agent-platform/src/agent_service/runtime_settings.py` — full `RuntimeSettings` dataclass, provider options, validation, per-provider env parsing
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings.from_env()`
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings.from_env()`
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings.from_env()` plus `parse_ingest_clients`, `parse_workload_clients`, `parse_positive_int`
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings.from_env()` plus `parse_query_clients`, `parse_workload_clients`, `parse_connectors`
- `products/execution-runtime/src/execution_runtime/core/config.py` — `ExecutionSettings.from_env()` with `__post_init__` validation
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings.from_env()` plus `parse_sources`, `parse_git_tokens`, `parse_query_clients`, `parse_workload_clients`
- `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings.from_env()` plus `_parse_service_clients`, `_parse_workload_clients`
- `docs/guides/configuration-reference.md` — authoritative cross-service environment variable reference, secret contracts, and dependency chain diagrams

## Architecture and conventions

### One frozen dataclass per service
Each service owns exactly one settings dataclass under `src/<service>/core/config.py`. The dataclass is `frozen=True`, so configuration is immutable after construction. Defaults are declared as class attributes; complex or optional fields use `field(default_factory=...)` for tuples/dicts.

### `from_env()` + `get_settings()` pattern
Every settings class implements `from_env()` that maps `os.getenv(<VAR>, <DEFAULT>)` to constructor arguments. A sibling `@lru_cache(maxsize=1) def get_settings() -> <Settings>` wraps it, giving callers a zero-overhead singleton. Services call `get_settings()` at import time or early in `main.py` to fail fast on bad configuration.

### Boolean parsing convention
Booleans are parsed by stripping whitespace and lowercasing, then checking membership in `{"1", "true", "yes", "on"}`. This is implemented inline in each service (e.g. `_TRUTHY = {"1", "true", "yes", "on"}` in tool-gateway, `_env_bool` helper) or via shared helpers in the agent-platform's `runtime_settings.py` (`_optional_bool`).

### Comma-separated list parsing
Multi-value settings (client registries, workload mappings, connectors) use a compact comma-delimited string format parsed in dedicated helpers:
- `client_id=secret,...` for ingest/query client registries (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`)
- `subject=client_id,...` for workload subject→client mapping (`*_WORKLOAD_CLIENTS`)
- `client_id:secret:aud1|aud2` for identity-service service clients (`IDENTITY_SERVICE_CLIENTS`)
- `subject=client_id:aud1|aud2` for identity-service workload clients (`IDENTITY_WORKLOAD_CLIENTS`)

### JSON-parsed structured lists
Complex nested configuration uses JSON strings parsed at load time with strict validation:
- `SKILLS_SOURCES` — JSON list of source entries validated against `SourceSpec` schema
- `SKILLS_GIT_TOKENS` — JSON map `source_id → token`
- Unknown types, duplicate IDs, malformed paths, and missing required fields raise `SettingsError` immediately.

### Validation strategy
Validation happens in two places:
1. `__post_init__` on the dataclass (used by `ExecutionSettings`, `RuntimeSettings`) — enforces numeric bounds, allowed backend enums, required field combinations (e.g. `postgres` backend requires `*_DB_URL`).
2. Parser functions raise typed exceptions (`ValueError`, `SettingsError`) when input is malformed (e.g. `parse_positive_int`, `parse_sources`).

### Secrets vs runtime config distinction
The documentation (`configuration-reference.md`) explicitly separates values sourced from ConfigMaps (`runtime-config.env`) versus Kubernetes Secrets (`*-runtime-secrets`). Secrets are never committed to Git and are provisioned by scripts under `shared/platform-ops/gitops/` (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-browser-credentials.sh`, `sync-otel-secrets.sh`).

### Cross-service contract via environment variables
Configuration is not just per-service; many variables form **contracts between services** that must match:
- Token delegation: `PLATFORM_GATEWAY_SERVICE_CLIENT_ID`/`SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry
- Audit ingestion: each emitter's `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` entry
- Skills query: `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS` entry
- Incident query: caller secrets ↔ `INCIDENT_QUERY_CLIENTS` entry
- Execution signing: `AGENT_EXECUTION_SIGNING_KEY` ↔ `EXECUTION_SIGNING_KEY`
- Execution handoff: `AGENT_EXECUTION_HANDOFF_TOKEN` ↔ `EXECUTION_HANDOFF_TOKEN`

These contracts are documented in `docs/guides/configuration-reference.md` with ASCII diagrams showing the dependency chains.

### Policy bundle configuration
Policy enforcement is configured via a file path (`GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH`) pointing to `shared/shared-contracts/policies/policy-default.yaml`, which is replicated byte-identically to both gateways' packaged defaults and the dev-k8s overlay. The canonical file is the single source of truth; consumers load it at startup and expose a SHA-256 fingerprint for provenance verification.

### Fail-closed posture
Missing or misconfigured critical secrets do not degrade silently. Missing execution signing keys fail mutating resumes closed (`signing_unavailable`), missing worker handoff tokens fail closed (`worker_unavailable`), unset incident/skills URLs fail routes with 503, and unknown store backends fail startup. Optional features like audit emission degrade to log-only when their URL is unset.

## Conventions and constraints

- **One settings dataclass per service**, frozen, with `from_env()` and a cached `get_settings()` accessor in `core/config.py`.
- **All configuration comes from `os.getenv`**; no `.env` files, no YAML/JSON config loading at startup, no Pydantic models.
- **Boolean env vars** accept only `1`, `true`, `yes`, `on` (case-insensitive, stripped).
- **Client registries** use `client_id=secret,...` comma-delimited format; workload mappings use `subject=client_id,...`.
- **Structured multi-value config** uses JSON strings parsed and strictly validated at load time (skills sources, git tokens).
- **Validation occurs in `__post_init__` or parser functions** and raises explicit exceptions to fail fast at startup.
- **Secrets are provisioned via K8s Secrets** managed by `sync-*` scripts under `shared/platform-ops/gitops/`; they are never embedded in code or committed to Git.
- **Cross-service contracts are enforced by matching environment variable pairs** documented in `configuration-reference.md` (delegation, audit, skills, incidents, execution signing/handoff).
- **Policy bundles live in a single canonical file** (`shared/shared-contracts/policies/policy-default.yaml`) and are replicated to consumers; drift is detected by `make verify`.
- **Store backends** follow a uniform `*_STORE_BACKEND` + `*_DB_URL` pattern (`memory` | `postgres`), with unknown values failing startup.