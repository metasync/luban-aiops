---
kind: configuration_system
name: Environment-Driven Settings with Frozen Dataclasses and GitOps Overlay Layering
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - docs/guides/configuration-reference.md
---

## Approach

Luban has no third-party configuration framework. Each FastAPI service owns its settings as a `frozen` Python `dataclass` with a classmethod `from_env()` that reads values from `os.environ`, applies defaults, performs range/enum validation in `__post_init__`, and exposes the instance through an `@lru_cache(maxsize=1)`-memoized `get_settings()` accessor. The agent-platform service additionally uses a hand-written `_optional_str/_int/_float/_bool/_choice` helper module rather than pydantic-settings.

Configuration is layered at deployment time via Kustomize overlays under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` (plain env files mounted as ConfigMaps) plus per-service `*-runtime-secrets` Kubernetes Secrets for sensitive values. A shared `shared/runtime.env` provides cluster-wide variables (`OTEL_*`, `IDENTITY_SERVICE_URL`). Per-feature runtime profiles live under `shared/platform-ops/gitops/runtime-profiles/<profile>/` (e.g. `browser-dev`, `ansible-dev`, `servicenow-dev`) and are selected by `select-runtime-profile.sh`; they overlay additional env vars on top of the base layer.

There is no hot reload: changing a ConfigMap or secret mount takes effect only after pod restart. Policy bundles are loaded once at startup from a file path (`GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH`, default `/etc/luban/policy/policy.yaml`); the canonical copy is `shared/shared-contracts/policies/policy-default.yaml` and is replicated byte-identically to both gateways' packaged defaults and the dev-k8s overlay by `make sync-policy`. Contract tests fail `make verify` on any drift.

## Key Files

- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` frozen dataclass, provider option types, all `AGENT*` / `AGENTSCOPE*` env parsing and validation.
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` frozen dataclass, connector feature flags (browser, http, secrets, ansible-mcp, servicenow, delegated-*), password policy tightening checks, credential-set path fallback chain.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` frozen dataclass, token delegation / audit / incident / skills proxy config.
- `products/execution-runtime/src/execution_runtime/core/config.py` — execution worker admission, signing key, handoff token.
- `products/identity-broker/src/identity_service/core/config.py` — Keycloak OIDC client, workload identity, client registry.
- `products/audit-service/src/audit_service/core/config.py` — ingest client registry, retention.
- `products/skills-hub/src/skills_hub/core/config.py` — federated source list, query client registry.
- `products/incident-service/src/incident_service/core/config.py` — webhook token, query client registry.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service env defaults mounted as ConfigMaps.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared OTel + identity broker URL.
- `shared/platform-ops/gitops/runtime-profiles/<profile>/` — feature profile overlays (browser-dev, ansible-dev, servicenow-dev, mutating-dev, delegated-dev).
- `docs/guides/configuration-reference.md` — authoritative cross-service environment variable dependency map, secret contracts, and provisioning procedures.

## Architecture and Conventions

