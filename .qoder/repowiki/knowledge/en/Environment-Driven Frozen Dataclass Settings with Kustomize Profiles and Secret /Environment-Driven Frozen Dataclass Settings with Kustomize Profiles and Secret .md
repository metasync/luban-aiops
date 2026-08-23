---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Kustomize Profiles and Secret Provisioning
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/agent-platform/src/agent_service/core/config.py
    - docs/guides/configuration-reference.md
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/runtime-profiles/openai/kustomization.yaml
    - shared/shared-contracts/policies/policy-default.yaml
---

## What System/Approach Is Used

Every Python service in the platform implements an identical, lightweight configuration subsystem built on three primitives:

1. **Frozen `dataclass` settings objects** — each service defines a single frozen dataclass (e.g. `PlatformGatewaySettings`, `AuditSettings`, `IncidentSettings`, `SkillsSettings`, `IdentitySettings`, `GatewaySettings`) whose fields are typed defaults.
2. **`from_env()` classmethod + `@lru_cache(maxsize=1)` accessor** — `get_settings()` is imported once at startup; values are read from `os.getenv(...)` with per-field defaults. Complex fields (comma-separated client registries, JSON lists/maps) are parsed by dedicated helpers (`parse_ingest_clients`, `parse_workload_clients`, `parse_sources`, `_parse_service_clients`, etc.).
3. **Kubernetes-native deployment via Kustomize overlays** — runtime config lives in per-service `runtime-config.env` files under `shared/platform-ops/gitops/dev-k8s/base/<service>/`; secrets live in `runtime-secrets.example.env` plus generated K8s Secrets mounted as env vars. Agent LLM backends are selected via Kustomize profile overlays under `shared/platform-ops/gitops/runtime-profiles/<provider>/`.

There is no external configuration library (no Pydantic, no dynaconf, no python-dotenv). The entire stack is stdlib + Kustomize.

## Key Files and Packages

- Per-service settings modules: `products/*/src/*/core/config.py` (and `agent-platform/src/agent_service/core/config.py` which delegates to `RuntimeSettings.from_env()`).
- Cross-service configuration reference: `docs/guides/configuration-reference.md` — the authoritative map of every environment variable, its purpose, default, source file, and cross-service secret contracts.
- Deployment manifests and env sources: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`, `runtime-secrets.example.env`, and `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`.
- Policy bundles: canonical `shared/shared-contracts/policies/policy-default.yaml`, mirrored into `products/*/policies/policy-default.yaml` and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`.
- Runtime profiles: `shared/platform-ops/gitops/runtime-profiles/{openai,dashscope,deepseek,mutating-dev}/configmap.yaml` plus `select-runtime-profile.sh` / `verify-runtime-profile.sh`.
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`.

## Architecture and Conventions

### One setting object per service
Each service exposes exactly one `get_settings()` cached function returning a frozen dataclass. Consumers import it and never call `from_env()` directly. This makes settings immutable after process start and guarantees a single source of truth per pod.

### Environment variables are the only input surface
All configuration flows through `os.getenv`. There are no `.env` files loaded at runtime, no YAML/JSON config files consumed by the settings layer (policy bundles are separate static assets referenced by path). Boolean flags are normalized via `.strip().lower() in {"1", "true", "yes", "on"}`. Unknown store backends fail fast because they are passed straight to downstream constructors that validate them.

### Complex fields use dedicated parsers
Comma-separated key=value registries (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `*_WORKLOAD_CLIENTS`) are parsed by small helper functions that split on `,`, then partition on `=` or `:`. JSON arrays/maps (`SKILLS_SOURCES`, `SKILLS_GIT_TOKENS`) are parsed with `json.loads` and validated eagerly, raising a per-service `SettingsError` on malformed input so misconfiguration fails at startup rather than silently later.

### Cross-service secrets are paired, not self-contained
The configuration reference documents explicit secret contracts between services:
- Token delegation: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match the `client_id:secret:audience` entry for `platform-gateway` in `IDENTITY_SERVICE_CLIENTS`.
- Audit ingestion: each emitter's `*_AUDIT_CLIENT_SECRET` must match the corresponding `client_id=secret` in `AUDIT_INGEST_CLIENTS`.
- Skills/incidents query: gateway/client secrets must match entries in the target service's `*_QUERY_CLIENTS` registry.
Secret provisioning is centralized in `sync-*-secrets.sh` scripts that generate random shared secrets and write matching K8s Secrets to both sides.

### Policy bundles are versioned separately from runtime config
Policy YAML is the canonical source of truth for authorization rules and is kept byte-identical across consumers via `make sync-policy`. It is mounted as a file path (`GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH`) rather than injected as env vars.

### Agent LLM provider is selected by Kustomize profile
The agent-service reads `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_PROFILE`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL`, `AGENTSCOPE_API_KEY` from ConfigMaps mounted by the active profile overlay under `runtime-profiles/<name>/`. Switching providers is a Kustomize operation, not a runtime env change.

## Conventions and Constraints

- **Frozen settings**: all settings dataclasses are `frozen=True`; mutation after construction is impossible.
- **Single cache**: `get_settings()` uses `@lru_cache(maxsize=1)` so settings are loaded once per process lifetime.
- **Fail-fast validation**: malformed JSON in `SKILLS_SOURCES` / `SKILLS_GIT_TOKENS`, unknown `*_STORE_BACKEND` values, and invalid `source_id` patterns raise exceptions during `from_env()` so bad configuration crashes the container immediately.
- **Feature toggles via env**: optional capabilities (Elastic connector, mutating tools, workload identity, HITL confirmation bridging, policy enforcement) are enabled by setting their respective `*_ENABLED` / `*_PATH` env vars to truthy values; unset means disabled.
- **Defaults encode dev-k8s behavior**: most defaults point to in-cluster DNS names (`http://identity-service:8000`, `http://agent-service:8000`, `http://tool-gateway:8000`) and `memory` stores, making local `make deploy` work without extra config.
- **Secrets never committed**: the reference explicitly states secrets are provisioned as Kubernetes Secrets via `sync-*` scripts and must not be checked into Git; example files end in `.example.env`.
- **Cross-boundary consistency enforced by docs + scripts**: the configuration reference is the authoritative contract; provisioning scripts enforce the pairing of secrets across services.
- **Policy bundle synchronization**: `make validate-policy` and `make sync-policy` enforce that the canonical `shared/shared-contracts/policies/policy-default.yaml` stays in sync with consumer copies.