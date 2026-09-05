---
kind: configuration_system
name: Environment-Driven Frozen Settings with GitOps Overlay and Secret Provisioning
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/shared-contracts/policies/policy-default.yaml
    - docs/guides/configuration-reference.md
---

# Configuration System

## Approach

Each microservice in the Luban platform loads its configuration exclusively from **environment variables** via a single `core/config.py` module per service. There is no YAML/JSON config file parsing at runtime; files are only used as deployment manifests (Kustomize overlays) that mount environment variables into pods. The pattern is:

1. A `@dataclass(frozen=True)` settings class defines every configurable field with sensible defaults.
2. A `from_env()` classmethod reads values from `os.getenv`, casting types and applying per-field validation.
3. A `@lru_cache(maxsize=1)`-wrapped `get_settings()` function provides a process-wide singleton.
4. Optional `__post_init__` or custom parsers enforce invariants (e.g. `EXECUTION_STATE_STORE_BACKEND` must be one of `{memory, postgres}`, positive integers, non-empty DB URLs when required).

Services implement this consistently: `PlatformGatewaySettings`, `AuditSettings`, `ExecutionSettings`, `IncidentSettings`, `SkillsSettings`, `GatewaySettings` (tool-gateway), plus identity-broker and agent-service equivalents.

## Key Files

- Per-service config loaders: `products/*/src/*/core/config.py` (and `agent_service/runtime_settings.py`).
- Shared runtime env: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — injected into every pod (`OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `IDENTITY_SERVICE_URL`).
- Per-service runtime ConfigMaps: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — non-secret knobs mounted as env vars.
- Per-service secret examples: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-secrets.example.env` — documents secret keys provisioned by scripts.
- Runtime profile overlay: `shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml` — LLM provider selection (`AGENTSCOPE_PROVIDER/MODEL_NAME/BASE_URL`).
- Policy bundle (configuration-as-code): `shared/shared-contracts/policies/policy-default.yaml`, replicated to both gateways and dev overlay via `make sync-policy`.
- Authoritative cross-service reference: `docs/guides/configuration-reference.md` — feature activation matrix, dependency chains, per-service variable tables, secret contracts, rollout workflow.
- Secret provisioning scripts under `shared/platform-ops/gitops/sync-*.sh` (audit, skills, incident, delegation, OTel, browser credentials, execution signing/handoff).

## Architecture and Conventions

### Layering
- **Defaults** live in Python dataclass default values (e.g. `store_backend = "memory"`, `require_auth = True`, `identity_jwks_cache_seconds = 300`).
- **Non-secret runtime config** lives in per-service `runtime-config.env` files under `dev-k8s/base/<service>/`, mounted into pods.
- **Secrets** live in Kubernetes Secrets created by `sync-*.sh` scripts; never committed to Git. Each service has its own `*-runtime-secrets` Secret (e.g. `platform-gateway-runtime-secrets`, `audit-service-runtime-secrets`).
- **Shared knobs** (OTel, identity broker URL) go in `base/shared/runtime.env` so every pod gets them uniformly.
- **Runtime profiles** (LLM provider selection) are Kustomize overlays under `runtime-profiles/<profile>/`; switching uses `select-runtime-profile.sh`.
- **Policy bundles** are the only non-env configuration consumed at runtime: a YAML file mounted at a configured path (`GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH`) and loaded once at startup — no hot reload.

### Cross-Service Contracts
Configuration is not isolated per service; many features require matching pairs across services:
- **Token delegation**: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry.
- **Audit ingestion**: each emitter's `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` registry.
- **Skills query**: `GATEWAY_SKILLS_CLIENT_SECRET` / `PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`.
- **Incidents query**: `PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET` / `GATEWAY_INCIDENTS_CLIENT_SECRET` / `AGENT_INCIDENT_CLIENT_SECRET` ↔ `INCIDENT_QUERY_CLIENTS`.
- **Browser credentials**: `GATEWAY_BROWSER_CREDENTIAL_SETS` points to a mounted JSON file containing credential sets.
- **Execution signing/handoff**: `AGENT_EXECUTION_SIGNING_KEY` ↔ `EXECUTION_SIGNING_KEY`; `AGENT_EXECUTION_HANDOFF_TOKEN` ↔ `EXECUTION_HANDOFF_TOKEN`.

The configuration reference document diagrams these chains explicitly and documents which side fails closed when a link is missing.

### Validation Strategy
- **Fail-fast on invalid values**: unknown store backends, negative timeouts, malformed JSON for `SKILLS_SOURCES`/`SKILLS_GIT_TOKENS`, duplicate `source_id` values all raise exceptions at startup.
- **Graceful degradation for optional dependencies**: unset `*_AUDIT_SERVICE_URL` degrades to log-only auditing; unset `*_SERVICE_URL` leaves routes fail-closed (503); unset `INCIDENT_WEBHOOK_TOKEN` disables intake.
- **Post-init constraints**: `ExecutionSettings.__post_init__` enforces `gateway_timeout_seconds > 0`, valid `state_store_backend`, required `state_db_url` when backend is `postgres`, and `flight_retention_seconds >= 1`.

### Boolean and List Parsing Conventions
- Booleans use a truthy set `{"1", "true", "yes", "on"}` parsed via `.strip().lower() in {...}`.
- Comma-separated lists are split and stripped (e.g. `browser_allow_origins`, `connectors`).
- Complex structures use JSON strings: `SKILLS_SOURCES` (list of source specs), `SKILLS_GIT_TOKENS` (map), `AUDIT_INGEST_CLIENTS` / `*_QUERY_CLIENTS` (`client_id=secret,...` tuples parsed by helper functions).

## Conventions and Constraints

- **Every setting is an environment variable.** No `.env` files, no `.yaml` config files read by the application at runtime. Deployment-time configuration is expressed entirely through Kustomize overlays and Kubernetes ConfigMaps/Secrets.
- **Settings objects are immutable** (`frozen=True` dataclasses) and cached via `lru_cache(maxsize=1)`, guaranteeing a single process-wide instance.
- **Secrets are never inline.** All sensitive values (API keys, client secrets, tokens, headers) come from Kubernetes Secrets provisioned by `sync-*.sh` scripts; example files end in `.example.env` and are not deployed.
- **Feature flags are explicit.** A capability is active only when *all* required variables are set to non-empty values, as documented in the Feature Activation Matrix in the configuration reference.
- **Policy bundles are canonical and versioned.** `shared/shared-contracts/policies/policy-default.yaml` is the single source of truth; `make sync-policy` replicates it byte-identically to consumer locations, and `make verify` enforces parity.
- **Profiles decouple LLM providers from deployments.** The active profile is selected via `select-runtime-profile.sh`, which swaps a ConfigMap; mutating-dev and browser-dev postures merge permanently alongside the active profile.
- **Cross-service secrets are coordinated by scripts.** `make deploy` orchestrates `sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-browser-credentials.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh` to generate matching pairs and register clients in the appropriate registries.