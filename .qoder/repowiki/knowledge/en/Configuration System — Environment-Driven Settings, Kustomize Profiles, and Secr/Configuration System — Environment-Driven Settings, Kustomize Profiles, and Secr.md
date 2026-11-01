---
kind: configuration_system
name: Configuration System — Environment-Driven Settings, Kustomize Profiles, and Secret Provisioning
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
    - shared/platform-ops/gitops/sync-browser-credentials.sh
    - shared/platform-ops/gitops/sync-ansible-credentials.sh
    - shared/platform-ops/gitops/sync-servicenow-credentials.sh
    - shared/platform-ops/gitops/sync-email-secrets.sh
---

# Configuration System

## Approach

The Luban Agentic AIOps platform uses a **pure environment-variable configuration model** with no YAML/JSON config files consumed at runtime by the Python services. Each service defines its own frozen `dataclass` settings object (e.g. `RuntimeSettings`, `PlatformGatewaySettings`) that reads values from `os.getenv` in a single `from_env()` classmethod, validates them in `__post_init__`, and exposes an `@lru_cache(maxsize=1)` singleton accessor (`get_settings()`). There is no third-party config library (no pydantic-settings, python-dotenv, dynaconf, etc.) — configuration loading is hand-rolled.

Kubernetes deployment overlays under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` supply non-secret configuration via ConfigMaps; secrets are mounted as separate Kubernetes Secrets or projected token files. Feature toggles, per-service URLs, and behavioral knobs are all environment variables.

## Key Files and Packages

- Per-service settings loaders:
  - `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass, typed provider options (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`), validation of kernel tuning, HITL timeout, execution worker/admission, browser flow TTL, evidence caps, authoring-trace bounds, graduation blast radius.
  - `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings`, cached via `@lru_cache(maxsize=1)`.
  - `products/tool-gateway/src/tool_gateway/core/config.py`
  - `products/execution-runtime/src/execution_runtime/core/config.py`
  - `products/identity-broker/src/identity_service/core/config.py`
  - `products/audit-service/src/audit_service/core/config.py`
  - `products/skills-hub/src/skills_hub/core/config.py`
  - `products/incident-service/src/incident_service/core/config.py`
- Authoritative cross-service variable map: `docs/guides/configuration-reference.md` (Feature Activation Matrix, per-service tables, secret contracts, cross-service dependency chains).
- Dev-Kustomize base overlays: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` (non-secret env) and `runtime-secrets.example.env` (secret templates).
- Runtime profile system: `shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml` plus `sync-runtime-secret.sh`, `select-runtime-profile.sh`, `verify-runtime-profile.sh`.
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-*.sh` (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-browser-credentials.sh`, `sync-ansible-credentials.sh`, `sync-servicenow-credentials.sh`, `sync-email-secrets.sh`).
- Policy bundle canonical source: `shared/shared-contracts/policies/policy-default.yaml` (replicated to gateways via `make sync-policy`; hot reload is explicitly not supported — changes require pod restart).

## Architecture and Conventions

### One setting module per service
Each product package owns its configuration loader under `<package>/core/config.py` (or `runtime_settings.py` for agent-platform). The loader is a frozen dataclass with a `from_env()` constructor and a module-level `get_settings()` cache. Services never read `os.environ` directly outside these modules.

### Validation at startup, fail-closed
Invalid values raise `ValueError` during `__post_init__` rather than being silently coerced. Examples enforced in code:
- `AGENTSCOPE_PROVIDER` must be one of `dashscope|deepseek|openai|luban`.
- `AGENTSCOPE_MAX_ITERS >= 1`, `0 < AGENTSCOPE_CONTEXT_TRIGGER_RATIO < 0.9`, `AGENTSCOPE_TOOL_RESULT_LIMIT >= 1`, `AGENTSCOPE_MODEL_MAX_RETRIES >= 0`.
- `AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS` must be > 0 and ≤ 120.
- Enabling `AGENT_EXECUTION_ADMISSION_ENABLED` requires both `AGENT_EXECUTION_STATE_DB_URL` and `AGENT_EXECUTION_ADMISSION_EPOCH`.
- Unknown `SESSION_STORE_BACKEND` / `AGENT_STATE_STORE_BACKEND` values fail startup; unknown backend names for other services follow the same pattern documented in the reference guide.

### Defaults live in code, overrides in env
Code defaults mirror agentscope's defaults so unset deployments behave identically to the upstream kernel. Dev overlays intentionally leave many knobs unset so code defaults apply (see comments in `dev-k8s/base/agent-platform/runtime-config.env`).

