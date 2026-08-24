---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Per-Service `get_settings()` Cache
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/runtime.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/runtime.py
    - products/audit-service/src/audit_service/core/config.py
    - products/audit-service/src/audit_service/core/runtime.py
    - products/incident-service/src/incident_service/core/config.py
    - products/incident-service/src/incident_service/core/runtime.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/skills-hub/src/skills_hub/core/runtime.py
    - products/identity-broker/src/identity_broker/core/config.py
    - products/identity-broker/src/identity_broker/core/runtime.py
    - docs/guides/configuration-reference.md
    - shared/shared-contracts/policies/policy-default.yaml
---

## What system/approach is used

Every Python service in the platform implements a uniform, zero-dependency configuration layer: frozen `dataclass` settings objects loaded exclusively from environment variables via `os.getenv`, wrapped in an `@lru_cache(maxsize=1)` accessor so the process reads env vars once at import time. There are no `.env` files, YAML/JSON config parsers for runtime behavior, or external config servers — configuration is purely 12-factor environment variables, with secrets delivered as Kubernetes Secrets mounted into the same pod.

The pattern is repeated across all services:
- `products/<service>/src/<service>/core/config.py` — feature/runtime settings dataclass + `from_env()` + cached `get_settings()`
- `products/<service>/src/<service>/core/runtime.py` — HTTP host/port run settings (hosted in a separate module to keep server bootstrap small)
- `products/<service>/src/<service>/core/metadata.py` — shared defaults like `DEFAULT_HTTP_HOST` / `DEFAULT_HTTP_PORT`

The agent-platform deviates slightly by keeping its settings in `runtime_settings.py` and exposing a thin `config.get_settings()` wrapper that delegates to it, but the shape is identical.

## Key files and packages

- `products/agent-platform/src/agent_service/runtime_settings.py` — largest settings object; validates ranges, IANA timezone, provider/options type safety in `__post_init__`; parses per-provider options (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) from `AGENTSCOPE_*`, `DASHSCOPE_*`, `DEEPSEEK_*`, `OPENAI_*`, `LUBAN_*` env vars.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` (JWKS URLs, token audience, delegation, audit/incident/skills client credentials).
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` (K8s/Elastic/connectors toggles, redaction, audit/skills/incidents clients).
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` plus `parse_ingest_clients` / `parse_workload_clients` helpers; supports comma-delimited `client_id=secret,...` lists.
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` with JSON-parsed `SKILLS_SOURCES` (source_id/type/url/ref/path) and `SKILLS_GIT_TOKENS`, plus strict validation raising a local `SettingsError`.
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` mirroring skills-hub's query/workload client registry vocabulary.
- `products/identity-broker/src/identity_service/core/config.py` — identity broker settings (Keycloak/OIDC, workload issuer, client registries).
- Per-service `core/runtime.py` — tiny `XxxRunSettings` dataclasses reading `<SERVICE>_HOST` / `<SERVICE>_PORT`.
- `docs/guides/configuration-reference.md` — authoritative cross-service dependency map, secret contracts, and per-variable table documenting every env var, default, and source (ConfigMap vs runtime-secret).
- `shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env` — per-service ConfigMaps providing non-secret values.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared OTLP endpoint and identity URL.
- `shared/shared-contracts/policies/policy-default.yaml` plus copies under each gateway's `policies/` directory — policy bundle consumed via `*_POLICY_PATH` env var.

## Architecture and conventions

1. **Frozen dataclasses with `from_env()` classmethod.** Every setting class is immutable (`frozen=True`). Configuration parsing lives in a classmethod that maps one env var per field, with sensible defaults. Complex fields (comma-separated client lists, JSON arrays/maps) are parsed by dedicated helper functions (`parse_ingest_clients`, `parse_query_clients`, `parse_sources`, `parse_git_tokens`, `parse_connectors`).

2. **Process-wide singleton via `@lru_cache(maxsize=1)`.** Each module exposes `get_settings()` which caches the result after the first call. This means changing `os.environ` after import has no effect — configuration is effectively immutable for the lifetime of the process, matching container semantics.

3. **Strict boolean parsing.** Boolean env vars accept `"1" | "true" | "yes" | "on"` (case-insensitive) and parse to `True`; everything else is `False`. Port resolution tolerates Kubernetes service-link strings like `tcp://IP:PORT` by falling back to the default on `int()` failure.

