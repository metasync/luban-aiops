---
kind: configuration_system
name: Environment-Driven Frozen Settings with Kustomize Runtime Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/mutating.env
    - shared/platform-ops/gitops/deploy-overlay.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-sessions-db.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
    - shared/shared-contracts/policies/policy-default.yaml
---

## Overview

Every Luban service loads configuration exclusively from **environment variables** at process startup into **frozen `dataclass` settings objects**, cached via `functools.lru_cache(maxsize=1)` behind a module-level `get_settings()` accessor. There is no runtime reload: changing a ConfigMap or Secret requires restarting the pod so the next `from_env()` call re-parses values.

## Per-service settings modules

Each product under `products/` exposes its own frozen settings class in `src/<service>/core/config.py` (or, for the agent platform, `src/agent_service/runtime_settings.py` plus a thin `core/config.py` wrapper):

| Service | Settings class | Key env prefixes / examples |
|---|---|---|
| Agent Platform (AgentService) | `RuntimeSettings` (`runtime_settings.py`) | `AGENTSCOPE_*`, `AGENT_*`, `TOOL_GATEWAY_URL`, `AGENT_EXECUTION_SIGNING_KEY`, `AGENT_AUDIT_*` |
| Platform Gateway | `PlatformGatewaySettings` | `PLATFORM_GATEWAY_*`, `IDENTITY_*`, `CHAT_RESPONSE_TIMEOUT_SECONDS` |
| Tool Gateway | `GatewaySettings` | `GATEWAY_*`, `IDENTITY_*`, `GATEWAY_ELASTIC_*`, `GATEWAY_AUDIT_*` |
| Audit Service | `AuditSettings` | `AUDIT_*` (`AUDIT_STORE_BACKEND`, `AUDIT_DB_URL`, `AUDIT_INGEST_CLIENTS`, `AUDIT_WORKLOAD_*`, `AUDIT_RETENTION_DAYS`) |
| Incident Service | `IncidentSettings` | `INCIDENT_*` (`INCIDENT_STORE_BACKEND`, `INCIDENT_DB_URL`, `INCIDENT_QUERY_CLIENTS`, `INCIDENT_CONNECTORS`) |
| Skills Hub | `SkillsSettings` | `SKILLS_*` (`SKILLS_SOURCES`, `SKILLS_GIT_TOKENS`, `SKILLS_STORE_BACKEND`, `SKILLS_DB_URL`, `SKILLS_QUERY_CLIENTS`) |
| Execution Runtime | `ExecutionSettings` | `EXECUTION_*`, `TOOL_GATEWAY_URL`, `EXECUTION_STATE_DB_URL` |

All classes are `@dataclass(frozen=True)` and expose a `classmethod from_env(cls)` that reads `os.getenv(...)` with typed defaults, then a module-level `@lru_cache(maxsize=1) get_settings()` returns the singleton.

## Parsing conventions

* **Booleans** are parsed case-insensitively against `{"1", "true", "yes", "on"}`; unset or anything else is `False`.
* **Integers / floats** use `int()` / `float()` on the env value with a string default.
* **Tuples of key=value pairs** (e.g. `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`) are split on `,` then partitioned on `=`.
* **Complex structures** use JSON: `SKILLS_SOURCES` is a JSON list of source dicts; `SKILLS_GIT_TOKENS` is a JSON map `source_id -> token`; `INCIDENT_CONNECTORS` is a comma-separated list of connector names.
* **Optional fields** use a helper `_optional_str/int/float/bool` pattern that treats empty strings as `None`.
* **Validation** happens in `__post_init__` (agent platform) or during parsing — malformed values raise `ValueError` or a service-specific `SettingsError`, causing startup failure rather than silent misconfiguration.

## Kubernetes delivery: ConfigMaps + Secrets + Kustomize overlays

Configuration is delivered to pods through two layers:

1. **Non-secret knobs** go into a shared `platform-runtime-config` ConfigMap built from `shared/platform-ops/gitops/runtime-profiles/<profile>/configmap.yaml`. The default profile sets `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`.
2. **Secrets** (API keys, client secrets, DB URLs, OTLP headers) are written into per-service `<service>-runtime-secrets` Kubernetes Secrets by scripts under `shared/platform-ops/gitops/sync-*.sh` (`sync-audit-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-sessions-db.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-delegation-secrets.sh`, `sync-otel-secrets.sh`). These scripts upsert lines into a local `*-runtime-secrets.env` file and mirror them into the cluster secret.
3. **Profile overlays** (e.g. `mutating-dev/mutating.env` setting `GATEWAY_MUTATING_TOOLS_ENABLED=true`) are merged into the base ConfigMap via Kustomize to switch feature flags per environment.
4. A `deploy-overlay.sh` script watches for changes to `platform-runtime-config` / `platform-policy` ConfigMaps and restarts app deployments so services pick up new settings.

The example secret template `shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env` documents every supported provider key (`AGENTSCOPE_API_KEY`, `DASHSCOPE_*`, `OPENAI_*`, `LUBAN_*`) and notes which ones are provisioned by sync scripts versus committed locally.

## Policy configuration

Policy files are separate from runtime config but follow the same delivery pattern:
* Each gateway/service has a `policy_path` setting read from env (`PLATFORM_GATEWAY_POLICY_PATH`, `GATEWAY_POLICY_PATH`).
* Default policy bundles live in `shared/shared-contracts/policies/policy-default.yaml` and `products/*/policies/policy-default.yaml`.
* The platform gateway also loads a YAML-driven RBAC matrix from `src/platform_gateway/services/policy_matrix.py`.

## Cross-cutting patterns

* **Fail-fast startup**: invalid env values raise exceptions before any request handling starts.
* **No hot-reload**: settings are immutable once loaded; deployment restart is required to apply changes.
* **Per-service isolation**: each service defines its own frozen dataclass; there is no shared settings library across products.
* **Default-safe**: every field has a sensible default so services start without all env vars set; missing credentials simply disable optional integrations (e.g. unset `audit_service_url` keeps log-only behavior).
* **Spec references**: docstrings frequently cite SPEC numbers (SPEC-013, SPEC-014, SPEC-015, SPEC-017, SPEC-018, SPEC-020, SPEC-025, SPEC-026, SPEC-027, SPEC-028, SPEC-037, SPEC-038) tying settings to requirements.