---
kind: configuration_system
name: Configuration System — Environment-Driven Settings, GitOps Profiles, and Secret Provisioning
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
    - shared/platform-ops/gitops/runtime-profiles/
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
    - shared/shared-contracts/policies/policy-default.yaml
---

## Approach

Luban has no centralized configuration framework. Each product reads its own settings directly from environment variables via `os.getenv`, validated into frozen dataclasses at startup. Configuration is layered in three stages:

1. **Code defaults** — hard-coded defaults in each service's `core/config.py` or `runtime_settings.py`.
2. **Runtime ConfigMaps** — per-service `runtime-config.env` files under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`, mounted as Kubernetes ConfigMaps.
3. **Secrets** — per-service `runtime-secrets` Kubernetes Secrets provisioned by `sync-*-secrets.sh` scripts; secrets are never committed to Git.
4. **Feature profiles** — Kustomize overlays under `shared/platform-ops/gitops/runtime-profiles/` (e.g. `browser-dev`, `ansible-dev`, `mutating-dev`, `model-router-dev`, `delegated-dev`) that merge additional env vars on top of the base overlay.

There is no `.env` file loader, no YAML config parser for runtime knobs, and no hot reload: a changed ConfigMap takes effect only on pod restart (rolling restart the gateway deployments).

## Key Files

- Per-service settings loaders:
  - `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings.from_env()` with typed `_optional_str/int/float/bool/choice` helpers and extensive `__post_init__` validation.
  - `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings.from_env()` cached via `@lru_cache(maxsize=1)`.
  - `products/tool-gateway/src/tool_gateway/core/config.py`
  - `products/execution-runtime/src/execution_runtime/core/config.py`
  - `products/identity-broker/src/identity_service/core/config.py`
  - `products/audit-service/src/audit_service/core/config.py`
  - `products/skills-hub/src/skills_hub/core/config.py`
  - `products/incident-service/src/incident_service/core/config.py`
- Canonical operator documentation: `docs/guides/configuration-reference.md` (the authoritative cross-service dependency map, feature activation matrix, per-service variable tables, secret contracts, and policy rollout procedure).
- Base runtime configs: `shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env`.
- Feature profile overlays: `shared/platform-ops/gitops/runtime-profiles/{browser-dev,ansible-dev,mutating-dev,model-router-dev,delegated-dev,secrets-dev,servicenow-dev}/kustomization.yaml` + their `.env` files.
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-*.sh` (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-otel-secrets.sh`, `sync-email-secrets.sh`, `sync-runtime-secret.sh`).
- Policy bundle source: `shared/shared-contracts/policies/policy-default.yaml` (replicated byte-identically to both gateways' packaged defaults and dev-k8s by `make sync-policy`).

## Architecture and Conventions

### One env var → one field
Each setting is read from a single uppercase snake_case environment variable. There is no nested config object hierarchy in code; cross-service dependencies are documented as flat variable names in `configuration-reference.md`. Boolean parsing accepts `1|true|yes|on` / `0|false|no|off`; unknown values raise `ValueError`.

### Validation-at-startup, fail-closed
Every service validates required combinations in `__post_init__` or `from_env`. Examples enforced by code:
- `AGENTSCOPE_PROVIDER` must be one of `dashscope|deepseek|openai|luban`.
- `SESSION_STORE_BACKEND` / `AGENT_STATE_STORE_BACKEND` must be `memory|redis|postgres` (unknown values fail startup).
- `AGENT_EXECUTION_ADMISSION_ENABLED=true` requires both `AGENT_EXECUTION_STATE_DB_URL` and `AGENT_EXECUTION_ADMISSION_EPOCH` — otherwise startup raises `ValueError`.
- `AGENTSCOPE_COMPRESS_CONTEXT_ENABLED` requires `AGENTSCOPE_CONTEXT_TRIGGER_RATIO > 0.2` (agentscope `context_buffer_ratio`).
- `AGENTSCOPE_MODEL_ROUTER_ENABLED` with a non-empty candidate map requires `AGENTSCOPE_MODEL_ROUTER_MODEL`.
- Unknown store backends, invalid JSON in `AGENTSCOPE_MODEL_ROUTER_CANDIDATES`, and malformed delegated custody fields all fail closed.

### Defaults live in code, not in env files
The dev `runtime-config.env` files intentionally leave many knobs unset so code defaults apply (see comments like "Kernel tuning knobs intentionally unset in dev: code defaults apply"). This makes the code default the single source of truth for behavior when a variable is absent.

### Secrets are separate from config
Secrets (API keys, HMAC signing keys, client secrets, OTLP auth headers) are injected via Kubernetes Secrets, never ConfigMaps. The convention is a `<service>-runtime-secrets` Secret whose keys are mapped into the pod's environment. Cross-service shared secrets (delegation, audit, skills, incidents, execution signing/handoff) are generated by `sync-*-secrets.sh` and written to both sides simultaneously.

### Feature flags are environment-driven
Features are toggled via boolean env vars (e.g. `GATEWAY_BROWSER_ENABLED`, `GATEWAY_HTTP_ENABLED`, `GATEWAY_ANSIBLE_MCP_ENABLED`, `GATEWAY_SERVICENOW_ENABLED`, `AGENTSCOPE_MODEL_ROUTER_ENABLED`, `AGENTSCOPE_COMPRESS_CONTEXT_ENABLED`). Most are `false` by default and enabled per-feature via a Kustomize profile overlay. The portal exposes a curated read-only inventory of these flags through `GET /api/v1/runtime/flags` (SPEC-072), gated by `runtime:flags` policy.

### Policy bundle is config-as-code
The action-authorization bundle has exactly one canonical copy: `shared/shared-contracts/policies/policy-default.yaml`. It is replicated to both gateways by `make sync-policy`, and contract tests enforce parity via `make verify`. A missing or invalid bundle fails startup (`PolicyLoadError`); there is no silent fallback to the packaged default.

### GitOps profile selection
`select-runtime-profile.sh` chooses which Kustomize overlay to apply, and `deploy-overlay.sh` runs the full deploy. Profiles compose additively on top of `base/`, enabling features like browser automation, Ansible MCP, mutating tools, model routing, and delegated identity without editing base configs.

### Documentation is the spec
`docs/guides/configuration-reference.md` is the definitive cross-service environment variable dependency map. Each section cites the owning service's `config.py` and the corresponding `runtime-config.env` fragment, making the doc the authoritative registry of every variable, default, and source.

## Conventions and Constraints

- **Environment variables are the sole runtime configuration mechanism.** No YAML/JSON config files are parsed for runtime knobs; file paths (e.g. `GATEWAY_PASSWORD_POLICY_PATH`, `GATEWAY_BROWSER_CREDENTIAL_SETS`, `PLATFORM_GATEWAY_WORKLOAD_TOKEN_PATH`) point to pre-provisioned artifacts, not dynamic configuration.
- **Unknown enum values fail startup.** Store backends, providers, transport types, and other constrained choices raise `ValueError` rather than falling back.
- **Cross-service shared secrets must match.** The delegation chain requires `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` to equal the `platform-gateway` entry in `IDENTITY_SERVICE_CLIENTS`; audit, skills, and incident query chains have identical contracts. Mismatch is a deployment error, not a runtime negotiation.
- **Secrets are never committed.** All `*-runtime-secrets` are created by `sync-*-secrets.sh`; `.env.example` files exist only as templates.
- **No hot reload.** Policy bundles and ConfigMaps take effect only on pod restart; the docs explicitly state this and instruct rolling restarts of gateway deployments.
- **Feature toggles are opt-in and default-off.** Browser, HTTP, Ansible, ServiceNow, mutating tools, model routing, context compression, and delegated identity are all disabled by default and enabled via profile overlays.
- **Validation is in `__post_init__`, not lazy.** Every numeric bound, URL shape, and cross-field dependency is checked during settings construction so misconfiguration is caught before the service becomes ready.
- **The canonical policy bundle path is `/etc/luban/policy/policy.yaml`** for both gateways, loaded from the `PLATFORM_GATEWAY_POLICY_PATH` / `GATEWAY_POLICY_PATH` env var.