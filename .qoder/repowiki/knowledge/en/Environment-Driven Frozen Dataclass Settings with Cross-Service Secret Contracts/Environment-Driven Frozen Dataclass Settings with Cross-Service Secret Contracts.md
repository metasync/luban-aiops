---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Cross-Service Secret Contracts
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
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/shared-contracts/policies/policy-default.yaml
---

# Configuration System

## What system/approach is used

Each service in the platform implements its own configuration layer using **Python `dataclasses` decorated as frozen**, loaded exclusively from **environment variables** via `os.getenv`. There is no YAML/JSON config file loading at runtime (policy bundles are separate). A module-level `@lru_cache(maxsize=1)`-wrapped `get_settings()` function provides a singleton settings object per process. The agent-platform additionally uses a richer `RuntimeSettings` class in `runtime_settings.py` that parses provider-specific options and performs validation in `__post_init__`.

Configuration values are injected into pods through Kustomize overlays under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`, while secrets live in per-service `*-runtime-secrets` Kubernetes Secrets provisioned by scripts such as `sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, and `sync-otel-secrets.sh`. A single authoritative cross-service variable map lives in `docs/guides/configuration-reference.md`.

## Key files and packages

- `products/agent-platform/src/agent_service/runtime_settings.py` — full runtime settings for the agent kernel, including LLM provider options, kernel tuning, HITL timeout, evidence caps, and typed boolean/int/float/choice parsers.
- `products/agent-platform/src/agent_service/core/config.py` — thin `get_settings()` cache returning `RuntimeSettings.from_env()`.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` dataclass with defaults and `from_env()` mapping `PLATFORM_GATEWAY_*`, `AGENT_SERVICE_URL`, `IDENTITY_*`, audit/incident/skills URLs.
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` dataclass covering K8s/Elastic/redaction/connectors/audit/skills/incidents.
- `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings` with OIDC/Keycloak knobs, service client registry (`IDENTITY_SERVICE_CLIENTS`), workload identity mappings, and audit integration.
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` with `AUDIT_STORE_BACKEND`, `AUDIT_DB_URL`, `AUDIT_INGEST_CLIENTS`, workload identity, retention/eviction knobs.
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` with JSON-parsed `SKILLS_SOURCES` (source_id/type/path/url/ref), `SKILLS_GIT_TOKENS`, query/workload client registries.
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` with webhook token, query/workload clients, store backends, connectors, and audit connector.
- `docs/guides/configuration-reference.md` — definitive cross-service environment variable dependency map, secret contracts, feature activation matrix, and per-service tables.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service ConfigMap env vars.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared OTLP endpoint and identity broker URL.
- `shared/shared-contracts/policies/policy-default.yaml` + `products/*/policies/policy-default.yaml` — policy bundle (separate concern, consumed via `*_POLICY_PATH`).

## Architecture and conventions

1. **Per-service frozen dataclass**: Every service defines a single frozen `*Settings` dataclass whose fields are the configuration surface. Defaults encode sensible dev behavior; production overrides come from env.
2. **Env-only loading**: `from_env()` reads every field via `os.getenv(key, default)`. Complex types (booleans, tuples, JSON lists/maps) are parsed inside dedicated helper functions (`parse_ingest_clients`, `parse_workload_clients`, `parse_sources`, `parse_query_clients`, `_parse_service_clients`, etc.).
3. **Singleton access**: Each module exposes `get_settings()` cached with `functools.lru_cache(maxsize=1)` so callers import `settings = get_settings()` once at startup.
4. **Typed parsing helpers** (agent-platform): `_optional_str`, `_optional_int`, `_optional_float`, `_optional_bool`, `_optional_choice` enforce value domains and raise `ValueError` on invalid input, causing startup failure.
5. **Validation in `__post_init__` or `from_env`**: Invalid configuration fails fast during process start rather than at first use. Examples: `max_iters >= 1`, `context_trigger_ratio ∈ (0, 0.9)`, IANA timezone validation, provider must be one of `dashscope|deepseek|openai`, duplicate `source_id` detection, path traversal rejection in git source paths.
6. **Cross-service secret contracts**: Many features require matching pairs across services (e.g., `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS`; `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`; `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`; `PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET` ↔ `INCIDENT_QUERY_CLIENTS`). These contracts are documented in `configuration-reference.md` and provisioned together by `make deploy` calling the corresponding `sync-*-secrets.sh` script.
7. **Feature toggles via env**: Features are enabled by setting specific env vars to truthy values (`PLATFORM_GATEWAY_REQUIRE_AUTH=true`, `GATEWAY_K8S_ENABLED=true`, `GATEWAY_MUTATING_TOOLS_ENABLED=true`, `GATEWAY_ELASTIC_ENABLED=true`, `OTEL_ENABLED=true`). Unset optional URLs disable the corresponding capability (e.g., unset `PLATFORM_GATEWAY_TOOL_GATEWAY_URL` makes the portal Tools route return 503).
8. **Policy bundles are external**: Policy enforcement reads a YAML file at `*_POLICY_PATH` (default `/etc/luban/policy/policy.yaml`); the canonical copy is `shared/shared-contracts/policies/policy-default.yaml` and is synced to consumer locations via `make sync-policy`.
9. **Runtime profiles**: Agent LLM providers are selected via `AGENTSCOPE_PROVIDER` plus profile ConfigMaps under `shared/platform-ops/gitops/runtime-profiles/`; only one profile is active at a time, switched via `select-runtime-profile.sh`.

## Conventions and constraints

- **Every setting has a default**: Even security-sensitive fields like `*_CLIENT_SECRET` default to empty string; missing secrets simply disable the related feature rather than crashing.
- **Boolean env parsing is uniform**: Values are accepted as `"1" | "true" | "yes" | "on"` (case-insensitive) and converted to `bool`; all other strings are treated as false.
- **Comma-separated list parsing**: Multi-value configs (`INGEST_CLIENTS`, `WORKLOAD_CLIENTS`, `QUERY_CLIENTS`) use `key=value,key=value,...` format parsed by splitting on commas then `=`/`:`.
- **JSON multi-value configs**: `SKILLS_SOURCES` and `SKILLS_GIT_TOKENS` are JSON arrays/objects parsed at load time with strict validation (unknown types, duplicates, malformed IDs, path traversal).
- **Store backends are chosen via env**: `*_STORE_BACKEND` accepts `memory` or `postgres`; unknown values fail startup (documented for session/state stores).
- **Secrets never live in Git**: All secrets are provisioned as Kubernetes Secrets via `sync-*` scripts; `.env` examples are committed but actual values are generated or supplied at deploy time.
- **Cross-service dependencies are explicit**: The configuration reference documents every inter-service chain (token delegation, identity verification, tool relay, mutating action approval, audit ingestion, skills retrieval, incident intake) with exact variable names and required matches.
- **Fail-closed by default**: Optional integrations (audit, skills, incidents, elastic, k8s tools) are disabled unless their enabling env var is set to a truthy value; unset URLs cause routes to fail closed (503) rather than proxying to nowhere.