4. **Fail-fast validation in `__post_init__` or parser helpers.** Invalid values raise `ValueError` (settings classes) or `SettingsError` (skills-hub) at import time, before any request handling starts. Examples: `AGENTSCOPE_PROVIDER` must be one of `dashscope|deepseek|openai|luban`; `AGENTSCOPE_TIMEZONE` must be a valid IANA zone; `SKILLS_SOURCES` rejects unknown types, duplicate `source_id`s, malformed ids, and path traversal attempts.

5. **Per-service env var namespaces.** Variables are prefixed by service name (`PLATFORM_GATEWAY_*`, `GATEWAY_*`, `AUDIT_*`, `SKILLS_*`, `INCIDENT_*`, `AGENTSCOPE_*`, `IDENTITY_*`) so there is no cross-service collision. Shared variables (`OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `IDENTITY_SERVICE_URL`) live in `shared/runtime.env` and are documented under the "Shared (all pods)" section.

6. **Secrets are never committed.** The configuration reference explicitly marks which keys come from runtime-config ConfigMaps versus runtime-secrets Secrets. Provisioning scripts (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-runtime-secret.sh`, `sync-otel-secrets.sh`) generate random secrets and write K8s Secret objects; they can be skipped via `SKIP_*_SECRETS=true`.

7. **Cross-service contracts are enforced by matching env pairs.** The configuration reference documents chains where two services must agree on a value (e.g., `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry; `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`; `*_CLIENT_SECRET` ↔ `*_QUERY_CLIENTS`). These are not validated programmatically — they are operational contracts enforced by provisioning scripts and documentation.

8. **Policy bundles are file-backed, not env-encoded.** Both gateways read a YAML policy file from a path given by `*_POLICY_PATH` (default `/etc/luban/policy/policy.yaml`). The canonical copy lives in `shared/shared-contracts/policies/policy-default.yaml` and is synced to consumer locations via `make sync-policy`.

9. **Runtime profiles (agent-service only).** LLM backend selection is driven by `AGENTSCOPE_PROFILE` (a generic label) plus `AGENTSCOPE_PROVIDER` set via a Kustomize profile overlay ConfigMap. Multi-model catalog entries are added by setting `<PROVIDER>_API_KEY` / `<PROVIDER>_BASE_URL` / `<PROVIDER>_MODELS` env vars per supported provider.

## Conventions and constraints

- **One source of truth per service:** a single `core/config.py` (or `runtime_settings.py`) defines every configurable knob; nothing outside these modules should call `os.getenv` directly for application behavior.
- **Defaults encode safe behavior:** booleans default to `True` for auth and TLS verification, `False` for mutating tools and optional connectors; unset URLs disable features gracefully (e.g., unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing, unset `*_SERVICE_URL` returns 503 for portal proxies).
- **Unknown store backends fail startup:** `STORE_BACKEND` values are trimmed and lowercased; unknown values cause startup errors rather than silently degrading.
- **Complex lists use a compact wire format:** comma-separated `key=value,key=value` strings for client registries; JSON strings for structured lists (`SKILLS_SOURCES`, `SKILLS_GIT_TOKENS`). Parsing failures raise explicit errors with context.
- **No hot-reload:** because `get_settings()` is cached with `lru_cache(maxsize=1)`, configuration changes require a process restart — consistent with container deployment models.
- **Documentation is the spec:** `docs/guides/configuration-reference.md` is treated as the authoritative contract between code and operators; every new env var must be added there alongside the code change.