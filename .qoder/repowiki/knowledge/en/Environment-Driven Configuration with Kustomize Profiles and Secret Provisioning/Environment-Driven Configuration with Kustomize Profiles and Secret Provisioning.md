---
kind: configuration_system
name: Environment-Driven Configuration with Kustomize Profiles and Secret Provisioning
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/secrets-dev/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/ansible-dev/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/servicenow-dev/kustomization.yaml
    - shared/platform-ops/gitops/select-runtime-profile.sh
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/platform-ops/gitops/sync-browser-credentials.sh
    - shared/platform-ops/gitops/sync-servicenow-credentials.sh
    - shared/platform-ops/gitops/sync-ansible-credentials.sh
    - shared/platform-ops/gitops/sync-email-secrets.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
    - shared/shared-contracts/policies/policy-default.yaml
---

# Configuration System

## Approach

The Luban platform uses a **12-factor environment-variable configuration model** layered on top of Kubernetes ConfigMaps/Secrets, orchestrated by Kustomize overlays. There is no centralized config server or framework (no Pydantic Settings, no `python-dotenv` loader, no Consul/Vault client). Each service owns its own settings module that reads `os.environ` directly.

Configuration has three layers:

1. **Code defaults** — hard-coded in each service's `core/config.py` / `runtime_settings.py` as frozen dataclass fields (e.g. `DEFAULT_IDENTITY_SERVICE_URL`, `DEFAULT_BROWSER_CDP_ENDPOINT`). These are the safe baseline; production deployments override via env vars.
2. **Kustomize profile overlays** — under `shared/platform-ops/gitops/runtime-profiles/`. The active LLM profile (`default`) is selected via `select-runtime-profile.sh`; non-LLM postures (`mutating-dev`, `browser-dev`, `secrets-dev`, `ansible-dev`, `servicenow-dev`) merge additive env into the base `platform-runtime-config` ConfigMap without being switchable at runtime.
3. **Runtime secrets** — provisioned as K8s `Secret` objects by `sync-*` scripts under `shared/platform-ops/gitops/` (e.g. `sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-browser-credentials.sh`, `sync-servicenow-credentials.sh`, `sync-ansible-credentials.sh`, `sync-email-secrets.sh`, `sync-otel-secrets.sh`). Secrets are never committed to Git.

## Key Files and Packages

- Per-service settings modules: `products/agent-platform/src/agent_service/runtime_settings.py`, `products/tool-gateway/src/tool_gateway/core/config.py`, `products/platform-gateway/src/platform_gateway/core/config.py`, plus equivalent `core/config.py` files in `execution-runtime`, `identity-broker`, `audit-service`, `skills-hub`, `incident-service`.
- Dev-k8s env fragments: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` and `runtime-secrets.example.env` per service.
- Shared env: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (OTLP endpoint, shared identity URL).
- Profile overlays: `shared/platform-ops/gitops/runtime-profiles/{default,browser-dev,mutating-dev,secrets-dev,ansible-dev,servicenow-dev}/kustomization.yaml` + `.env` files.
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-*.sh`.
- Canonical policy bundle: `shared/shared-contracts/policies/policy-default.yaml`, synced to both gateways' packaged defaults and dev overlay via `make sync-policy`.
- Authoritative cross-service variable map: `docs/guides/configuration-reference.md`.

## Architecture and Conventions

### Settings modules
Each service exposes a frozen `@dataclass` settings object plus a `from_env()` classmethod and an `lru_cache(maxsize=1)`-wrapped `get_settings()` accessor. Boolean parsing accepts `{"1", "true", "yes", "on"}` (case-insensitive); optional values use helper functions like `_optional_str/_optional_int/_optional_bool/_optional_choice` (agent-service) or `_env_optional_int/_env_optional_tuple` (tool-gateway).

Validation happens in `__post_init__` (or `RuntimeSettings.__post_init__`), raising `ValueError` on invalid values so misconfiguration fails startup rather than degrading silently. Examples include:
- `GATEWAY_SECRET_DELIVERY_BACKEND` must be `memory` or `redis`.
- `GATEWAY_ANSIBLE_MCP_TRANSPORT` must be `streamable_http` or `stdio`.
- Password-policy overrides may only tighten the contract floor; weakening raises.
- `AGENT_EXECUTION_ADMISSION_ENABLED` requires both `AGENT_EXECUTION_STATE_DB_URL` and `AGENT_EXECUTION_ADMISSION_EPOCH`.
- `AGENTSCOPE_CONTEXT_TRIGGER_RATIO` must be in `(0, 0.9)` and above `0.2` when compression is enabled.

