---
kind: configuration_system
name: Environment-Driven Settings with Per-Service Dataclass Configs and GitOps Overlays
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

The platform uses a uniform, environment-variable-driven configuration system. Each Python service defines a frozen `dataclass` (e.g. `RuntimeSettings`, `GatewaySettings`, `PlatformGatewaySettings`) that reads its knobs from `os.environ` via a classmethod `from_env()`. A module-level `@lru_cache(maxsize=1)` accessor (`get_settings()`) returns a singleton settings object per process. There is no YAML/JSON config file consumed at runtime by the services themselves; all runtime values come from Kubernetes `ConfigMap`/`Secret` mounted as environment variables.

Configuration is layered through Kustomize overlays under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` plus per-service `runtime-secrets.example.env` files. The dev overlay ships defaults; production deployments are expected to layer additional overlays on top. Policy bundles are the only non-env artifact loaded at runtime: both gateways read a YAML policy file from a path configured via `GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH` (default `/etc/luban/policy/policy.yaml`).

## Key files and packages

- `products/agent-platform/src/agent_service/core/config.py` — cached `get_settings()` entry point returning `RuntimeSettings`
- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass, env parsing helpers (`_optional_str/int/float/bool/choice`), provider-specific option types, startup validation in `__post_init__`
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` dataclass + `get_settings()`
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` dataclass + `get_settings()`
- `products/execution-runtime/src/execution_runtime/core/config.py`, `products/identity-broker/src/identity_service/core/config.py`, `products/audit-service/src/audit_service/core/config.py`, `products/skills-hub/src/skills_hub/core/config.py`, `products/incident-service/src/incident_service/core/config.py` — analogous per-service settings modules
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — default env var definitions for each pod
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared vars (`OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `IDENTITY_SERVICE_URL`)
- `docs/guides/configuration-reference.md` — authoritative cross-service dependency map, secret contracts, rollout workflow, and per-service variable tables
- `shared/shared-contracts/policies/policy-default.yaml` — canonical policy bundle, replicated byte-identically to consumers by `make sync-policy`

## Architecture and conventions

1. **Per-service frozen dataclass**: Every service owns its own settings type. Fields have sensible defaults so an unset env var produces a valid (often disabled) posture. Boolean flags use a truthy set `{"1", "true", "yes", "on"}` parsed uniformly.
2. **Process-wide singleton**: `get_settings()` is wrapped in `functools.lru_cache(maxsize=1)`, so settings are parsed once at import/startup time and reused throughout the process.
3. **Startup validation**: Non-trivial settings validate their ranges in `__post_init__` (e.g. `AGENTSCOPE_MAX_ITERS >= 1`, `AGENT_MODEL_DISCOVERY_REFRESH_SECONDS >= 1`, IANA timezone validation). Invalid values raise `ValueError` at startup rather than failing later.
4. **Fail-closed vs degrade-by-design**: Optional integrations degrade gracefully when their URL/secret is absent (audit ingestion falls back to log-only; skills tools stay unregistered if `GATEWAY_SKILLS_SERVICE_URL` is unset). Critical security knobs fail closed (missing `AGENT_EXECUTION_SIGNING_KEY` or `AGENT_EXECUTION_HANDOFF_TOKEN` rejects mutating resumes; empty `INCIDENT_WEBHOOK_TOKEN` disables intake with 503).
5. **GitOps-first deployment**: Defaults live in `dev-k8s/base/*.env`; secrets live in Kubernetes Secrets provisioned by scripts under `shared/platform-ops/gitops/gitops/` (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-otel-secrets.sh`, `sync-browser-credentials.sh`). No secrets are committed to Git.
6. **Cross-service secret contracts**: Many variables form pairs across services (e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match an `IDENTITY_SERVICE_CLIENTS` entry; `*_AUDIT_CLIENT_SECRET` must match the corresponding entry in `AUDIT_INGEST_CLIENTS`). These contracts are documented centrally in `configuration-reference.md` and enforced at the receiving service's auth layer.
7. **Policy bundle discipline**: The single source of truth is `shared/shared-contracts/policies/policy-default.yaml`. It is replicated to both gateway consumers and the dev overlay by `make sync-policy`; contract tests enforce byte parity. Changes require editing the canonical file, bumping its `version`, updating scenario expectations, syncing, verifying, then deploying. Bundles are not hot-reloaded — changes take effect on pod restart.
8. **Runtime profiles**: Agent-service LLM providers are selected via `AGENTSCOPE_PROVIDER` plus profile ConfigMaps under `shared/platform-ops/gitops/gitops/runtime-profiles/`. Two permanent non-switchable postures (`mutating-dev`, `browser-dev`) merge extra env into `platform-runtime-config`.

## Conventions and constraints

- **All runtime knobs are environment variables** — there is no `.env` file loader, no TOML/INI parser, no config file watcher inside the services.
- **Boolean flags accept only the four truthy strings** (`1`, `true`, `yes`, `on`); anything else is treated as false.
- **Unknown backend names fail startup**: e.g. unknown `SESSION_STORE_BACKEND` or unsupported `AGENTSCOPE_PROVIDER` raise errors during settings construction.
- **Secrets never travel through code paths that reach prompts/tools**: credential sets for browser flows are mounted as a file path (`GATEWAY_BROWSER_CREDENTIAL_SETS`) and never appear in tool results or audit trails.
- **Audit emission is fire-and-forget**: unreachable audit-service degrades to log-only auditing without blocking user requests.
- **Policy bundle load failures fail startup**: a missing or invalid bundle raises `PolicyLoadError` — there is no silent fallback to a packaged default.
- **Cross-service client registries are string-encoded maps**: `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS` follow a `client_id=secret,...` or `client_id:client_secret:audience1|audience2` format and must be kept in sync by the provisioning scripts.
- **OpenTelemetry headers are injected per-pod**: `OTEL_EXPORTER_OTLP_HEADERS` lives in each service's runtime-secrets Secret and is provisioned by `sync-otel-secrets.sh`.