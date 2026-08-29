---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings per Service
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
---

## What system/approach is used

Each Python service in the platform implements its own configuration subsystem using a consistent pattern: **frozen `dataclass` settings objects** loaded exclusively from **environment variables** via a `from_env()` classmethod, exposed through an `lru_cache(maxsize=1)` `get_settings()` accessor. There is no shared config library — every product directory (`agent-platform`, `platform-gateway`, `tool-gateway`, `audit-service`, `execution-runtime`, `skills-hub`, `incident-service`, `identity-broker`) defines its own `core/config.py` (or equivalent) with a single frozen dataclass and parser helpers.

Configuration values are never read directly at call sites; services import `get_settings()` to obtain a process-wide singleton. Secrets (API keys, client secrets, signing keys, OIDC secrets) are mounted into pods as Kubernetes `Secret`s and consumed through environment variables declared in each service's `runtime-config.env` or `runtime-secrets.env`. Policy bundles are loaded from file paths configured via `*_POLICY_PATH` env vars.

There is no `.env` file loading, no YAML/JSON config files for runtime behavior (policy YAMLs aside), and no feature-flag framework — features are toggled by boolean env vars such as `GATEWAY_MUTATING_TOOLS_ENABLED`, `AGENT_MODEL_DISCOVERY_ENABLED`, `PLATFORM_GATEWAY_REQUIRE_AUTH`, etc.

## Key files and packages

- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass with provider-specific option sub-dataclasses (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`), extensive `__post_init__` validation, and `_optional_*` helper parsers.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` covering identity, delegation, audit, incident, and skills hub URLs/secrets.
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` for K8s/Elastic/connectors and policy enforcement.
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` with nested `IngestClient` / `WorkloadClient` tuples parsed from comma-delimited env strings.
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` with JSON-parsed `SKILLS_SOURCES` and `SKILLS_GIT_TOKENS`, plus query/workload client registries.
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` mirroring the skills-hub vocabulary.
- `products/execution-runtime/src/execution_runtime/core/config.py` — `ExecutionSettings` with startup validation enforcing supported backends and required URL pairs.
- `docs/guides/configuration-reference.md` — authoritative cross-service environment variable dependency map, secret contracts, provisioning scripts, and per-service tables.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service default env files consumed by dev deployments.
- `shared/shared-contracts/policies/policy-default.yaml` — canonical policy bundle synced into each gateway consumer location.

## Architecture and conventions

1. **Per-service frozen dataclass**: Each service defines exactly one frozen dataclass holding all runtime knobs. Fields have sensible defaults so services start without any env vars set (e.g. `memory` store backends, empty URLs disabling optional connectors).
2. **`from_env()` + `get_settings()`**: A classmethod reads `os.getenv(...)` with defaults; a module-level `@lru_cache(maxsize=1)` function returns the singleton. Tests can reload by clearing the cache.
3. **Typed parsing helpers**: Services define small helpers (`_optional_str`, `_optional_bool`, `_optional_int`, `_optional_float`, `_optional_choice`, `parse_ingest_clients`, `parse_query_clients`, `parse_workload_clients`, `parse_sources`, `parse_git_tokens`) to centralize env-to-type conversion and validation.
4. **Startup validation in `__post_init__`**: Invalid combinations raise `ValueError` immediately on import of settings, failing fast before the app serves traffic. Examples: unsupported `AGENTSCOPE_PROVIDER`, out-of-range `AGENTSCOPE_MAX_ITERS`, unknown `EXECUTION_STATE_STORE_BACKEND`, missing `EXECUTION_STATE_DB_URL` when backend is `postgres`, invalid IANA timezone.
5. **Optional connector pattern**: Optional integrations (audit-service, skills-hub, incidents, elastic, k8s tools) are disabled when their URL/env var is unset rather than failing startup — they degrade gracefully (log-only auditing, 503 routes, unregistered connectors).
6. **Cross-service secret contracts**: The same secret value must be configured on both sides of a communication channel (e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS`; `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`; `AGENT_EXECUTION_SIGNING_KEY` ↔ `EXECUTION_SIGNING_KEY`). These contracts are documented in `configuration-reference.md` and provisioned by shell scripts under `shared/platform-ops/gitops/` (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-otel-secrets.sh`).
7. **Policy-as-code**: Policy bundles live as YAML under `shared/shared-contracts/policies/policy-default.yaml` and are copied byte-for-byte into each gateway consumer (`tool-gateway`, `platform-gateway`, dev overlay). Consumers load them from the path given by `*_POLICY_PATH`.
8. **Runtime profiles**: The agent-service supports pluggable LLM backends via Kustomize profile overlays; the active profile selects `AGENTSCOPE_PROVIDER` and model catalog entries, while the `profile` field itself is a free-form deploy label decoupled from the provider.
9. **Shared OTel config**: `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and `OTEL_EXPORTER_OTLP_HEADERS` are documented as shared across all pods.

## Conventions and constraints

- **Environment-only runtime config**: All runtime configuration comes from environment variables; there is no runtime config file format. Configuration reference files (`*.env`) are deployment manifests, not application config loaders.
- **Boolean parsing convention**: Boolean env vars accept `"1"`, `"true"`, `"yes"`, `"on"` (case-insensitive) as truthy; everything else is falsy. This is applied consistently across `PLATFORM_GATEWAY_REQUIRE_AUTH`, `GATEWAY_K8S_ENABLED`, `GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_REDACTION_ENABLED`, `GATEWAY_ELASTIC_VERIFY_TLS`, etc.
- **Comma-separated list parsing**: Multi-value configs use `client_id=secret,...` (ingest/query clients) or `subject=client_id,...` (workload mappings) formats parsed by dedicated helpers.
- **JSON-complex types**: Complex structures like skill sources and git tokens use JSON-encoded env vars (`SKILLS_SOURCES`, `SKILLS_GIT_TOKENS`) with strict schema validation that fails startup on malformed input.
- **Fail-fast validation**: Unknown enum values (provider names, store backends), negative/zero timeouts, and missing required URL pairs raise exceptions during settings construction — misconfiguration cannot silently propagate.
- **Secrets via Kubernetes Secrets**: Secrets are never committed to Git; they are provisioned by `make deploy` calling sync scripts that generate random values or reuse exported ones, then mount them into pods as env vars. Each service's `runtime-secrets.env` documents which keys belong in which K8s Secret.
- **Feature flags opt-in**: New capabilities (HITL confirmation bridging, live model discovery, isolated execution worker, kernel tracing, task tools) are gated behind explicit env vars that default to off so existing deployments are unaffected.
- **Single source of truth for policy**: The canonical `policy-default.yaml` in `shared/shared-contracts/policies/` must be kept in sync with copies in `tool-gateway`, `platform-gateway`, and the dev overlay via `make sync-policy`.