---
kind: configuration_system
name: Configuration System — Environment-Driven Settings, Kustomize Profiles, and GitOps Secrets
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
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
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
---

## Approach

Luban is a Python monorepo with no centralized configuration framework. Each product service owns its own settings module that reads **environment variables** at startup via `os.getenv`, validates them in `__post_init__`, and exposes the result through an `lru_cache` singleton (`get_settings()`). There are no `.env` files committed to source; values come from Kubernetes ConfigMaps (non-secret) and Secrets (credentials), provisioned by scripts under `shared/platform-ops/gitops/sync-*.sh`.

The repository's single authoritative operator-facing reference is `docs/guides/configuration-reference.md`, which documents every variable per service, cross-service dependency chains, secret contracts, runtime profiles, and policy rollout procedure.

## Key Files

- Per-service settings modules:
  - `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass, provider options, all `AGENT*` / `AGENTSCOPE_*` env parsing and validation.
  - `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` + cached `get_settings()`.
  - `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` + cached `get_settings()`, including browser/http/secrets/ansible connectors.
  - `products/execution-runtime/src/execution_runtime/core/config.py`
  - `products/identity-broker/src/identity_service/core/config.py`
  - `products/audit-service/src/audit_service/core/config.py`
  - `products/skills-hub/src/skills_hub/core/config.py`
  - `products/incident-service/src/incident_service/core/config.py`
- Shared defaults: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (OTel endpoint, identity broker URL).
- Per-service dev overlays: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` and `runtime-secrets.example.env`.
- Runtime profile system: `shared/platform-ops/gitops/runtime-profiles/default/` plus `select-runtime-profile.sh`, `verify-runtime-profile.sh`.
- Secret provisioning scripts: `sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-browser-credentials.sh`, `sync-email-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`.
- Policy bundle canonical source: `shared/shared-contracts/policies/policy-default.yaml`, synced to both gateways' packaged defaults and the dev overlay via `make sync-policy`.

## Architecture and Conventions

1. **Environment-first settings.** Every service defines a frozen `dataclass` with typed defaults and a `from_env()` classmethod that maps environment variables to fields. Boolean flags accept `true/false/yes/on/1` (case-insensitive); optional strings/integers/floats return `None` when unset.
2. **Validation in `__post_init__`.** Invalid combinations fail startup rather than degrading silently — e.g. `AGENT_EXECUTION_ADMISSION_ENABLED=true` requires both `AGENT_EXECUTION_STATE_DB_URL` and `AGENT_EXECUTION_ADMISSION_EPOCH`; `AGENTSCOPE_COMPRESS_CONTEXT_ENABLED` requires `AGENTSCOPE_CONTEXT_TRIGGER_RATIO > 0.2`; password-policy overrides may only tighten the contract, never weaken it.
3. **Cached singleton access.** Gateway services expose `@lru_cache(maxsize=1)` `get_settings()` so the parsed config is loaded once per process.
4. **Kustomize profile overlays.** The agent-service supports pluggable LLM backends through Kustomize profiles under `shared/platform-ops/gitops/runtime-profiles/`. Only one profile is active at a time, selected via `select-runtime-profile.sh`. Two non-switchable postures (`mutating-dev`, `browser-dev`) merge extra env into `platform-runtime-config` on top of the base.
5. **ConfigMap + Secret split.** Non-secret knobs go in `<service>-runtime-config` ConfigMaps; secrets go in `<service>-runtime-secrets` Secrets. Examples live as `runtime-secrets.example.env` for each service.
6. **Secret provisioning scripts.** Cross-service shared secrets (delegation, audit, skills, incidents, execution signing/handoff, OTLP headers, browser credentials, email) are generated or rotated by dedicated `sync-*.sh` scripts under `shared/platform-ops/gitops/`, not committed to Git.
7. **Feature-flag pattern.** Most capabilities are opt-in via boolean env vars defaulting to `false` (e.g. `GATEWAY_BROWSER_ENABLED`, `GATEWAY_HTTP_ENABLED`, `GATEWAY_SECRETS_ENABLED`, `GATEWAY_MUTATING_TOOLS_ENABLED`, `AGENT_MODEL_DISCOVERY_ENABLED`). Deny-by-default is the norm for allowlists (origin lists, recipient allowlists, mutation tools).
8. **Cross-service credential registries.** Services that act as callers register a client id+secret pair against their target's registry: `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`. The format is documented in the configuration reference and enforced at the receiving service.
9. **Policy bundle as code.** The action-authorization bundle has exactly one canonical copy (`shared/shared-contracts/policies/policy-default.yaml`), replicated byte-identically to both gateways and the dev overlay by `make sync-policy`. Drift fails `make verify`; hot reload is intentionally absent — changes require a pod restart.
10. **OpenTelemetry push.** All services share `OTEL_ENABLED` and `OTEL_EXPORTER_OTLP_ENDPOINT` from `shared/runtime.env`; auth headers are injected per-service via `sync-otel-secrets.sh` into each service's runtime-secrets Secret.

