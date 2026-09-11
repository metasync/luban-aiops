---
kind: configuration_system
name: Environment-Driven Configuration with Per-Service Settings Dataclasses and GitOps Runtime Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/shared-contracts/policies/policy-default.yaml
    - docs/guides/configuration-reference.md
---

## What system/approach is used

The platform uses a uniform, environment-variable-driven configuration system across all eight Python microservices. Each service defines a frozen `dataclass` (e.g. `RuntimeSettings`, `GatewaySettings`, `PlatformGatewaySettings`) in its `src/<service>/core/config.py` or equivalent, with a classmethod `from_env()` that reads values from `os.environ` and applies type coercion, defaults, and validation. A module-level `@lru_cache(maxsize=1)` accessor (`get_settings()`) exposes a singleton settings object for the lifetime of the process. There are no external config libraries — pure stdlib `os.getenv` plus dataclass-based parsing.

Configuration is layered through Kubernetes: each service has a `runtime-config.env` ConfigMap fragment under `shared/platform-ops/gitops/dev-k8s/base/<service>/` and an optional `runtime-secrets.example.env` for secret keys; shared variables live in `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`. The agent-service additionally supports Kustomize "runtime profiles" (Kustomize overlays) that swap LLM provider knobs (`AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL`, `<PROVIDER>_API_KEY`, etc.) without rebuilding images.

Policy bundles are treated as immutable runtime configuration files: the canonical copy at `shared/shared-contracts/policies/policy-default.yaml` is replicated byte-identically to both gateways' packaged defaults and the dev-k8s overlay via `make sync-policy`; consumers load them from a configured path (`GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH`) and fail startup on missing/invalid bundle.

## Key files and packages

- `products/agent-platform/src/agent_service/core/config.py` — cached `get_settings()` entry point delegating to `RuntimeSettings.from_env()`
- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass with per-provider option types, full env mapping, and `__post_init__` validation
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` dataclass (browser connector, k8s tools, elastic, audit, skills, incidents)
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` dataclass (identity, delegation, policy, incident proxy, skills proxy)
- `products/execution-runtime/src/execution_runtime/core/config.py`, `products/audit-service/src/audit_service/core/config.py`, `products/identity-broker/src/identity_service/core/config.py`, `products/incident-service/src/incident_service/core/config.py`, `products/skills-hub/src/skills_hub/core/config.py` — analogous per-service settings modules
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service default env fragments mounted into pods
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared OTLP/identity endpoints
- `docs/guides/configuration-reference.md` — authoritative cross-service variable dependency map, secret contracts, and rollout procedures
- `shared/shared-contracts/policies/policy-default.yaml` — canonical policy bundle source

## Architecture and conventions

1. **Per-service settings dataclass**: Every service owns its own frozen dataclass with a `from_env()` constructor. Defaults are declared as class attributes; boolean flags are parsed via a small truthy set (`{"1", "true", "yes", "on"}`).
2. **Cached singleton access**: Each settings module exposes `get_settings()` wrapped in `@lru_cache(maxsize=1)` so the parsed config is read once per process.
3. **Strict validation at construction**: Invalid values raise `ValueError` during `from_env()` / `__post_init__`, failing pod startup rather than silently misconfiguring the runtime (e.g. out-of-range timeouts, unsupported providers, invalid IANA timezone).
4. **Feature flags are opt-in by default**: Mutating tools, browser connector, Elastic connector, workload identity, and most integrations default to `false` or empty; enabling requires explicit env vars.
5. **Secrets never live in ConfigMaps**: Sensitive values (`*_CLIENT_SECRET`, `*_AUDIT_CLIENT_SECRET`, `OTEL_EXPORTER_OTLP_HEADERS`, signing keys, webhook tokens) are provisioned as separate Kubernetes Secrets via `sync-*` scripts under `shared/platform-ops/gitops/` and mounted into pods. Non-secret runtime knobs go in `runtime-config.env`.
6. **Cross-service secret contracts**: Shared secrets are paired between caller and callee (e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS`, `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`). The contract format is documented centrally in `configuration-reference.md`.
7. **Policy bundle immutability**: The single canonical `policy-default.yaml` is synced to consumers; any drift breaks `make verify`. Consumers cache the loaded bundle keyed on file path with no hot reload — changes require a pod restart.
8. **Agent-service runtime profiles**: LLM backends are selected via Kustomize profile overlays; only one profile is active at a time, and the profile label is decoupled from the provider name.
9. **Fallback/degradation semantics**: Unset optional URLs (audit, skills, incidents) degrade gracefully (log-only auditing, disabled connectors, 503 routes). Missing required secrets (signing key, handoff token) fail closed — there is no in-process fallback for mutating execution.

## Conventions and constraints

- **All configuration flows through environment variables** — no `.env` files, YAML configs, or TOML files are read at runtime by services.
- **Boolean flags use a fixed truthy vocabulary**: `1`, `true`, `yes`, `on` (case-insensitive); anything else is falsy.
- **Unknown store backends fail startup**: e.g. `SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND`, `INCIDENT_STORE_BACKEND` must be one of the documented choices.
- **Cross-service client registries use a `client_id=secret,...` format**: `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS` — callers and servers must agree on both id and secret.
- **Policy bundle path is mandatory and validated at startup**: a missing or invalid bundle raises `PolicyLoadError` with no silent fallback to a packaged default.
- **Mutating execution requires two signed steps**: `AGENT_EXECUTION_SIGNING_KEY` (HMAC) and `AGENT_EXECUTION_WORKER_URL` + `AGENT_EXECUTION_HANDOFF_TOKEN` (isolated worker handoff); absence fails closed with audited rejections (`signing_unavailable`, `worker_unavailable`).
- **Browser tooling is deny-by-default**: `GATEWAY_BROWSER_ENABLED=false`, `GATEWAY_BROWSER_ALLOW_ORIGINS` empty denies all navigation; credentials come only from a mounted JSON file (`GATEWAY_BROWSER_CREDENTIAL_SETS`), never inline.
- **OpenTelemetry headers are secret material**: `OTEL_EXPORTER_OTLP_HEADERS` lives in each service's runtime-secrets Secret and is provisioned via `sync-otel-secrets.sh`.
- **Profile switching is done via Kustomize overlay**, not at runtime: `select-runtime-profile.sh <profile-name>` swaps the active LLM provider ConfigMap; agentscope provider selection is a deployment-time knob, not a runtime toggle.