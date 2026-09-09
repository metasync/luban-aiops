---
kind: configuration_system
name: Environment-Driven Per-Service Configuration with Kustomize Profiles and GitOps Secret Sync
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env
    - shared/shared-contracts/policies/policy-default.yaml
---

## What system/approach is used

The platform uses a **pure environment-variable configuration model** layered on top of Kubernetes ConfigMaps and Secrets, orchestrated through Kustomize overlays. Each Python service defines its own frozen `dataclass` settings object that reads from `os.getenv()` at process startup, validated in `__post_init__`, and cached via an `@lru_cache(maxsize=1)` accessor (`core/config.py`). There are no YAML/TOML config files consumed by the services at runtime; all behavior is driven by environment variables.

Configuration is provisioned in two layers:
- **ConfigMaps** (non-secret knobs) live under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` and are mounted into each pod's container env.
- **Secrets** (API keys, client secrets, signing keys) are provisioned by shell scripts under `shared/platform-ops/gitops/` (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-incident-secrets.sh`, `sync-skills-secrets.sh`, `sync-browser-credentials.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`) which generate random values or read them from exported variables and write them into per-service K8s `Secret` objects.

A third layer — **Kustomize runtime profiles** under `shared/platform-ops/gitops/runtime-profiles/` — merges additional env vars to toggle optional capabilities without changing base manifests (e.g. `mutating-dev` enables `GATEWAY_MUTATING_TOOLS_ENABLED=true`; `browser-dev` enables `GATEWAY_BROWSER_ENABLED=true` plus a Chromium sidecar).

Policy bundles are a special case: they are **file-based** YAML loaded from a path configured via `*_POLICY_PATH` (default `/etc/luban/policy/policy.yaml`), with one canonical source `shared/shared-contracts/policies/policy-default.yaml` that is byte-synced to both gateways' packaged defaults and the dev overlay via `make sync-policy`. The bundle has no hot reload — changes take effect only after pod restart.

## Key files and packages

- Per-service settings loaders: `products/*/src/*_service/core/config.py` (thin `get_settings()` wrappers) and the heavy-lifting dataclasses in `products/agent-platform/src/agent_service/runtime_settings.py`, `products/platform-gateway/src/platform_gateway/core/config.py`, and analogous `core/config.py` files in every other service.
- Shared runtime defaults: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (OTel endpoint + identity broker URL shared by all pods).
- Per-service runtime configs: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` for each of agent-platform, platform-gateway, tool-gateway, identity-broker, audit-service, skills-hub, incident-service, execution-runtime.
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-*.sh`.
- Policy bundle: `shared/shared-contracts/policies/policy-default.yaml` (canonical) plus replicas in each gateway's package and the dev overlay.
- Authoritative cross-service dependency map: `docs/guides/configuration-reference.md`.

## Architecture and conventions

1. **One dataclass per service.** Each service exposes a frozen `dataclass` (e.g. `RuntimeSettings`, `PlatformGatewaySettings`) whose fields have sensible defaults and whose `from_env()` classmethod maps `os.getenv(<VAR>, <default>)` to typed values. A module-level `@lru_cache(maxsize=1)` `get_settings()` function provides a singleton accessor.
2. **Validation in `__post_init__`.** All numeric bounds, allowed choices, and IANA timezone parsing are enforced at construction time; invalid configuration raises `ValueError` and fails startup rather than degrading silently.
3. **Feature flags are boolean env vars parsed as strict booleans.** Values accepted for true: `"1"`, `"true"`, `"yes"`, `"on"` (case-insensitive); false: `"0"`, `"false"`, `"no"`, `"off"`. Unknown strings raise `ValueError`.
4. **Optional features degrade gracefully by default.** Unset URLs leave connectors unregistered or routes fail-closed (503); unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing; unset `AGENT_EXECUTION_WORKER_URL` rejects mutating resumes with `worker_unavailable` instead of falling back to in-process execution.
5. **Cross-service credentials use a shared-secret registry pattern.** Each consumer service stores `<SERVICE>_CLIENT_ID` / `<SERVICE>_CLIENT_SECRET` env vars; the provider service (identity-service, audit-service, skills-hub, incident-service) maintains a registry string like `client_id=secret,...` in its own `*-runtime-secrets` Secret. Provisioning scripts ensure the two sides match.
6. **Kustomize profile overlays enable optional capabilities.** Base manifests stay deny-by-default; capability toggles (mutating tools, browser web-checks, LLM providers) are applied via profile overlays merged into `platform-runtime-config`.
7. **Policy bundles are immutable at runtime.** The canonical YAML is synced to consumers; there is no hot reload, and a missing/invalid bundle fails startup (`PolicyLoadError`).
8. **Secrets never live in Git.** All sensitive material is generated by `sync-*.sh` scripts and stored in K8s Secrets; `.env.example` files document required keys but contain no real values.
9. **Shared OTel configuration is centralized.** `shared/runtime.env` sets `OTEL_ENABLED` and `OTEL_EXPORTER_OTLP_ENDPOINT` once; per-service `OTEL_EXPORTER_OTLP_HEADERS` auth headers are injected via each service's runtime-secrets Secret.

## Conventions and constraints

- Every service's configuration is documented in `docs/guides/configuration-reference.md`, which serves as the authoritative cross-service variable dependency map and secret contract reference. Changes to env var behavior must be reflected there.
- Feature activation requires **all** prerequisites to be set simultaneously (e.g. enabling mutating tools requires `GATEWAY_MUTATING_TOOLS_ENABLED=true` AND `tools:mutate` policy grant AND RBAC AND `AGENT_HITL_CONFIRM_TIMEOUT>0`); partial configuration leaves the feature disabled.
- Cross-service secret contracts are enforced by provisioning scripts: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match the `platform-gateway` entry in `IDENTITY_SERVICE_CLIENTS`; `*_AUDIT_CLIENT_SECRET` must match the corresponding entry in `AUDIT_INGEST_CLIENTS`; `GATEWAY_SKILLS_CLIENT_SECRET` must match `tool-gateway` in `SKILLS_QUERY_CLIENTS`; etc.
- Runtime profiles are selected via `shared/platform-ops/gitops/select-runtime-profile.sh <profile-name>`; only one LLM profile is active at a time, but `mutating-dev` and `browser-dev` postures merge permanently alongside the active profile.
- Policy bundle edits follow a strict workflow: edit canonical file → bump `version` → update `policy-scenarios.yaml` if grants change → run `make sync-policy` → verify with `make verify` → commit all synced copies together → deploy; `make verify` enforces byte-parity between canonical and replicas.
- Unknown backend values for store backends (`SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND`, `INCIDENT_STORE_BACKEND`) fail startup; unknown values for `AGENTSCOPE_PROVIDER` fail startup with a list of supported providers.