## Conventions and Constraints

- **Observed convention:** Each service's settings are defined as a frozen `dataclass` with a `from_env()` constructor and an `lru_cache`-wrapped `get_settings()` accessor.
- **Observed convention:** Feature flags default to `false` (deny-by-default); enabling a feature requires setting its flag plus any required companion variables.
- **Observed convention:** Secrets are mounted as Kubernetes Secrets and referenced via environment variables; no inline secrets appear in ConfigMaps or source.
- **Enforced rule:** Unknown backend names for store selection (`SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `SECRET_DELIVERY_BACKEND`, etc.) raise `ValueError` at startup — see the corresponding `_optional_choice` / `__post_init__` checks in each service's config.
- **Enforced rule:** Enabling `AGENT_EXECUTION_ADMISSION_ENABLED` without both `AGENT_EXECUTION_STATE_DB_URL` and `AGENT_EXECUTION_ADMISSION_EPOCH` raises `ValueError` (startup failure, not silent fallback) — enforced in `RuntimeSettings.__post_init__`.
- **Enforced rule:** Password-policy env overrides (`GATEWAY_PASSWORD_MIN_LENGTH`, `GATEWAY_PASSWORD_REQUIRED_CLASSES`) may only tighten the canonical policy; weakening values raise `ValueError` in `GatewaySettings.__post_init__`.
- **Enforced rule:** `AGENTSCOPE_COMPRESS_CONTEXT_ENABLED` requires `AGENTSCOPE_CONTEXT_TRIGGER_RATIO > 0.2` (agentscope's `context_buffer_ratio`); otherwise startup raises `ValueError`.
- **Enforced rule:** `AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS` must be > 0 and ≤ 120; bounds are validated in `RuntimeSettings.__post_init__`.
- **Enforced rule:** `AGENTSCOPE_TIMEZONE` must be a valid IANA timezone name; invalid values raise `ValueError` during construction.
- **Enforced rule:** Unsupported `AGENTSCOPE_PROVIDER` values raise `ValueError` listing the supported set `{dashscope, deepseek, openai, luban}`.
- **Enforced rule:** Policy bundles loaded from `PLATFORM_GATEWAY_POLICY_PATH` / `GATEWAY_POLICY_PATH` — if missing or invalid, startup fails with `PolicyLoadError` (no silent fallback to the packaged default).
- **Enforced rule:** Cross-service client registries (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`) must match the caller's configured client id and secret; mismatches cause authentication failures at the receiver.
- **Enforced rule:** The policy bundle is maintained as a single canonical file under `shared/shared-contracts/policies/policy-default.yaml`; replicas in `products/*/policies/` and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` must stay byte-identical, verified by `make verify`.
- **Enforced rule:** Runtime profiles are switched exclusively via `shared/platform-ops/gitops/select-runtime-profile.sh <profile-name>`; two posture overlays (`mutating-dev`, `browser-dev`) are permanently merged and not switchable.