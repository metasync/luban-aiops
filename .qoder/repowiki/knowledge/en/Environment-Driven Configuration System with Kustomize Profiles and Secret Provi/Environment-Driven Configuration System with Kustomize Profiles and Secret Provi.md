---
kind: configuration_system
name: Environment-Driven Configuration System with Kustomize Profiles and Secret Provisioning
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - docs/guides/configuration-reference.md
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/platform-ops/gitops/select-runtime-profile.sh
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/platform-ops/gitops/sync-browser-credentials.sh
    - shared/platform-ops/gitops/sync-email-secrets.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
    - shared/platform-ops/gitops/sync-runtime-secret.sh
    - shared/shared-contracts/policies/policy-default.yaml
---

# Configuration System

## Approach

The Luban platform uses a **pure environment-variable configuration model** — no YAML/JSON config files are parsed at runtime. Each Python service defines frozen `dataclass` settings objects that read exclusively from `os.environ` via `from_env()` classmethods, wrapped in an `lru_cache(maxsize=1)` singleton (`get_settings()`). Values are validated eagerly in `__post_init__`, so misconfiguration fails at process startup rather than at first use.

Configuration is layered through **Kustomize overlays** under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` (ConfigMap-backed env) plus per-service `runtime-secrets.example.env` templates. A separate `shared/platform-ops/gitops/runtime-profiles/` directory provides pluggable LLM backends (`default`, `browser-dev`, `mutating-dev`, `secrets-dev`) selected via `select-runtime-profile.sh`. The base overlay stays deny-by-default; profiles merge additive flags on top.

Secrets are never committed to Git. They are provisioned as Kubernetes `Secret` objects by dedicated shell scripts under `shared/platform-ops/gitops/sync-*.sh` (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-browser-credentials.sh`, `sync-email-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`).

## Key Files

- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass, the largest settings surface (LLM providers, kernel tuning, HITL, evidence caps, execution worker/admission, skills/incident clients, authoring-trace bounds)
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` (connectors: k8s, browser, HTTP, secrets/password generation, email, Ansible MCP-ingestion)
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` (identity broker, delegation, policy path, audit/incident/skills proxies)
- `docs/guides/configuration-reference.md` — authoritative cross-service variable dependency map, secret contracts, feature activation matrix, and per-service tables
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — default env for each service
- `shared/platform-ops/gitops/runtime-profiles/` — profile overlays (default, browser-dev, mutating-dev, secrets-dev)
- `shared/platform-ops/gitops/sync-*.sh` — secret provisioning scripts
- `shared/shared-contracts/policies/policy-default.yaml` — canonical policy bundle (not runtime config, but part of the same deployment artifact lifecycle)

## Architecture and Conventions

### Per-service settings modules

Every service follows the same pattern:

1. A `core/config.py` (or equivalent) defines a frozen `dataclass` with typed defaults.
2. A `from_env()` classmethod reads every field from `os.getenv(name, default)`.
3. A module-level `@lru_cache(maxsize=1) def get_settings()` returns the cached singleton.
4. `__post_init__` validates ranges, enums, and cross-field invariants (e.g. `AGENT_EXECUTION_ADMISSION_ENABLED` requires both `AGENT_EXECUTION_STATE_DB_URL` and `AGENT_EXECUTION_ADMISSION_EPOCH`; password-policy overrides may only tighten the contract).

The agent-service's `RuntimeSettings` is the most complex, with provider-specific option subclasses (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) selected by `provider_options_type(self.provider)` and validated against the active `AGENTSCOPE_PROVIDER`.

### Boolean parsing convention

Boolean env vars accept `1`, `true`, `yes`, `on` (case-insensitive); empty or unset means false unless explicitly optional. The agent-service helper `_optional_bool` raises `ValueError` on non-empty unrecognized values, while gateway helpers accept a default string.

### Feature gating

Most features are opt-in via boolean env vars that gate tool registration or connector wiring:
- `GATEWAY_K8S_ENABLED`, `GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_BROWSER_ENABLED`, `GATEWAY_HTTP_ENABLED`, `GATEWAY_SECRETS_ENABLED`, `GATEWAY_ELASTIC_ENABLED`
- `AGENT_MODEL_DISCOVERY_ENABLED`, `AGENTSCOPE_TASK_TOOLS_ENABLED`, `AGENTSCOPE_COMPRESS_CONTEXT_ENABLED`
- `EXECUTION_ADMISSION_ENABLED`, `AGENT_EXECUTION_ADMISSION_ENABLED`

Unset connectors stay unregistered and their routes fail closed (503) rather than degrading silently.

### Cross-service credential contracts