### Two-tier secret handling
- Non-secret configuration → `runtime-config.env` → mounted into pods as ConfigMap/env.
- Secrets → dedicated Kubernetes Secrets (`agent-platform-runtime-secrets`, `platform-gateway-runtime-secrets`, `tool-gateway-runtime-secrets`, `identity-service-runtime-secrets`, `audit-service-runtime-secrets`, `skills-hub-runtime-secrets`, `execution-signing-secret`, `execution-handoff-secret`, `tool-gateway-browser-credentials`, `tool-gateway-ansible-credentials`, `tool-gateway-servicenow-credentials`, …) provisioned by `sync-*.sh` scripts. Secrets are never committed to Git.

### Cross-service credential registries
Inter-service auth follows a shared contract: each consumer sets `<SERVICE>_CLIENT_ID` + `<SERVICE>_CLIENT_SECRET` pointing at a registry on the target service (e.g. `IDENTITY_SERVICE_CLIENTS`, `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`). The `configuration-reference.md` documents every chain (token delegation, audit ingestion, skills retrieval, incident intake) and the exact `client_id=secret,...` format.

### Runtime profiles
Agent-platform supports a deploy-time "profile" concept (`AGENTSCOPE_PROFILE` + `AGENTSCOPE_PROVIDER` + `AGENTSCOPE_MODEL_NAME` + `AGENTSCOPE_BASE_URL`) loaded from a `ConfigMap` named `agent-platform-runtime-profile`. The profile name is decoupled from the provider (SPEC-026 R-5); the default profile hosts `deepseek-v4-flash` against `https://api.deepseek.com`. Additional providers can be added via `<PROVIDER>_API_KEY` / `<PROVIDER>_MODEL_NAME` / `<PROVIDER>_BASE_URL` env vars (SPEC-024).

### Policy bundle rollout
The policy bundle has exactly one canonical copy (`shared/shared-contracts/policies/policy-default.yaml`). It is replicated byte-identically to both gateways' packaged defaults and the dev-k8s overlay by `make sync-policy`. Contract tests enforce parity via `make verify`; drift fails verification. Changes require bumping the `version` field, updating `policy-scenarios.yaml`, syncing, verifying, committing together, then deploying. Loaded bundles are cached keyed on path; there is no hot reload — a changed ConfigMap takes effect only on pod restart. Both gateways expose a SHA-256 fingerprint of the loaded bundle on `/health/ready`.

### Feature activation matrix
Every capability is activated by explicit environment variables; defaults are deny-by-default for mutating surfaces (`GATEWAY_MUTATING_TOOLS_ENABLED=false`, `GATEWAY_BROWSER_ENABLED=false`, `GATEWAY_HTTP_ENABLED=false`, `GATEWAY_ANSIBLE_MCP_ENABLED=false`, `GATEWAY_SERVICENOW_ENABLED=false`, `GATEWAY_DELEGATED_CUSTODY_*` disabled). Optional features degrade gracefully when their dependencies are absent (e.g. unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing; unset `GATEWAY_SKILLS_SERVICE_URL` leaves skills tools unregistered).

## Conventions and Constraints

- **All runtime configuration is passed via environment variables.** No `.yaml`/`.json` config files are consumed by the Python services at runtime; file paths (e.g. `GATEWAY_POLICY_PATH`, `GATEWAY_PASSWORD_POLICY_PATH`, `GATEWAY_BROWSER_CREDENTIAL_SETS`) point to volumes mounted by Kubernetes, not checked out from source.
- **Settings objects are frozen dataclasses with `from_env()` constructors and `__post_init__` validation.** Invalid values fail process startup with a descriptive `ValueError` rather than degrading silently.
- **Secrets are provisioned exclusively through `sync-*.sh` scripts** and stored as Kubernetes Secrets; they are never committed to version control. The `configuration-reference.md` documents which script provisions which secret key.
- **Cross-service client credentials use a uniform `client_id=secret,...` registry format** on the receiving service, documented centrally in `docs/guides/configuration-reference.md`.
- **Policy bundles are immutable after load:** `make sync-policy` enforces byte-parity between the canonical file and gateway replicas; `make verify` fails on drift. Hot reload is deliberately unsupported — operators must rolling-restart workloads.
- **Feature flags are opt-in and deny-by-default:** mutating tool registration, browser/HTTP/Ansible/ServiceNow connectors, delegated custody, and durable admission are all off unless explicitly enabled.
- **Dev overlays intentionally omit knobs to exercise code defaults**, while production overlays (via runtime profiles) pin provider/model endpoints.
- **The authoritative configuration surface is `docs/guides/configuration-reference.md`**: it is the single source of truth for variable names, defaults, sources (runtime-config vs runtime-secrets), and cross-service dependency chains.