1. **One settings module per service.** Each product ships a single `core/config.py` (or `runtime_settings.py` for agent-platform) that owns every env var it consumes. Consumers import `get_settings()` and never call `os.getenv` directly for application configuration.
2. **Frozen dataclasses with `from_env` + cached accessor.** Defaults live as class-level attributes; parsing lives in `from_env`; cross-field validation lives in `__post_init__`. `get_settings()` is memoized process-wide.
3. **Boolean parsing is uniform:** truthy strings are `{"1", "true", "yes", "on"}` (case-insensitive, stripped); unknown boolean values raise `ValueError` (agent-platform's `_optional_bool`) or are rejected by `__post_init__`.
4. **Feature flags are opt-in and deny-by-default.** Connector switches (`GATEWAY_BROWSER_ENABLED`, `GATEWAY_HTTP_ENABLED`, `GATEWAY_ANSIBLE_MCP_ENABLED`, `GATEWAY_SERVICENOW_ENABLED`, `GATEWAY_SECRETS_ENABLED`, `GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_DELEGATED_*_ENABLED`, `AGENT_EXECUTION_ADMISSION_ENABLED`, `AGENT_TARGET_AUTHORIZATION_ENABLED`) default to `false`; enabling them requires additional mandatory fields validated at startup.
5. **Allowlists are empty-by-default.** Origin allowlists (`GATEWAY_BROWSER_ALLOW_ORIGINS`, `GATEWAY_HTTP_ALLOW_ORIGINS`, `GATEWAY_EMAIL_RECIPIENT_ALLOWLIST`) default to empty tuples, which reject all requests unless explicitly populated.
6. **Secrets are never inline.** Credential paths point to mounted files (`credential-sets.json`, keyring JSON, mapping JSON). Inline credential values are never accepted from env vars; they come from Kubernetes Secrets provisioned by `sync-*-secrets.sh` scripts.
7. **Cross-service credentials use paired registries.** Every caller-side `*_CLIENT_ID` / `*_CLIENT_SECRET` must match an entry in the callee's registry (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`), documented as a contract in `configuration-reference.md` and enforced at runtime by the receiving service.
8. **GitOps overlay hierarchy.** Base env → runtime profile overlay → Kustomize merge into each Deployment's envFrom. Profile selection is explicit via `select-runtime-profile.sh`; there is no implicit profile discovery.
9. **Policy bundle is code-managed, not runtime-configured.** The canonical bundle is versioned YAML under `shared/shared-contracts/policies/`; `make sync-policy` replicates it, `make verify` asserts parity, and `make policy-diff` reports outcome transitions between bundles.
10. **Validation fails startup, never degrades silently.** Invalid enum values, out-of-range numbers, missing required fields for enabled features, and mismatched epochs all raise `ValueError` during settings construction. Missing optional dependencies degrade gracefully (e.g. unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing; unreachable audit-service degrades to log-only per the reference doc).

## Conventions and Constraints

- **Convention:** All runtime configuration is exposed as uppercase environment variables with a service-specific prefix (`AGENT*`, `GATEWAY*`, `PLATFORM_GATEWAY*`, `EXECUTION_*`, `AUDIT_*`, `SKILLS_*`, `INCIDENT_*`, `KEYCLOAK_*`, `OIDC_*`).
- **Convention:** Feature toggles follow the `<FEATURE>_ENABLED=true` naming pattern and default to `false`.
- **Convention:** Optional multi-value lists are comma-separated strings parsed into tuples (e.g. `GATEWAY_BROWSER_ALLOW_ORIGINS`, `GATEWAY_EMAIL_RECIPIENT_ALLOWLIST`, `GATEWAY_DELEGATED_IDENTITY_ACTORS`).
- **Convention:** Service URLs default to in-cluster DNS names (`http://agent-service:8000`, `http://tool-gateway:8000`, `http://identity-service:8000`) so deployments need no host override when services are colocated.
- **Constraint (startup validation):** Unknown backend names fail startup — e.g. `SESSION_STORE_BACKEND` rejects anything other than `memory|redis|postgres` (documented in configuration-reference.md); `GATEWAY_SECRET_DELIVERY_BACKEND` must be `memory` or `redis`; `GATEWAY_ANSIBLE_MCP_TRANSPORT` must be `streamable_http` or `stdio`; `AGENTSCOPE_PROVIDER` must be one of `dashscope|deepseek|openai|luban`.
- **Constraint (policy bundle):** A missing or invalid bundle at the configured path fails startup with `PolicyLoadError`; there is no silent fallback to a packaged default. Both gateways expose a SHA-256 fingerprint of the loaded bundle on `/health/ready`.
- **Constraint (cross-service secrets):** The `platform-gateway` ↔ `identity-service` delegation secret pair (`PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` vs `IDENTITY_SERVICE_CLIENTS`) must match exactly; provisioning is performed by `sync-delegation-secrets.sh` and documented as a hard contract in `configuration-reference.md`.
- **Constraint (delegated custody, SPEC-070):** Enabling `GATEWAY_DELEGATED_ACQUISITION_ENABLED` or `GATEWAY_DELEGATED_AUTHORIZATION_ENABLED` requires the full Postgres-custody runtime (DSN, keyring path, config path, set id, trusted HTTPS callback on the ratified `CALLBACK_PATH`) plus the delegated-human trust set; enabling without these raises `ValueError` at startup — there is no fallback to a machine grant.
- **Constraint (password policy overrides):** `GATEWAY_PASSWORD_MIN_LENGTH` and `GATEWAY_PASSWORD_REQUIRED_CLASSES` may only tighten the canonical contract in `tools/password_policy.py`; weakening overrides raise `ValueError` in `GatewaySettings.__post_init__`.
- **Constraint (config-as-code for dashboards):** Dashboard JSON under `shared/platform-ops/dashboards/` is validated by `make validate-dashboards` and applied by `apply-dashboards.sh`; rendering requires `OTEL_ENABLED=true` so mirrored domain metrics reach OpenObserve.
- **Constraint (no hot reload):** Policy bundles and most configuration take effect only on pod restart; the reference document states "there is deliberately no hot reload" for policy bundles.