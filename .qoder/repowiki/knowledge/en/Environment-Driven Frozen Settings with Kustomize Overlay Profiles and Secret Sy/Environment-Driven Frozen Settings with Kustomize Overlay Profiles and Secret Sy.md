---
kind: configuration_system
name: Environment-Driven Frozen Settings with Kustomize Overlay Profiles and Secret Sync Scripts
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/incident-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env
    - shared/shared-contracts/policies/policy-default.yaml
    - docs/guides/configuration-reference.md
---

# Configuration System

## Approach

Every service in the monorepo uses an identical, minimal configuration pattern: a frozen `dataclass` (or nested dataclasses) under `<service>/src/<service>/core/config.py` that reads all runtime values from environment variables via `os.getenv`, exposes a classmethod `from_env()` to construct the settings object, and wraps it in a module-level `@lru_cache(maxsize=1)` accessor named `get_settings()`. The agent-platform is the only exception — its settings live in `runtime_settings.py` and are consumed through `agent_service/core/config.py:get_settings()` which delegates to `RuntimeSettings.from_env()`.

Configuration is layered at deployment time:

1. **Code defaults** — hard-coded defaults inside each frozen dataclass (e.g. `DEFAULT_AGENT_SERVICE_URL = "http://agent-service:8000"`, `store_backend = "memory"`).
2. **Shared runtime env** — `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` provides cluster-wide keys (`OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `IDENTITY_SERVICE_URL`) mounted into every pod.
3. **Per-service runtime config** — one `runtime-config.env` per service under `shared/platform-ops/gitops/dev-k8s/base/<service>/` supplies non-secret knobs (URLs, feature flags, policy paths).
4. **Per-service runtime secrets** — `runtime-secrets.example.env` files document secret keys; actual values are provisioned by shell scripts (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`) into Kubernetes Secrets and never committed to Git.
5. **Kustomize profile overlays** — `shared/platform-ops/gitops/dev-k8s/runtime-profiles/` (default, mutating-dev) swap or merge environment overrides for different deployment modes (e.g. enabling mutating tools requires the `mutating-dev` profile).
6. **Policy bundle** — a single canonical YAML `shared/shared-contracts/policies/policy-default.yaml` is synced to three consumer locations (`tool-gateway`, `platform-gateway`, dev-k8s base) via `make sync-policy`; consumers load it from the path given by their `*_POLICY_PATH` env var.

## Key Files

- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass with provider-specific option subtypes (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`), typed validation in `__post_init__`, and `from_env()` mapping ~30 `AGENTSCOPE_*` / `AGENT_*` env vars.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` with identity/JWKS, delegation, audit, incident, skills, and tool-gateway proxy URLs.
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` covering K8s/Elastic/connectors, redaction, mutation gating, and cross-service client credentials.
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` plus `parse_ingest_clients` / `parse_workload_clients` helpers parsing comma-delimited `client_id=secret,...` lists.
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` mirroring the audit/skills vocabulary (query clients, workload clients, connectors).
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` with strict JSON-parsed `SKILLS_SOURCES` (source_id regex `[a-z0-9][a-z0-9-]*`, duplicate detection, relative-path traversal guard) and `SKILLS_GIT_TOKENS` map.
- `shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env` — per-service non-secret environment files.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared OTel + identity broker endpoint.
- `docs/guides/configuration-reference.md` — authoritative cross-service dependency map, feature activation matrix, secret contracts, and per-variable table.

## Architecture & Conventions

- **Frozen dataclasses**: All settings classes are `@dataclass(frozen=True)`, making them immutable once constructed and safe to share across threads.
- **Single source of truth per service**: Each service has exactly one `config.py` (or `runtime_settings.py`) that owns its env-var vocabulary; no other module calls `os.getenv` directly for configuration.
- **Typed boolean parsing**: Boolean env vars are parsed via `.strip().lower() in {"1", "true", "yes", "on"}` (gateway services) or a shared `_optional_bool` helper that raises `ValueError` on invalid input (agent-platform). Unknown store backends fail startup.
- **Fail-fast validation**: Complex settings raise `SettingsError` (skills-hub, incident-service) or `ValueError` during `from_env()` / `__post_init__` so misconfiguration is caught at process start, not at runtime.
- **Optional features gated by empty URL**: Unset `*_SERVICE_URL` fields leave connectors/routes disabled (e.g. unset `PLATFORM_GATEWAY_SKILLS_HUB_URL` → 503; unset `GATEWAY_ELASTIC_ENABLED` → connector off). This makes features opt-in rather than requiring explicit disable flags.
- **Cross-service credential registries**: Services expose a `*_CLIENTS` env var (comma-separated `client_id=secret,...`) that callers must match against their own `*_CLIENT_ID` / `*_CLIENT_SECRET`. The `configuration-reference.md` documents these contracts explicitly (delegation, audit ingestion, skills query, incidents query, workload identity).
- **Secrets via sync scripts**: No secret value lives in Git. `make deploy` invokes `sync-*` scripts that generate random secrets (or read exported overrides) and write them into per-service `*-runtime-secrets` Kubernetes Secrets.
- **Profile-driven overrides**: Runtime profiles under `runtime-profiles/` select LLM providers and toggle mutating tools; `select-runtime-profile.sh` applies the chosen overlay.

## Conventions & Constraints

- Every service's settings class must provide a `from_env()` classmethod and a module-level `@lru_cache(maxsize=1) get_settings()` accessor — this is enforced by tests that import and call `get_settings()` (see `tests/test_config.py` / `tests/test_runtime_settings.py` patterns across services).
- Environment variable names follow a service-scoped prefix convention: `PLATFORM_GATEWAY_*`, `GATEWAY_*`, `AUDIT_*`, `SKILLS_*`, `INCIDENT_*`, `AGENTSCOPE_*` / `AGENT_*`, `OTEL_*`, `KEYCLOAK_*`, `OIDC_*`.
- Cross-service URLs default to in-cluster DNS names (`http://agent-service:8000`, `http://identity-service:8000`, `http://tool-gateway:8000`, `http://audit-service:8000`, `http://skills-hub:8000`, `http://incident-service:8000`) so deployments need only override when running outside the cluster.
- Policy bundles must stay byte-identical across the three consumer locations; `make validate-policy` enforces schema compliance before syncing.
- Mutating tool activation is intentionally multi-gated: `GATEWAY_MUTATING_TOOLS_ENABLED=true` alone is insufficient — it also requires `GATEWAY_K8S_ENABLED=true`, `AGENT_HITL_CONFIRM_TIMEOUT>0`, the `tools:mutate` policy grant, and pod-delete RBAC (documented as a required checklist in `tool-gateway/runtime-config.env`).
- Store backends (`memory` | `postgres` | `redis`) are validated at startup; unknown values cause startup failure.
- Secrets are never committed: `*.example.env` files exist only as documentation; real values come from `*-runtime-secrets` Kubernetes Secrets provisioned by `sync-*` scripts.