---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Per-Service `from_env()` Loading
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - docs/guides/configuration-reference.md
---

## What system/approach is used

Every service in the platform implements configuration as **frozen Python dataclasses** loaded exclusively from **environment variables** via a per-service `Settings.from_env()` classmethod. There is no YAML/JSON config file loading at runtime, no `.env` file parsing, and no third-party settings framework (Pydantic v2 `BaseSettings`, Dynaconf, etc.). The pattern is uniform across all nine services: `products/{audit-service,execution-runtime,identity-broker,incident-service,platform-gateway,skills-hub,tool-gateway}/src/<service>/core/config.py` plus `products/agent-platform/src/agent_service/runtime_settings.py`. A module-level `@lru_cache(maxsize=1)` exposes `get_settings()` so the process-wide singleton is constructed once on first access.

Configuration values are typed by dataclass field defaults and validated in `__post_init__` (or constructor helpers) — invalid values raise `ValueError` or a service-specific `SettingsError`, causing startup to fail fast. Optional secrets use a helper that strips whitespace and returns `None` when empty, so missing secrets never crash the process; instead they disable the feature path (e.g. unset `*_AUDIT_SERVICE_URL` degrades audit emission to log-only).

## Key files and packages

- `products/agent-platform/src/agent_service/runtime_settings.py` — largest settings object (`RuntimeSettings`) covering LLM provider options, kernel tuning, HITL, evidence persistence, model discovery, execution worker handoff, and incident-report assembly. Uses nested frozen dataclasses (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) selected by `AGENTSCOPE_PROVIDER`.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` (service URLs, JWKS cache, token audience, policy path, portal proxies).
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` (K8s connector, Elastic, redaction, skills/incidents connectors, identity/JWKS).
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` with `IngestClient` / `WorkloadClient` tuples parsed from comma-delimited env strings.
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` with query/workload client registries and connector list parser.
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` with JSON-parsed `SKILLS_SOURCES` and `SKILLS_GIT_TOKENS`, strict `source_id` regex validation.
- `products/execution-runtime/src/execution_runtime/core/config.py` — `ExecutionSettings` with `__post_init__` enforcing supported backends and required DB URL for postgres.
- `docs/guides/configuration-reference.md` — authoritative cross-service environment variable dependency map, secret contracts, and per-service tables.
- `shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env` — dev-k8s ConfigMap fragments that supply non-secret defaults per service.
- `shared/platform-ops/gitops/gitops/*.sh` — `sync-*-secrets.sh` scripts that generate and mount Kubernetes Secrets into each pod's environment.

## Architecture and conventions

1. **One frozen dataclass per service.** Each service defines exactly one top-level `*Settings` dataclass whose fields are the complete configuration surface. Nested dataclasses group related knobs (provider options, client registries).
2. **`from_env()` reads only `os.getenv`.** No file I/O, no dotenv, no config server. Defaults are hard-coded constants at the top of the module (e.g. `DEFAULT_AGENT_SERVICE_URL = "http://agent-service:8000"`).
3. **`@lru_cache(maxsize=1)` singleton accessor.** `get_settings()` is imported wherever settings are needed; it constructs the object lazily and caches it for the process lifetime.
4. **Strict boolean parsing.** Booleans accept `"1"|"true"|"yes"|"on"` (case-insensitive); everything else is falsy. Custom helpers `_optional_bool` in agent-platform also reject unknown strings with `ValueError`.
5. **Comma-separated lists parsed into tuples.** `AUDIT_INGEST_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `SKILLS_WORKLOAD_CLIENTS`, `INCIDENT_CONNECTORS` are all `client_id=secret,...` or `subject=client_id,...` strings split on commas and stripped.
6. **Complex structures via JSON env vars.** `SKILLS_SOURCES` is a JSON array of source specs; `SKILLS_GIT_TOKENS` is a JSON map `source_id→token`; both are validated at parse time with explicit error messages.
7. **Validation in `__post_init__` or constructor helpers.** Out-of-range values (negative timeouts, unsupported store backends, invalid IANA timezone, mismatched `provider_options` type) raise `ValueError` immediately during settings construction, so misconfiguration fails before the app starts serving.
8. **Secrets are injected as environment variables from Kubernetes Secrets.** The `configuration-reference.md` documents every secret contract and which `sync-*-secrets.sh` script provisions it. Secrets are never committed to Git; non-secret runtime defaults live in `dev-k8s/base/<service>/runtime-config.env` ConfigMaps.
9. **Cross-service credential matching is enforced by convention + docs.** Emitter `*_AUDIT_CLIENT_ID`/`*_AUDIT_CLIENT_SECRET` must match an entry in the receiver's registry env var (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`). The reference doc diagrams each chain and calls out the provisioning script.
10. **Policy bundles are separate from runtime settings.** Policy YAML lives under `policies/policy-default.yaml` and is synced to consumers via `make sync-policy`; it is not loaded through the settings dataclass but referenced by path (`PLATFORM_GATEWAY_POLICY_PATH`, `GATEWAY_POLICY_PATH`).

## Conventions and constraints

- **All configuration is environment-variable driven.** No code path loads a config file at runtime; files exist only as deployment manifests (ConfigMaps, Secrets).
- **Settings objects are immutable.** `@dataclass(frozen=True)` prevents mutation after construction; callers receive a snapshot.
- **Missing optional secrets degrade gracefully.** Unset `*_AUDIT_SERVICE_URL`, unset `*_AUDIT_CLIENT_SECRET`, unset `TOOL_GATEWAY_URL`, unset `AGENT_EXECUTION_WORKER_URL` do not crash startup — they disable the corresponding feature path (log-only auditing, unregistered tools, failing closed mutating resumes).
- **Required configuration failures abort startup.** Invalid store backends, negative timeouts, unsupported providers, malformed JSON in `SKILLS_SOURCES`/`SKILLS_GIT_TOKENS`, and unknown enum values raise exceptions during `from_env()`.
- **Per-service env var prefixes are mandatory.** Agent-platform uses `AGENTSCOPE_*` / `AGENT_*`; platform-gateway uses `PLATFORM_GATEWAY_*`; tool-gateway uses `GATEWAY_*`; others use their own prefix (`AUDIT_*`, `SKILLS_*`, `INCIDENT_*`, `EXECUTION_*`). This avoids collisions between services.
- **Defaults mirror production behavior where safe.** In-memory stores, `require_auth=true`, `mutating_tools_enabled=false`, `redaction_enabled=true` are conservative defaults; operators must explicitly opt into risky features.
- **The canonical configuration reference is the single source of truth.** `docs/guides/configuration-reference.md` enumerates every variable, its default, its source (runtime-config vs runtime-secrets), and cross-service dependency chains; new settings should be added there alongside the code.