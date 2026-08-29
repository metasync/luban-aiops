---
kind: configuration_system
name: Environment-Driven Frozen Settings with Per-Service Config Modules and GitOps Secret Sync
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - docs/guides/configuration-reference.md
---

## What system/approach is used

The Luban AIOps platform uses a **pure environment-variable configuration system** built on Python `dataclasses` with frozen instances, loaded at process startup via a single `from_env()` classmethod per service. There are no `.env` files read by the application code, no YAML/JSON config files parsed at runtime (policy bundles are mounted as files but are not runtime settings), and no framework like Pydantic or dynaconf — just stdlib `os.getenv` plus small helper parsers for comma-separated lists and JSON blobs. Each service exposes a `core/config.py` (or `runtime_settings.py` for agent-platform) that defines a frozen dataclass of settings, a `get_settings()` function cached via `functools.lru_cache(maxsize=1)`, and a `from_env()` constructor that reads every setting from an environment variable.

Configuration is layered through Kubernetes: each service has a `runtime-config.env` file under `shared/platform-ops/gitops/dev-k8s/base/<service>/` that provides non-secret defaults (URLs, feature flags, timeouts), and a separate `runtime-secrets.env` / `*-secrets.example.env` file for sensitive values (client secrets, API keys, webhook tokens). The `sync-*.sh` scripts in `shared/platform-ops/gitops/` generate shared secrets (e.g. one random `AUDIT_INGEST_SECRET`) and upsert them into the appropriate `runtime-secrets.env` files, then apply them as Kubernetes Secrets and restart affected deployments.

## Key files and packages

- Per-service settings modules:
  - `products/platform-gateway/src/platform_gateway/core/config.py` → `PlatformGatewaySettings`
  - `products/tool-gateway/src/tool_gateway/core/config.py` → `GatewaySettings`
  - `products/audit-service/src/audit_service/core/config.py` → `AuditSettings` (+ `IngestClient`, `WorkloadClient`)
  - `products/incident-service/src/incident_service/core/config.py` → `IncidentSettings` (+ `QueryClient`, `WorkloadClient`)
  - `products/skills-hub/src/skills_hub/core/config.py` → `SkillsSettings` (+ `SourceSpec`, `QueryClient`, `WorkloadClient`)
  - `products/execution-runtime/src/execution_runtime/core/config.py` → `ExecutionSettings`
  - `products/agent-platform/src/agent_service/runtime_settings.py` → `RuntimeSettings` (+ provider-specific option dataclasses)
  - `products/agent-platform/src/agent_service/core/config.py` → thin re-export of `RuntimeSettings.get_settings()`
- Kustomize overlays and env files:
  - `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` (non-secret defaults)
  - `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-secrets.example.env` (secret templates)
  - `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (shared variables like `OTEL_*`, `IDENTITY_SERVICE_URL`)
- Secret provisioning scripts:
  - `shared/platform-ops/gitops/sync-audit-secrets.sh` (single shared audit ingest secret across all emitters)
  - `shared/platform-ops/gitops/sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-otel-secrets.sh`
- Authoritative cross-service dependency map: `docs/guides/configuration-reference.md` (documents every variable, default, source, and cross-service contract).

## Architecture and conventions

1. **Frozen dataclass + `from_env()` + `lru_cache` singleton**: Every service follows the same three-part pattern. `from_env()` reads only environment variables; `__post_init__` performs validation (e.g. `EXECUTION_STATE_STORE_BACKEND` must be `memory` or `postgres`, `AGENTSCOPE_TIMEZONE` must be a valid IANA zone, boolean fields accept `1|true|yes|on`). `get_settings()` wraps the instance in `@lru_cache(maxsize=1)` so callers import it once and get a stable reference.
2. **Per-service environment variable prefixes**: Variables are namespaced by service to avoid collisions: `PLATFORM_GATEWAY_*`, `GATEWAY_*`, `AUDIT_*`, `INCIDENT_*`, `SKILLS_*`, `EXECUTION_*`, `AGENTSCOPE_*` / `AGENT_*`. Cross-cutting variables live in `base/shared/runtime.env` (`OTEL_*`, `IDENTITY_SERVICE_URL`).
3. **Boolean parsing convention**: All boolean knobs are parsed via `value.strip().lower() in {"1", "true", "yes", "on"}` (or a shared `_optional_bool` helper in agent-platform), so `true`, `True`, `1`, `yes`, `on` all enable a flag.
4. **Optional secrets degrade gracefully**: Missing secrets never fail startup. Unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing; unset `TOOL_GATEWAY_URL` leaves skills tools unregistered; unset `AGENT_EXECUTION_SIGNING_KEY` fails mutating resumes closed (`signing_unavailable`); unset `AGENT_EXECUTION_WORKER_URL`+`AGENT_EXECUTION_HANDOFF_TOKEN` fails closed (`worker_unavailable`). This is enforced by the code paths, not just documented.
5. **Complex multi-value configs use delimited strings**: Comma-separated `client_id=secret,...` lists are parsed by helpers like `parse_ingest_clients`, `parse_query_clients`, `parse_workload_clients`; JSON blobs are used for structured data (`SKILLS_SOURCES`, `SKILLS_GIT_TOKENS`). Unknown types, duplicate IDs, malformed JSON, or missing required fields raise `SettingsError` at parse time (fail-fast).
6. **Policy bundles are separate from runtime settings**: Policy YAML lives under `policies/policy-default.yaml` and is mounted as a file path (`GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH`); it is validated against a JSON schema and synced across consumers via `make validate-policy` / `make sync-policy`.
7. **Secrets are provisioned by scripts, never committed**: `runtime-secrets.env` files contain placeholders or examples; real values are generated by `sync-*.sh` scripts and applied as Kubernetes Secrets. Scripts preserve previously provisioned keys (e.g. OTLP headers) when rewriting files.

## Conventions and constraints

- **Every setting has a default in the dataclass**; `from_env()` only overrides when the corresponding environment variable is set. This makes services startable with minimal configuration.
- **Startup validation rejects invalid values**: Invalid store backends, out-of-range timeouts, unsupported providers, unknown policy types, and malformed JSON all raise exceptions during `from_env()` / `__post_init__`, failing fast before any request is served.
- **Cross-service contracts are explicit and bidirectional**: e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match the `platform-gateway` entry in `IDENTITY_SERVICE_CLIENTS`; `*_AUDIT_CLIENT_SECRET` must match the client id in `AUDIT_INGEST_CLIENTS`; `GATEWAY_SKILLS_CLIENT_SECRET` must match the `tool-gateway` entry in `SKILLS_QUERY_CLIENTS`. These are enforced at runtime by the receiving service's credential registry.
- **Feature toggles are opt-in via environment variables**: Mutating tools require `GATEWAY_MUTATING_TOOLS_ENABLED=true` AND `tools:mutate` policy grant AND RBAC; HITL bridging requires `AGENT_HITL_CONFIRM_TIMEOUT > 0`; Elastic observability requires `GATEWAY_ELASTIC_ENABLED=true` plus URL/auth. No feature is implicitly enabled.
- **The canonical configuration reference is documentation, not code**: `docs/guides/configuration-reference.md` is the authoritative source of truth for every variable, its default, where it comes from, and how it interacts with other services. It is maintained alongside the code changes.