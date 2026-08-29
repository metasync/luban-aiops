---
kind: configuration_system
name: Environment-Driven Settings with Kustomize Runtime Profiles and Cross-Service Secret Contracts
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/core/env.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/deepseek/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/README.md
    - docs/guides/configuration-reference.md
    - shared/shared-contracts/policies/policy-default.yaml
---

## What system/approach is used

The Luban AIOps platform uses a uniform, environment-variable-driven configuration system across all Python services. Each service defines frozen `dataclass` settings objects under `src/<service>/core/config.py` (or `runtime_settings.py` for agent-platform) that read values from `os.getenv`, coerce types, validate constraints in `__post_init__`, and expose a cached `get_settings()` accessor via `functools.lru_cache(maxsize=1)`. Configuration is layered: hard-coded defaults in the dataclass → optional overrides from environment variables → runtime profiles (Kustomize ConfigMaps) for non-secret knobs → Kubernetes Secrets mounted as env vars for secrets. There are no YAML/JSON config files consumed at runtime by the services themselves; policy bundles are the only file-based config, loaded from a path set via env.

## Key files and packages

- **agent-platform**: `products/agent-platform/src/agent_service/runtime_settings.py` (provider-specific options, kernel tuning, HITL bridging), `core/config.py` (`RuntimeSettings.from_env` + cached `get_settings`), `core/env.py` (`get_env_value`, `get_env_int`).
- **platform-gateway**: `products/platform-gateway/src/platform_gateway/core/config.py` (`PlatformGatewaySettings`).
- **tool-gateway**: `products/tool-gateway/src/tool_gateway/core/config.py` (`GatewaySettings`).
- **audit-service**: `products/audit-service/src/audit_service/core/config.py` (`AuditSettings`, `IngestClient`, `WorkloadClient`, parsers for comma-separated client registries).
- **identity-broker / incident-service / skills-hub**: each follow the same `core/config.py` pattern (referenced in docs).
- **Runtime profiles**: `shared/platform-ops/gitops/runtime-profiles/{openai,dashscope,deepseek}/configmap.yaml` — Kustomize overlays that mount non-secret LLM profile env vars into agent-platform pods.
- **Secret provisioning scripts**: `shared/platform-ops/gitops/sync-*-secrets.sh` generate and apply per-service `*-runtime-secrets` Kubernetes Secrets.
- **Documentation contract**: `docs/guides/configuration-reference.md` is the authoritative cross-service env var map, secret contracts, and feature activation matrix.

## Architecture and conventions

1. **Frozen dataclass settings per service.** Every service exposes a single frozen dataclass (e.g. `PlatformGatewaySettings`, `GatewaySettings`, `AuditSettings`, `RuntimeSettings`) whose fields are the canonical configuration surface. Defaults are declared on the class so unconfigured deployments run with safe, documented defaults.
2. **`from_env()` factory + cached accessor.** Each settings class implements `from_env()` which reads `os.getenv(<VAR>, <default>)` and coerces types. A module-level `@lru_cache(maxsize=1)` `get_settings()` function provides a singleton-style global access point used throughout the service.
3. **Boolean parsing convention.** Booleans are parsed by stripping whitespace, lowercasing, and accepting `{"1", "true", "yes", "on"}` as truthy — consistently applied across all services.
4. **Optional helpers for typed env vars.** The agent-platform defines `_optional_str/int/float/bool` helpers that return `None` when unset and raise `ValueError` for invalid booleans or out-of-range choices; other services use inline `int(...)` or `.strip().lower() in {...}` patterns.
5. **Startup validation in `__post_init__`.** Invalid combinations or out-of-range values fail fast at import/startup time (e.g. `AGENTSCOPE_PROVIDER` must be one of `dashscope|deepseek|openai`; `AGENTSCOPE_TIMEZONE` must be a valid IANA timezone; `max_iters >= 1`; `context_trigger_ratio` in `(0, 0.9)`). This enforces invariant configuration before any request is served.
6. **Feature toggles via env.** Features like Elastic connector (`GATEWAY_ELASTIC_ENABLED`), Kubernetes tools (`GATEWAY_K8S_ENABLED`), output redaction (`GATEWAY_REDACTION_ENABLED`), audit ingestion (`*_AUDIT_SERVICE_URL`), skills hub (`GATEWAY_SKILLS_SERVICE_URL`), incidents (`PLATFORM_GATEWAY_INCIDENT_SERVICE_URL`), and OpenTelemetry push (`OTEL_ENABLED`) are opt-in: unset means disabled or log-only fallback.
7. **Cross-service secret contracts.** Inter-service authentication is configured via matching pairs of env vars on both sides (e.g. `PLATFORM_GATEWAY_*_CLIENT_SECRET` ↔ `*_INGEST_CLIENTS` or `*_QUERY_CLIENTS` entries). The `configuration-reference.md` documents every chain (token delegation, identity verification, tool relay, audit ingestion, skills retrieval, incident intake) and the exact secret names and formats.
8. **Runtime profiles for agent-platform.** Non-secret LLM backend selection is done through Kustomize overlays under `shared/platform-ops/gitops/runtime-profiles/`. Each profile contributes a `ConfigMap` named `agent-platform-runtime-profile` setting `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL`. Only one profile overlay is active at a time in the dev-k8s deployment.
9. **Policy bundle as file-based config.** Policy enforcement is driven by a YAML bundle loaded from a path specified by `*_POLICY_PATH` env vars. The canonical source is `shared/shared-contracts/policies/policy-default.yaml`; consumers keep byte-identical copies synced via `make sync-policy`.
10. **Shared runtime env.** Common variables like `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_ENABLED`, and `IDENTITY_SERVICE_URL` live in `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` and are referenced across services.

## Conventions and constraints

- **All runtime configuration comes from environment variables**; services do not read arbitrary files except policy bundles and projected workload tokens (paths set via env).
- **Secrets are never committed to Git.** They are provisioned as Kubernetes Secrets via `sync-*-secrets.sh` scripts and mounted into pods; example templates live under `runtime-profiles/*/runtime-secrets.example.env`.
- **Unknown store backends fail startup.** Values like `SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `INCIDENT_STORE_BACKEND` are validated against known enums (`memory`, `postgres`, `redis`) — unknown values cause startup failure.
- **Unset optional endpoints degrade gracefully.** If `*_AUDIT_SERVICE_URL`, `GATEWAY_SKILLS_SERVICE_URL`, `GATEWAY_INCIDENTS_SERVICE_URL`, or `PLATFORM_GATEWAY_TOOL_GATEWAY_URL` / `PLATFORM_GATEWAY_SKILLS_HUB_URL` are unset, the corresponding connectors/routes are disabled (log-only auditing, 503 for portal proxies, unregistered tools).
- **Cross-service client IDs and secrets must match exactly.** The configuration reference documents the required pairings (e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry; `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` registry). Mismatches cause authentication failures at runtime.
- **Provider options are type-checked against the selected provider.** `RuntimeSettings.__post_init__` ensures `provider_options` matches `AGENTSCOPE_PROVIDER` and raises `ValueError` otherwise.
- **Policy changes require rebuild/redeploy.** Because policy bundles are baked into images or Kustomize overlays, changing `policy-default.yaml` requires running `make validate-policy` and `make sync-policy`, then rebuilding and redeploying.