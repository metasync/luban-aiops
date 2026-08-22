---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Kustomize Profiles and GitOps Secret Provisioning
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
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/deepseek/configmap.yaml
    - shared/shared-contracts/policies/policy-default.yaml
    - docs/guides/configuration-reference.md
---

## What system/approach is used

Every microservice in the platform implements a **pure environment-variable configuration layer** using Python `dataclasses` decorated as `frozen=True`, loaded at process start via a module-level `@lru_cache(maxsize=1)` accessor named `get_settings()`. There is no YAML/JSON config file consumed by the services at runtime; all behavior is driven by `os.getenv()` calls inside each service's `core/config.py` (or, for the agent-platform, `runtime_settings.py`). Configuration values are injected into pods through Kubernetes ConfigMaps and Secrets mounted as environment variables, orchestrated by Kustomize overlays under `shared/platform-ops/gitops/`.

## Key files and packages

- Per-service settings modules: `products/{agent-platform,platform-gateway,audit-service,identity-broker,incident-service,skills-hub,tool-gateway}/src/{service_name}/core/config.py` plus `products/agent-platform/src/agent_service/runtime_settings.py`.
- Shared runtime env: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (OTLP endpoint, shared identity broker URL).
- Runtime profiles (LLM backends): `shared/platform-ops/gitops/runtime-profiles/{dashscope,deepseek,openai}/configmap.yaml` which set `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL`.
- Service-specific runtime-config fragments: e.g. `shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env` referenced from deployment manifests.
- Policy bundle (the only non-env configuration artifact consumed at runtime): `shared/shared-contracts/policies/policy-default.yaml`, copied to each consumer's `policies/policy-default.yaml` and mounted at `/etc/luban/policy/policy.yaml`.
- Authoritative cross-service variable map: `docs/guides/configuration-reference.md`.
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-*-secrets.sh` (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`).

## Architecture and conventions

### Frozen dataclass + lru_cache pattern
Each service defines one frozen dataclass (e.g. `PlatformGatewaySettings`, `AuditSettings`, `IncidentSettings`, `IdentitySettings`, `GatewaySettings`, `RuntimeSettings`) whose fields carry sensible defaults. A classmethod `from_env()` reads every field from `os.getenv(<VAR>, <default>)`, performing type coercion (`int`, `float`, boolean parsing) inline. A module-level `@lru_cache(maxsize=1)` function `get_settings()` returns a singleton instance so the parsed config is read once per process lifetime. The agent-platform additionally validates bounds in `__post_init__` (e.g. `max_iters >= 1`, `context_trigger_ratio` in `(0, 0.9)`, valid IANA timezone), raising `ValueError` at startup — this is the enforcement mechanism for invalid configuration.

### Boolean parsing convention
Booleans are normalized via `.strip().lower() in {"1", "true", "yes", "on"}` across services (gateway auth flags, mutating tools, redaction, Elastic TLS verification). The agent-platform helper `_optional_bool` also recognizes `{"0", "false", "no", "off"}` and raises `ValueError` on unknown values, providing stricter validation for optional booleans.

### Comma-separated list parsing
Multi-value settings use a compact wire format parsed at load time:
- `AUDIT_INGEST_CLIENTS`: `client_id=secret,...`
- `IDENTITY_SERVICE_CLIENTS`: `client_id:secret:aud1|aud2,...`
- `*_WORKLOAD_CLIENTS`: `subject=client_id[:aud1|aud2],...`
- `INCIDENT_CONNECTORS`: comma list of connector names
- `SKILLS_SOURCES`: JSON string
This avoids per-entry env vars while remaining shell-friendly.

### Feature toggles via empty-string opt-in
Optional integrations are disabled when their URL/env var is unset or empty: `AUDIT_STORE_BACKEND="memory"` when no DB URL is set, `GATEWAY_ELASTIC_ENABLED=false` default, unset `PLATFORM_GATEWAY_TOOL_GATEWAY_URL` leaves portal Tools route 503, unset `GATEWAY_SKILLS_SERVICE_URL` unregisters skills tools. This makes features additive without breaking deployments that omit them.

### Kustomize profile overlays for LLM backends
The agent-platform supports pluggable providers (`dashscope`, `deepseek`, `openai`) via Kustomize overlays. Each profile is a `ConfigMap` named `agent-platform-runtime-profile` containing `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL`. Only one profile is active at a time; switching is done via `shared/platform-ops/gitops/select-runtime-profile.sh <profile-name>`.

### Policy as the sole non-env runtime artifact
Policy decisions are enforced by both `platform-gateway` and `tool-gateway` reading a YAML bundle from `GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH`, defaulting to `/etc/luban/policy/policy.yaml`. The canonical source is `shared/shared-contracts/policies/policy-default.yaml`; it is validated against a JSON schema (`make validate-policy`) and synced to all consumers (`make sync-policy`). Consumers must keep the file byte-identical.

### Secret contracts and provisioning
Secrets are never committed to Git. Cross-service credentials are provisioned by `make deploy` calling dedicated `sync-*-secrets.sh` scripts that generate random shared secrets (or accept exported overrides like `DELEGATION_CLIENT_SECRET`, `AUDIT_INGEST_SECRET`, `SKILLS_GIT_TOKEN`) and create Kubernetes `Secret` objects. Each script writes matching entries on both sides of the contract (e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS`, `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`). Opt-out is possible via `SKIP_*_SECRETS=true`.

### Documentation-driven configuration reference
`docs/guides/configuration-reference.md` is the authoritative cross-service dependency map: it documents every environment variable, its purpose, default, source (ConfigMap vs runtime secret), and the cross-service chains (token delegation, identity verification, tool relay, audit ingestion, skills retrieval, incident intake, mutating action approval). It is the single source operators consult to understand what must be configured and where.

## Conventions and constraints

- **One setting module per service** under `src/<service>/core/config.py` (or `runtime_settings.py` for agent-platform); no shared settings library — each service owns its own frozen dataclass.
- **All settings are immutable**: dataclasses are `frozen=True`; there is no mutable global state for configuration.
- **Startup-time validation**: Invalid values raise `ValueError` during `from_env()` / `__post_init__`, failing fast before the service starts serving requests (e.g. unsupported provider, out-of-range ratios, invalid IANA timezone).
- **Unknown store backends fail startup**: `SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND`, `INCIDENT_STORE_BACKEND` reject unknown values at parse time.
- **Feature gating by absence**: Optional integrations are disabled by leaving their URL/env var unset rather than requiring an explicit `false` flag, except for explicit feature flags like `*_ENABLED`.
- **Cross-service secrets are paired**: Every emitter's `*_AUDIT_CLIENT_SECRET`, `*_CLIENT_SECRET`, or OIDC client secret must match the corresponding registry entry in the receiving service's `*_CLIENTS` env var; mismatches cause authentication failures at runtime.
- **Policy files must stay byte-identical** across all consumer locations; deviation breaks policy enforcement consistency.
- **No runtime reload**: Because settings are cached via `lru_cache`, changing environment variables requires a pod restart; there is no hot-reload mechanism.