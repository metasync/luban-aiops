---
kind: configuration_system
name: Environment-Driven Per-Service Settings with Frozen Dataclass Profiles and GitOps Secret Provisioning
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - docs/guides/configuration-reference.md
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/deploy-overlay.sh
    - shared/platform-ops/gitops/select-runtime-profile.sh
---

## What system/approach is used

The platform uses a **per-service, environment-variable-driven configuration system** built on Python `dataclasses` with frozen instances. Each service defines its own settings class in a `core/config.py` (or equivalent) module under `products/<service>/src/<service>/core/`. There is no shared configuration library — each service independently reads `os.environ`, parses values, validates them, and exposes a cached singleton via `functools.lru_cache(maxsize=1)`.

Configuration is loaded at import time through a `get_settings()` function that calls a `Settings.from_env()` classmethod. The dataclass defaults encode the documented defaults; `from_env()` overrides them from environment variables. Validation happens in `__post_init__` (for services like agent-platform's `RuntimeSettings`) or during parsing helpers (`parse_sources`, `parse_ingest_clients`, etc.), so invalid configuration fails startup rather than runtime.

Secrets are never committed to Git. They are provisioned into Kubernetes `Secret` objects by scripts under `shared/platform-ops/gitops/` (e.g. `sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-runtime-secret.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`). Service deployments mount these as env vars via Kustomize overlays under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` and per-service `*-runtime-secrets` Secrets.

## Key files and packages

- `products/agent-platform/src/agent_service/runtime_settings.py` — largest settings object; covers LLM provider selection (`AGENTSCOPE_PROVIDER`), model catalog, kernel tuning, HITL bridging, evidence persistence caps, isolated execution worker handoff, and audit emission. Uses typed helper functions `_optional_str/_int/_float/_bool/_choice` for robust parsing.
- `products/platform-gateway/src/platform_gateway/core/config.py` — gateway-to-service URLs, identity/JWKS endpoints, delegation audience, policy path, portal proxy URLs.
- `products/tool-gateway/src/tool_gateway/core/config.py` — identity verification, policy path, feature flags (`GATEWAY_K8S_ENABLED`, `GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_REDACTION_ENABLED`), Elastic connector config, audit/skills/incidents client credentials.
- `products/audit-service/src/audit_service/core/config.py` — store backend, retention, ingest/workload client registries parsed from comma-separated `client_id=secret` lists.
- `products/skills-hub/src/skills_hub/core/config.py` — federated skill sources (`SKILLS_SOURCES` JSON list of `{source_id,type,path,url,ref}`), git tokens map, query client registry.
- `products/incident-service/src/incident_service/core/config.py` — webhook token, query clients, connectors, triage timeout.
- `products/execution-runtime/src/execution_runtime/core/config.py` — signing key, handoff token, tool-gateway URL, state store backend, audit emission.
- `docs/guides/configuration-reference.md` — authoritative cross-service dependency map, secret contracts, provisioning scripts, and per-service variable tables.
- `shared/shared-contracts/policies/policy-default.yaml` — canonical policy bundle synced to all consumers.
- `shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env` — per-service ConfigMap env var defaults.

## Architecture and conventions

1. **Per-service frozen dataclass settings**: Every service defines one primary `*Settings` dataclass (e.g. `PlatformGatewaySettings`, `AuditSettings`, `ExecutionSettings`, `SkillsSettings`, `IncidentSettings`, `RuntimeSettings`) decorated with `@dataclass(frozen=True)`. This makes settings immutable after construction and signals they are process-scoped singletons.

2. **Environment-only loading**: All configuration comes from `os.getenv(...)`. No `.env` file loader, no YAML/JSON config file reader for runtime settings (policy bundles are the exception — loaded from a file path configured via `*_POLICY_PATH`).

3. **Cached singleton accessor**: Each settings module exposes `@lru_cache(maxsize=1) def get_settings() -> *Settings`, so callers import once and reuse the same instance.

4. **Strict validation on load**: Invalid values raise exceptions during `from_env()` / `__post_init__`:
   - Unknown store backends raise `ValueError` (execution-runtime, skills-hub, incident-service).
   - Boolean parsing rejects non-boolean strings.
   - Choice fields validate against allowed sets (e.g. `AGENTSCOPE_PROVIDER` must be one of `dashscope|deepseek|openai|luban`).
   - IANA timezone names are validated via `zoneinfo.ZoneInfo`.
   - Numeric bounds enforced (e.g. `max_iters >= 1`, `context_trigger_ratio` in `(0, 0.9)`, `model_discovery_refresh_seconds >= 1`).

5. **Cross-service credential registries**: Services expose their own client registries via comma-separated env vars:
   - `AUDIT_INGEST_CLIENTS` — `client_id=secret,...`
   - `SKILLS_QUERY_CLIENTS` — `client_id=secret,...`
   - `INCIDENT_QUERY_CLIENTS` — `client_id=secret,...`
   - `IDENTITY_SERVICE_CLIENTS` — `client_id:client_secret:audience1|audience2`
   Consumers declare matching `*_CLIENT_ID` / `*_CLIENT_SECRET` env vars; mismatches fail at the receiving service's auth layer.

6. **Fail-closed vs fail-open features**: Optional integrations degrade gracefully when unset:
   - Unset `*_AUDIT_SERVICE_URL` → log-only auditing (never blocks requests).
   - Unset `PLATFORM_GATEWAY_TOOL_GATEWAY_URL` / `PLATFORM_GATEWAY_SKILLS_HUB_URL` → portal routes return 503.
   - Unset `TOOL_GATEWAY_URL` in agent-service → tools unregistered.
   - Missing `AGENT_EXECUTION_SIGNING_KEY` / `AGENT_EXECUTION_WORKER_URL` → mutating resumes fail closed with audited rejections (`signing_unavailable`, `worker_unavailable`).

7. **Policy bundles as deploy-time artifacts**: Policy is not an env var — it is a YAML file whose canonical source is `shared/shared-contracts/policies/policy-default.yaml`, synced to consumer locations via `make sync-policy`. Consumers read it from a path set by `*_POLICY_PATH`.

8. **Runtime profiles for agent-service**: LLM provider selection is driven by `AGENTSCOPE_PROVIDER` plus profile-specific ConfigMaps under `shared/platform-ops/gitops/runtime-profiles/`. A script `select-runtime-profile.sh` switches the active profile.

## Conventions and constraints

- **Naming convention**: Environment variables follow `<SERVICE>_<FEATURE>_<OPTION>` (e.g. `PLATFORM_GATEWAY_POLICY_PATH`, `GATEWAY_ELASTIC_URL`, `AGENTSCOPE_MAX_ITERS`). Cross-cutting options use shorter prefixes (`OTEL_*`, `IDENTITY_*`).
- **Boolean parsing**: Booleans accept `1|true|yes|on` (case-insensitive) and reject other strings. Some services parse booleans inline; agent-platform centralizes this in `_optional_bool`.
- **Secrets live in K8s Secrets only**: The reference document explicitly states "Secrets are provisioned as Kubernetes Secret objects, never committed to Git." Runtime secrets are mounted into pods via `secretKeyRef` or env-from Secret.
- **Provisioning via scripts**: Cross-service secret synchronization is centralized in `shared/platform-ops/gitops/` scripts. Running `make deploy` invokes these scripts to generate random secrets and write K8s Secrets. Individual scripts support opt-out via `SKIP_*_SECRETS=true`.
- **Store backends**: Persistent storage is selected via `*_STORE_BACKEND` (`memory` | `postgres`) with corresponding `*_DB_URL`. Unknown values fail startup.
- **Feature toggles**: Features are enabled by setting explicit env vars to truthy values (e.g. `GATEWAY_K8S_ENABLED=true`, `GATEWAY_MUTATING_TOOLS_ENABLED=true`, `AGENT_MODEL_DISCOVERY_ENABLED=true`). Defaults are conservative (most optional features disabled).
- **Documentation as contract**: `docs/guides/configuration-reference.md` is treated as the authoritative specification — every service's settings module references SPEC numbers (e.g. `SPEC-013 R-2`, `SPEC-038 R-1`) and the reference doc mirrors those requirements verbatim.