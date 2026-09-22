---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Per-Service `get_settings()` Caches
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - docs/guides/configuration-reference.md
---

## What system/approach is used

Every product service in the Luban platform loads its runtime configuration exclusively from **environment variables** via a per-service frozen `dataclass` plus a module-level `@lru_cache(maxsize=1)` `get_settings()` accessor. There is no YAML/JSON config file loader, no `.env` parser, and no framework (Pydantic, dynaconf, etc.) — just `os.getenv` with typed defaults, parsed into immutable settings objects at process start.

The pattern is uniform across all nine products:
- `products/<service>/src/<service_pkg>/core/config.py` defines a frozen dataclass (e.g. `PlatformGatewaySettings`, `GatewaySettings`, `AuditSettings`, `IdentitySettings`, `IncidentSettings`, `SkillsSettings`, `ExecutionSettings`) with a `from_env()` classmethod that reads `os.getenv(...)` for every field.
- A cached `get_settings()` function returns the singleton instance.
- The service's `app.py` / `main.py` calls `get_settings()` early so validation runs at import time.

The agent-platform is the only exception: its settings live in `agent_service/runtime_settings.py` as `RuntimeSettings` (with nested provider option dataclasses) and are exposed through `agent_service/core/config.get_settings()`.

## Key files and packages

- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings`, provider-specific option classes (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`), boolean/int/float/choice helpers, and full `from_env()` mapping.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` (service URLs, JWKS cache, token audience, policy path, audit/incident/skills/proxy clients).
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` (identity/JWKS, K8s/Elastic/Browser/HTTP/Secrets connectors, email delivery, password policy enforcement).
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` + `IngestClient` / `WorkloadClient` parsers for comma-delimited registries.
- `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings` + `ServiceClient` / `WorkloadClient` parsers; supports static client registry and projected workload identity mapping.
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` with connector name list parsing.
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` with JSON-parsed `sources` (`local`/`git`), `git_tokens`, query/workload client registries, and composition cap validation.
- `products/execution-runtime/src/execution_runtime/core/config.py` — `ExecutionSettings` with startup validation of supported backends and required DB URL.
- `docs/guides/configuration-reference.md` — authoritative cross-service environment variable dependency map, feature activation matrix, secret contracts, and per-service tables.

## Architecture and conventions

1. **Frozen dataclasses with `__post_init__` validation.** Every settings object is immutable after construction. Validation lives in `__post_init__` (e.g. `tool_gateway` enforces `secret_delivery_backend ∈ {memory, redis}`, positive TTL/capacity, valid Redis/SMTP ports, and password-policy overrides may only *tighten* the contract); complex parsing lives in helper functions like `parse_ingest_clients`, `parse_workload_clients`, `parse_sources`, `parse_connectors`, `parse_git_tokens`, `parse_positive_int`, `_env_bool`, `_env_optional_int`, `_env_optional_tuple`.

2. **Per-service env var prefixes.** Each service owns its namespace: `AGENTSCOPE_*` / `AGENT_*` for agent-platform, `PLATFORM_GATEWAY_*` for platform-gateway, `GATEWAY_*` for tool-gateway, `AUDIT_*` for audit-service, `IDENTITY_*` for identity-service, `INCIDENT_*` for incident-service, `SKILLS_*` for skills-hub, `EXECUTION_*` for execution-runtime. Cross-service shared vars include `OTEL_*` and `IDENTITY_SERVICE_URL`.

3. **Deny-by-default feature flags.** Optional capabilities are disabled unless explicitly enabled: `GATEWAY_BROWSER_ENABLED=false`, `GATEWAY_HTTP_ENABLED=false`, `GATEWAY_SECRETS_ENABLED=false`, `GATEWAY_ELASTIC_ENABLED=false`, `GATEWAY_K8S_ENABLED=false`, `GATEWAY_MUTATING_TOOLS_ENABLED=false`. Allowlists default to empty tuples, which reject everything.

4. **Comma-separated or JSON multi-value fields.** Registries use compact string formats parsed at load time: `client_id=secret,...` (ingest/query clients), `subject=client_id,...` (workload mappings), `client_id:secret:aud1|aud2` (identity service clients), JSON lists/maps for `SKILLS_SOURCES` and `SKILLS_GIT_TOKENS`, comma-separated origin allowlists.

5. **Cross-service secret contracts.** Secrets are never embedded in code; they are provisioned as Kubernetes Secrets and mounted or injected. Contracts are documented in `configuration-reference.md`: delegation secrets (`PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS`), audit ingest credentials (`*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`), skills query credentials, incident query credentials, execution signing/handoff tokens, OTLP headers, browser credential sets.

6. **Policy bundle as configuration.** Policy enforcement uses a single canonical YAML (`shared/shared-contracts/policies/policy-default.yaml`) synced byte-identically into both gateways' packaged defaults and the dev-k8s overlay. Consumers read it via `*_POLICY_PATH`; missing/invalid bundles fail startup rather than falling back silently.

7. **Agent-platform runtime profiles.** LLM provider selection rides Kustomize ConfigMap overlays selected by `select-runtime-profile.sh`; the active profile sets `AGENTSCOPE_PROVIDER`, model names, base URLs, and API keys. Provider-specific options (`*_THINKING_ENABLE`, `*_REASONING_EFFORT`, `*_PARALLEL_TOOL_CALLS`) are layered on top.

## Conventions and constraints

- **Immutable settings:** All settings dataclasses are `frozen=True`; mutation is impossible after construction.
- **Fail-fast startup:** Invalid values raise `ValueError` or `SettingsError` during `from_env()` / `__post_init__`, preventing misconfigured processes from starting.
- **Typed coercion helpers:** Boolean parsing normalizes `{"1", "true", "yes", "on"}` to `True`; optional int/tuple helpers return `None` for blank values; choice helpers validate against a known set.
- **Secrets-only sensitive values:** Passwords, API keys, and tokens are read as optional strings and never logged; many services treat empty/unset as "feature disabled" rather than failing.
- **Backward-compatible defaults:** Defaults mirror upstream frameworks (agentscope, Chromium headless shell) so unmodified deployments behave identically to before settings existed.
- **Single source of truth for env vars:** `docs/guides/configuration-reference.md` is the authoritative reference; each service's `core.config` module is the implementation source cited at the top of each table.
- **No hot reload:** Policy bundles and settings are loaded once at import; changes require a pod restart. The documentation explicitly states there is no hot reload for policy files.