### Feature flags
Capabilities are opt-in via boolean env vars with deny-by-default semantics: `GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_BROWSER_ENABLED`, `GATEWAY_HTTP_ENABLED`, `GATEWAY_SECRETS_ENABLED`, `GATEWAY_ANSIBLE_MCP_ENABLED`, `GATEWAY_SERVICENOW_ENABLED`, `AGENT_MODEL_DISCOVERY_ENABLED`, `AGENT_EXECUTION_ADMISSION_ENABLED`, etc. An unset connector stays unregistered; it does not crash the service.

### Cross-service contracts
Inter-service credentials are paired via matching client_id/client_secret pairs documented in `configuration-reference.md`:
- Token delegation: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry for `platform-gateway`.
- Audit ingestion: each emitter's `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` registry.
- Skills query: `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`.
- Incident query: `*_INCIDENT_*_CLIENT_SECRET` ↔ `INCIDENT_QUERY_CLIENTS`.

These are generated once by `sync-*-secrets.sh` and mounted into every consumer's `*-runtime-secrets` K8s Secret.

### Policy bundle
There is exactly one canonical copy of the authorization policy: `shared/shared-contracts/policies/policy-default.yaml`. It is replicated byte-identically to `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` by `make sync-policy`. Contract tests fail `make verify` on any drift. Consumers load from `GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH` (default `/etc/luban/policy/policy.yaml`); a missing or invalid bundle fails startup (`PolicyLoadError`, no silent fallback). Bundles are cached keyed on path and do not hot-reload — pod restart is required.

### Runtime profiles
The agent-service supports pluggable LLM backends through Kustomize profile overlays. Only one LLM profile is active at a time, selected via `shared/platform-ops/gitops/select-runtime-profile.sh <profile-name>`. The profile label is decoupled from the provider since SPEC-026; provider selection is a ConfigMap knob (`AGENTSCOPE_PROVIDER`). Five non-LLM postures ride alongside permanently in dev-k8s and cannot be switched at runtime.

### Secrets
All secrets live in K8s `Secret` objects, never in Git. Each service has a `runtime-secrets.example.env` documenting expected keys. Some secrets are referenced via `secretKeyRef` in Deployments (e.g. `execution-signing-secret`, `execution-handoff-secret`); others are injected as env vars from ConfigMaps/Secrets. Credential-set JSON files (browser, HTTP, Ansible, ServiceNow) are mounted as read-only volumes at paths referenced by `GATEWAY_BROWSER_CREDENTIAL_SETS`, `GATEWAY_HTTP_CREDENTIAL_SETS`, `GATEWAY_ANSIBLE_MCP_CREDENTIAL_SETS`, `GATEWAY_SERVICENOW_CREDENTIAL_SETS`.

### OpenTelemetry
Shared across all pods via `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`: `OTEL_ENABLED=true`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and per-service `OTEL_EXPORTER_OTLP_HEADERS` (Basic auth) from each service's runtime-secrets Secret.

## Conventions and Constraints

- **Every setting is an environment variable.** No YAML/JSON/TOML config files are parsed at runtime by services; deployment manifests mount env from ConfigMaps/Secrets.
- **Deny-by-default feature flags.** New capabilities (browser tools, HTTP tools, secrets delivery, Ansible MCP, ServiceNow, mutating tools, durable admission) are off unless explicitly enabled.
- **Startup validation over runtime fallback.** Invalid enum values, out-of-range numbers, and missing required pairs raise `ValueError` during settings construction; services fail fast instead of running degraded.
- **Cross-service secrets are provisioned centrally.** `sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, and similar scripts generate random shared secrets and write them into every consumer's K8s Secret.
- **Policy bundle is single-source-of-truth.** Editing replicas directly is prohibited; `make sync-policy` enforces byte-identical copies, and `make verify` fails on drift.
- **No hot reload for policy bundles.** A changed ConfigMap takes effect only on pod restart (rolling restart the gateway deployments).
- **Secrets are never inline.** Credential sets are file paths mounted from K8s Secrets; SMTP passwords, API keys, HMAC keys, and bearer tokens come from `runtime-secrets` or `secretKeyRef`.
- **Dev vs prod posture separation.** Base overlays stay deny-by-default; dev-specific toggles live in `runtime-profiles/*-dev/kustomization.yaml` and merge additive env into the base ConfigMap.
- **Configuration reference is authoritative.** `docs/guides/configuration-reference.md` documents every environment variable, default, source, and cross-service dependency chain; new variables should be added there alongside code changes.