Inter-service auth is configured as paired env vars across services:
- Token delegation: `PLATFORM_GATEWAY_SERVICE_CLIENT_ID` / `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS`
- Audit ingestion: `*_AUDIT_CLIENT_ID` / `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`
- Skills query: `GATEWAY_SKILLS_CLIENT_ID` / `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`
- Incident query: `*_INCIDENT_CLIENT_ID` / `*_INCIDENT_CLIENT_SECRET` ↔ `INCIDENT_QUERY_CLIENTS`

Each consumer registers its own client id (e.g. `tool-gateway`, `platform-gateway`, `agent-service`, `execution-runtime`) and the server holds a `client_id=secret,...` registry.

### Policy bundle lifecycle

The action-authorization bundle has one canonical copy at `shared/shared-contracts/policies/policy-default.yaml`, replicated byte-identically to both gateways' packaged defaults and the dev-k8s GitOps overlay by `make sync-policy`. Contract tests fail `make verify` on drift. Consumers load it from `GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH` (default `/etc/luban/policy/policy.yaml`); a missing or invalid bundle fails startup (`PolicyLoadError`, no silent fallback).

### Runtime profiles

Profiles are Kustomize overlays applied alongside the base. Only one LLM profile is active at a time, selected via `select-runtime-profile.sh <profile-name>`. Two non-LLM postures (`mutating-dev`, `browser-dev`) ride permanently and merge their env into `platform-runtime-config`. The profile's `runtime-secrets.example.env` documents the active provider key plus multi-model catalog knobs.

### Secrets delivery

Secrets live in Kubernetes `Secret` objects mounted as env vars or file paths:
- `agent-platform-runtime-secrets`, `execution-signing-secret`, `execution-handoff-secret`, `platform-gateway-runtime-secrets`, `identity-service-runtime-secrets`, `tool-gateway-runtime-secrets`, `tool-gateway-browser-credentials`, `audit-service-runtime-secrets`, `skills-hub-runtime-secrets`, `incident-service-runtime-secrets`
- File-based secrets include `GATEWAY_PASSWORD_POLICY_PATH`, `GATEWAY_BROWSER_CREDENTIAL_SETS`, `GATEWAY_HTTP_CREDENTIAL_SETS`, `GATEWAY_EMAIL_PASSWORD`, `OTEL_EXPORTER_OTLP_HEADERS`

## Conventions and Constraints

- **Rule:** All runtime configuration comes from environment variables read via `os.getenv`; no `.env` files, YAML configs, or JSON configs are parsed at runtime. Enforced by the design of every `from_env()` method.
- **Rule:** Settings classes are `frozen=True` dataclasses with defaults declared inline; mutation happens only during construction.
- **Rule:** Unknown enum values (e.g. `SESSION_STORE_BACKEND`, `SECRET_DELIVERY_BACKEND`, `AGENTSCOPE_PROVIDER`, `GATEWAY_ANSIBLE_MCP_TRANSPORT`) raise `ValueError` at startup rather than falling back.
- **Rule:** Mutating features are deny-by-default: `GATEWAY_MUTATING_TOOLS_ENABLED=false`, `GATEWAY_BROWSER_ENABLED=false`, `GATEWAY_HTTP_ENABLED=false`, `GATEWAY_SECRETS_ENABLED=false`, `AGENT_EXECUTION_ADMISSION_ENABLED=false`, `EXECUTION_ADMISSION_ENABLED=false`.
- **Rule:** Missing required cross-service credentials fail closed (not degrade): absent `AGENT_EXECUTION_SIGNING_KEY` rejects mutating resumes with `signing_unavailable`; absent `AGENT_EXECUTION_WORKER_URL` / `AGENT_EXECUTION_HANDOFF_TOKEN` rejects with `worker_unavailable`; unset incident/skills URLs return 503.
- **Rule:** Password-policy env overrides (`GATEWAY_PASSWORD_MIN_LENGTH`, `GATEWAY_PASSWORD_REQUIRED_CLASSES`) may only tighten the contract; `__post_init__` raises if they weaken it.
- **Rule:** The policy bundle at `shared/shared-contracts/policies/policy-default.yaml` is the single source of truth; replicas must be kept byte-identical via `make sync-policy` and verified by `make verify`.
- **Rule:** Secrets are provisioned as Kubernetes `Secret` objects via `sync-*.sh` scripts and never committed to Git; `runtime-secrets.example.env` files are templates only.
- **Rule:** OTel push is enabled by default (`OTEL_ENABLED=true`) but anonymous pushes without `OTEL_EXPORTER_OTLP_HEADERS` fail open (401 from OpenObserve), requiring explicit provisioning via `sync-otel-secrets.sh`.
- **Rule:** Durable execution admission requires coordinated enablement on agent, worker, and Postgres catalog with matching epochs; partial enablement refuses startup rather than silently degrading.