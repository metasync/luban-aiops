---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Cross-Service Secret Contracts
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - docs/guides/configuration-reference.md
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
---

## What system/approach is used

Every service in the monorepo implements configuration through a uniform pattern: a `frozen` Python `dataclass` named `<Service>Settings` (e.g. `PlatformGatewaySettings`, `AuditSettings`, `ExecutionSettings`, `IncidentSettings`, `SkillsSettings`, `GatewaySettings`, `RuntimeSettings`) lives under `products/<service>/src/<service>/core/config.py`. Each settings class exposes a `from_env()` classmethod that reads values from environment variables via `os.getenv(...)` and a module-level `@lru_cache(maxsize=1) get_settings()` accessor that consumers call at runtime. There are no YAML/JSON/TOML config files loaded by the services at startup — configuration is purely environment-driven.

The agent-service (`agent-platform`) is the most complex, loading LLM provider options (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) dynamically based on `AGENTSCOPE_PROVIDER`, plus kernel tuning knobs, HITL bridging, evidence persistence caps, live model discovery, isolated execution worker handoff, and audit emission settings.

Configuration values are injected into pods via Kustomize overlays under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` (non-secret env) and per-service `runtime-secrets.example.env` / generated secrets mounted as Kubernetes Secrets. A single shared `shared/runtime.env` provides cross-cutting values like `OTEL_*` and `IDENTITY_SERVICE_URL`.

## Key files and packages

- `products/*/src/*/core/config.py` — one frozen dataclass + `from_env()` + cached `get_settings()` per service
- `products/agent-platform/src/agent_service/runtime_settings.py` — agent-service's richer settings with provider option parsing and validation
- `docs/guides/configuration-reference.md` — authoritative cross-service environment variable map, dependency chains, secret contracts, and per-service tables
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — non-secret defaults for each pod
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-secrets.example.env` — secret key names (values provisioned by scripts)
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared env across all pods
- `shared/platform-ops/gitops/*.sh` — secret provisioning scripts (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-otel-secrets.sh`)
- `shared/shared-contracts/policies/policy-default.yaml` — canonical policy bundle consumed by gateway services via `*_POLICY_PATH`

## Architecture and conventions

**Per-service frozen settings objects.** Each service defines its own `Settings` dataclass with sensible defaults. Values are parsed from environment variables in `from_env()`, then validated in `__post_init__` (e.g. `ExecutionSettings` rejects unknown store backends or missing Postgres URL; `RuntimeSettings` validates kernel tuning bounds, IANA timezone, provider/options type matching). Unknown backend types fail startup rather than silently defaulting.

**Cached singleton access.** Every settings module exports `@lru_cache(maxsize=1) get_settings()` so callers (FastAPI routes, app startup) import once and reuse the same instance. This avoids re-parsing env vars on every request.

**Secrets vs config separation.** Non-sensitive configuration goes in `runtime-config.env` ConfigMaps; sensitive values go in per-service `*-runtime-secrets` Kubernetes Secrets. The reference doc documents which keys live where and how they are provisioned by `make deploy`-invoked sync scripts.

**Cross-service secret contracts.** Configuration is not just per-service — many features require matching pairs of secrets across services:
- Token delegation: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry
- Audit ingestion: each emitter's `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` registry
- Skills query: `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`; portal uses `PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET` ↔ same registry
- Incident query: `PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET` / `GATEWAY_INCIDENTS_CLIENT_SECRET` ↔ `INCIDENT_QUERY_CLIENTS`
- Execution signing/handoff: `AGENT_EXECUTION_SIGNING_KEY` ↔ `EXECUTION_SIGNING_KEY`; `AGENT_EXECUTION_HANDOFF_TOKEN` ↔ `EXECUTION_HANDOFF_TOKEN`

**Feature flags via env booleans.** Boolean toggles accept `true/false/yes/no/1/0/on/off` after `.strip().lower()`. Features are disabled by default unless explicitly enabled (e.g. `GATEWAY_MUTATING_TOOLS_ENABLED=false`, `GATEWAY_ELASTIC_ENABLED=false`, `AGENTSCOPE_KERNEL_TRACING=False`).

**Fail-closed vs degrade-to-log.** Missing optional secrets never crash the process — they cause feature-specific failure modes: unset `*_AUDIT_SERVICE_URL` degrades to log-only auditing; unset `TOOL_GATEWAY_URL` means tool tools are unregistered; unset `AGENT_EXECUTION_WORKER_URL` fails mutating resumes with an audited `worker_unavailable` rejection; unset `AGENT_EXECUTION_SIGNING_KEY` fails with `signing_unavailable`. Only required configuration (e.g. unknown store backend, invalid numeric bounds) raises during `__post_init__`.

**Policy-as-code.** Policy bundles are YAML files (`policy-default.yaml`) maintained as a single source under `shared/shared-contracts/policies/` and synced to consumer locations. Consumers load them via `*_POLICY_PATH` env var (default `/etc/luban/policy/policy.yaml`). Validation is enforced via `make validate-policy` against a JSON schema.

## Conventions and constraints

- **One settings file per service** under `core/config.py` with a frozen dataclass, `from_env()`, and cached `get_settings()` — observed consistently across all seven services.
- **Environment variable naming**: service-scoped prefixes (`AGENTSCOPE_*`, `PLATFORM_GATEWAY_*`, `GATEWAY_*`, `AUDIT_*`, `SKILLS_*`, `INCIDENT_*`, `EXECUTION_*`) keep variables namespace-safe across the cluster.
- **Store backends are enumerated**: `memory`/`postgres` (sometimes `redis` for sessions) are the only accepted values; unknown values raise at startup.
- **Comma-separated lists use `key=value,key=value` tuples** parsed by helper functions (`parse_ingest_clients`, `parse_query_clients`, `parse_workload_clients`, `parse_connectors`), producing immutable tuples of typed sub-dataclasses.
- **Complex multi-value configs use JSON env vars** (e.g. `SKILLS_SOURCES` as a JSON list of `{source_id, type, url, ref, path}` entries; `SKILLS_GIT_TOKENS` as a JSON map `source_id→token`). Parsing failures raise `SettingsError` at startup.
- **Provider options are dynamic**: `RuntimeSettings._provider_options_from_env` selects the correct options dataclass based on `AGENTSCOPE_PROVIDER`, validating the choice against `SUPPORTED_RUNTIME_PROVIDERS = ("dashscope", "deepseek", "openai", "luban")`.
- **Defaults mirror production posture**: booleans default to secure/disabled (`require_auth=true`, `mutating_tools_enabled=false`, `redaction_enabled=true`, `model_discovery_enabled=True`); opt-in features must be explicitly enabled.
- **Secret provisioning is script-gated**: cross-service secrets are created by `sync-*.sh` scripts invoked from `make deploy`; exporting `SKIP_*_SECRETS=true` opts out of specific provisioning steps.
- **Policy files must stay byte-identical** across consumer locations (`tool-gateway`, `platform-gateway`, dev-k8s overlay) — enforced by the sync workflow documented in the configuration reference.